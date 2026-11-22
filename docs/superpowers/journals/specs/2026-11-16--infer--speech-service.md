<!-- fr:journal-schema=4 -->
# Journal: 2026-11-16--infer--speech-service

<!-- fr:journal kind=discovery scope=spec id=operator-brief-1006 created=2026-11-16T20:09:57+00:00 input=true -->
### operator-brief-1006 · discovery · Issue #1006: infer: speech service on gpu-1 (STT/TTS sharing the GPU with Ollama, OpenAI-compatible API, transcription UI)

## Background: current state

- gpu-1 has one RTX 5070 Ti (16 GB VRAM, Blackwell `sm_120`). `apps/gpu-switcher` gives the card exclusively to one workload at a time. Its `WORKLOADS` env in `apps/gpu-switcher/manifests/deployment.yaml` lists two: `ollama:ollama:ollama` and `comfyui:comfyui:comfyui`.
- `apps/gpu-operator/values.yaml` has no device plugin sharing config. Each pod that requests `nvidia.com/gpu` gets the whole card.
- `apps/ollama/values.yaml` sets `OLLAMA_MAX_LOADED_MODELS=1`. Some models in the lineup already use most of the 16 GB on their own (about 9.7 GB measured for one tag, and one larger model offloads to CPU).

### Temporary batch transcription (not GitOps)

Since 2026-11-02 a temporary script does batch transcription of long recordings:

1. It calls gpu-switcher `/api/deactivate`. This pauses Ollama.
2. It creates a transient pod `whisper-gpu` (`nvidia/cuda:12.8.1-devel-ubuntu24.04`). The pod builds whisper.cpp with CUDA for `sm_120` on every run, then runs whisper `large-v3` (Greek, beam 5, `-mc 0`, Silero VAD).
3. It deletes the pod and calls `/api/activate/ollama`.

A 2 h 25 min recording takes about 6 minutes. The script ran from secure-agent-pod, which has since been retired (#950), so the mechanism has no supported host now. Its runbook lives in private operator notes, not in this repo.

### Findings from the first runs

- **Alert side effect.** The first run created the pod in namespace `secure-agent-pod`. The pod stayed about 9 minutes in `ContainerCreating` (image pull). This fired the critical "Agent Pod Not Running" alert, and the persistent-agent layer showed as dead until the alert auto-resolved (health-bridge auto-issue, closed 2026-11-02). That rule is now tombstoned in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`, but the lesson stays: a transient GPU job must never run in a namespace that a workload-liveness alert watches.
- **Repetition loops.** whisper's default context carry-over caused repetition loops of 25 to 34 minutes on long audio. `-mc 0` (no context carry-over) fixed it.

## Consumers

1. **Batch transcription** of long recorded interviews in Greek, English and German.
2. **Agent chat voice notes.** Short batch STT with EN/DE/EL auto-detect. The current CPU `base` model often detects the wrong language.
3. **Laptop companion for children.** STT and TTS in EN/DE/EL. The laptops must keep a local offline fallback. The cluster service is an optional upgrade on the home network only.
4. **Planned private household assistant with real-time voice.** Push-to-talk first, then streaming STT, sentence-level TTS and barge-in. The concept exists only in private operator notes.

**Out of scope:** commercial book and audiobook rendering. That work uses frontier cloud models.

## Design direction (proposal, to be validated)

### Share the GPU with Ollama; do not add a third exclusive workload

- Real-time voice needs STT, LLM and TTS loaded at the same time. A third exclusive gpu-switcher workload cannot do that. Speech must share the card with Ollama, for example with NVIDIA device plugin time-slicing through the gpu-operator config.
- Time-slicing gives no memory isolation. The VRAM budget must be explicit and enforced by configuration: the Ollama model and `num_ctx` allowed while speech is up, plus fixed speech model sizes.
- Rough, unmeasured estimate: Ollama `gemma4:12b` about 8.4 GB plus a speech stack of about 3 to 4 GB fits in 16 GB. The benchmark below must confirm or reject this.
- ComfyUI stays exclusive under gpu-switcher.

### A GitOps-managed speech service

- OpenAI-compatible API: `/v1/audio/transcriptions` and `/v1/audio/speech`.
- A WebSocket or WebRTC streaming endpoint for real-time voice.
- Models cached on a PVC. No toolchain build per job.
- A small transcription UI: upload, progress, speaker labels, download as txt, srt or json.

### Priorities and GPU hand-over

- Priority classes: real-time > interactive (voice notes) > batch (long transcriptions).
- Batch jobs go in a queue and yield when a live session starts.
- gpu-switcher must know about the speech service. When ComfyUI takes the card, it pauses or drains both Ollama and speech, then restores both.

### Models and licences

- The operator has decided that this GPU is used only for non-commercial purposes. Strong multilingual and voice-cloning models with non-commercial weight licences (XTTS-v2, Fish-Speech, F5-TTS class) are therefore acceptable.
- STT: whisper `large-v3` / `large-v3-turbo` is proven for Greek.
- The main open model question is Greek and German TTS quality.

## Acceptance criteria

- [ ] Benchmark first: VRAM use and latency of candidate STT and TTS models on gpu-1 with Ollama loaded. Measure time-to-first-audio for push-to-talk and real-time factor for batch. Include Greek and German TTS quality.
- [ ] Ollama and the speech service share the GPU without OOM under the measured VRAM budget. ComfyUI activation drains and restores both.
- [ ] OpenAI-compatible STT and TTS endpoints, reachable in-cluster and over the private network only. No public ingress.
- [ ] Streaming endpoint for real-time voice.
- [ ] Priority and queueing: a batch job never blocks a live session.
- [ ] Transcription UI with job history and txt/srt/json download. Timings are kept.
- [ ] Health checks and alerts that do not fire during the normal batch job lifecycle. No transient job runs in a namespace that a workload-liveness alert watches.
- [ ] The temporary `whisper-gpu` script mechanism is retired after the service covers batch transcription.

## Related

- #554: live GPU-switch-flip test for the gpu-timeshare health probes. A speech service on the card changes what "inference up" means for those probes and for `gpu-node-both-down`.
- #950: secure-agent-pod retirement (removed the host of the temporary script and the agent-pod alert).
- `docs/runbooks/frank-gotchas/gpu-1.md`: gpu-1 scheduling idiom (`nodeSelector` plus defensive `nvidia.com/gpu:NoSchedule` toleration).
- `docs/papers-dossiers/05-gpu-scheduling/dossier.md`: background on MIG/MPS and device plugin sharing.

<!-- fr:journal kind=decision scope=spec id=scope-core-service created=2026-11-16T20:09:57+00:00 decided_by=operator -->
### scope-core-service · decision · Core service this run; streaming/queue/UI/script retirement as follow-ups

Q1 answer: core service, rest follow-ups.

decider: operator

<!-- fr:journal kind=decision scope=spec id=stack-upstream-pinned created=2026-11-16T20:09:57+00:00 decided_by=operator -->
### stack-upstream-pinned · decision · Upstream OpenAI-compatible speech server pinned by digest

Q2 answer: no custom image; verify sm_120 image at plan time.

decider: operator

<!-- fr:journal kind=decision scope=spec id=gpu-sharing-timeslicing created=2026-11-16T20:09:57+00:00 decided_by=operator -->
### gpu-sharing-timeslicing · decision · Time-slicing replicas via gpu-operator device plugin config

Q3 answer.

decider: operator

<!-- fr:journal kind=decision scope=spec id=exposure-traefik-private created=2026-11-16T20:09:57+00:00 decided_by=operator -->
### exposure-traefik-private · decision · ClusterIP + Traefik speech.cluster.derio.net, LAN/mesh only

Q4 answer.

decider: operator

<!-- fr:journal kind=decision scope=spec id=models-stt-turbo-tts-by-benchmark created=2026-11-16T20:09:57+00:00 decided_by=operator -->
### models-stt-turbo-tts-by-benchmark · decision · STT large-v3-turbo default; Greek/German TTS chosen by benchmark

Q5 answer.

decider: operator

<!-- fr:journal kind=decision scope=spec id=verification-live-devops created=2026-11-16T20:09:57+00:00 decided_by=operator -->
### verification-live-devops · decision · strategy live, gate devops

Q6 answer.

decider: operator

<!-- fr:journal kind=lens scope=spec id=lens-security-1 created=2026-11-16T20:09:57+00:00 lens=security step=brainstorm -->
### lens-security-1 · lens · Private-only exposure and no-auth machine API on the LAN

<!-- fr:journal kind=finding scope=spec id=s1 created=2026-11-16T20:11:56+00:00 state=open review_scope=in -->
### s1 · finding [open] (reviewer: in scope) · gpu-switcher change is Go code plus an image bump

check: spec review; see reviewer return.

<!-- fr:journal kind=finding scope=spec id=s2 created=2026-11-16T20:11:56+00:00 state=open review_scope=in -->
### s2 · finding [open] (reviewer: in scope) · Alert changes name wrong or no files

check: spec review; see reviewer return.

<!-- fr:journal kind=finding scope=spec id=s3 created=2026-11-16T20:11:56+00:00 state=open review_scope=in -->
### s3 · finding [open] (reviewer: in scope) · Auth model for the LAN API unspecified

check: spec review; see reviewer return.

<!-- fr:journal kind=finding scope=spec id=s4 created=2026-11-16T20:11:56+00:00 state=open review_scope=in -->
### s4 · finding [open] (reviewer: in scope) · Time-slicing isolation gap and no VRAM guard location

check: spec review; see reviewer return.

<!-- fr:journal kind=finding scope=spec id=s5 created=2026-11-16T20:11:56+00:00 state=open review_scope=in -->
### s5 · finding [open] (reviewer: in scope) · Device-plugin roll has no manual-op or rollback

check: spec review; see reviewer return.

<!-- fr:journal kind=finding scope=spec id=s6 created=2026-11-16T20:11:56+00:00 state=open review_scope=in -->
### s6 · finding [open] (reviewer: in scope) · Test Plan does not cover several design promises

check: spec review; see reviewer return.

<!-- fr:journal kind=finding scope=spec id=s7 created=2026-11-16T20:11:56+00:00 state=open review_scope=in -->
### s7 · finding [open] (reviewer: in scope) · App wiring and exposure files incompletely named

check: spec review; see reviewer return.

<!-- fr:journal kind=review scope=spec id=spec-review created=2026-11-16T20:11:56+00:00 -->
### spec-review · review · independent spec review: 7 findings

verified against codebase; all findings in scope and fixed in the spec.

<!-- fr:journal kind=finding scope=spec id=s1-resolved created=2026-11-16T20:11:56+00:00 state=fixed resolves=s1 -->
### s1-resolved · finding [fixed] · resolves s1: gpu-switcher change is Go code plus an image bump

Spec now names parseWorkloads/Workload/ActivateWorkload edits, group syntax, Go tests, image bump and pod label.

<!-- fr:journal kind=finding scope=spec id=s2-resolved created=2026-11-16T20:11:56+00:00 state=fixed resolves=s2 -->
### s2-resolved · finding [fixed] · resolves s2: Alert changes name wrong or no files

Spec names vmprobe.yaml, alert-rules-cm.yaml:381 and :1781, the guard scripts, and defines both-down semantics.

<!-- fr:journal kind=finding scope=spec id=s3-resolved created=2026-11-16T20:11:56+00:00 state=fixed resolves=s3 -->
### s3-resolved · finding [fixed] · resolves s3: Auth model for the LAN API unspecified

Spec decides ip-allowlist + security-headers without forwardauth and sets upload limits.

<!-- fr:journal kind=finding scope=spec id=s4-resolved created=2026-11-16T20:11:56+00:00 state=fixed resolves=s4 -->
### s4-resolved · finding [fixed] · resolves s4: Time-slicing isolation gap and no VRAM guard location

Spec sets N to group size, names the budget file and guard test.

<!-- fr:journal kind=finding scope=spec id=s5-resolved created=2026-11-16T20:11:56+00:00 state=fixed resolves=s5 -->
### s5-resolved · finding [fixed] · resolves s5: Device-plugin roll has no manual-op or rollback

Spec adds the manual-op block with ordering and rollback.

<!-- fr:journal kind=finding scope=spec id=s6-resolved created=2026-11-16T20:11:56+00:00 state=fixed resolves=s6 -->
### s6-resolved · finding [fixed] · resolves s6: Test Plan does not cover several design promises

Test Plan gains rows for batch/alerts, no public ingress, benchmark; decision/benchmark file named.

<!-- fr:journal kind=finding scope=spec id=s7-resolved created=2026-11-16T20:11:56+00:00 state=fixed resolves=s7 -->
### s7-resolved · finding [fixed] · resolves s7: App wiring and exposure files incompletely named

Spec names ingressroutes.yaml, services.yaml, ArgoCD conventions and defers blog/README to close-out.

<!-- fr:journal kind=decision scope=spec id=exit-baseline created=2026-11-16T20:11:58+00:00 -->
### exit-baseline · decision · exit when spec-review resolved

The exit when spec-review resolved; `fr verification set` and `deliver` compare against it.

```yaml
row_gates:
  infer-speech-benchmark: devops
  infer-speech-gpu-sharing: devops
  infer-speech-quiet-alerts: devops
  infer-speech-stt-api: devops
  infer-speech-switcher-handover: devops
  infer-speech-tts-api: devops
row_kinds:
  infer-speech-benchmark: live
  infer-speech-gpu-sharing: live
  infer-speech-quiet-alerts: live
  infer-speech-stt-api: live
  infer-speech-switcher-handover: live
  infer-speech-tts-api: live
run_gate: devops
run_kind: live
```

<!-- fr:journal kind=decision scope=spec id=phase-split-2026-11-16--infer--speech-service-p2 created=2026-11-16T20:12:57+00:00 -->
### phase-split-2026-11-16--infer--speech-service-p2 · decision · ask: the speech app, exposure and alerts are a separate reviewable ask from GPU sharing and the switcher

<!-- fr:journal kind=decision scope=spec id=phase-split-2026-11-16--infer--speech-service-p3 created=2026-11-16T20:13:00+00:00 -->
### phase-split-2026-11-16--infer--speech-service-p3 · decision · ask: live rollout, benchmark run and follow-up filing are operator-only work

<!-- fr:journal kind=decision scope=spec id=derived-speech-image created=2026-11-16T20:30:11+00:00 -->
### derived-speech-image · decision · Operator chose a derived image with CTranslate2 >= 4.6.3 over pinning the upstream rc.3-cuda image; no upstream image has proven sm_120 support

<!-- fr:journal kind=discovery scope=spec id=test-plan-step-1 created=2026-11-22T06:23:01+00:00 -->
### test-plan-step-1 · discovery · Test Plan step 1: ran

Step: [ ] After merge, roll the device plugin and confirm `kubectl get node gpu-1 -o jsonpath='{.status.allocatable}'` shows the time-sliced `nvidia.com/gpu` count, with Ollama and speech Running together and `nvidia-smi` memory under budget.

Evidence: postmerge-timeslice-allocatable: check passed — no output

<!-- fr:journal kind=discovery scope=spec id=test-plan-step-2 created=2026-11-22T11:22:57+00:00 -->
### test-plan-step-2 · discovery · Test Plan step 2: ran

Step: [ ] POST a Greek, an English and a German sample to `/v1/audio/transcriptions` and check the language auto-detect and text.

Evidence: scripts/tmp/speech-stt-check.sh on 2026-11-22 against https://speech.cluster.derio.net (model deepdml/faster-whisper-large-v3-turbo-ct2, no language hint, speech pod on image 0.9.0-rc.3-ct2-4.6.3-r2 after frank#1017): live 8 s mic recordings auto-detected en=en, de=de, el=el, all PASS, rtf 0.07-0.09 (11-14x real time incl. network); en "The cluster is called FRANK and it lives in a cupboard."; de "Der Kloster heißt Frank und wohnt in einem Schrank." (loanword misheard as homophone); el "The cluster λέγεται Frank και μένει σε μια δουλάπα." (homophone spelling ντ/δ; code-switched English word kept in Latin script)

<!-- fr:journal kind=discovery scope=spec id=test-plan-step-3 created=2026-11-22T11:37:11+00:00 -->
### test-plan-step-3 · discovery · Test Plan step 3: ran

Step: [ ] POST text in each language to `/v1/audio/speech` and listen to the result.

Evidence: speech-tts-check.sh --try-piper on 2026-11-22 against speech.cluster.derio.net, listened on the Mac - en PASS (Kokoro-82M voice af_heart, ttfb 0.17s, 4.3s audio); de PASS (piper-de_DE-thorsten-high voice thorsten, ttfb 0.16s, 4.0s audio, 3.1s total incl. first load); el PASS (piper-el_GR-rapunzelina-low voice rapunzelina, ttfb 0.12s, 4.2s audio) - deployed Kokoro-82M has no de or el voices (with it, de had an English accent and el was spelled letter by letter), so de and el use Piper; the two Piper models were downloaded into the speech PVC at runtime and are NOT yet in PRELOAD_MODELS (follow-up pins them, spec R5 decision)
