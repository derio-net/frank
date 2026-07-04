---
title: "Local Inference — Ollama, LiteLLM, and OpenRouter"
series: ["building"]
layer: infer
date: 2026-03-09
draft: false
tags: ["ollama", "litellm", "openrouter", "llm", "inference", "gpu", "ai"]
summary: "A unified OpenAI-compatible gateway that routes between a local RTX 5070 Ti running Ollama and free cloud models via OpenRouter — one API for everything."
weight: 11
---

The cluster has a GPU. Layer 4 installed the NVIDIA operator. Layer 5 gave the mini nodes their Intel iGPUs. But none of that is useful until something actually runs inference.

Layer 10 wires up a unified LLM gateway. Any tool on the network — agentic frameworks, document processors, coding assistants — talks to one OpenAI-compatible endpoint at `192.168.55.206:4000`. Behind that endpoint, requests route to either a local model on gpu-1's RTX 5070 Ti or a free cloud model via OpenRouter. The consumer never needs to know which.

## The Architecture

Three components:

**[Ollama](https://ollama.com)** runs on gpu-1 and serves local models. It manages model downloads, VRAM allocation, and the inference runtime. It exposes a ClusterIP on port 11434 — internal only.

**[LiteLLM](https://litellm.ai)** is the gateway. It presents a single OpenAI-compatible API and routes requests to the right backend based on the model name in the request. It also handles virtual API keys, spend tracking, and rate limiting. It runs on any non-GPU node.

**[OpenRouter](https://openrouter.ai)** aggregates cloud model providers behind one API key. Free-tier models have limits (20 requests/minute, 200/day per model), but that is plenty for a homelab.

```
Consumers (AnythingLLM, Paperless-ngx, agentic frameworks, etc.)
    |
    v
LiteLLM Gateway (192.168.55.206:4000)
    |  unified OpenAI-compatible API
    |  virtual keys, spend tracking, rate limits
    |
    |---> Ollama (gpu-1, ClusterIP)
    |       |-- mistral-small3.2:24b   (default, kept warm)
    |       |-- gemma3:12b             (multimodal — vision general)
    |       |-- qwen2.5vl:7b-q8_0      (multimodal — OCR/structured)
    |       |-- qwen2.5-coder:14b q6   (code)
    |       +-- qwen3:14b              (reasoning, thinking mode)
    |
    +---> OpenRouter (cloud, free tier)
            +-- gemma-31b, nemotron-vl-12b, nemotron-omni-30b,
                qwen-next-80b, qwen-coder-480b, hermes-405b
```

Any consumer that speaks OpenAI's API format works out of the box:

```bash
OPENAI_API_BASE=http://192.168.55.206:4000/v1
OPENAI_API_KEY=<litellm-virtual-key>
```

## Why Not Just Ollama?

Ollama alone handles local models well. But the moment you want cloud fallback, multiple consumers with different keys, or spend tracking, you need a routing layer. LiteLLM adds that without changing how consumers connect.

It also means model migration is invisible to consumers. If a cloud model gets retired or a better local model appears, you update LiteLLM's config. No consumer reconfiguration.

## Local Models: What Fits in 16GB?

The RTX 5070 Ti has 16GB of GDDR7. That is the hard constraint. Ollama quantizes models to Q4 by default, which cuts memory roughly in half — but at 16GB there is enough headroom to upgrade specific models to Q6 or Q8 where it matters.

Five models in the current lineup, each chosen to fit alongside ~1.5GB of KV cache (and, for vision models, a ~1.4GB vision tower):

| Alias | Tag | Quant | VRAM | Context | Best For |
|-------|-----|-------|------|---------|----------|
| `mistral-small-24b` | `mistral-small3.2:24b` | Q4_K_M | ~14 GB | 128K | Default general-purpose, function calling |
| `gemma-12b` | `gemma3:12b` | Q4_K_M | ~9 GB | 128K | Multimodal — general vision, screenshots, charts |
| `qwen-vl-7b` | `qwen2.5vl:7b-q8_0` | Q8_0 | ~9 GB | 128K | Multimodal — OCR, tables, scanned docs |
| `qwen-coder-14b` | `qwen2.5-coder:14b-instruct-q6_K` | Q6_K | ~12 GB | 32K | Code generation and completion |
| `qwen-think-14b` | `qwen3:14b` | Q4_K_M | ~10 GB | 32K | Reasoning with native thinking mode |

Only one model stays loaded in VRAM at a time (`OLLAMA_MAX_LOADED_MODELS=1`). The default model is kept warm for 24 hours (`OLLAMA_KEEP_ALIVE=24h`). Switching takes about 5 seconds — Ollama unloads one and loads the other from the Longhorn PVC.

This is a deliberate trade-off. Loading multiple models simultaneously would leave each with less VRAM for KV cache, reducing effective context length. For a homelab with low concurrency, fast swapping is better than degraded context.

### Why Two Multimodal Models?

`gemma-12b` and `qwen-vl-7b` look redundant on paper — both are vision models that fit in VRAM. They are not. Gemma 3's vision tower was trained on a wide image corpus and excels at "what is in this picture": general visual reasoning, screenshots, photographs. Qwen2.5-VL was specifically trained on structured visual content — tables, charts with dense text, scanned documents — and produces noticeably more accurate OCR. Picking one would force every vision request through a model that is wrong for half the cases.

### Why Q6 for the Coder?

Code is the one place where quantization quality is measurable in production. At Q4_K_M, 14B-class coding models produce more syntax errors and forget API surface details. At Q6_K the model uses ~3GB more VRAM but the error rate drops noticeably. The 16GB budget makes that trade-off available; the 12GB original config didn't.

### Why Not the Mini iGPUs?

The three mini nodes each have an Intel Arc iGPU. These share system RAM instead of having dedicated VRAM — which makes them unsuitable for LLM inference where memory bandwidth is the bottleneck. Their value is in media and vision workloads: hardware video transcode via Quick Sync, object detection via OpenVINO, and general OpenCL compute.

## Cloud Models: The Free Tier Treadmill

OpenRouter aggregates providers and offers free tiers for many models. The catch: free model availability shifts constantly. Models get promoted, retired, or rate-limited without notice. This is a maintenance concern, not an architectural one.

The current free model roster (refreshed May 2026 — see "Refresh" below):

| Alias | Model | Context | Modalities | Strengths | Data Policy |
|-------|-------|---------|------------|-----------|-------------|
| `gemma-31b` | Gemma 4 31B Instruct | 256K | text + image + video | Flagship multimodal, function calling, 140+ langs | Open-weight |
| `nemotron-vl-12b` | NVIDIA Nemotron Nano 2 VL | 128K | text + image + video | Document intelligence, video understanding | Open-weight |
| `nemotron-omni-30b` | NVIDIA Nemotron 3 Nano Omni 30B | 256K | text + image + video + audio | Multimodal + reasoning | Open-weight |
| `qwen-next-80b` | Qwen3 Next 80B A3B Instruct | 262K | text | Strong reasoning, coding, math | Alibaba; may retain |
| `qwen-coder-480b` | Qwen3 Coder 480B MoE | 262K | text | Frontier coding | Alibaba; may retain |
| `hermes-405b` | Hermes 3 (Llama 3.1 405B) | 131K | text | Largest open-weight backstop | Open-weight |

The data policy column matters. Some free providers train on prompts. The config comments document this per model so you can make informed choices about what you send where.

### Keeping the List Current

We built a `/update-openrouter-models` command that automated the refresh cycle: query the OpenRouter API for current free models, compare against the config, replace retired ones, deploy, and verify. Run it when models start returning 404s — for as long as that lasted.

> **Retired.** The cluster later dropped OpenRouter free models entirely (local Ollama or a paid frontier key only — the free tier's churn and data-policy fine print stopped being worth the maintenance), and the command went with them. That is a five-stage pipeline that terminates in nothing; we keep this section because the *pattern* — verify against the provider's live API, not its marketing page — outlived the command.

## Deploying Ollama

Ollama uses the [community Helm chart](https://github.com/otwld/ollama-helm) via ArgoCD:

```yaml
# apps/ollama/values.yaml (abbreviated)
ollama:
  gpu:
    enabled: true
    type: nvidia
    number: 1
  models:
    pull: []   # pulled on first request via LiteLLM
    run: []

extraEnv:
  - name: OLLAMA_KEEP_ALIVE
    value: "24h"
  - name: OLLAMA_MAX_LOADED_MODELS
    value: "1"

persistentVolume:
  enabled: true
  size: 200Gi   # 5-model shelf ≈ 55GB at rest, with experimentation room
  storageClass: longhorn

tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
```

The GPU resource request and toleration ensure Ollama lands on gpu-1 — the only node with an NVIDIA GPU and the corresponding NoSchedule taint.

## Deploying LiteLLM

LiteLLM uses two ArgoCD apps — one for the Helm chart, one for the ExternalSecret manifest:

| App | Source | Purpose |
|-----|--------|---------|
| `litellm` | OCI Helm chart (`docker.litellm.ai/berriai/litellm-helm`) | Gateway + PostgreSQL |
| `litellm-extras` | `apps/litellm/manifests/` | ExternalSecret for API keys |

The model routing config lives in `values.yaml` under `proxy_config.model_list`. Each model entry maps an alias to a backend:

```yaml
proxy_config:
  model_list:
    - model_name: mistral-small-24b
      litellm_params:
        model: ollama/mistral-small3.2:24b
        api_base: http://ollama.ollama.svc.cluster.local:11434

    - model_name: qwen-coder-480b
      litellm_params:
        model: openrouter/qwen/qwen3-coder:free
        api_key: os.environ/OPENROUTER_API_KEY
```

LiteLLM resolves `os.environ/OPENROUTER_API_KEY` at runtime from the pod's environment, which is injected by the ExternalSecret.

{{< asciinema src="litellm-stream.cast" cols="180" rows="8" >}}

### Secrets Flow

```
Infisical (192.168.55.204)
    |
    v
ExternalSecret "litellm-api-keys" (litellm namespace)
    |  syncs: OPENROUTER_API_KEY, LITELLM_MASTER_KEY
    v
K8s Secret --> env vars in LiteLLM pod
```

No plaintext secrets in the repo. The ExternalSecret refreshes every 5 minutes.

## Gotchas

### LiteLLM Image Tags

The LiteLLM Helm chart generates an image tag from the chart version (e.g., `main-v1.81.13`). That tag does not exist on GHCR. Override it explicitly:

```yaml
image:
  repository: ghcr.io/berriai/litellm-database
  tag: main-stable
  pullPolicy: Always
```

### LoadBalancer IP Pinning

The LiteLLM chart does not expose a `service.loadBalancerIP` field. Use a Cilium annotation instead:

```yaml
service:
  type: LoadBalancer
  annotations:
    lbipam.cilium.io/ips: "192.168.55.206"
```

### Free Model Churn

During deployment, four of the six originally selected cloud models had already been retired from OpenRouter's free tier. The models that replaced them were verified against the live API (`/api/v1/models`) rather than the marketing page. Trust the API, not the website.

## Multi-tenancy

LiteLLM has built-in virtual key management. Each consumer gets its own key with optional per-key budgets and rate limits. When multi-tenancy via vCluster arrives in a future layer, tenant isolation is a configuration concern — not an architectural change.

## Refresh — May 2026

The original lineup (`qwen3.5:9b`, `deepseek-coder:6.7b`, plus a six-model OpenRouter shelf) was assembled before the GPU Operator fix landed. Two things changed since:

1. **The card had 16GB all along.** The first version of this post said "12GB" because that is the spec for the non-Ti RTX 5070 — but gpu-1 actually runs the Ti variant with 16GB GDDR7. The 4GB extra unlocked the 24B class at Q4 (Mistral Small 3.2) and let the coder model jump to Q6 quantization.
2. **The OpenRouter free tier had churned.** Mistral Small 3.1 and Step Flash were no longer free; Qwen3-Next, Nemotron-VL, Nemotron-Omni, and Gemma 4 had appeared. The `/update-openrouter-models` skill confirmed the live list against `/api/v1/models`.

The replacement strategy:
- Move Mistral Small 24B from cloud to local — the 16GB card can run it.
- Add two local multimodal models (Gemma 3 12B for general vision, Qwen2.5-VL 7B at Q8 for OCR), removing the old text-only-only constraint.
- Replace the aging cloud shelf with three multimodal options (Gemma 4 31B, Nemotron-VL, Nemotron-Omni) plus a stronger reasoning option (Qwen3-Next 80B).
- Drop `deepseek-coder:6.7b` and `omnicoder:9b` in favor of one stronger `qwen2.5-coder:14b` at Q6.
- Bump the Ollama PVC from 30Gi to 200Gi — the new lineup occupies ~55GB at rest, and disk is no longer scarce.

Aliases changed in this refresh — consumers using the old names (`qwen3.5`, `deepseek-coder`, `mistral-small`, `gemma-27b`, `llama-70b`, `step-flash`) need to update to the new ones (`mistral-small-24b`, `qwen-coder-14b`, `gemma-31b`, etc.). The data-policy comments per model are kept and re-verified against each provider's current terms.

## Refresh — June 2026

The multimodal slot moved generations: `gemma3:12b` → `gemma4:12b` (2026-06-05). The alias stayed `gemma-12b`, so no consumer changed a line of config. What the swap actually took:

1. **An Ollama runtime bump first.** The chart's default image (0.17.7) predates the Gemma 4 architecture — `ollama pull gemma4:12b` refuses before downloading a byte. Support landed in Ollama 0.30.3, but 0.30.3/0.30.4 shipped a floating-point-exception crash on exactly this model; the pin went straight to 0.30.5 (`image.tag` in `apps/ollama/values.yaml`).
2. **Validation before the cutover, on the failure modes that matter:** text generation, vision/OCR against a real dashboard screenshot, and — the one that historically breaks — `stream: true` + `tools` on the native `/api/chat` path. Gemma 4 populated `tool_calls` cleanly with zero scaffolding JSON leaked into `content`.
3. **One behavioral change to know about:** Gemma 4 12B is a thinking model. The CLI shows a reasoning preamble before the answer; over the API the reasoning stays out of `content`, but time-to-first-token is longer than gemma3's was.

Q4_K_M is 7.6GB on disk (gemma3 was 8.1GB), context ceiling rose from 128K to 256K upstream — still server-capped at 16K by `OLLAMA_CONTEXT_LENGTH` on the 16GB card. `gemma3:12b` was deleted from the PVC after the LiteLLM gateway verified end-to-end on the new backend.

## What is Next

Any consumer on the network can use `192.168.55.206:4000` today — local GPU models, multimodal vision (local + cloud), and frontier-scale reasoning (cloud) are all operational behind one OpenAI-compatible endpoint.
