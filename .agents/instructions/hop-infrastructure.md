## Hop Cluster

Hetzner Cloud edge cluster — standalone talosctl (not Omni-managed), single control-plane+worker node.

### Node

| Host  | IP                     | Role                 | Zone                | Key Hardware       |
|-------|------------------------|----------------------|---------------------|--------------------|
| hop-1 | $HOP_IP (see .env_hop) | control-plane+worker | Edge (Hetzner fsn1) | CX23, 2 vCPU, 4GB |

### Services

| Service | Domain | Exposed Via |
|---------|--------|-------------|
| Headscale | headscale.hop.derio.net | Caddy (public) |
| Headplane | headplane.hop.derio.net | Caddy (mesh only) |
| Blog | blog.derio.net/frank | Caddy (public) |
| Landing | entry.hop.derio.net | Caddy (mesh only) |

### Apps Layout

```
clusters/hop/apps/
  root/        # Entry point for Hop's Application CRs
  argocd/      # ArgoCD values (minimal single-replica)
  headscale/   # Headscale mesh + Tailscale DaemonSet
  headplane/   # Headscale web UI
  caddy/       # Reverse proxy + TLS (Cloudflare DNS challenge)
  blog/        # Hugo blog container deployment
  landing/     # Private landing page (mesh-only)
  storage/     # Static PVs for Hetzner Volume
clusters/hop/packer/         # Packer template for Hetzner Talos image
clusters/hop/talosconfig/    # Talos client config (gitignored, contains secrets)
```
