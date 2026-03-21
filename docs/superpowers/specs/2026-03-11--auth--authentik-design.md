# Unified Authentication & Authorization Design

**Date:** 2026-03-11
**Layer:** auth
**Status:** Draft

## Problem Statement

Frank cluster has three authentication gaps:

1. **Agent auth** — The only authentication mechanism is Auth0 at the Omni level, which requires interactive browser login. Tokens expire, blocking non-interactive workflows (Claude Code running `kubectl`, `talosctl`, `omnictl`).
2. **Multi-user access** — No way to grant other users fine-grained cluster access (e.g., scoped to a vCluster, with role-based permissions).
3. **Fragmented service auth** — Exposed services (Grafana, Sympozium, Longhorn UI, etc.) either have no authentication or isolated, manually-created accounts. No single sign-on.

## Solution: Authentik as Cluster Identity Provider

Deploy [Authentik](https://goauthentik.io/) inside frank-cluster as an ArgoCD app. Authentik provides OIDC, proxy-based auth, service accounts, and declarative configuration via blueprints.

### Why Authentik

| Criterion | Authentik | Keycloak | Zitadel |
|-----------|----------|----------|---------|
| Resource footprint | Moderate (Python/Django) | Heavy (Java, 512MB-1GB+) | Light (Go) |
| Proxy auth for non-OIDC services | Yes (outpost model) | Requires separate proxy | No native proxy |
| Declarative config | Blueprints (YAML) | Realm export (fragile JSON) | Terraform provider |
| Machine users / service accounts | Native support | Supported | Native support |
| Community / docs for homelab | Strong | Enterprise-focused | Smaller community |

Authentik wins on the combination of proxy outpost support (critical for services without OIDC), YAML-based declarative blueprints (fits declarative-only principle), and reasonable resource footprint.

## Identity Model

### Organization-Based Hierarchy

Organizations are the top-level grouping. Each organization can access one or more vClusters. Within each organization, users are assigned roles.

```
Organization (root)
  admins       -> host cluster-admin + all vClusters
  devops       -> host namespace-scoped RBAC + all vClusters
  developers   -> host read-only + all vClusters
  agents       -> scoped service accounts, API access

Organization (team-alpha)  <- future, post-tenant layer
  admins       -> team-alpha vCluster admin
  devops       -> team-alpha vCluster operator
  developers   -> team-alpha vCluster user
  agents       -> team-alpha scoped tokens
```

### Authentik Group Mapping

Authentik supports nested groups. Groups use org-aware naming:

- `root` (parent group representing the organization)
  - `root-admins` (parent: root)
  - `root-devops` (parent: root)
  - `root-developers` (parent: root)
  - `root-agents` (parent: root)

Nesting provides organizational structure inside Authentik, but the OIDC `groups` claim sent to Kubernetes and services is a flat list of group names. Kubernetes RBAC matches on the flat string values (e.g., `root-admins`).

### User Types

- **Human users** — authenticate via Authentik login flow (username/password + optional TOTP). For the expected scale (<10 users), Authentik's built-in user directory is sufficient. No external LDAP or social login needed.
- **Machine users (agents)** — Authentik service accounts with long-lived API tokens via OAuth2 client credentials grant. No interactive login required. Each agent gets its own identity for audit trail.

### Group-to-Kubernetes RBAC Mapping

- Authentik includes group claims in the OIDC token (`groups` claim)
- ClusterRoleBindings map Authentik groups to K8s RBAC roles
- For vCluster users (future), they receive a kubeconfig scoped to their vCluster only

### Per-Service Role Mapping

| Service | Group Mapping |
|---------|--------------|
| ArgoCD | `root-admins` -> admin role, `root-devops` -> read/write, `root-developers` -> read-only |
| Grafana | `root-admins` -> Admin org role, `root-devops` -> Editor, `root-developers` -> Viewer |
| Proxied services | Authenticated = allowed, with optional group-based access rules |

## Service Integration Plan

### Native OIDC Integration

| Service | How | Config Approach |
|---------|-----|----------------|
| ArgoCD | Replace built-in Dex with Authentik OIDC provider | `oidc.config` in ArgoCD values.yaml, group-to-role mapping in `argocd-rbac-cm` |
| Grafana | Native `auth.generic_oauth` | Grafana values.yaml, map Authentik groups to Grafana org roles |
| Infisical | Native OIDC support | Configure via Infisical settings |

### Proxy Outpost (Forward Auth)

| Service | How |
|---------|-----|
| Longhorn UI | Authentik proxy provider — only authenticated users pass through |
| Hubble UI | Authentik proxy provider with group-based access rules |
| Sympozium | Authentik proxy provider (unless native OIDC support is added) |

Traffic flow for proxied services:

```
User -> Cilium LB -> Authentik Proxy Outpost -> Backend Service
```

Existing LoadBalancer IPs for proxied services would point to the proxy outpost instead of directly to the backend.

### API-Only (Unchanged)

| Service | Reason |
|---------|--------|
| LiteLLM | API key auth is appropriate for programmatic access. Agents get keys scoped to their org. |

## Agent Authentication (Non-Interactive)

### kubectl — Authentik OIDC Client Credentials

- Kubeconfig uses `oidc-login` credential exec plugin
- Human users: browser-based OIDC login flow
- Agents: `client_credentials` grant type (client ID + secret, no browser)
- Token refresh is automatic — no timeout/expiry problem
- Dedicated Authentik OAuth2 application for agent access

### talosctl — Talos mTLS Certificates

- Talos uses its own mTLS certificates, independent of OIDC
- Current talosconfig downloaded from Omni, but certs expire
- Solution: generate long-lived talosconfig via Omni with appropriate TTL, or use Omni service account to issue talosconfigs on demand

### omnictl — Omni Service Account Key

- Existing `OMNI_SERVICE_ACCOUNT_KEY` may have a TTL issue
- **Investigation needed:** check if key TTL is configurable in Omni self-hosted config
- If configurable: set appropriate TTL and document
- If architectural limitation: document workaround

### Agent Environment File

Single `.env_agent` file for all non-interactive credentials:

```bash
# Cluster access
KUBECONFIG=...
TALOSCONFIG=...
OMNICONFIG=...

# Non-interactive auth
OMNI_SERVICE_ACCOUNT_KEY=...
AUTHENTIK_CLIENT_ID=...
AUTHENTIK_CLIENT_SECRET=...
```

Usage: `source .env_agent && kubectl get nodes` — works without browser interaction.

**Security:** `.env_agent` is gitignored (contains plaintext secrets). It is generated manually from credentials stored in Infisical (the cluster's secrets manager). Never committed to the repo.

## DNS and TLS Strategy

Authentik's OIDC and proxy outpost flows require browser redirects between services and Authentik. This requires resolvable hostnames with TLS.

**Existing infrastructure:** A Traefik reverse proxy on raspi-omni holds a wildcard `*.frank.derio.net` certificate from Let's Encrypt. It already routes hostnames to Cilium L2 IPs for all exposed services (ArgoCD, Grafana, Longhorn UI, etc.).

**Authentik hostname:** `auth.frank.derio.net` -> 192.168.55.211

This is added to the Traefik config on raspi-omni as a manual step (consistent with existing services). All OIDC redirect URIs use `https://<service>.frank.derio.net` — no HTTP redirect concerns.

**Service hostnames for OIDC redirect URIs:**

| Service | Hostname | Already configured |
|---------|----------|--------------------|
| Authentik | `auth.frank.derio.net` | No — add during deployment |
| ArgoCD | `argocd.frank.derio.net` | Yes |
| Grafana | `grafana.frank.derio.net` | Yes |
| Infisical | `infisical.frank.derio.net` | Yes |
| Longhorn UI | `longhorn.frank.derio.net` | Yes |
| Hubble UI | `hubble.frank.derio.net` | Yes |
| Sympozium | `sympozium.frank.derio.net` | Yes |

## Deployment Architecture

### Components

| Component | Purpose | Scheduling | Replicas |
|-----------|---------|-----------|----------|
| Authentik Server | Core app (Django) — UI, OIDC, admin API | Control-plane nodes | 2+ (HA) |
| Authentik Worker | Background tasks (email, sync, blueprints) | Control-plane nodes | 1 |
| PostgreSQL | User store, config, sessions | Control-plane nodes | 1 (Longhorn 3-replica PVC) |
| Redis | Cache, session store, task queue | Control-plane nodes | 1 (Longhorn PVC) |
| Proxy Outpost (embedded) | Forward auth for non-OIDC services | Control-plane nodes | Auto-managed by Authentik |

**Scheduling note:** All Authentik pods require `tolerations` for the control-plane taint (`node-role.kubernetes.io/control-plane: NoSchedule`), consistent with the Infisical deployment pattern.

**Proxy outpost model:** Use Authentik's **embedded outpost** (runs inside the Authentik server pod, no separate deployment). This avoids needing a separate LoadBalancer IP for the outpost. The `proxy-outpost.yaml` in authentik-extras defines the outpost configuration object (which services to proxy), not a standalone pod deployment. The embedded outpost handles forward-auth callbacks on the same hostname (`auth.frank.derio.net`).

### ArgoCD Structure

```
apps/
  authentik/
    values.yaml            # Helm values (server, worker, PostgreSQL, Redis)
    manifests/
      blueprints/          # Declarative config (flows, providers, groups)
  authentik-extras/
    manifests/
      proxy-outpost.yaml   # Outpost config (if not auto-managed)
      lb-service.yaml      # LoadBalancer at 192.168.55.211
```

### Helm Chart

Official `goauthentik/authentik` chart. Chart version must be pinned (research latest stable version during implementation).

**Subchart strategy:** The chart bundles PostgreSQL and Redis as subcharts. The existing Infisical deployment in this repo splits these into separate ArgoCD apps to avoid subchart secret drift issues. During implementation, evaluate whether Authentik's chart has the same subchart environment variable collision bug. If so, adopt the split-app pattern (`authentik`, `authentik-postgresql`, `authentik-redis`). If not, use bundled subcharts with `ignoreDifferences` on auto-generated PostgreSQL/Redis secrets to prevent perpetual ArgoCD diffs.

### LoadBalancer

Authentik UI/OIDC endpoint: **192.168.55.211** via Cilium L2 LoadBalancer.

### Declarative Configuration via Blueprints

Authentik blueprints (YAML) define:
- Authentication flows (login, MFA enrollment)
- OAuth2/OIDC providers (one per service)
- Proxy providers (one per proxied service)
- Applications (service registrations)
- Groups (org hierarchy)
- Service accounts (agent users)

Blueprints are mounted into the Authentik server pod via ConfigMaps, sourced from the Git repo. All auth config lives in code — aligned with the declarative-only principle.

**Blueprint scope:** Blueprints define only structural config (flows, groups, applications, providers). They do NOT contain secret values (OAuth2 client secrets, admin passwords). Secret values are handled separately via SOPS-encrypted Kubernetes Secrets applied out-of-band (see Secrets Handling section).

## Secrets Handling

Authentik requires several secrets that must exist before the application starts. Following the project's declarative-only principle, these are stored as SOPS-encrypted files in `secrets/authentik/` and applied manually out-of-band.

**Required secrets:**

| Secret | Purpose | Notes |
|--------|---------|-------|
| `authentik-secret-key` | Signs cookies, tokens, sessions | Generated once, must not change |
| `authentik-postgresql-password` | PostgreSQL database password | Used by both Authentik and PostgreSQL pods |
| `authentik-bootstrap-password` | Initial admin (`akadmin`) password | Used only on first boot |
| OAuth2 client secrets | Per-service OIDC client secrets | One per integrated service (ArgoCD, Grafana, etc.) |

**Storage:** `secrets/authentik/` directory with SOPS/age-encrypted YAML files, gitignored plaintext.

**Application:** Manual out-of-band via `sops --decrypt <file> | kubectl apply -f -`.

**Manual operations:** The `# manual-operation` blocks for each secret are deferred to the implementation plan (not this design spec). The implementation plan will include a block per secret with `when`, `why_manual`, `commands`, and `verify` fields, and will be synced to the runbook via `/sync-runbook`.

## Migration Path

Four independent stages, each self-contained with rollback safety:

### Migration Stage 1 — Deploy Authentik Standalone

- Install Authentik via ArgoCD (Helm chart + blueprints)
- Configure blueprints: root org groups, login flow, admin account
- Verify Authentik UI accessible at 192.168.55.211
- **Rollback:** Remove ArgoCD app. No other services affected.

### Migration Stage 2 — Agent Auth

- Create machine user + OAuth2 client credentials application in blueprints
- Configure `.env_agent` with client ID/secret
- Set up kubeconfig with OIDC credential exec (`oidc-login` plugin)
- Investigate and fix Omni service account TTL
- Verify: `source .env_agent && kubectl get nodes` works non-interactively
- **Rollback:** Revert to existing kubeconfig/talosconfig.

### Migration Stage 3 — Service SSO (One at a Time)

Switch services to Authentik OIDC, one by one:

1. ArgoCD — replace Dex with Authentik OIDC
2. Grafana — configure `auth.generic_oauth`
3. Infisical — configure OIDC provider

Each service: configure, test, confirm, then move to next. If any service has issues, it keeps its existing auth.

### Migration Stage 4 — Proxy Outpost for Remaining Services

- Deploy Authentik proxy outpost
- Longhorn UI — route through proxy
- Hubble UI — route through proxy
- Sympozium — route through proxy
- **Rollback:** Point LB IPs back to services directly.

## Scope Boundaries

### In Scope
- Authentik deployment and declarative blueprints
- OIDC integration for ArgoCD, Grafana, Infisical
- Proxy outpost for Longhorn UI, Hubble UI, Sympozium
- Agent auth via client credentials (kubectl)
- Omni service account TTL investigation
- Root organization with admins/devops/developers/agents groups
- `.env_agent` consolidation

### Out of Scope (Deferred)
- Multi-organization support (deferred to tenant layer / vClusters)
- Self-service user onboarding / approval workflows
- External identity federation (LDAP, social login)
- MFA enforcement (can be enabled later via blueprints)
- LiteLLM auth changes (API keys remain)

## IP Allocation Note

When selecting LoadBalancer IPs, check both implemented and planned design documents in `docs/superpowers/specs/` for reservations. Current known allocations:

| IP | Service | Status |
|----|---------|--------|
| 192.168.55.200 | ArgoCD | Deployed |
| 192.168.55.201 | Longhorn UI | Deployed |
| 192.168.55.202 | Hubble UI | Deployed |
| 192.168.55.203 | Grafana | Deployed |
| 192.168.55.204 | Infisical | Deployed |
| 192.168.55.205 | KubeVirt | Reserved |
| 192.168.55.206 | LiteLLM | Deployed |
| 192.168.55.207 | Sympozium | Deployed |
| 192.168.55.208 | n8n | Reserved |
| 192.168.55.209 | Gitea | Reserved |
| 192.168.55.210 | Harbor | Reserved |
| 192.168.55.211 | Authentik | This layer |
