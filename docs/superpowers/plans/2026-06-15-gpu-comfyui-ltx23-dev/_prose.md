# ComfyUI v0.24 bump + LTX-2.3 "dev" model hydration (gpu-1)

Frank-side implementation of the stoa pipeline's native-audio unblock
(content-factory#70). The on-box `ltx-2.3-22b-distilled-fp8` checkpoint is the
wrong lineage — its baked audio connector is 2048-dim while the installed
Gemma-3-12B encoder needs 3840-dim — so native LTX-2 audio fails. The fix is to
hydrate the current Gemma-paired **LTX-2.3 "dev"** checkpoint set and move the
ComfyUI core off the stale January `v0.9.2`.

> **OPSEC.** Public frank repo. The pipeline is the "stoa pipeline"/"stoa
> runner" everywhere — never the private codename, in any commit, comment, or
> manifest.

## Scope (operator-approved, Blackwell-optimal)

fp8 dev checkpoint **+** distilled-1.1 LoRA **+** NVFP4 dev checkpoint **+**
ComfyUI core bump `v0.9.2 → v0.24.0`, **and** removal of the wrong-lineage
on-box `distilled-fp8` checkpoint. NVFP4 weight loading needs the v0.24.x core;
the RTX 5070 Ti is Blackwell → native NVFP4 matmul, lower VRAM than fp8.

## Phases

1. **Image bump** — `COMFYUI_REF v0.9.2→v0.24.0` (Dockerfile + workflow),
   `STOA_NODES 3→4` with a rev comment, and re-pin the derived tag
   `comfyui-v0.24.0-pt2.10.0-cu128-stoa4` in `deployment.yaml` +
   `job-model-download.yaml`. The tag is composed from these vars, so all three
   tag occurrences must move together or the deploy serves a stale image.
2. **Hydration Job** — rewrite the LTX-2 download block: drop the distilled-fp8
   line, add an idempotent `rm -f` of the old file, add fp8-dev + NVFP4-dev
   checkpoints + the distilled LoRA. Refresh the pvc.yaml capacity comment.
3. **CI build validation** — dispatch `build-comfyui.yml` on the branch to prove
   the 5-month / 15-minor core jump compiles before merge. A failure means a
   pinned custom node broke → bump that one node ref as a fast-follow.
4. **[manual] Cluster verification** — back-loaded, operator-driven post-merge:
   ArgoCD sync, Job delete+re-apply re-hydration, GPU-switcher bring-up,
   `/object_info` check, and a small LTX-2.3 audio+video render (the real G2
   proof). Ships unimplemented; the operator pushes evidence to the PR.

## Key facts (verified 2026-06-15)

- ComfyUI `v0.24.0` (2026-06-03); `v0.23.0` fixed the LTX a/v bugs.
- fp8: `Lightricks/LTX-2.3-fp8/…/ltx-2.3-22b-dev-fp8.safetensors`
- nvfp4: `Lightricks/LTX-2.3-nvfp4/…/ltx-2.3-22b-dev-nvfp4.safetensors`
- LoRA: `Comfy-Org/ltx-2.3/…/split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors`
- PVC `comfyui-models` 200Gi; net ≈ +22GB after removing the old checkpoint.
- ComfyUI Deployment is `replicas: 0` (gpu-1 GPU time-share); the download Job
  requests no GPU and runs anytime.

## Risks

- **Core jump may break pinned custom nodes** (LTXVideo/GGUF/Wan/Kokoro/Fish).
  Caught by Phase 3 (build) + the operator's render (runtime). Nodes are NOT
  pre-bumped; fix the offender as a fast-follow. The kornia-`pad` Dockerfile
  patch is keyed to kornia, not ComfyUI core — carries forward unchanged.
- **Job immutability** → re-hydration is delete+apply (operator, Phase 4).
