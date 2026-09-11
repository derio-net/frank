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

<!-- fr:journal kind=finding scope=plan id=brace-count-string-unaware created=2026-09-11T11:23:05 phase=1 state=fixed -->
### brace-count-string-unaware · finding [fixed] · The injector's brace counter treated braces inside strings and comments as structure (phase 1)

Found in phase-1 review, reproduced before fixing. _find_block_close counted every brace as structure. The block it edits contains plugin_config: '{"NUM_STREAMS": "1" }' — whose braces balance only by accident — so the counter worked on today's graph and would silently break on a plausible one. Reproduced: with one extra '{' inside that quoted string the counter overshot to the brace closing node_options, the rewriter wrote BOTH bounds outside the RerankCalculatorOVOptions block, and it PRINTED SUCCESS. The calculator would never read them, the model image would publish unguarded, and CI, ArgoCD, the pod and the .seed-rev marker would all still agree it shipped — precisely the silent no-op the module's docstring promises is impossible. Latent today, live the moment any plugin_config value carries a brace in a string (a CACHE_DIR template, nested JSON). Fixed by making the scan skip quoted strings (both quote characters, with backslash-escape handling) and '#' comments. Four regression tests added, which deliberately do NOT use the test module's own _options_block helper — it counts braces the same naive way, and a helper sharing the bug under test cannot witness it; they locate the block by line instead. One of those tests initially failed on a badly-escaped fixture of my own (\\" is an escaped BACKSLASH plus a real closing quote, not an escaped quote), which is now spelled out in a comment beside it.

<!-- fr:journal kind=review scope=plan id=review-phase-1 created=2026-09-11T11:23:08 phase=1 -->
### review-phase-1 · review · Phase 1 review — one finding fixed, the rest of the work stands (phase 1)

Reviewed the six phase-1 commits against the spec and plan. The captures are verbatim and match the design's stated precondition (add_bos_token absent, model_max_length 16000, neither bound present), so nothing moved. The injector's refusal design is right and its failure messages name the file and say why a no-op would be worse. The SCANNED_PATHS work is better than the plan asked for: it found an eighth artefact the plan did not name (the three acceptance rows), measured rather than assumed that a whole-file scan of the matrix fires an unrelated hit, and scoped it by row id instead of silencing it; and it correctly did NOT re-list the injector, which the pre-existing apps/ovms-retrieval directory entry already covers by rglob. The executor's refusal to tick P1.T3.S2 as done — its push-and-confirm-CI clauses were outside its contract — is the right call and is now mine to close. One finding fixed: brace-count-string-unaware.

<!-- fr:journal kind=discovery scope=plan id=branch-ci-needs-workflow-dispatch created=2026-09-11T11:29:44 phase=1 -->
### branch-ci-needs-workflow-dispatch · discovery · Pushing a branch in this repo runs NO CI — every check is pull_request-only off main (phase 1)

P1.T3.S2 asked to push and confirm CI green before later phases build on the skeleton. That is not achievable by pushing: repo-tripwires.yml, agent-config.yml and build-ovms-retrieval-models.yml all restrict their push trigger to branches [main], so a feature-branch push starts nothing, and fr-goal reserves the PR for the deliver step. Escape hatch: both relevant workflows carry workflow_dispatch, so "gh workflow run repo-tripwires.yml --ref BRANCH" runs the real gate on the branch. Done for f1b4147f — Repo Tripwires completed success on exactly HEAD, alongside a local full-suite run of 801 passed, 1 xfailed. The step is now genuinely satisfied rather than assumed. This is the same silent-asymmetry family the build-ovms-retrieval-models.yml header already documents, where the half that runs is the half that works. Note also that phase 1 added a file under apps/ovms-retrieval/docker/, which is that workflow path filter — so the full IR build WILL fire on the eventual PR.

<!-- fr:journal kind=discovery scope=plan id=283ec622800e created=2026-09-11T11:45:00 phase=2 -->
### 283ec622800e · discovery · The sweep records a success as status 200 because _post_json throws the code away (phase 2)

Worth knowing before phase 3 quotes the curve. _post_json returns a parsed body, not a response object, so on a 2xx the actual status code is gone by the time the sweep sees it. The record therefore writes 200 for every success, and says so in a status_note field carried in the record itself rather than leaving a reader to discover it.

Failures are unaffected and are where the precision matters: a non-2xx status is the server's own, read off the raised HTTPError, and a null status means no response reached the client at all. Recording 0 or 500 for a closed socket would invent a response the server never sent, which is precisely the distinction Test Plan row 6 turns on (a response, not a closed socket).

Changing _post_json to return (status, body) was considered and rejected: every existing test and the recorder fake stand in for it returning a dict, and a signature change there is a much wider blast radius than a documented convention in one new record section.

<!-- fr:journal kind=discovery scope=plan id=718f209679f7 created=2026-09-11T11:45:12 phase=2 -->
### 718f209679f7 · discovery · HTTPError is a URLError subclass — catch order decides whether a refusal keeps its status (phase 2)

urllib.error.HTTPError subclasses URLError, which subclasses OSError; http.client.RemoteDisconnected subclasses ConnectionResetError, so it is an OSError too. A single except (URLError, OSError) would therefore swallow a refusal into the no-status branch, and the sweep would record the guard working as if the server had died — the two outcomes the curve exists to tell apart, collapsed into one.

The sweep catches HTTPError first and the socket-level family second, and the parametrised tolerance test covers all three shapes (500 refusal, RemoteDisconnected, connection refused) so the ordering cannot silently regress.

Verified against a real socket as well as the fakes: running the script against http://127.0.0.1:1 produces a complete record, provenance intact, with warm-up and both sizes carrying status null and the genuine URLError text — not a traceback. The fakes prove the sweep handles the exception types the test constructs; only the real socket proves those are the types urllib actually raises.

<!-- fr:journal kind=discovery scope=plan id=5a57633eb9c9 created=2026-09-11T11:45:27 phase=2 -->
### 5a57633eb9c9 · discovery · Padding vocabulary is derived from the filler text, not authored — and the discretion scan is why (phase 2)

--rerank-words pads each passage to an exact word count. The padding had to come from somewhere, and writing 180 words of plausible filler prose is exactly the thing scripts/tests/test_third_party_discretion.py scans this script to prevent. So _FILLER_VOCABULARY is DERIVED at import from the sentence template plus the existing topic list, and a test asserts the padded word set is a subset of the unpadded one — the property, not a promise.

Two details found while making that test true. The word note was in the pool but appears in the filler only in the rotation suffix (note N), which shows up at offsets past 20, so it is not in the base sample; dropped from the pool rather than widened in the test. And a topic's final word only ever appears comma-attached in the sentence (about basic bicycle maintenance, written as...), so a bare maintenance in the padding read as a new word; the test now strips punctuation on both sides, with the reason written beside it. That was a correction to how the test expressed the property, not a weakening of it.

generate_filler_passages REFUSES a word count below the base sentence instead of truncating. Truncating would either cut the topic anchor the degeneracy check depends on, or record a word count that was never sent.

Passage length is recorded per size MEASURED from the bodies actually built, not echoed back from the flag, so a padding bug surfaces in the record rather than being papered over by it.

<!-- fr:journal kind=finding scope=plan id=5866844fd3d1 created=2026-09-11T11:45:40 phase=2 state=open -->
### 5866844fd3d1 · finding [open] · Sweep mode replaces the timed benchmark and exits 0 whatever the curve says — two deliberate choices phase 3 must know (phase 2)

Neither is a defect; both would be surprises if met for the first time while driving a live OOM-kill.

1. --rerank-sweep REPLACES benchmark mode. main() runs the sweep, writes the record and returns before _run_rerank_benchmark or _run_embeddings_benchmark. Running a 30-iteration embeddings loop straight after deliberately killing the server would time a restarting pod and report it as embedding latency. Consequence for phase 3: a sweep record carries no embeddings or latency-percentile section at all, and a before/after comparison against the parent spec's numbers needs a separate benchmark-mode run.

2. Sweep mode exits 0 even when every size fails. A refused batch is the result, not an error. The spec's rule that a sweep in which N+1 SUCCEEDS is a failed run is a judgement against the curve, and N does not exist yet — phase 3 is what derives it. Encoding a pass/fail rule now would be guessing at the number this phase exists to make measurable. Phase 3 must read the curve rather than trust the exit code.

Left open because it is a handoff to phase 3, not a defect to fix; close it once the live sweep has been driven and the curve read.

Also worth carrying: --rerank-warmup defaults to 3, so a sweep with no explicit flag sends three extra calls at the smallest size before the curve starts.
