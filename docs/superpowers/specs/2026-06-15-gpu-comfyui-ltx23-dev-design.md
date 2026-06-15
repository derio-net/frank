# Design: ComfyUI v0.24 bump + LTX-2.3 "dev" model hydration (gpu-1)

**Status:** ready
**Layer:** gpu
**Date:** 2026-06-15
**Source:** stoa pipeline ticket (content-factory#70) — native-audio gate (G2)

## Goal

Move gpu-1's ComfyUI from the stale `v0.9.2` core to `v0.24.0` and hydrate the
current, Gemma-3-paired **LTX-2.3 "dev"** checkpoint set into the `comfyui-models`
PVC, replacing the wrong-lineage on-box `distilled-fp8` checkpoint. This unblocks
the stoa video pipeline's native-audio gate, which currently fails because the
on-box checkpoint's baked audio connector is 2048-dim while the installed
Gemma-3-12B text encoder requires 3840-dim.

The frank-side deliverable is **image + model store** only. The stoa runner graph
wiring lives in the private content-factory repo and is out of scope here.

> **OPSEC.** This is the public frank repo. Refer to the pipeline only as the
> "stoa pipeline"/"stoa runner". Do not write the private codename in any frank
> artifact (spec, plan, commit, manifest comment, blog).

## Operator decisions (batched Q&A, 2026-06-15)

1. **Scope:** Blackwell-optimal — fp8 dev checkpoint **+** distilled-1.1 LoRA
   **+** NVFP4 dev checkpoint **+** ComfyUI core bump to v0.24.0. (NVFP4 weight
   loading requires the v0.24.x core; the RTX 5070 Ti is Blackwell → native NVFP4
   matmul, lower VRAM than fp8.)
2. **On-box wrong checkpoint:** Remove `ltx-2.3-22b-distilled-fp8.safetensors`
   (2048-dim connector, unusable for the Gemma audio path; ~29.5 GB reclaimed).
3. **Test plan:** Full — download + a real LTX-2.3 audio+video render
   (operator-driven, post-merge).

## Verified facts (HuggingFace + GitHub, 2026-06-15)

- ComfyUI releases: `v0.22.0` (05-20), `v0.23.0` (06-01, **fixed two LTX
  audio-video correctness bugs**), `v0.24.0` (06-03). Current pin `v0.9.2`
  (01-15) is ~5 months / 15 minor versions stale. Target = **`v0.24.0`** (latest
  with a full GitHub release; `v0.24.1` exists as a tag but has no release object).
- fp8 dev: `https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors` (~29 GB)
- NVFP4 dev: `https://huggingface.co/Lightricks/LTX-2.3-nvfp4/resolve/main/ltx-2.3-22b-dev-nvfp4.safetensors` (~21.7 GB)
- distilled LoRA: `https://huggingface.co/Comfy-Org/ltx-2.3/resolve/main/split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors`
- Gemma-3-12B encoder + spatial upscaler: already on-box (from content-factory#69).
- PVC `comfyui-models` = 200Gi (`allowVolumeExpansion=true`). Net delta:
  `-29.5` (remove distilled-fp8) `+29 +21.7 +~2` ≈ **+22 GB** → fits comfortably.

## Changes (frank repo only)

All paths under `apps/comfyui/` unless noted.

1. **`docker/Dockerfile`** — `ARG COMFYUI_REF=v0.9.2` → `v0.24.0`.
2. **`.github/workflows/build-comfyui.yml`** —
   - `COMFYUI_REF: "v0.9.2"` → `"v0.24.0"`
   - `STOA_NODES: "3"` → `"4"` + a `# rev 4:` comment documenting the core bump
     (the rev-log is the image's human-readable change history; the tag is also
     made unique by the `v0.24.0` change, so this is belt-and-suspenders).
3. **Re-pin the image tag** `comfyui-v0.9.2-pt2.10.0-cu128-stoa3` →
   `comfyui-v0.24.0-pt2.10.0-cu128-stoa4` in both:
   - `manifests/deployment.yaml`
   - `manifests/job-model-download.yaml`
4. **`manifests/job-model-download.yaml`** (the hydration Job):
   - **Remove** the `distilled-fp8` download line.
   - **Add** a one-line `rm -f` of the old `checkpoints/ltx-2.3-22b-distilled-fp8.safetensors`
     before the downloads (idempotent; `-f` so a re-run after deletion is a no-op).
   - **Add** downloads:
     - `checkpoints/ltx-2.3-22b-dev-fp8.safetensors`
     - `checkpoints/ltx-2.3-22b-dev-nvfp4.safetensors`
     - `loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors`
   - Update the header comment block (model inventory + the 2026-06-15 verification note).
5. **`manifests/pvc.yaml`** — refresh the capacity-budget comment to reflect the
   dev checkpoints replacing the distilled one. No size change.

## Risks & mitigations

- **Primary risk — core jump (v0.9.2 → v0.24.0) breaks the pinned custom nodes**
  (ComfyUI-LTXVideo, GGUF, WanVideoWrapper, Kokoro, FishSpeech) at build or
  runtime. Mitigation: validate the image build on the feature branch via
  `gh workflow run build-comfyui.yml --ref feat/stoa-comfyui-models-70`
  (catches pip/import breakage at build time); the operator's post-merge render
  catches runtime node-load issues. **Node SHAs are NOT pre-bumped** — bump only
  the offending node as a fast-follow if the build or render surfaces a break.
  The Dockerfile's existing kornia-`pad` patch is keyed to kornia, not ComfyUI
  core, so it carries forward unchanged.
- **NVFP4 filename drift** — verified present in the repo today; the download is
  skip-if-present, so a wrong name fails loudly in the Job log (not silently).
- **Job immutability** — k8s Jobs are immutable and the comfyui ArgoCD app has no
  `Replace=true`; re-hydration is `kubectl delete job … && kubectl apply -f`
  (or ArgoCD recreate). This makes re-hydration an operator step (back-loaded).

## Test Plan (post-merge, operator-driven)

1. **CI build** — `comfyui-v0.24.0-pt2.10.0-cu128-stoa4` builds green
   (validated on the branch pre-merge; re-runs on merge via the docker/** push trigger, cache-hit).
2. **Deploy** — after merge, ArgoCD syncs `deployment.yaml`, re-pinning the
   image. The Deployment is `replicas: 0` by design (gpu-1 GPU time-share —
   ComfyUI and Ollama alternate on the GPU; the Application `ignoreDifferences`
   on `/spec/replicas`), so no pod starts on sync. Confirm the pin landed:
   `kubectl -n comfyui get deploy comfyui -o jsonpath='{.spec.template.spec.containers[0].image}'`.
3. **Re-hydrate** — the download Job requests no GPU (`nodeSelector: gpu-1`), so
   it runs even while Ollama holds the GPU. `kubectl delete job
   comfyui-stoa-model-download -n comfyui` then re-apply (or let ArgoCD
   recreate); watch logs → new checkpoints + LoRA downloaded, old `distilled-fp8`
   removed. (~50 GB; the Job is immutable, hence the delete+apply.)
4. **Bring ComfyUI up + /object_info** — switch the GPU to ComfyUI via the GPU
   switcher (`192.168.55.214:8080` — scales ComfyUI→1, Ollama→0); once the pod is
   Ready, `GET /object_info` → `CheckpointLoaderSimple.ckpt_name` lists
   `ltx-2.3-22b-dev-fp8.safetensors` **and** `ltx-2.3-22b-dev-nvfp4.safetensors`;
   the LoRA loader lists the distilled-1.1 LoRA.
5. **Render** — a small LTX-2.3 audio+video test render via the stoa runner
   completes (e.g. 544×960, ~97 frames / 8n+1, 8 distilled steps) — the real G2
   proof that native audio works.

## Manual phases (back-loaded)

Steps 2–5 of the Test Plan touch the live gpu-1 cluster, ~50 GB of HF downloads,
and the stoa runner — all operator-driven post-merge. The PR ships the
Dockerfile / workflow / manifest changes; the operator runs the Test Plan and
pushes any node-bump fast-follow to the same PR if a break surfaces.
