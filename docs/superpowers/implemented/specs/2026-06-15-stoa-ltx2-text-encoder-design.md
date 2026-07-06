# Design: LTX-2 Gemma-3-12B text encoder (+ spatial upscaler + camera LoRAs) for stoa native-audio generation

**Date:** 2026-06-15
**Layer:** `comfy` (extension of the 2026-06-14 stoa-frank-infra ComfyUI hydration)
**Target repo:** derio-net/frank
**Upstream request:** agentic-stoa/content-factory#69
**Status:** Deployed

> **Codename / OPSEC.** The upstream issue describes the **stoa** content
> pipeline. The upstream repo is private; in *our* (frank) deliverables —
> branch names, commits, comments, this spec, manifest comments, the issue
> close-out — the pipeline is referred to as **stoa**, never by its private
> codename. We stay at the technical level (model files, folders, ComfyUI
> nodes); we do not obfuscate the engineering. The existing
> `job-model-download.yaml` already follows this ("stoa pipeline").

## Problem

The stoa pipeline's Phase 8 audio gate (judge LTX-2 *native* dialogue audio)
is blocked. gpu-1's ComfyUI (0.9.2, RTX 5070 Ti, `192.168.55.213:8188`) has the
LTX-2.3 transformer + both VAEs, but is **missing the text-encoder model** the
audio-capable checkpoint requires.

The deployed checkpoint `ltx-2.3-22b-distilled-fp8.safetensors` conditions on
**Gemma-3-12B** text embeddings (hidden dim **3840**). The installed encoders
cannot satisfy this:

- `t5xxl_fp8_e4m3fn_scaled` → `ValueError: invalid tokenizer`
- `umt5_xxl_fp8_e4m3fn_scaled` → `size mismatch … audio_embeddings_connector …
  [128, 2048] vs current [128, 3840]` (3840 = Gemma-3-12B hidden size)
- `gemma-3-12b-it-Q4_K_S.gguf` (already on the PVC) is a **GGUF** quant; the
  native ComfyUI `LTXAVTextEncoderLoader` node reads a **safetensors**
  text-encoder from `models/text_encoders/`, so the GGUF does not surface in
  that node's enum.

## Goal (this is the deliverable)

1. Add the required + recommended + optional LTX-2 model files to the **stoa
   ComfyUI model-hydration Job** (`apps/comfyui/manifests/job-model-download.yaml`)
   — declarative, idempotent, skip-if-present.
2. **Drive the live hydration** onto the `comfyui-models` PVC on gpu-1 and
   verify the new files surface in the ComfyUI node enums via `GET /object_info`.
3. **Close content-factory#69** with the verification evidence.
4. Ship the manifest change as a single PR to frank.

## Models to install (operator chose: encoder + upscaler + camera LoRAs)

Verified placements against the **live** ComfyUI node source on gpu-1
(`folder_paths.get_filename_list(...)`), not the issue's guesses:

| # | File | HF source (`resolve/main`) | Target folder | ~Size | Node |
|---|------|----------------------------|---------------|-------|------|
| 1 (required) | `gemma_3_12B_it_fp4_mixed.safetensors` | `Comfy-Org/ltx-2` → `split_files/text_encoders/` | `text_encoders/` | 9.5 GB | `LTXAVTextEncoderLoader` |
| 2 (recommended) | `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | `Lightricks/LTX-2.3` | `latent_upscale_models/` | 1.0 GB | `LatentUpscaleModelLoader` / `LTXVLatentUpsampler` |
| 3 (optional) | `ltx-2-19b-lora-camera-control-{static,dolly-left,dolly-right,dolly-in,dolly-out,jib-up,jib-down}.safetensors` (7 files) | `Lightricks/LTX-2-19b-LoRA-Camera-Control-<Move>` (one repo per move) | `loras/` | 0.33 GB ×7 ≈ 2.3 GB | `LoraLoader` |

**Total new download ≈ 12.8 GB.** The `comfyui-models` PVC is 200 Gi with
82 Gi free (59% used) — ample headroom.

### Decisions & rationale

- **Folder correction (caught from live node source).** The issue guessed the
  upscaler lands in `models/upscale_models/`. The actual node
  `LatentUpscaleModelLoader` (defined in `comfy_extras/nodes_hunyuan.py`) calls
  `folder_paths.get_filename_list("latent_upscale_models")`. ComfyUI registers
  `upscale_models` and `latent_upscale_models` as **separate** folders; the LTX
  latent upscaler must go in **`latent_upscale_models/`** or the node enum stays
  empty. The Job's `mkdir -p` creates the folder.
- **Upscaler version match.** The deployed checkpoint is LTX-**2.3**, so we use
  the `Lightricks/LTX-2.3` upscaler (`x2-1.1`, the long-video hotfix), not the
  LTX-2 `1.0` file named verbatim in the issue. Matching the checkpoint family
  is the correctness call.
- **Keep the existing GGUF encoder.** `gemma-3-12b-it-Q4_K_S.gguf` stays — the
  addition is purely additive (a different loader path may use it; removing
  risks an unrelated graph). Disk is not a constraint.
- **Camera LoRAs are 19B-trained; checkpoint is 22B-2.3 — known caveat.** These
  LoRAs target the LTX-2 19B base. They will appear in the `LoraLoader` enum
  (any `.safetensors` in `models/loras/` does), which is all the chosen
  verification proves. Whether they cleanly apply to the 22B-2.3 distilled
  checkpoint is a **pipeline-activation** concern (real render), out of scope
  for #69's gate-unblock. Documented so a later mismatch isn't a surprise.

## Redeployment (driving the live hydration)

The Job is ArgoCD-managed and immutable; a same-named `delete + apply` of the
worktree (pre-merge) manifest would fight ArgoCD self-heal (live spec ≠ git
spec on `main` → self-heal reverts to the old spec mid-download, dropping the
new download lines). Root App-of-Apps re-templating compounds this.

**Chosen mechanism:** run a **one-off, differently-named** hydration Job
(`comfyui-stoa-ltx2-encoder-hydrate`) built from the same download script,
pinned to gpu-1, mounting `comfyui-models`. ArgoCD does not manage that name,
so there is no self-heal conflict and **root GitOps is never suspended**. The
shared PVC is RWO but the Job co-locates on gpu-1 with the serving ComfyUI pod
(same node → multi-mount allowed), exactly as the original hydration Job did.
After completion the one-off Job is deleted; the canonical
`job-model-download.yaml` (updated in the PR) reproduces the same files
declaratively (skip-if-present no-ops) on the next ArgoCD-driven recreate.

Pre-flight: HEAD-check (`curl -sIL`, expect HTTP 302) the three new URL groups
from inside the cluster before the full download, to fail fast on any gated /
moved weight (the existing Job header asserts "302, no token" for its URLs).

ComfyUI caches folder listings with mtime invalidation; adding files bumps the
dir mtime, so a fresh `GET /object_info` re-scans. If an enum still looks stale,
`kubectl rollout restart deploy/comfyui -n comfyui` forces a clean re-read.

## Verification (operator chose: /object_info)

Pass criteria, captured live:

- `LTXAVTextEncoderLoader.text_encoder` enum includes
  `gemma_3_12B_it_fp4_mixed.safetensors`.
- `LatentUpscaleModelLoader.model_name` enum includes
  `ltx-2.3-spatial-upscaler-x2-1.1.safetensors`.
- `LoraLoader.lora_name` enum includes the 7 camera-control LoRA filenames.
- The Gemma encoder **loads without the dim-3840 mismatch** — node enum
  presence + clean file (correct safetensors header) is the bar; we do not run
  a full LTX-2 audio+video render here.

**Out of scope:** the full Phase 8 / G2 audio render. The stoa runner graph
lives in the private content-factory repo and belongs to pipeline activation,
not this infra gate-unblock. Recorded in the issue close-out.

## Files changed (frank)

- `apps/comfyui/manifests/job-model-download.yaml` — add the three model groups
  (encoder, latent upscaler, 7 camera LoRAs) to the `download` script, with a
  comment noting the `latent_upscale_models` folder and the 19B-LoRA caveat.

No new app, no chart change, no secret. Pure additive hydration — consistent
with the layer-extension workflow (extend the existing ComfyUI app, don't
deploy fresh).

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|-------------|--------|-------|
| `2026-06-15-stoa-ltx2-text-encoder` | derio-net/frank | Deployed | Encoder + upscaler + camera LoRAs; live hydration + /object_info verify + close content-factory#69 |
