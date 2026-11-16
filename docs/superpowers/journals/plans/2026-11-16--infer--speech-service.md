<!-- fr:journal-schema=4 -->
# Journal: 2026-11-16--infer--speech-service

<!-- fr:journal kind=lens scope=plan id=lens-tests-1 created=2026-11-16T20:13:48+00:00 lens=tests step=plan -->
### lens-tests-1 · lens · Most rows are live-only, so the offline guards (VRAM budget, manifests, alert rules, switcher Go tests) carry the pre-merge confidence

<!-- fr:journal kind=decision scope=plan id=switcher-group-semantics created=2026-11-16T20:18:32+00:00 phase=1 -->
### switcher-group-semantics · decision · Group key defaults to the workload's own name (phase 1)

Entry speech:speech:speech@ollama puts speech in group 'ollama', which is also the implicit group of the workload named ollama. Activating either scales both to 1 and everything else (comfyui) to 0. ParseWorkloads(raw) (error) was extracted from parseWorkloads so the grammar is unit-testable; /api/status now also reports group.

<!-- fr:journal kind=discovery scope=plan id=switcher-image-build created=2026-11-16T20:18:32+00:00 phase=1 -->
### switcher-image-build · discovery · gpu-switcher image has no CI workflow; tag push is manual (phase 1)

No .github workflow builds it; apps/gpu-switcher/app/Dockerfile is built by hand (recent commits: cross-compile for linux/amd64). Manifest now pins ghcr.io/derio-net/gpu-switcher:v0.1.2. MANUAL STEP before merge/sync: build apps/gpu-switcher/app for linux/amd64 and push ghcr.io/derio-net/gpu-switcher:v0.1.2 (package must stay public), else ImagePullBackOff.

<!-- fr:journal kind=discovery scope=plan id=speech-env-notes created=2026-11-16T20:18:32+00:00 phase=1 -->
### speech-env-notes · discovery · Env notes (phase 1)

Worktree .venv is a dangling symlink; used the base repo's .venv/bin/pytest. Go is installed and go test ./... passes. scripts/tests is run in CI by repo-tripwires.yml (no paths filter), so the speech tests are exercised on PRs. vram-budget.yaml sizes for speech (stt 2.5, tts 2.0 GB) are estimate: true placeholders; gemma4:12b-64k 9.7 GB is the measured figure from apps/ollama/values.yaml (9,686 MiB at 16k + 846 MiB at 64k ~ 10.5 GiB, so recheck in the benchmark); qwen3.6:35b-a3b-64k is hybrid CPU/GPU and left off the allowlist.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t1 created=2026-11-16T20:18:32+00:00 phase=1 -->
### no-refactor-p1-t1 · discovery · no-refactor-because P1.T1 (phase 1)

single trivial assertion; nothing to clean

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t3 created=2026-11-16T20:18:32+00:00 phase=1 -->
### no-refactor-p1-t3 · discovery · no-refactor-because P1.T3 (phase 1)

manifest edit plus a small regex test; nothing to clean

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · WORKLOADS lists speech before its Deployment exists (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · Ollama allowlist not enforced against what Ollama can load (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · VRAM guard self-referential, num_ctx not compared (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · gpu-switcher v0.1.2 has no CI build; manual push (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r5 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=in -->
### p1-r5 · finding [open] (reviewer: in scope) · Stale gpu-switcher v0.1.1 references (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r6 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=in -->
### p1-r6 · finding [open] (reviewer: in scope) · time-slicing ConfigMap vs ClusterPolicy sync ordering (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r7 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=in -->
### p1-r7 · finding [open] (reviewer: in scope) · ParseWorkloads Split vs SplitN (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r8 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=in -->
### p1-r8 · finding [open] (reviewer: in scope) · Go tests miss pod-label status and partial-failure ordering (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r9 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=in -->
### p1-r9 · finding [open] (reviewer: in scope) · UI does not show the group (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r10 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=out -->
### p1-r10 · finding [open] (reviewer: out of scope) · Activation ordering follows WORKLOADS list (pre-existing) (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r11 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=out -->
### p1-r11 · finding [open] (reviewer: out of scope) · Time-slicing has no VRAM isolation (by design, documented) (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=finding scope=plan id=p1-r12 created=2026-11-16T20:23:36+00:00 phase=1 state=open review_scope=out -->
### p1-r12 · finding [open] (reviewer: out of scope) · speech ignoreDifferences rule belongs to phase 2 (phase 1)

Reviewer a6b08dc69666a4275, phase 1.

<!-- fr:journal kind=review scope=plan id=p1-review created=2026-11-16T20:23:36+00:00 phase=1 -->
### p1-review · review · phase 1 review: 12 findings (phase 1)

Independent read-only review of the phase 1 diff; 8 in-scope findings fixed or refuted, 3 out of scope.

<!-- fr:journal kind=finding scope=plan id=p1-r1-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=refuted resolves=p1-r1 -->
### p1-r1-resolved · finding [refuted] · resolves p1-r1: WORKLOADS lists speech before its Deployment exists (phase 1)

Phase 1 and 2 land in one PR; ArgoCD syncs main only after merge, when the speech Deployment exists, so the switcher never runs against a missing Deployment.

<!-- fr:journal kind=finding scope=plan id=p1-r2-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=fixed resolves=p1-r2 -->
### p1-r2-resolved · finding [fixed] · resolves p1-r2: Ollama allowlist not enforced against what Ollama can load (phase 1)

vram-budget.yaml now classifies every chart-created model as allowlisted or excluded; test enforces both directions plus OLLAMA_MAX_LOADED_MODELS=1.

<!-- fr:journal kind=finding scope=plan id=p1-r3-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=fixed resolves=p1-r3 -->
### p1-r3-resolved · finding [fixed] · resolves p1-r3: VRAM guard self-referential, num_ctx not compared (phase 1)

Guard now compares allowlisted num_ctx to the Modelfile PARAMETER.

<!-- fr:journal kind=finding scope=plan id=p1-r4-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=fixed resolves=p1-r4 -->
### p1-r4-resolved · finding [fixed] · resolves p1-r4: gpu-switcher v0.1.2 has no CI build; manual push (phase 1)

Added pre-merge op premerge-gpu-switcher-image to the plan ops.yaml, checked with docker manifest inspect.

<!-- fr:journal kind=finding scope=plan id=p1-r5-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=fixed resolves=p1-r5 -->
### p1-r5-resolved · finding [fixed] · resolves p1-r5: Stale gpu-switcher v0.1.1 references (phase 1)

README and life fixtures updated to v0.1.2; life image tests pass.

<!-- fr:journal kind=finding scope=plan id=p1-r6-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=refuted resolves=p1-r6 -->
### p1-r6-resolved · finding [refuted] · resolves p1-r6: time-slicing ConfigMap vs ClusterPolicy sync ordering (phase 1)

Transient: selfHeal converges, the plugin retries until the ConfigMap exists, and the roll is an ordered manual op anyway.

<!-- fr:journal kind=finding scope=plan id=p1-r7-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=refuted resolves=p1-r7 -->
### p1-r7-resolved · finding [refuted] · resolves p1-r7: ParseWorkloads Split vs SplitN (phase 1)

No valid Kubernetes name contains a colon; rejecting extra colons is stricter and intended.

<!-- fr:journal kind=finding scope=plan id=p1-r8-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=refuted resolves=p1-r8 -->
### p1-r8-resolved · finding [refuted] · resolves p1-r8: Go tests miss pod-label status and partial-failure ordering (phase 1)

The pod-label path is untouched code and the partial-failure ordering predates this change; group behaviour is covered by the fake-clientset tests.

<!-- fr:journal kind=finding scope=plan id=p1-r9-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=refuted resolves=p1-r9 -->
### p1-r9-resolved · finding [refuted] · resolves p1-r9: UI does not show the group (phase 1)

The spec requires no UI work; the API change is additive and index.html keeps working.

<!-- fr:journal kind=finding scope=plan id=p1-r10-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=open resolves=p1-r10 out_of_scope=true -->
### p1-r10-resolved · finding [out-of-scope] · resolves p1-r10: Activation ordering follows WORKLOADS list (pre-existing) (phase 1)

Pre-existing ordering, not caused by this change.

<!-- fr:journal kind=finding scope=plan id=p1-r11-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=open resolves=p1-r11 out_of_scope=true -->
### p1-r11-resolved · finding [out-of-scope] · resolves p1-r11: Time-slicing has no VRAM isolation (by design, documented) (phase 1)

By design and documented in gpu-1.md.

<!-- fr:journal kind=finding scope=plan id=p1-r12-resolved created=2026-11-16T20:23:36+00:00 phase=1 state=open resolves=p1-r12 out_of_scope=true -->
### p1-r12-resolved · finding [out-of-scope] · resolves p1-r12: speech ignoreDifferences rule belongs to phase 2 (phase 1)

Belongs to phase 2, not this phase's change.

<!-- fr:journal kind=decision scope=plan id=derived-speech-image created=2026-11-16T20:46:54+00:00 phase=2 -->
### derived-speech-image · decision · Build a derived speaches image with CTranslate2 4.6.3 instead of using an upstream tag (phase 2)

Operator decision (2026-11-16): no upstream speaches image proves Blackwell sm_120 support (0.9.0-rc.3-cuda, digest sha256:f4eb14d1c53b19c5bd1f76d10ea9fc10288ceaf82dca09506d3f0ef92ee943de, ships CTranslate2 4.5.0 on CUDA 12.2). apps/speech/docker/Dockerfile is FROM that digest and `uv pip install`s ctranslate2==4.6.3 into the image venv, with a build-time version assertion. CI (.github/workflows/build-speech.yml, SPEECH_REV tag, copy of build-comfyui.yml's shape) builds it; the Deployment pins ghcr.io/derio-net/speech:<SPEECH_REV>, equality guarded by test_speech_image_build.py. The derived image is pinned by tag only; no digest is invented.

<!-- fr:journal kind=discovery scope=plan id=ctranslate2-version-compat created=2026-11-16T20:46:54+00:00 phase=2 -->
### ctranslate2-version-compat · discovery · ctranslate2 4.6.3 exists on PyPI with cp312 manylinux wheels and is compatible with faster-whisper 1.1.1 (phase 2)

curl against pypi.org (2026-11-16): ctranslate2 4.6.2, 4.6.3, 4.7.0 and 4.7.1 all exist (latest 4.9.0); 4.6.3 has cp310/311/312 manylinux_2_27 x86_64 wheels and requires_python >=3.9, requires setuptools/numpy/pyyaml. The upstream venv is Python 3.12 (speaches pyproject requires-python ==3.12.*) and pins ctranslate2>=4.5.0. faster-whisper 1.1.1 requires ctranslate2<5,>=4.0, so the bump stays within its declared range. The 4.6.3 manylinux_2_27 wheel needs glibc >= 2.27; the Ubuntu 24.04 base is fine. NOT verified on-card: sm_120 STT behaviour is proven only by the ops-gated live benchmark (infer-speech-benchmark-run), and the CUDA 12.8 CT2 build is run against the image's CUDA 12.9 runtime.

<!-- fr:journal kind=discovery scope=plan id=speech-model-ids created=2026-11-16T20:46:54+00:00 phase=2 -->
### speech-model-ids · discovery · Default model repos verified on Hugging Face (phase 2)

HF API (2026-11-16): deepdml/faster-whisper-large-v3-turbo-ct2 and speaches-ai/Kokoro-82M-v1.0-ONNX return 200 (mobiuslabsgmbh/faster-whisper-large-v3-turbo redirects, 307, so not used). Preloaded through speaches' PRELOAD_MODELS; vram-budget.yaml names the same two repos (guarded). Sizes remain estimate: true. Kokoro's Greek/German quality is unproven: the TTS engine for EL/DE is chosen by the benchmark.

<!-- fr:journal kind=discovery scope=plan id=speech-route-limits created=2026-11-16T20:46:54+00:00 phase=2 -->
### speech-route-limits · discovery · Long-recording limits are per-route (buffering middleware + ServersTransport), not entrypoint timeouts (phase 2)

The Traefik chart sets no explicit respondingTimeouts; changing the websecure entrypoint would affect every route. The speech route instead gets a `speech-upload-limit` buffering middleware (2 GiB request cap, 32 MiB in-memory before spilling to temp) and a `speech-long-requests` ServersTransport (responseHeaderTimeout 3h, since transcription returns headers only when the whole file is done). Buffering spills to the Traefik pod's temp dir; if the live run shows the pod's filesystem is read-only/too small for a large upload, the fallback is to drop the middleware and accept the uvicorn default (no cap).

<!-- fr:journal kind=discovery scope=plan id=shell-guard-offline created=2026-11-16T20:46:54+00:00 phase=2 -->
### shell-guard-offline · discovery · assert-gpu-timeshare-rules.sh cannot run via `uv run` here; its embedded Python was run with the repo venv (phase 2)

`uv run --with pyyaml` in the worktree resolves the project's frank-cluster-scripts deps and fails building pydantic-core on this Mac's default Python 3.15. The script body is pure PyYAML, so the embedded heredoc was extracted and run with the repo .venv python: OK (L11/L16, both-down, route ordering, speech probe/rule/exclusion). The scale-to-zero and both-down guarantees are also covered by pytest in test_feature_health_workload_metrics.py.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t1 created=2026-11-16T20:46:54+00:00 phase=2 -->
### no-refactor-p2-t1 · discovery · no-refactor-because P2.T1 (phase 2)

Image test plus Dockerfile and workflow were written together as one small unit; nothing to clean.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t3 created=2026-11-16T20:46:54+00:00 phase=2 -->
### no-refactor-p2-t3 · discovery · no-refactor-because P2.T3 (phase 2)

The route reuses the existing ip-allowlist/security-headers middlewares; the only new objects are the buffering middleware and ServersTransport, already minimal.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p2-t5 created=2026-11-16T20:46:54+00:00 phase=2 -->
### no-refactor-p2-t5 · discovery · no-refactor-because P2.T5 (phase 2)

Benchmark script is a single stdlib module built to its test; nothing to clean.

<!-- fr:journal kind=finding scope=plan id=p2-r1 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r1 · finding [open] (reviewer: in scope) · Buffering middleware exhausts edge disk and buffers TTS (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r2 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=out -->
### p2-r2 · finding [open] (reviewer: out of scope) · No per-request auth on route (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r3 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r3 · finding [open] (reviewer: in scope) · Allowlist covers all RFC1918 (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r4 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r4 · finding [open] (reviewer: in scope) · Pre-merge image build via workflow_dispatch not runnable (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r5 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r5 · finding [open] (reviewer: in scope) · Workflow paths filter ignores rev bump (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r6 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r6 · finding [open] (reviewer: in scope) · Probes hit shallow /health (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r7 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r7 · finding [open] (reviewer: in scope) · Liveness margin thin during long jobs (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r8 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r8 · finding [open] (reviewer: in scope) · Entrypoint timeouts untouched (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r9 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r9 · finding [open] (reviewer: in scope) · Benchmark uses one TTS voice for all languages (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r10 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r10 · finding [open] (reviewer: in scope) · VRAM figure is whole card (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r11 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r11 · finding [open] (reviewer: in scope) · Benchmark op filename and inputs wrong (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r12 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r12 · finding [open] (reviewer: in scope) · Device-plugin roll ordering and restart claim (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r13 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r13 · finding [open] (reviewer: in scope) · Dockerfile upstream details unverified (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r14 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r14 · finding [open] (reviewer: in scope) · Image build test weak (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r15 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r15 · finding [open] (reviewer: in scope) · Smoke and manifest tests vacuous (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r16 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r16 · finding [open] (reviewer: in scope) · Gotcha entry too long (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r17 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=out -->
### p2-r17 · finding [open] (reviewer: out of scope) · pod-security privileged (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r18 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=out -->
### p2-r18 · finding [open] (reviewer: out of scope) · Time-slicing overlap during switch (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r19 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=out -->
### p2-r19 · finding [open] (reviewer: out of scope) · Phase 1 items (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r20 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=in -->
### p2-r20 · finding [open] (reviewer: in scope) · Health rule lacks startup grace (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=finding scope=plan id=p2-r21 created=2026-11-16T20:55:56+00:00 phase=2 state=open review_scope=out -->
### p2-r21 · finding [open] (reviewer: out of scope) · Verified-OK note (phase 2)

Reviewer a1da39f1e24c1aec6, phase 2.

<!-- fr:journal kind=review scope=plan id=p2-review created=2026-11-16T20:55:56+00:00 phase=2 -->
### p2-review · review · phase 2 review: 21 findings (phase 2)

Independent read-only review; in-scope findings fixed in commit b3fe5def; the automated security review's two findings are covered by r1 and r3/r2.

<!-- fr:journal kind=finding scope=plan id=p2-r1-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r1 -->
### p2-r1-resolved · finding [fixed] · resolves p2-r1: Buffering middleware exhausts edge disk and buffers TTS (phase 2)

Buffering middleware removed from middlewares.yaml and the route; tests assert none.

<!-- fr:journal kind=finding scope=plan id=p2-r2-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=open resolves=p2-r2 out_of_scope=true -->
### p2-r2-resolved · finding [out-of-scope] · resolves p2-r2: No per-request auth on route (phase 2)

No per-request auth is the spec-accepted trade-off (litellm/comfyui precedent); the route is now additionally narrowed to LAN and mesh CIDRs (r3).

<!-- fr:journal kind=finding scope=plan id=p2-r3-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r3 -->
### p2-r3-resolved · finding [fixed] · resolves p2-r3: Allowlist covers all RFC1918 (phase 2)

speech-ip-allowlist (LAN, mesh 100.64.0.0/10) used on the route.

<!-- fr:journal kind=finding scope=plan id=p2-r4-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r4 -->
### p2-r4-resolved · finding [fixed] · resolves p2-r4: Pre-merge image build via workflow_dispatch not runnable (phase 2)

Op and ops.yaml now do a local buildx build and push.

<!-- fr:journal kind=finding scope=plan id=p2-r5-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r5 -->
### p2-r5-resolved · finding [fixed] · resolves p2-r5: Workflow paths filter ignores rev bump (phase 2)

Workflow file added to on.push.paths, test added.

<!-- fr:journal kind=finding scope=plan id=p2-r6-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r6 -->
### p2-r6-resolved · finding [fixed] · resolves p2-r6: Probes hit shallow /health (phase 2)

Readiness /v1/models, startup and liveness tuned, vmprobe /v1/models.

<!-- fr:journal kind=finding scope=plan id=p2-r7-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r7 -->
### p2-r7-resolved · finding [fixed] · resolves p2-r7: Liveness margin thin during long jobs (phase 2)

Liveness tolerates 10 minutes of a blocked loop.

<!-- fr:journal kind=finding scope=plan id=p2-r8-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r8 -->
### p2-r8-resolved · finding [fixed] · resolves p2-r8: Entrypoint timeouts untouched (phase 2)

Documented: long recordings use the in-cluster Service URL; entrypoint left untouched on purpose.

<!-- fr:journal kind=finding scope=plan id=p2-r9-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r9 -->
### p2-r9-resolved · finding [fixed] · resolves p2-r9: Benchmark uses one TTS voice for all languages (phase 2)

Per-language --tts LANG=MODEL:VOICE and saved audio.

<!-- fr:journal kind=finding scope=plan id=p2-r10-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r10 -->
### p2-r10-resolved · finding [fixed] · resolves p2-r10: VRAM figure is whole card (phase 2)

Speech-only VRAM = peak - baseline.

<!-- fr:journal kind=finding scope=plan id=p2-r11-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r11 -->
### p2-r11-resolved · finding [fixed] · resolves p2-r11: Benchmark op filename and inputs wrong (phase 2)

Filename fixed, samples-dir documented, robust commands.

<!-- fr:journal kind=finding scope=plan id=p2-r12-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r12 -->
### p2-r12-resolved · finding [fixed] · resolves p2-r12: Device-plugin roll ordering and restart claim (phase 2)

Ordering stated and restart claim corrected.

<!-- fr:journal kind=finding scope=plan id=p2-r13-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r13 -->
### p2-r13-resolved · finding [fixed] · resolves p2-r13: Dockerfile upstream details unverified (phase 2)

Verified upstream at the pinned tag; UV_NO_SYNC and a stronger build assert.

<!-- fr:journal kind=finding scope=plan id=p2-r14-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r14 -->
### p2-r14-resolved · finding [fixed] · resolves p2-r14: Image build test weak (phase 2)

Workflow arg compared to Dockerfile ARG, vacuous assert dropped.

<!-- fr:journal kind=finding scope=plan id=p2-r15-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r15 -->
### p2-r15-resolved · finding [fixed] · resolves p2-r15: Smoke and manifest tests vacuous (phase 2)

Smoke and manifest tests made meaningful, non-root context added.

<!-- fr:journal kind=finding scope=plan id=p2-r16-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r16 -->
### p2-r16-resolved · finding [fixed] · resolves p2-r16: Gotcha entry too long (phase 2)

One-liner pointing to gpu-1.md.

<!-- fr:journal kind=finding scope=plan id=p2-r17-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=open resolves=p2-r17 out_of_scope=true -->
### p2-r17-resolved · finding [out-of-scope] · resolves p2-r17: pod-security privileged (phase 2)

pod-security privileged matches the comfyui/ollama precedent; not caused by this change.

<!-- fr:journal kind=finding scope=plan id=p2-r18-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=open resolves=p2-r18 out_of_scope=true -->
### p2-r18-resolved · finding [out-of-scope] · resolves p2-r18: Time-slicing overlap during switch (phase 2)

Overlap during a switch is a phase 1/spec design point of time-slicing, documented in gpu-1.md.

<!-- fr:journal kind=finding scope=plan id=p2-r19-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=open resolves=p2-r19 out_of_scope=true -->
### p2-r19-resolved · finding [out-of-scope] · resolves p2-r19: Phase 1 items (phase 2)

Phase 1 matters, already reviewed.

<!-- fr:journal kind=finding scope=plan id=p2-r20-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=fixed resolves=p2-r20 -->
### p2-r20-resolved · finding [fixed] · resolves p2-r20: Health rule lacks startup grace (phase 2)

speech-health-degraded now has a 30m for.

<!-- fr:journal kind=finding scope=plan id=p2-r21-resolved created=2026-11-16T20:55:56+00:00 phase=2 state=open resolves=p2-r21 out_of_scope=true -->
### p2-r21-resolved · finding [out-of-scope] · resolves p2-r21: Verified-OK note (phase 2)

Reviewer verified-OK note, no defect.

<!-- fr:journal kind=finding scope=plan id=l-security-r1 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-security-r1 · finding [open] (reviewer: in scope) · Speech namespace at PodSecurity privileged

security lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-security-r2 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-security-r2 · finding [open] (reviewer: in scope) · No container hardening securityContext

security lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-security-r3 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-security-r3 · finding [open] (reviewer: in scope) · Allowlist is the only control, in-cluster pods bypass it

security lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-security-r4 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-security-r4 · finding [open] (reviewer: in scope) · No concurrency/size limit on unauthenticated route

security lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-security-r5 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-security-r5 · finding [open] (reviewer: in scope) · Mutable action and model references

security lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-security-r6 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-security-r6 · finding [open] (reviewer: in scope) · Benchmark script and op use predictable tmp paths and raw multipart

security lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-security-r7 created=2026-11-16T21:03:58+00:00 state=open review_scope=out -->
### l-security-r7 · finding [open] (reviewer: out of scope) · gpu-switcher ClusterRole is cluster-wide (pre-existing)

security lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-tests-r1 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-tests-r1 · finding [open] (reviewer: in scope) · ParseWorkloads accepts dangling group

tests lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-tests-r2 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-tests-r2 · finding [open] (reviewer: in scope) · Switcher manifest test restates the grammar

tests lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-tests-r3 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-tests-r3 · finding [open] (reviewer: in scope) · Ingress timeout test overclaims, silently skips middlewares

tests lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-tests-r4 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-tests-r4 · finding [open] (reviewer: in scope) · Degraded rule test checks substrings

tests lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-tests-r5 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-tests-r5 · finding [open] (reviewer: in scope) · PVC test misses the mount

tests lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-tests-r6 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-tests-r6 · finding [open] (reviewer: in scope) · Dockerfile ctranslate2 guard vacuous

tests lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-tests-r7 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-tests-r7 · finding [open] (reviewer: in scope) · Benchmark fake server and error paths weak

tests lens reviewer.

<!-- fr:journal kind=finding scope=plan id=l-tests-r8 created=2026-11-16T21:03:58+00:00 state=open review_scope=in -->
### l-tests-r8 · finding [open] (reviewer: in scope) · Tests restate manifests, grace window unrelated to startup budget

tests lens reviewer.

<!-- fr:journal kind=review scope=plan id=lens-review created=2026-11-16T21:03:58+00:00 -->
### lens-review · review · security and tests lens reviews: 15 findings

One dispatched reviewer per lens; in-scope findings fixed in the lens fix commits.

<!-- fr:journal kind=finding scope=plan id=l-security-r1-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-security-r1 -->
### l-security-r1-resolved · finding [fixed] · resolves l-security-r1: Speech namespace at PodSecurity privileged

Namespace now baseline.

<!-- fr:journal kind=finding scope=plan id=l-security-r2-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-security-r2 -->
### l-security-r2-resolved · finding [fixed] · resolves l-security-r2: No container hardening securityContext

Container securityContext hardened; readOnlyRootFilesystem left off with a reason.

<!-- fr:journal kind=finding scope=plan id=l-security-r3-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-security-r3 -->
### l-security-r3-resolved · finding [fixed] · resolves l-security-r3: Allowlist is the only control, in-cluster pods bypass it

Comment made honest; NetworkPolicy and CIDR narrowing recorded as follow-up in the spec (R10 and not-done list).

<!-- fr:journal kind=finding scope=plan id=l-security-r4-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-security-r4 -->
### l-security-r4-resolved · finding [fixed] · resolves l-security-r4: No concurrency/size limit on unauthenticated route

speech-inflight inFlightReq (4 per source IP) added.

<!-- fr:journal kind=finding scope=plan id=l-security-r5-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-security-r5 -->
### l-security-r5-resolved · finding [fixed] · resolves l-security-r5: Mutable action and model references

Actions pinned to SHAs already used in repo workflows; image hash and model revision pinning accepted as low risk, noted in comments.

<!-- fr:journal kind=finding scope=plan id=l-security-r6-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-security-r6 -->
### l-security-r6-resolved · finding [fixed] · resolves l-security-r6: Benchmark script and op use predictable tmp paths and raw multipart

Scheme and field validation, mktemp in the manual op.

<!-- fr:journal kind=finding scope=plan id=l-security-r7-resolved created=2026-11-16T21:03:58+00:00 state=open resolves=l-security-r7 out_of_scope=true -->
### l-security-r7-resolved · finding [out-of-scope] · resolves l-security-r7: gpu-switcher ClusterRole is cluster-wide (pre-existing)

Pre-existing, unchanged by this diff.

<!-- fr:journal kind=finding scope=plan id=l-tests-r1-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-tests-r1 -->
### l-tests-r1-resolved · finding [fixed] · resolves l-tests-r1: ParseWorkloads accepts dangling group

Dangling group rejected; Go test reads the shipped WORKLOADS value.

<!-- fr:journal kind=finding scope=plan id=l-tests-r2-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-tests-r2 -->
### l-tests-r2-resolved · finding [fixed] · resolves l-tests-r2: Switcher manifest test restates the grammar

Grammar copy removed; WORKLOADS split strips @group.

<!-- fr:journal kind=finding scope=plan id=l-tests-r3-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-tests-r3 -->
### l-tests-r3-resolved · finding [fixed] · resolves l-tests-r3: Ingress timeout test overclaims, silently skips middlewares

Test split and renamed, missing middleware now fails.

<!-- fr:journal kind=finding scope=plan id=l-tests-r4-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-tests-r4 -->
### l-tests-r4-resolved · finding [fixed] · resolves l-tests-r4: Degraded rule test checks substrings

Regex assertions on the rule shape.

<!-- fr:journal kind=finding scope=plan id=l-tests-r5-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-tests-r5 -->
### l-tests-r5-resolved · finding [fixed] · resolves l-tests-r5: PVC test misses the mount

Mount, mount path and uid asserted.

<!-- fr:journal kind=finding scope=plan id=l-tests-r6-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-tests-r6 -->
### l-tests-r6-resolved · finding [fixed] · resolves l-tests-r6: Dockerfile ctranslate2 guard vacuous

Asserts the install line uses the version arg.

<!-- fr:journal kind=finding scope=plan id=l-tests-r7-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-tests-r7 -->
### l-tests-r7-resolved · finding [fixed] · resolves l-tests-r7: Benchmark fake server and error paths weak

Multipart parsed; error paths and bad --tts keys tested.

<!-- fr:journal kind=finding scope=plan id=l-tests-r8-resolved created=2026-11-16T21:03:58+00:00 state=fixed resolves=l-tests-r8 -->
### l-tests-r8-resolved · finding [fixed] · resolves l-tests-r8: Tests restate manifests, grace window unrelated to startup budget

for raised to 45m and asserted above the startup budget; other points accepted as live-only limits.

<!-- fr:journal kind=finding scope=plan id=p1-r10-resolved-2 created=2026-11-16T21:55:32+00:00 phase=1 state=open resolves=p1-r10 tracked_by=https://github.com/derio-net/frank/issues/1008 -->
### p1-r10-resolved-2 · finding [deferred → https://github.com/derio-net/frank/issues/1008] · resolves p1-r10: Activation ordering follows WORKLOADS list (pre-existing) (phase 1)

Filed at deliver as https://github.com/derio-net/frank/issues/1008.

<!-- fr:journal kind=finding scope=plan id=p1-r11-resolved-2 created=2026-11-16T21:55:39+00:00 phase=1 state=open resolves=p1-r11 tracked_by=https://github.com/derio-net/frank/issues/1009 -->
### p1-r11-resolved-2 · finding [deferred → https://github.com/derio-net/frank/issues/1009] · resolves p1-r11: Time-slicing has no VRAM isolation (by design, documented) (phase 1)

Filed at deliver as https://github.com/derio-net/frank/issues/1009.
