# Journal: 2026-10-13-stoa-status-bridge-idle

<!-- fr:journal kind=repro scope=debug id=1f5ac1bd0872 created=2026-10-13T15:25:28+00:00 -->
### 1f5ac1bd0872 · repro · Layer 25 Pipeline Idle stoa-status-bridge fires: 0 runs in 6h

Alert layer-25-idle-stoa-status-bridge (warning, frank-ops#25) fired 2026-10-13. Repro: kubectl -n tekton-pipelines get pipelinerun -l tekton.dev/pipeline=stoa-status-bridge; exact inter-run gaps from creationTimestamp. Last run before the gap 07:04Z, next 15:22Z (8.3h). Listener pod 33h old, 0 restarts; first event after the gap created a run immediately.

<!-- fr:journal kind=ruled-out scope=debug id=dc8e251a3814 created=2026-10-13T15:25:32+00:00 -->
### dc8e251a3814 · ruled-out · Webhook delivery / listener broken

Ruled out. el-gitea-listener 1/1 Running 33h, no restarts; logs show events at 15:22:31Z creating PipelineRuns the moment CI activity resumed; runs succeed (46s). Delivery path works. Operator notes concurrent local Gitea/Tekton disturbances; the gap pattern predates them (see root-cause).

<!-- fr:journal kind=hypothesis scope=debug id=257620618d82 created=2026-10-13T15:25:37+00:00 -->
### 257620618d82 · hypothesis · Rule window calibrated on a premise that no longer holds

Rule comment justifies [6h]/for:1h with 'max observed idle gap 0.5h -> 12x headroom' (measured 2026-09-13). Hypothesis: traffic is now bursty and idle gaps routinely exceed 6h, so the rule fires on quiet periods.

<!-- fr:journal kind=root-cause scope=debug id=53a8c87b6957 created=2026-10-13T15:25:41+00:00 -->
### 53a8c87b6957 · root-cause · Idle window [6h] is shorter than normal idle gaps (max 8.3h)

Confirmed. Exact gaps from 767 retained runs (10-10..10-13): 8.3h, 7.3h, 7.1h, 7.0h, 5.5h... four gaps >=6h in 3.4d. 30d hourly VictoriaMetrics series (09-14..10-13, includes four weekends): zero idle stretches >=5h until 10-07, five >=6h since, longest 7 empty hourly buckets (~8h). So the 0.5h premise was true when measured and has drifted; the rule fires on routine quiet periods, not an outage. No test pinned the window against measured gaps, so the drift was invisible.

<!-- fr:journal kind=finding scope=debug id=29ae938abb50 created=2026-10-13T15:29:12+00:00 state=fixed -->
### 29ae938abb50 · finding [fixed] · Idle window 6h -> 24h, pinned by a measured-gap test

alert-rules-cm.yaml: layer-25-idle-stoa-status-bridge [6h]->[24h] (query, relativeTimeRange A/B/C, summary, calibration comment); for:1h unchanged. Failing-first test test_the_idle_window_exceeds_the_measured_idle_gap_with_headroom (red: 6h < 2.5x8.3h; green after). 235 passed across alert-rule and gotcha guards. 30d backtest: longest idle stretch ~8h, so the new rule would not have fired once. Gotcha added (grafana.md + frank-gotchas.md). Trade-off: dead-webhook detection latency ~25h.

<!-- fr:journal kind=review scope=debug id=557fd8892c6d created=2026-10-13T15:29:33+00:00 -->
### 557fd8892c6d · review · Self-review of the 4-file diff (no independent reviewer)

Read the full diff myself; no subagent reviewer was dispatched (change is one rule window + one test + docs). Findings raised: none blocking. Checked: relativeTimeRange A/B/C all moved with the PromQL range (test asserts it); for:1h and noDataState untouched; github-pull-sync passes the new test unchanged at 4.6x; a controller restart during a quiet stretch still self-clears like before. Residual risk, stated in the PR: the 8.3h max rests on 3.4d of runs plus a 30d hourly series, and detection latency for a truly dead webhook is now ~25h. The operator reports concurrent local Gitea/Tekton disturbances; they were not separable from the gap data and did not change the conclusion.
