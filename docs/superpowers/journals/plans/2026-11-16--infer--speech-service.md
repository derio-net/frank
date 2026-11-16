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
