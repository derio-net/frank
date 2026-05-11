# Paperclip AI Orchestrator Implementation Plan

## Phase 1: Paperclip AI Orchestrator Implementation Plan

### Task 1: Paperclip PostgreSQL values

- P1.T1.S1: Create the values file

- P1.T1.S2: Commit

### Task 2: Paperclip-db ArgoCD Application CR

- P1.T2.S1: Create the Application CR

- P1.T2.S2: Commit

### Task 3: Namespace manifest

- P1.T3.S1: Create the namespace manifest

- P1.T3.S2: Commit

### Task 4: ConfigMap

- P1.T4.S1: Create the ConfigMap

- P1.T4.S2: Commit

### Task 5: ExternalSecret for LiteLLM credentials

- P1.T5.S1: Create the ExternalSecret

- P1.T5.S2: Commit

### Task 6: ExternalSecret for auth secret

- P1.T6.S1: Create the ExternalSecret

- P1.T6.S2: Commit

### Task 7: ExternalSecret for GHCR image pull secret

- P1.T7.S1: Create the ExternalSecret

- P1.T7.S2: Commit

### Task 8: PersistentVolumeClaim

- P1.T8.S1: Create the PVC

- P1.T8.S2: Commit

### Task 9: Deployment

- P1.T9.S1: Create the Deployment

- P1.T9.S2: Commit

### Task 10: LoadBalancer Service

- P1.T10.S1: Create the Service

- P1.T10.S2: Commit

### Task 11: Paperclip ArgoCD Application CR

- P1.T11.S1: Create the Application CR

- P1.T11.S2: Commit

### Task 12: Manual operation — Build and push container image

- P1.T12.S1: Execute manual operation `orch-build-paperclip-image`

- P1.T12.S2: Verify the image is pullable

### Task 13: Manual operation — Create Infisical secrets

- P1.T13.S1: Execute manual operation `orch-create-infisical-secrets`

- P1.T13.S2: Verify secrets exist

### Task 14: Push and verify ArgoCD sync

- P1.T14.S1: Push to remote

- P1.T14.S2: Verify ArgoCD detects the new apps

- P1.T14.S3: Sync the root app to pick up new Application CRs

- P1.T14.S4: Verify paperclip-db is healthy

- P1.T14.S5: Verify ExternalSecrets are synced

- P1.T14.S6: Verify Paperclip deployment is running

- P1.T14.S7: Verify LoadBalancer Service has IP assigned

- P1.T14.S8: Test web UI access

### Task 15: Update CLAUDE.md services table

- P1.T15.S1: Add Paperclip to the services table

- P1.T15.S2: Commit

### Task 16: Sync runbook

- P1.T16.S1: Run sync-runbook

- P1.T16.S2: Verify the runbook was updated

- P1.T16.S3: Commit if changed

### Task 17: Final push

- P1.T17.S1: Push
