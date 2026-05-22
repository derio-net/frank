---
paper: 16-media-generation
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: ComfyUI
  positioning: "Node-graph diffusion frontend — every step (load checkpoint, encode prompt, sample, decode VAE, save) is a node you wire by hand. Workflows are JSON artefacts. Frank's choice."
  primary_url: "https://docs.comfy.org/"
- name: AUTOMATIC1111 Stable Diffusion WebUI
  positioning: "Monolith web UI — the original community frontend; txt2img / img2img / extras tabs, deepest extension ecosystem, no node graph."
  primary_url: "https://github.com/AUTOMATIC1111/stable-diffusion-webui"
- name: InvokeAI
  positioning: "Commercial-leaning OSS — opinionated UX, canvas-first workflow, paid hosted tier, OSS core. Node graph available but secondary to the canvas."
  primary_url: "https://invoke-ai.github.io/InvokeAI/"
- name: Fooocus
  positioning: "Opinionated single-button SDXL pipeline — Midjourney-like ergonomics, hidden complexity, no node graph, no plugin ecosystem by design."
  primary_url: "https://github.com/lllyasviel/Fooocus"
- name: Replicate (cloud API)
  positioning: "Pay-per-second managed inference for community models — image, audio, video. The OSS-models-on-someone-else's-GPU option."
  primary_url: "https://replicate.com/docs"
- name: Midjourney / DALL-E (cloud, closed)
  positioning: "Managed, closed-weight image-gen APIs — best-in-class aesthetics, zero infra, no node graph, no weights you can pull. The 'just use the API' null hypothesis."
  primary_url: "https://docs.midjourney.com/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "ComfyUI Documentation"
  type: vendor-docs
  url: "https://docs.comfy.org/"
  quoted_passages:
    - "The most powerful open source node-based application for generative AI."
    - "Understand workflows, nodes, and links."
  relevance: "Establishes ComfyUI's positioning as a node-graph frontend and the canonical mental model — workflow = directed graph of nodes connected by typed links."
- title: "ComfyUI GitHub README"
  type: vendor-docs
  url: "https://github.com/comfyanonymous/ComfyUI"
  quoted_passages:
    - "The most powerful and modular AI engine for content creation."
    - "ComfyUI is designed for visual professionals who demand control over every model, every parameter, and every output."
  relevance: "Vendor self-description that motivates the node graph: control over every model, every parameter, every output. Anchors §1 (what this is)."
- title: "High-Resolution Image Synthesis with Latent Diffusion Models (Rombach et al., 2022)"
  type: paper
  url: "https://arxiv.org/abs/2112.10752"
  quoted_passages:
    - "We apply them in the latent space of powerful pretrained autoencoders... significantly reducing computational requirements compared to pixel-based DMs."
    - "By introducing cross-attention layers into the model architecture, we turn diffusion models into powerful and flexible generators for general conditioning inputs such as text or bounding boxes."
  relevance: "The foundational paper that made consumer-GPU image generation possible. Every vendor in scope is downstream of this architecture; §3 architecture comparisons all collapse to 'which latent-diffusion variant + which conditioning hooks'."
- title: "Black Forest Labs FLUX repository"
  type: benchmark
  url: "https://github.com/black-forest-labs/flux"
  quoted_passages:
    - "FLUX.1 is an open-weight model suite for image generation and editing tasks."
  relevance: "The current open-weight benchmark above SDXL. Frank pulls FLUX-dev checkpoints into ComfyUI; the vendor's release notes calibrate the seconds-per-image bar and the VRAM floor (FLUX-dev needs ~16 GB just for the model weights, which is why Frank cannot run Ollama and FLUX concurrently on a 16 GB RTX 5070 Ti)."
- title: "Frank gpu-1 gotchas — Ollama RAM pinning"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/docs/runbooks/frank-gotchas/gpu-1.md"
  quoted_passages:
    - "Ollama 'system memory' errors mean container cgroup RAM (not VRAM) — OLLAMA_KEEP_ALIVE page cache pins the cgroup near resources.limits.memory."
    - "With OLLAMA_KEEP_ALIVE=24h page cache from previously-loaded models pins the cgroup near its resources.limits.memory ceiling."
  relevance: "The first scar of running diffusion + LLM on one consumer GPU. Establishes that GPU contention on a 16 GB consumer card surfaces as RAM errors before it surfaces as VRAM errors — the runbook entry that motivated the GPU Switcher's existence."
- title: "ComfyUI custom-image design spec (Frank)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/docs/superpowers/specs/2026-03-16--media--comfyui-custom-image-design.md"
  quoted_passages:
    - "Seven concrete problems with the stock ai-dock image, none patchable from values.yaml."
  relevance: "The decision record for replacing ai-dock/comfyui with a 60-line custom Dockerfile. Lists the seven concrete problems (broken Caddy proxy, wrong env var names, supervisord with cloudflared, ComfyUI v0.2.2 unable to load Flux, PyTorch 2.4.1+cu121 with no sm_120 for Blackwell, outdated Manager, permission mismatch). Anchors §5 scar callout 2."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "https://github.com/derio-net/frank/blob/main/apps/comfyui/manifests/deployment.yaml"
  date: 2026-03-16
  demonstrates: "Why ComfyUI ships at zero replicas and is woken by an external controller — single consumer GPU cannot host LLM + diffusion model concurrently. Deployment pins to gpu-1 via nodeSelector, requests nvidia.com/gpu: 1, sets strategy: Recreate (RWO PVC), uses custom image ghcr.io/derio-net/comfyui:comfyui-v0.9.2-pt2.10.0-cu128, defensive nvidia.com/gpu:NoSchedule toleration, fsGroup: 1000."
- kind: yaml
  path_or_url: "https://github.com/derio-net/frank/blob/main/apps/comfyui/docker/Dockerfile"
  date: 2026-03-16
  demonstrates: "Why off-the-shelf ai-dock/comfyui:latest-cuda had to be replaced — broken Caddy template, wrong env var names, supervisord with cloudflared+SSH+Jupyter, ComfyUI v0.2.2 unable to load Flux, PyTorch 2.4.1+cu121 with no sm_120 Blackwell support. Custom CUDA 12.8 base image with PyTorch 2.10.0+cu128, ComfyUI v0.9.2, ComfyUI-Manager 4.x as a pip package (NOT in custom_nodes/), uid 1000:1000 non-root."
- kind: yaml
  path_or_url: "https://github.com/derio-net/frank/blob/main/apps/gpu-switcher/app/main.go"
  date: 2026-03-16
  demonstrates: "How a ~150-line Go HTTP service replaces K8s primitives that don't exist for single consumer GPUs — no Time-Slicing, no MIG, no 'schedule this OR that, never both'. API contract: POST /api/activate/{ollama|comfyui}, POST /api/deactivate, GET /api/status. The Switcher is the smallest possible workaround that enforces single-GPU exclusivity by scaling Deployments between 0 and 1."
- kind: incident
  path_or_url: "https://github.com/derio-net/frank/blob/main/docs/runbooks/frank-gotchas/gpu-1.md"
  date: 2026-03-16
  demonstrates: "GPU contention isn't only about VRAM — cgroup RAM, container limits, and PVC mount order all surface as 'GPU' errors when a workload shares a node. The Ollama 'system memory' misdiagnosis: OLLAMA_KEEP_ALIVE=24h page cache pinned container cgroup RAM near resources.limits.memory ceiling so a 15 GB model failed to load with ~15 GB of VRAM free."
- kind: incident
  path_or_url: "https://github.com/derio-net/frank/blob/main/docs/superpowers/specs/2026-03-16--media--comfyui-custom-image-design.md"
  date: 2026-03-16
  demonstrates: "The custom-image migration (ai-dock → derio-net/comfyui). Seven concrete problems with the stock image — broken Caddy proxy, wrong env var names (COMFYUI_ARGS not COMFYUI_FLAGS), outdated ComfyUI v0.2.2, outdated PyTorch 2.4.1+cu121 with no sm_120 for RTX 5070 Ti, outdated Manager v2.51.2, permission mismatch — none patchable, all solved by a 60-line custom Dockerfile."

## Diagrams planned
- landscape:
    x_axis: "Opinionated ↔ Composable"
    y_axis: "Self-hosted ↔ Managed"
    vendors_plotted: ["ComfyUI", "AUTOMATIC1111", "InvokeAI", "Fooocus", "Replicate", "Midjourney/DALL-E"]
- architecture_comparison:
    vendors: ["ComfyUI", "AUTOMATIC1111", "Replicate"]
- decision_tree:
    leaves: 4

## Named gaps (≥1)
- "No public benchmark exists for seconds-per-image at SDXL or FLUX-dev settings on a 16 GB consumer GPU that is concurrently hosting (or contended with) a 7B-parameter LLM. Vendor benchmarks (BFL Flux release notes, Civitai comparisons, Stability throughput charts) all assume a dedicated GPU — usually an H100 or an RTX 4090 with no other workloads. The bundled cost of GPU sharing — cold-start time when ComfyUI swaps in for Ollama, VRAM fragmentation, the cgroup-RAM ceiling — is rarely measured. This gap matters because the homelab / startup audience is exactly the cohort that runs one consumer GPU for both inference and image generation, and they have no apples-to-apples seconds-per-image number to anchor expectations against."

## Counter-arguments considered (≥1)
- "Midjourney costs $10/month, requires zero infrastructure, and produces aesthetically superior images out of the box for most prompts. DALL-E 3 ships inside ChatGPT for $20/month and is equally hands-off. Why does Frank self-host? Three honest answers: (1) data sovereignty — prompts and reference images stay on Frank, not Midjourney's training pipeline; (2) learning value — every scar in §5 (GPU contention, custom-image build, cgroup-RAM misdiagnosis) is a lesson the API hides; (3) ComfyUI's node graph is a programmable workflow artefact — LoRA stacking, custom samplers, region-conditioning, ControlNet chains, inpainting at specific denoising strengths — these are things an API fundamentally cannot expose because they collapse the workflow into a JSON request. The counter-argument wins for users who want a single image per session; it loses for users who want the workflow itself as the durable artefact."
