---
title: "Hopping Through the Portal — A Public Edge Cluster"
date: 2026-03-20
draft: false
tags: ["hop", "hetzner", "talos", "headscale", "tailscale", "caddy", "edge", "mesh"]
summary: "Deploying a single-node Talos cluster on Hetzner Cloud as a public edge — Headscale mesh, Caddy reverse proxy, and everything that went wrong along the way."
weight: 18
cover:
  image: cover.png
  alt: "Frank the cluster monster hopping through a glowing portal into a cloud datacenter"
  relative: true
---

The Frank cluster lives behind a residential NAT. Every service — ArgoCD, Grafana, Ollama — is reachable only from the local network at `192.168.55.x`. That's fine for tinkering at home, but useless when you want to reach the lab from a laptop at a coffee shop, or host a blog that the internet can actually visit.

This post covers deploying **Hop** — a single-node Talos cluster on Hetzner Cloud that acts as Frank's public face. It provides a Headscale mesh for remote access, a Caddy reverse proxy for public services, and a container-hosted blog. More importantly, it covers the ten deviations from the original plan and what each one teaches about the gap between designing infrastructure and actually running it.

## Why a Separate Cluster?

The simplest approach would be a VPS running Caddy and WireGuard. No Kubernetes, no ArgoCD, just a reverse proxy and a tunnel. But this project exists to learn Kubernetes infrastructure, and a single-node edge cluster is a genuinely useful pattern:

- **Mesh networking needs a public coordination point.** Headscale (the open-source Tailscale control server) must be reachable from the internet. Running it on Frank would require exposing Frank's IP — defeating the purpose.
- **GitOps consistency.** Hop uses the same ArgoCD App-of-Apps pattern as Frank. Adding a service means writing YAML and pushing to Git, not SSH-ing into a VPS and editing config files.
- **Operational practice on a different topology.** Frank has 7 nodes, an HA control plane, Cilium, Longhorn, GPU scheduling. Hop has 1 node, Flannel, hostPath storage, and no Omni. Different constraints surface different lessons.

## Architecture

```
Internet
  │
  ├─ TCP 80/443 ────→ Caddy (hostPort) ─┬─→ headscale.hop.derio.net  (public)
  │                                      ├─→ blog.derio.net/frank     (public)
  │                                      ├─→ headplane.hop.derio.net  (mesh only → 403)
  │                                      └─→ entry.hop.derio.net      (mesh only → 403)
  │
  └─ UDP 3478 ──────→ Headscale DERP relay

Tailscale Mesh (100.64.0.0/10)
  │
  ├─ hop-1 (100.64.0.4) ─── Tailscale DaemonSet (kernel mode, hostNetwork)
  ├─ laptop ─────────────── tailscale up --login-server headscale.hop.derio.net
  └─ phone ──────────────── Tailscale app → custom control URL

Hetzner CX23 (2 vCPU, 4GB RAM, 40GB disk + 10GB Volume)
  └─ hop-1: Talos Linux, standalone talosctl (not Omni)
```

Caddy handles all ingress. Mesh-only services check the source IP — if it's in the Tailscale CGNAT range (`100.64.0.0/10`), the request passes. Otherwise, 403. This split is invisible to clients: mesh users resolve `headplane.hop.derio.net` to hop-1's Tailscale IP via Headscale's MagicDNS, while public clients resolve it to the Hetzner public IP via Cloudflare DNS. Same domain, different resolution, different access.

## Infrastructure: Packer + talosctl

### Building the Image

Hetzner doesn't offer Talos Linux as a stock OS. The workaround is Packer in rescue mode — boot an Ubuntu server into Hetzner's rescue environment, `dd` the Talos raw image directly onto the disk, snapshot it, then create servers from that snapshot.

```hcl
source "hcloud" "talos" {
  token       = var.hcloud_token
  location    = "fsn1"
  server_type = "cx23"
  image       = "ubuntu-24.04"
  rescue      = "linux64"      # Boot into rescue, not the OS
}

build {
  sources = ["source.hcloud.talos"]
  provisioner "file" {
    source      = var.talos_image_path
    destination = "/tmp/talos.raw.xz"
  }
  provisioner "shell" {
    inline = [
      "xz -d /tmp/talos.raw.xz",
      "dd if=/tmp/talos.raw of=/dev/sda bs=4M status=progress",
      "sync",
    ]
  }
}
```

### Deviation #1: Standalone Talos, Not Omni

The plan called for Omni-managed Hop, matching Frank's setup. This failed immediately: the self-hosted Omni at `omni.frank.derio.net` is an internal hostname. Hetzner can't reach it. SideroLink registration requires the Talos node to phone home to Omni on boot — no connectivity, no registration.

The fix was straightforward but changed the operational model entirely:

```bash
# Generate configs (standalone, no Omni)
talosctl gen config hop https://<HOP_IP>:6443

# Apply to the server (first boot, insecure mode)
talosctl apply-config --insecure -n <HOP_IP> --file controlplane.yaml

# Bootstrap etcd
talosctl bootstrap -n <HOP_IP>
```

**What we learned:** Omni's value is lifecycle management at scale — rolling upgrades, config sync across nodes. For a single-node cluster that rarely changes, `talosctl` is simpler. The tradeoff is manual upgrades and no dashboard, but that's acceptable for an edge node. Hop's talosconfig lives at `clusters/hop/talosconfig/` (gitignored — it contains client certificates).

### Deviation #2: CX23, Not CX22

Trivial but worth noting: Hetzner renamed CX22 to CX23. Same specs (2 vCPU, 4GB, 40GB), same price. The Packer variables and documentation were updated.

## Workloads: ArgoCD App-of-Apps

Hop reuses Frank's GitOps pattern: a root Helm chart that templates Application CRs. The difference is scale — Hop has 7 applications versus Frank's 40+, and all use raw manifests (no upstream Helm charts).

```
clusters/hop/apps/
├── root/                    # App-of-Apps entry point
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── project.yaml     # AppProject
│       ├── ns-*.yaml        # 4 namespaces
│       ├── argocd.yaml      # ArgoCD (Helm, self-managing)
│       ├── headscale.yaml
│       ├── headplane.yaml
│       ├── caddy.yaml
│       ├── blog.yaml
│       ├── landing.yaml
│       └── storage.yaml
├── argocd/values.yaml       # Minimal single-replica ArgoCD
├── headscale/manifests/     # Headscale + Tailscale DaemonSet
├── headplane/manifests/     # Headplane UI + config
├── caddy/manifests/         # Caddy reverse proxy + Caddyfile
├── blog/manifests/          # Hugo blog container
├── landing/manifests/       # Private landing page
└── storage/manifests/       # StorageClass + static PVs
```

Bootstrap is the same chicken-and-egg as Frank: one manual `helm install` for ArgoCD, then ArgoCD manages itself and everything else.

```bash
source .env_hop
helm install argocd argo/argo-cd -n argocd --create-namespace \
  -f clusters/hop/apps/argocd/values.yaml
kubectl apply -f <(helm template root clusters/hop/apps/root/)
```

### Storage: Static PVs on a Hetzner Volume

No distributed storage on a single node — Longhorn would be overhead for no benefit. Instead, a Hetzner Volume (10GB block device) is mounted via Talos machine config at `/var/mnt/hop-data/`, and static PVs point at subdirectories:

```yaml
# clusters/hop/apps/storage/manifests/pv-headscale.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: headscale-data
spec:
  capacity:
    storage: 1Gi
  accessModes: [ReadWriteOnce]
  storageClassName: local-hop
  local:
    path: /var/mnt/hop-data/headscale
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values: [hop-1]
```

Simple, predictable, no CSI driver needed. The volume survives server rebuilds (Hetzner Volumes are detachable block devices).

## Headscale: The Mesh Coordination Point

Headscale is the open-source implementation of the Tailscale control server. It coordinates key exchange, node registration, and DERP relay fallback for clients that can't establish direct WireGuard connections.

The deployment is straightforward — a single pod with the Headscale binary, a ConfigMap for `config.yaml`, and a PVC backed by the static PV for the SQLite database.

### Deviation #3: Tailscale DaemonSet

The original plan assumed Caddy could distinguish mesh traffic by source IP — Tailscale clients would arrive with CGNAT addresses (`100.64.0.x`). But there was a gap: hop-1 itself wasn't on the mesh. It was just hosting Headscale.

Without hop-1 having a Tailscale interface, mesh clients connecting via the DERP relay would have their traffic source-NATted to the Headscale pod's cluster IP. Caddy would see an internal IP, not a mesh IP, and couldn't make access decisions.

The fix was a kernel-mode Tailscale DaemonSet that runs on hop-1 with `hostNetwork: true`:

```yaml
containers:
  - name: tailscale
    image: tailscale/tailscale:latest
    env:
      - name: TS_AUTHKEY
        valueFrom:
          secretKeyRef:
            name: tailscale-auth
            key: TS_AUTHKEY
      - name: TS_USERSPACE
        value: "false"   # Kernel mode — real tun device
    securityContext:
      privileged: true   # Required for kernel WireGuard
```

This gives hop-1 a `tailscale0` interface with a stable mesh IP (`100.64.0.4`). Mesh clients connect directly to this IP, and Caddy sees the real source address.

**What we learned:** Hosting a mesh coordination server and *being on the mesh* are separate concerns. Headscale manages the mesh; the Tailscale client joins it. A node can do both, but you have to deploy both.

### Deviation #4: MagicDNS with extra_records

Split-DNS fell out naturally from Headscale's `extra_records` feature. Mesh-only services need to resolve to hop-1's Tailscale IP, not its public IP:

```yaml
# In Headscale config.yaml
dns:
  magic_dns: true
  base_domain: hop.derio.net
  extra_records:
    - name: headplane.hop.derio.net
      type: A
      value: 100.64.0.4
    - name: entry.hop.derio.net
      type: A
      value: 100.64.0.4
```

Mesh clients use Headscale as their DNS resolver (configured automatically by Tailscale). They resolve `headplane.hop.derio.net` → `100.64.0.4` (Tailscale IP). Public clients use Cloudflare DNS and resolve the same domain to the Hetzner public IP — where Caddy returns 403.

No per-client configuration, no `/etc/hosts` hacks, no conditional forwarders. Just Headscale doing what it already does.

## The Headplane Saga

Headplane is a web UI for Headscale. In theory, it's a React app that talks to the Headscale gRPC API. In practice, it was the source of 60% of the debugging time in this deployment.

### Deviation #6: Config, Base Path, and API Key

The plan said: set a few environment variables, point it at Headscale, done. Reality:

**Problem 1: Config file required.** Headplane v0.5.5 silently ignores environment variables for core settings. It requires a `config.yaml` ConfigMap:

```yaml
headscale:
  url: http://headscale.headscale-system.svc:8080
  config_path: /etc/headscale/config.yaml
  config_strict: true     # Initially false — see below
server:
  host: 0.0.0.0
  port: 3000
  cookie_secret: "exactly-32-characters-needed!!!"
```

**Problem 2: config_strict kills the listener (initially).** The default is `config_strict: true`. During initial deployment with Headscale v0.25.1, this caused Headplane to detect "unknown" config fields and silently not start the HTTP listener. No error, no log line, no crash. The pod runs, health checks pass (the process is alive), but port 3000 never opens.

This took the longest to diagnose. The symptom was `wget 127.0.0.1:3000` returning "Connection refused" inside a pod that `kubectl` showed as Running/Ready. Setting `config_strict: false` fixed it instantly.

**Post-deploy update:** After stabilizing the Headscale config (removing fields that tripped strict parsing), `config_strict: true` works correctly. The non-strict setting was reverted a few days later. The lesson stands — silent failures are hostile — but the workaround turned out to be temporary.

**Problem 3: Base path.** Headplane's React Router is compiled with `basename="/admin/"`. All routes live under `/admin/*`. Hitting `/` returns a blank page. Caddy needs a redirect:

```
headplane.hop.derio.net {
  @not_mesh not remote_ip 100.64.0.0/10
  respond @not_mesh "Forbidden" 403
  @not_admin not path /admin /admin/*
  redir @not_admin /admin/ permanent
  reverse_proxy headplane.headscale-system.svc:3000
}
```

The `@not_admin` matcher catches *any* path that isn't already under `/admin*` and redirects — not just the root `/`. This prevents 404s from stale bookmarks or mistyped URLs.

**Problem 4: API key injection.** Headplane authenticates to Headscale via an API key, injected through `HEADPLANE_HEADSCALE_API_KEY` from a Kubernetes Secret. The key is created manually:

```bash
kubectl -n headscale-system exec deploy/headscale -- headscale apikeys create
kubectl -n headscale-system create secret generic headplane-api-key \
  --from-literal=HEADPLANE_HEADSCALE_API_KEY=<key>
```

**Problem 5: IPv4-only binding.** `wget localhost:3000` fails because `localhost` resolves to `::1` (IPv6) in Alpine containers, but Headplane only binds `0.0.0.0` (IPv4). Use `wget 127.0.0.1:3000` for health checks.

**What we learned:** When a service "doesn't work" but the pod is Running, check whether the HTTP listener actually started. `config_strict: true` as a default that silently drops functionality is a hostile design choice — it should at minimum log a warning. The broader lesson: don't trust `kubectl get pods` showing `1/1 Running` as proof that a service is healthy. Always verify the actual port.

## Caddy: The Front Door

Caddy handles TLS termination (via Cloudflare DNS challenge), public/mesh routing, and path rewriting. A single Caddyfile covers all services:

```
headscale.hop.derio.net {
  reverse_proxy headscale.headscale-system.svc:8080
}

blog.derio.net {
  handle_path /frank/* {
    reverse_proxy blog.blog-system.svc:80
  }
  handle /frank {
    redir /frank/ permanent
  }
}

headplane.hop.derio.net {
  @not_mesh not remote_ip 100.64.0.0/10
  respond @not_mesh "Forbidden" 403
  @not_admin not path /admin /admin/*
  redir @not_admin /admin/ permanent
  reverse_proxy headplane.headscale-system.svc:3000
}
```

### Deviation #5: Privileged Namespaces

Caddy uses `hostPort` (80, 443) to bind directly on the node's public IP. Talos enforces Pod Security Standards at the namespace level. The default `baseline` profile rejects `hostPort` pods. Both `caddy-system` and `headscale-system` (for the Tailscale DaemonSet) needed `privileged`:

```yaml
metadata:
  name: caddy-system
  labels:
    pod-security.kubernetes.io/enforce: privileged
```

**What we learned:** On Frank, Cilium handles L2 LoadBalancer IPs — no pod ever needs `hostPort`. On Hop, there's no Cilium, no MetalLB, no cloud load balancer. `hostPort` is the only option for binding public ports. This immediately forces `privileged` namespace security, which is a real tradeoff on a multi-tenant cluster. Single-node edge clusters are inherently less isolated.

### Custom Caddy Image with Cloudflare DNS

Caddy's automatic TLS needs a DNS challenge plugin for wildcard certs. The stock Caddy image doesn't include it. A custom Dockerfile adds the Cloudflare module:

```dockerfile
FROM caddy:2.9-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2.9
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

Built via GitHub Actions, pushed to `ghcr.io/derio-net/caddy-cloudflare:2.9`.

## Blog Deployment

The blog runs as a container on Hop. Hugo builds the static site, a minimal Caddy serves it:

```dockerfile
FROM hugomods/hugo:exts as builder
WORKDIR /src
COPY . .
RUN hugo --minify

FROM caddy:2-alpine
COPY --from=builder /src/public /usr/share/caddy
COPY <<'EOF' /etc/caddy/Caddyfile
:80 {
  root * /usr/share/caddy
  try_files {path} {path}/ /index.html
  file_server
}
EOF
```

### Deviation #9: Blog Path Handling

The plan expected Hugo's `baseURL: https://blog.derio.net/frank` to output content at `/frank/` inside the container. It doesn't — Hugo always outputs to the root of the public directory regardless of `baseURL`. The `baseURL` only affects internal link generation.

The fix is two layers of path handling:
1. **External Caddy** (the hop-1 reverse proxy) strips `/frank` from the path before forwarding
2. **Internal Caddy** (inside the blog container) serves from `/` as if the prefix doesn't exist

**What we learned:** `baseURL` in Hugo is for link generation, not for output directory structure. If you need a subpath, handle it at the reverse proxy layer.

## Deviation #7: Control Plane Scheduling

Talos applies a `NoSchedule` taint to control-plane nodes by default. On a 7-node cluster, that's fine — workloads run on workers. On a single-node cluster, nothing can schedule.

```bash
# Emergency fix
kubectl taint nodes hop-1 node-role.kubernetes.io/control-plane:NoSchedule-

# Permanent fix in Talos config
cluster:
  allowSchedulingOnControlPlanes: true
```

**What we learned:** This is a documentation issue, not a bug — Talos assumes multi-node clusters. Single-node clusters need explicit opt-in for control-plane scheduling. Check taints early.

## Deviation #8: Hetzner Firewall Ports

The plan opened TCP 80, 443, and UDP 3478 (STUN). Without Omni managing the cluster, two more ports were needed:

- **TCP 6443** — Kubernetes API server (for `kubectl`)
- **TCP 50000** — Talos API (for `talosctl`)

Both require mutual TLS (client certificates), so unauthenticated access is impossible. They're left open as a break-glass recovery path if the Tailscale mesh goes down. Day-to-day management uses the mesh IP (`100.64.0.4`).

## Deviation #10: Environment File Structure

Frank uses `.env` to set `KUBECONFIG`. Adding Hop meant `.env_hop` with a different `KUBECONFIG` path. The danger: sourcing `.env` after `.env_hop` silently overrides the kubeconfig back to Frank. Every `kubectl` command hits the wrong cluster, and the errors are confusing ("resource not found" for resources that definitely exist — on the other cluster).

**What we learned:** Multiple env files that export the same variable are a footgun. The mitigation is discipline: never source `.env` when working on Hop. A better solution would be explicit context switching (like `kubectx`), but for two clusters, separate terminal sessions work.

## Blog CI Pipeline

The blog has two deployment targets:
1. **GitHub Pages** — the existing workflow, deploys to `blog.derio.net` via GitHub's CDN
2. **Hop container** — new workflow job, builds the Docker image and pushes to GHCR

Both run on push to `main` when files under `blog/` change. The container build uses the same Dockerfile but pushes to `ghcr.io/derio-net/frank-blog:latest`. On Hop, the blog Deployment pulls this image.

## What We Have Now

Hop gives the homelab a public presence:

- **Headscale mesh** — any device can join via `tailscale up --login-server https://headscale.hop.derio.net`. Once on the mesh, Frank's entire `192.168.55.x` network is reachable through the mesh routing.
- **Split-DNS** — mesh clients resolve mesh-only domains to Tailscale IPs automatically. No client configuration beyond `tailscale up`.
- **Public blog** at `blog.derio.net/frank`, served from a container rebuilt on every push.
- **Private services** (Headplane, landing page) accessible only from the mesh, enforced at Caddy's `remote_ip` check.
- **Full GitOps** — all workloads managed by ArgoCD, same pattern as Frank.

## Post-Deploy Fixes (Day 3)

Three days after the initial deployment, a routine check surfaced four more issues. These are less dramatic than the deployment deviations — more "cleaning up what we left behind" than "discovering the plan was wrong."

### Deviation #11: Caddy Deployment Strategy

The Caddy Deployment used the default `RollingUpdate` strategy. On a single-node cluster with `hostPort`, this deadlocks: the new pod can't bind ports 80/443 while the old pod still holds them. The old pod won't terminate until the new pod is ready. Stalemate.

Changed to `strategy: Recreate`, which kills the old pod first. There's a ~5-second window where no pod serves traffic, but on a single-node edge cluster, that's acceptable — you're already accepting that a node reboot means full downtime.

**What we learned:** `RollingUpdate` assumes you have somewhere else to schedule the replacement. Single-node clusters need `Recreate` for any resource that can't be shared (hostPorts, exclusive volume mounts).

### Deviation #12: Empty Cloudflare Secret

After a `rollout restart`, the new Caddy pod crashed: `API token '' appears invalid`. The secret `caddy-cloudflare` existed but contained an empty value. The old pod was fine because Kubernetes injects `secretKeyRef` env vars at pod creation — they're baked in and never refreshed. The old pod had the valid token from when it was first created; the secret was emptied at some point afterward.

**What we learned:** Running pods mask broken secrets. A `rollout restart` is the moment the truth surfaces. After any out-of-band secret management, consider restarting the consumer pod to verify the secret is still valid.

### Deviation #13: config_strict Corrected

During the original deployment (Deviation #6), `config_strict: false` was set as a workaround for a silent HTTP listener failure. But strict mode had actually worked at one point during the debugging session — non-strict just happened to be active when the fix landed. Three days later, switched back to `config_strict: true` — no issues. The Headscale config no longer contains the fields that tripped strict parsing.

**What we learned:** Workarounds that stick around become cargo cult. When a workaround is applied under pressure, note it for later review. "It works now, don't touch it" is a reasonable attitude during deployment, but not a permanent configuration strategy.

### Deviation #14: Caddy Redirect Robustness

The original Caddy redirect `redir / /admin/ permanent` only matched the exact root path `/`. Any other path (bookmarks, typos, stale links) would pass through to Headplane, which returns 404 for anything outside `/admin/*`. Changed to a `@not_admin` matcher that catches all non-`/admin*` paths.

**What we learned:** Exact-path redirects are brittle. If you're redirecting to a base path, catch everything that *isn't* already under that path.

## The Deviation Scorecard

Fourteen deviations across the deployment and post-deploy period. The original ten happened during deployment; four more surfaced during the first week of operation.

| Category | Count | Example |
|----------|-------|---------|
| **Architecture gap** | 3 | Omni unreachable, Tailscale DaemonSet missing, MagicDNS needed |
| **Software behavior** | 3 | Headplane config, blog path handling, IPv4 binding |
| **Platform surprise** | 2 | CX23 rename, control-plane taint |
| **Operational gap** | 2 | Firewall ports, env file conflicts |
| **Post-deploy cleanup** | 4 | Recreate strategy, empty secret, strict mode revert, redirect robustness |

The architecture gaps are the most interesting. The plan was designed top-down from the spec, but the spec didn't account for the difference between "hosting a service" and "participating in a service." Hop hosts Headscale, but it also needs to *be on* the mesh. The plan had Caddy checking source IPs, but didn't think through how those IPs would actually appear on the wire.

The Headplane issues are a different class — they're upstream documentation and design problems. No amount of planning prevents a silent failure mode that isn't documented. The only defense is verifying that each service actually listens on its expected port, not just that the pod is running.

The post-deploy fixes are the most preventable category. The Recreate strategy is something any single-node operator should set from the start. The empty secret is a side effect of out-of-band secret management. The redirect and strict mode are cleanup of expedient choices made under deployment pressure. This is the category that shrinks with experience — you start adding `strategy: Recreate` to your single-node templates before you hit the deadlock.

**The meta-lesson:** Plans are hypotheses about how infrastructure will behave. The plan was right about *what* to build (the architecture is sound) but wrong about *how* several components would need to be configured. The deviations were all fixable — none required rethinking the architecture. That's the sign of a good plan with imperfect details, which is the normal outcome for infrastructure work. The post-deploy fixes show that "deployed" isn't "done" — the first week of operation always reveals configuration decisions that were expedient rather than correct.

## References

- [Talos Linux](https://www.talos.dev/) — Immutable Kubernetes OS
- [Headscale](https://github.com/juanfont/headscale) — Open-source Tailscale control server
- [Headplane](https://github.com/tale/headplane) — Web UI for Headscale
- [Tailscale](https://tailscale.com/) — WireGuard-based mesh networking
- [Caddy](https://caddyserver.com/) — Automatic HTTPS web server
- [Packer](https://www.packer.io/) — Machine image automation
- [Hetzner Cloud](https://www.hetzner.com/cloud) — European cloud provider
- [Hugo](https://gohugo.io/) — Static site generator

**Next: [Operating on Hop — Single-Node Talos Edge Cluster]({{< relref "/operating/11-public-edge" >}})**
