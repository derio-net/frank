# Declarative Drift Remediation Implementation Plan

## Phase 1: Declarative Drift Remediation Implementation Plan

### Task 1: Fix `longhorn` Application CR — remove ad-hoc finalizers

### Task 2: Fix `longhorn-extras` Application CR — `ignoreDifferences` and `prune`

### Task 3: Fix `gpu-operator` Application CR — remove ad-hoc finalizers, add `prune: false`

### Task 4: Make Grafana VictoriaLogs datasource declarative

### Task 5: Document the Grafana datasource migration as a manual operation

### Task 6: Create `docs/runbooks/manual-operations.yaml`

### Task 7: Create the `/sync-runbook` skill

### Task 8: Update CLAUDE.md — add `/sync-runbook` to layer workflow and document the manual-op format

### Task 9: Push and verify root app syncs clean
