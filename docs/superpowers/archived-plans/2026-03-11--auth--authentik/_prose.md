# Unified Authentication & Authorization Implementation Plan

## Phase 1: Unified Authentication & Authorization Implementation Plan

### Task 1: Research Authentik Helm Chart

- P1.T1.S1: Add Authentik Helm repo and inspect chart

- P1.T1.S2: Inspect default values

- P1.T1.S3: Check subchart behavior

### Task 2: Create SOPS-Encrypted Bootstrap Secrets

- P1.T2.S1: Generate secret values

- P1.T2.S2: Create the Kubernetes Secret manifest

- P1.T2.S3: Encrypt with SOPS

- P1.T2.S4: Apply the secret to the cluster

- P1.T2.S5: Commit encrypted secrets

- P1.T2.S1: Create namespace manifest

- P1.T2.S2: Commit

### Task 3: Create Authentik ArgoCD Application

- P1.T3.S1: Create Authentik Helm values

- P1.T3.S2: Create Authentik Application CR

- P1.T3.S3: Commit

### Task 4: Create Authentik Extras (LoadBalancer + Blueprints)

- P1.T4.S1: Create LoadBalancer Service

- P1.T4.S2: Create groups blueprint ConfigMap

- P1.T4.S3: Create authentik-extras Application CR

- P1.T4.S5: Commit

### Task 5: Deploy and Verify Authentik

- P1.T5.S1: Push to remote

- P1.T5.S2: Sync ArgoCD root app

- P1.T5.S3: Verify pods are running

- P1.T5.S4: Verify LoadBalancer

- P1.T5.S5: Add Traefik route on raspi-omni

- P1.T5.S6: Access Authentik initial setup

- P1.T5.S7: Add akadmin to root-admins group

### Task 6: ArgoCD OIDC Integration with Authentik

- P1.T6.S1: Create OIDC client secret for ArgoCD

- P1.T6.S2: Create Authentik OIDC provider blueprint for ArgoCD

- P1.T6.S3: Update authentik values to include new blueprint ConfigMap

- P1.T6.S4: Update ArgoCD values for OIDC

- P1.T6.S5: Set the client_secret in Authentik UI

- P1.T6.S6: Commit and deploy

- P1.T6.S7: Verify ArgoCD OIDC login

### Task 7: Grafana OIDC Integration with Authentik

- P1.T7.S1: Research current Grafana deployment

- P1.T7.S2: Generate OIDC client secret for Grafana

- P1.T7.S3: Create Authentik OIDC provider blueprint for Grafana

- P1.T7.S4: Update Grafana values for OIDC

- P1.T7.S5: Update authentik values with new blueprint ConfigMap

- P1.T7.S6: Set client secret in Authentik UI and commit

### Task 8: Infisical OIDC Integration with Authentik

- P1.T8.S1: Research Infisical OIDC support

- P1.T8.S2: Create Authentik OIDC provider blueprint for Infisical

- P1.T8.S3: Generate and store Infisical OIDC client secret

- P1.T8.S4: Configure Infisical OIDC via admin UI

- P1.T8.S4: Update authentik values and commit

### Task 9: Proxy Outpost for Longhorn, Hubble, Sympozium

- P1.T9.S1: Research embedded outpost configuration

- P1.T9.S2: Create proxy provider blueprints

- P1.T9.S3: Update authentik values with proxy blueprint

- P1.T9.S4: Configure Traefik forward auth on raspi-omni

- P1.T9.S5: Commit

### Task 10: Agent Auth — Authentik Client Credentials

- P1.T10.S1: Create agent auth blueprint

- P1.T10.S2: Update authentik values and commit

- P1.T10.S3: Create machine user and set client secret in Authentik UI

### Task 11: Configure Kubernetes OIDC and Agent Kubeconfig

- P1.T11.S1: Research Kubernetes OIDC configuration on Talos

- P1.T11.S2: Create Talos OIDC patch

- P1.T11.S3: Create Kubernetes RBAC for Authentik groups

- P1.T11.S4: Install kubelogin (oidc-login) plugin

- P1.T11.S5: Create .env_agent with OIDC kubeconfig

- P1.T11.S6: Verify agent auth

- P1.T11.S7: Commit RBAC manifests

### Task 12: Investigate and Fix Omni Service Account TTL

- P1.T12.S1: Check current Omni service account configuration

- P1.T12.S2: Research Omni service account TTL docs

- P1.T12.S3: Document findings

### Task 13: End-to-End Verification and Cleanup

- P1.T13.S1: Verify all ArgoCD apps are healthy

- P1.T13.S2: Verify OIDC login for all native OIDC services

- P1.T13.S3: Verify proxy outpost for non-OIDC services

- P1.T13.S4: Verify agent auth

- P1.T13.S5: Create .env_agent alongside existing .env_devops

- P1.T13.S6: Sync runbook

- P1.T13.S7: Final commit
