# VK Remote Self-Host — Design Spec

**Layer:** agents (12 — Agentic Control Plane)
**Date:** 2026-04-12
**Status:** Spec

## Problem

VibeKanban (VK) announced shutdown on 2026-04-10. Cloud services (projects, issues, organizations, comments) go dark in 30 days. The OAuth flow for the `clawdia-ai-assistant@gmail.com` account already fails — likely early decomissioning.

VK provides critical orchestration for our agentic workflow:
- Multi-repo kanban board (visual tracking of work across repos)
- Issue/project management via MCP API (33 tools)
- PR status polling and lifecycle transitions
- GitHub Issue → VK card → workspace bridge

Local VK features (workspaces, sessions, git worktrees, agent spawning) survive the shutdown. The kanban/issue layer does not — it lives in the `/remote` crate backed by PostgreSQL.

**The remote crate already supports self-hosting with local auth.** We deploy it on Frank.

## Approach

Deploy VK's `crates/remote/` as a Kubernetes service on Frank. Connect the existing secure-agent-pod's VK binary to our self-hosted instance via `VK_SHARED_API_BASE`. The bridge, MCP tools, and superpowers-for-vk skills continue working unchanged.

### Components

| Component | Image | Port | Purpose |
|-----------|-------|------|---------|
| vk-remote | Built from fork (GHCR) | 8081 | Kanban API server (Rust/Axum) |
| postgres-vk | PostgreSQL 16 Alpine | 5432 | Issue/project data, logical replication |
| electric | ElectricSQL 1.4.13 | 3000 (internal) | Real-time sync engine for frontend |

### Network Topology

```
secure-agent-pod (VK local binary)
  └── VK_SHARED_API_BASE=http://vk-remote.agents.svc:8081
        └── vk-remote (Rust, port 8081)
              ├── postgres-vk (dedicated PG 16, WAL logical)
              └── electric (sync engine, reads PG WAL)

Operator laptop (browser)
  └── https://vk.frank.derio.net (Traefik IngressRoute)
        └── vk-remote:8081
```

## Design Decisions

### Dedicated PostgreSQL

VK's ElectricSQL requires `wal_level=logical` which creates overhead on shared PG instances. A dedicated lightweight PG 16 avoids risk to n8n's database.

Resource allocation: 256Mi RAM, 1Gi PVC (issues/projects are tiny).

### No OAuth — Local Auth Only

Single-user self-hosted mode:
```
SELF_HOST_LOCAL_AUTH_EMAIL=admin@localhost
SELF_HOST_LOCAL_AUTH_PASSWORD=<from Infisical>
```

No Google/GitHub OAuth provider configuration needed. POST to `/v1/auth/local/login` returns JWT tokens. The secure-agent-pod's bridge authenticates this way.

### Fork Strategy

Fork `BloopAI/vibe-kanban` to `derio-net/vibe-kanban`. Build the remote crate via GitHub Actions, push to GHCR. This gives us:
- Control over the image
- Ability to patch if needed
- Reproducible builds pinned to a commit

The fork tracks upstream's open-source release. Minimal patches — only what's needed to build and run `crates/remote/`.

### ElectricSQL

Required for the VK frontend's real-time sync (the board updates live as issues change status). Lightweight container, no external dependencies — just reads PG's logical replication stream.

### No Optional Services

Skip for now (can add later if needed):
- ~~Cloudflare R2 / Azure Blob~~ — No file attachments needed
- ~~Loops email~~ — No email notifications (single user)
- ~~Stripe billing~~ — Self-hosted, free
- ~~GitHub App~~ — PR integration via `gh` CLI in the bridge
- ~~Relay tunnel~~ — Direct network access on Frank
- ~~PostHog / Application Insights~~ — No analytics

### Secrets Management

Via Infisical (existing pattern on Frank):
- `VIBEKANBAN_REMOTE_JWT_SECRET` — Generated once, 48-byte base64
- `SELF_HOST_LOCAL_AUTH_PASSWORD` — Simple password for local login
- `ELECTRIC_ROLE_PASSWORD` — PG role password for ElectricSQL
- `SERVER_DATABASE_URL` — PG connection string

### Namespace

Deploy in `agents` namespace alongside secure-agent-pod. Shared concerns, same Cilium policies (with additions for VK remote's needs).

## What Changes in Existing Infrastructure

### secure-agent-pod

Add environment variable:
```yaml
- name: VK_SHARED_API_BASE
  value: "http://vk-remote.agents.svc:8081"
```

### vk-issue-bridge

Update hardcoded `VK_ORG_ID` and `VK_DERIO_OPS_PROJECT` to match the new self-hosted org/project IDs (created on first login). The bridge script at `secure-agent-kali/scripts/vk-issue-bridge.py` reads these from env vars — set them in the deployment.

### MCP Server

The MCP server (`npx vibe-kanban --mcp`) in the secure-agent-pod already talks to the local VK binary, which proxies to `VK_SHARED_API_BASE`. No MCP changes needed.

### Cilium NetworkPolicy

Add egress rule allowing secure-agent-pod → vk-remote on port 8081 (same namespace, should be allowed by default, but verify).

## Migration Plan

### Data

No data migration needed. The old cloud projects/issues are lost (cloud is dying). We create fresh:
1. Login creates personal org automatically
2. Create "Derio Ops" project manually (or via API)
3. Configure statuses to match existing workflow: Backlog, Todo, In Progress, In Review, Done
4. Update bridge env vars with new org/project IDs

### Verification

1. `curl http://vk-remote.agents.svc:8081/v1/health` returns OK
2. Login via `/v1/auth/local/login` returns JWT
3. Create project via API, create issue, verify in browser at `vk.frank.derio.net`
4. Bridge creates a VK card from a `vk-ready` GitHub Issue
5. MCP tools (`list_issues`, `create_issue`, `update_issue`) work from secure-agent-pod

## What Stays Unchanged

- VK local binary (workspaces, sessions, agent spawning) — untouched
- superpowers-for-vk skills (vk-plan, vk-dispatch, vk-execute, vk-progress) — unchanged
- GitHub Issues as source of truth — unchanged
- Bridge logic — same flow, different VK backend URL
- Secure-agent-pod image — only env var addition

## Resource Estimates

| Component | CPU | Memory | Storage |
|-----------|-----|--------|---------|
| vk-remote | 100m/500m | 128Mi/256Mi | — |
| postgres-vk | 100m/500m | 256Mi/512Mi | 1Gi PVC |
| electric | 50m/200m | 64Mi/128Mi | — |
| **Total** | 250m/1200m | 448Mi/896Mi | 1Gi |

Fits comfortably on Frank's existing capacity.

## Timeline

Target: operational within 1 week (before cloud degradation accelerates).

- Phase 0 [manual]: Fork repo, set up GHCR build workflow
- Phase 1 [agentic]: Frank manifests (Deployment, Service, IngressRoute, PG StatefulSet, ElectricSQL, Secrets)
- Phase 2 [manual]: Deploy, verify login, create project, configure bridge, end-to-end test
