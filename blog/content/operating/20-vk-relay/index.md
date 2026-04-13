---
title: "Operating on VK Relay"
date: 2026-04-13
draft: false
tags: ["operations", "agents", "vibekanban", "relay", "websocket", "troubleshooting"]
summary: "Day-to-day commands for the VK relay server — health checks, tunnel status, re-pairing, and troubleshooting the browser-to-agent connection."
weight: 120
cover:
  image: cover.png
  alt: "Frank checking relay connection status on a monitoring dashboard"
  relative: true
---

This is the operational companion to [VK Relay — Tunneling the Browser to a Local Agent Server]({{< relref "/building/25-vk-relay" >}}). That post explains the architecture and deployment. This one is the day-to-day runbook.

## What "Healthy" Looks Like

A healthy VK relay setup has:
- The `vk-remote` pod running with **two containers**: `vk-remote` and `relay-server`
- Relay server listening on port 8082
- The `/v1/relay/` path reachable through Traefik at `vk.cluster.derio.net`
- The local VK server in the secure-agent-pod connected via WebSocket tunnel
- Browser paired and able to view workspace data through the remote UI

## Observing State

### Pod Health

```bash
# Verify both containers are running
kubectl -n agents get pods -l app=vk-remote -o wide

# Check container names (should list: vk-remote relay-server)
kubectl -n agents get pods -l app=vk-remote \
  -o jsonpath='{.items[0].spec.containers[*].name}'
```

### Relay Server Logs

```bash
# Relay server logs
kubectl -n agents logs deploy/vk-remote -c relay-server --tail=20

# Follow relay logs (useful during pairing or debugging)
kubectl -n agents logs deploy/vk-remote -c relay-server -f
```

Expected healthy output includes: `Relay server listening on 0.0.0.0:8082`

### Relay Endpoint Reachability

```bash
# Test relay endpoint through Traefik (expect 401 — JWT auth required)
curl -s -o /dev/null -w "%{http_code}" https://vk.cluster.derio.net/v1/relay/connect
```

A `401` means the relay is running and reachable — it's rejecting the request because there's no JWT token. A `404` means the IngressRoute isn't routing correctly. A `502` means the relay container is down.

### Service Ports

```bash
# Verify both ports are exposed
kubectl -n agents get svc vk-remote
# Expected: 8081/TCP (http) and 8082/TCP (relay)
```

## Common Operations

### Restart the Relay

The relay is a sidecar in the vk-remote pod — restarting the pod restarts both containers:

```bash
kubectl -n agents rollout restart deploy/vk-remote
kubectl -n agents rollout status deploy/vk-remote
```

### Re-Pairing

If the browser loses its IndexedDB data (cleared storage, new browser, new device), re-pair:

1. Port-forward to the local VK server:
   ```bash
   kubectl -n secure-agent-pod port-forward deploy/secure-agent-pod 8081:8081
   ```
2. Open `http://localhost:8081` → Settings → Relay Settings → "Generate pairing code"
3. Open `https://vk.cluster.derio.net` → Settings → "Pair host" → enter code
4. Stop the port-forward — the relay handles everything from here

### Check Local Server Relay Connection

```bash
# Check if the local VK server is connected to the relay
kubectl -n secure-agent-pod logs deploy/secure-agent-pod -c kali --tail=50 | grep -i relay
```

If the local server isn't connecting, verify the env var is set:

```bash
kubectl -n secure-agent-pod exec deploy/secure-agent-pod -c kali -- \
  env | grep VK_SHARED_RELAY
# Expected: VK_SHARED_RELAY_API_BASE=https://vk.cluster.derio.net
```

## Troubleshooting

### Workspace Data Not Loading in Remote UI

**Symptom:** The remote UI at `vk.cluster.derio.net` shows workspaces but clicking into one shows no repos, sessions, or diffs.

**Check:** Is the relay tunnel established?

```bash
# Relay logs — look for active tunnel connections
kubectl -n agents logs deploy/vk-remote -c relay-server --tail=30
```

If no tunnel connections appear, the local VK server isn't connecting. Check:
1. The secure-agent-pod is running
2. `VK_SHARED_RELAY_API_BASE` env var is set
3. Cilium egress policy allows outbound to `vk.cluster.derio.net`

### 502 on Relay Path

**Symptom:** `curl https://vk.cluster.derio.net/v1/relay/connect` returns 502.

**Cause:** The relay-server container is not running or not ready.

```bash
# Check container status
kubectl -n agents describe pod -l app=vk-remote | grep -A5 relay-server

# Check for crash loops
kubectl -n agents logs deploy/vk-remote -c relay-server --previous
```

### Pairing Code Rejected

**Symptom:** Entering the 6-digit pairing code in the remote UI fails.

**Causes:**
- Code expired (codes are short-lived — generate a fresh one)
- Browser and local server not on the same relay (verify both point to `vk.cluster.derio.net`)
- SPAKE2 mismatch — regenerate and try again

## ArgoCD Sync

```bash
# Check vk-remote app status
argocd app get vk-remote --port-forward --port-forward-namespace argocd

# Force sync if needed
argocd app sync vk-remote --port-forward --port-forward-namespace argocd
```

## References

- [Building Post: VK Relay]({{< relref "/building/25-vk-relay" >}})
- [Operating on Secure Agent Pod]({{< relref "/operating/14-secure-agent-pod" >}})
