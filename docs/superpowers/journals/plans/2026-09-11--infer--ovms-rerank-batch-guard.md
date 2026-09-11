# Journal: 2026-09-11--infer--ovms-rerank-batch-guard

<!-- fr:journal kind=discovery scope=plan id=nrb-p1t1 created=2026-09-11T10:57:21 phase=1 -->
### nrb-p1t1 · discovery · no-refactor-because P1.T1 (phase 1)

This task writes no code. It captures two files verbatim off the running pod into a fixture directory; the whole point is that the bytes are unedited, so there is nothing to clean up and any tidying would destroy the property the fixture exists to have.

<!-- fr:journal kind=discovery scope=plan id=nrb-p1t3 created=2026-09-11T10:57:22 phase=1 -->
### nrb-p1t3 · discovery · no-refactor-because P1.T3 (phase 1)

Appending paths to SCANNED_PATHS and running the suite. No production code, no design latitude — the list is a list, and the second step is a CI observation. The injector's refactor lives in P1.T2.S3, where the code actually is.

<!-- fr:journal kind=discovery scope=plan id=nrb-p3t1 created=2026-09-11T10:57:24 phase=3 -->
### nrb-p3t1 · discovery · no-refactor-because P3.T1 (phase 3)

Measurement, not implementation: read the baseline restart count and idle working set, then run the harness built and refactored in phase 2. Refactoring the instrument mid-measurement would invalidate the curve.

<!-- fr:journal kind=discovery scope=plan id=nrb-p3t2 created=2026-09-11T10:57:26 phase=3 -->
### nrb-p3t2 · discovery · no-refactor-because P3.T2 (phase 3)

Live cluster operations plus arithmetic over the resulting curve. The only artefact produced is two numbers written into the spec and the reasoning behind them written into this journal. Nothing here is code that could be refactored.

<!-- fr:journal kind=discovery scope=plan id=nrb-p3t3 created=2026-09-11T10:57:28 phase=3 -->
### nrb-p3t3 · discovery · no-refactor-because P3.T3 (phase 3)

A restore-and-verify task: put the ArgoCD sync policy back exactly as found and assert on the live object. It is deliberately a separate task rather than a trailing step precisely so it cannot be skipped — turning it into a refactor slot would dilute that.

<!-- fr:journal kind=discovery scope=plan id=nrb-p6t2 created=2026-09-11T10:57:29 phase=6 -->
### nrb-p6t2 · discovery · no-refactor-because P6.T2 (phase 6)

Prose edits to two existing blog posts plus the final full-suite gate. The refactor step for phase 6's documentation work is P6.T1.S3, which re-reads the gotcha and runbook prose against house style; re-reading the same posts twice in one phase is ceremony, not review.

<!-- fr:journal kind=discovery scope=plan id=3771e3702078 created=2026-09-11T11:00:41 phase=1 -->
### 3771e3702078 · discovery · Live captures match the spec's precondition exactly (phase 1)

Captured from `deploy/ovms-retrieval` container `ovms` on 2026-09-11.

`graph.pbtxt`: one `node {}` named `RerankExecutor`, `calculator: "RerankCalculatorOV"`, `node_options` holding exactly `models_path: "./"`, `plugin_config: '{"NUM_STREAMS": "1" }'`, `target_device: "GPU"`. Neither `max_allowed_chunks` nor `max_position_embeddings` is present, so the proto default of 10000 documents is live — as the spec established from upstream source.

`tokenizer_config.json` (381 bytes): `add_bos_token` ABSENT, `model_max_length` 16000, `tokenizer_class` `XLMRobertaTokenizer`. Absent is the answer the design needed: `RerankServable::addBosToken` stays true, so `max_position_embeddings` is a CHUNKING boundary, not a hard rejection boundary. The design's cost note (chunked scoring semantics for long documents) stands as written; no revisit needed.

Neither capture was hand-edited.

<!-- fr:journal kind=discovery scope=plan id=42511195a930 created=2026-09-11T11:17:26 phase=1 -->
### 42511195a930 · discovery · docs/acceptance/matrix.yaml needs ROW-scoping, not a whole-file entry (phase 1)

The plan's P1.T3.S1 names seven artefacts. There is an eighth: this branch also appends three rows to `docs/acceptance/matrix.yaml`, which carries prose about the work and is therefore in scope.

It cannot go into `SCANNED_PATHS` whole. Measured, not assumed: scanning the 900+-line file fires exactly one hit, on a row belonging to an unrelated layer where a frank issue citation lands inside the context window of a requester-word. Silencing it would mean exempting a number this work has never looked at — which is precisely the rot the file documents. So the matrix is scoped by row id (`_SCOPED_ACCEPTANCE_ROWS` + `_acceptance_row_text()`), mirroring the `_SCOPED_OPS` treatment of the 144-op manual-operations registry, with the same loud assertion if a row is renamed or dropped.

Also deliberately NOT re-listed: `apps/ovms-retrieval/docker/inject_rerank_guard.py`. It is already covered by the existing `apps/ovms-retrieval` directory entry, which `_files()` walks with `rglob`. Verified by walking `_files()` — every branch artefact is scanned, with zero duplicate entries — rather than by reading the list.

<!-- fr:journal kind=finding scope=plan id=bff70c36faa4 created=2026-09-11T11:17:33 phase=1 state=fixed -->
### bff70c36faa4 · finding [fixed] · The discretion guard fired on the comment explaining the discretion guard (phase 1)

While documenting WHY `docs/acceptance/matrix.yaml` is row-scoped, the natural comment quoted the one hit a whole-file scan produces — the issue number and the requester-word beside it. `test_third_party_discretion.py` scans itself, so the comment tripped `test_no_issue_number_is_correlatable_with_the_requester` immediately.

Useful two ways. It is live proof the self-scan works rather than being decorative prose about working. And the fix followed the file's own stated rule — 'if a match is genuinely benign, rephrase rather than widen the allowlist' — so the comment now describes the shape of the hit and tells the reader to re-derive it by scanning the file whole, instead of reproducing it. Adding `_SELFTEST_MARKER` would have been the wrong reflex: that exemption exists for the detector's own pattern definitions, not for a sentence that is inconvenient.

No open risk. Full suite after the change: 797 passed, 1 xfailed.

<!-- fr:journal kind=discovery scope=plan id=42347127ea0d created=2026-09-11T11:17:47 phase=1 -->
### 42347127ea0d · discovery · The captured graph.pbtxt has NO trailing newline — that is the server's bytes (phase 1)

`scripts/tests/fixtures/ovms-retrieval/rerank-graph.live.pbtxt` is 518 bytes ending in `}` with no final newline. That reads like a sloppy capture and is not one: `export_model.py`'s Jinja template emits it that way and the pod serves exactly those bytes. The companion `tokenizer_config.json` DOES end in a newline, so the difference is upstream's, not the capture's.

Consequence for phase 3: the injector preserves it (it splices inside the options block and never touches the tail), so a rewritten graph is still newline-free at EOF. Any later check that compares the built graph against a hand-written expected file must account for that, or it will fail on a byte nobody added.

<!-- fr:journal kind=finding scope=plan id=1894eae90d3b created=2026-09-11T11:18:38 phase=1 state=open -->
### 1894eae90d3b · finding [open] · P1.T3.S2 is half done: suite is green locally, CI confirmation is owed (phase 1)

`uv run --frozen pytest scripts/tests -q` -> **797 passed, 1 xfailed in 447s** on the branch as committed. That is the local half of the step.

The other half — push the branch and confirm CI is green *before any later phase builds on it* — was deliberately not performed. The phase executor never pushes and never opens a PR; delivery is the orchestrator's. So the step is recorded `-` with a note rather than `x`, because ticking it would claim a CI observation nobody has made.

**Open until the orchestrator pushes and reads the run.** Phase 2 measures a live server and phase 3 rewrites the Dockerfile; both assume this skeleton is genuinely green in CI and not just on a Mac. The local run cannot substitute: the suite has never executed against this branch on the CI runner, and the one thing phase 1 exists to establish is that it does.
