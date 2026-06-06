# In-Cluster Ingress Implementation Plan

## Phase 1: In-Cluster Ingress Implementation Plan

### Task 1: Verify backend service names and ports

- P1.T1.S1: Source the Frank cluster environment

- P1.T1.S2: List all ClusterIP and LoadBalancer services

- P1.T1.S3: Resolve each VERIFY marker

- P1.T1.S4: Check Authentik outpost forward-auth port

- P1.T1.S5: Record findings

### Task 2: Create Traefik ArgoCD Application CR

- P1.T2.S1: Research the current Traefik Helm chart version

- P1.T2.S2: Create the Application CR

- P1.T2.S3: Commit

### Task 3: Create Traefik Extras ArgoCD Application CR

- P1.T3.S1: Create the extras Application CR

- P1.T3.S2: Commit

### Task 4: Create Traefik Helm values

- P1.T4.S1: Create the values file

- P1.T4.S2: Verify YAML syntax

- P1.T4.S3: Commit

### Task 5: Create Middleware CRDs

- P1.T5.S1: Create the middlewares file

- P1.T5.S2: Verify YAML syntax

- P1.T5.S3: Commit

### Task 6: Create IngressRoute CRDs

- P1.T6.S1: Create the IngressRoutes file

- P1.T6.S2: Verify YAML syntax and count

- P1.T6.S3: Commit

### Task 7: Create Homepage ArgoCD Application CR

- P1.T7.S1: Create the Application CR

- P1.T7.S2: Commit

### Task 8: Create Homepage manifests

- P1.T8.S1: Create the Deployment

- P1.T8.S2: Create the Service

- P1.T8.S3: Create the services ConfigMap

- P1.T8.S4: Create the settings ConfigMap

- P1.T8.S5: Verify all manifests parse correctly

- P1.T8.S6: Commit

### Task 9: Manual operations — SOPS Secret, Pi-hole DNS, Authentik Provider

- P1.T9.S1: Create and encrypt the Cloudflare credentials Secret *(done by operator on main)*

- P1.T9.S2: Configure Pi-hole DNS *(done by operator)*

- P1.T9.S3: Commit the encrypted secret *(done by operator on main)*

- P1.T9.S4: Push all commits and verify ArgoCD sync

- P1.T9.S5: Verify Traefik pod is running

- P1.T9.S6: Verify ACME certificate was issued

- P1.T9.S7: Test a no-auth route

- P1.T9.S8: Create Authentik Proxy Provider *(handled declaratively via blueprint)*

- P1.T9.S9: Test a forward-auth route

- P1.T9.S10: Verify Homepage loads

### Task 10: Update Claude rules and infrastructure docs

- P1.T10.S1: Update frank-argocd.md

- P1.T10.S2: Update frank-infrastructure.md Services table

- P1.T10.S3: Commit

### Task 11: Sync manual operations runbook

- P1.T11.S1: Run the sync-runbook skill

- P1.T11.S2: Verify all 3 manual ops are in the runbook

- P1.T11.S3: Commit

### Task 12: Final verification and spec status update

- P1.T12.S1: Verify all routes

- P1.T12.S2: Verify Homepage shows all services

- P1.T12.S3: Update spec status

- P1.T12.S4: Final commit
