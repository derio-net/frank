# Phase XX — Hop: Public Edge Entrypoint

**Date:** 2026-03-16
**Status:** Design
**Phase:** XX (assigned on implementation)

## Overview

Deploy a Hetzner Cloud VPS running Talos Linux as a public-facing edge node ("Hop"), managed by Omni as a separate single-node cluster. Hop provides three capabilities:

1. **Headscale mesh** — self-hosted Tailscale coordination server enabling remote access to the entire homelab via VLAN 10 subnet routers
2. **Public web presence** — Hugo blog at `blog.derio.net/frank` and portfolio at `www.derio.net`, served by Caddy
3. **Private landing page** — `entry.hop.derio.net`, accessible only to mesh members

Two dedicated Raspberry Pis on VLAN 10 (Services) act as Tailscale subnet routers, advertising home network routes through the mesh. These are outside Frank and Hop — standalone devices managed independently.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │         Hetzner Cloud CX22 (Hop)            │
                    │         Talos Linux · Omni-managed          │
                    │                                             │
  Internet ────▶   │  ┌────────────────────────────────────┐     │
  :80/:443         │  │ Caddy (hostPort 80/443)            │     │
                    │  │  *.hop.derio.net  (wildcard cert)  │     │
                    │  │  blog.derio.net   (public)         │     │
                    │  │  www.derio.net    (public)         │     │
                    │  └──┬──────┬──────┬──────┬───────────┘     │
                    │     │      │      │      │                  │
                    │     ▼      ▼      ▼      ▼                  │
                    │  Headscale Headplane Blog  Landing           │
                    │  (public)  (mesh)  (pub)  (mesh)            │
                    │     │                                        │
                    │     │  Hetzner Volume (10GB)                 │
                    │     │  ├── headscale.db                     │
                    │     │  └── caddy certs                      │
                    │     │                                        │
                    │  ArgoCD (Hop instance)                      │
                    └─────┼───────────────────────────────────────┘
                          │
              WireGuard mesh (Tailscale protocol)
                          │
         ┌────────────────┼────────────────┐
         │                │                │
         ▼                ▼                ▼
    Phone/Laptop    RPi subnet-1     RPi subnet-2
    (Tailscale      (VLAN 10)        (VLAN 10)
     client)        advertises       advertises
                    home routes      home routes
                         │                │
                         ▼                ▼
                    ┌─────────────────────────┐
                    │  Home Network            │
                    │  VLAN 10 (Services)      │
                    │    → routes to VLAN 55   │
                    │      (Frank cluster)     │
                    │    → routes to other     │
                    │      homelab services    │
                    └─────────────────────────┘
```

## Hetzner Provisioning

**Node:** CX22 (2 vCPU, 4GB RAM, 40GB disk, ~€3.49/mo)
**Storage:** Hetzner Volume 10GB (~€0.48/mo)
**Location:** EU (e.g., `hel1` Helsinki or `fsn1` Falkenstein)

**Image build workflow:**

1. Download Talos installation media from Omni dashboard — select "Hetzner" variant (includes Omni join credentials + hcloud platform extensions)
2. Packer builds a Hetzner Cloud snapshot from the image (rescue mode → `dd` → snapshot)
3. `hcloud server create --image <SNAPSHOT_ID> --type cx22 --location <loc>`
4. Server auto-registers with Omni, allocate to "hop" cluster

Packer config lives at `clusters/hop/packer/`.

## Hop Cluster Configuration

**Single-node Talos cluster in Omni:**
- Control plane + worker on same node
- CNI: Flannel (default) — Cilium is unnecessary for a single public node
- No LoadBalancer abstraction — Caddy uses `hostPort` on 80/443

**Workloads:**

| App | Type | Source | Notes |
|-----|------|--------|-------|
| ArgoCD | Helm chart | Upstream | Minimal single-replica install (~512MB RAM), manages Hop's app-of-apps |
| Headscale | Raw manifests | `headscale/headscale` container | Coordination server, gRPC + HTTPS, embedded DERP |
| Headplane | Raw manifests | Container image | Web UI for Headscale |
| Caddy | Raw manifests | Container image | Reverse proxy, TLS, static file serving |
| Blog | Raw manifests | `ghcr.io/derio-net/blog` | Hugo static output baked into container |

**Storage:**
- Hetzner Volume (10GB) attached as a block device, mounted via Talos machine config (`extraMounts`)
- Static PV + PVC pointing to the host mount path — no CSI driver needed
- Used for: Headscale SQLite DB, Caddy certificate storage
- Survives node reimaging (Hetzner Volume persists independently of the server)

## Networking & DNS

**DNS records (Cloudflare):**

| Record | Type | Value | Proxy |
|--------|------|-------|-------|
| `*.hop.derio.net` | A | Hetzner public IP | No (Caddy manages TLS) |
| `blog.derio.net` | A | Hetzner public IP | No |
| `www.derio.net` | A | Hetzner public IP | No |

**Caddy routes:**

| Domain | Target | Access |
|--------|--------|--------|
| `headscale.hop.derio.net` | Headscale gRPC/HTTPS | Public (clients must reach it) |
| `headplane.hop.derio.net` | Headplane UI | Private (Tailscale CGNAT source IPs only) |
| `entry.hop.derio.net` | Landing page | Private (Tailscale CGNAT source IPs only) |
| `blog.derio.net` | Blog container | Public |
| `www.derio.net` | Portfolio/personal site | Public |

**Private route enforcement:** Caddy `remote_ip` matcher restricts to `100.64.0.0/10` (Tailscale CGNAT range). Non-mesh requests get 403.

## Headscale Mesh

**Headscale** runs on Hop as the coordination server. It manages:
- Client registrations (phone, laptop)
- Subnet router approvals (RPi subnet routers)
- ACL policies (which clients can reach which subnets)
- DNS configuration (optional: MagicDNS for mesh hostnames)
- **Embedded DERP server** — Headscale runs its own DERP relay for NAT traversal, sharing port 443 with Caddy via path-based routing (`/derp` path proxied from Caddy to Headscale's DERP listener). Public Tailscale DERP servers used as fallback.

**Subnet routers (out of scope for this repo):**
- 2 Raspberry Pis on VLAN 10 (Services network)
- Run standard Tailscale client, pointed at `headscale.hop.derio.net`
- Each advertises VLAN 10 subnet as a route (`--advertise-routes=<VLAN10_CIDR>`)
- Both advertise the same routes — Headscale handles failover
- VLAN 10 can route to VLAN 55 (Frank cluster), so mesh clients access all homelab services

**Client devices:**
- Install Tailscale, configure to use `headscale.hop.derio.net` as coordination server
- Once connected, traffic to home subnets routes through the nearest available subnet router
- All `*.frank.derio.net` services (ArgoCD, Grafana, etc.) accessible as if on the home network

## Blog Deployment

**Current state:** Hugo blog at `derio-net.github.io/frank/`, built by GitHub Actions, deployed to GitHub Pages.

**Target state:** Same Hugo source, but deployed to Hop as a container image.

**CI pipeline:**
1. GitHub Actions builds Hugo with `baseURL: https://blog.derio.net/frank`
2. Packages static output into a minimal container image (Caddy or nginx base)
3. Pushes to `ghcr.io/derio-net/blog:<tag>`
4. ArgoCD on Hop detects new image (or manual sync) and rolls out

**URL structure:**
- `blog.derio.net/frank` — the Frank building/operating blog (replaces GitHub Pages)
- `blog.derio.net` — root, redirects to `/frank` initially (or a blog index later)
- `www.derio.net` — personal portfolio (future content, serves a placeholder page initially)

**Migration from GitHub Pages:**
- During transition, keep the GitHub Pages deployment running in parallel
- Add a `<meta http-equiv="refresh">` redirect or GitHub Pages custom 404 pointing to `blog.derio.net/frank`
- Decommission GitHub Pages deployment once DNS propagation is confirmed and the new URL is indexed

## Repo Structure (After Refactoring)

**Note:** The repo restructure is a **separate, deferrable task**. Hop can be deployed first under `clusters/hop/` without moving Frank's existing `apps/` and `patches/` directories. The restructure should only be attempted once Hop is fully operational and verified, and can be skipped or deferred to a later phase if the risk is too high.

The final task restructures the repo from single-cluster to multi-cluster:

```
clusters/
  frank/
    apps/                      # moved from apps/
      root/                    # Frank's app-of-apps
      argocd/
      cilium/
      longhorn/
      ...
    patches/                   # moved from patches/
      phase01-node-config/
      phase02-cilium/
      ...
  hop/
    apps/
      root/                    # Hop's app-of-apps
      argocd/
      headscale/
      headplane/
      caddy/
      blog/
    packer/                    # Hetzner image build
blog/                          # Hugo source (unchanged)
docs/                          # Specs, plans, runbooks (unchanged)
secrets/                       # SOPS-encrypted secrets (unchanged)
scripts/                       # Utility scripts (unchanged)
omni/                          # Omni self-hosted config (unchanged)
```

**Migration checklist:**
- `git mv apps/ clusters/frank/apps/`
- `git mv patches/ clusters/frank/patches/`
- Update every Application CR template: `$values/apps/<app>/` → `$values/clusters/frank/apps/<app>/`
- Update Frank's ArgoCD root app source path
- Script Omni patch path updates via `omnictl` (delete old path references, apply with new paths)
- Update `CLAUDE.md` — all path references
- Update blog posts referencing repo structure
- Update `docs/runbooks/manual-operations.yaml` path references
- Update any CI workflows referencing `apps/` or `patches/`
- Verify: `argocd app sync root` reconciles cleanly after the move

**Rollback plan:** If ArgoCD fails to reconcile after the move, `git revert` the restructure commit and re-sync. Since ArgoCD reads from Git, reverting the commit restores all paths immediately. The Omni patch path updates via `omnictl` would also need to be reverted.

**Atomicity:** The git move and Application CR path updates must be in a single commit. ArgoCD will see the new paths atomically on the next sync. Disable auto-sync before the commit, push, then manually trigger sync to verify before re-enabling auto-sync.

## Dependencies

- Hetzner Cloud account with API token
- Omni dashboard access (for Hetzner image download)
- Packer installed locally (or in CI)
- `hcloud` CLI installed
- Cloudflare DNS access (for new records)
- 2 Raspberry Pis on VLAN 10 (pre-existing hardware, setup is out of scope)
- `derio.net` domain (already owned)

## Cost

| Item | Monthly Cost |
|------|-------------|
| CX22 (2 vCPU, 4GB) | ~€3.49 |
| Hetzner Volume 10GB | ~€0.48 |
| **Total** | **~€3.97/mo** |

## Security Considerations

- Headscale endpoint is public (necessary for client registration) — rate limiting and auth via Headscale's built-in mechanisms
- All other Hop management (Headplane, landing page) restricted to mesh members via Caddy IP filtering
- ArgoCD on Hop is cluster-internal only (no external exposure)
- Hetzner firewall: allow inbound TCP 80, TCP 443, UDP 3478 (STUN for DERP); deny all other inbound
- SOPS-encrypted secrets for Headscale private key, Caddy config secrets
- Blog and portfolio are intentionally public — no secrets involved

## Git Repo Access

Hop's ArgoCD needs read access to the `frank-cluster` Git repo. The repo is currently public on GitHub, so no credentials are needed. If the repo ever goes private, a deploy key or GitHub App credential must be provisioned for Hop's ArgoCD (same pattern as Frank's ArgoCD). Hop's root app uses the same `repoURL` as Frank but with its own `path` pointing to `clusters/hop/apps/root`.

## Backup & Disaster Recovery

**Headscale state:** The SQLite database contains all mesh registrations, node keys, and ACL policies. Loss requires re-registering all clients.

Mitigation:
- CronJob on Hop backs up `headscale.db` daily to an S3-compatible object store (e.g., Hetzner Object Storage, ~€0.01/mo for this volume)
- Alternatively, a periodic `kubectl cp` via the mesh to a home NAS
- Headscale config itself is declarative (in Git), so only the runtime state (registrations) needs backup

**Private route IP verification:** Caddy sees real source IPs because it binds directly via `hostPort`. Flannel's default SNAT applies only to pod-to-pod traffic leaving the node, not to inbound traffic arriving on the host network interface. No additional configuration needed.
