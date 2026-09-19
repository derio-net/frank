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
