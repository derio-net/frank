---
title: "Operating on Local Inference"
series: ["operating"]
layer: infer
date: 2026-03-13
draft: false
tags: ["operations", "ollama", "litellm", "openrouter", "ai", "troubleshooting"]
summary: "Day-to-day commands for managing local LLM inference, checking model status, routing through LiteLLM, and debugging GPU memory issues."
weight: 8
reader_goal: "Manage Ollama models, test inference through LiteLLM, diagnose GPU memory issues (VRAM vs cgroup RAM), and resolve routing errors between LiteLLM aliases and Ollama tags."
diataxis: [how-to, reference]
last_updated: 2026-07-15
last_updated_commit: https://github.com/derio-net/frank/commit/a8bed9a1d358b7ad87bb6dcaa9b0162e5fb0e127
---

{{< last-updated >}}

This is the operational companion to [Local Inference — Ollama, LiteLLM, and OpenRouter]({{< relref "/docs/building/10-local-inference" >}}). That post explains the architecture and deployment. This one is the day-to-day runbook for keeping models running, routing requests, and troubleshooting GPU memory issues.

Source your environment:

```bash
source .env
```

## What "Healthy" Looks Like

The inference stack is healthy when Ollama is running on gpu-1 with at least one model loaded, LiteLLM at `192.168.55.206:4000` is responding to health checks, and requests route correctly.

**Canonical health signal — the end-to-end probe.** gpu-1 time-shares between Ollama (inference) and ComfyUI (media), so inference is *down by design* when the GPU is handed to ComfyUI. The Ops board reads real state from a blackbox probe: `probe_success{layer="11"}` (VMUI, VictoriaMetrics datasource) is `1` only when a completion truly succeeds. A `0` with ComfyUI holding the GPU is the expected quiet-degraded tile; a `0` with **both** `gpu_timeshare` probes at `0` pages (`gpu-node-both-down`). Check ownership with `kubectl -n ollama get deploy ollama` (`0/0` = it yielded the GPU). Note: `kube_pod_status_ready` is *not* a valid inference health check — it is blind to Ollama scaled to 0.

### Verify

```bash
# LiteLLM health
curl -s http://192.168.55.206:4000/health/liveliness

# Ollama has a model loaded
kubectl exec -n ollama deploy/ollama -- ollama ps

# GPU allocated
kubectl describe node gpu-1 | grep -A 5 "nvidia.com/gpu"
```

## Observing State

### Ollama Status

```bash
kubectl get pods -n ollama
kubectl exec -n ollama deploy/ollama -- ollama list
kubectl exec -n ollama deploy/ollama -- ollama ps
kubectl exec -n ollama deploy/ollama -- nvidia-smi
```

### LiteLLM Gateway

```bash
curl -s http://192.168.55.206:4000/health | jq
curl -s http://192.168.55.206:4000/v1/models | jq '.data[].id'
kubectl logs -n litellm deploy/litellm --tail=50
```

```console
$ curl -s http://192.168.55.206:4000/health/liveliness
"I'm alive!"
```

### GPU Memory

```bash
kubectl exec -n ollama deploy/ollama -- nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
```

Only one model is loaded in VRAM at a time on the RTX 5070 Ti (16 GB GDDR7). Switching models evicts the old one.

## Routine Operations

### Pull or Remove Models

```bash
kubectl exec -n ollama deploy/ollama -- ollama pull qwen3:14b
kubectl exec -n ollama deploy/ollama -- ollama rm qwen2.5-coder:14b-instruct-q6_K
```

Do not use `postStart` hooks for model pulls on Talos — the nvidia-container-runtime exec hooks fail. Always pull via `kubectl exec` after the pod is running.

### Test Inference

```bash
# Via LiteLLM (routes to Ollama via the alias)
curl -s http://192.168.55.206:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-small-24b",
    "messages": [{"role": "user", "content": "Hello, one sentence reply."}],
    "max_tokens": 50
  }' | jq '.choices[0].message.content'

# Direct Ollama test (bypassing LiteLLM — uses the Ollama tag)
kubectl exec -n ollama deploy/ollama -- curl -s http://localhost:11434/api/generate \
  -d '{"model": "mistral-small3.2:24b", "prompt": "Hello", "stream": false}' | jq '.response'
```

### Check LiteLLM Routing

```bash
kubectl get configmap -n litellm litellm-config -o yaml | grep -A 5 'model_name'
```

## Runbook

### Ollama Not Responding

```bash
kubectl describe pod -n ollama -l app.kubernetes.io/name=ollama
kubectl describe node gpu-1 | grep -A 5 "nvidia.com/gpu"
kubectl logs -n ollama deploy/ollama --tail=100
```

### Out of Memory: Which Kind?

Ollama emits two error patterns that both look like "out of memory" but have different root causes.

**Pattern A — VRAM exhaustion:** the model genuinely doesn't fit in 16 GB. Diagnose:

```bash
kubectl exec -n ollama deploy/ollama -- nvidia-smi --query-gpu=memory.used,memory.free --format=csv
```

If `memory.free` is < 1 GB, stop the current model and pull a smaller quant:

```bash
kubectl exec -n ollama deploy/ollama -- ollama stop mistral-small3.2:24b
kubectl exec -n ollama deploy/ollama -- ollama pull qwen2.5-coder:14b-instruct-q4_K_M
```

**Pattern B — container cgroup RAM exhaustion (misleading):** the error reads `model requires more system memory (X GiB) than is available (Y MiB)`. "System memory" means container RAM, not VRAM — `nvidia-smi` will show plenty of VRAM free. With `OLLAMA_KEEP_ALIVE=24h`, page cache from previously-loaded model files pins the container near its `resources.limits.memory` ceiling. Diagnose:

```bash
kubectl exec -n ollama deploy/ollama -- sh -c 'cat /sys/fs/cgroup/memory.current; echo; cat /sys/fs/cgroup/memory.max'
```

If `memory.current` is within ~1–2 GiB of `memory.max`, bump `resources.limits.memory` in `apps/ollama/values.yaml`. Reducing `num_ctx` will **not** help — the bottleneck is at-load buffers, not the KV cache.

### LiteLLM Aliases vs. Ollama Tags

Two name spaces are in play. LiteLLM aliases (`mistral-small-24b`, `gemma-12b`) live in `apps/litellm/values.yaml` under `model_list[].model_name`. Ollama tags (`mistral-small3.2:24b`) live under `model_list[].litellm_params.model`. If a request returns "model not found", check both:

```bash
# What aliases does LiteLLM advertise?
curl -s http://192.168.55.206:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq '.data[].id'

# What Ollama tags exist on disk?
kubectl exec -n ollama deploy/ollama -- ollama list
```

### LiteLLM Routing Errors

```bash
kubectl logs -n litellm deploy/litellm --tail=100 | grep -i error
kubectl exec -n litellm deploy/litellm -- curl -s http://ollama.ollama.svc:11434/api/tags | jq '.models[].name'
```

## Missteps

| What we assumed | Why it was wrong | What it cost |
|-----------------|------------------|-------------|
| `kube_pod_status_ready` is a valid inference health check | It's blind to Ollama scaled to 0 (GPU yielded to ComfyUI) | False inference-down alerts until switching to the blackbox probe (`probe_success{layer="11"}`). |
| PostStart hooks work on Talos for model pulls | The nvidia-container-runtime exec hook conflicts with Talos's containerd config | All model pulls must happen manually via `kubectl exec` after the pod is running. |
| "Out of memory" always means VRAM exhaustion | Container cgroup RAM can also be the bottleneck, especially with long `OLLAMA_KEEP_ALIVE` | Wasted time trying smaller quants when the fix was bumping `resources.limits.memory`. |
| LiteLLM alias names match Ollama tag names | Two independent name spaces — aliases are in `model_name`, tags in `litellm_params.model` | "Model not found" errors until both were checked. |

## Quick Reference

| Command | What It Does |
|---------|-------------|
| `kubectl exec -n ollama deploy/ollama -- ollama list` | List downloaded models |
| `kubectl exec -n ollama deploy/ollama -- ollama ps` | Show model currently in memory |
| `kubectl exec -n ollama deploy/ollama -- ollama pull <model>` | Download a model |
| `kubectl exec -n ollama deploy/ollama -- ollama rm <model>` | Delete a model |
| `kubectl exec -n ollama deploy/ollama -- nvidia-smi` | Check GPU memory usage |
| `curl http://192.168.55.206:4000/health` | LiteLLM health check |
| `curl http://192.168.55.206:4000/v1/models` | List available models |
| `kubectl logs -n litellm deploy/litellm` | LiteLLM proxy logs |
| `kubectl logs -n ollama deploy/ollama` | Ollama server logs |

## References

- [Ollama API Reference](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [LiteLLM Documentation](https://docs.litellm.ai/)
- [Building Post — Local Inference]({{< relref "/docs/building/10-local-inference" >}})
