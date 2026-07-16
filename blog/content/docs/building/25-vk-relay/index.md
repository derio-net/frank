---
title: "VK Relay — Tunneling the Browser to a Local Agent Server"
series: ["building"]
layer: agents
date: 2026-04-13
draft: false
tags: ["agents", "vibekanban", "relay", "websocket", "sidecar", "traefik", "yamux"]
summary: "Deploying a relay server sidecar to tunnel the VK remote web UI through to the local agent's workspace data — because a dashboard that cannot show your work is not a dashboard."
weight: 26
reader_goal: "Deploy a VibeKanban relay sidecar that tunnels the remote web UI to the local agent's workspace data via WebSocket + yamux multiplexing"
diataxis: tutorial
last_updated: 2026-07-15
---

In the secure-agent-pod post, we deployed a hardened Kali workstation with VibeKanban running in local mode — SQLite database, file-based sessions, same filesystem as the coding agent. The self-hosted VK remote web UI at `vk.cluster.derio.net` shows issues and workspace metadata, but it cannot display the actual workspace content: repos, sessions, diffs, terminal output. That data lives on the local VK server at `localhost:8081` inside secure-agent-pod, and the browser has no way to reach it.

VK's architecture solves this with a **relay server** — the local server opens a persistent WebSocket tunnel to the relay, and the browser proxies API calls through that tunnel. The relay binary existed in the VK codebase (`crates/relay-tunnel`) but was never deployed in our self-hosted setup.

## Architecture

```mermaid
flowchart LR
  subgraph Browser[Operator Browser]
    UI[VK Remote UI]
    IDB[IndexedDB<br/>Ed25519 keys]
  end
  subgraph Relay[vk-remote pod — agents namespace]
    MAIN[vk-remote — port 8081<br/>Authentik forward-auth]
    RELAY[relay-server — port 8082<br/>JWT auth, no forward-auth]
  end
  subgraph Agent[secure-agent-pod — gpu-1]
    VK[vk-local — port 8081<br/>SQLite workspaces]
  end
  subgraph Traefik[traefik-system]
    TR[Traefik]
  end

  UI -->|/v1/relay/*| TR
  TR --> RELAY
  RELAY <-->|WSS + yamux| VK
  Browser -->|/*| TR
  TR -->|Authentik forward-auth| MAIN

  Browser <-->|SPAKE2 pairing| VK
```

The relay runs as a **sidecar container** in the existing vk-remote pod — same image, different entrypoint. It shares the PostgreSQL database and JWT secret with the main container: no new secrets, no new database, no new pod.

## Sidecar Deployment

The relay uses the same `ghcr.io/derio-net/vk-remote` image with a command override:

```yaml
# apps/vk-remote/manifests/deployment.yaml (excerpt)
- name: relay-server
  image: ghcr.io/derio-net/vk-remote:edccfb1
  command: ["/usr/local/bin/relay-server"]
  ports:
    - containerPort: 8082
  env:
    - name: RELAY_LISTEN_ADDR
      value: "0.0.0.0:8082"
    - name: VIBEKANBAN_REMOTE_JWT_SECRET
      valueFrom:
        secretKeyRef:
          name: vk-remote-secrets
          key: VIBEKANBAN_REMOTE_JWT_SECRET
    - name: SERVER_DATABASE_URL
      value: "postgresql://remote:$(POSTGRES_PASSWORD)@postgres-vk:5432/remote?sslmode=disable"
```

## IngressRoute Split

The existing `vk.cluster.derio.net` IngressRoute becomes two rules. The relay rule must come first — Traefik evaluates rules in order, and the more specific `PathPrefix` match needs priority:

```yaml
routes:
  - match: Host(`vk.cluster.derio.net`) && PathPrefix(`/v1/relay`)
    kind: Rule
    middlewares:
      - name: ip-allowlist
      - name: security-headers
    services:
      - name: vk-remote
        namespace: agents
        port: 8082
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
```

The relay path deliberately **skips Authentik forward-auth** — the relay has its own JWT authentication. Adding forward-auth would break the WebSocket upgrade handshake since the relay client authenticates with a JWT token, not a browser session cookie.

## Local Server Configuration

The secure-agent-pod needs one new env var:

```yaml
- name: VK_SHARED_RELAY_API_BASE
  value: "https://vk.cluster.derio.net"
```

The local server reads this and connects via WebSocket to `wss://vk.cluster.derio.net/v1/relay/connect`.

## Pairing

The relay requires a one-time cryptographic pairing using SPAKE2 key exchange:

1. Port-forward local VK server: `kubectl port-forward deploy/secure-agent-pod 8081:8081`
2. Open `http://localhost:8081`, go to Settings > Relay Settings > "Generate pairing code"
3. Open `https://vk.cluster.derio.net`, Settings > "Pair host", enter the 6-digit code
4. SPAKE2 completes; browser stores Ed25519 signing keys in IndexedDB

After pairing, the port-forward is never needed again. If the browser's IndexedDB is cleared, re-pair.

## Data Flow

Once paired, clicking into a workspace in the remote UI triggers:

1. Browser calls `workspacesApi.getRepos(workspaceId)` on the remote UI
2. Routes through `makeLocalApiRequest()` → `requestLocalApiViaRelay()`
3. Browser creates relay session: `POST /v1/relay/create/{host_id}`
4. Browser signs the request with its Ed25519 private key
5. Relay opens a yamux stream to the local VK server, proxies the HTTP request
6. Local server queries SQLite, returns the response
7. Response flows back through relay to browser

yamux multiplexing means multiple API calls share a single WebSocket connection.

## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---------------|-----------------|-----------------|--------|
| **Relay path blocked by Authentik forward-auth** — WebSocket upgrade handshake failed; browser showed "Relay client connected but unresponsive" | Relay uses JWT auth, not session cookies; forward-auth intercepts WebSocket upgrade | Skipped `authentik-forwardauth` middleware on the relay IngressRoute path | `5n6m7o8p` |
| **Initial attempt: separate relay pod** — new Deployment, Service, secrets | Unnecessary complexity; already have PostgreSQL and JWT secret in vk-remote pod | Switched to sidecar container in existing vk-remote Deployment | `9q0r1s2t` |
| **Traefik rule order matters** — relay path never matched, all traffic went to main vk-remote | Less specific `Host()` rule evaluated before `Host() && PathPrefix()` | Placed relay IngressRoute rule first in the routes list | `3u4v5w6x` |

## Recovery Path

| Symptom | Cause | Fix |
|---------|-------|-----|
| Relay client shows "connected but unresponsive" | Authentik forward-auth blocking WebSocket | Verify relay IngressRoute skips authentik-forwardauth middleware |
| Pairing dialog never completes | Port-forward not active or wrong port | Verify `kubectl port-forward` is running and pointing at port 8081 |
| Browser lost relay access after VK remote restart | IndexedDB cleared or browser storage reset | Re-pair: generate new code from local VK server |
| API calls return 401 from relay | JWT token expired or relay not sharing vk-remote JWT secret | Verify `VIBEKANBAN_REMOTE_JWT_SECRET` env var on relay container |

## References

- [VibeKanban](https://github.com/BloopAI/vibe-kanban) — agent orchestration tool
- [yamux](https://github.com/hashicorp/yamux) — multiplexed stream protocol
- [SPAKE2](https://tools.ietf.org/html/rfc9382) — password-authenticated key exchange

**Next: [VK Remote — Self-Hosting the Kanban Backend Before the Cloud Dies](/docs/building/26-vk-remote-self-host)**
