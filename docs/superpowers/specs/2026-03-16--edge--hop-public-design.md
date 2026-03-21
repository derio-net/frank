# Hop: Public Edge Entrypoint

**Date:** 2026-03-16
**Updated:** 2026-03-19
**Status:** Deployed
**Layer:** edge

## Overview

Deploy a Hetzner Cloud VPS running Talos Linux as a public-facing edge node ("Hop"), managed as a standalone single-node Talos cluster via `talosctl`. Hop provides three capabilities:

1. **Headscale mesh** — self-hosted Tailscale coordination server enabling remote access to the entire homelab via VLAN 10 subnet routers
2. **Public web presence** — Hugo blog at `blog.derio.net/frank` and portfolio at `www.derio.net`, served by Caddy
3. **Private landing page** — `entry.hop.derio.net`, accessible only to mesh members

Two dedicated Raspberry Pis on VLAN 10 (Services) act as Tailscale subnet routers, advertising home network routes through the mesh. These are outside Frank and Hop — standalone devices managed independently.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │         Hetzner Cloud CX23 (Hop)            │
                    │         Talos Linux · standalone talosctl   │
                    │                                             │
  Internet ────▶    │  ┌────────────────────────────────────┐     │
  :80/:443          │  │ Caddy (hostPort 80/443)            │     │
                    │  │  *.hop.derio.net  (wildcard cert)  │     │
                    │  │  blog.derio.net   (public)         │     │
                    │  │  www.derio.net    (public)         │     │
                    │  └──┬──────┬──────┬──────┬────────────┘     │
                    │     │      │      │      │                  │
                    │     ▼      ▼      ▼      ▼                  │
                    │  Headscale Headplane Blog  Landing          │
                    │  (public)  (mesh)  (pub)  (mesh)            │
                    │     │                                       │
                    │     │  Tailscale DaemonSet (kernel-mode)    │
                    │     │  hostNetwork + privileged             │
                    │     │  → gives hop-1 a mesh IP (100.64.x)   │
                    │     │  → Caddy sees mesh source IPs         │
                    │     │                                       │
                    │     │  MagicDNS (extra_records)             │
                    │     │  → mesh clients resolve mesh-only     │
                    │     │    domains to Tailscale IP            │
                    │     │                                       │
                    │     │  Hetzner Volume (10GB)                │
                    │     │  ├── headscale.db                     │
                    │     │  ├── caddy certs                      │
                    │     │  └── tailscale state                  │
                    │     │                                       │
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
                    │  Home Network           │
                    │  VLAN 10 (Services)     │
                    │    → routes to VLAN 55  │
                    │      (Frank cluster)    │
                    │    → routes to other    │
                    │      homelab services   │
                    └─────────────────────────┘
```

## Hetzner Provisioning

**Node:** CX23 (2 vCPU, 4GB RAM, 40GB disk, ~€3.49/mo) — CX22 was deprecated by Hetzner
**Storage:** Hetzner Volume 10GB (~€0.48/mo)
**Location:** `fsn1` (Falkenstein)
**Public IP:** stored in `.env_hop` as `HOP_IP` (not committed)

**Image build workflow:**

1. Download plain Talos Hetzner image from Talos Image Factory (`hcloud-amd64.raw.xz`)
2. Packer builds a Hetzner Cloud snapshot from the image (rescue mode → `dd` → snapshot)
3. `hcloud server create --image <SNAPSHOT_ID> --type cx23 --location fsn1 --volume hop-data`
4. Apply Talos config via `talosctl apply-config --insecure`
5. Bootstrap etcd via `talosctl bootstrap`
6. Retrieve kubeconfig via `talosctl kubeconfig`

**Why not Omni:** The self-hosted Omni instance at `omni.frank.derio.net` is only reachable on the home network. A Hetzner VPS cannot reach it for registration. Standalone `talosctl` is simpler for a single-node cluster.

Packer config lives at `clusters/hop/packer/`. Talosconfig (secrets) at `clusters/hop/talosconfig/` (gitignored).

## Hop Cluster Configuration

**Standalone single-node Talos cluster managed via `talosctl`:**
- Control plane + worker on same node (`allowSchedulingOnControlPlanes: true`)
- CNI: Flannel (default) — Cilium is unnecessary for a single public node
- No LoadBalancer abstraction — Caddy uses `hostPort` on 80/443
- PodSecurity: `caddy-system` and `headscale-system` namespaces labeled `privileged` (required for hostPort and privileged containers)

**Workloads:**

| App | Type | Source | Notes |
|-----|------|--------|-------|
| ArgoCD | Helm chart | Upstream (argo-cd 9.4.14) | Minimal single-replica install, manages Hop's app-of-apps |
| Headscale | Raw manifests | `headscale/headscale:0.25.1` | Coordination server, gRPC + HTTPS, embedded DERP |
| Headplane | Raw manifests | `ghcr.io/tale/headplane:0.5.5` | Web UI for Headscale (requires config.yaml file) |
| Caddy | Raw manifests | `ghcr.io/derio-net/caddy-cloudflare:2.9` | Reverse proxy, TLS via Cloudflare DNS challenge |
| Blog | Raw manifests | `ghcr.io/derio-net/blog:latest` | Hugo static output baked into Caddy container |
| Landing | Raw manifests | ConfigMap HTML | Private entry page for mesh members |
| Tailscale | Raw manifests (DaemonSet) | `tailscale/tailscale:v1.82.5` | Kernel-mode client, gives hop-1 a mesh IP |

**Talos machine config (combined patch applied via `talosctl`):**
- Disk mount: `/dev/sdb` → `/var/mnt/hop-data` (XFS, auto-formatted)
- Kubelet extra mount: binds `/var/mnt/hop-data` into kubelet namespace
- `allowSchedulingOnControlPlanes: true`

**Storage:**
- Hetzner Volume (10GB) attached as `/dev/sdb`, mounted at `/var/mnt/hop-data` via Talos `machine.disks` config
- Static PV + PVC pointing to the host mount path — no CSI driver needed
- Used for: Headscale SQLite DB, Caddy certificate storage, Tailscale state
- Subdirectories: `headscale/`, `caddy/`, `backups/headscale/`, `tailscale/`
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

**MagicDNS (mesh-only DNS resolution):** Headscale's `extra_records` config maps mesh-only domains to hop-1's Tailscale IP. Mesh clients automatically resolve `headplane.hop.derio.net` and `entry.hop.derio.net` to the Tailscale IP (e.g., `100.64.0.4`), routing traffic through the mesh tunnel. Public DNS (Cloudflare) resolves the same domains to the public IP, where Caddy blocks them with 403. No per-client DNS configuration needed — any device joining the mesh gets the correct records automatically.

**Tailscale DaemonSet:** A kernel-mode Tailscale client runs on hop-1 as a DaemonSet with `hostNetwork: true` and `privileged: true`. This creates a `tailscale0` interface on the host's network namespace, giving hop-1 a mesh IP. When mesh clients connect to hop-1's Tailscale IP, traffic arrives through the tunnel and Caddy sees the source as a `100.64.0.0/10` IP — allowing access to mesh-only routes.

## Headscale Mesh

**Headscale** runs on Hop as the coordination server. It manages:

- Client registrations (phone, laptop)
- Subnet router approvals (RPi subnet routers)
- ACL policies (which clients can reach which subnets)
- DNS configuration (MagicDNS with `extra_records` for mesh-only service resolution)
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

**Note:** The repo restructure is a **separate, deferrable task**. Hop can be deployed first under `clusters/hop/` without moving Frank's existing `apps/` and `patches/` directories. The restructure should only be attempted once Hop is fully operational and verified, and can be skipped or deferred to a later layer if the risk is too high.

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

- Hetzner Cloud account with API token (`HCLOUD_TOKEN` in `.env_common`)
- Packer installed locally
- `hcloud` CLI installed
- `talosctl` installed (for cluster management)
- Cloudflare DNS access (for new records)
- Cloudflare API token (`CF_API_TOKEN` in `.env_hop`) for Caddy TLS
- 2 Raspberry Pis on VLAN 10 (pre-existing hardware, setup is out of scope)
- `derio.net` domain (already owned)

## Cost

| Item | Monthly Cost |
|------|-------------|
| CX23 (2 vCPU, 4GB) | ~€3.49 |
| Hetzner Volume 10GB | ~€0.48 |
| **Total** | **~€3.97/mo** |

## Security Considerations

- Headscale endpoint is public (necessary for client registration) — rate limiting and auth via Headscale's built-in mechanisms
- All other Hop management (Headplane, landing page) restricted to mesh members via Caddy IP filtering + MagicDNS
- ArgoCD on Hop is cluster-internal only (no external exposure)
- Hetzner firewall (`hop-fw`): allow inbound TCP 80, TCP 443, UDP 3478 (STUN), TCP 6443 (K8s API), TCP 50000 (talosctl); deny all other inbound
- Ports 6443 and 50000 are left open as a break-glass path. Both the Kubernetes API and Talos API require mutual TLS (client certificates from talosconfig) — unauthenticated access is not possible. Prefer the Tailscale mesh for daily management (faster, encrypted tunnel), but the public ports ensure recovery if the mesh goes down. Home IP is not static, so IP-based firewall rules are impractical.
- Caddy Cloudflare API token stored as Kubernetes Secret (`caddy-cloudflare`), applied out-of-band
- Tailscale auth key stored as Kubernetes Secret (`tailscale-auth`), applied out-of-band
- Blog and portfolio are intentionally public — no secrets involved

## Git Repo Access

Hop's ArgoCD needs read access to the `frank-cluster` Git repo. The repo is currently public on GitHub, so no credentials are needed. If the repo ever goes private, a deploy key or GitHub App credential must be provisioned for Hop's ArgoCD (same pattern as Frank's ArgoCD). Hop's root app uses the same `repoURL` as Frank but with its own `path` pointing to `clusters/hop/apps/root`.

## Backup & Disaster Recovery

**Headscale state:** The SQLite database contains all mesh registrations, node keys, and ACL policies. Loss requires re-registering all clients.

Mitigation:
- CronJob on Hop backs up `headscale.db` daily to an S3-compatible object store (e.g., Hetzner Object Storage, ~€0.01/mo for this volume)
- Alternatively, a periodic `kubectl cp` via the mesh to a home NAS
- Headscale config itself is declarative (in Git), so only the runtime state (registrations) needs backup

**Private route IP verification:** For public traffic, Caddy sees real source IPs because it binds directly via `hostPort`. For mesh traffic, the kernel-mode Tailscale DaemonSet creates a `tailscale0` interface in the host network namespace. Since Caddy also runs with `hostPort` (same network namespace), it sees mesh source IPs (`100.64.0.0/10`) on connections arriving through the tunnel. MagicDNS `extra_records` ensure mesh clients resolve mesh-only domains to the Tailscale IP, directing traffic through the tunnel rather than the public IP.
