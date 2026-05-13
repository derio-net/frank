# Stoa Org Gitea-Primary Implementation Plan

> **SUPERSEDED 2026-05-13.** Direction inverted to GitHub-primary. Active work moved to sibling rework plan: `docs/superpowers/plans/2026-05-05--cicd--stoa-gitea-primary-rework-1/`. See spec sections `## Architectural Constraint: Paperclip AI requires GitHub-primary` and `## Direction Inversion (2026-05-13)` in `docs/superpowers/specs/2026-05-04--cicd--stoa-gitea-primary-design.md` for context. Phases 0–2 of this plan completed and produced substrate (Gitea org, stoa-bot, per-repo CI Pipeline manifests, gitea-listener Triggers, ESO/PAT Secret) reused by the rework. Phase 3 partially executed (mirror-clone of `hum`, `content-factory`, `stoa-blog` — that initial Gitea-side state is now the **initial state of Gitea as a replica** under the active design). Remaining Phase 3 + Phase 4 steps are marked `-` (skipped, with note) below; this plan's status will be `Complete` once that's done.

## Phase 0: Prerequisites — secrets, org, bot account

### Task 1: Push outstanding local WIP to GitHub

- P0.T1.S1: Inspect each local clone for uncommitted work

- P0.T1.S2: Push every local branch to GitHub

- P0.T1.S3: Verify GitHub has every local ref

### Task 2: Create agentic-stoa Gitea org and stoa-bot service account

- P0.T2.S1: Create the org via Gitea UI (per manual-op block above)

- P0.T2.S2: Create stoa-bot user

### Task 3: Create GitHub fine-grained PAT

- P0.T3.S1: Generate the PAT in GitHub UI (per manual-op block)

- P0.T3.S2: Verify PAT works

### Task 4: Verify all secrets are accessible

- P0.T4.S1: Confirm Infisical has both new keys under /agentic-stoa

- P0.T4.S2: Confirm existing layer-19 secrets still healthy

## Phase 1: Shared github-backup-sync pipeline

### Task 1: ExternalSecret for STOA_GITHUB_MIRROR_TOKEN

- P1.T1.S1: Confirm the ClusterSecretStore name

- P1.T1.S2: Create the ExternalSecret manifest

### Task 2: github-backup-sync Pipeline manifest

- P1.T2.S1: Create the Pipeline manifest

### Task 3: Add backup-sync Trigger and TriggerTemplate to gitea-listener

- P1.T3.S1: Read the current EventListener config

- P1.T3.S2: Append the new TriggerTemplate

- P1.T3.S3: Add the new Trigger inside the EventListener spec.triggers list

### Task 4: Commit, sync, and verify backup pipeline is healthy

- P1.T4.S1: Commit changes

- P1.T4.S2: Wait for ArgoCD sync and verify resources

- P1.T4.S3: Confirm EventListener picked up the new trigger

## Phase 2: Per-repo CI pipelines

### Task 1: hum-ci Pipeline

- P2.T1.S1: Create the Pipeline manifest

### Task 2: content-factory-ci Pipeline

- P2.T2.S1: Create the Pipeline manifest

### Task 3: Per-repo CI TriggerTemplates

- P2.T3.S1: Append two new TriggerTemplates to eventlistener.yaml

### Task 4: Per-repo CI Triggers

- P2.T4.S1: Append the two CI Triggers inside spec.triggers

### Task 5: Scope existing gitea-push trigger to non-stoa repos

- P2.T5.S1: Add agentic-stoa exclusion to existing trigger filter

### Task 6: Commit, sync, and verify

- P2.T6.S1: Commit changes

- P2.T6.S2: Verify resources synced

- P2.T6.S3: Confirm EventListener pod healthy after re-render

## Phase 3: Migration of hum and content-factory

### Task 1: Create empty Gitea repos

- P3.T1.S1: Create agentic-stoa/hum on Gitea

- P3.T1.S2: Create agentic-stoa/content-factory on Gitea

- P3.T1.S3: Verify both empty repos exist

### Task 2: Mirror clone GitHub → Gitea

- P3.T2.S1: Mirror-clone hum

- P3.T2.S2: Mirror-clone content-factory

### Task 3: Add Gitea webhook (per repo)

- P3.T3.S1: Add webhook on hum (per manual-op block)

- P3.T3.S2: Add webhook on content-factory (per manual-op block)

### Task 4: Smoke test CI pipelines

- P3.T4.S1: Push a no-op feature-branch commit to hum

- P3.T4.S2: Verify hum-ci PipelineRun fired

- P3.T4.S3: Verify Gitea PR view shows commit status

- P3.T4.S4: Repeat Steps 1–3 for content-factory

### Task 5: Smoke test backup-sync

- P3.T5.S1: Merge the test PR on hum (Gitea UI)

- P3.T5.S2: Verify backup PipelineRun fired and pushed to GitHub

- P3.T5.S3: Confirm a non-main push does NOT trigger backup-sync

- P3.T5.S4: Repeat Steps 1–3 for content-factory

### Task 6: Prune non-main branches from GitHub

- P3.T6.S1: Authenticate gh CLI as operator

- P3.T6.S2: Delete non-main branches on hum

- P3.T6.S3: Delete non-main branches on content-factory

- P3.T6.S4: Verify tags retained

### Task 7: Enable Gitea branch protection on main

- P3.T7.S1: Enable branch protection on hum (per manual-op block)

- P3.T7.S2: Enable branch protection on content-factory (per manual-op block)

- P3.T7.S3: Verify protection blocks direct push as stoa-bot

### Task 8: Update local clone remotes

- P3.T8.S1: Update hum clone remote

- P3.T8.S2: Update content-factory clone remote

- P3.T8.S3: Final sanity push

## Phase 4: Post-Deploy Checklist
