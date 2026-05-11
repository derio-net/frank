# Work Lifecycle Tracking — M3: Health Bridge Service (Frank)

## Phase 1: Work Lifecycle Tracking — M3: Health Bridge Service (Frank)

### Task 1: Create Go Project and Repository

- P1.T1.S1: Create the repository on GitHub

- P1.T1.S2: Initialize Go module

- P1.T1.S3: Write `main.go`

- P1.T1.S4: Commit

### Task 2: Implement Core Bridge Logic

- P1.T2.S1: Write `bridge.go`

- P1.T2.S2: Commit

### Task 3: Implement GitHub GraphQL Client

- P1.T3.S1: Write `github.go`

- P1.T3.S2: Commit

### Task 4: Write Tests

- P1.T4.S1: Write `bridge_test.go`

- P1.T4.S2: Run tests

- P1.T4.S3: Commit

### Task 5: Create Dockerfile

- P1.T5.S1: Write `Dockerfile`

- P1.T5.S2: Build locally and verify image size

- P1.T5.S3: Write GitHub Actions workflow for GHCR publish

- P1.T5.S4: Commit

- P1.T5.S5: Tag and push to trigger first build

- P1.T5.S6: Verify GHCR image exists

### Task 6: Store Secrets in Infisical

- P1.T6.S1: Create HEALTH_BRIDGE_WEBHOOK_SECRET in Infisical

### Task 7: Create Kubernetes Manifests in Frank Repo

- P1.T7.S1: Create ExternalSecret for health-bridge credentials

- P1.T7.S2: Create ConfigMap for non-secret config

- P1.T7.S3: Create Deployment + Service

- P1.T7.S4: Create VMServiceScrape for self-monitoring

- P1.T7.S5: Commit in frank repo

### Task 8: Create ArgoCD Application CR

- P1.T8.S1: Create ArgoCD Application

- P1.T8.S2: Commit

- P1.T8.S3: Push and verify ArgoCD sync

### Task 9: Configure Grafana Webhook Contact Point

- P1.T9.S1: Create webhook contact point in Grafana

- P1.T9.S2: Update notification policy to route to webhook

### Task 10: Add `github_issue` Labels to Alert Rules

- P1.T10.S1: Update existing alert rules with `github_issue` labels

### Task 11: End-to-End Verification

- P1.T11.S1: Check bridge pod is healthy

- P1.T11.S2: Send a test webhook directly to the bridge

- P1.T11.S3: Send a resolved alert to restore state

- P1.T11.S4: Trigger a real Grafana alert and verify bridge receives it

- P1.T11.S5: Add self-monitoring probe (dogfooding)
