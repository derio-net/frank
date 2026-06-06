# Observability Implementation Plan

## Phase 1: Observability Implementation Plan

### Task 1: Create monitoring namespace

- P1.T1.S1: Create the namespace manifest

- P1.T1.S2: Verify ArgoCD picks it up

- P1.T1.S3: Commit

### Task 2: Add victoria-metrics ArgoCD Application

- P1.T2.S1: Check latest chart version

- P1.T2.S2: Create values file

- P1.T2.S3: Create Application CR

- P1.T2.S4: Sync and verify namespace exists

- P1.T2.S5: Commit

### Task 3: Deploy victoria-metrics and verify

- P1.T3.S1: Push and watch rollout

- P1.T3.S2: Verify Grafana is reachable

- P1.T3.S3: Verify VMSingle is scraping

- P1.T3.S4: Verify node-exporter is on all nodes

### Task 4: Add victoria-logs ArgoCD Application

- P1.T4.S1: Check latest chart version

- P1.T4.S2: Create values file

- P1.T4.S3: Create Application CR

- P1.T4.S4: Commit

### Task 5: Deploy victoria-logs and verify

- P1.T5.S1: Push and sync

- P1.T5.S2: Verify VictoriaLogs endpoint

- P1.T5.S3: Verify PVC is bound

### Task 6: Add fluent-bit ArgoCD Application

- P1.T6.S1: Check latest chart version

- P1.T6.S2: Create values file

- P1.T6.S3: Create Application CR

- P1.T6.S4: Commit

### Task 7: Deploy fluent-bit and verify log flow

- P1.T7.S1: Push and sync

- P1.T7.S2: Check Fluent Bit logs for errors

- P1.T7.S3: Verify logs arriving in VictoriaLogs

### Task 8: Verify VictoriaLogs datasource in Grafana

- P1.T8.S1: Open Grafana and check plugin

- P1.T8.S2: Verify datasource is configured

- P1.T8.S3: Query logs in Explore

### Task 9: Verify pre-built dashboards

- P1.T9.S1: Check bundled dashboards

- P1.T9.S2: Verify Longhorn and Cilium metrics appear

### Task 10: Final commit and push

- P1.T10.S1: Verify all apps healthy

- P1.T10.S2: Verify all PVCs bound

- P1.T10.S3: Final commit

### Task 11: Blog post — `07-observability`

- P1.T11.S1: Create post directory and frontmatter

- P1.T11.S2: Write post sections

- P1.T11.S3: Generate cover image

- P1.T11.S4: Build and verify

- P1.T11.S5: Publish and commit
