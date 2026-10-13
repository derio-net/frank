# Journal: 2026-10-13-stoa-status-bridge-idle

<!-- fr:journal kind=repro scope=debug id=1f5ac1bd0872 created=2026-10-13T15:25:28+00:00 -->
### 1f5ac1bd0872 · repro · Layer 25 Pipeline Idle stoa-status-bridge fires: 0 runs in 6h

Alert layer-25-idle-stoa-status-bridge (warning, frank-ops#25) fired 2026-10-13. Repro: kubectl -n tekton-pipelines get pipelinerun -l tekton.dev/pipeline=stoa-status-bridge; exact inter-run gaps from creationTimestamp. Last run before the gap 07:04Z, next 15:22Z (8.3h). Listener pod 33h old, 0 restarts; first event after the gap created a run immediately.
