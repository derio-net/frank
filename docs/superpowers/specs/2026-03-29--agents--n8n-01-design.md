# n8n-01: Per-User Workflow Automation Instance

**Layer:** agents (12 — Agentic Control Plane)
**Date:** 2026-03-29
**Status:** Deployed

## Overview

Deploy a single-user n8n Community Edition instance (`n8n-01`) on gpu-1, backed by a dedicated PostgreSQL database. Authentication is handled by Authentik forward-auth proxy; n8n's built-in auth is hardcoded to `admin@n8n.local` / `admin` via an init container. The pattern is designed for copy-paste duplication — adding n8n-02, n8n-03 is a find-replace operation.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Node placement | gpu-1 | Underutilized resources (i9, 128GB); no GPU resource request needed |
| Database | Dedicated Bitnami PostgreSQL | Multi-user robustness; matches infisical-postgresql pattern |
| Manifest style | Raw manifests | Matches gpu-1 workload pattern (ComfyUI, Kali); full control |
| Auth | Authentik forward-auth + hardcoded n8n built-in | OIDC is enterprise-only; forward-auth gates access, n8n session persists |
| Multi-user isolation | Separate instances per user | n8n Community Edition does not support multi-user accounts |
| Parameterization | Copy-paste duplication | YAGNI — 2-3 instances max, 6 files each, no chart complexity |
| Metrics | Prometheus annotations | VMAgent auto-discovers; no VMServiceScrape CRD needed |
| n8n-oidc project | Rejected | Unmaintained (no commits in 3 months), open "doesn't work" issues, no releases |
| Layer | agents (12) | n8n is a workflow automation / agentic tool |

## Architecture

```
Authentik (forward-auth)
  │
  ▼
n8n-01 Service (LB 192.168.55.216:5678)
  │
  ▼
n8n-01 Deployment (gpu-1, 1 replica, Recreate)
  ├── init container: n8n user:create (bootstrap admin)
  ├── PVC: n8n-01-data (10Gi Longhorn, /home/node/.n8n)
  └── env: DB connection, metrics, webhook URL
        │
        ▼
n8n-01-postgresql (Bitnami chart, 5Gi Longhorn)
  └── auth from SOPS secret: n8n-01-secrets
```

## Components

### n8n-01 Deployment

- **Image:** `docker.io/n8nio/n8n:<pinned>` (pin to latest stable at implementation time)
- **Replicas:** 1
- **Strategy:** `Recreate` (RWO PVC constraint)
- **Scheduling:**
  - `nodeSelector: kubernetes.io/hostname: gpu-1`
  - `tolerations: [{key: nvidia.com/gpu, operator: Exists, effect: NoSchedule}]`
  - No `nvidia.com/gpu` resource request
- **Resources:**
  - Requests: `500m` CPU, `512Mi` memory
  - Limits: `2000m` CPU, `2Gi` memory
- **PVC:** `n8n-01-data` — 10Gi Longhorn, mounted at `/home/node/.n8n`
- **Init container:** REMOVED — `n8n user:create` CLI command does not exist in n8n Community Edition 2.13.4. Owner account is created via the first-time setup wizard in the browser instead.
- **Probes:** HTTP GET `/healthz` (startup, liveness, readiness)

### Environment Variables

```yaml
# Database
DB_TYPE: postgresdb
DB_POSTGRESDB_HOST: n8n-01-postgresql
DB_POSTGRESDB_PORT: "5432"
DB_POSTGRESDB_DATABASE: n8n
DB_POSTGRESDB_USER: n8n
DB_POSTGRESDB_PASSWORD: <from n8n-01-secrets Secret, key: password>
N8N_ENCRYPTION_KEY: <from n8n-01-secrets Secret, key: encryption-key>

# Metrics
N8N_METRICS: "true"
N8N_METRICS_PREFIX: n8n_

# General
N8N_HOST: 0.0.0.0
N8N_PORT: "5678"
WEBHOOK_URL: https://n8n-01.frank.derio.net/
```

### PostgreSQL (Bitnami chart)

- **Chart:** `registry-1.docker.io/bitnamicharts/postgresql` (pinned version)
- **Image:** `mirror.gcr.io/bitnamilegacy/postgresql` (Docker Hub mirror workaround)
- **`fullnameOverride: n8n-01-postgresql`**
- **Architecture:** standalone
- **Auth:** `existingSecret: n8n-01-secrets` (keys: `postgres-password`, `password`)
- **Database:** `n8n`, user: `n8n`
- **Storage:** 5Gi Longhorn

### Networking

- **Service:** `type: LoadBalancer`, annotation `lbipam.cilium.io/ips: "192.168.55.216"`, port 5678
- **Domain:** `n8n-01.frank.derio.net`
- **Prometheus annotations on pod:**
  ```yaml
  prometheus.io/scrape: "true"
  prometheus.io/port: "5678"
  prometheus.io/path: "/metrics"
  ```

### Authentik Integration

Add to existing `apps/authentik-extras/manifests/blueprints-proxy-providers.yaml`:

- **Proxy provider:** `name: n8n-01`, `mode: forward_single`, `external_host: https://n8n-01.frank.derio.net`
- **Application:** `slug: n8n-01`, `meta_launch_url: https://n8n-01.frank.derio.net`

No client secret needed for forward-auth proxy providers.

## File Layout

```
apps/root/templates/ns-n8n-01.yaml              # Namespace manifest (not an Application CR)
apps/root/templates/n8n-01.yaml                  # Application CR (raw manifests)
apps/root/templates/n8n-01-postgresql.yaml        # Application CR (Bitnami chart)
apps/n8n-01/manifests/deployment.yaml             # Deployment + init container
apps/n8n-01/manifests/service.yaml                # LoadBalancer Service
apps/n8n-01/manifests/pvc.yaml                    # 10Gi Longhorn PVC
apps/n8n-01-postgresql/values.yaml                # Postgres Helm values
apps/authentik-extras/manifests/                   # Update blueprints-proxy-providers.yaml
secrets/n8n-01/n8n-01-secrets.yaml                   # SOPS-encrypted bootstrap secret
```

### ArgoCD Application CRs

- **n8n-01:** Single source, `path: apps/n8n-01/manifests`. Standard `ServerSideApply=true`, `RespectIgnoreDifferences=true`, `prune: false`, `selfHeal: true`. `ignoreDifferences` on Secret `/data` (SOPS secret applied out-of-band).
- **n8n-01-postgresql:** Multi-source (Bitnami chart + `$values` ref), `destination.namespace: n8n-01` (same namespace as the main app, matching infisical pattern). Same sync options. `ignoreDifferences` on Secret `/data`.

## Manual Operations

```yaml
# manual-operation
id: n8n-01-sops-secret
layer: agents
app: n8n-01
plan: 2026-03-29--agents--n8n-01
when: Before first ArgoCD sync
why_manual: Bootstrap secret must exist before n8n-01-postgresql starts; SOPS secrets applied out-of-band
commands:
  - sops --decrypt secrets/n8n-01/n8n-01-secrets.yaml | kubectl apply -f -
verify:
  - kubectl -n n8n-01 get secret n8n-01-secrets -o jsonpath='{.data.password}' | base64 -d
status: pending
```

## Duplication Guide (n8n-02, n8n-03, ...)

To add a new instance:

1. Copy `apps/n8n-01/` → `apps/n8n-<NN>/`, find-replace `n8n-01` → `n8n-<NN>`
2. Copy `apps/n8n-01-postgresql/` → `apps/n8n-<NN>-postgresql/`, find-replace
3. Copy the 3 Application CR templates (`ns-`, `n8n-`, `n8n-*-postgresql`), find-replace
4. Pick next available IP from `192.168.55.2xx` range
5. Add proxy provider + application entries to `blueprints-proxy-providers.yaml`
6. Create and encrypt `secrets/n8n-<NN>-secrets.yaml` with new Postgres passwords
7. Apply SOPS secret, commit, push — ArgoCD syncs

## Security Notes

- n8n has had critical CVEs in early 2026 (CVE-2026-21858 unauthenticated RCE, CVE-2026-21877 authenticated RCE). Pin to a version that includes the February 2026 security patches.
- The hardcoded `admin/admin` credentials are acceptable only because Authentik forward-auth is the security boundary. If forward-auth is ever removed, change these immediately.
- LAN-only exposure via Cilium L2 LoadBalancer — not publicly routable.
- `N8N_ENCRYPTION_KEY` is stored in the SOPS secret for credential recoverability. Without it, n8n auto-generates a key on the filesystem — if the PVC is lost, all stored credentials become unrecoverable.

## Post-Deployment Updates

- Update `.claude/rules/frank-infrastructure.md` Service table with n8n-01 entry (IP 192.168.55.216, port 5678)
- Run `/update-readme` to sync Technology Stack, Service Access, and Current Status
