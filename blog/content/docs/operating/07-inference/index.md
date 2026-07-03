---
title: "Operating on Local Inference"
series: ["operating"]
date: 2026-03-13
draft: false
tags: ["operations", "ollama", "litellm", "openrouter", "ai"]
summary: "Day-to-day commands for managing local LLM inference, checking model status, routing through LiteLLM, and debugging GPU memory issues."
weight: 8
---

This is the operational companion to [Local Inference — Ollama, LiteLLM, and OpenRouter]({{< relref "/docs/building/10-local-inference" >}}). That post explains the architecture and deployment. This one is the day-to-day runbook for keeping models running, routing requests, and troubleshooting GPU memory issues.

## What "Healthy" Looks Like

The inference stack is healthy when Ollama is running on gpu-1 with at least one model loaded, LiteLLM at `192.168.55.206:4000` is responding to health checks, and requests route correctly to either the local GPU or OpenRouter cloud models depending on the model name.

> **Canonical health signal — the end-to-end probe.** gpu-1 time-shares its single GPU between
> Ollama (inference) and ComfyUI (media), so inference is **down by design** whenever the GPU is
> handed to ComfyUI — that is not an outage. The Ops board reads the real state from a blackbox
> probe that runs an actual chat completion through LiteLLM: `probe_success{layer="11"}` (VMUI,
> VictoriaMetrics datasource) is `1` only when a completion truly succeeds. A `0` with ComfyUI
> holding the GPU is the expected quiet-degraded tile; a `0` with **both** `gpu_timeshare` probes
> at `0` is the only condition that pages (`gpu-node-both-down`). Check ownership with
> `kubectl -n ollama get deploy ollama` (`0/0` = it yielded the GPU). Note: `kube_pod_status_ready`
> is *not* a valid inference health check — it is blind to Ollama scaled to 0.

## Observing State

### Ollama Status

```bash
# Check the Ollama pod is running
kubectl get pods -n ollama

# List loaded models
kubectl exec -n ollama deploy/ollama -- ollama list

# Check which model is currently in memory
kubectl exec -n ollama deploy/ollama -- ollama ps

# Check GPU memory usage
kubectl exec -n ollama deploy/ollama -- nvidia-smi
```

### LiteLLM Gateway

```bash
# Health check
curl -s http://192.168.55.206:4000/health | jq

# List available models (both local and cloud)
curl -s http://192.168.55.206:4000/v1/models | jq '.data[].id'

# Check LiteLLM pod logs
kubectl logs -n litellm deploy/litellm --tail=50
```

```console
$ curl -s http://192.168.55.206:4000/health/liveliness
"I'm alive!"
$ kubectl -n litellm get pods -o wide
NAME                       READY   STATUS    RESTARTS   AGE   IP              NODE     NOMINATED NODE   READINESS GATES
litellm-84d78cd556-rglgl   1/1     Running   0          25d   10.244.8.237    mini-3   <none>           <none>
litellm-postgresql-0       1/1     Running   0          28d   10.244.12.161   mini-1   <none>           <none>
```

### GPU Memory

```bash
# Detailed GPU utilization
kubectl exec -n ollama deploy/ollama -- nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
```

> Only one model is loaded in VRAM at a time on the RTX 5070 Ti (16 GB GDDR7). Switching models means the old one gets evicted.

## Routine Operations

### Pull or Remove Models

```bash
# Pull a new model
kubectl exec -n ollama deploy/ollama -- ollama pull qwen3:14b

# Remove a model to free disk space
kubectl exec -n ollama deploy/ollama -- ollama rm qwen2.5-coder:14b-instruct-q6_K
```

> Do not use `postStart` hooks for model pulls on Talos — the nvidia-container-runtime exec hooks fail. Always pull via `kubectl exec` after the pod is running.

### Test Inference

```bash
# Quick test via LiteLLM (routes to Ollama via the LiteLLM alias, not the Ollama tag)
curl -s http://192.168.55.206:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-small-24b",
    "messages": [{"role": "user", "content": "Hello, one sentence reply."}],
    "max_tokens": 50
  }' | jq '.choices[0].message.content'

# Direct Ollama test (bypassing LiteLLM — uses the Ollama tag, not the alias)
kubectl exec -n ollama deploy/ollama -- curl -s http://localhost:11434/api/generate \
  -d '{"model": "mistral-small3.2:24b", "prompt": "Hello", "stream": false}' | jq '.response'

# Multimodal test — send an image to gemma-12b
curl -s http://192.168.55.206:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-12b",
    "messages": [{"role": "user", "content": [
      {"type": "text", "text": "Describe this image in one sentence."},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    ]}]
  }' | jq '.choices[0].message.content'
```

### Check LiteLLM Routing

```bash
# See which models route where
kubectl get configmap -n litellm litellm-config -o yaml | grep -A 5 'model_name'
```

### OpenRouter Free Models (retired)

The cluster no longer routes to OpenRouter free models — the policy is local Ollama or a paid frontier key only. The `/update-openrouter-models` command that used to refresh the free-model list has been retired with them. If you are reading this with a config that still lists `openrouter/*:free` models, it predates the purge: remove them rather than refresh them.

## Debugging

### Ollama Not Responding

```bash
# Check pod status and events
kubectl describe pod -n ollama -l app.kubernetes.io/name=ollama

# Check if GPU is allocated
kubectl describe node gpu-1 | grep -A 5 "nvidia.com/gpu"

# Check Ollama logs
kubectl logs -n ollama deploy/ollama --tail=100
```

### Out of Memory: which kind?

Ollama emits **two error patterns** that both look like "out of memory" but have different root causes. Mis-identify which one you're hitting and you'll waste a lot of time trying smaller quants when the issue is something else entirely.

**Pattern A — VRAM exhaustion** (real GPU OOM): the model genuinely doesn't fit in the 16 GB on the RTX 5070 Ti, or you're trying to load two models at once. Diagnose with:

```bash
kubectl exec -n ollama deploy/ollama -- nvidia-smi --query-gpu=memory.used,memory.free --format=csv
```

If `memory.free` is < 1 GB, you have a real VRAM problem. Fix: stop the current model and pull a smaller quant.

```bash
kubectl exec -n ollama deploy/ollama -- ollama stop mistral-small3.2:24b
kubectl exec -n ollama deploy/ollama -- ollama pull qwen2.5-coder:14b-instruct-q4_K_M
```

**Pattern B — container cgroup RAM exhaustion** (the misleading one): the error message reads `model requires more system memory (X GiB) than is available (Y MiB)`. "System memory" here means **container RAM**, not VRAM — and `nvidia-smi` will show plenty of VRAM free. With `OLLAMA_KEEP_ALIVE=24h`, page cache from previously-loaded model files pins the container near its `resources.limits.memory` ceiling, leaving no room for new-model load buffers. Diagnose with:

```bash
kubectl exec -n ollama deploy/ollama -- sh -c 'cat /sys/fs/cgroup/memory.current; echo; cat /sys/fs/cgroup/memory.max'
```

If `memory.current` is within ~1–2 GiB of `memory.max`, that's the constraint. Fix: bump `resources.limits.memory` in `apps/ollama/values.yaml`. Reducing `num_ctx` via a derived Modelfile will **not** help here — the bottleneck is at-load buffers, not the KV cache, so the error is identical at 32K and 8K context.

### Reconciling LiteLLM Aliases vs. Ollama Tags

Two name spaces are in play. LiteLLM aliases (`mistral-small-24b`, `gemma-12b`, `qwen-vl-7b`, `qwen-coder-14b`, `qwen-think-14b`) live in `apps/litellm/values.yaml` under `model_list[].model_name` — these are what consumers send. Ollama tags (`mistral-small3.2:24b`, `qwen2.5-coder:14b-instruct-q6_K`, etc.) live under `model_list[].litellm_params.model` — these are what Ollama pulls and runs. If a request returns "model not found", check both: either the alias is wrong on the consumer side, or the underlying Ollama tag was never pulled.

```bash
# What aliases does LiteLLM advertise?
curl -s http://192.168.55.206:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq '.data[].id'

# What Ollama tags actually exist on disk?
kubectl exec -n ollama deploy/ollama -- ollama list
```

### LiteLLM Routing Errors

```bash
# Check LiteLLM logs for routing failures
kubectl logs -n litellm deploy/litellm --tail=100 | grep -i error

# Verify Ollama is reachable from LiteLLM
kubectl exec -n litellm deploy/litellm -- curl -s http://ollama.ollama.svc:11434/api/tags | jq '.models[].name'
```

### Model Loading Very Slow

Large models can take 30-60 seconds to load into VRAM. Check `nvidia-smi` to see if memory is being allocated. If the model doesn't fit, Ollama falls back to CPU which is extremely slow — this looks like a hang but is actually just CPU inference.

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
- [OpenRouter Documentation](https://openrouter.ai/docs/)
- [Building Post — Local Inference]({{< relref "/docs/building/10-local-inference" >}})
