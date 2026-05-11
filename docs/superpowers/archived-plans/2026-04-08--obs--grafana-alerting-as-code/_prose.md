# Grafana Alerting as Code — Implementation Plan

## Phase 1: Grafana Alerting as Code — Implementation Plan

### Task 1: Create the ArgoCD Application CR

- P1.T1.S1: Create the Application CR

- P1.T1.S2: Verify YAML syntax

- P1.T1.S3: Commit

### Task 2: Create the Alert Rules ConfigMap

- P1.T2.S1: Create the manifests directory

- P1.T2.S2: Create the alert rules ConfigMap

- P1.T2.S3: Validate YAML syntax

- P1.T2.S4: Commit

### Task 3: Create the Contact Points ConfigMap

- P1.T3.S1: Create the contact points ConfigMap

- P1.T3.S2: Validate YAML syntax

- P1.T3.S3: Commit

### Task 4: Create the Notification Policy ConfigMap

- P1.T4.S1: Create the notification policy ConfigMap

- P1.T4.S2: Validate YAML syntax

- P1.T4.S3: Commit

### Task 5: Create the ExternalSecret for Alerting Env Vars

- P1.T5.S1: Create the ExternalSecret

- P1.T5.S2: Validate YAML syntax

- P1.T5.S3: Commit

### Task 6: Create the Dashboard ConfigMap

- P1.T6.S1: Create the dashboard ConfigMap

- P1.T6.S2: Validate YAML syntax

- P1.T6.S3: Commit

### Task 7: Update victoria-metrics Values (Mounts + Secrets)

- P1.T7.S1: Add extraConfigmapMounts entries

- P1.T7.S2: Switch envFromSecret to envFromSecrets

- P1.T7.S3: Verify the complete values file

- P1.T7.S4: Validate YAML syntax

- P1.T7.S5: Commit

### Task 8: Deploy and Verify File-Provisioned Resources

- P1.T8.S1: Push the branch and wait for ArgoCD sync

- P1.T8.S2: Verify the ExternalSecret synced

- P1.T8.S3: Verify Grafana pod is running with new mounts

- P1.T8.S4: Verify file-provisioned alert rules appear

- P1.T8.S5: Verify file-provisioned contact points appear

- P1.T8.S6: Verify notification policy

- P1.T8.S7: Verify Feature Health dashboard in feature-health folder

### Task 9: Delete API-Provisioned Duplicates (Migration)

- P1.T9.S1: Set up auth variable

- P1.T9.S2: Delete API-provisioned alert rules

- P1.T9.S3: Check for duplicate contact points and delete API copies

- P1.T9.S4: Restart Grafana pod to flush alertmanager dedup state

### Task 10: End-to-End Verification

- P1.T10.S1: Verify all 5 alert rules are file-provisioned

- P1.T10.S2: Verify contact points and notification policy

- P1.T10.S3: Verify dashboard

- P1.T10.S4: PVC loss simulation — restart Grafana and verify survival

- P1.T10.S5: Trigger test alert (optional live verification)

### Task 11: Update Blog Posts

- P1.T11.S1: Add a "File-Provisioned Alerting" section

- P1.T11.S2: Mark API commands as historical

- P1.T11.S3: Commit

### Task 12: Update Gotchas

- P1.T12.S1: Add provisioning gotcha

- P1.T12.S2: Commit
