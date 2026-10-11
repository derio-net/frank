# Journal: 2026-10-12-frank-tekton-gc

<!-- fr:journal kind=repro scope=debug id=5090888fe413 created=2026-10-11T23:56:41+00:00 -->
### 5090888fe413 · repro · kid-laptops-ci PipelineRuns are never GC'd (frank#791)

Live 2026-10-12: `kubectl get pipelinerun -A` = 1175 in tekton-pipelines (swept daily) and 13 in kid-laptops-ci, plus 12 PVCs there. The kid-laptops-ci runs finished 2026-07-27 to 2026-08-01, so they are 70+ days past the 3-day TTL. `apps/tekton/manifests/pipelinerun-ttl-gc.yaml` hard-codes `-n tekton-pipelines` in all three kubectl calls, and its Role/RoleBinding exist only in tekton-pipelines.

<!-- fr:journal kind=ruled-out scope=debug id=ce8c61bc930a created=2026-10-11T23:56:43+00:00 -->
### ce8c61bc930a · ruled-out · frank#792 no-op bridge churn is already fixed at the source

Hypothesis: the gitea-status-bridge trigger still forwards a status for every 30-minute pins-update poll, about 48 runs/day. Ruled out by live measurement (991 retained stoa-status-bridge PipelineRuns, 2026-10-08 to 10-11). `pins-update / pins (push)` now produces 0-2 runs/day: one pending and one success per daily 04:17Z run, all Succeeded. agentic-stoa/cnc-fr#97 (closed 2026-10-07) moved the poll off its 30-min status-emitting cadence. Every remaining bridge run is a real CI job status (pending plus final per job), so a Frank-side CEL filter would only drop real statuses. That is the hazard #792 itself warned about. No Frank change; #792 closes with this evidence.

<!-- fr:journal kind=root-cause scope=debug id=ef1225a712a6 created=2026-10-11T23:56:45+00:00 -->
### ef1225a712a6 · root-cause · GC namespace is hard-coded; no RBAC outside tekton-pipelines

The GC sweeps one literal namespace. kid-laptops-ci was added later (2026-07-26, kid-laptops CI) as a second PipelineRun target via its TriggerTemplate (`apps/tekton/triggers/kid-laptops-ci.yaml` resourcetemplate `namespace: kid-laptops-ci`). Nothing tied the GC namespace set to the set of namespaces git creates PipelineRuns in. Consequences: unbounded accumulation, leaked longhorn-cicd workspace PVCs (ownerRef cascade never fires), and Longhorn instance-manager PDBs pinned so node drains stall (#791 comment, #762 roll).
