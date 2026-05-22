# The Frank Papers — Paper 16: Self-Hosted Media Generation

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Drafting (2026-05-22) — plan created; awaiting agentic Phase 1 execution.

**Prerequisite:** Papers 00, 04, 06, 07, 09, 10, 11, 14 published; Paper 10 (Self-Hosted Inference) in particular provides the shared GPU-language for §3/§5 — Paper 16 is its GPU-sharing companion. The custom ComfyUI image (`apps/comfyui/docker/`) and GPU Switcher API (`apps/gpu-switcher/`) referenced in the case study are live on Frank.

Paper 16 is the media-generation capability paper in the series: 2400–4200 words, the standard 8-section skeleton (§1 capability → §2 landscape → §3 architecture per vendor → §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap → §8 references). It is the first Paper to confront *contended GPU scheduling for consumer hardware* — the capability that looks "obvious" until you discover that a 16 GB consumer GPU cannot simultaneously host a 7B-parameter LLM and an SDXL/FLUX diffusion model, and the standard K8s GPU operator has no opinion about what to evict.

The capability question is: *if you want to generate images (or video, or audio) on your own infrastructure — and you've got exactly one consumer-grade GPU you also use for LLM inference — what wins, and what's the cost of sharing?* The vendor space splits along two axes: how the workflow is expressed (node graph, monolith UI, opinionated pipeline, API JSON) and where the GPU lives (dedicated, contended, cloud). Six candidates make the landscape, with **ComfyUI + a custom CUDA 12.8 image + the GPU Switcher** as Frank's case study — a three-piece stack where Frank builds his own ComfyUI image to control PyTorch/CUDA versions, runs it as a `replicas: 0` Deployment on `gpu-1`, and uses a small Go HTTP service to scale either Ollama or ComfyUI to 1 (never both) when the operator clicks a button at `192.168.55.214`.

The scars are the point. The off-the-shelf `ghcr.io/ai-dock/comfyui` image with broken Caddy template substitution, the wrong env var names (`COMFYUI_ARGS` vs `COMFYUI_FLAGS`), supervisord running cloudflared / SSH / Jupyter / Syncthing inside the container, ComfyUI v0.2.2 unable to load Flux models, PyTorch 2.4.1+cu121 with no sm_120 (Blackwell) support for the RTX 5070 Ti. The GPU contention with Ollama — `nvidia.com/gpu: 1` is a binary resource, K8s has no "schedule this OR that, never both" primitive, and Time-Slicing / MIG aren't an option on a single consumer GPU. The Ollama "system memory" error that actually means container cgroup RAM, not VRAM. The custom-image build pattern itself — why not just mount the models as a PVC and use a stock image — and the answer (CUDA 12.8 base, ComfyUI-Manager 4.x as a pip package not a custom_node, fsGroup 1000 instead of ai-dock's 1111).

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts across ≥2 kinds, the named gap on the absence of a credible seconds-per-image benchmark at SDXL/FLUX settings on a 16 GB consumer GPU shared with a 7B-parameter LLM (vendor benchmarks assume a dedicated GPU), and the counter-argument that for most people Midjourney costs $10/month and produces better aesthetics out of the box — so why self-host? Parallel subagents per vendor are appropriate — one each for ComfyUI, AUTOMATIC1111, InvokeAI, Fooocus, Replicate (as the cloud baseline), and OpenAI DALL-E / Midjourney as the "just use an API" null hypothesis — with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and the counter-argument. The counter to nail: *"Midjourney costs $10/month and is better at most aesthetics — why does Frank self-host?"* The honest answer involves three threads — data sovereignty (your prompts and reference images stay on your hardware), learning value (every scar in §5 is a lesson the API hides), and ComfyUI's node graph capability (LoRA stacking, custom samplers, region-conditioning, ControlNet chains — things APIs cannot expose because they collapse the workflow into a JSON request). The counter-argument wins for users who want a single image per session; it loses for users who want the workflow as a programmable artefact.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram — "where image-gen workloads sit between the GPU device and the human prompt"
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language — ComfyUI's node graph vs AUTO1111's monolith UI vs Fooocus's hidden-pipeline vs cloud-API's "post a JSON" model
- §4 What scale changes (300–600 words) + benchmark callouts: seconds-per-image at SDXL/FLUX settings, VRAM-headroom-vs-LoRA-count tradeoff, the cost-per-image cliff when sharing a GPU with inference (cold-start when GPU switches back)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (GPU contention with Ollama and the Switcher mechanics, ai-dock image abandoned for a custom CUDA 12.8 build, "system memory" misdiagnosed as VRAM)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves — ComfyUI vs AUTO1111 vs cloud API vs dedicated GPU server
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a freshly-printed photo with a satisfied-but-critical expression — a GPU rack behind him glowing — the kind of person who finally has a clean image-gen pipeline but knows the GPU sharing tax. Thin black tie, round reading glasses. The visual metaphor is *the finished print*. Mermaid diagrams: §1 stack position, §2 landscape (quadrantChart) + capability matrix, §3 four-to-six architecture flowcharts, §6 decision tree. Optional: a self-generated ComfyUI image as one of the inline figures (meta-honesty — the Paper exists because Frank can generate this Paper's own cover via ComfyUI). At least one Grafana / asciinema artefact from the cluster showing the GPU switch in action (Ollama replicas: 1→0, ComfyUI replicas: 0→1). Cluster-side captures may be deferred with `-TODO.png` placeholders if access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-person cluster, not academic). TL;DR ≤150 words written last. Dossier-link rendering check (use either inline shortcode OR rely on automatic injection — not both). Set `draft: false`, `status: published`. CI deploys via the existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md` (or verify the `papers-roadmap` shortcode auto-builds from frontmatter), verify the auto-rendered cross-link chips appear on Building 16-media-generation and Operating 10-media-generation, update README if relevant, set plan status to Complete.

## Phase summary

| # | Phase | Tag | Depends on |
|---|-------|-----|-----------|
| 1 | Dossier construction | agentic | — |
| 2 | Gate validation | manual | 1 |
| 3 | Scaffold + draft | agentic | 2 |
| 4 | Media fill | agentic | 3 |
| 5 | Review + publish | manual | 4 |
| 6 | Post-deploy checklist | manual | 5 |
