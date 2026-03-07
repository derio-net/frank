# Phase 09: Secrets Management — Design

**Date:** 2026-03-07

## Overview

Deploy Infisical (self-hosted) as a secrets backend and External Secrets Operator (ESO) to sync secrets into Kubernetes. This replaces the SOPS/age workflow for runtime secrets — SOPS may still be used for bootstrap secrets (e.g., Infisical's own database credentials) that need to exist before Infisical is running.

Infisical is MIT-licensed, self-hostable, and has a clean modern UI. ESO is the CNCF-standard bridge between external secret stores and K8s Secrets.

## Stack

| Component | Tool | Chart |
|-----------|------|-------|
| Secrets backend | Infisical | `infisical/infisical` |
| K8s sync operator | External Secrets Operator | `external-secrets/external-secrets` |

## Architecture

```
Infisical (self-hosted)
    └── Projects / Environments / Secrets
            ↓  (ESO InfisicalSecret CR or ClusterSecretStore)
External Secrets Operator
            ↓
    K8s Secret objects
            ↓
    App pods (secretKeyRef / envFrom)
```

### Infisical

Deployed as a self-hosted instance in the `infisical` namespace. Requires a PostgreSQL database (deployed as a dependency or via a managed instance). Infisical stores secrets in projects, organized by environment (dev/staging/prod or equivalent).

UI exposed at `192.168.55.204` via Cilium L2 LoadBalancer.

### External Secrets Operator

Deployed in the `external-secrets` namespace. Configured with a `ClusterSecretStore` pointing at the self-hosted Infisical instance. Apps reference secrets via `ExternalSecret` CRs that define which Infisical project/environment/key to sync.

### Bootstrap

Infisical's own database credentials and initial admin token are bootstrapped via SOPS-encrypted secrets in git — the only remaining SOPS use case.

## ArgoCD Apps

**`infisical`** (namespace: `infisical`)
- Chart: `infisical/infisical`
- Values: `apps/infisical/values.yaml`
- LoadBalancer IP: `192.168.55.204`
- PostgreSQL: deployed as subchart or separate app

**`external-secrets`** (namespace: `external-secrets`)
- Chart: `external-secrets/external-secrets`
- Values: `apps/external-secrets/values.yaml`
- Includes `ClusterSecretStore` manifest pointing at Infisical

## Storage

| Component | Size | Notes |
|-----------|------|-------|
| Infisical PostgreSQL | 5Gi | Longhorn, primary data store |

## Exposure

| Service | IP | Notes |
|---------|----|-------|
| Infisical UI | `192.168.55.204` | Cilium L2 LoadBalancer |
| ESO | ClusterIP only | Internal operator |

## Blog Post

**Title:** "Phase 9 — Secrets Management: Self-Hosting Infisical with External Secrets Operator"

**Angle:** Why we moved beyond SOPS for runtime secrets. Introduce Infisical as a Vault alternative (MIT, self-hosted, clean UI). Walk through ESO setup, the ClusterSecretStore → ExternalSecret → K8s Secret flow. Show a real app consuming a secret from Infisical. Contrast with Vault complexity.
