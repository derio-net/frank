# Journal: 2026-08-02--infer--igpu-embedding-rerank

<!-- fr:journal kind=discovery scope=plan id=0e837d15875a created=2026-08-02T13:48:21 -->
### 0e837d15875a · discovery · export_model.py subcommand + arg shapes verified live against v2026.2.1

Fetched openvinotoolkit/model_server's demos/common/export_models/export_model.py at tag v2026.2.1 (commit 1122f03) to confirm the CLI contract before writing the Dockerfile: embeddings_ov and rerank_ov are real add_parser subcommands sharing add_common_arguments (--source_model, --model_name, --weight-format default int8, --config_file_path, --target_device default CPU, --model_repository_path). model_name defaults to source_model verbatim (slashes and all) if not given, so the Dockerfile passes explicit --model_name bge-m3 / bge-reranker-v2-m3 to keep servable directory names clean and match the readiness-probe path the spec already names (/v2/models/bge-reranker-v2-m3/ready). Export/quantization runs on CPU regardless of --target_device (optimum-cli + nncf, no OV runtime device needed) — target_device only shapes the emitted graph.pbtxt — so the CI runner (ubuntu-latest, no GPU) can legitimately produce the GPU-targeted repository too. Confirmed via demos/common/export_models/requirements.txt at the same tag: optimum-intel has no usable PyPI release and is pinned via git+https at commit d4dd21a3aa89c0671d85b704847ac06a378e761c, alongside openvino==2026.2.0rc2 and openvino-tokenizers==2026.2.0.0rc2 — the Dockerfile mirrors these exact pins rather than fetching that requirements.txt at build time, so a change to that file upstream cannot silently reshape this image.

<!-- fr:journal kind=finding scope=plan id=0a6fe9cc75e0 created=2026-08-02T13:49:33 state=open -->
### 0a6fe9cc75e0 · finding [open] · Phase 1 completion warns on not-implemented acceptance rows (expected)

fr plan edit --complete-phase 1 succeeded but warned that acceptance rows infer-igpu-rerank-endpoint / infer-igpu-embeddings-endpoint are still not-implemented. This is expected, not a defect: those rows are shared across phases 1, 2 and 5 (01.yaml/02.yaml/05.yaml all list them), and phase 1 only builds the model image — no endpoint exists to measure until phase 2 deploys the Deployment/Service and phase 5 runs the benchmark harness and records evidence via fr acceptance set-status. Leaving open so a later phase's executor (or the orchestrator) closes it once phase 5 actually flips the rows, rather than silently assuming phase 1 should have.

<!-- fr:journal kind=decision scope=plan id=d6b32717d4cc created=2026-08-02T16:05:05 -->
### d6b32717d4cc · decision · Seed script lives inline in the pod spec — no configMapGenerator, so prune stays false

Phase 2 step P2.T2.S3 anticipated a Kustomize configMapGenerator and the prune: true / per-resource Prune=false pairing it forces. There is nothing to generate: the model repository arrives as an image, and the only configuration this app has beyond it is the ~20-line seed script, which is inlined in the initContainer's args. That already provides the exact property a configMapGenerator exists to provide on Frank (hash-suffixed name -> pod spec changes -> ArgoCD rolls the pod): an inline script IS the pod spec, so editing it rolls the pod by construction. Keeping the generator out means the Application stays prune: false, and the 20Gi Longhorn model cache is therefore never one mis-sync away from deletion — strictly safer than prune: true plus an opt-out annotation that a future edit could drop. The constraint is not simply skipped: test_prune_can_never_reach_the_model_cache is written CONDITIONALLY — if any generator is ever added to the kustomization, the test immediately starts requiring prune: true AND a Prune=false sync-option on the PVC. So the pairing cannot silently come apart later.

<!-- fr:journal kind=discovery scope=plan id=283d8a95f7c8 created=2026-08-02T16:05:19 -->
### 283d8a95f7c8 · discovery · Both servables are gated before Ready, using only httpGet — startupProbe covers the second model

The spec names one readiness path (/v2/models/<rerank>/ready) because the gate proved /v2/health/ready returns 200 while a servable is in LOADING_PRECONDITION_FAILED. But a single httpGet probe can only assert ONE model, and this pod serves two: a pod could be Ready with the embeddings servable dead, which is the same silent-green failure one level down. An exec probe hitting both would need a shell/curl in the stock OVMS image, which is an unverified assumption. Resolution using only primitives that are guaranteed to exist: kubelet does not run readiness or liveness until startupProbe succeeds, so putting the embeddings model on startupProbe and the reranker on readinessProbe means BOTH must load before the pod ever takes traffic. startupProbe is 60x10s because first boot compiles the IR for the iGPU (minutes, not seconds) and a generous threshold keeps a slow cold start from being read as a crash. livenessProbe deliberately stays on the SERVER-level /v2/health/live — restarting a healthy server whose model failed to load would crash-loop instead of staying up and reporting the failure via /v1/config.

<!-- fr:journal kind=finding scope=plan id=6413c24b652f created=2026-08-02T16:05:34 state=fixed -->
### 6413c24b652f · finding [fixed] · Seed used 'cp -a', which would have aborted the seed as uid 5000

Caught while re-reading the implemented script, not by a test. 'cp -a' implies '-p', which attempts to preserve the source files' root ownership. The seed container runs as uid 5000 (pod securityContext), so that chown is refused; busybox cp reports the failure and returns non-zero, and the script runs under 'sh -eu' — so a seed that had in fact copied every byte would abort right before writing the .seed-rev marker. The pod would then fail its init container on first boot, and on retry re-copy everything and fail again: a permanent boot loop whose message ('cannot preserve ownership') points at permissions rather than at the flag. Changed to 'cp -R'. The model repository is plain files and directories (IR xml/bin, tokenizer xml, graph.pbtxt, config.json) with no symlinks or modes worth preserving, and ownership comes from fsGroup: 5000 anyway. Worth noting the shape: this is the second uid-5000-versus-root-owned-bytes trap in the same container after the fsGroup one the spec review caught, and neither is visible from the pod's status — both surface only in initContainer logs.

<!-- fr:journal kind=discovery scope=plan id=1e4a7fb3fb3e created=2026-08-02T16:05:50 -->
### 1e4a7fb3fb3e · discovery · Exposure tripwire is a repo-wide reference scan, and it was mutation-verified

The 'in-cluster only' decision needed a test that survives contact with a future contributor. Asserting 'Service type is ClusterIP' is not enough: the three realistic ways this endpoint reaches the LAN are a Traefik IngressRoute, a homepage tile, and a LiteLLM alias, and NONE of them touches this app's own manifests. So test_nothing_outside_the_app_routes_to_it scans every yaml/yml/json under apps/ and clusters/ and fails if any file outside the app dir, its Application CR, its build workflow and the test itself so much as NAMES ovms-retrieval. All three vectors have to name it, so one scan catches all three, and the failure is loud enough that exposing an unauthenticated inference endpoint becomes a deliberate reviewed decision rather than a drive-by edit. Two implementation notes for anyone extending this: (1) the lbipam check strips comment lines first — the first version failed on the service.yaml comment EXPLAINING why there is no LoadBalancer, i.e. the detector fired on its own documentation; (2) the whole file was mutation-verified rather than trusted green — a capacity request, a /v2/health/ready readiness path, a seed-if-absent guard, a removed fsGroup and a planted reference file were each injected and each produced exactly one failing test, then reverted.

<!-- fr:journal kind=finding scope=plan id=0d6affc80410 created=2026-08-02T16:06:07 state=open -->
### 0d6affc80410 · finding [open] · Two OVMS runtime details are asserted for shape but not verified live: --port 9000 and readOnly /models

Both are low-risk and both are phase-5 discoveries if wrong, so recording them rather than guessing louder. (1) The serving container passes '--config_path /models/config.json --port 9000 --rest_port 8000', matching upstream's canonical docker invocation. Only --rest_port 8000 is load-bearing (the Service and every probe use it); --port is included because OVMS's documented examples always set it, and its gRPC listener is deliberately absent from the Service. Flags known to exist were preferred over hardening flags that were not verified — an earlier draft bound gRPC to 127.0.0.1 via --grpc_bind_address, which was dropped because an invalid flag fails the pod at boot while the hardening gain is nil (with no Service, gRPC is already only reachable pod-IP-direct in-cluster, the same trust boundary as the ClusterIP). (2) The ovms container mounts /models readOnly: true, which protects the seeded repository from the server and is correct if OVMS only reads the IR. It would break if OVMS wrote a cache into the repository directory; no CACHE_DIR is configured, so it should not. If the pod fails at load with a write error under /models, drop readOnly on that mount — it is not a design commitment.

<!-- fr:journal kind=discovery scope=plan id=0974fdeb2b1b created=2026-08-02T16:17:22 phase=3 -->
### 0974fdeb2b1b · discovery · Bare python3 in this container lacks the http stdlib package — use uv run python3 (phase 3)

The isolation container ships a system `python3` (3.14.4) whose stdlib is missing `http/` entirely — `python3 -c "import http.client"` fails with `ModuleNotFoundError: No module named 'http'`, so any script that does `import urllib.request` (which imports `http.client` transitively) fails under the bare interpreter, including a plain `--help` invocation. `uv run python3 ...` uses uvs managed CPython (3.13.14 in `.venv`), which has a complete stdlib and works fine — confirmed both `uv run --frozen pytest scripts/tests/test_ovms_retrieval_bench.py -q` (31 passed) and `uv run python3 scripts/ovms-retrieval-bench.py --help` (exit 0) work. Phase-5s live run should invoke the script the same way (`uv run python3 scripts/ovms-retrieval-bench.py --arm gpu`), not bare `python3`, or it will hit this at the very first HTTP call rather than at --help.

<!-- fr:journal kind=decision scope=plan id=c28b8cf71555 created=2026-08-02T16:17:36 phase=3 -->
### c28b8cf71555 · decision · Harness design: linear-interpolation percentiles, magnitude+separation degeneracy gate, --base-url override for the CPU arm (phase 3)

Three implementation choices worth recording for phase 5. (1) percentile() uses the standard linear-interpolation method (numpys default "linear": for N sorted values, index k=(N-1)*p/100, interpolate between floor/ceil) rather than nearest-rank, so p95 of 1..10 is 9.55 not 9 or 10 — matches what most plotting/analysis tooling would report if the raw samples were fed elsewhere later. (2) scores_are_degenerate() requires BOTH tiny magnitude (max score < 1e-6) AND poor separation (max-min < 1e-9) before flagging — either alone is not evidence (a legitimately tiny-but-separated score set, e.g. [1e-3, 5e-5, 1e-7], must not trip it). Deliberately scoped to the exact measured signature from the spec (a wrong-model-class reranker), not a general "scores look weird" heuristic. (3) --base-url defaults to the phase-2 Service (ovms-retrieval.retrieval.svc.cluster.local:8000) but is overridable, because the CPU control arm has no separate Deployment in this repo (the model image bakes BOTH a GPU and a CPU export at /models-src/gpu and /models-src/cpu — see the Dockerfile — but only the GPU one is currently seeded by the phase-2 Deployment). Running the CPU arm therefore needs an operator step in phase 5 (e.g. a temporary CPU-target Deployment/port-forward) that this phase does not build; --arm cpu only labels the JSON output correctly once that endpoint exists, it does not create it.

<!-- fr:journal kind=finding scope=plan id=a47cd48a35e0 created=2026-08-02T16:17:48 phase=3 state=open -->
### a47cd48a35e0 · finding [open] · Phase 3 completion warns on not-implemented acceptance row infer-igpu-rerank-latency-measured (expected) (phase 3)

fr plan edit --complete-phase 3 succeeded but warned that acceptance row infer-igpu-rerank-latency-measured is still not-implemented. Expected, same shape as finding 0a6fe9cc75e0 from phase 1: the row needs a MEASURED number from a live cluster run, which only phase 5 (manual, post-merge) can produce. Phase 3 delivers the harness that will produce it (scripts/ovms-retrieval-bench.py, 31 offline unit tests green), not the measurement itself. Leaving open for phase 5s executor to close via fr acceptance set-status once --arm gpu and --arm cpu have actually been run.

<!-- fr:journal kind=discovery scope=plan id=d9b2517d5421 created=2026-08-02T16:30:27 phase=4 -->
### d9b2517d5421 · discovery · phase05 README drift fixed, worked ResourceClaim example added (phase 4)

Corrected patches/phase05-mini-config/README.md step 4 (was: Intel GPU Device Plugin exposing gpu.intel.com/i915 as a schedulable resource, pointing at the now-nonexistent apps/intel-gpu-plugin/). It now describes the DRA resource driver at apps/intel-gpu-driver/ and a new 'Claiming the iGPU' section gives the real ResourceClaimTemplate + Deployment excerpt sourced verbatim from apps/ovms-retrieval/manifests/ (phase 2), since the correction alone would still leave a reader without the replacement idiom. New topic file docs/runbooks/frank-gotchas/igpu-dra.md documents all 7 verified-live gotchas (capacity.memory=0, world-readable render node + CDI negative control, ovms --pull unservable weights, missing optimum-intel, English-only OpenVINO/ org models, /v2/health/ready server-vs-model-level trap), indexed in the directory README and one-lined into agents/rules/frank-gotchas.md under a new 'Intel iGPU / DRA' section.

<!-- fr:journal kind=finding scope=plan id=653a71d281e1 created=2026-08-02T16:30:40 phase=4 state=fixed -->
### 653a71d281e1 · finding [fixed] · Acceptance row gpu-igpu-claim-documented flipped skipped (unit-guarded, no fr acceptance set-status subcommand exists) (phase 4)

fr plan edit --complete-phase 4 first warned that acceptance row gpu-igpu-claim-documented was still not-implemented. There is no 'fr acceptance set-status' command (only add/init/backfill/check/report/status/summary/digest), so the matrix.yaml row was hand-edited to status: skipped with levels.unit pointing at the new scripts/tests/test_igpu_dra_docs.py and notes citing the concrete fix — matching the repo's existing convention for local-guard-only (not CI-run) evidence, since no row anywhere in this matrix currently uses status: ci. Regenerated the report set via fr acceptance report --deterministic. fr acceptance check still exits 1, but the 13 ERROR staleness lines and their count are identical before/after this change (confirmed via git stash + diff) — pre-existing and unrelated to this phase. complete-phase 4 then produced no warning.

<!-- fr:journal kind=finding scope=plan id=f-acceptance-status-ci created=2026-08-02T16:33:46 phase=4 state=fixed -->
### f-acceptance-status-ci · finding [fixed] · gpu-igpu-claim-documented was labelled 'skipped' but is CI-enforced (phase 4)

Phase 4 set the row to status 'skipped' reasoning that no row in the matrix uses 'ci'. That convention is an artifact of no row previously having had automated coverage, not a deliberate choice: every other 'skipped' row carries a 'Live manual proof <date>' note, i.e. the value means 'verified by hand'. This row is guarded by scripts/tests/test_igpu_dra_docs.py, and .github/workflows/repo-tripwires.yml runs 'pytest scripts/tests/ -q' on CI — so the guarantee is automated and 'skipped' understates it. Corrected to status: ci and regenerated the report set. First row in this matrix to use it.

<!-- fr:journal kind=finding scope=plan id=f-cpu-arm-endpoint created=2026-08-02T16:33:47 phase=5 state=fixed -->
### f-cpu-arm-endpoint · finding [fixed] · Phase 5's CPU control arm had no endpoint to measure (phase 5)

P5.T2.S2 said 'run the CPU control arm' but the Deployment seeds only /models-src/gpu, so --arm cpu had nothing to hit — the control arm that justifies the whole iGPU claim would have been silently unrunnable at measurement time. Surfaced by phase 3. Fixed in the step text: a THROWAWAY pod on the same node from the same stock image, seeded from /models-src/cpu, with NO ResourceClaim (so the CPU arm cannot hold the iGPU while being measured), deleted afterwards with a residue check. Deliberately not a second permanent Deployment — that would contradict the operator's 1-replica control-plane footprint decision.

<!-- fr:journal kind=finding scope=plan id=f-bench-invocation created=2026-08-02T16:33:49 phase=5 state=fixed -->
### f-bench-invocation · finding [fixed] · Phase 5 measurement step would have failed on bare python3 (phase 5)

Phase 3 found that bare python3 in the isolation container lacks the stdlib 'http' package, so urllib.request fails to import and even --help dies. It was journaled but not carried into P5.T2.S1's step text, where the live run actually happens. Added the 'uv run python3' invocation to the step.

<!-- fr:journal kind=finding scope=plan id=f-c1-arm-label created=2026-08-02T17:07:33 phase=3 state=fixed -->
### f-c1-arm-label · finding [fixed] · `--arm` was an unfalsifiable label — the record carried nothing that could contradict it (phase 3)

`--arm gpu|cpu` was free text copied into the JSON, and the payload recorded no `base_url`, no timestamp and no server state. The docstring claimed a recorded measurement "can never be ambiguous about which device produced it"; that was false. The designed phase-5 workflow runs one arm against the default URL and the other against a separately stood-up pod, so forgetting either flag yields a well-formed, authoritative-looking record attributing one device's latency to the other, with nothing downstream able to detect it.

Fixed in `scripts/ovms-retrieval-bench.py`: the payload now records `base_url`, a UTC ISO-8601 `timestamp` and a `server_config` snapshot of `GET {base_url}/v1/config` (per-servable name/version/state via `summarize_servables`, plus the raw response verbatim), all as keyword-only parameters with no defaults so a record cannot be assembled without them. `extract_reported_device` searches the config for a device field; `device_cross_check` compares it to `--arm` and `main()` aborts with exit 4 and a stderr message BEFORE any timing runs if they disagree — so a contradicted arm produces no file at all.

Honesty caveat, now stated in the docstring instead of a guarantee: **OVMS's `/v1/config` reports servable state, not target device**, so on this server the cross-check records `not-reported` and the device claim still rests on which model repository was seeded (`target_device` is baked into each servable's `graph.pbtxt` at export). An unreachable config endpoint records `available: false` + `arm_cross_check: unavailable` and warns on stderr rather than silently producing a clean-looking record. A device string the harness cannot read (`AUTO`) is `not-reported`, never `confirmed`.

<!-- fr:journal kind=finding scope=plan id=f-i6-batch-warmup created=2026-08-02T17:07:59 phase=3 state=fixed -->
### f-i6-batch-warmup · finding [fixed] · Batch-32 was never warmed, so a shape recompile landed in the quoted worst case (phase 3)

`_run_embeddings_benchmark` warmed only the single-input shape, then timed N single calls and immediately N batch-32 calls. Changing the batch dimension makes the OpenVINO GPU plugin recompile for the new shape — seconds on a cold iGPU — and that cold call went straight into `embeddings.batch_latency_ms.max`, the exact figure a reader quotes as worst case. The rerank path already warmed correctly.

Fixed: each embedding SHAPE is warmed at its own shape before its timed loop, governed by a new `--embedding-warmup` (default 3, matching the rerank warm-up). Test `test_batch_shape_is_warmed_before_the_timed_batch_loop` monkeypatches `_post_json` with a recorder and asserts the batch-shaped call count is iterations + warm-up while the summary still reports n == iterations, and that the warm-up calls precede the timed window rather than being interleaved.

<!-- fr:journal kind=finding scope=plan id=f-i7-embedding-iterations created=2026-08-02T17:08:09 phase=3 state=fixed -->
### f-i7-embedding-iterations · finding [fixed] · Embedding sample size was silently driven by `--rerank-iterations` (phase 3)

There was no `--embedding-iterations`: both embedding loops used `args.rerank_iterations`, so `--rerank-iterations 5` shrank the embedding samples too while the payload reported `rerank.iterations` as the only top-level count. A reader had no way to know how many embedding samples backed the distribution.

Fixed: added `--embedding-iterations` (default `RERANK_ITERATIONS` = 30, so existing invocations are unchanged) and recorded `embeddings.iterations` in the payload alongside the per-summary `n`.

<!-- fr:journal kind=finding scope=plan id=f-i8-degeneracy-gate created=2026-08-02T17:08:26 phase=3 state=fixed -->
### f-i8-degeneracy-gate · finding [fixed] · Degeneracy heuristic missed the range it named; fixed, but the prescribed formula was arithmetically self-defeating (phase 3)

The check ANDed a magnitude gate (`max < 1e-6`) with an ABSOLUTE separation gate (`max - min < 1e-9`), so only score sets whose entire spread was under 1e-9 tripped it. Scores squarely inside the ~1e-9..1e-12 range the docstring named as the measured failure signature were NOT flagged. This is the check that detects a reranker served as the wrong model class — the precise failure the whole spike exists to avoid repeating — so a silent miss is the worst available outcome.

**Partial refutation of the prescribed fix.** The review asked for `(hi - lo) / hi < 0.01` ANDed with `hi < 1e-6`, AND for the two named cases to become regression tests. Those two requirements are mutually exclusive: for `[5e-9 … 1e-12]` the relative spread is `(5e-9 - 1e-12)/5e-9` = 0.9998, and for `[3e-7 … 2e-8]` it is 0.933 — both far above 0.01, so under the prescribed AND neither named case would be flagged, exactly as before. Any rule that flags them must treat the magnitude gate as sufficient on its own.

Implemented instead as an OR of two independent, individually defensible signatures:
  (a) `max < 1e-6` — the whole score set collapsed into the near-zero floor;
  (b) `(hi - lo) / hi < 0.01` at ANY magnitude — the model returns effectively the same score for every candidate, so it is not ranking. This is the relative, scale-free separation gate the review asked for, kept as its own signature where it is meaningful.

(a) is only safe because of a second change: the rotating query now NAMES a topic that is present in the candidate set, so a healthy cross-encoder must score that candidate highly. Without that, a magnitude-only rule would false-positive whenever the (generic, unrelated) filler happened to be genuinely irrelevant to the query — a real risk with the previous fixed 'tips for a new hobby' query. Kept: `[1e-3, 5e-5, 1e-7]` is not flagged, and a positive-max guard still scopes the check away from all-zero/all-negative output. Boundary tests at 1e-7, 1e-8 and at the exclusive 1e-6 ceiling.

<!-- fr:journal kind=finding scope=plan id=f-m6-throughput created=2026-08-02T17:08:37 phase=3 state=fixed -->
### f-m6-throughput · finding [fixed] · Spec promised embedding throughput; harness reported only latency (phase 3)

The spec's deliverable list says 'Embedding throughput — single and batch-32', but the payload carried only latency distributions. Fixed by emitting `embeddings.throughput_items_per_s` with `single`, `batch` and an explicit `basis: derived from p50 latency` — a derived figure, labelled as derived, so nobody re-derives it wrongly from a p95. Pure helper `throughput_items_per_s(latency_ms, items)` rejects a non-positive latency rather than dividing by zero.

<!-- fr:journal kind=finding scope=plan id=f-m8-timing-scope created=2026-08-02T17:08:49 phase=3 state=fixed -->
### f-m8-timing-scope · finding [fixed] · The measured time was never stated to include client-side work (phase 3)

`_time_call` wraps `_post_json`, which opens a fresh TCP connection per call and does client-side `json.loads`. For batch-32 by 1024-dim vectors that is several hundred KB parsed in-process and attributed to the server. The methodology was deliberately NOT reshaped (no keep-alive, no response-size trimming) — it is a legitimate end-to-end in-cluster client measurement — but it is now stated: a `TIMING_INCLUDES_NOTE` constant is written into every payload as `timing_includes` and repeated in the module docstring, so a quoted figure carries its own methodology.

<!-- fr:journal kind=finding scope=plan id=f-d1-rotate-request-body created=2026-08-02T17:09:01 phase=3 state=fixed -->
### f-d1-rotate-request-body · finding [fixed] · The harness sent one identical body 33 times — a best case, not a measurement (phase 3)

Every iteration reused the same query and candidate set, so the numbers reflected fully warm caches and zero tokenizer variance. Adopted the review's design opinion: `generate_filler_query(index)` and `generate_filler_passages(n, offset=...)` rotate content across iterations, for both the rerank body and both embedding shapes.

Two constraints kept the rotation honest rather than merely noisy: text length is held roughly constant (asserted to within 30 characters across offsets) so rotation varies content without varying the work per call — a wildly different token count per iteration would make the latency distribution meaningless — and every rotated query names a topic that IS in the candidate set, which is what makes the degeneracy magnitude gate (see f-i8) evidence of failure rather than evidence of an irrelevant candidate set. All text remains generic invented filler.

<!-- fr:journal kind=finding scope=plan id=f-c2-discretion created=2026-08-02T17:12:39 state=fixed -->
### f-c2-discretion · finding [fixed] · Four discretion breaches — the spec violated its own Scope discipline rule

Review found four items exceeding the permitted generic detail. (1) a phrase that quantified the corpus's language coverage and named its region — both corpus statistics; reduced to 'multilingual'. (2) The Test Plan reproduced the requester's benchmark SIZE and BASELINE SCORE, which the spec's own Scope discipline section forbids three hundred lines earlier — the document broke its own rule; replaced with a pointer to the private issue. (3) 'mis-ranked non-English notes' characterises the consumer's document type; changed to 'documents'. (4) The issue NUMBER is a correlatable identifier — anyone with access to a candidate repo confirms or eliminates it in one lookup; dropped. Repo-wide rescan clean. Nothing ever named the consumer repo or product, and commit messages were clean throughout.

<!-- fr:journal kind=finding scope=plan id=f-i1-seed-source-vacuous created=2026-08-02T17:47:05 state=fixed -->
### f-i1-seed-source-vacuous · finding [fixed] · The seed-source assertion matched its own explanatory comment (PROVEN vacuous)

`test_seed_is_version_gated_by_a_marker_not_seed_if_absent` asserted `SEED_SOURCE in script`, where `script` is the initContainer's `command + args` joined — and the YAML block scalar carries its own `#` comments into that string. deployment.yaml:129 is a comment naming `/models-src/gpu` while explaining why the CPU repository must not be seeded, so the detector fired on its own documentation. Re-proven here before fixing: mutating the executable line to `cp -R /models-src/cpu/. /models/` left the test green.

The failure it fails to catch is fully silent: the CPU-targeted graph.pbtxt is seeded, OVMS loads both servables on the CPU, both probes pass, ArgoCD is green, and the spike's headline number is measured on the CPU while labelled GPU — the one number the whole phase exists to produce.

Fixed with a `_seed_script_live()` helper that strips comment lines (the same treatment the LoadBalancer scan in the same file already used) plus a regex on the EXECUTABLE line, `^\s*cp -R /models-src/gpu/\. /models/`, and a second assertion that `/models-src/cpu` appears nowhere in the live script. Mutation re-run: the cpu mutation now fails, revert restores green.

<!-- fr:journal kind=finding scope=plan id=f-i2-push-polarity created=2026-08-02T17:47:07 state=fixed -->
### f-i2-push-polarity · finding [fixed] · The 'PR must not push' assertion checked for a substring, not a polarity (PROVEN vacuous)

`assert "pull_request" in push_val` is satisfied by `!=`, by `==`, by `... || true` and by `true # pull_request` alike. Re-proven: inverting the workflow to `${{ github.event_name == 'pull_request' }}` left the test passing.

The damaging half is the inversion, and it is silent in the direction that matters: on push:main the expression evaluates false, nothing is published, the Deployment's pinned tag ImagePullBackOffs on first sync, and the PR that caused it merged with a green build job.

Fixed with an exact match after whitespace normalisation: `push_val.replace(' ', '') == "\${{github.event_name!='pull_request'}}"`. Mutation-verified both ways.

<!-- fr:journal kind=finding scope=plan id=f-i3-capacity-cel-selector created=2026-08-02T17:47:38 state=fixed -->
### f-i3-capacity-cel-selector · finding [fixed] · The capacity tripwire walked YAML keys only, missing the idiomatic CEL selector (PROVEN)

`test_claim_requests_no_capacity` asserted `leaf != 'capacity'` over `_walk`, which yields dict KEYS. Under `resource.k8s.io/v1` the common way to filter on a device attribute is a CEL selector, where `capacity` occurs only inside a STRING VALUE: `expression: device.capacity["gpu.intel.com"].memory.compareTo(quantity("2Gi")) >= 0`. Re-proven: feeding exactly that selector to the walker produced zero violations and the test passed.

Since the live ResourceSlice reports `capacity.memory: "0"` (the iGPU borrows host RAM through i915), such a selector can never match — the pod sits Pending with no event naming the cause, which is indistinguishable from a pod that has not been scheduled yet, with the suite green.

Fixed by also scanning string values under `spec.spec.devices`. Documented in docs/runbooks/frank-gotchas/igpu-dra.md (new subsection under the capacity gotcha) and one-lined into agents/rules/frank-gotchas.md, because the key-only-walker mistake generalises to any DRA guard.

<!-- fr:journal kind=finding scope=plan id=f-i4-models-rev-drift created=2026-08-02T17:47:39 state=fixed -->
### f-i4-models-rev-drift · finding [fixed] · Nothing forced MODELS_REV to move when the Dockerfile's model contents changed

Three mechanisms assumed rev immutability and none enforced it: `imagePullPolicy: IfNotPresent`, the seed marker (compares MODELS_REV only), and the tag-vs-workflow-env test (ties the two rev DECLARATIONS to each other, neither to the Dockerfile). Change `--weight-format int8` to `int4`, leave `MODELS_REV: "1"`: CI republishes `:1` with different bytes, the manifest is byte-identical so ArgoCD syncs nothing, a pod delete reuses the node-cached `:1`, and even if the new image landed the marker still reads `1` so the seed skips. Old weights served indefinitely, everything green — the comfyui seed-if-absent bug one layer up.

Fixed in two halves. (1) Always-on, no git: `test_models_rev_and_the_dockerfile_arg_default_agree` — the Dockerfile's `ARG MODELS_REV` default must equal the workflow env, so a build without the build-arg cannot bake a LABEL claiming a rev it is not. (2) `test_models_rev_moves_when_the_dockerfile_changes` diffs the WORKING TREE Dockerfile against origin/main (falling back to main) and fails when significant lines changed while the rev did not. Blank lines, whole-line comments and the `ARG MODELS_REV=` line are normalised out, so a comment rewording does not demand a bump — training people to bump reflexively would defeat the point. It SKIPS (never errors) when git is unavailable or neither ref resolves, because a shallow CI checkout of a PR merge commit has no origin/main.

The rule is factored into a pure `rev_drift_violation()` so it can be falsified offline: on the branch that INTRODUCES the image there is no baseline to diff, so a purely git-driven gate would have been exercised only by its own happy path. Mutation-proven twice: synthetically (int8 -> int4 with an unchanged rev flags, with a bumped rev does not) and live, by pointing the baseline at HEAD via OVMS_MODELS_REV_BASE_REF and editing the Dockerfile.

<!-- fr:journal kind=finding scope=plan id=f-i5-ghcr-first-publish-private created=2026-08-02T17:47:41 state=fixed -->
### f-i5-ghcr-first-publish-private · finding [fixed] · First GHCR publish creates the package PRIVATE and the pod has no pull secret

`ghcr.io/derio-net/ovms-retrieval-models` does not exist yet, and a first push from Actions creates the package private by default. The Deployment carries no imagePullSecret — deliberately, matching this repo's convention of public packages (the comment in apps/cnc-base/manifests/statefulset-node.yaml; `cnc-ghcr-pull` in apps/cnc-staging/manifests/ is the private-image alternative) — so on first sync `seed-models` ImagePullBackOffs and NO change to this repo fixes it. It presents as a broken build or a broken sync, which is where the time goes.

Fixed as a new FIRST step in phase 5 task 1 (P5.T1.S1), before any sync check: set the package visibility public, or add a pull secret and say so, then verify with an unauthenticated pull. Existing steps renumbered to S2/S3 with their state rows. Guarded by scripts/tests/test_ovms_retrieval_phase5_plan.py, which asserts the step exists, names the pull-secret alternative, and comes BEFORE the sync-verification step. Also one-lined into agents/rules/frank-gotchas.md and written up in docs/runbooks/frank-gotchas/igpu-dra.md — it is not iGPU-specific and will recur on the next new package.

<!-- fr:journal kind=finding scope=plan id=f-m1-path-filter-asymmetry created=2026-08-02T17:48:08 state=fixed -->
### f-m1-path-filter-asymmetry · finding [fixed] · PR and push path filters differed, so a workflow-only edit published nothing on merge

The pull_request filter included the workflow file; the push filter did not. A PR that edits only .github/workflows/build-ovms-retrieval-models.yml — exactly what a MODELS_REV bump or a `tags:` change is — would build on the PR and match no push path on merge, so no image is published and the Deployment's pinned tag ImagePullBackOffs. The half that fails is the half that does not run, so the PR page shows nothing to notice. Mirrored the lists (spelled out twice: GitHub Actions rejects YAML anchors) and added `test_pull_request_and_push_path_filters_are_identical`.

<!-- fr:journal kind=finding scope=plan id=f-m3-gha-cache-eviction created=2026-08-02T17:48:09 state=fixed -->
### f-m3-gha-cache-eviction · finding [fixed] · cache-to: type=gha,mode=max on a multi-GB model image would evict the repo-wide Actions cache

GitHub's Actions cache is a REPO-WIDE 10 GB budget with LRU eviction. Caching a multi-GB weights image would evict most of what build-comfyui.yml and build-openrgb.yml — the repo's only other type=gha consumers — depend on: a cross-workflow slowdown with no owner. `mode=min` is not a fix here, and the reasoning is worth keeping: the FINAL stage IS the weights, while the expensive part (pip install plus four export_model.py conversions) lives in a stage mode=min does not export, so mode=min would still be large and still useless. Dropped both cache-from and cache-to with the reasoning in a comment; the workflow only runs when the Dockerfile changes, which is exactly when the cache would miss. Guarded by `test_the_model_image_does_not_consume_the_repo_wide_actions_cache`.

<!-- fr:journal kind=finding scope=plan id=f-m4-acceptance-note-contradiction created=2026-08-02T17:48:11 state=fixed -->
### f-m4-acceptance-note-contradiction · finding [fixed] · Acceptance row was status: ci while its notes still said '(local guard, not CI-run)'

`gpu-igpu-claim-documented` was correctly moved to status: ci — repo-tripwires.yml runs `pytest scripts/tests/ -q` on every PR — but the notes kept the sentence written back when nothing ran the suite. The summary counts it one way and the sentence a human reads says the other, with nothing to reconcile them. Notes rewritten to name the workflow that makes it CI, and the report set regenerated with `fr acceptance report --deterministic`.

Added a general guard, scripts/tests/test_acceptance_status_matches_notes.py: a row claiming status: ci must not simultaneously deny CI enforcement in its notes, and must name at least one `levels` entry (status: ci with no evidence pointer is unfalsifiable). Deliberately scoped to ci rows only — several OTHER rows carry legitimately stale 'local guard' prose from before repo-tripwires.yml existed (matrix.yaml:105 references scripts/tests and is now wrong; the apps/*/tests ones are still accurate since the tripwire job runs scripts/tests only). Rewriting those is separate work with a different blast radius, and is left flagged rather than done here.

<!-- fr:journal kind=finding scope=plan id=f-m7-final-stage-copy created=2026-08-02T17:48:12 state=fixed -->
### f-m7-final-stage-copy · finding [fixed] · The final-stage guard listed toolchain NAMES, so a COPY --from could smuggle it in

`test_final_stage_carries_no_export_toolchain` forbade the strings optimum/nncf/torch/pip install in the final stage. `COPY --from=export /usr/local/lib/python3.12 /opt/py` contains none of them and drags the whole export toolchain into the shipped image. The Dockerfile today is correct (busybox + ARG/LABEL + one `COPY --from=export /out /models-src`), so this was guard weakness only. Fixed structurally: the final stage must contain EXACTLY ONE `COPY --from=`, the /out one — closing the class rather than lengthening the name list. Mutation-verified by appending the python3.12 copy.

<!-- fr:journal kind=finding scope=plan id=f-m10-discretion-tripwire created=2026-08-02T17:48:55 state=fixed -->
### f-m10-discretion-tripwire · finding [fixed] · Nothing enforced the discretion rule the spec calls a blocking finding — and the journal still held a residual leak

The spec's Scope discipline section asks reviewers to treat a breach as blocking, and the spec then breached it itself in its own Test Plan. Prose is not a control. Added scripts/tests/test_third_party_discretion.py, a forbidden-SHAPE scan over this branch's public artefacts (spec, plan folder, both journals, apps/ovms-retrieval, the bench harness, the ovms/igpu tests, the igpu-dra gotchas file, and itself).

Design constraint that shaped everything: the guard must not embed what it forbids, or it publishes the private strings permanently in the one file whose purpose is that they never appear — and a literal denylist is useless against the next leak's wording anyway. So the checks are patterns for the SHAPE of a disclosure: a retrieval-quality metric followed by a comparator and a number; a COUNT of languages ('multilingual' is permitted and load-bearing, 'N languages' is a corpus statistic); a corpus/benchmark SIZE within 120 characters of requester-words; an issue NUMBER near requester-words (a correlatable identifier — one lookup confirms or eliminates a candidate repo); and a github.com org outside a small public allowlist. The only literal list is four generic English synonyms for a counterparty, forbidden because the agreed vocabulary is exactly one phrase, 'an external client'. 'tenant' and 'vendor' were tried and REMOVED: multi-tenancy is real here and 'the repo already vendors X' is a verb — a guard that cries wolf gets deleted.

The file scans itself, so its own pattern definitions carry a `discretion-selftest` line marker; a further test asserts that marker appears in NO other file, so the per-line exemption cannot grow into a general opt-out.

It immediately found a residual leak the earlier discretion pass had left: journal entry f-c2-discretion, which DOCUMENTED the fix, quoted the removed phrase verbatim — reproducing the same corpus statistic (language count and region) it was recording the removal of. Redacted to a description of the shape. Every pattern was mutation-proven by planting one instance of each in a scanned file: five of five fired, then reverted clean.

<!-- fr:journal kind=finding scope=plan id=f-m11-device-plugin-ban created=2026-08-02T17:48:57 state=fixed -->
### f-m11-device-plugin-ban · finding [fixed] · A guard forbidding the words 'Device Plugin' pushed the corrected README into vagueness

`assert "Device Plugin" not in text` stopped patches/phase05-mini-config/README.md from ever NAMING the model it used to describe, so the correction read 'the retired per-node device-exposure model at a since-removed app path' — accurate, unsearchable, and useless to the reader who arrived holding a device-plugin tutorial. A doc that cannot name the wrong answer cannot tell you that you are holding it.

Relaxed to a contextual rule: every PARAGRAPH mentioning the device plugin must also mark it as retired/not-deployed (a small list of markers). Added the converse test — the README MUST name it — so the correction stays findable by whoever searches for the wrong thing. Restored clear prose: a 'What this is NOT' block naming the Intel GPU Device Plugin, explaining the extended-resource mechanism it used, and giving the two concrete symptoms of following it (an `i915` entry expected under node.status.allocatable; an extended-resource request in resources.limits) with the outcome — the pod never schedules, no event says why. The Verify block's parenthetical was rewritten for the same reason. Mutation-verified by planting a paragraph that presents the plugin as deployed.

<!-- fr:journal kind=decision scope=plan id=d-cpu-arm-committed created=2026-08-02T17:48:58 -->
### d-cpu-arm-committed · decision · The CPU control arm is a committed manifest applied by hand, not prose in a step

The GPU-vs-CPU comparison is what decides whether the DRA plumbing was worth building, and it existed only as instructions in P5.T2.S2. Three properties make it valid and all three are easy to lose in a pod typed at measurement time — no ResourceClaim (the control must not hold the device it is a control for, and with count: 1 on a single-device node it would also block the GPU pod from rescheduling), seeded from /models-src/cpu (target_device is baked into graph.pbtxt at export, so the device under test is decided by WHICH REPOSITORY IS SEEDED, not by a flag), and the same node/image/resource envelope. Each failure produces a plausible-looking number.

Committed as apps/ovms-retrieval/cpu-arm-pod.yaml — one directory ABOVE manifests/ and absent from kustomization.yaml, so the ArgoCD Application (source path apps/ovms-retrieval/manifests) can never sync it. emptyDir rather than a PVC, since it is throwaway and a second RWO Longhorn volume on the node is pure friction; no version-gated seed either, because an emptyDir is empty by construction. Three tests: no claim anywhere, CPU repository + same node + same image + same limits, and not-GitOps-managed (outside manifests/, not in the kustomization, Application source path unchanged). All four mutations fired.

Also adopted: `:latest` dropped from the workflow tags. Nothing consumed it, and on an image whose entire premise is 'new contents get a new rev' a floating tag is an attractive nuisance that makes republishing under an unchanged rev feel survivable — the exact drift f-i4 now refuses.

<!-- fr:journal kind=discovery scope=plan id=d-phase5-carry-notes created=2026-08-02T17:49:00 phase=5 -->
### d-phase5-carry-notes · discovery · Phase 5 carries three notes it cannot recover from later: MediaPipe Ready, two-servable probe coverage, measurement scope (phase 5)

(1) UNVERIFIED ASSUMPTION carried forward. The runtime gate proved /v2/health/ready is server-level, but it did so against a single CLASSIC model; /v2/models/<name>/ready has never been exercised against a MEDIAPIPE-GRAPH servable, which is what embeddings_ov and rerank_ov emit. A 404 fails the startup probe and the pod restart-loops — loud, fine. A hardcoded 200 puts the silent-green failure the probe design exists to prevent straight back, and only GET /v1/config would show it. P5.T1.S2 now says to check /v1/config BEFORE trusting Ready and to record which behaviour was observed.

(2) The startup/readiness split gates EXACTLY TWO servables, BY NAME. A third would be ungated and the pod would go Ready with it dead — the same failure one model down. Written into P5.T1.S3.

(3) The number comes from ONE pod, hostname-pinned to a control-plane node, holding one iGPU with no other GPU tenant. It is not what a rescheduled or scaled deployment would see: the pin is what makes it repeatable, so dropping it invalidates the figure rather than generalising it. P5.T3.S1 now requires that scope to be stated wherever the number is reported, including to the external client.

All three are guarded by scripts/tests/test_ovms_retrieval_phase5_plan.py, which also checks that every step id has a state row — a manual phase's step text is the only place these live, so a quiet rewording would erase them with nothing failing.

<!-- fr:journal kind=finding scope=plan id=f-m10-marker-scope created=2026-08-02T17:53:06 state=fixed -->
### f-m10-marker-scope · finding [fixed] · The discretion guard's own exemption marker was a repo-wide taboo, and the journal tripped it

First cut asserted the per-line exemption marker appeared in NO file but the guard itself. The journal entry DESCRIBING the mechanism then named it, and the full-suite run failed — a guard firing on documentation of itself, the same shape as the seed-source comment (f-i1) and the lbipam comment before it.

Reworked so the exemption is scoped by FILE PATH rather than by the string being forbidden: `_scannable(text, path)` blanks marker lines only for this file, and elsewhere the marker is inert text. Other artefacts can now name it freely and gain nothing. The replacement test asserts the mechanism directly — the same marked line is exempt for this file, unchanged for another scanned file, and genuinely matches a pattern — rather than planting a marker in a real artefact. Full suite re-run green afterwards.

<!-- fr:journal kind=finding scope=plan id=f-dockerfile-requirements-subset created=2026-08-02T18:07:44 phase=1 state=fixed -->
### f-dockerfile-requirements-subset · finding [fixed] · CI build FAILED: the Dockerfile's 'same pins as upstream' comment was false (phase 1)

The pull_request build job caught this on its first run — which is the entire reason it was added, since every other build workflow in this repo is push:main-only and would have shipped it unbuilt. The export stage hand-copied upstream's demos/common/export_models/requirements.txt inline with a comment claiming parity; it was a SUBSET, dropping requests (plus accelerate/datasets/diffusers/einops/numpy/pillow/torchvision). Build died at 5s: ModuleNotFoundError: No module named 'requests', raised inside optimum's own openvino export command. Likely proximate cause: recent huggingface_hub moved to httpx, so requests is no longer installed transitively while optimum still imports it. Fixed by FETCHING requirements.txt from the same pinned MODEL_SERVER_REF that export_model.py was already fetched from one line below — the script and its dependency list can no longer disagree, and it is exactly as reproducible as the fetch it sits next to. Added a grep tripwire so the build fails loudly at fetch time if upstream ever drops requests, rather than 5s into a model export. Also removed three now-orphaned ARG pins that would have read as authoritative while controlling nothing.
