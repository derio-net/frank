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
