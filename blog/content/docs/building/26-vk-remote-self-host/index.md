---
title: "VK Remote — Self-Hosting the Kanban Backend Before the Cloud Dies"
date: 2026-04-13
draft: false
tags: ["agents", "vibekanban", "postgresql", "electricsql", "rust", "axum", "authentik", "self-hosting"]
summary: "The VibeKanban cloud announced shutdown with 30 days' notice. This is how we deployed the self-hosted remote crate — PostgreSQL, ElectricSQL, and a Rust API — before the lights went out."
weight: 27
---

On April 10th, VibeKanban announced it was shutting down. Thirty days. The OAuth flow for our service account was already failing — likely early decommissioning. The local VK features (workspaces, sessions, git worktrees, agent spawning) would survive. But the kanban board, issue management, the 33 MCP tools that our agentic workflow depends on — all of that lives in the remote crate, backed by a PostgreSQL database that was about to stop existing.

The good news: VK's remote crate already supports self-hosting with local auth. The plan was straightforward. Fork the repo, build the image, deploy three containers, point the agent at it.

## What We're Deploying

Three components, one namespace, zero cloud dependencies:

| Component | Image | Port | Purpose |
|-----------|-------|------|---------|
| **vk-remote** | `ghcr.io/derio-net/vk-remote` (Rust/Axum) | 8081 | Kanban API server |
| **postgres-vk** | `postgres:16-alpine` | 5432 | Issue/project data, WAL logical replication |
| **electric** | `electricsql/electric:1.4.13` | 3000 | Real-time sync engine for the frontend |

ElectricSQL reads PostgreSQL's logical replication stream to push live updates to the browser — when an issue changes status on the board, every open tab sees it immediately. That's why we need `wal_level=logical` and a dedicated PostgreSQL instance rather than sharing n8n's database.

## Architecture

```
secure-agent-pod (VK local binary)
  └── VK_SHARED_API_BASE=http://vk-remote.agents.svc.cluster.local:8081
        └── vk-remote (Rust/Axum, port 8081)
              ├── postgres-vk (PG 16, WAL logical, 1Gi PVC)
              └── electric (reads PG WAL stream)

Browser → https://vk.cluster.derio.net
  └── Traefik IngressRoute → Authentik forward-auth → vk-remote:8081
```

The secure-agent-pod talks to vk-remote over in-cluster DNS. The browser goes through Traefik with Authentik SSO — same pattern as every other Frank service.

## Fork and Build

We forked `BloopAI/vibe-kanban` to `derio-net/vibe-kanban` and added a GitHub Actions workflow that builds the remote crate into a container image on every push to `main`:

```yaml
# .github/workflows/build-remote.yaml (excerpt)
name: Build vk-remote
on:
  push:
    branches: [main]
    paths:
      - 'crates/remote/**'
      - 'Cargo.toml'
      - 'Cargo.lock'
env:
  IMAGE_NAME: derio-net/vk-remote
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: crates/remote/Dockerfile
          push: true
          tags: |
            ghcr.io/${{ env.IMAGE_NAME }}:${{ github.sha }}
            ghcr.io/${{ env.IMAGE_NAME }}:latest
```

Images are pinned by commit SHA in manifests. We own the fork, so we can patch if upstream disappears entirely.

## PostgreSQL with Logical Replication

The dedicated PostgreSQL instance runs with WAL-level logical replication enabled via command-line args — no custom `postgresql.conf` needed:

```yaml
# apps/vk-remote/manifests/postgres.yaml (excerpt)
containers:
  - name: postgres
    image: postgres:16-alpine
    args:
      - "-c"
      - "wal_level=logical"
      - "-c"
      - "max_replication_slots=5"
      - "-c"
      - "max_wal_senders=5"
    env:
      - name: POSTGRES_DB
        value: remote
      - name: POSTGRES_USER
        value: remote
      - name: POSTGRES_PASSWORD
        valueFrom:
          secretKeyRef:
            name: vk-remote-secrets
            key: POSTGRES_PASSWORD
```

Recreate strategy because of the RWO PVC — the familiar deadlock avoidance pattern.

A PostSync Job creates the ElectricSQL role with replication privileges:

```yaml
# apps/vk-remote/manifests/postgres-init-job.yaml (excerpt)
annotations:
  argocd.argoproj.io/hook: PostSync
  argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
```

The Job waits for PG to be ready, then creates the `electric` role with `LOGIN` and `REPLICATION` privileges plus full grants on the `remote` database.

## Auth: Local Only

No OAuth. No identity provider integration on the application itself. Single admin user:

```
SELF_HOST_LOCAL_AUTH_EMAIL=admin@localhost
SELF_HOST_LOCAL_AUTH_PASSWORD=<from Infisical>
```

POST to `/v1/auth/local/login` returns JWT tokens. The secure-agent-pod's bridge authenticates this way. Browser access goes through Authentik forward-auth at the Traefik layer — the VK remote server itself doesn't know or care about SSO.

{{< asciinema src="vk-remote-pods.cast" >}}

## Secrets via Infisical

Four secrets in Infisical, pulled by External Secrets Operator:

| ExternalSecret Key | Maps To | Purpose |
|---|---|---|
| `VK_REMOTE_JWT_SECRET` | `VIBEKANBAN_REMOTE_JWT_SECRET` | JWT signing key (48-byte base64) |
| `VK_REMOTE_LOCAL_AUTH_PASSWORD` | `SELF_HOST_LOCAL_AUTH_PASSWORD` | Admin login password |
| `VK_REMOTE_ELECTRIC_PASSWORD` | `ELECTRIC_ROLE_PASSWORD` | ElectricSQL PG role |
| `VK_REMOTE_PG_PASSWORD` | `POSTGRES_PASSWORD` | Main PG user password |

Same ClusterSecretStore, same ESO pattern as every other Frank app.

## IngressRoute and Authentik

The IngressRoute follows the standard Frank pattern — Traefik with IP allowlist, security headers, and Authentik forward-auth:

```yaml
# apps/traefik/manifests/ingressroutes.yaml (excerpt)
routes:
  - match: Host(`vk.cluster.derio.net`)
    kind: Rule
    middlewares:
      - name: ip-allowlist
      - name: security-headers
      - name: authentik-forwardauth
    services:
      - name: vk-remote
        namespace: agents
        port: 8081
tls:
  certResolver: cloudflare
  domains:
    - main: "*.cluster.derio.net"
```

An Authentik blueprint creates the proxy provider and application. The embedded outpost assignment is manual (Django ORM) — Authentik blueprints can create providers but can't assign them to outposts without clobbering existing assignments.

## Connecting the Agent

The secure-agent-pod just needs one environment variable to switch from cloud to self-hosted:

```yaml
# apps/secure-agent-pod/manifests/deployment.yaml (excerpt)
- name: VK_SHARED_API_BASE
  value: "http://vk-remote.agents.svc.cluster.local:8081"
```

The VK binary, MCP server, bridge, and all 33 MCP tools work unchanged. They all proxy through the local VK server which reads `VK_SHARED_API_BASE`. Zero code changes.

## What Changed

| File | Change |
|------|--------|
| `apps/vk-remote/manifests/namespace.yaml` | New `agents` namespace |
| `apps/vk-remote/manifests/externalsecret.yaml` | ExternalSecret for four Infisical secrets |
| `apps/vk-remote/manifests/postgres.yaml` | PVC + Deployment + Service for PG 16 |
| `apps/vk-remote/manifests/postgres-init-job.yaml` | PostSync Job for ElectricSQL role |
| `apps/vk-remote/manifests/electric.yaml` | ElectricSQL Deployment + Service |
| `apps/vk-remote/manifests/deployment.yaml` | vk-remote Deployment + Service |
| `apps/root/templates/vk-remote.yaml` | ArgoCD Application CR |
| `apps/traefik/manifests/ingressroutes.yaml` | IngressRoute for `vk.cluster.derio.net` |
| `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml` | Authentik proxy provider + application |
| `apps/secure-agent-pod/manifests/deployment.yaml` | `VK_SHARED_API_BASE` env var |
| `apps/homepage/manifests/configmap-services.yaml` | Homepage entry under Development |

## Domain Deviation

The spec originally called for `vk.frank.derio.net`, but Frank's Traefik wildcard cert covers `*.cluster.derio.net`. Using `vk.cluster.derio.net` avoids provisioning a new certificate. Pragmatism over naming purity.

<!-- MEDIA: screenshot | Self-hosted VK kanban board running on vk.cluster.derio.net | Navigate to https://vk.cluster.derio.net after Authentik login, capture the project board view with at least one issue in each lifecycle column, dark mode preferred -->
<!-- {{</* screenshot src="vk-remote-board.png" caption="Self-hosted VK board rendering issues from the local PostgreSQL + ElectricSQL backend" */>}} -->

## Gotchas

- ElectricSQL requires `wal_level=logical` on PostgreSQL — this is set via container args, not a config file. If you switch to a Helm chart later, make sure the Helm values preserve this.
- The PostSync Job uses `pg_isready` polling with a sleep loop. If PG is slow to start on a cold node, the Job may exhaust its backoff limit (5 retries). Delete the Job and let ArgoCD re-trigger it.
- The `agents` namespace is separate from `secure-agent-pod`. Cross-namespace DNS uses FQDN: `vk-remote.agents.svc.cluster.local:8081`.
- Data migration: there is none. The old cloud data is gone. Fresh project, fresh issues, fresh start.

## References

- [VibeKanban](https://github.com/BloopAI/vibe-kanban) — the agent orchestration tool
- [ElectricSQL](https://electric-sql.com/) — real-time sync engine for PostgreSQL
- [Post 21: Secure Agent Pod]({{< relref "/docs/building/21-secure-agent-pod" >}}) — the agent workstation that connects to vk-remote
- [Post 24: In-Cluster Ingress]({{< relref "/docs/building/24-in-cluster-ingress" >}}) — Traefik and Authentik forward-auth setup
- [Post 25: VK Relay]({{< relref "/docs/building/25-vk-relay" >}}) — the WebSocket relay sidecar added on top of this deployment
