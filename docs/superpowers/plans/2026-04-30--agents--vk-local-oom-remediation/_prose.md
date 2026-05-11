# vk-local OOMKill Remediation — Implementation Plan

## Phase 1: Verify Option A in production

### Task 1: Confirm live limit and zero post-bump OOMKills

- P1.T1.S1: Verify live container spec

- P1.T1.S2: Read restart count and last-termination reason

- P1.T1.S3: Inspect kubelet events for OOM since merge

- P1.T1.S4: Capture pre-cadvisor RSS baseline

### Task 2: Document the verification

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

### Task 4: Fallback if root cause cannot be isolated

## Phase 3: Housekeeping — npm cache + worktree prune

### Task 1: Decide cron host

### Task 2: Implement the crons (agent-images repo)

- P3.T2.S1: npm cache prune cron — shipped as [`kali/scripts/npm-cache-prune.sh`](https://github.com/derio-net/agent-images/blob/agents/vk-local-housekeeping-crons/kali/scripts/npm-cache-prune.sh). Crontab line: `0 4 * * 0 /opt/scripts/npm-cache-prune.sh >> __AGENT_HOME__/.willikins-agent/npm-cache-prune.log 2>&1`.

- P3.T2.S2: Worktree prune cron — shipped as [`kali/scripts/worktree-prune.sh`](https://github.com/derio-net/agent-images/blob/agents/vk-local-housekeeping-crons/kali/scripts/worktree-prune.sh). Iterates `$AGENT_HOME/repos/*/.git` (the canonical repo root on Frank — vibe-kanban worktrees under `/var/tmp/vibe-kanban/worktrees/` link back via gitdir files). Crontab line: `30 4 * * * /opt/scripts/worktree-prune.sh >> __AGENT_HOME__/.willikins-agent/worktree-prune.log 2>&1`.

- P3.T2.S3: Open PR in agent-images — [`derio-net/agent-images#34`](https://github.com/derio-net/agent-images/pull/34).

### Task 3: Image-bumper picks up the new SHA

### Task 4: Verify housekeeping is running

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

## Phase 6: File tracking issues for B2, B3, R

### Task 1: File B2 tracking issue

### Task 2: File B3 tracking issue

### Task 3: File the R (regression cross-check) tracking issue

## Phase 7: Post-Deploy Checklist
