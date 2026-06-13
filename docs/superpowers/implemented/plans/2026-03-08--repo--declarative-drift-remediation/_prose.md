# Declarative Drift Remediation Implementation Plan

## Phase 1: Declarative Drift Remediation Implementation Plan

### Task 1: Fix `longhorn` Application CR — remove ad-hoc finalizers

- P1.T1.S1: Verify the current template only has the one correct finalizer

- P1.T1.S2: Confirm the file is correct as-is

- P1.T1.S3: Commit a no-op comment to document the finding

### Task 2: Fix `longhorn-extras` Application CR — `ignoreDifferences` and `prune`

- P1.T2.S1: Verify the current template

- P1.T2.S2: Verify `prune: false` is present

- P1.T2.S3: If either is missing, add them now

- P1.T2.S4: Commit

### Task 3: Fix `gpu-operator` Application CR — remove ad-hoc finalizers, add `prune: false`

- P1.T3.S1: Add `prune: false` to the gpu-operator template

- P1.T3.S2: Verify no extra finalizers are in the git file

- P1.T3.S3: Commit

### Task 4: Make Grafana VictoriaLogs datasource declarative

- P1.T4.S1: Create the provisioning ConfigMap

- P1.T4.S2: Mount the ConfigMap into Grafana via values

- P1.T4.S3: Add the ConfigMap to the victoria-metrics ArgoCD app

- P1.T4.S4: Commit

- P1.T4.S5: Push and verify ArgoCD picks up the new ConfigMap

- P1.T4.S6: Delete the live API-added datasource and verify provisioning takes over

### Task 5: Document the Grafana datasource migration as a manual operation

- P1.T5.S1: Add manual-operation block to this plan

- P1.T5.S2: Retroactively add manual-operation block to Backup plan

- P1.T5.S3: Commit

### Task 6: Create `docs/runbooks/manual-operations.yaml`

- P1.T6.S1: Create the runbooks directory and the YAML file

- P1.T6.S2: Commit

### Task 7: Create the `/sync-runbook` skill

- P1.T7.S1: Create the skill file

- P1.T7.S2: Commit

### Task 8: Update CLAUDE.md — add `/sync-runbook` to layer workflow and document the manual-op format

- P1.T8.S1: Add `/sync-runbook` to the Standard Layer Workflow section

- P1.T8.S2: Add a Manual Operations section to CLAUDE.md

- P1.T8.S3: Commit

### Task 9: Push and verify root app syncs clean

- P1.T9.S1: Push all commits

- P1.T9.S2: Sync root app and check status

- P1.T9.S3: Verify longhorn Application CR finalizers were cleaned up

- P1.T9.S4: Verify gpu-operator Application CR

- P1.T9.S5: Verify Grafana provisioning ConfigMap exists

- P1.T9.S6: Execute the Grafana datasource migration manual operation

- P1.T9.S7: Sync the runbook

- P1.T9.S8: Final commit if runbook status was updated
