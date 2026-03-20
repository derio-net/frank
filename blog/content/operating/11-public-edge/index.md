---
title: "Operating on Hop — Single-Node Talos Edge Cluster"
date: 2026-03-20
draft: false
tags: ["operations", "hop", "talos", "headscale", "tailscale", "caddy", "edge"]
summary: "Day-to-day commands for managing Hop — a standalone single-node Talos cluster on Hetzner Cloud with Headscale mesh, Caddy, and ArgoCD."
weight: 111
cover:
  image: cover.png
  alt: "Frank checking on a miniature portal-connected server in the cloud"
  relative: true
---

This is the operational companion to [Hopping Through the Portal]({{< relref "/building/17-public-edge" >}}). That post covers the deployment story and the ten deviations. This one covers the commands you actually type to manage Hop — a very different operational profile from Frank.

## Key Differences from Frank

Hop is a single-node, standalone-talosctl cluster. Almost everything about its operational model differs from Frank:

| Concern | Frank | Hop |
|---------|-------|-----|
| **Talos management** | Omni (UI + API) | `talosctl` directly |
| **CNI** | Cilium (eBPF, L2 LB) | Flannel (default) |
| **Storage** | Longhorn (distributed) | Static PVs on Hetzner Volume |
| **Nodes** | 7 (HA control plane) | 1 (control-plane + worker) |
| **Ingress** | Cilium L2 LoadBalancer | Caddy hostPort (80/443) |
| **Remote access** | LAN only | Tailscale mesh + public endpoints |

The critical operational difference: **Hop has no redundancy.** A node reboot means all services are down. A botched Talos upgrade means you're rebuilding from the Packer snapshot. Treat Hop as a pet, not cattle.

## Environment Setup

**Critical:** Hop and Frank use separate env files that export the same `KUBECONFIG` variable. Sourcing the wrong one points every command at the wrong cluster.

```bash
# Hop operations — ALWAYS use this
source .env_hop

# Verify you're targeting the right cluster
kubectl get nodes
# Expected: hop-1   Ready   control-plane   ...
```

Never run `source .env` in a terminal where you intend to work on Hop. If you're unsure which cluster you're targeting:

```bash
kubectl config current-context
# Should show: admin@hop
```

For `talosctl`, also set the config path:

```bash
export TALOSCONFIG=$(pwd)/clusters/hop/talosconfig/talosconfig
talosctl -n $HOP_IP version
```

## Observing State

### Cluster Health

Talos health check works the same as on Frank, but you only have one node:

```bash
talosctl -n $HOP_IP health
```

This validates etcd, API server, kubelet, and node readiness. Since there's no HA, any failure here means the entire cluster is down.

```bash
kubectl get nodes -o wide
# hop-1 should be Ready

kubectl get pods -A
# All pods should be Running/Completed — no Pending or CrashLoopBackOff
```

### ArgoCD Applications

```bash
argocd app list --port-forward --port-forward-namespace argocd
```

All applications should show `Synced` and `Healthy`. If any show `Degraded`, check the specific app:

```bash
argocd app get <app-name> --port-forward --port-forward-namespace argocd
```

### Service Health Checks

Verify each service is actually responding (not just that pods are Running):

```bash
# Public endpoints (from anywhere)
curl -sI https://headscale.hop.derio.net | head -3
curl -sI https://blog.derio.net/frank/ | head -3

# Mesh-only endpoints (from a mesh client)
curl -sI https://headplane.hop.derio.net | head -3
# Should return 200 from mesh, 403 from public

# From inside the cluster (verify internal routing)
kubectl -n headscale-system exec deploy/headscale -- wget -qO- 127.0.0.1:8080/health
kubectl -n headscale-system exec deploy/headplane -- wget -qO- 127.0.0.1:3000/admin/
```

**Important:** Headplane binds IPv4 only. Use `127.0.0.1`, not `localhost` (which resolves to `::1` in Alpine containers).

## Headscale Operations

### Managing Users and Nodes

```bash
# List users
kubectl -n headscale-system exec deploy/headscale -- headscale users list

# Create a user
kubectl -n headscale-system exec deploy/headscale -- headscale users create <username>

# List registered nodes
kubectl -n headscale-system exec deploy/headscale -- headscale nodes list

# Create a pre-auth key (for registering new devices)
kubectl -n headscale-system exec deploy/headscale -- \
  headscale preauthkeys create --user <username> --reusable --expiration 24h
```

### Registering a New Device

On the client device:

```bash
tailscale up --login-server https://headscale.hop.derio.net --authkey <PREAUTH_KEY>
```

Verify the node appears in Headscale:

```bash
kubectl -n headscale-system exec deploy/headscale -- headscale nodes list
```

### Adding a Mesh-Only Service

When adding a new mesh-only domain to Hop, three things need updating:

1. **Headscale extra_records** — add the domain → Tailscale IP mapping to the ConfigMap
2. **Caddy Caddyfile** — add a `@mesh` handler block for the new domain
3. **Cloudflare DNS** — add an A record pointing the domain to Hop's public IP (for the 403 response)

```yaml
# In headscale ConfigMap, under dns.extra_records:
- name: newservice.hop.derio.net
  type: A
  value: 100.64.0.4  # hop-1's Tailscale IP
```

After updating the ConfigMap, restart Headscale to pick up DNS changes:

```bash
kubectl -n headscale-system rollout restart deploy/headscale
```

### Headscale Backup and Recovery

A CronJob runs daily at 3 AM UTC, backing up the SQLite database:

```bash
# Check backup job status
kubectl -n headscale-system get cronjobs
kubectl -n headscale-system get jobs --sort-by=.metadata.creationTimestamp

# List backups
kubectl -n headscale-system exec deploy/headscale -- ls -la /var/lib/headscale/backups/

# Manual backup
kubectl -n headscale-system exec deploy/headscale -- \
  sqlite3 /var/lib/headscale/db.sqlite ".backup /var/lib/headscale/backups/manual-$(date +%F).db"
```

Backups are stored on the Hetzner Volume (persistent across pod restarts). Retention is 7 days.

## Caddy Operations

### TLS Certificate Status

Caddy manages TLS automatically via Cloudflare DNS challenge. To check certificate status:

```bash
kubectl -n caddy-system logs deploy/caddy | grep -i "tls\|cert\|acme"
```

The Cloudflare API token is stored as a Kubernetes Secret (`caddy-cloudflare-token`). If TLS stops working, check the token hasn't expired:

```bash
kubectl -n caddy-system get secret caddy-cloudflare-token -o jsonpath='{.data.CF_API_TOKEN}' | base64 -d
# Verify the token is valid in Cloudflare dashboard
```

### Reloading Caddy Config

After editing the Caddyfile ConfigMap:

```bash
kubectl -n caddy-system rollout restart deploy/caddy
```

Caddy reloads gracefully — existing connections are not dropped.

### Debugging Access Issues

If a mesh-only service returns 403 when it shouldn't:

```bash
# Check if the client has a mesh IP
tailscale ip -4
# Should return 100.64.0.x

# Check if Caddy sees the mesh IP
kubectl -n caddy-system logs deploy/caddy | grep "headplane\|remote_ip"

# Verify DNS resolution from the client
dig headplane.hop.derio.net
# From mesh: should resolve to 100.64.0.4
# From public: should resolve to Hop's public IP
```

If DNS resolves to the public IP from a mesh client, Headscale's MagicDNS isn't active. Check that the client is using Headscale as its DNS:

```bash
tailscale status
# Verify "exit node" is not set (overrides DNS)
```

## Talos Operations

### Upgrading Talos

Hop upgrades are manual (no Omni to orchestrate). This is a **service-impacting operation** — all pods stop during the reboot.

```bash
# Check current version
talosctl -n $HOP_IP version

# Stage the upgrade (downloads image, does not reboot yet)
talosctl -n $HOP_IP upgrade --image ghcr.io/siderolabs/installer:<NEW_VERSION> --stage

# Reboot to apply
talosctl -n $HOP_IP reboot
```

After reboot, wait for the node to come back:

```bash
talosctl -n $HOP_IP health     # Wait until all checks pass
kubectl get nodes              # hop-1 should be Ready
kubectl get pods -A            # All pods should recover
```

**Expected downtime:** 3-5 minutes for the reboot cycle.

### Applying Config Changes

Talos config patches must be combined into a single `talosctl apply-config` invocation. You can't apply patches incrementally — each `--config-patch` replaces the previous one.

```bash
# View current config
talosctl -n $HOP_IP get machineconfig -o yaml

# Apply updated config (combines base + patches)
talosctl -n $HOP_IP apply-config --file controlplane.yaml
```

### Node Recovery

If hop-1 becomes unreachable:

1. **Check Hetzner console** — `hcloud server status hop-1`
2. **Try talosctl via public IP** — `talosctl -n <PUBLIC_IP> health` (TCP 50000 is open)
3. **Power cycle** — `hcloud server reset hop-1` (hard reboot)
4. **Rebuild from snapshot** — last resort; PV data survives on the Hetzner Volume

## Blog Operations

### Redeploying the Blog

The blog container rebuilds automatically on push to `main` (GitHub Actions). To manually trigger:

```bash
# From the repo root
cd blog && hugo --minify  # Verify build succeeds locally

# The CI pipeline builds and pushes ghcr.io/derio-net/frank-blog:latest
# To force a new pull on Hop:
kubectl -n blog-system rollout restart deploy/blog
```

### Checking Blog Content

```bash
# Verify the container is serving the expected content
kubectl -n blog-system exec deploy/blog -- ls /usr/share/caddy/frank/
# Should show index.html and the post directories
```

## Storage Operations

### Hetzner Volume Health

```bash
# Check volume is attached
hcloud volume list
# hop-data should show "attached to hop-1"

# Check mount inside Talos
talosctl -n $HOP_IP mounts | grep hop-data
# Should show /var/mnt/hop-data

# Check PVs are bound
kubectl get pv
# headscale-data and caddy-data should be Bound
```

### Disk Space

The Hetzner Volume is 10GB. Monitor usage:

```bash
talosctl -n $HOP_IP usage /var/mnt/hop-data/
```

Headscale's SQLite database is small (< 1MB). Caddy's TLS certificates and OCSP staples are the main consumers (typically < 50MB). If space becomes an issue, expand the volume in Hetzner dashboard (no downtime).

## Emergency Procedures

### Complete Cluster Rebuild

If hop-1 is unrecoverable:

```bash
# 1. Create new server from Talos snapshot
hcloud server create --name hop-1 --type cx23 --location fsn1 \
  --image <SNAPSHOT_ID> --volume hop-data

# 2. Apply Talos config
talosctl apply-config --insecure -n <NEW_IP> --file controlplane.yaml
talosctl bootstrap -n <NEW_IP>

# 3. Wait for cluster
talosctl -n <NEW_IP> health

# 4. Bootstrap ArgoCD
source .env_hop  # Update HOP_IP if changed
helm install argocd argo/argo-cd -n argocd --create-namespace \
  -f clusters/hop/apps/argocd/values.yaml
kubectl apply -f <(helm template root clusters/hop/apps/root/)

# 5. Re-create secrets (not in Git)
kubectl -n caddy-system create secret generic caddy-cloudflare-token \
  --from-literal=CF_API_TOKEN=<token>
kubectl -n headscale-system create secret generic tailscale-auth \
  --from-literal=TS_AUTHKEY=<key>

# 6. Update DNS if IP changed
# Update Cloudflare A records for *.hop.derio.net and blog.derio.net
```

The Hetzner Volume (with Headscale DB and Caddy certs) survives server deletion — reattach it to the new server. Headscale clients will automatically reconnect once the control server is back.

### Mesh Recovery Without Mesh Access

If the Tailscale mesh is down and you need to reach Hop:

```bash
# Use the public IP directly (mTLS-protected ports)
talosctl -n <PUBLIC_IP> -e <PUBLIC_IP> health
kubectl --kubeconfig clusters/hop/talosconfig/kubeconfig get pods -A
```

TCP 6443 and 50000 are open on the Hetzner firewall specifically for this scenario. Both require client certificates from the talosconfig/kubeconfig — unauthenticated access is impossible.

## References

- [Talos Linux Operations](https://www.talos.dev/v1.9/talos-guides/) — Official operations guide
- [Headscale CLI Reference](https://github.com/juanfont/headscale/blob/main/docs/) — Headscale command documentation
- [Caddy Documentation](https://caddyserver.com/docs/) — Caddy server configuration
- [Hetzner Cloud CLI](https://github.com/hetznercloud/cli) — `hcloud` command reference
