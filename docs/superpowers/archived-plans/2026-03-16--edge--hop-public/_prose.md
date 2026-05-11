# Hop: Public Edge Entrypoint — Implementation Plan

## Phase 1: Hop: Public Edge Entrypoint — Implementation Plan

### Task 1: Packer Image Build ✅

- P1.T1.S1: Create directory structure

- P1.T1.S2: Create Packer variables file

- P1.T1.S3: Create Packer template

- P1.T1.S4: Create .gitignore

- P1.T1.S5: Validate Packer template

- P1.T1.S6: Commit

### Task 2: Provision Hetzner Server and Omni Registration ✅ DEVIATED

- P1.T2.S1: Document the provisioning procedure

- P1.T2.S2: Create Talos machine config patch for Hetzner Volume mount

- P1.T2.S3: Set up DNS records

- P1.T2.S4: Commit the manual-operation blocks to the plan

### Task 3: Hop App-of-Apps Root Chart ✅

- P1.T3.S1: Create directory structure

- P1.T3.S2: Create Chart.yaml

- P1.T3.S3: Create values.yaml

- P1.T3.S4: Create AppProject

- P1.T3.S5: Commit

### Task 4: Bootstrap ArgoCD on Hop ✅

- P1.T4.S1: Create ArgoCD values for Hop

- P1.T4.S2: Create ArgoCD Application CR template

- P1.T4.S3: Document ArgoCD bootstrap procedure

- P1.T4.S4: Commit

### Task 5: Static Storage (PV + StorageClass) ✅

- P1.T5.S1: Create directory structure

- P1.T5.S2: Create StorageClass

- P1.T5.S3: Create static PV for Headscale

- P1.T5.S4: Create static PV for Caddy

- P1.T5.S5: Create Application CR for storage

- P1.T5.S6: Commit

### Task 6: Headscale Deployment ✅ DEVIATED

- P1.T6.S1: Create directory structure

- P1.T6.S2: Create namespace template

- P1.T6.S3: Create Headscale ConfigMap *(actual: added `extra_records` for split-DNS — Deviation #4)*

- P1.T6.S4: Create Headscale PVC

- P1.T6.S5: Create Headscale Deployment

- P1.T6.S6: Create Headscale Service

- P1.T6.S7: Create Application CR for Headscale

- P1.T6.S8: Commit

### Task 7: Headplane Deployment ✅ DEVIATED

- P1.T7.S1: Create directory structure

- P1.T7.S2: Create Headplane Deployment *(actual: env vars replaced with config file mount + API key Secret ref — Deviation #6)*

- P1.T7.S3: Create Headplane Service

- P1.T7.S4: Create RBAC for Headplane's Kubernetes integration

- P1.T7.S5: Create Application CR for Headplane

- P1.T7.S6: Commit

### Task 8: Caddy Reverse Proxy ✅ DEVIATED

- P1.T8.S1: Create directory structure

- P1.T8.S2: Create namespace template

- P1.T8.S3: Create Caddyfile ConfigMap *(actual: added `/admin/` redirect for Headplane, blog path stripping — Deviations #6, #9)*

- P1.T8.S4: Create Caddy PVC

- P1.T8.S5: Create Caddy Deployment

- P1.T8.S6: Create Caddy Cloudflare secret

- P1.T8.S7: Create Application CR for Caddy

- P1.T8.S8: Commit

### Task 9: Blog Container and Deployment ✅ DEVIATED

- P1.T9.S1: Create directory structure

- P1.T9.S2: Create namespace template

- P1.T9.S3: Create blog Dockerfile

- P1.T9.S4: Create Blog Deployment

- P1.T9.S5: Create Blog Service

- P1.T9.S6: Create Application CR for Blog

- P1.T9.S7: Commit

### Task 10: Landing Page ✅

- P1.T10.S1: Create directory structure

- P1.T10.S2: Create landing page HTML

- P1.T10.S3: Create Landing Deployment

- P1.T10.S4: Create Landing Service

- P1.T10.S5: Create namespace template

- P1.T10.S6: Create Application CR

- P1.T10.S7: Commit

### Task 11: Update Blog CI Pipeline ✅

- P1.T11.S1: Update workflow to build and push container image

- P1.T11.S2: Commit

### Task 12: Build Custom Caddy Image with Cloudflare Plugin ✅

- P1.T12.S1: Create Caddy Dockerfile

- P1.T12.S2: Create CI workflow for Caddy image

- P1.T12.S3: Update Caddy deployment to use custom image

- P1.T12.S4: Commit

### Task 13: SOPS-Encrypted Secrets ⏭️ SKIPPED

- P1.T13.S1: Create secrets directory

- P1.T13.S2: Document all secrets that need out-of-band application

- P1.T13.S3: Commit secrets directory

### Task 14: Headscale DB Backup CronJob ✅

- P1.T14.S1: Create backup CronJob

- P1.T14.S2: Commit

### Task 15: End-to-End Verification ✅

- P1.T15.S1: Verify all pods are running

- P1.T15.S2: Verify ArgoCD apps are synced

- P1.T15.S3: Verify public endpoints

- P1.T15.S4: Verify private endpoint enforcement

- P1.T15.S5: Test Headscale client registration

### Task 16: Update Documentation ✅

- P1.T16.S1: Add Hop to Architecture section in CLAUDE.md

- P1.T16.S2: Add Hop node to Nodes table

- P1.T16.S3: Add Hop services to Services table

- P1.T16.S4: Commit
