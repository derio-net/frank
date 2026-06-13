# Secure Agent Pod — tmux + mosh Implementation Plan

## Phase 1: Image — install tmux + mosh

### Task 1: Add packages to kali Dockerfile

- P1.T1.S1: Edit `kali/Dockerfile` apt block in agent-images repo

- P1.T1.S2: Commit + push to main

## Phase 2: Frank — mosh UDP Service + container ports

### Task 1: Author the new LoadBalancer Service

- P2.T1.S1: Create `apps/secure-agent-pod/manifests/service-mosh.yaml`

### Task 2: Add UDP containerPorts to the kali container

- P2.T2.S1: Append UDP ports to `apps/secure-agent-pod/manifests/deployment.yaml`

### Task 3: Land the manifests on `main`

- P2.T3.S1: Open a PR for the manifest changes *(PR #125)*

- P2.T3.S2: Operator merges both PRs *(#124 → a1a21b1, #125 → 88a4de7)*

## Phase 3: Verify

### Task 1: Confirm tools are present

- P3.T1.S1: `kubectl exec` checks *(tmux 3.6, mosh 1.4.0, LANG/LC_ALL=C.UTF-8)*

### Task 2: Confirm Cilium L2 LB advertises mosh IP

- P3.T2.S1: Service status *(EXTERNAL-IP=192.168.55.219, 4×UDP ports allocated)*

### Task 3: End-to-end mosh from a client

- P3.T3.S1: Connect from a host on the lab LAN

## Phase 4: Post-deploy documentation

### Task 1: Update operating blog post

- P4.T1.S1: Add a "Persistent shells with mosh + tmux" section to `blog/content/docs/operating/14-secure-agent-pod/index.md`

### Task 2: Update building blog post (passing mention)

- P4.T2.S1: One-line correction in `blog/content/docs/building/21-secure-agent-pod/index.md`

### Task 3: Update README service table

- P4.T3.S1: Run `/update-readme`

### Task 4: Sync runbook (only if needed)

- P4.T4.S1: Run `/sync-runbook`

### Task 5: Update gotchas (if Cilium L2 UDP turned out to be quirky)

- P4.T5.S1: Append to `.claude/rules/frank-gotchas.md` if applicable <!-- skipped — Cilium L2 UDP worked first try; all 10 documented failure modes were client-side (ssh/mosh/zsh/wezterm/tmux), none cluster-side -->

### Task 6: Set plan status

- P4.T6.S1: Edit ` Status:**` to `Deployed`**

## Phase 5: Post-deploy tuning — 16 ports + 1h mosh timeout

### Task 1: Expand the Service to 16 ports

- P5.T1.S1: Edit `apps/secure-agent-pod/manifests/service-mosh.yaml`

### Task 2: Add timeout env + matching containerPorts

- P5.T2.S1: Edit `apps/secure-agent-pod/manifests/deployment.yaml`

### Task 3: Land + roll

- P5.T3.S1: Open PR `feat(agents): mosh tuning — 16 ports + 1h timeout`

- P5.T3.S2: Operator merges; ArgoCD syncs; pod recreates (env-var change forces a Recreate; expected ~30-60s of unavailability)

### Task 4: Re-verify

- P5.T4.S1: Confirm new pod has the env var

- P5.T4.S2: Confirm Service has 16 UDP ports
