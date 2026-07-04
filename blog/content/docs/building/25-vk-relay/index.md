---
title: "VK Relay — Tunneling the Browser to a Local Agent Server"
series: ["building"]
layer: agents
date: 2026-04-13
draft: false
tags: ["agents", "vibekanban", "relay", "websocket", "sidecar", "traefik", "yamux"]
summary: "Deploying a relay server sidecar to tunnel the VK remote web UI through to the local agent's workspace data — because a dashboard that can't show your work isn't a dashboard."
weight: 26
---

In [Post 21]({{< relref "/docs/building/21-secure-agent-pod" >}}), we deployed a hardened Kali workstation with VibeKanban running in local mode — SQLite database, file-based sessions, same filesystem as the coding agent. The self-hosted VK remote web UI at `vk.cluster.derio.net` shows issues and workspace metadata (synced via the remote API), but it can't display the actual workspace content: repos, sessions, diffs, terminal output. That data lives on the local VK server at `localhost:8081` inside the secure-agent-pod, and the browser has no way to reach it.

The VK architecture solves this with a **relay server** — the local server opens a persistent WebSocket tunnel to the relay, and the browser proxies API calls through that tunnel. The relay binary existed in the VK codebase (`crates/relay-tunnel`) but was never deployed in our self-hosted setup. This post fixes that.

## Architecture

```
Browser --> vk.cluster.derio.net (Traefik)
  |-- /v1/relay/* --> relay sidecar:8082 (JWT auth, no Authentik)
  |     <-> WSS tunnel (yamux multiplexed)
  |     <-> local VK server in secure-agent-pod:8081
  '-- /* --> vk-remote:8081 (Authentik forward-auth + web UI + API)
```

The relay runs as a **sidecar container** in the existing vk-remote pod. Same image, different entrypoint. It shares the PostgreSQL database and JWT secret with the main container — no new secrets, no new database, no new pod. The local VK server in the secure-agent-pod connects outbound to the relay via WebSocket, so there's no inbound networking required to the agent pod.

## Sidecar Deployment

The relay container uses the same `ghcr.io/derio-net/vk-remote` image as the main container, with a command override to run the relay binary:

```yaml
# apps/vk-remote/manifests/deployment.yaml (excerpt)
- name: relay-server
  image: ghcr.io/derio-net/vk-remote:edccfb1
  command: ["/usr/local/bin/relay-server"]
  ports:
    - containerPort: 8082
      protocol: TCP
  env:
    - name: RELAY_LISTEN_ADDR
      value: "0.0.0.0:8082"
    - name: VIBEKANBAN_REMOTE_JWT_SECRET
      valueFrom:
        secretKeyRef:
          name: vk-remote-secrets
          key: VIBEKANBAN_REMOTE_JWT_SECRET
    - name: POSTGRES_PASSWORD
      valueFrom:
        secretKeyRef:
          name: vk-remote-secrets
          key: POSTGRES_PASSWORD
    - name: SERVER_DATABASE_URL
      value: "postgresql://remote:$(POSTGRES_PASSWORD)@postgres-vk:5432/remote?sslmode=disable"
  resources:
    requests:
      cpu: 50m
      memory: 64Mi
    limits:
      cpu: 200m
      memory: 128Mi
```

The Service adds port 8082 alongside the existing 8081, and Traefik routes based on path prefix.

## IngressRoute Split

The existing `vk.cluster.derio.net` IngressRoute becomes two rules. The relay rule must come first — Traefik evaluates rules in order, and the more specific `PathPrefix` match needs priority:

```yaml
# apps/traefik/manifests/ingressroutes.yaml (excerpt)
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
    services:
      - name: vk-remote
        namespace: agents
        port: 8081
```

The relay path deliberately **skips Authentik forward-auth** — the relay has its own JWT authentication at the application level. Adding forward-auth would break the WebSocket upgrade handshake since the relay client (the local VK server) authenticates with a JWT token, not a browser session cookie.

## Local Server Configuration

The secure-agent-pod needs one new env var to tell the local VK server where the relay lives:

```yaml
# apps/secure-agent-pod/manifests/deployment.yaml (excerpt)
- name: VK_SHARED_RELAY_API_BASE
  value: "https://vk.cluster.derio.net"
```

The local server reads this and connects via WebSocket to `wss://vk.cluster.derio.net/v1/relay/connect`. Registration uses the existing JWT token from `VK_SHARED_API_BASE` authentication. The `relay_enabled` config flag defaults to `true`, so no config file changes are needed.

## Pairing

The relay requires a one-time cryptographic pairing between the browser and the local server using SPAKE2 key exchange:

1. Port-forward the local VK server: `kubectl -n secure-agent-pod port-forward deploy/secure-agent-pod 8081:8081`
2. Open `http://localhost:8081` in the browser, go to Settings > Relay Settings > "Generate pairing code"
3. Open `https://vk.cluster.derio.net`, go to Settings > "Pair host", enter the 6-digit code
4. SPAKE2 completes, browser stores Ed25519 signing keys in IndexedDB

After pairing, the port-forward is never needed again. The relay handles all communication going forward — unless the browser's IndexedDB is cleared, in which case you re-pair.

{{< screenshot src="vk-relay-pairing.png" caption="Browser-side pairing dialog where the SPAKE2 code from the local VK server is entered" >}}

## Data Flow

Once paired, here's what happens when you click into a workspace in the remote UI:

1. Browser calls `workspacesApi.getRepos(workspaceId)` on the remote UI
2. The web app routes this through `makeLocalApiRequest()` into `requestLocalApiViaRelay()`
3. Browser creates a relay session: `POST /v1/relay/create/{host_id}`
4. Browser signs the request with its Ed25519 private key
5. Request goes to the relay: `GET /v1/relay/h/{host_id}/s/{session_id}/api/workspaces/{id}/repos`
6. Relay opens a yamux stream to the local VK server, proxies the HTTP request
7. Local server queries SQLite, returns the response
8. Response flows back through the relay to the browser

The yamux multiplexing means multiple API calls share a single WebSocket connection. After the first successful relay request, the browser attempts a WebRTC P2P upgrade for lower latency — but the relay remains the reliable fallback.

## What Changed

| File | Change |
|------|--------|
| `apps/vk-remote/manifests/deployment.yaml` | Added relay-server sidecar container + relay port on Service |
| `apps/traefik/manifests/ingressroutes.yaml` | Split VK route: `/v1/relay/*` to port 8082, everything else to 8081 |
| `apps/secure-agent-pod/manifests/deployment.yaml` | Added `VK_SHARED_RELAY_API_BASE` env var |

Three files, one sidecar, zero new secrets. The relay reuses everything that was already deployed for the VK remote server.

## References

- [VibeKanban](https://github.com/BloopAI/vibe-kanban) — the agent orchestration tool
- [yamux](https://github.com/hashicorp/yamux) — multiplexed stream protocol over a single connection
- [SPAKE2](https://tools.ietf.org/html/rfc9382) — password-authenticated key exchange
- [Post 21: Secure Agent Pod]({{< relref "/docs/building/21-secure-agent-pod" >}}) — the hardened workstation this relay connects to
- [Post 24: In-Cluster Ingress]({{< relref "/docs/building/24-in-cluster-ingress" >}}) — the Traefik IngressRoute setup this extends
