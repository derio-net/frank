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

<!-- fr:journal kind=finding scope=plan id=sweep-no-recovery-wait created=2026-09-11T11:49:36 phase=2 state=fixed -->
### sweep-no-recovery-wait · finding [fixed] · The sweep walked straight from a killed server into the next size (phase 2)

Found in phase-2 review. _run_rerank_sweep attempted its sizes back to back with no wait, so a size that OOM-killed the server was followed immediately by the next one against a restarting pod. The issue this instrument exists to measure records about ten seconds of refused connections after each kill, so that next size would record a URLError indistinguishable from its own death — a size that was never served, entered into the curve as a size that failed, in the very curve the guard cap is read off. Fixed by waiting for the reranker to serve again after any failure with NO status, which is the discriminator: a refusal carries the server code and leaves it serving, so only a closed or refused socket means the process went away. The wait probes the MODEL-level endpoint rather than server liveness, because the server answers server-level liveness while its servable is still loading — the same trap the Deployment probes are written around. A timeout is recorded with a note rather than raised, so a sweep that could not confirm recovery says so instead of vanishing, and the recovery duration is itself data. Four tests plus an autouse fixture that makes the wait instant offline, so the rest of the module does not block on a five-minute timeout; the tests that assert the wait override the seam explicitly.

<!-- fr:journal kind=review scope=plan id=review-phase-2 created=2026-09-11T11:49:38 phase=2 -->
### review-phase-2 · review · Phase 2 review — one finding fixed, the instrument is otherwise sound (phase 2)

Reviewed the seven phase-2 commits against the spec and plan. Both defects the phase existed to remove are genuinely gone, and two of the executor discoveries are load-bearing: HTTPError is a URLError subclass and RemoteDisconnected is an OSError, so a single combined except clause would have recorded a working guard as a dead server, collapsing exactly the two outcomes the curve exists to separate; and the padding vocabulary is derived from the existing filler rather than authored, which is the right answer to the discretion constraint. Recording status 200 as a convention with a status_note, rather than changing the _post_json signature every test depends on, is the proportionate call. One finding fixed: sweep-no-recovery-wait.

<!-- fr:journal kind=finding scope=plan id=p1-ci-carryover-closed created=2026-09-11T11:49:55 phase=1 state=fixed -->
### p1-ci-carryover-closed · finding [fixed] · Phase-1 carry-over closed: branch validated via workflow_dispatch (phase 1)

The phase-1 executor left P1.T3.S2 at - because its push-and-confirm-CI clauses were outside its contract. Closed by the orchestrator: Repo Tripwires completed success on f1b4147f, which was exactly HEAD at the time, plus a local full suite of 801 passed and 1 xfailed. The mechanism is recorded separately under branch-ci-needs-workflow-dispatch.

<!-- fr:journal kind=finding scope=plan id=peak-not-scrape created=2026-09-11T11:52:20 phase=3 state=fixed -->
### peak-not-scrape · finding [fixed] · The planned memory instrument would have missed almost every peak (phase 3)

Phase 3 as planned sampled container_memory_working_set_bytes from VictoriaMetrics. Measured before running anything: vmagent scrapes at 20s, while the calls being measured last 0.13s (the fatal 50-document one) to 6.7s (30 documents). The scrape would therefore miss the peak of nearly every call and the cap would be derived from whatever the sampler happened to catch between them. Correct instrument: the container cgroup high-water mark. Verified readable inside the ovms container on the live pod — memory.current 2372685824 (2.21 GiB, matching the issue idle figure), memory.peak 2534780928, memory.max 6442450944, and memory.events oom_kill 0 for this instance, which is also an unambiguous per-instance kill signal that does not depend on polling the restart count at the right moment. memory.peak cannot be reset here: /sys/fs/cgroup is mounted read-only, so a write is refused. It is therefore monotonic for the life of a container instance — acceptable because the sweep ascends, so the high-water after size N is the peak of size N, and a kill resets it by starting a new instance. Plan step P3.T1.S2 and P3.T2.S3 amended to read the cgroup rather than query metrics; the metrics query is kept only as a cross-check for the idle baseline.

<!-- fr:journal kind=discovery scope=plan id=mechanism-is-quadratic-in-t created=2026-09-11T12:07:47 phase=3 -->
### mechanism-is-quadratic-in-t · discovery · Memory is super-linear in document length and roughly linear in batch size — T is the dominant lever (phase 3)

Measured live at the 6Gi limit, single calls on a freshly restarted container (see ratchet finding for why that qualifier matters). At 10 documents: T~329 tokens cost 0.285 GiB, T~667 cost 0.947 GiB, T~1329 cost 3.220 GiB — doubling length more than TRIPLES the cost, an exponent near 1.7. That is transformer attention: the scores tensor is batch x heads x T x T, and the model is XLM-RoBERTa-large (24 layers, 16 heads, hidden 1024, max_position_embeddings 8194, read from the served config.json). Batch size enters roughly linearly by comparison. Consequence for the design: max_position_embeddings is NOT a secondary precaution behind max_allowed_chunks, it is the PRIMARY control — a document-count cap constrains the linear term and leaves the quadratic one unbounded. It also answers the worry that a cap fitted to synthetic filler would be too generous for real text: once T is bounded, the worst case per row is bounded regardless of how token-dense the client text is.

<!-- fr:journal kind=discovery scope=plan id=token-density-explains-the-report created=2026-09-11T12:07:49 phase=3 -->
### token-density-explains-the-report · discovery · The issue reproduced at 70 documents, not 50, and the gap is token density — measured, not guessed (phase 3)

A first sweep at 200 words per document had 50 documents SUCCEED (peak 94.9 percent of limit at 60) where the issue reports 50 dying. The difference is tokens per word, measured with the served tokenizer.json against the XLM-R vocabulary: this harness padded filler tokenizes at 1.66 tokens per word, while random dictionary words — what the issue describes sending — tokenize at 3.02. Their documents were therefore about 1.8x denser at the same word count, and since cost is near-quadratic in T that is roughly 3x the length-dependent memory. Their 50-document call lands at T~605, between two measured kills at this limit: (50 docs, T~664) dies and (64 docs, T~511) dies. So the report is reproduced on its own terms rather than contradicted. General lesson for any later measurement here: words are not tokens, and the mechanism is tokens.

<!-- fr:journal kind=finding scope=plan id=peak-ratchets-across-a-sweep created=2026-09-11T12:07:51 phase=3 state=fixed -->
### peak-ratchets-across-a-sweep · finding [fixed] · Memory is not released after a call, so a monotonic peak read across a sweep overstates every size after the first (phase 3)

memory.current after a large call equals memory.peak and STAYS there — idle 2.21 GiB, then 4.90 GiB after a 50-document call, with no return to idle. The allocator holds it for the life of the container. Two consequences. First, this explains the issue restart pattern over a week of light use better than any single request does: the resident floor ratchets up to the high-water of the largest call served, so later headroom is whatever is left. Second, and this corrupted my own first reading: the per-size deltas in an ascending sweep are NOT per-call costs, they are increments of a monotonic high-water mark on a ratcheted container. I initially read them as evidence that each distinct batch SHAPE cost about 800 MiB permanently, and built a retained-compiled-variant hypothesis on it. A thirty-second discriminating experiment killed that: replaying an already-seen size added nothing, and a genuinely NEW size (35) also added nothing, because the 50-document call had already pushed the high-water above it. Every clean number in this phase therefore comes from a single call on a freshly restarted container.

<!-- fr:journal kind=discovery scope=plan id=measured-6gi-iso-surface created=2026-09-11T12:08:16 phase=3 -->
### measured-6gi-iso-surface · discovery · Measured survival surface at the current 6Gi limit (phase 3)

Single calls, fresh container each time where a kill intervened, peak read from /sys/fs/cgroup/memory.peak in the ovms container. SURVIVES: 64 documents at T~332 tokens, peak 3.50 GiB (58 percent of limit); 50 at T~511, peak 4.38 GiB (73 percent); 64 at T~415, peak 4.81 GiB (80 percent). KILLED: 64 at T~511; 50 at T~664; 40 at T~664. Note the last one — at T~664 even FORTY rows is fatal, which is the quadratic term dominating. The client default of up to 50 candidate passages of natural text sits at T~600 and is therefore NOT servable at 6Gi, which is what the operator decision to raise the ceiling was for. Latencies at the surviving points run 1.7 to 2.5 seconds.

<!-- fr:journal kind=finding scope=plan id=do-not-extrapolate-the-cost-model created=2026-09-11T12:08:17 phase=3 state=fixed -->
### do-not-extrapolate-the-cost-model · finding [fixed] · The fitted cost model was wrong in both directions — only the measured pair counts (phase 3)

I fitted cost per row = 0.0285 GiB x (T/329)^1.75 from three points and checked it at an independent one: 40 documents at T~498 cost 1.694 GiB against 2.355 predicted, over-predicting by 28 percent, which is the safe direction. Then the same model predicted about 4.9 GiB for 64 documents at T~511 — comfortably inside a 6 GiB limit — and that configuration KILLED the server. So the model is not merely imprecise, it is unreliable in the direction that matters, because the per-row cost is not separable from a fixed per-call component. Practical rule recorded for phase 5 and for anyone retuning later: measure the (N, T) pair you intend to ship, at the limit you intend to ship it with. Do not interpolate a curve and quote it as a bound.

<!-- fr:journal kind=finding scope=plan id=ten-gi-arm-blocked created=2026-09-11T12:08:19 phase=3 state=open -->
### ten-gi-arm-blocked · finding [open] · BLOCKED: the 10Gi arm needs a live Deployment patch, which the permission layer refused (phase 3)

Phase 3 task 2 raises limits.memory to 10Gi live, with ArgoCD self-heal suspended root-first, re-sweeps, and derives the shipping pair. The kubectl patch of the two Applications was refused by the harness permission classifier, so the step did not run and nothing was changed: both Applications still carry their original automated maps (root prune true selfHeal true; ovms-retrieval prune false selfHeal true), the Deployment is still 6Gi, and ovms-retrieval reports Synced and Healthy. Root reports OutOfSync on longhorn and victoria-metrics, which is pre-existing drift unrelated to this work. Left for the operator to decide: grant the patch, run it themselves, or size the pair against the CURRENT 6Gi limit and defer the raise to the post-merge Test Plan. The last option is not free — fitting under 6Gi means a T low enough that ordinary passages chunk, which changes their relevance scores. Cost of the measurement so far: four deliberate OOM-kills, restart count 9 to 13 across two pod generations, each about ten seconds of refused connections.

<!-- fr:journal kind=finding scope=plan id=iso-surface-was-ratchet-contaminated created=2026-09-11T13:36:51 phase=3 state=fixed -->
### iso-surface-was-ratchet-contaminated · finding [fixed] · CORRECTION: the reported kills were floor-plus-call, not call — and that reverses the conclusion (phase 3)

An earlier entry (measured-6gi-iso-surface) presented kills at 64 documents by T~511, 50 by T~664 and 40 by T~664 as an iso-surface and concluded that at T~664 even forty documents is fatal. That is wrong. Because memory is never released, each of those three calls ran on a container already holding 3.5 to 4.8 GiB from the PREVIOUS call in the same batch, so they died of floor plus call rather than of call. The same ratchet had already fooled me once, making an ascending sweep look like per-shape accumulation. Valid measurements come only from a single call on a freshly restarted container; there are three of them (64 by 332 costing 1.29 GiB, 40 by 498 costing 1.69, 50 by 511 costing 2.17) and they fit cost per row = 0.0202 x (T/332)^1.78. The corrected conclusion is materially different and is the real finding of this phase: the largest batch this endpoint is expected to serve, at T~605, costs 2.93 GiB and therefore totals 5.14 GiB on a fresh server — it FITS inside the current 6 GiB limit. It dies only once the floor has ratcheted beneath it. That is why the reranker works, then does not, then works again after a restart, and it explains restarts accumulating 1 to 9 over a week of light use, which no single request size can. Spec corrected in place, with the correction stated rather than silently rewritten.

<!-- fr:journal kind=decision scope=plan id=shipping-pair-64-640 created=2026-09-11T13:36:53 phase=3 -->
### shipping-pair-64-640 · decision · Shipping max_allowed_chunks 64 and max_position_embeddings 640 (phase 3)

Chosen from the clean anchors with a short extrapolation, not from the blocked 10Gi arm (operator elected to ship the raise through git and verify post-merge). 64 sits above the clients 50-document default with headroom and, because the field caps total CHUNKS as well as documents, a request of long documents is refused rather than allocated. 640 tokens is about 212 words of natural text per chunk, so a typical candidate passage is scored whole while longer ones chunk and count against the 64. Predicted worst case 4.15 GiB of call on top of 2.21 GiB idle = 6.36 GiB, which is 64 percent of a 10Gi limit and 76 percent even if the fit under-predicts by 30 percent. It is 106 percent of the CURRENT 6Gi limit, which is the measured justification for the raise: a guard whose own worst case OOMs is decorative. Test Plan row 10 measures the real surface at the shipped limit and the pair may need retuning, which costs a model rebuild and a reseed — an accepted cost of the decision to keep the guard in the model image.

<!-- fr:journal kind=finding scope=plan id=rev-pin-is-atomic-not-splittable created=2026-09-11T13:56:16 phase=4 state=fixed -->
### rev-pin-is-atomic-not-splittable · finding [fixed] · The rev bump cannot be split from the Deployment pin — two tripwires pull in opposite directions (phase 4)

The plan gives phase 4 the MODELS_REV bump and phase 5 the Deployment pin. The repo's own guards make that split impossible, and I only found out by trying it.

test_models_rev_moves_when_the_dockerfile_changes fails any Dockerfile edit that leaves MODELS_REV where it was. test_model_image_tag_matches_the_rev_ci_publishes fails any workflow rev the Deployment's seed image does not consume. So phase 4 must move the rev, and the moment it does, the Deployment must follow in the same change. There is no arrangement in which a phase that edits the Dockerfile leaves the suite green without also moving the pin. Measured, not reasoned: with the Dockerfile edited and the rev at 2, the manifests suite reported exactly one failure, Deployment pins model rev 1 but build-ovms-retrieval-models.yml publishes 2.

Resolution: phase 4 carries all three values — Dockerfile ARG default, workflow env, and the Deployment's seed image tag plus its MODELS_REV env. Nothing else of phase 5's was touched. P5.T1.S1 asks for a red on two properties; the tag-and-env-equal-each-other half is now already green, and the limits.memory 10Gi half is still red, which is the substantive half. P5.T1.S2 through S4 are untouched.

The cost, stated because it is real and it is what the plan's ordering was buying. The Deployment is strategy Recreate, so merging the pin ahead of the published image means the old pod is deleted and the new one waits in ImagePullBackOff on the seed initContainer for as long as the model build takes (two model downloads plus int8 quantization). Publishing before pinning avoids that window entirely. The orchestrator can recover it by merging phase 4 and phase 5 together, or by letting the build finish before phase 5 syncs. I did not make that call, because it is a delivery decision and not mine.

Worth noting the guard is not wrong. Its docstring already says a Deployment ahead of CI is an ImagePullBackOff and a Deployment behind CI is a model bump that silently never deploys. Both are statements about main's steady state, and it enforces them on every branch — which is what makes these three values one unit of change rather than three.

<!-- fr:journal kind=finding scope=plan id=drift-gate-fixture-pinned-rev-one created=2026-09-11T13:56:33 phase=4 state=fixed -->
### drift-gate-fixture-pinned-rev-one · finding [fixed] · A test used the live Dockerfile as a fixture and hard-coded the one value designed to move (phase 4)

test_rev_drift_rule_ignores_comment_and_rev_only_edits builds its synthetic mutations by string-replacing into the real Dockerfile. One of them was base.replace('ARG MODELS_REV=1', 'ARG MODELS_REV=2'), followed by assert rev_only != base.

The moment the rev actually moved to 2, that replacement matched nothing, rev_only came back identical to base, and the test failed — on precisely the change it exists to declare legitimate. It is a self-disarming fixture: correct for exactly one value of a field whose whole purpose is to change, and it fires on the first successful use of the gate around it.

Fixed by reading the current rev out of the Dockerfile and mutating to rev plus one, so the mutation is always a real edit. The comment beside it now says why the value is read rather than named.

Two things this is worth remembering for. First, it was caught only because phase 4 is the first change to move this rev since the image was introduced, so the defect had been latent since the file was written and no run had ever exercised it. Second, the sibling assertion two lines above it passes literal revs to rev_drift_violation as synthetic arguments — that is fine, because those are inputs to a pure function, not string-matches against a live file. The distinction is between a value used as data and a value used as a needle.

<!-- fr:journal kind=discovery scope=plan id=four-graphs-is-two-graphs created=2026-09-11T13:56:49 phase=4 -->
### four-graphs-is-two-graphs · discovery · The plan says run the injector over all four emitted graphs; the injector's contract says two (phase 4)

P4.T1.S3 reads run it over all four emitted graphs after the export_model.py invocations. Four graphs are emitted — embeddings and rerank, times GPU and CPU — but only two are rerank graphs, and inject_rerank_guard.py raises GuardInjectionError on any file with no RerankCalculatorOVOptions block. That refusal is deliberate and load-bearing: it is what makes a silent no-op impossible. Running the injector over the two embeddings graphs would therefore fail the build every time, by design.

So the correct reading of all four is one rerank graph per exported repository, which is what the spec itself says: add two fields in both exported repositories, /out/gpu and /out/cpu. The Dockerfile loops over the two repository roots and rewrites RERANK_MODEL_NAME/graph.pbtxt under each. The path is derived from the existing ARG rather than re-spelling the model name, so a model rename cannot leave the guard pointing at a file that no longer exists.

Recording it because the phrase all four graphs reads like an instruction to widen the loop, and widening it turns a working build into a build that cannot succeed.

<!-- fr:journal kind=finding scope=plan id=p4-build-job-unobserved created=2026-09-11T14:02:48 phase=4 state=open -->
### p4-build-job-unobserved · finding [open] · P4.T1.S4 is half done: the suite is green, the real build has not been run (phase 4)

uv run --frozen pytest scripts/tests -q gives 848 passed, 1 xfailed on the branch as committed (840 passed, 1 xfailed before this phase; eight new tests). That is the local half.

The other half — confirm the Build OVMS Retrieval Models job is green — was deliberately not performed, and cannot be from here. The phase executor never pushes and never opens a PR. That job runs on pull_request and on workflow_dispatch, and workflow_dispatch needs a ref that exists on the remote, so an unpushed branch has neither route. Same shape as the phase-1 carry-over, and it should be closed the same way: push, then either read the PR's job or run gh workflow run build-ovms-retrieval-models.yml --ref fix/ovms-rerank-oom-guard.

This one matters more than phase 1's did, and it should block phase 5 rather than trail it. Everything asserted in this phase is SHAPE: that the Dockerfile copies the injector, loops over both repositories, passes 64 and 640, and greps the result. No test here has ever seen export_model.py emit a graph. Two specific things only the real build can answer:

- whether a freshly exported graph.pbtxt from v2026.2.1 still has the shape the injector understands. The injector is exercised against a capture taken off the running pod, which came from the SAME pinned exporter ref, so this is very likely fine — but likely is not observed, and the injector's whole design is to refuse rather than guess, which means a template change fails the build rather than shipping quietly.
- whether the export stage still resolves at all. The stage fetches export_model.py and requirements.txt from raw.githubusercontent.com at build time and pip-installs from PyPI, so it can break for reasons entirely unrelated to this change.

The good news is that the pull_request trigger makes this cheap: this workflow is the only build-*.yml in the repo that runs on PRs, the path filter covers apps/ovms-retrieval/docker/**, and a PR build does not publish. So opening the PR proves the export toolchain and the injection against real exported graphs without pushing anything to the registry. Confirm it before phase 5, as the step says.

<!-- fr:journal kind=discovery scope=plan id=nrb-note-p4t1 created=2026-09-11T14:03:04 phase=4 -->
### nrb-note-p4t1 · discovery · The refactor step had real work: the mechanism sentence was wrong in the safe direction (phase 4)

P4.T1.S5 asked for the new Dockerfile block to be re-read as prose. It needed it.

The green-phase comment said a single long passage costs as much as a whole batch of short ones. That is a fair description of a LINEAR cost in tokens and it is not what phase 3 measured: attention scores are T x T, the fitted exponent on document length is about 1.78, and doubling the length more than tripled the memory. So a long passage costs MORE than a batch of short ones, and the sentence understated the very fact that makes max_position_embeddings the primary control rather than a secondary precaution behind the document cap. Written as it was, a future reader could reasonably conclude that capping documents alone is sufficient — the exact wrong conclusion the spec spends a section refusing.

Also added: a one-line meaning beside each ARG. Neither is guessable from the identifier — max_allowed_chunks is checked before a single token is allocated, max_position_embeddings is what bounds the padded tensor width — and a number in a build file with no semantics is a number the next person cannot safely change.

Recording this because no-refactor-because was the expected shape here and would have been wrong.

<!-- fr:journal kind=finding scope=plan id=publish-before-merge created=2026-09-11T14:05:42 phase=4 state=fixed -->
### publish-before-merge · finding [fixed] · Merging before the image is published would take the retrieval tier down for a whole model build (phase 4)

Surfaced by the phase-4 executor as a merge-ordering concern and verified here. On merge, ArgoCD polls about every three minutes and syncs the Deployment now pinned to ovms-retrieval-models:2, while the push-to-main build is still downloading and int8-quantizing two models. The Deployment is strategy Recreate, so the running pod is deleted and its replacement sits in ImagePullBackOff on the seed initContainer until the image exists — an outage as long as the build. The fix is cheap and was hiding in the workflow: the build step publishes on anything that is not a pull_request (push: github.event_name != pull_request), so workflow_dispatch on the BRANCH publishes rev 2 ahead of the merge. Bytes are identical to what push-to-main would build from the same ref, any later Dockerfile change moves the rev again under an existing guard, and the package is already public so the first-push-is-private trap does not apply. Recorded as a Before merging section in the spec so it is a step rather than folklore. Note this also removes the executor concern about phase 4 merging alone: this work delivers as ONE pull request, so the pin and the ceiling land together regardless.

<!-- fr:journal kind=review scope=plan id=review-phase-4 created=2026-09-11T14:06:05 phase=4 -->
### review-phase-4 · review · Phase 4 review — sound, and two executor judgement calls were right (phase 4)

Reviewed the four phase-4 commits. The Dockerfile block is minimal and its prose explains the mechanism rather than restating the commands; the read-back verification uses the real grep against the injector emitted spelling, and the executor added an unasked-for test binding those two independent specs together and mutation-proved it. Two judgement calls both correct. First, touching deployment.yaml — nominally phase 5 — was forced by the repo tripwires, which make the Dockerfile rev, the workflow rev and the Deployment pin one atomic change; the executor moved only the pin and left the 10Gi ceiling red for phase 5. Second, declining to widen the injection loop to all four emitted graphs: only two are rerank graphs and the injector hard-fails on anything else by design, so the plan text would have made the build unable to succeed. Also caught a pre-existing test that disarmed itself the first time it was needed — it hard-coded the rev-1 string it mutated, so it would have failed on exactly the change it exists to bless. One finding added by review: publish-before-merge.

<!-- fr:journal kind=discovery scope=plan id=p5-rev-clauses-already-green created=2026-09-11T14:21:06 phase=5 -->
### p5-rev-clauses-already-green · discovery · Two of S1's clauses were already green, and the third was changed on purpose (phase 5)

S1 asks for a red on two properties. Recording exactly which half was red, so the TDD record is not read as stronger than it is.

Already satisfied by phase 4, which had to carry the rev pin for the reasons in rev-pin-is-atomic-not-splittable: the seed image tag is 2, the seed container's MODELS_REV env is 2, and both equal the rev the build workflow publishes. I asserted those rather than re-changing anything, and they passed on the first run. The genuinely red half was limits.memory, and S2's provenance clause.

One deliberate change of shape. S1 says both must be 2. I did not write == 2. This file already shipped an assertion that hard-coded the rev it expected and therefore failed on the first legitimate bump (drift-gate-fixture-pinned-rev-one, found in phase 4, on this very plan). An equality against 2 is the same defect wearing different clothes: correct for exactly one value of a field whose entire purpose is to move, and it fires on the next model bump, which is a change it exists to bless.

What went in instead, as test_model_rev_is_the_same_value_in_all_three_places:
- the three-way equality, stated once and directly. Each pair was already guarded separately, so the triangle held by transitivity, but only while both of those tests survive; deleting either one silently unpinned the other side.
- int(rev) >= 2 as a floor. The property that actually matters is that the rev never goes BACKWARDS, because a lower rev pins an image whose graph carries no bound while the marker on the volume claims it does.

If the orchestrator wants the literal equality anyway it is a one-line change, but it should be made knowing it self-disarms.

<!-- fr:journal kind=finding scope=plan id=cpu-arm-envelope-must-track created=2026-09-11T14:21:22 phase=5 state=fixed -->
### cpu-arm-envelope-must-track · finding [fixed] · The ceiling exists in TWO files, and only a tripwire said so (phase 5)

Raising limits.memory on the Deployment turned the manifests suite red on a test I had not touched: test_cpu_control_arm_seeds_the_cpu_repository_on_the_same_node asserts that apps/ovms-retrieval/cpu-arm-pod.yaml carries the same CPU/memory envelope as the serving container.

It is right, and the reason is not housekeeping. The CPU arm exists to isolate the DEVICE. Two arms with different ceilings do not compare a GPU against a CPU; a batch the GPU arm serves and the CPU arm OOM-kills has measured the limit. The failure would have been invisible in the only place it mattered: the comparison run would simply have reported the CPU arm dying at a size the GPU arm survived, which is exactly the shape of the result that arm is there to produce.

Nothing in the plan, the spec, or phase 5's brief names cpu-arm-pod.yaml. Neither did I, before the test did. Raised it to 10Gi with a comment that says the envelope TRACKS the Deployment's and points at the Deployment for the provenance rather than duplicating it, so the two copies cannot drift into two different justifications.

Worth carrying: the phase-5 brief was written as if the ceiling were one number in one file. It is two, and the second one is not in any manifests directory, so a grep of apps/ovms-retrieval/manifests finds only half of it.

<!-- fr:journal kind=discovery scope=plan id=p5-provenance-scope-and-refactor created=2026-09-11T14:21:42 phase=5 -->
### p5-provenance-scope-and-refactor · discovery · The provenance test is only worth its scope, and the refactor had real work (phase 5)

Two notes on how S2 was built, because a provenance test is easy to write in a form that proves nothing.

SCOPE. The assertion reads the comments attached to the ovms container's resources block only: the contiguous comment run directly above it, plus every comment inside it, extracted from the raw file rather than from parsed YAML (PyYAML discards comments, so a YAML-level check cannot see the thing being asserted at all). Scanning the whole Deployment would let a future edit satisfy the test with a sentence three hundred lines away, which is provenance nobody reading limits memory 10Gi will ever find.

The clauses are content, not keywords: the mechanism (quadratic, or the T x T tensor), the measured idle floor 2.21 GiB, the post-call floor 4.90 GiB, a word for the ratchet, the predicted worst case 6.36 GiB, both graph bounds NAMED with their values (max_allowed_chunks near 64, max_position_embeddings near 640 — a bare 64 and 640 reads as arbitrary and would also match 64% in the same paragraph), the 6Gi to 10Gi move, and Test Plan row 10. One correction during writing: the two-clause patterns needed re.S, because the prose is multi-line and .* stops at a newline — without it those clauses only pass when both halves happen to land on one line, which is a test that passes for the wrong reason.

REFACTOR, not no-refactor-because. Two real defects in the green-pass comment. First, the spec path had been wrapped across two comment lines to respect the column limit, which makes the one thing in that block a reader will act on — opening the Test Plan row that closes the unverified ceiling — impossible to paste. Second, the original note sized the limit against the node (6 of 64 GB) and my rewrite had dropped that for a bare 10Gi ceiling; on an etcd member, what fraction of node RAM the ceiling can take is precisely the number a reader needs, so it reads 10 of 64 GB again.

The discretion guard did not fire. The comment never refers to the requester — the largest batch this endpoint is expected to serve, not whose batch it is — so no rephrasing was needed and no exemption was added.

<!-- fr:journal kind=finding scope=plan id=ten-gi-ships-unmeasured created=2026-09-11T14:22:01 phase=5 state=open -->
### ten-gi-ships-unmeasured · finding [open] · OPEN: 10Gi ships without ever having been measured at 10Gi (phase 5)

Carried forward from ten-gi-arm-blocked, now shipped rather than blocked, and it should stay open until row 10 closes it.

Every figure behind this ceiling was taken at 6Gi. The plan's own step 4 said the 6Gi arm can only report hit the ceiling, never the true requirement, and the arm that would have reported the true requirement never ran: the live Deployment patch was refused by the permission layer in phase 3. The operator's decision was to ship the raise through git and verify afterwards, which is the right call — leaving the ceiling below the guard's own worst case would make the guard decorative — but it means the number in the manifest is a short extrapolation, not an observation.

Specifically unproven:
- 6.36 GiB is PREDICTED from a fit over three measured points, and the spec records that a fit over those points over-predicted an independent check by 28 percent. The direction of that error is not guaranteed.
- 64 percent of 10Gi is arithmetic on that prediction, so it inherits the same uncertainty.
- nothing has ever observed this pod holding more than the 4.90 GiB the 50-document call left resident at 6Gi.

The manifest comment says so in its own words (WHAT IS NOT PROVEN) rather than presenting 10Gi as measured, because an unverified number that looks verified is worse than no number. Test Plan row 10 closes it: re-run the batch sweep against the deployed pod and require every peak at or under about 70 percent of the limit. Note the sweep must run on a freshly restarted container for the same ratchet reason phase 3 found, or the reading overstates every size after the first.

If row 10 comes back above 70 percent the response is to tighten max_position_embeddings, not to raise the ceiling again — the whole point of this shape is that the bound moves and the backstop does not.
