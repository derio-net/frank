# Speech service on gpu-1 — STT/TTS sharing the card with Ollama

**Date:** 2026-11-16
**Layer:** `infer` (11) — Local Inference
**Status:** Draft
**Prompted by:** `derio-net/frank` issue #1006
**Repos:** `derio-net/frank` only

gpu-1's single RTX 5070 Ti (16 GB) is handed to one workload at a time by
`apps/gpu-switcher`. Batch transcription currently runs from a temporary,
non-GitOps script that deactivates Ollama and builds whisper.cpp in a transient
pod, and its host (secure-agent-pod) is retired. This spec delivers the **core**
of a supported replacement: a GitOps-managed, OpenAI-compatible speech service
that shares the GPU with Ollama.

**Scope of this run:** GPU sharing, the speech service (STT + TTS), gpu-switcher
hand-over, private exposure, alerts, and the benchmark. The streaming endpoint,
priority queue / batch job API, transcription UI and retirement of the
`whisper-gpu` script are filed as follow-up issues, not built here.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-11-16--infer--speech-service | `derio-net/frank` | `2026-11-16--infer--speech-service` | — |

## Requirements

R1. The gpu-operator device plugin advertises `nvidia.com/gpu` with time-slicing replicas (declared in git) so Ollama and the speech service can both be scheduled onto gpu-1 at once.
R2. The VRAM budget is explicit and enforced by configuration: the Ollama model and `num_ctx` allowed while speech is up, plus fixed speech model sizes, with an offline guard test that fails when the declared budget exceeds 16 GB.
R3. The speech service is an ArgoCD Application running an upstream OpenAI-compatible speech server pinned by image digest on gpu-1, with models cached on a PVC and no toolchain build per job.
R4. `/v1/audio/transcriptions` serves faster-whisper `large-v3-turbo` (or `large-v3`) by default and handles English, German and Greek with language auto-detect.
R5. `/v1/audio/speech` is served with a conservative default TTS model; the Greek and German TTS engine is chosen from the benchmark and recorded as a decision, not assumed.
R6. gpu-switcher knows the speech service: activating ComfyUI drains both Ollama and speech, and returning to Ollama restores both.
R7. The API is reachable in-cluster and at `speech.cluster.derio.net` over LAN/mesh only (Traefik IngressRoute, homepage tile); there is no public ingress.
R8. Health checks and alerts do not fire during the normal batch lifecycle; no transient job runs in a namespace a workload-liveness alert watches; the gpu-timeshare probes and `gpu-node-both-down` account for speech on the card.
R9. A repeatable benchmark (manual operation) measures VRAM and latency of candidate STT/TTS models on gpu-1 with Ollama loaded — real-time factor for batch, time-to-first-audio — including Greek and German TTS quality, and its results are recorded in the repo.
R10. The deferred issue items (streaming endpoint, priority/queue, transcription UI, retirement of the temporary script) are filed as follow-up issues.

## Design

**GPU sharing (R1, R2).** `apps/gpu-operator/values.yaml` gains `devicePlugin.config`
referencing a time-slicing ConfigMap shipped from `apps/gpu-operator-extras/manifests/`
(`renameByDefault: false`, `replicas: N`). Time-slicing gives no memory isolation, so the
budget lives in one declared place (a small values/ConfigMap section) read by a guard
test: Ollama's loaded model + `num_ctx` while speech is up, plus the speech models'
fixed sizes, must sum under 16 GB minus headroom. `OLLAMA_MAX_LOADED_MODELS=1` stays.

**Service (R3–R5, R7).** New `apps/speech/` (values/manifests) and
`apps/root/templates/speech.yaml`: an upstream OpenAI-compatible server (speaches-class)
pinned by digest, `nodeSelector: gpu-1` with the defensive `nvidia.com/gpu` toleration,
`strategy: Recreate`, a Longhorn PVC for model cache, ClusterIP Service, IngressRoute
and homepage tile. STT default is faster-whisper large-v3-turbo; TTS ships a conservative
default and the Greek/German engine is a benchmark-driven configuration change. The image's
Blackwell (`sm_120`) CUDA support is verified at plan time; if no upstream image works the
plan escalates rather than silently building a custom one.

**Hand-over (R6).** gpu-switcher's `WORKLOADS` syntax gains an optional group so `speech`
rides with `ollama`: `/api/activate/ollama` scales Ollama and speech up and ComfyUI down;
`/api/activate/comfyui` scales both down; `/api/deactivate` scales everything down. The
existing three-field entries keep their meaning (backward compatible).

**Alerts (R8).** A speech readiness probe joins the `gpu_timeshare` group; rules that
treat scale-to-0 as healthy gain speech in their exclusion sets (derived by reading the
switcher group, never a comment); `gpu-node-both-down` and the #554 probe semantics are
updated so "inference up" accounts for speech. Batch work uses the always-running service,
so no transient pod appears in a watched namespace.

**Benchmark (R9).** A script under `scripts/` plus a `# manual-operation` block runs the
candidates with Ollama loaded and writes results to `docs/investigations/`.

## What this deliberately does not do

- No streaming/WebRTC endpoint, priority queue, batch job API or transcription UI (R10).
- No commercial book/audiobook rendering.
- ComfyUI stays exclusive under gpu-switcher.
- The `whisper-gpu` script is not retired here; that waits for the batch path.

## Verification

strategy: live
gate: devops

- infer-speech-gpu-sharing: live — needs the real RTX 5070 Ti on gpu-1 and a device-plugin roll; ArgoCD only syncs main, so no pre-merge candidate can exercise it.
- infer-speech-stt-api: live — needs the GPU-backed model and the Traefik route on the live cluster.
- infer-speech-tts-api: live — needs the GPU-backed model; Greek/German quality is judged by listening.
- infer-speech-switcher-handover: live — needs live gpu-switcher scaling of Ollama, speech and ComfyUI.
- infer-speech-quiet-alerts: live — alert behaviour is observable only against the live Grafana and a real batch lifecycle.
- infer-speech-benchmark: live — measures VRAM and latency on gpu-1 with Ollama loaded.

## Test Plan

- [ ] After merge, roll the device plugin and confirm `kubectl get node gpu-1 -o jsonpath='{.status.allocatable}'` shows the time-sliced `nvidia.com/gpu` count, with Ollama and speech Running together and `nvidia-smi` memory under budget.
- [ ] POST a Greek, an English and a German sample to `/v1/audio/transcriptions` and check the language auto-detect and text.
- [ ] POST text in each language to `/v1/audio/speech` and listen to the result.
- [ ] Activate ComfyUI through gpu-switcher, confirm Ollama and speech are both at 0, then activate Ollama and confirm both are back.
- [ ] Run a batch transcription and confirm no alert fires; run the benchmark and commit its results.
