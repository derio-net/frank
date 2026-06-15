# LTX-2 Gemma-3-12B text encoder (+ upscaler + camera LoRAs) for stoa native audio

Extends the 2026-06-14 stoa ComfyUI hydration. The stoa pipeline's Phase 8
audio gate is blocked because gpu-1's ComfyUI lacks the **safetensors**
Gemma-3-12B text encoder the `ltx-2.3-22b-distilled-fp8` checkpoint conditions
on (hidden dim 3840). The installed t5xxl/umt5 encoders dimension-mismatch, and
the existing Gemma **GGUF** does not surface in the `LTXAVTextEncoderLoader`
node.

This plan adds three model groups to the declarative hydration Job, drives the
live hydration onto the `comfyui-models` PVC, verifies the files surface in the
ComfyUI node enums, closes the upstream issue, and ships one PR.

## Codename / OPSEC

The upstream request describes the **stoa** pipeline. The upstream repo is
private; all frank deliverables (branch, commits, comments, this plan, the
issue close-out) say **stoa**, never the private codename — at the technical
level, not obfuscated. The existing manifest already follows this.

## Models (operator chose encoder + upscaler + camera LoRAs)

Placements verified against the **live** ComfyUI node source on gpu-1, not the
issue's guesses:

- `gemma_3_12B_it_fp4_mixed.safetensors` → `text_encoders/` (`Comfy-Org/ltx-2`, ~9.5 GB) — **required**, unblocks the audio gate.
- `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` → `latent_upscale_models/` (`Lightricks/LTX-2.3`, ~1 GB) — recommended quality path. Folder is `latent_upscale_models`, **not** `upscale_models` (the issue's guess); confirmed from `LatentUpscaleModelLoader` source. Version-matched to the 2.3 checkpoint.
- 7 × `ltx-2-19b-lora-camera-control-*.safetensors` → `loras/` (per-move `Lightricks/LTX-2-19b-LoRA-Camera-Control-<Move>` repos, ~0.33 GB each) — optional directability. 19B-trained; cross-apply to the 22B-2.3 checkpoint is a pipeline-activation concern, not gated here.

Total ~12.8 GB; PVC has 82 GB free.

## Approach

A same-named `delete + apply` of the immutable Job would fight ArgoCD self-heal
(git `main` still has the old spec) and the root App-of-Apps re-templating, so
the new download lines would be reverted mid-run. Instead, drive the hydration
with a **one-off differently-named Job** that ArgoCD does not manage (no
self-heal conflict, root GitOps untouched), co-located on gpu-1 with the
serving pod (RWO multi-mount on one node). Delete it after. The PR updates the
canonical `job-model-download.yaml` so ArgoCD reproduces the files declaratively
(skip-if-present no-ops).

## Phases

1. **Add model files** — pre-flight HEAD-check the HF URLs (302), add the three
   groups to `job-model-download.yaml`, client-side dry-run validate.
2. **Drive + verify** — run the one-off hydration Job to completion, assert all
   three `/object_info` node enums list the new files, clean up the Job.
3. **Close + ship** — close content-factory#69 with the live evidence, open the
   frank PR.

## Out of scope

The full Phase 8 / G2 audio render (runner graph lives in the private
content-factory repo; pipeline-activation work). No new app, chart, or secret —
pure additive hydration.
