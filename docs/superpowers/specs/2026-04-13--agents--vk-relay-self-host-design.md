# VK Relay Self-Host Design

**Decision point:** End of July 2026 — extend 80% employment or return to 100%
**Date:** 2026-04-13

## Problem

The self-hosted VK remote web UI at `vk.cluster.derio.net` shows issues and workspace metadata (synced via the remote API), but cannot display workspace details — repos, sessions, diffs, terminal output. These are served by the local VK server (`localhost:8081` in the secure-agent-pod) via `/api/` endpoints that the browser cannot reach directly.

The VK architecture uses a **relay server** to bridge this gap: the local server opens a persistent WebSocket tunnel to the relay, and the browser proxies API calls through that tunnel. The relay binary exists in the VK codebase (`crates/relay-tunnel`) but was never deployed in the self-hosted setup.

## Architecture

```
Browser → vk.cluster.derio.net (Traefik)
  ├── /v1/relay/* → relay sidecar:8082 (JWT auth, no Authentik)
  │     ↔ WSS tunnel (yamux multiplexed)
  │     ↔ local VK server in secure-agent-pod:8081
  └── /* → vk-remote:8081 (Authentik forward-auth + web UI + API)
```

### Relay Server Sidecar

Deploy the relay server as a sidecar container in the existing vk-remote pod (`agents` namespace):

- **Image:** Same as vk-remote — add `relay-server` binary to the existing Dockerfile build
- **Entrypoint override:** `/usr/local/bin/relay-server`
- **Port:** 8082 (configurable via `RELAY_LISTEN_ADDR`)
- **Database:** Shares the same PostgreSQL via `SERVER_DATABASE_URL` (from existing ExternalSecret)
- **JWT:** Shares `VIBEKANBAN_REMOTE_JWT_SECRET` (from existing ExternalSecret)
- **No new secrets or database required**

### IngressRoute Split

Split the existing `vk.cluster.derio.net` IngressRoute into two rules:

1. **Relay rule** (new): `Host(vk.cluster.derio.net) && PathPrefix(/v1/relay)`
   - Routes to relay sidecar service on port 8082
   - Middlewares: `ip-allowlist`, `security-headers` only — **no Authentik forward-auth**
   - The relay has its own JWT authentication at the application level
   - Must support WebSocket upgrades for the `/v1/relay/connect` endpoint

2. **Default rule** (existing, narrowed): `Host(vk.cluster.derio.net)`
   - Routes to vk-remote on port 8081
   - Keeps all existing middlewares including `authentik-forwardauth`

### Local Server Configuration

Add `VK_SHARED_RELAY_API_BASE` environment variable to the secure-agent-pod deployment:

- **Value:** `https://vk.cluster.derio.net`
- The local VK server reads this and connects via WSS to `wss://vk.cluster.derio.net/v1/relay/connect`
- Registration uses the existing JWT token from `VK_SHARED_API_BASE` authentication
- The `relay_enabled` config flag defaults to `true` — no config file changes needed

### Browser Configuration

No changes required. The remote-web UI reads `VITE_RELAY_API_BASE_URL` at build time, falling back to the remote server URL (`window.location.origin`). Since the relay is served from the same domain, the fallback works without a rebuild.

## Pairing (Manual, One-Time)

The relay requires a cryptographic pairing between the browser and the local server:

1. Port-forward the local VK server: `kubectl -n secure-agent-pod port-forward deploy/secure-agent-pod 8081:8081`
2. Open `http://localhost:8081` in the browser
3. Go to Settings → Relay Settings → "Generate pairing code" — note the 6-digit code
4. Open `https://vk.cluster.derio.net` in the browser
5. Go to Settings → "Pair host" → enter the 6-digit code
6. SPAKE2 key exchange completes, browser stores Ed25519 signing keys in IndexedDB

After pairing, the relay handles all communication. The port-forward is never needed again unless re-pairing (e.g., browser data cleared).

## Data Flow (Post-Pairing)

1. Browser calls `workspacesApi.getRepos(workspaceId)` → `/api/workspaces/{id}/repos`
2. `web-core` routes this through `makeLocalApiRequest()` → `requestLocalApiViaRelay()`
3. Browser creates relay session: `POST /v1/relay/create/{host_id}` → session_id
4. Browser signs request with Ed25519 private key
5. Sends to relay: `GET /v1/relay/h/{host_id}/s/{session_id}/api/workspaces/{id}/repos`
6. Relay opens yamux stream to local VK server, proxies HTTP request
7. Local server queries SQLite `workspace_repos` + `repos`, returns response
8. Response flows back through relay to browser
9. After first successful request, WebRTC P2P upgrade is attempted for lower latency

## Dockerfile Changes (vk-remote)

Add `relay-server` binary to the existing `crates/remote/Dockerfile`:

- Build stage: `cargo build --release --bin server --bin relay-server`
- Final stage: `COPY --from=builder /usr/local/bin/relay-server /usr/local/bin/relay-server`
- No change to `ENTRYPOINT` — the sidecar uses command override

Also add to `build-remote.yml` CI workflow if needed (path triggers for `crates/relay-tunnel/**`).

## Relay Database Schema

The relay server uses tables in the same PostgreSQL database as vk-remote. Required tables (from `crates/relay-tunnel/src/server_bin/db/`):

- `relay_hosts` — registered hosts (machine_id, user_id, name, status, last_seen)
- `relay_browser_sessions` — active browser sessions per host
- Auth tables are shared with vk-remote (users, JWT validation)

These tables are NOT auto-migrated by the relay server — it expects them to exist. They must be added as a migration in the vk-remote crate (`crates/remote/migrations/`) so they're created when vk-remote runs. The relay server's `crates/relay-tunnel/src/server_bin/db/` module defines the expected schema via `sqlx` queries — extract the DDL from there.

## Scope

**In scope:**
- Relay server sidecar deployment
- IngressRoute split (relay paths bypass Authentik)
- `VK_SHARED_RELAY_API_BASE` env var for secure-agent-pod
- Dockerfile update to include relay-server binary
- One-time manual pairing step

**Out of scope:**
- Multi-user / multi-host support (single operator, single local server)
- Relay HA / scaling (single replica sufficient)
- VK codebase changes (relay code works as-is)
- Automated pairing (manual one-time port-forward is acceptable)

## Implementation Plans

| Plan | Repo | Status |
|------|------|--------|
| VK Relay Deployment | frank | Not Started |
| VK Relay Binary + Migration | vibe-kanban | Not Started |
