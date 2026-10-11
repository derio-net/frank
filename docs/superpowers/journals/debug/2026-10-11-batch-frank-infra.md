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

<!-- fr:journal kind=root-cause scope=debug id=673a390a5229 created=2026-10-11T21:44:15+00:00 -->
### 673a390a5229 · root-cause · #821: Rule 1 counted reclaimable file-LRU page cache in memory.current

memory.current includes active_file+inactive_file, which grow with pod uptime (1.40 GiB at 12 days) and are reclaimed before OOM. The 53% line was calibrated on a fresh pod (LRUs=0), so the trigger drifted tighter: 7.74 GiB incident peak + 12-day cache = 9.58 GiB > 8.48 GiB line.

<!-- fr:journal kind=finding scope=debug id=962fb3db1696 created=2026-10-11T21:44:25+00:00 state=fixed -->
### 962fb3db1696 · finding [fixed] · #821 fixed: Rule 1 numerator = memory.current - active_file - inactive_file

Commit 79fa4015. Failing-first tests: test_the_exec_reads_both_file_lrus_from_memory_stat, test_rule_one_does_not_count_reclaimable_page_cache (incident peak on a 12-day pod: restarted before, busy/no restart after), test_rule_one_still_fires_when_the_unreclaimable_part_is_critical, test_the_restart_line_reports_the_figure_rule_one_compared. CRITICAL_PERCENT stays 53. Targeted run: test_ovms_pool_watchdog + test_ovms_retrieval_manifests, 73 passed.
