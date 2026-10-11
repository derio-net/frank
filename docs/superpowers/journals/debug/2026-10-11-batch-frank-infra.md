# Journal: 2026-10-11-batch-frank-infra

<!-- fr:journal kind=repro scope=debug id=e0be643d4d4c created=2026-10-11T21:38:00+00:00 -->
### e0be643d4d4c · repro · All three members still present on origin/main c6ab533b

- #821: apps/ovms-retrieval/manifests/pool-watchdog.yaml still CRITICAL_PERCENT=53 against memory.current (no file-LRU subtraction).
- #774: clusters/hop/apps/headscale/manifests/configmap.yaml autoApprovers.routes lists only 192.168.10/50/55; exitNode only tag:subnet-router.
- #827: #823 (cb112fa9) is merged in git; per the issue the live Deployment carries a stale 2026-05-17 kubectl-apply managedFields entry that blocks the sync. Live cluster state, not re-checked yet.

<!-- fr:journal kind=hypothesis scope=debug id=92fbda2702a7 created=2026-10-11T21:38:06+00:00 -->
### 92fbda2702a7 · hypothesis · Batch premise (one shared root cause) does not hold: three independent causes

#827 = SSA field-ownership residue from a hand apply (live metadata, fix is a managedFields deletion plus a gotcha). #821 = the watchdog numerator counts reclaimable page cache (manifest/script change). #774 = an incomplete Headscale autoApprovers policy on Hop (ConfigMap change, coordinated with ice#3). No shared mechanism, no shared file, and two of them are on different clusters. Per the batch rule, stop and ask before fixing any.

<!-- fr:journal kind=finding scope=debug id=310e848709a9 created=2026-10-11T21:39:14+00:00 state=open -->
### 310e848709a9 · finding [open] · Operator decision: one PR, three independent fixes

Operator chose to keep one draft PR on fix/batch-frank-infra with a separate commit and failing test per member. #827's live managedFields deletion stays an operator manual-op; the PR carries the gotcha and a guard.
