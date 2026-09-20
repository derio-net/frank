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
