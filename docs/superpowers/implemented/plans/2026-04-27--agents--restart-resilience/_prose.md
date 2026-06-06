# Agent Pod Restart Resilience — Implementation Plan (frank side)

## Phase 1: Deploy ArgoCD Notifications + Telegram template

### Task 1: Enable notifications in argocd Helm values

- P1.T1.S1: Edit `apps/argocd/values.yaml`

### Task 2: Create `apps/argocd-notifications/manifests/configmap.yaml`

- P1.T2.S1: Telegram service + triggers + templates

### Task 3: Create `apps/argocd-notifications/manifests/externalsecret.yaml`

- P1.T3.S1: Pull Telegram credentials from Infisical via ESO

### Task 4: Add Application CR to `apps/root/templates/argocd-notifications.yaml`

- P1.T4.S1: Wire it into the App-of-Apps

### Task 5: Push, sync, verify controller starts

- P1.T5.S1: Push the branch + open PR + merge

- P1.T5.S2: Sync and verify

- P1.T5.S3: Verify the secret resolves

### Task 6: Test with a benign trigger

- P1.T6.S1: Annotate any test app temporarily, force a sync, observe Telegram

## Phase 2: Image bump cutover

### Task 1: Confirm Phases 1-4 are merged in agent-images

- P2.T1.S1: Check agent-images main has all four PRs *(skipped — agent-images Phases 2-4 not yet merged; Phase 2 closed with blocker documented)*

### Task 2: Merge the accumulated bumper PR in frank

- P2.T2.S1: Identify the bump PR *(skipped — bump PRs closed; s6 image not yet available from agent-images)*

- P2.T2.S2: Merge the latest bump PR *(skipped — pending agent-images Phases 2-4)*

### Task 3: Observe the rollout

- P2.T3.S1: Watch ArgoCD sync + pod recreation *(skipped — s6 image cutover not yet executed)*

### Task 4: Re-spawn mosh + verify pod-side state

- P2.T4.S1: Cmd+Shift+2 in WezTerm *(skipped — s6 image cutover pending)*

- P2.T4.S2: Verify s6 + services *(skipped — s6 image cutover pending)*

### Task 5: Smoke test in-pod resilience

- P2.T5.S1: Kill supercronic, observe respawn *(skipped — current image uses tini+entrypoint.sh, not s6; pkill of supercronic would kill the container, not respawn it)*

- P2.T5.S2: Confirm no historical regressions *(skipped — pending s6 image cutover)*

## Phase 3: Drop preStop, add notification annotations

### Task 1: Remove `lifecycle.preStop` from deployment.yaml

- P3.T1.S1: Edit `apps/secure-agent-pod/manifests/deployment.yaml`

### Task 2: Add notification subscription annotations to the Application CR

- P3.T2.S1: Edit `apps/root/templates/secure-agent-pod.yaml`

### Task 3: Open PR + merge

- P3.T3.S1: Open PR `feat(agents): drop preStop, subscribe to ArgoCD bump alerts`

- P3.T3.S2: Merge after CI green *(merged via PR #148 on 2026-04-29)*

### Task 4: Re-spawn mosh + verify Telegram fired

- P3.T4.S1: Cmd+Shift+2 *(N/A — pod is still on the pre-s6 image; preStop removal didn't trigger pod recreate by itself, since cont-finish.d isn't there yet either. Verified separately in Phase 4 Task 4 via test-trigger annotation)*

- P3.T4.S2: Confirm Telegram alert arrived for this sync *(verified separately — see Phase 4 Task 4)*

## Phase 4: End-to-end verification

### Task 1: Layout persistence across an image bump

- P4.T1.S1: Set up a test layout *(deferred — pending s6 image)*

- P4.T1.S2: Wait 6 minutes *(deferred — pending s6 image)*

- P4.T1.S3: Trigger a pod restart *(deferred — pending s6 image)*

- P4.T1.S4: Re-spawn mosh, observe restoration *(deferred — pending s6 image)*

### Task 2: Crashloop bail

- P4.T2.S1: Break supercronic and observe bail-out *(deferred — pending s6 image)*

- P4.T2.S2: Restore supercronic and recover *(deferred — pending s6 image)*

### Task 3: Independent service deaths

- P4.T3.S1: Kill sshd, observe readinessProbe failure + recovery *(deferred — pending s6 image)*

### Task 4: Bump alert end-to-end

- P4.T4.S1: Trigger a sync (real or simulated) *(triggered via `kubectl patch app secure-agent-pod` with operation field; sync ran at 11:02:11Z and 11:03:51Z)*

- P4.T4.S2: Confirm Telegram alert content matches the template *(notification engine logs show successful delivery to recipient `{telegram }`; controller log line `Notification ... already sent` confirms dedup-after-success)*

### Task 5: Document learned gotchas

- P4.T5.S1: For any quirk encountered (s6 non-root edge cases, tmux save timing, ESO refresh latency), append to `.claude/rules/frank-gotchas.md` *(appended ArgoCD Notifications named-webhook annotation gotcha — the `.webhook: <name>` vs `.<name>: ""` confusion that silently broke Phase 3 deliveries)*

## Phase 5: Post-deploy documentation

### Task 1: Update operating post

- P5.T1.S1: Add an "Architecture: s6-overlay" section to `blog/content/docs/operating/14-secure-agent-pod/index.md`

- P5.T1.S2: Update the "Persistent shells with mosh + tmux" section

- P5.T1.S3: Update the "What 'Healthy' Looks Like" process list

### Task 2: Update building post

- P5.T2.S1: Update the "Architecture" section in `blog/content/docs/building/21-secure-agent-pod/index.md`

- P5.T2.S2: Update the "Process Supervision" section

### Task 3: Update README

- P5.T3.S1: Update Technology Stack row for Secure Agent Pod

- P5.T3.S2: Add ArgoCD Notifications row to Technology Stack

### Task 4: Update gotchas

- P5.T4.S1: Add to `.claude/rules/frank-gotchas.md`

### Task 5: Set plan status

- P5.T5.S1: Edit ` Status:**` to `Deployed` in this file AND the agent-images-side plan**

### Task 6: Sync runbook

- P5.T6.S1: Run `/sync-runbook`
