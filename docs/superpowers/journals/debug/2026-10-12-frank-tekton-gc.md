# Journal: 2026-10-12-frank-tekton-gc

<!-- fr:journal kind=repro scope=debug id=5090888fe413 created=2026-10-11T23:56:41+00:00 -->
### 5090888fe413 · repro · kid-laptops-ci PipelineRuns are never GC'd (frank#791)

Live 2026-10-12: `kubectl get pipelinerun -A` = 1175 in tekton-pipelines (swept daily) and 13 in kid-laptops-ci, plus 12 PVCs there. The kid-laptops-ci runs finished 2026-07-27 to 2026-08-01, so they are 70+ days past the 3-day TTL. `apps/tekton/manifests/pipelinerun-ttl-gc.yaml` hard-codes `-n tekton-pipelines` in all three kubectl calls, and its Role/RoleBinding exist only in tekton-pipelines.
