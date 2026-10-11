# Journal: 2026-10-11-batch-frank-infra

<!-- fr:journal kind=repro scope=debug id=e0be643d4d4c created=2026-10-11T21:38:00+00:00 -->
### e0be643d4d4c · repro · All three members still present on origin/main c6ab533b

- #821: apps/ovms-retrieval/manifests/pool-watchdog.yaml still CRITICAL_PERCENT=53 against memory.current (no file-LRU subtraction).
- #774: clusters/hop/apps/headscale/manifests/configmap.yaml autoApprovers.routes lists only 192.168.10/50/55; exitNode only tag:subnet-router.
- #827: #823 (cb112fa9) is merged in git; per the issue the live Deployment carries a stale 2026-05-17 kubectl-apply managedFields entry that blocks the sync. Live cluster state, not re-checked yet.
