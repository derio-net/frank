---
paper: 10-self-hosted-inference
status: draft
---

## Vendors in scope (≥3, typically 4–6)
- name: Ollama
  positioning: "Run open models locally with a single binary — Modelfile abstraction over llama.cpp + GGUF."
  primary_url: "https://ollama.com"
- name: vLLM
  positioning: "Throughput-optimised LLM serving with PagedAttention — the engine many SaaS providers run."
  primary_url: "https://docs.vllm.ai"
- name: llama.cpp / llama-server
  positioning: "CPU-first OSS inference — GGUF quantization, runs on a Raspberry Pi as easily as a laptop."
  primary_url: "https://github.com/ggml-org/llama.cpp"
- name: HuggingFace TGI (Text Generation Inference)
  positioning: "Production-grade transformer inference server — continuous batching, tensor parallelism."
  primary_url: "https://huggingface.co/docs/text-generation-inference"
- name: LiteLLM
  positioning: "OSS gateway/proxy — virtual keys, cost tracking, OpenAI-compatible routing across ~100 providers."
  primary_url: "https://docs.litellm.ai"
- name: OpenRouter
  positioning: "Managed gateway-as-a-service — pay-per-token aggregation across hosted models, no infra to run."
  primary_url: "https://openrouter.ai"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Efficient Memory Management for Large Language Model Serving with PagedAttention"
  type: paper
  url: "https://arxiv.org/abs/2309.06180"
  quoted_passages:
    - "We propose PagedAttention, an attention algorithm inspired by the classical virtual memory and paging techniques in operating systems."
    - "On top of it, we build vLLM, an LLM serving system that achieves (1) near-zero waste in KV cache memory and (2) flexible sharing of KV cache within and across requests to further reduce memory usage."
    - "Evaluations on various models and workloads show that vLLM improves the throughput of popular LLMs by 2-4× compared with the state-of-the-art systems, such as FasterTransformer and Orca, with the same level of latency."
  relevance: "Foundational paper for vLLM. Defines why PagedAttention beats naive KV-cache layouts under batched workloads — the load-bearing throughput argument for §3 and §4 of the paper. Anchors the 'why are SaaS providers running vLLM' claim."

- title: "Ollama README & Modelfile reference"
  type: vendor-docs
  url: "https://github.com/ollama/ollama"
  quoted_passages:
    - "Get up and running with large language models locally."
    - "Ollama provides the simplest way to run large language models on your own hardware. It packages model weights, configuration, and data into a single Modelfile."
    - "OLLAMA_KEEP_ALIVE — Set the duration that models stay loaded in memory (default: 5m, e.g. '24h' to keep loaded indefinitely)."
  relevance: "Vendor's own articulation of what Ollama actually is — a llama.cpp wrapper with a Modelfile abstraction and an OpenAI-shaped API. Pairs with the dated Frank incident in §5 where OLLAMA_KEEP_ALIVE pinned the cgroup RAM ceiling and made VRAM look like the bottleneck."

- title: "LiteLLM virtual keys, budgets & rate limits"
  type: vendor-docs
  url: "https://docs.litellm.ai/docs/proxy/virtual_keys"
  quoted_passages:
    - "Track Spend, set budgets and create virtual keys for the proxy."
    - "Maintain different rate limits per user/key/team."
    - "Prometheus Metrics — Available on Enterprise. Track LiteLLM usage metrics, with: Total spend on a per-user, model, team basis. Token usage per user, model, team. Rate limit errors."
  relevance: "Vendor's articulation of the gateway pattern as Frank uses it: virtual keys, cost tracking, OpenAI-compatible routing. Critically, the page itself documents that Prometheus metrics are an Enterprise feature — the load-bearing 'marketing-vs-reality' gap for §5 carries a direct citation, not just a Frank gotcha."

- title: "vLLM v0.6.0: 2.7× Throughput Improvement and 5× Latency Reduction"
  type: benchmark
  url: "https://blog.vllm.ai/2024/09/05/perf-update.html"
  quoted_passages:
    - "vLLM v0.6.0 delivers up to 2.7x higher throughput and 5x faster TPOT compared to v0.5.3, on Llama 8B model. The performance is measured on ShareGPT dataset using a single H100 GPU."
    - "For Llama 70B and a single H100, vLLM v0.6.0 delivers 1.8× higher throughput, with TPOT reduced from 200ms to 100ms."
    - "Across H100, A100, A10 GPUs, vLLM consistently outperforms TGI and TensorRT-LLM."
  relevance: "Reproducible benchmark with named hardware (H100, A100, A10), named workload (ShareGPT), and named comparators (TGI, TensorRT-LLM). Anchors the throughput claim in §3 and the 'datacenter-scale benchmarks don't speak to the homelab regime' gap in §4. The 2.7× / 5× numbers are quotable."

- title: "Simon Willison — Notes on running LLMs locally (llm-pricing tag)"
  type: postmortem
  url: "https://simonwillison.net/tags/llm-pricing/"
  quoted_passages:
    - "One of the most notable trends from 2024 was the total collapse in terms of LLM pricing — the API models are absurdly inexpensive now."
    - "Generating captions for 68,000 photos using Gemini 1.5 Flash 8B costs $1.68."
    - "Llama 3.2 3B from a developer's perspective: running locally on my laptop using Ollama, it's blazingly fast — about 100 tokens per second on my M2 Mac."
  relevance: "Named practitioner running OSS LLMs at small scale and tracking the API-price collapse in real time. Critical counterweight for §1 and §6 — the 'just use the API' counter-argument is grounded in numbers Simon has actually paid. Pairs with the data-locality / latency-floor / learning-depth triple in §5."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/litellm/values.yaml"
  date: 2026-05-15
  demonstrates: "The gateway pattern as Frank lives it: LiteLLM OSS image at v1.83.14-stable, virtual model catalog driven by a separate ConfigMap, Ollama as upstream provider on gpu-1. The values file is the literal source of truth for the §3 'Frank's stack' diagram."

- kind: commit
  path_or_url: "https://github.com/derio-net/frank/commits/main/apps/litellm"
  date: 2026-04-22
  demonstrates: "The LiteLLM main-v1.83.14-stable bump together with the discovery that `litellm_*` Prometheus metrics are Enterprise-only. The Grafana panels stayed empty for two weeks before anyone noticed — the dated incident is the load-bearing scar for §5."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md#gpu-1-specifics"
  date: 2026-04-08
  demonstrates: "OLLAMA_KEEP_ALIVE cgroup-RAM incident: Ollama emitted 'system memory' errors that read like VRAM exhaustion; the real cause was the container cgroup memory ceiling because OLLAMA_KEEP_ALIVE had pinned the model in the page cache near `resources.limits.memory`. High-value scar artefact — proves the gateway/engine stack has cgroup-level failure modes that don't show up in vendor docs."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md#argo-rollouts"
  date: 2026-04-29
  demonstrates: "Argo Rollouts canary tuning for LiteLLM: the Prometheus provider panics on empty result vectors, retries at 10s cadence, aborts in ~50s; AnalysisTemplate has no `inconclusiveCondition` field. Real production scar from putting a canary in front of the gateway — shows the gateway tier inherits the observability tier's bugs."

- kind: grafana-screenshot
  path_or_url: "docs/papers-dossiers/10-self-hosted-inference/inference-dashboard-TODO.png"
  date: 2026-05-19
  demonstrates: "Frank's local-inference Grafana dashboard at 192.168.55.203 — latency, tokens/sec, GPU utilisation. Placeholder committed from the worktree; replace from a cluster-connected machine before publish. The empty `litellm_*` panels prove the §5 scar in pixels, not prose."

## Diagrams planned
- landscape:
    x_axis: "engine ↔ gateway"
    y_axis: "self-hosted ↔ managed"
    vendors_plotted: ["Ollama", "vLLM", "llama.cpp", "HuggingFace TGI", "LiteLLM", "OpenRouter"]
- architecture_comparison:
    vendors: ["Ollama", "vLLM", "llama.cpp / TGI", "LiteLLM / OpenRouter"]
- decision_tree:
    leaves: 4
    description: "Question: should I self-host inference in 2026? Branches on data-locality requirement, concurrent-user load, and operator time. Terminates in: OpenAI/OpenRouter API, Ollama + LiteLLM (Frank's choice), vLLM cluster, or 'don't — the question was wrong'."

## Named gaps (≥1)
- "No published head-to-head latency + cost benchmark for Ollama vs vLLM vs llama.cpp at ≤2 concurrent users on a single consumer GPU (e.g. 16GB GDDR7). Public benchmarks assume datacenter GPUs (H100, A100) and batched workloads; the small-scale homelab regime is under-served by the literature. Frank cannot fill this gap from a single GPU without a real comparative measurement run."
- "LiteLLM OSS emits no `litellm_*` Prometheus metrics — gateway observability at the OSS tier requires synthesising signals from access logs or upstream model-server metrics. No vendor-side documentation acknowledges this gap clearly outside the virtual-keys page footnote."

## Counter-arguments considered (≥1)
- "Just use the OpenAI API — why doesn't that win? For most production teams it does: the API is cheaper than amortised GPU capex below ~24/7 utilisation (Simon Willison's $1.68/68k-captions number is the canonical proof), faster on the frontier-model curve, and the SLA is someone else's problem. Self-hosted wins on three axes only: data-locality (the prompt never leaves your network), latency floor (no internet round-trip on the hot path), and learning depth (you see the GPU memory map, the cgroup ceilings, and the gateway-tier gotchas in your own logs). Frank chose self-hosted to pay the learning tax in full — and the empty `litellm_*` panels in §5 are exactly the receipt for that choice."
