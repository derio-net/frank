# Local Inference Gateway — Design

**Date:** 2026-03-09

## Overview

Deploy a unified LLM inference gateway across Frank that routes between local models (served by Ollama on gpu-1) and free cloud models (via OpenRouter). All consumers — agentic frameworks, tools like AnythingLLM, Paperless-ngx, etc. — talk to a single OpenAI-compatible API endpoint and never need to know where inference happens.

## Stack

| Component | Tool | Role |
|-----------|------|------|
| Local inference | Ollama | Serves models on gpu-1's RTX 5070 |
| API gateway | LiteLLM | Unified routing, virtual keys, spend tracking |
| Cloud provider | OpenRouter | Aggregator for free-tier cloud models |
| Secrets | Infisical + ExternalSecret | API key injection |
| Storage | Longhorn PVC | Ollama model persistence |

## Architecture

```
Consumers (AnythingLLM, Paperless-ngx, agentic frameworks, etc.)
    │
    ▼
LiteLLM Gateway (192.168.55.206:4000)
    │  unified OpenAI-compatible API
    │  virtual keys, spend tracking, rate limits
    │
    ├──► Ollama (gpu-1, ClusterIP)
    │       ├── qwen3.5:9b  (default, kept warm)
    │       └── deepseek-coder:6.7b  (on-demand)
    │
    └──► OpenRouter (cloud)
            └── DeepSeek R1, Gemini Flash, Devstral 2,
                Llama 3.3 70B, GPT-OSS 120B, Step 3.5 Flash
```

### Design Decisions

- **gpu-1 only for inference** — The mini nodes' Intel Arc iGPUs are unsuitable for LLM inference (shared memory, immature driver support). Their value is in media/vision workloads (transcoding, object detection, computer vision). The minis' 64GB RAM could serve as CPU fallback, but the added complexity isn't justified at this stage.
- **Ollama over vLLM** — Simpler model management, broad hardware support, good enough throughput for homelab concurrency. vLLM is overkill at this scale.
- **LiteLLM as gateway** — Mature OpenAI-compatible proxy with built-in multi-tenancy primitives (virtual keys, per-key budgets). When Phase 10 (vCluster) lands, tenant isolation is a configuration concern, not an architectural change.
- **OpenRouter as sole cloud provider** — Single API key provides access to all major cloud models. No direct Anthropic API (Max subscription cannot legally be used as API proxy per Anthropic ToS, February 2026).

## Ollama Deployment

**ArgoCD App:** `ollama`
**Namespace:** `ollama`
**Chart:** `otwld/ollama-helm` (community Helm chart)

**Scheduling:**
- `nvidia.com/gpu: 1` resource request — claims RTX 5070 and ensures gpu-1 placement
- Toleration for gpu-1's NoSchedule taint

**Storage:**
- Longhorn PVC: 30GB at `/root/.ollama` (covers both models with room to grow)

**Configuration:**
- `OLLAMA_KEEP_ALIVE=24h` — keeps default model loaded in VRAM between requests
- `OLLAMA_MAX_LOADED_MODELS=1` — avoids accidental VRAM pressure on 12GB card

**Models (auto-pulled on startup):**
- `qwen3.5:9b` (6.6GB Q4) — default general-purpose; multimodal, 256K context, tool calling, thinking mode
- `deepseek-coder:6.7b` (~4GB Q4) — code generation; swapped in on-demand (~5s cold load)

**Service:** ClusterIP on port 11434 (internal only)

## LiteLLM Deployment

**ArgoCD App:** `litellm`
**Namespace:** `litellm`
**Chart:** `litellm/litellm` (official Helm chart)

**Service:** LoadBalancer at `192.168.55.206`, port 4000

**Secrets (via Infisical → ExternalSecret):**
- `OPENROUTER_API_KEY`
- `LITELLM_MASTER_KEY`

**Consumer usage:**
```
OPENAI_API_BASE=http://192.168.55.206:4000/v1
OPENAI_API_KEY=<litellm-virtual-key>
```

### Model Routing Config

```yaml
model_list:
  # ──────────────────────────────────────────────
  # LOCAL MODELS (Ollama on gpu-1)
  # ──────────────────────────────────────────────

  # Qwen 3.5 9B — default general-purpose model
  # Multimodal (text+image), 256K context, tool calling, thinking mode
  # Runs fully in VRAM on RTX 5070 (6.6GB Q4)
  - model_name: qwen3.5
    litellm_params:
      model: ollama/qwen3.5:9b
      api_base: http://ollama.ollama.svc.cluster.local:11434

  # DeepSeek Coder 6.7B — code generation and completion
  # Swapped in on-demand (~5s cold load)
  - model_name: deepseek-coder
    litellm_params:
      model: ollama/deepseek-coder:6.7b
      api_base: http://ollama.ollama.svc.cluster.local:11434

  # ──────────────────────────────────────────────
  # CLOUD MODELS — Free tier via OpenRouter
  # Rate limit: 20 req/min, 200 req/day per model
  # ──────────────────────────────────────────────

  # DeepSeek R1 — 671B MoE (37B active), reasoning model
  # Visible chain-of-thought, on par with OpenAI o1
  # ⚠ Data: Chinese servers, prompts may train models, no opt-out
  - model_name: deepseek-r1
    litellm_params:
      model: openrouter/deepseek/deepseek-r1:free
      api_key: os.environ/OPENROUTER_API_KEY

  # Gemini 2.0 Flash Exp — 1M context, long document processing
  # ⚠ Data: Google experimental; prompts may train future models
  - model_name: gemini-flash
    litellm_params:
      model: openrouter/google/gemini-2.0-flash-exp:free
      api_key: os.environ/OPENROUTER_API_KEY

  # Devstral 2 — Mistral's 123B dense coding model, 256K context
  # Agentic coding, multi-file project understanding
  # ⚠ Data: Mistral Experiment plan; prompts may train models
  - model_name: devstral
    litellm_params:
      model: openrouter/mistralai/devstral-2512:free
      api_key: os.environ/OPENROUTER_API_KEY

  # Llama 3.3 70B — Meta's general-purpose open model, 128K context
  # Strong all-rounder, Apache-like license
  # ✅ Data: Open-weight, served by third-party; check provider policy
  - model_name: llama-70b
    litellm_params:
      model: openrouter/meta-llama/llama-3.3-70b-instruct:free
      api_key: os.environ/OPENROUTER_API_KEY

  # GPT-OSS 120B — OpenAI's open-weight MoE (5.1B active), 131K context
  # Designed for agentic and general-purpose production use
  # ✅ Data: Open-weight (Apache 2.0), served by third-party
  - model_name: gpt-oss
    litellm_params:
      model: openrouter/openai/gpt-oss-120b:free
      api_key: os.environ/OPENROUTER_API_KEY

  # Step 3.5 Flash — StepFun's 196B MoE (11B active), 256K context
  # Reasoning model, strong general-purpose
  # ⚠ Data: Training disabled, but prompts retained by StepFun
  - model_name: step-flash
    litellm_params:
      model: openrouter/stepfun/step-3.5-flash:free
      api_key: os.environ/OPENROUTER_API_KEY

litellm_settings:
  default_model: qwen3.5
```

### Model Summary

| Model Name | Provider | Context | Best For | Data Policy |
|------------|----------|---------|----------|-------------|
| `qwen3.5` | Local (Ollama) | 256K | General, multimodal | Private — never leaves cluster |
| `deepseek-coder` | Local (Ollama) | 16K | Code generation | Private — never leaves cluster |
| `deepseek-r1` | DeepSeek (free) | 164K | Reasoning | ⚠ CN servers, may train |
| `gemini-flash` | Google (free) | 1M | Long documents | ⚠ Experimental, may train |
| `devstral` | Mistral (free) | 256K | Agentic coding | ⚠ May train on prompts |
| `llama-70b` | Meta (free) | 128K | General purpose | ✅ Open-weight |
| `gpt-oss` | OpenAI (free) | 131K | Agentic tasks | ✅ Open-weight (Apache 2.0) |
| `step-flash` | StepFun (free) | 256K | Reasoning | ⚠ Prompts retained |

## ArgoCD Integration

### File Structure

```
apps/ollama/values.yaml              # Ollama Helm values
apps/litellm/values.yaml             # LiteLLM Helm values (includes model config)
apps/litellm/manifests/              # ExternalSecret CRs for API keys
apps/root/templates/ollama.yaml      # Ollama Application CR
apps/root/templates/litellm.yaml     # LiteLLM Application CR
```

### Sync Policy (both apps)

```yaml
syncPolicy:
  automated:
    prune: false
    selfHeal: true
  syncOptions:
    - ServerSideApply=true
    - RespectIgnoreDifferences=true
```

### Secrets Flow

```
Infisical (secret store)
    │
    ▼
ExternalSecret CR (litellm namespace)
    │
    ▼
K8s Secret → mounted as env vars in LiteLLM pod
```

## Exposure

| Service | IP | Port | Access |
|---------|-----|------|--------|
| LiteLLM Gateway | 192.168.55.206 | 4000 | LoadBalancer (Cilium L2) |
| Ollama | ClusterIP | 11434 | Internal only |
