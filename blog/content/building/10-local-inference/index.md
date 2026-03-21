---
title: "Local Inference — Ollama, LiteLLM, and OpenRouter"
date: 2026-03-09
draft: false
tags: ["ollama", "litellm", "openrouter", "llm", "inference", "gpu", "ai"]
summary: "A unified OpenAI-compatible gateway that routes between a local RTX 5070 running Ollama and free cloud models via OpenRouter — one API for everything."
weight: 11
cover:
  image: cover.png
  alt: "Frank the cluster monster routing LLM requests between a local GPU and cloud models"
  relative: true
---

The cluster has a GPU. Layer 4 installed the NVIDIA operator. Layer 5 gave the mini nodes their Intel iGPUs. But none of that is useful until something actually runs inference.

Layer 10 wires up a unified LLM gateway. Any tool on the network — agentic frameworks, document processors, coding assistants — talks to one OpenAI-compatible endpoint at `192.168.55.206:4000`. Behind that endpoint, requests route to either a local model on gpu-1's RTX 5070 or a free cloud model via OpenRouter. The consumer never needs to know which.

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
    |       |-- qwen3.5:9b  (default, kept warm)
    |       +-- deepseek-coder:6.7b  (on-demand)
    |
    +---> OpenRouter (cloud)
            +-- qwen3-coder, hermes-405b, gemma-27b,
                mistral-small, llama-70b, step-flash
```

Any consumer that speaks OpenAI's API format works out of the box:

```bash
OPENAI_API_BASE=http://192.168.55.206:4000/v1
OPENAI_API_KEY=<litellm-virtual-key>
```

## Why Not Just Ollama?

Ollama alone handles local models well. But the moment you want cloud fallback, multiple consumers with different keys, or spend tracking, you need a routing layer. LiteLLM adds that without changing how consumers connect.

It also means model migration is invisible to consumers. If a cloud model gets retired or a better local model appears, you update LiteLLM's config. No consumer reconfiguration.

## Local Models: What Fits in 12GB?

The RTX 5070 has 12GB of VRAM. That is the hard constraint. Ollama quantizes models to Q4 by default, which cuts memory roughly in half.

Two models are available:

| Model | Size (Q4) | Context | Best For |
|-------|-----------|---------|----------|
| `qwen3.5:9b` | 6.6 GB | 256K | General-purpose, multimodal, tool calling |
| `deepseek-coder:6.7b` | ~4 GB | 16K | Code generation and completion |

Only one model stays loaded in VRAM at a time (`OLLAMA_MAX_LOADED_MODELS=1`). The default model is kept warm for 24 hours (`OLLAMA_KEEP_ALIVE=24h`). Switching to the other model takes about 5 seconds — Ollama unloads one and loads the other from the Longhorn PVC.

This is a deliberate trade-off. Loading two models simultaneously would leave each with less VRAM for KV cache, reducing effective context length. For a homelab with low concurrency, fast swapping is better than degraded context.

### Why Not the Mini iGPUs?

The three mini nodes each have an Intel Arc iGPU. These share system RAM instead of having dedicated VRAM — which makes them unsuitable for LLM inference where memory bandwidth is the bottleneck. Their value is in media and vision workloads: hardware video transcode via Quick Sync, object detection via OpenVINO, and general OpenCL compute.

## Cloud Models: The Free Tier Treadmill

OpenRouter aggregates providers and offers free tiers for many models. The catch: free model availability shifts constantly. Models get promoted, retired, or rate-limited without notice. This is a maintenance concern, not an architectural one.

The current free model roster (as of March 2026):

| Alias | Model | Context | Strengths | Data Policy |
|-------|-------|---------|-----------|-------------|
| `qwen3-coder` | Qwen3 Coder 480B MoE | 262K | Coding, reasoning | Alibaba Cloud; may retain |
| `hermes-405b` | Hermes 3 (Llama 3.1 405B) | 131K | General purpose, instruction following | Open-weight |
| `gemma-27b` | Gemma 3 27B | 131K | General purpose, vision | Open-weight |
| `mistral-small` | Mistral Small 3.1 24B | 128K | Fast, coding | Open-weight |
| `llama-70b` | Llama 3.3 70B Instruct | 128K | Strong all-rounder | Open-weight |
| `step-flash` | Step 3.5 Flash 196B MoE | 256K | Reasoning | Prompts retained |

The data policy column matters. Some free providers train on prompts. The config comments document this per model so you can make informed choices about what you send where.

### Keeping the List Current

We built a `/update-openrouter-models` command that automates the refresh cycle: query the OpenRouter API for current free models, compare against the config, replace retired ones, deploy, and verify. Run it when models start returning 404s.

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
    pull:
      - qwen3.5:9b
      - deepseek-coder:6.7b

extraEnv:
  - name: OLLAMA_KEEP_ALIVE
    value: "24h"
  - name: OLLAMA_MAX_LOADED_MODELS
    value: "1"

persistentVolume:
  enabled: true
  size: 30Gi
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
    - model_name: qwen3.5
      litellm_params:
        model: ollama/qwen3.5:9b
        api_base: http://ollama.ollama.svc.cluster.local:11434

    - model_name: qwen3-coder
      litellm_params:
        model: openrouter/qwen/qwen3-coder:free
        api_key: os.environ/OPENROUTER_API_KEY
```

LiteLLM resolves `os.environ/OPENROUTER_API_KEY` at runtime from the pod's environment, which is injected by the ExternalSecret.

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

## What is Next

**Update:** The GPU Operator fix landed. The RTX 5070 Ti is running Ollama at 100% GPU with 15.9 GiB VRAM. Local models are live. See [GPU Containers on Talos — The Validation Fix]({{< relref "/building/12-gpu-talos-fix" >}}) for the full debugging story.

Any consumer on the network can use `192.168.55.206:4000` today — both local GPU models and cloud fallback are operational.
