# RustDesk Relay Server on Frank — Design Spec

*Date: 2026-04-07*

## Overview

Deploy a self-hosted RustDesk relay (hbbs + hbbr) on Frank to support remote desktop access for the kid-laptops project. The relay handles connection brokering and traffic relay for RustDesk clients on the three laptops.

**Parent project:** [`derio-net/kid-laptops`](https://github.com/derio-net/kid-laptops) — see `docs/superpowers/specs/2026-04-07-kid-laptops-design.md`

## Why Self-Hosted

- RustDesk's public relay servers are slow and unreliable
- Self-hosted relay on Frank keeps all traffic on the tailnet (private, low latency)
- No dependency on external infrastructure for remote support

## Architecture

### Components

| Component | Purpose | Port |
|-----------|---------|------|
| `hbbs` | Rendezvous/signaling server | 21115 (TCP), 21116 (TCP+UDP) |
| `hbbr` | Relay server (traffic relay when direct P2P fails) | 21117 (TCP) |

### Deployment

- **Namespace:** `rustdesk` (or appropriate service namespace per Frank conventions)
- **Method:** ArgoCD application, Helm chart or raw manifests
- **Image:** `rustdesk/rustdesk-server` (official Docker image)
- **Storage:** Persistent volume for keypair (`id_ed25519` / `id_ed25519.pub`) — generated on first run, must survive restarts
- **Resources:** Lightweight — minimal CPU/memory. No GPU needed.

### Networking

- Exposed on Tailscale only — no public ingress
- Laptops connect to the relay via its Tailscale IP/hostname
- Firewall: ports 21115-21117 open within the tailnet only

### Security

- RustDesk generates an Ed25519 keypair on first run
- The public key is distributed to all laptop clients via Ansible (`group_vars/all.yml`)
- Clients are configured to only trust this relay (no fallback to public relays)
- Encryption key ensures only authorised clients can use the relay

## Configuration

The relay's Tailscale address and public key are consumed by the kid-laptops Ansible repo:

```yaml
# kid-laptops/inventory/group_vars/all.yml
rustdesk_relay_host: "rustdesk.frank.tailnet"  # Tailscale hostname
rustdesk_relay_key: "<ed25519-public-key>"      # From hbbs first-run
```

## Dependencies

- Frank cluster operational
- Tailscale configured on Frank
- ArgoCD for deployment (per Frank conventions)

## Out of Scope

- RustDesk web client (not needed — native clients on laptops)
- Public internet access to the relay
- High availability (single instance is sufficient for 3 laptops)
