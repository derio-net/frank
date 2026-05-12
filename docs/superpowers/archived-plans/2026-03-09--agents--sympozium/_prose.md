# Sympozium Implementation Plan

## Phase 1: Sympozium Implementation Plan

### Task 1: cert-manager ArgoCD Application

- P1.T1.S1: Create cert-manager Helm values

- P1.T1.S2: Create cert-manager Application CR

- P1.T1.S3: Commit

### Task 2: Sympozium Helm ArgoCD Application

- P1.T2.S1: Research Helm chart values

- P1.T2.S2: Create Sympozium Helm values

- P1.T2.S3: Create Sympozium Application CR

- P1.T2.S4: Commit

### Task 3: sympozium-extras Application CR + ExternalSecret

- P1.T3.S1: Create sympozium-extras Application CR

- P1.T3.S2: Create ExternalSecret for LiteLLM API key

- P1.T3.S3: Commit

### Task 4: SympoziumPolicy Manifests

- P1.T4.S1: Create default policy (for platform-team ops agents)

- P1.T4.S2: Create restrictive policy (for devops-essentials dev agents)

- P1.T4.S3: Commit

### Task 5: PersonaPack Manifests

- P1.T5.S1: Discover CRD baseURL field

- P1.T5.S2: Create platform-team PersonaPack

- P1.T5.S3: Create devops-essentials PersonaPack

- P1.T5.S4: Commit

### Task 6: Verify Helm Chart Values Against Actual Chart

- P1.T6.S1: Pull and inspect the chart

- P1.T6.S2: Compare key fields

- P1.T6.S3: Fix mismatches

- P1.T6.S4: Verify OCI chart URL for ArgoCD

- P1.T6.S5: Commit any fixes

### Task 7: Manual Operation — Create Infisical Secret

### Task 8: Push and Verify cert-manager Deployment

- P1.T8.S1: Push

- P1.T8.S2: Wait for ArgoCD sync

- P1.T8.S3: Verify cert-manager is healthy

- P1.T8.S4: If cert-manager fails

### Task 9: Verify Sympozium Control Plane Deployment

- P1.T9.S1: Check ArgoCD sync

- P1.T9.S2: Verify core pods

- P1.T9.S3: Verify CRDs installed

- P1.T9.S4: Verify NATS persistence

- P1.T9.S5: Verify ExternalSecret synced

- P1.T9.S6: Verify PersonaPacks created

- P1.T9.S7: If Sympozium fails to sync

### Task 10: Verify Web Dashboard and Test Agent Run

- P1.T10.S1: Verify LoadBalancer IP

- P1.T10.S2: Retrieve web UI token

- P1.T10.S3: Access web dashboard

- P1.T10.S4: Run a test agent

- P1.T10.S5: Watch the agent run

- P1.T10.S6: Clean up test run

- P1.T10.S7: If agent run fails

### Task 11: Update CLAUDE.md Services Table

- P1.T11.S1: Add Sympozium Web UI entry

- P1.T11.S2: Commit

### Task 12: Sync Runbook

- P1.T12.S1: Run sync-runbook skill

- P1.T12.S2: Commit if changes

### Task 13: Final Push and Verification

- P1.T13.S1: Push all commits

- P1.T13.S2: Full health check
