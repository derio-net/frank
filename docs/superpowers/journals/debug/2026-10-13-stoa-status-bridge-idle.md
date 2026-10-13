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
