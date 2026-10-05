# Journal: 2026-09-19--infer--ovms-pool-watchdog-activity-signal

<!-- fr:journal kind=discovery scope=plan id=p1-success-series-confirmed created=2026-09-20T00:24:21 phase=1 -->
### p1-success-series-confirmed · discovery · Adding ovms_requests_success to the sum breaks FIVE tests, not one (phase 1)

P1.T3.S1 passed on its first run, so the guard was proved by deliberately breaking the implementation it guards against: activity temporarily became accepted + rejected + success.

Both readings, from the committed fixtures (2026-09-19 capture):
  correct sum (accepted + rejected): metrics-idle 1, metrics-busy 2 -> the probe-only fixture equals the stamped baseline, busy=no.
  with success included:             metrics-idle 450, metrics-busy 453 -> activity=450 against a stamped 1, busy=yes.

The break failed test_readiness_probe_traffic_alone_does_not_read_as_busy AND four pre-existing idle tests (pool-at-baseline, idle-with-elevated-pool, idle-too-recent, unlimited-cgroup), every one of them flipping to 'reason=busy'. That is the spec's predicted failure mode observed directly: ovms_requests_success is dominated by readinessProbe traffic (449 of the idle fixture's 450), so every tick reads busy forever and Rule 2 is silently disabled. Reverted; 22 tests green.

<!-- fr:journal kind=discovery scope=plan id=p1-activity-baseline-and-scrape-gap created=2026-09-20T00:24:58 phase=1 -->
### p1-activity-baseline-and-scrape-gap · discovery · Three choices Phase 1 had to make that the spec does not state (phase 1)

1. FIRST TICK. With no pool-watchdog-last-activity annotation yet, the script sets last_activity=activity (no delta) rather than 0. Treating an absent annotation as 0 would make every fresh Deployment read busy on its first tick, because the idle fixture's own counters are already non-zero (accepted=1 from the startupProbe era, not 0). The in_flight term still applies on that tick, and the pre-existing no-baseline-yet path still guards the idle clock.

2. THE SCRAPE CAN FAIL WITHOUT THE EXEC FAILING. curl is inside the same exec as the cgroup read, so if curl alone fails the exec still returns shmem+limit and the script proceeds with in_flight=0, activity=0 — it then STAMPS last-activity=0, and the next tick's real counter reads as a rise, i.e. busy. Not wrong, but it is not the spec's 'reason=metrics-unreadable, take no hygiene action' behaviour. Phase 2's 'Unreadable metrics fail toward busy' task closes this; Phase 1 deliberately leaves it.

3. THE TICK GOT SHORTER. Removing the CPU path removed 'sleep $SAMPLE_SECONDS' with it, and the test suite's wall time dropped from ~20s to ~11s — the same ~10s comes off every real tick, as the spec predicts.

<!-- fr:journal kind=finding scope=plan id=f1 created=2026-09-20T00:33:51 phase=1 state=fixed -->
### f1 · finding [fixed] · sum_series matched a metric name by PREFIX, so a suffixed series would inflate activity (phase 1)

Review of phase 1. Both the script's awk helper and the test's mirror used a bare prefix match (index($0,name)==1 / str.startswith(name)). OVMS already ships ovms_graph_processing_time_us_bucket/_count/_sum from the same endpoint, so suffixing a base name is the source's established habit — a future ovms_requests_accepted_total would have been folded into the activity sum silently. Failure direction is the quiet one: permanently busy, Rule 2 stops reclaiming, nothing reports it until the ceiling — the same shape as the ovms_requests_success near-miss this phase exists to prevent. Fixed by anchoring on name+'{' or name+' ' (the exposition format guarantees one follows the name), in BOTH helpers — mirroring the bug in the test would have made the suite agree with a broken parser. RED test added first (test_a_suffixed_metric_name_is_not_counted_as_activity): confirmed activity=100001 against an expected 1, then green. 23 passed.

<!-- fr:journal kind=review scope=plan id=r1 created=2026-09-20T00:33:53 phase=1 -->
### r1 · review · Phase 1 review: three claims checked objectively, two cleared (phase 1)

(1) awk large-integer printing — a scientific-notation result would abort $(( )) under set -e and silently kill the watchdog every tick. Checked: awk prints integral values as integers (12345678, 10000000, 2147483648 all exact), so counters cannot trigger it. Cleared. (2) Prefix collisions among the ten current ovms_* names: none today, which is why this was a latent hazard rather than a live bug — see f1. (3) Removal of millicores= from the result lines: no consumer anywhere in the repo reads that field (the remaining 'millicores' hits are the DRA ResourceSlice's unrelated capacity figure). Cleared. Also confirmed the phase left Rule 1's thresholds, cost model and comments untouched as scoped.

<!-- fr:journal kind=discovery scope=plan id=bd7d1406a681 created=2026-09-20T00:46:57 phase=2 -->
### bd7d1406a681 · discovery · Two REFACTOR-step tests passed before their implementation existed — proved non-vacuous by deliberate breakage (phase 2)

P2.T1.S3 (test_a_second_consecutive_tick_does_not_restart_again) and P2.T3.S3
(test_rule_one_still_fires_when_metrics_are_unreadable) both passed on first
run, before their task's GREEN step was implemented — same shape as phase 1's
p1-success-series-confirmed, but for REFACTOR-labelled steps rather than RED
ones. Cause differs per test:

1. The second-tick test can't observe the stub's *actual* persisted state
   (the fake kubectl is stateless across subprocess invocations, driven by env
   vars), so it approximates "the stamped value" with `int(time.time())`
   computed after the first run_script() call returns. That means it never
   exercises whether restart() itself stamped anything — it independently
   re-tests "a fresh last-busy clock does not restart", which was already true
   pre-Task-1 (test_does_not_restart_when_idleness_is_recent covers the same
   ground). The real guard for the stamp mechanism is P2.T1.S1's call-log
   assertion.

2. The Rule-1-still-fires test passed because unreadable-metrics handling
   didn't exist AT ALL yet on the pre-Task-3 script — Rule 1 already ran
   unconditionally before any busy/metrics check, so of course it fired.

Neither is vacuous, though: confirmed by temporarily breaking the
implementation each is supposed to pin (dispatch-prompt discipline for a
test that passes where red was expected), then reverting.

  - Broke the idle_for>=IDLE_SECONDS gate to always restart -> the
    second-tick test failed exactly as expected (spurious second
    `rollout restart`). Confirms it DOES pin the "no restart on a second
    consecutive tick" shape, even though it isn't exercising the stamp call
    site directly.
  - Moved the metrics-unreadable exit to BEFORE Rule 1 (the literal ordering
    mistake the step exists to prevent) -> the rule-one test failed exactly
    as expected (`action=none reason=metrics-unreadable` instead of
    `action=restart reason=critical-pool`).

Both reverted; 28/28 green afterward.

<!-- fr:journal kind=discovery scope=plan id=9e65f080e861 created=2026-09-20T00:47:19 phase=2 -->
### 9e65f080e861 · discovery · Phase 2 implementation choices the plan text left implicit (phase 2)

1. UNREADABLE-METRICS DETECTION is a single flag (`metrics_unreadable`, set
   when the tail'd metrics blob is empty), checked in three places: it guards
   the busy/activity_reset determination (skipped entirely, so busy stays
   `no` and the counter-reset branch can't misfire on a bogus 0), it guards
   BOTH annotate calls (activity stamp and busy stamp — stamping
   `activity=0` on an unreadable tick would poison the NEXT tick's baseline
   into reading any real count as a rise, reopening root cause A one tick
   later than the original bug), and it gates a dedicated exit placed AFTER
   Rule 1 and BEFORE the `busy=yes` check. Placement is load-bearing: Rule 1
   does not read this flag at all, by construction, so it fires on shmem/
   limit alone regardless of metrics health — pinned by
   test_rule_one_still_fires_when_metrics_are_unreadable (see the
   deliberate-break confirmation in the sibling discovery entry).

2. `activity_reset=1` is appended only to the `reason=busy` log line (not
   every line), since it only has meaning when busy is decided partly or
   wholly by the reset branch. The metrics-unreadable exit line intentionally
   omits `in_flight=`/`activity=`/`activity_reset=` altogether — both are
   placeholder zeros on that path and printing them would misrepresent an
   unread value as a read one, undermining the "greppable result line carries
   its inputs" contract for exactly the tick where that contract matters
   most (this is the tick nobody trusts on faith).

3. The restart() stamp uses the SAME `$now` the tick already computed
   earlier (`date -u +%s`), not a fresh timestamp at stamp time — the two
   `kubectl` calls inside restart() (rollout restart, then annotate) are
   sequential but both describe one tick's decision, so reusing `$now` keeps
   the log line and the stamped value in agreement even though the rollout
   restart call itself takes real wall time.

<!-- fr:journal kind=finding scope=plan id=f2 created=2026-09-20T00:53:58 phase=2 state=fixed -->
### f2 · finding [fixed] · restart() stamped the clock before logging, so a failed stamp erased the restart's only record (phase 2)

Review of phase 2. The new idle-clock stamp was placed between 'rollout restart' and the result line. Under 'set -e' a non-zero kubectl aborts the script, so a transient API error on the annotate would abort BEFORE the echo: the Deployment really rolls, and nothing anywhere records it — not the log, and therefore not the ovms-pool-watchdog-restart-loop alert phase 4 builds on that log. The alert exists precisely because the 2026-09-19 loop was invisible; an unlogged restart is the same blindness by a narrower route. Fixed by emitting the result line first, then stamping. Deliberately NOT '|| true' on the annotate: a swallowed stamp failure leaves the stale clock in place and re-opens the per-tick loop, whereas aborting fails the Job visibly (backoffLimit 1 bounds the retry). RED test added first with failure injection in the kubectl stub (test_a_restart_is_logged_even_if_stamping_the_clock_fails): confirmed 'the restart happened but was never logged' with empty stdout and rc=1, then green. 29 passed.

<!-- fr:journal kind=review scope=plan id=r2 created=2026-09-20T00:54:00 phase=2 -->
### r2 · review · Phase 2 review: the metrics-unreadable placement is right, and checked against both rules (phase 2)

The metrics_unreadable exit sits AFTER Rule 1 and BEFORE the busy check, which is the only correct position: Rule 1 does not consult busy and must stay armed when the scrape fails (an unreadable /metrics is not a reason to stop avoiding an OOM), while every decision past that point needs a real activity reading. Confirmed the phase also skips BOTH annotate calls on that path - stamping the placeholder activity=0 would poison the next tick into reading a genuine count as a rise, which is the mirror image of the bug being fixed. Also confirmed: first-tick default (last_activity=activity) makes the counter-reset branch unreachable on a fresh Deployment rather than firing spuriously; Rule 1's thresholds and comments untouched as scoped; f1's anchored metric matching intact.

<!-- fr:journal kind=discovery scope=plan id=58b518d099b3 created=2026-09-20T01:09:24 phase=3 -->
### 58b518d099b3 · discovery · P3.T1.S1's RED test passed on first write, for the wrong reason — a stub-shift confound (phase 3)

Writing the RED test required first shifting the kubectl-exec stub's output shape
(shmem, current, limit, metrics — a new line before limit), since the script's
new `memory.current` comparison can't be expressed against the old stub at all.
Doing that against the UNMODIFIED script first (before touching pool-watchdog.yaml)
is what the phase description's "positional sed -n Np parsing must move together"
warns about: the old script still reads line 2 as `limit`, so it silently received
FAKE_CURRENT's value instead of the real limit.

`test_rule_one_triggers_on_memory_current_not_shmem`'s first draft
(FAKE_SHMEM=0.4*LIMIT=6.4GiB, FAKE_CURRENT=0.6*LIMIT=9.6GiB) passed immediately —
but for the wrong reason: old script's critical = FAKE_CURRENT/2 = 4.8GiB, and
shmem(6.4GiB) >= 4.8GiB was true by coincidence, not because memory.current was
read at all. Confirmed by rerunning the isolated test and inspecting its captured
`limit=` field in the result line: it read `limit=$FAKE_CURRENT`'s value, not
$FAKE_LIMIT.

Fixed by rechoosing fixture values (FAKE_SHMEM=1.71GiB, well below both the real
critical of 8GiB AND ELEVATED_BYTES) so the old-broken parsing and the new-correct
parsing diverge in their VERDICT, not just their internal arithmetic: old script
(critical = FAKE_CURRENT/2 = 4.8GiB, shmem 1.71GiB < 4.8GiB) falls through to Rule 2
and reports pool-at-baseline (no restart); new script (critical = real limit/2 =
8GiB, current 9.6GiB >= 8GiB) restarts on critical-pool. Reran against the
unmodified script: genuinely RED (action=none/pool-at-baseline, not
action=restart/critical-pool). Then implemented the GREEN script change; both new
tests plus the full 29-test baseline passed (31/31).

The collateral effect worth recording: applying ONLY the stub shift (before the
script fix) flipped 12 of the 29 pre-existing tests red too, all via the same
mechanism (old `limit` var silently reading FAKE_CURRENT's default-to-FAKE_SHMEM
value). That is expected fallout of the interface coupling the phase description
calls out, not a regression — the script fix in the same task restores all of
them, and the full suite was green again before moving to REFACTOR.

<!-- fr:journal kind=review scope=plan id=029335c90609 created=2026-09-20T01:09:39 phase=3 -->
### 029335c90609 · review · Phase 3 review: Rule 1/Rule 2 numerators verified to diverge as designed; f1/f2 untouched (phase 3)

Confirmed the split is real, not just log-line cosmetics: Rule 1 (`if [ "$current"
-ge "$critical" ]`) reads memory.current; Rule 2 (`if [ "$shmem" -lt
"$ELEVATED_BYTES" ]`) still reads shmem. test_the_elevated_pool_is_still_measured_on_shmem
pins this directly (current above ELEVATED_BYTES, shmem below it, idle clock stale
-> no restart, pool-at-baseline) and genuinely reds if Rule 2's comparison is
swapped to `current` (verified during RED, see the sibling discovery entry for the
mechanics of getting a clean red here).

Checked the three untouched constraints named in the dispatch:
- f1 (anchored metric matching, name+'{'/name+' '): sum_series and its
  awk pattern are byte-identical to before this phase; not touched.
- f2 (restart() logs before stamping the idle clock): restart()'s statement
  order is unchanged; only the echo text grew a `current=$current` field.
  test_a_restart_is_logged_even_if_stamping_the_clock_fails still passes.
- memory.max="max" guard: unaffected — it still only touches `limit`, and
  test_an_unlimited_cgroup_does_not_divide_by_a_word passes unchanged (current
  is simply unused when limit=0, since Rule 1's body is skipped).

Also confirmed every shmem-carrying result line now also carries `current=`
(restart, metrics-unreadable, busy, pool-at-baseline, no-baseline-yet,
idle-too-recent) per the task instruction "keep shmem= in every result line and
add current= beside it" — the two exit paths before the cgroup read
(no-running-pod, unreadable-cgroup) carry neither, since shmem/current are not
yet known at that point and never did carry shmem= either.

31/31 pool-watchdog tests green after the REFACTOR step (comment-only change to
CRITICAL_PERCENT, no behavioural diff, confirmed by an identical 31/31 rerun).

<!-- fr:journal kind=finding scope=plan id=f3 created=2026-09-20T10:24:54 phase=3 state=fixed -->
### f3 · finding [fixed] · Porting CRITICAL_PERCENT to memory.current would have moved the trigger and re-killed the consumer's index (phase 3)

Review of phase 3, and the most consequential finding in the run. The numerator change is right — memory.current is what memory.max is enforced against, and with swap off none of the difference is reclaimable (live: shmem 1.72 GiB, anon 0.50, kernel 0.01, current 2.22). But memory.current runs a roughly CONSTANT ~0.5 GiB above shmem, and CRITICAL_PERCENT=50 was calibrated against shmem, so carrying it across unchanged tightens the trigger by ~3.1 points of a 16Gi limit with nobody deciding to. Measured against the incident's own log line: peak shmem 8313102336 (7.74 GiB) was under the 8.00 GiB trigger, but the same moment as memory.current is 8.17 GiB — over by 174 MiB. Rule 1 would have killed the batch index that Rule 2 killed, so the PR would have shipped fixing root causes A and B while failing Test Plan row 5 for a third reason. My own framing of the Q&A option ('safety posture unchanged in spirit') was what missed this. Put to the operator, who chose recalibration: CRITICAL_PERCENT 50 -> 53, which is 8.48 GiB of memory.current, about 7.98 GiB of shmem — where the line effectively already sat. RED test first (test_the_numerator_change_did_not_silently_move_the_trigger), asserting BOTH directions so a future raise cannot hide behind this one. Spec and manifest comment updated to match.

<!-- fr:journal kind=discovery scope=plan id=21777db0e94f created=2026-09-20T10:39:55 phase=4 -->
### 21777db0e94f · discovery · The blog-edge/Hop rules confirmed the exemption list before it was written (phase 4)

P4.T2.S1's RED run enumerated exactly four hits before any exemption existed: headscale-api-key-expiry-warning, headscale-api-key-expiry-heartbeat-stale, crowdsec-decision-burst, crowdsec-canary-heartbeat-stale — all four querying Hop-originated namespaces (headscale-system, crowdsec-system) forwarded to Frank's VictoriaLogs via cross-cluster ingest, whose fluent-bit pipeline maps the message under `log`, not Frank's own `_msg` (this is independently documented in the alert-agent-cred-expiry rule's own comment, verified live against the endpoint). falco-critical-event shares the same folder and datasourceUid but filters on `priority:Critical` with no `log:`/`_msg:` field at all, so it correctly did not appear as a hit. Recorded all four as named exemptions with the reason inline in the test itself (_HOP_LOG_FIELD_EXEMPTIONS), not a silent skip.

<!-- fr:journal kind=discovery scope=plan id=51b87b06f440 created=2026-09-20T10:39:57 phase=4 -->
### 51b87b06f440 · discovery · Phase 4's acceptance row stays not-implemented — it belongs to Phase 6 (phase 4)

'fr plan edit --complete-phase 4' warned that acceptance row retrieval-pool-watchdog-restart-loop-is-visible is still not-implemented. Checked the matrix note and the plan itself: the row's proof is 'Test Plan row 7' (docs/superpowers/specs/...-design.md §Test Plan, explicitly 'post-merge, operator-driven') — a live check that the provisioned rule reads Normal with no restarts in the window, which cannot be done offline against the committed YAML. Phase 6 ('Post-merge Test Plan', tag: manual) lists this exact id in its own acceptance array and is the phase whose task walks the live cluster verification. Phases 1-3 left this row (and its sibling retrieval-batch-job-survives-pool-watchdog) untouched for the same reason. Left it as-is rather than flipping status to ci/scheduled, which would overclaim a live confirmation Phase 4's offline tests cannot provide — the offline half (rule shape, _msg/log:, queryType, noDataState, uid length) is what test_a_restart_loop_has_an_alert now pins.

<!-- fr:journal kind=discovery scope=plan id=b7ac4415a9a9 created=2026-09-20T10:51:51 phase=4 -->
### b7ac4415a9a9 · discovery · The new alert rule collided with a pre-existing exposure tripwire in a different app's test file (phase 4)

Adding the restart-loop rule's prose (comment header citing apps/ovms-retrieval/manifests/pool-watchdog.yaml, the annotation summary, and the runbook's 'kubectl ... get deploy ovms-retrieval') broke scripts/tests/test_ovms_retrieval_manifests.py::test_nothing_outside_the_app_routes_to_it, which fails any apps/**/*.yaml or clusters/**/*.yaml outside apps/ovms-retrieval that contains the literal substring 'ovms-retrieval' — a guard against IngressRoute/homepage-tile/LiteLLM-alias exposure. My rule is alerting, not exposure, but the check is a blunt substring scan with no such distinction. Rather than obfuscate the app name to dodge the scan (gaming the detector, the exact anti-pattern the frank-gotchas Process entry warns against), added ALERT_RULES to that test's existing named-exemption allowlist (alongside APP_DIR/APP_CR/WORKFLOW), with the reason inline — the same 'named exemption, never a silent skip' discipline this phase's own Task 2 teaches. Out of the dispatch's stated file scope (alert-rules-cm.yaml + test_ovms_pool_watchdog.py) but necessary to keep the full suite green; flagging explicitly for review. Full suite afterward: 952 passed (up from a baseline of 950+3 new tests), 1 xfailed, plus one unrelated pre-existing network-flaky failure (test_argocd_vcluster_pod_exclusion.py — helm template fetching a chart from a GitHub release asset timed out; file untouched by this phase, last touched in #658).

<!-- fr:journal kind=finding scope=plan id=f4 created=2026-09-20T10:56:31 phase=4 state=fixed -->
### f4 · finding [fixed] · The new alert's runbook recommended ovms_requests_success — the probe series this PR exists to discredit (phase 4)

Review of phase 4. The runbook annotation told the responder to 'compare request volume via ovms_requests_success'. That is the readiness-probe series: it moves ~8,600/day whether or not a client exists, and phase 1 exists because choosing it would have disabled Rule 2 silently. It got written into the runbook of the alert this work created, on the same branch that removes it everywhere else — which is the clearest possible evidence of how plausible the wrong name is. Fixed to ovms_requests_accepted with the reason inline. NOTE FOR PHASE 5: this shape would NOT be caught by the guard as specified (test_no_doc_recommends_the_probe_dominated_usage_query looks for 'increase(ovms_requests_success'), because the runbook names the series in advisory prose with no PromQL function. Phase 5 must widen it — but not to a blanket string ban, since the series is legitimately NAMED in places that explain why not to use it.

<!-- fr:journal kind=finding scope=plan id=f5 created=2026-09-20T10:56:33 phase=4 state=fixed -->
### f5 · finding [fixed] · The rule's comment and the spec both claimed a health-bridge-only routing that does not exist (phase 4)

Review of phase 4. Both said 'routes to health-bridge by the folder default (no telegram_direct)'. Read against notification-policy-cm.yaml that is false: the severity=warning route to 'Telegram - Willikins' sits BEFORE the grafana_folder=feature-health route and carries continue: true, so a warning-severity feature-health rule reaches Telegram AND health-bridge. There is no folder default for warnings; health-bridge-only requires an explicit health_bridge_only=true label (four rules in the folder carry it, matched by a route that precedes the severity routes with continue: false). Counted the folder to decide rather than guess: 49 rules, 22 of them warning-with-no-label, so Telegram is the plurality. Kept the paging and corrected the claim instead of adding the label — the operator's stated reason for wanting this alert was that five restarts in sixteen minutes paged nobody, and a bound of one hygiene restart per 30 minutes makes >2-in-30m close to noise-free. Originally my own spec text; corrected there too.

<!-- fr:journal kind=review scope=plan id=r4 created=2026-09-20T10:56:35 phase=4 -->
### r4 · review · Phase 4 review: exemptions verified live, out-of-scope edit accepted, suite failure confirmed environmental (phase 4)

(1) The four log: exemptions are correct and were checked against the live endpoint rather than accepted: Hop-forwarded logs carry a 'log' field and NO _msg at all (a sample record returns 'missing _msg field'), and log:"crowdsec-ban-canary verdict=" returns 8747 where the _msg form returns 0. (2) Out-of-scope edit to test_ovms_retrieval_manifests.py accepted: the exemption is one named file with reasoning inline, matching the three exemptions the guard already carries, and the guard still catches the three exposure mechanisms it exists for (IngressRoute, homepage tile, LiteLLM alias) — an alerting reference carries no auth story to withhold. (3) The reported full-suite failure (test_argocd_vcluster_pod_exclusion) was verified rather than taken on trust: the file and apps/argocd are untouched on this branch (empty diff against origin/main) and it passes on re-run — a helm template fetch timing out against a GitHub release asset. ADJACENT OBSERVATION, not actioned: crowdsec-decision-burst's query returns 0 on both log: and _msg: forms while 764,727 crowdsec lines exist and the namespace label matches, so its 'Adding ... decisions' phrase may never appear. It is a burst detector, so 0 is also the correct quiet reading, and it is pre-existing and out of scope — worth a separate look.

<!-- fr:journal kind=discovery scope=plan id=8796790cac1d created=2026-09-20T11:10:39 phase=5 -->
### 8796790cac1d · discovery · Widened f4's guard beyond a bare PromQL-function match, without a blanket string ban (phase 5)

f4 flagged that the phase-file-specified guard (match `increase(ovms_requests_success`) would not have caught phase 4's own regression — an advisory runbook line ("compare request volume via ovms_requests_success") with no PromQL function anywhere near it. Widened `scripts/tests/test_ovms_usage_query_docs.py` to two layers: (1) the literal `increase(ovms_requests_success` form, flagged unconditionally, and (2) a contextual check that flags the metric name when an advisory verb/phrase ("ask", "check", "compare", "query", "use", "run", "the useful series") governs it within 60 characters with no negation ("not"/"never") or a different, correct metric name in between.

Chose contextual detection over a blanket string ban because the series is legitimately NAMED in several places that exist to warn a reader off it: this docstring, the spec, the plan journal, other test docstrings in this suite, and the corrected comments this phase writes (e.g. "NOT ovms_requests_success, which counts the readiness probe..." right next to the name). A bare string ban would forbid explaining the mistake. Four whole-file/whole-directory exemptions carry that narrative material instead: docs/superpowers/journals/, this plan's own phase files, the spec itself (which quotes the broken advice in a blockquote specifically in order to correct it a few lines later), and scripts/tests/.

Verified empirically against the real repo before writing assertions: the two-layer check (a) flags all three of today's known-bad sites (frank-gotchas.md, igpu-dra.md, deployment.yaml) with zero false positives elsewhere in the tree, (b) flags a reconstruction of phase 4's exact regression shape, and (c) does NOT flag the already-fixed alert-rules-cm.yaml runbook line, which names the series specifically to warn against it ("compare ... via ovms_requests_accepted (NOT ovms_requests_success, which counts...)"). Pinned all three as separate tests: test_no_doc_recommends_the_probe_dominated_usage_query (RED->GREEN against the real docs), test_the_advisory_phrase_check_would_have_caught_phase_4s_regression, and test_the_check_does_not_flag_a_mention_that_warns_against_the_series.

<!-- fr:journal kind=discovery scope=plan id=4334cc9d2d71 created=2026-09-20T11:10:59 phase=5 -->
### 4334cc9d2d71 · discovery · The blog is deliberately not updated — no published post names the watchdog to correct (phase 5)

`grep -rl "pool-watchdog" blog/content/` returns nothing — no published post names the watchdog at all, so no published claim exists for this branch to make wrong. Per the repo's fix/extension blog workflow (agents/rules/repo-workflows.md, "Layer Fix/Extension Workflow"), a retroactive blog edit is for correcting something an existing post already asserts; writing the watchdog's first public description from scratch is new-content work, which this phase's scope (docs/gotchas corrections) does not cover. Recorded here as a deliberate decision, not a gap, so a later reviewer does not read the blog's silence as an oversight.

<!-- fr:journal kind=discovery scope=plan id=5b086337b3e7 created=2026-09-20T11:15:43 phase=5 -->
### 5b086337b3e7 · discovery · frank#813 collided with the third-party-discretion guard's requester-context check (phase 5)

Task 1's deployment.yaml correction cites `frank#813` for provenance, next to the word "client" ("however much real traffic it serves. frank#813."). That collided with `scripts/tests/test_third_party_discretion.py::test_no_issue_number_is_correlatable_with_the_requester` — a repo-wide guard, unrelated to this phase's stated scope, that flags any issue number sitting near requester-identifying words ("client", "requester", "the corpus", etc.) unless the number is in that file's `_PUBLIC_FRANK_ISSUES` allowlist. 813 genuinely is one of frank's own public issues (it is this plan's driving issue, named in the spec header), so it belongs in the same list as 748/751/759/793 — added with a reason inline, same discipline as those four and as phase 4's ALERT_RULES precedent (discovery b7ac4415a9a9). Out of the dispatch's stated file scope but necessary to keep the full suite green; flagging explicitly for review rather than reordering the citation to dodge the guard.

<!-- fr:journal kind=review scope=plan id=r5 created=2026-09-20T11:21:21 phase=5 -->
### r5 · review · Phase 5 review: the guard was proved against phase 4's actual regression, not just asserted (phase 5)

(1) Re-introduced phase 4's EXACT runbook wording ('compare request volume via ovms_requests_success against ...', advisory prose with no PromQL function) into alert-rules-cm.yaml and confirmed the new guard fails on it — two tests red — then restored the file and confirmed a clean empty diff and four green. That is the shape finding f4 said the plan's specified guard would have missed, so the widening is verified rather than claimed. (2) The guard is correctly NOT a blanket string ban: it does not flag the corrected runbook line that names the series in order to warn against it, and it carries whole-file exemptions for the journal, plan, spec and test dirs, which name the series for the same reason. (3) The out-of-scope edit to test_third_party_discretion.py is correct and was checked against the forge rather than reasoned about: 813 is a public derio-net/frank issue filed by the operator, and the allowlist entry matches the existing 748/751/759/793 pattern with its reason inline. (4) Hot-file discipline held: two single-line entries, full prose (106 lines) in the per-topic igpu-dra.md, both near-misses recorded with their measurements (449 of 450, and the 174 MiB margin). (5) Blog deliberately not updated and now on record — no published post mentions the watchdog.

<!-- fr:journal kind=decision scope=plan id=p6 created=2026-09-20T11:25:41 phase=6 -->
### p6 · decision · Phase 6 ships unimplemented — it is the back-loaded manual Test Plan (phase 6)

Phase 6 is tagged manual and every step is a live-cluster check that can only run against merged code: rows 1-4 and 6-8 are agent-drivable immediately post-merge, row 5 needs the downstream consumer to re-run its 40-batch index and is the acceptance proof. No phase-executor was dispatched — fr-goal does not dispatch manual phases, and nothing agentic depends on this one. Both acceptance rows stay not-implemented until their evidence exists; four phase executors independently declined to flip them for the same reason, which is the right instinct. The PR body carries the Test Plan verbatim and marks this phase unimplemented.
