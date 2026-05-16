# vk-local OOMKill Remediation — Implementation Plan

## Phase 1: Verify Option A in production

### Task 1: Confirm live limit and zero post-bump OOMKills

- P1.T1.S1: Verify live container spec

- P1.T1.S2: Read restart count and last-termination reason

- P1.T1.S3: Inspect kubelet events for OOM since merge

- P1.T1.S4: Capture pre-cadvisor RSS baseline

### Task 2: Document the verification

- P1.T2.S1: Add an entry to the `Verification Log (Phase 1)` section at the bottom of this plan with: timestamp, live limit value, current restart count, OOM events found (or none), and the `kubectl top` reading. This becomes the input to Phase 5's soak comparison.

## Phase 2: Fix cadvisor metric pipeline for 5 nodes

### Task 1: Investigate root cause

- P2.T1.S1: Read vmagent scrape stats for cadvisor targets

- P2.T1.S2: Test the relabel-rule hypothesis (case 1)

- P2.T1.S3: Test cardinality / disk-usage limits (case 2)

- P2.T1.S4: Test cadvisor endpoint directly on an affected node

### Task 2: Apply the fix

- P2.T2.S1: Apply the case-specific fix. One of:

- P2.T2.S2: Verify. Wait 5 minutes, then run:

### Task 3: 24h soak

- P2.T3.S1: After 24 h, re-query the count. Series count must be non-zero for all 7 nodes continuously. Document the result in this plan's Deployment Notes section.

### Task 4: Fallback if root cause cannot be isolated

- P2.T4.S1: *(skipped — root cause was isolated in Task 1, see Deployment Deviations below).* If after one working day the cause is still unknown, file a tracking issue in `derio-net/frank` titled `obs: cadvisor scrape data gap on amd64 nodes` with the investigation log so far. Mark Phase 2 as `Closed (deferred)` in this plan and continue with Phase 3 — the housekeeping work does not depend on Phase 2's outcome, only Phase 5's evaluation does.

## Phase 3: Housekeeping — npm cache + worktree prune

### Task 1: Decide cron host

- P3.T1.S1: Inspect `kali`'s supercronic crontab and the PVC mount layout. The default placement is `kali`'s supercronic crontab, since it already runs scheduled work and shares the agent-home PVC with `vk-local`. Confirm by reading the kali Dockerfile / `crontab` content in agent-images.

### Task 2: Implement the crons (agent-images repo)

- P3.T2.S1: npm cache prune cron — shipped as [`kali/scripts/npm-cache-prune.sh`](https://github.com/derio-net/agent-images/blob/agents/vk-local-housekeeping-crons/kali/scripts/npm-cache-prune.sh). Crontab line: `0 4 * * 0 /opt/scripts/npm-cache-prune.sh >> __AGENT_HOME__/.willikins-agent/npm-cache-prune.log 2>&1`.

- P3.T2.S2: Worktree prune cron — shipped as [`kali/scripts/worktree-prune.sh`](https://github.com/derio-net/agent-images/blob/agents/vk-local-housekeeping-crons/kali/scripts/worktree-prune.sh). Iterates `$AGENT_HOME/repos/*/.git` (the canonical repo root on Frank — vibe-kanban worktrees under `/var/tmp/vibe-kanban/worktrees/` link back via gitdir files). Crontab line: `30 4 * * * /opt/scripts/worktree-prune.sh >> __AGENT_HOME__/.willikins-agent/worktree-prune.log 2>&1`.

- P3.T2.S3: Open PR in agent-images — [`derio-net/agent-images#34`](https://github.com/derio-net/agent-images/pull/34).

### Task 3: Image-bumper picks up the new SHA

- P3.T3.S1: Once Task 2's PR merges in agent-images, the existing image-bumper workflow opens a PR in this repo updating the image SHA in `apps/secure-agent-pod/manifests/deployment.yaml`. Merge that PR. ArgoCD syncs. The kali container restarts; supercronic loads the new crontab automatically (no extra restart needed — supercronic auto-reloads on file change, see `frank-gotchas.md`).

### Task 4: Verify housekeeping is running

- P3.T4.S1: After the first weekly window passes (or trigger manually inside the pod for verification: `kubectl -n secure-agent-pod exec -c kali deploy/secure-agent-pod -- supercronic -test /home/claude/.crontab`), inspect the log files:

## Phase 4: Option B1 — `max_concurrent_executions` cap

### Task 1: Add the cap to the vibe-kanban fork (agent-images repo)

- P4.T1.S1: Bump config schema v8 → v9

- P4.T1.S2: Add env-var fallback

- P4.T1.S3: Wrap executor spawn in a counting semaphore

- P4.T1.S4: Add structured queue logs

- P4.T1.S5: Add `/metrics` endpoint

- P4.T1.S6: Open PR in agent-images. Tests must cover: missing field / `null` (treated as `None`, no cap, current behavior), `cap=1` (serialization round-trip), and `cap=N` with N+1 concurrent spawns (queueing — the (N+1)th must wait until one permit is released, not error). `cap=0` should be rejected at config-load with a clear error (degenerate "never spawn anything"). Reviewer should verify the v8→v9 migration works on a recorded v8 config.

### Task 2: Surface the env var on Frank

- P4.T2.S1: Edit `apps/secure-agent-pod/manifests/deployment.yaml`

- P4.T2.S2: Add a `VMPodScrape` for the new endpoint

- P4.T2.S3: Verify metrics arrive

- P4.T2.S4: Add a Grafana panel for queue depth

## Phase 5: Soak + dial-back assessment

### Task 1: Collect soak data

- P5.T1.S1: Daily checks

- P5.T1.S2: Record findings

### Task 2: Decision and follow-up PR

- P5.T2.S1: After 14 days, choose one outcome and document the rationale:

  **Outcome: (b) Dial back to 3 Gi** — `vk-local limits.memory: 8Gi → 3Gi` (PR #264).

---

## Soak Log (Phase 5)

**Soak window:** 2026-05-03 → 2026-05-16 (14 days from Phase 4 Task 2 merge at `c88b755`).

Auto-filled by `scripts/phase5-soak-daily.sh` via supercronic (`0 8 * * *` UTC, kali sibling container).

| Day | Date (UTC) | `restartCount` | OOMKills since soak start | p99 working-set (24 h) | Peak `vibekanban_queued_executions` (24 h) | Notes |
|-----|------------|----------------|---------------------------|------------------------|---------------------------------------------|-------|
| 1 | 2026-05-03 | 0 | 0 | ~2.35 GiB (cadvisor) / ~2.53 GiB (resource) | 0 | Soak start. Phase 4 image `8af0d080` live, `VK_MAX_CONCURRENT_EXECUTIONS=4` confirmed. |
| 2 | 2026-05-04 | 0 | 0 | 2.95 GiB | 3 | pod=secure-agent-pod-c976f9946-rqdqc |
| 3 | 2026-05-05 | 0 | 0 | 0.74 GiB | 0 | pod=secure-agent-pod-c976f9946-rqdqc |
| 4 | 2026-05-06 | 0 | 0 | 0.97 GiB | 0 | pod=secure-agent-pod-c976f9946-rqdqc |
| 5 | 2026-05-07 | 0 | 0 | 1.05 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 6 | 2026-05-08 | 0 | 0 | 0.24 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 7 | 2026-05-09 | 0 | 0 | 0.38 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 8 | 2026-05-10 | 0 | 0 | 1.11 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 9 | 2026-05-11 | 0 | 0 | 0.99 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 10 | 2026-05-12 | 0 | 0 | 1.56 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 11 | 2026-05-13 | 0 | 0 | 1.73 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 12 | 2026-05-14 | 0 | 0 | 1.90 GiB | 0 | pod=secure-agent-pod-5c46cb8f7b-9765c |
| 13 | 2026-05-15 | 0 | 0 | 1.66 GiB | 0 | pod=secure-agent-pod-fc9585b8b-jn2rx (pod replaced — node eviction, not OOM) |
| 14 | 2026-05-16 | 0 | 0 | 0.19 GiB | 0 | pod=secure-agent-pod-548744b988-dngfj (pod replaced again) |

**Decision rationale:** 14 days, zero OOMKills, zero container restarts. p99 RSS peaked at 2.95 GiB on Day 2 (the only day with queue depth > 0). All other days 0.19–1.90 GiB. The 8 Gi limit was a conservative post-OOM placeholder; 3 Gi covers the p99 peak with ~5 % headroom. `vk-local limits.memory` dialled back to 3 Gi in PR #264.

## Phase 6: File tracking issues for B2, B3, R

### Task 1: File B2 tracking issue

- P6.T1.S1: Open issue in `derio-net/frank` titled `agents: B2 — delegate vk-local child spawn to kali sibling cgroup`.

### Task 2: File B3 tracking issue

- P6.T2.S1: Open issue in `derio-net/frank` titled `agents: B3 — per-task Kubernetes Jobs for vibe-kanban executions`.

### Task 3: File the R (regression cross-check) tracking issue

- P6.T3.S1: Open issue in `derio-net/frank` titled `agents: investigate 9× OOM-rate escalation on vibe-kanban image dc414b4`.

## Phase 7: Post-Deploy Checklist
