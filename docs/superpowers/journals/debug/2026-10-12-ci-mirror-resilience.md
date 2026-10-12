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
