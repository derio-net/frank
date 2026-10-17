<!-- fr:journal-schema=2 -->
# Journal: 2026-10-12-ci-mirror-resilience

<!-- fr:journal kind=repro scope=debug id=a53b793ef57d created=2026-10-12T15:37:43+00:00 -->
### a53b793ef57d · repro · agentic-stoa commits got no gitea-actions statuses 2026-10-11 21:22Z to 2026-10-12 12:39Z

second-brain PR #124 head ab45e07 and main 59b0437/6d3672d/6673521/7288a3d/d1bcaf1 got no gitea-actions/* statuses. The runner was healthy and picked up later commits (752bdfe 12:40Z, b0ec508 15:01Z). Repro: list github-pull-sync PipelineRuns in the window. Every one is PipelineRunTimeout with its step never started; GitHub webhook deliveries at 06:49-06:51Z show HTTP 502.

<!-- fr:journal kind=ruled-out scope=debug id=c3c903885b99 created=2026-10-12T15:37:46+00:00 -->
### c3c903885b99 · ruled-out · Gitea Actions runner and status write-back are not the cause

act-runner was Running and fetched tasks for other repos throughout. stoa-status-bridge runs all Succeeded. Gitea never had the commits, so no run was ever created.

<!-- fr:journal kind=ruled-out scope=debug id=54cebf2ac425 created=2026-10-12T15:37:49+00:00 -->
### 54cebf2ac425 · ruled-out · Gitea repo corruption is unrelated

13 empty object files exist, but only in derio-homelab/kid-laptops, all dated 2026-08-01 10:42Z. They predate this outage and break kid-laptops fetches only. Filed separately.

<!-- fr:journal kind=root-cause scope=debug id=cc3ca5e2c1eb created=2026-10-12T15:37:51+00:00 -->
### cc3ca5e2c1eb · root-cause · Mirror sync stalled on a missing hdd disk tag; listeners pinned to a draining node; no alert or repair path

(1) #836 merged 2026-10-11 21:19:47Z, ahead of its pre-merge manual ops. It moved Tekton workspaces to longhorn-hdd while no Longhorn disk carried the hdd tag, so every sync PVC stayed Pending until the 1h timeout (first at 21:22Z, last at 04:21Z). (2) el-github-listener and el-gitea-listener are single replicas pinned to pc-1, so the drain at 06:49-06:51Z 502'd three pushes, which GitHub never retries. (3) layer-25-pipeline-failing requires zero successes in 24h and so stayed silent (backtested at 23:30Z: empty), and the mirror has no reconcile path.

<!-- fr:journal kind=finding scope=debug id=715cefb7dcba created=2026-10-12T16:11:16+00:00 state=fixed -->
### 715cefb7dcba · finding [fixed] · Fix: listeners survive a drain, mirror-reconcile repairs drift, three alerts see the outage

Listeners: 2 replicas, hostname spread, amd64, PDBs (live nodeSelector owned only by argocd-controller Apply, so removal propagates). mirror-reconcile CronJob: */15, --force-with-lease, emptyDir only, all 11 main-sync repos and all 8 sync-pr repos. Alerts layer-25-mirror-sync-failing (backtest: 0 FP over 28d, fires 22:25Z-07:05Z), -ci-pvc-pending, -mirror-reconcile-stale. Failing-first tests: test_ci_mirror_resilience.py (16 red before the fix), test_mirror_reconcile_behaviour.py (host + alpine/git busybox). First live run predicted read-only: hermes-brain main, cnc-fr sync-pr-128 and sync-pr-130, all still-dropped refs from this outage.

<!-- fr:journal kind=review scope=debug id=9ffdddfc2cb1 created=2026-10-12T16:11:18+00:00 -->
### 9ffdddfc2cb1 · review · Independent review: 0 critical, 3 important, 8 minor; all in-scope fixed, 1 deferred

Important: (1) live nodeSelector might be owned by a non-SSA manager. Refuted: only argocd-controller Apply owns it; post-merge 2-node check added to the test plan. (2) cnc/hum/content-factory/stoa-blog PR mirrors were uncovered. Fixed: guard now derives every sync-pr trigger, and the docs say Tekton CI bodies are not re-run. (3) behaviour test not on busybox; plan.py main() untested. Fixed: alpine/git:2.47.2 variant plus main() and unreadable-repo tests. Minor fixed: PR grace on commit time, per-repo clone cleanup and 900s deadline, alert runbook wording, stale alert ~1h, pc-1 sync-pipeline SPOF documented, GIT_TERMINAL_PROMPT=0, DRY_RUN switch. Deferred: (9) alert on successful repairs (follow-up issue). Not changed: python:3.13-slim tag, which matches the repo convention.

<!-- fr:journal kind=finding scope=debug id=e7beea1d06b7 created=2026-10-13T18:55:13+00:00 state=fixed -->
### e7beea1d06b7 · finding [fixed] · Merge with #855: alerts folded into main's rather than duplicated

#855 shipped layer-25-ci-workspace-pvc-pending and layer-25-pipelinerun-timeout for the same outage. Dropped this branch's layer-25-ci-pvc-pending. Narrowed layer-25-mirror-sync-failing to fast failures, inside the le=1800 bucket and so the complement of the timeout rule. Backtest: quiet on the 10-11 timeouts, fires from 2026-10-13 17:55Z on derio-homelab-pull-sync, where Gitea rejects every kid-laptops push since 16:50Z (#849, escalation noted there).
