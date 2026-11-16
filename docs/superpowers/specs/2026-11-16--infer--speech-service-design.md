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
R3. The speech service is an ArgoCD Application running a derived image of an upstream OpenAI-compatible speech server (speaches) with CTranslate2 >= 4.6.3 for Blackwell sm_120, built by CI from `apps/speech/docker/` on a digest-pinned upstream base and pinned in the Deployment by version tag, on gpu-1, with models cached on a PVC and no toolchain build per job.
R4. `/v1/audio/transcriptions` serves faster-whisper `large-v3-turbo` (or `large-v3`) by default and handles English, German and Greek with language auto-detect.
R5. `/v1/audio/speech` is served with a conservative default TTS model; the Greek and German TTS engine is chosen from the benchmark and recorded as a decision, not assumed.
R6. gpu-switcher knows the speech service: activating ComfyUI drains both Ollama and speech, and returning to Ollama restores both.
R7. The API is reachable in-cluster and at `speech.cluster.derio.net` over LAN/mesh only (Traefik IngressRoute, homepage tile); there is no public ingress.
R8. Health checks and alerts do not fire during the normal batch lifecycle; no transient job runs in a namespace a workload-liveness alert watches; the gpu-timeshare probes and `gpu-node-both-down` account for speech on the card.
R9. A repeatable benchmark (manual operation) measures VRAM and latency of candidate STT/TTS models on gpu-1 with Ollama loaded — real-time factor for batch, time-to-first-audio — including Greek and German TTS quality, and its results are recorded in the repo.
R10. The deferred issue items (streaming endpoint, priority/queue, transcription UI, retirement of the temporary script, a NetworkPolicy on the speech namespace with a narrowed 192.168.55.0/24 allowlist) are filed as follow-up issues.

## Design

**GPU sharing (R1, R2).** `apps/gpu-operator/values.yaml` gains `devicePlugin.config`
referencing a time-slicing ConfigMap shipped from `apps/gpu-operator-extras/manifests/`
(`renameByDefault: false`, `replicas: N`). Time-slicing gives no memory isolation, so the
budget lives in one declared place (a small values/ConfigMap section) read by a guard
test: Ollama's loaded model + `num_ctx` while speech is up, plus the speech models'
fixed sizes, must sum under 16 GB minus headroom. `OLLAMA_MAX_LOADED_MODELS=1` stays.

**Service (R3–R5, R7).** New `apps/speech/` (values/manifests) and
`apps/root/templates/speech.yaml`: an upstream OpenAI-compatible server (speaches-class)
pinned by version tag (`ghcr.io/derio-net/speech:<rev>`, derived image, see below), `nodeSelector: gpu-1` with the defensive `nvidia.com/gpu` toleration,
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

**gpu-switcher change is code, not env (R6).** `parseWorkloads` (`apps/gpu-switcher/app/main.go:127-148`) splits on exactly three fields; the `Workload` struct (`k8s.go:11-16`) gains an optional `Group`, written `speech:speech:speech@ollama` (fourth part after `@`, three-field entries unchanged). `ActivateWorkload` (`k8s.go:57-78`) scales the target and every workload sharing its group to 1 and all others to 0; `DeactivateAll` is unchanged. `GetStatus` finds pods by label `app.kubernetes.io/name=<Name>` (`k8s.go:39-41`), so the speech pod carries `app.kubernetes.io/name: speech`. Go unit tests in `k8s_test.go` cover group activation and the legacy syntax. The image is rebuilt by CI and the tag in `apps/gpu-switcher/manifests/deployment.yaml:22` (now `v0.1.1`) is bumped, with `WORKLOADS` at `:29` extended.

**Exclusivity after time-slicing (R1).** Today exclusivity comes from the single `nvidia.com/gpu` unit. With `replicas: N`, only gpu-switcher's scaling keeps ComfyUI away from Ollama and speech, so N is set to exactly the number of workloads that may coexist (Ollama + speech = 2) and the guard asserts N equals the size of the largest switcher group. ComfyUI is therefore unable to schedule alongside a full group; selfHeal does not fight the switcher because replica counts are already `ignoreDifferences` for the switched Deployments (the new speech Deployment gets the same rule).

**VRAM budget location (R2).** Declared in `apps/speech/manifests/files/vram-budget.yaml`: the Ollama model allowlist while speech is up (named tags with their `num_ctx`, from the Modelfile variants in `apps/ollama/values.yaml:34,46`), each speech model's measured size, the 16 GB total and a headroom figure. `scripts/tests/test_speech_vram_budget.py` reads it, checks the sum is under the limit, that every allowlisted Ollama tag exists in `apps/ollama/values.yaml`, and that N matches the switcher group.

**Exposure and auth (R7).** The route goes in `apps/traefik/manifests/ingressroutes.yaml` beside comfyui (`:258-280`) with `ip-allowlist` and `security-headers` but **not** `authentik-forwardauth`, which would break API clients (litellm-api precedent); callers are LAN/mesh hosts and in-cluster services, with no per-request key in this run. A permissive-in-the-LAN API is the accepted trade-off and the security lens reviews it. Long recordings: the route does not buffer bodies (uploads and TTS audio stream through) and sets a long backend response timeout, but the `websecure` entrypoint's default read timeout is left as is, so `speech.cluster.derio.net` serves short clips (voice notes, laptops); long recordings are sent to the in-cluster Service URL `http://speech.speech.svc.cluster.local:8000`. The route uses its own narrow `speech-ip-allowlist` (LAN 192.168.0.0/16, mesh 100.64.0.0/10, pods 10.0.0.0/8). The tile goes in `apps/homepage/manifests/files/services.yaml`. The Application follows `frank-argocd.md` (`ServerSideApply`, `prune: false`, `selfHeal`).

**Alert wiring (R8).** The speech probe is added to `apps/blackbox-exporter/manifests/vmprobe.yaml` with `probe_group: gpu_timeshare` (existing entries `:107,:131`). `alert-rules-cm.yaml:381` (`namespace!~"ollama|comfyui"`) gains `speech`. `gpu-node-both-down` (`:1781`, `sum(probe_success{probe_group="gpu_timeshare"})`) keeps its meaning "no GPU inference up": speech is counted but speech-only-up must not mask a dead Ollama and ComfyUI, so the rule is changed to sum only the Ollama and ComfyUI probes (speech probe labelled `probe_group: gpu_timeshare_speech`, with its own non-paging health rule). The #554 flip semantics are documented in `gpu-1.md`. `apps/grafana-alerting/tests/assert-gpu-timeshare-rules.sh` and `scripts/tests/test_feature_health_workload_metrics.py` are updated to the new set.

**Device-plugin roll (R1).** A `# manual-operation` block (`infer-speech-device-plugin-roll`) rolls the plugin after merge: confirm the allocatable count, then check Ollama re-acquires the GPU; rollback is reverting the values commit and restarting the plugin, then `fr`/gpu-switcher re-activation of Ollama. It is ordered before the speech Deployment is scaled up.

**Record locations (R5, R9).** Benchmark results and the Greek/German TTS decision are written to `docs/investigations/2026-11-16--infer--speech-benchmark.md`.

**Layer-workflow close-out.** The building and operating blog posts and README update are deferred to the post-deploy checklist after the live rows pass, recorded in the plan's last phase as manual.

## What this deliberately does not do

- No streaming/WebRTC endpoint, priority queue, batch job API or transcription UI (R10).
- No NetworkPolicy and no narrowing of the pod CIDR (10.0.0.0/8) / LAN (192.168.0.0/16) allowlist: in-cluster callers are not yet inventoried and a policy could break litellm/hermes. The IP allowlist is the only access control, and in-cluster pods reach the Service directly, bypassing Traefik. A NetworkPolicy plus narrowing the LAN range to 192.168.55.0/24 is a tracked follow-up.
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

- (op: postmerge-timeslice-allocatable) [ ] After merge, roll the device plugin and confirm `kubectl get node gpu-1 -o jsonpath='{.status.allocatable}'` shows the time-sliced `nvidia.com/gpu` count, with Ollama and speech Running together and `nvidia-smi` memory under budget.
- [ ] POST a Greek, an English and a German sample to `/v1/audio/transcriptions` and check the language auto-detect and text.
- [ ] POST text in each language to `/v1/audio/speech` and listen to the result.
- [ ] Activate ComfyUI through gpu-switcher, confirm Ollama and speech are both at 0, then activate Ollama and confirm both are back.
- [ ] Run a batch transcription of a long recording and confirm no alert fires, including while ComfyUI is activated and released.
- [ ] Confirm `speech.cluster.derio.net` answers on LAN/mesh and does not resolve or route from the public edge.
- [ ] Run the benchmark and commit `docs/investigations/2026-11-16--infer--speech-benchmark.md`.
