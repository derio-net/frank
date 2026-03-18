# Hop: Public Edge Entrypoint — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a Hetzner Cloud CX23 running Talos Linux as "Hop" — a public-facing single-node Kubernetes cluster managed via `talosctl`, providing Headscale mesh networking for remote homelab access, Caddy reverse proxy with TLS, a Hugo blog, and a private landing page.

**Architecture:** Hop is a standalone Talos cluster living in `clusters/hop/` within the existing frank-cluster monorepo. Packer builds a Hetzner Cloud snapshot from the official Talos hcloud image. ArgoCD on Hop manages all workloads via an independent app-of-apps. Caddy handles all ingress via hostPort 80/443. Hetzner Volume provides persistent storage via Talos `machine.disks` config + static PV. A kernel-mode Tailscale DaemonSet gives hop-1 a mesh IP, enabling Caddy to distinguish mesh vs public traffic. MagicDNS `extra_records` provide split-DNS for mesh-only services.

**Tech Stack:** Talos Linux, talosctl, Packer (HCL), Hetzner Cloud (`hcloud` CLI), ArgoCD (Helm), Headscale, Headplane, Tailscale, Caddy, Hugo, Flannel CNI

**Status:** Deployed 2026-03-18. All services healthy. See deployment deviations below.

**Spec:** `docs/superpowers/specs/2026-03-16-phaseXX-hop-public-edge-design.md`

---

## Deployment Deviations (2026-03-18)

The plan was executed interactively on 2026-03-18. The following deviations from the original plan occurred:

### 1. Standalone Talos (not Omni)

**Original:** Omni-managed cluster with auto-registration via SideroLink.
**Actual:** Standalone Talos cluster managed via `talosctl`. The self-hosted Omni at `omni.frank.derio.net` is unreachable from Hetzner (internal-only hostname). Used `talosctl gen config`, `talosctl apply-config --insecure`, and `talosctl bootstrap` directly.
**Impact:** Tasks 1-2 manual operations changed entirely. No Omni dashboard needed. Talosconfig stored at `clusters/hop/talosconfig/` (gitignored).

### 2. Server Type CX23

**Original:** CX22.
**Actual:** CX23 — Hetzner deprecated/renamed CX22. Same specs, same price.

### 3. Tailscale DaemonSet for Mesh Routing

**Original:** Not in plan. Caddy's `remote_ip` check assumed mesh traffic would arrive with CGNAT source IPs.
**Actual:** Added `clusters/hop/apps/headscale/manifests/tailscale-client.yaml` — a kernel-mode Tailscale DaemonSet with `hostNetwork: true` and `privileged: true`. This gives hop-1 a real `tailscale0` interface and mesh IP, so Caddy can distinguish mesh vs public traffic.
**Impact:** New manifests (DaemonSet, ServiceAccount, Role, RoleBinding). Required `headscale-system` namespace to be labeled `pod-security.kubernetes.io/enforce: privileged`.

### 4. MagicDNS with extra_records

**Original:** Not in plan. Mesh-only access was expected to work via Caddy IP filtering alone.
**Actual:** Added `extra_records` to Headscale's DNS config mapping mesh-only domains to hop-1's Tailscale IP. Mesh clients resolve via Headscale DNS, public clients via Cloudflare. Split-DNS without per-client configuration.

### 5. PodSecurity Namespace Labels

**Original:** Not addressed.
**Actual:** `caddy-system` and `headscale-system` namespaces required `pod-security.kubernetes.io/enforce: privileged` label for hostPort and privileged containers. Added to namespace templates in root app.

### 6. Headplane v0.5+ Config File

**Original:** Environment variables only.
**Actual:** Headplane 0.5.5 requires a `config.yaml` file. Added ConfigMap with `headscale.url`, `headscale.integration`, and `server.cookie_secret` (exactly 32 chars).

### 7. Control Plane Scheduling

**Original:** Not addressed (single-node cluster assumed to work).
**Actual:** Talos applies `NoSchedule` taint to control-plane nodes by default. Required `kubectl taint nodes hop-1 node-role.kubernetes.io/control-plane:NoSchedule-` and permanent fix via `cluster.allowSchedulingOnControlPlanes: true` in Talos config patch.

### 8. Hetzner Firewall Ports

**Original:** TCP 80, TCP 443, UDP 3478 only.
**Actual:** Also opened TCP 6443 (K8s API) and TCP 50000 (talosctl API) — needed since Omni is not managing the cluster. Both APIs require mutual TLS (client certificates), so unauthenticated access is not possible. Ports are left open as a break-glass recovery path in case the Tailscale mesh goes down. Prefer mesh IP (`100.64.0.4`) for daily management.

### 9. Blog Path Handling

**Original:** Hugo builds with `baseURL: https://blog.derio.net/frank`, content at `/frank/` in container.
**Actual:** Hugo outputs to root `/` in the container regardless of baseURL. Caddy's reverse proxy handles the `/frank` path prefix by stripping it before forwarding to the blog container.

### 10. Env File Structure

**Original:** `.env` only.
**Actual:** Added `.env_hop` for Hop-specific vars (KUBECONFIG, CF_API_TOKEN). Critical: sourcing `.env` overrides KUBECONFIG to Frank — never source it when working on Hop.

### Task Completion Summary

| Task | Status | Notes |
|------|--------|-------|
| 1. Packer Image Build | Done | Used plain Talos image instead of Omni |
| 2. Provision Server | Done | `talosctl` instead of Omni registration |
| 3. Root Chart | Done | Pre-existing from plan execution |
| 4. Bootstrap ArgoCD | Done | Helm install + root app apply |
| 5. Static Storage | Done | PV/PVC + StorageClass |
| 6. Headscale | Done | + Tailscale DaemonSet + MagicDNS |
| 7. Headplane | Done | Config file required for v0.5+ |
| 8. Caddy | Done | Cloudflare secret applied out-of-band |
| 9. Blog | Done | Path handling differs from plan |
| 10. Landing Page | Done | |
| 11. Blog CI | Done | Hugo image tag updated |
| 12. Custom Caddy Image | Done | Pre-existing from plan execution |
| 13. SOPS Secrets | Skipped | Secrets applied as plain K8s Secrets out-of-band |
| 14. Backup CronJob | Done | Pre-existing from plan execution, needs verification |
| 15. E2E Verification | Done | All services healthy |
| 16. Update Documentation | In Progress | This update |
| 17. Repo Restructure | Deferred | Separate phase |

---

## File Structure

### Packer Image Build

| Action | Path | Purpose |
|--------|------|---------|
| Create | `clusters/hop/packer/hetzner-talos.pkr.hcl` | Packer template: rescue mode → dd Talos image → snapshot |
| Create | `clusters/hop/packer/variables.pkr.hcl` | Variable definitions (hcloud token, location, image path) |
| Create | `clusters/hop/packer/.gitignore` | Ignore Packer cache, downloaded images |

### Hop ArgoCD Root App

| Action | Path | Purpose |
|--------|------|---------|
| Create | `clusters/hop/apps/root/Chart.yaml` | Helm chart metadata for Hop's app-of-apps |
| Create | `clusters/hop/apps/root/values.yaml` | repoURL, targetRevision, destination for Hop |
| Create | `clusters/hop/apps/root/templates/project.yaml` | ArgoCD AppProject for Hop |
| Create | `clusters/hop/apps/root/templates/ns-headscale.yaml` | Namespace: headscale-system |
| Create | `clusters/hop/apps/root/templates/ns-caddy.yaml` | Namespace: caddy-system |
| Create | `clusters/hop/apps/root/templates/ns-blog.yaml` | Namespace: blog-system |
| Create | `clusters/hop/apps/root/templates/headscale.yaml` | ArgoCD Application CR for Headscale |
| Create | `clusters/hop/apps/root/templates/headplane.yaml` | ArgoCD Application CR for Headplane |
| Create | `clusters/hop/apps/root/templates/caddy.yaml` | ArgoCD Application CR for Caddy |
| Create | `clusters/hop/apps/root/templates/blog.yaml` | ArgoCD Application CR for Blog |
| Create | `clusters/hop/apps/root/templates/landing.yaml` | ArgoCD Application CR for Landing page |
| Create | `clusters/hop/apps/root/templates/storage.yaml` | ArgoCD Application CR for storage (PV/PVC) |

### Headscale

| Action | Path | Purpose |
|--------|------|---------|
| Create | `clusters/hop/apps/headscale/manifests/deployment.yaml` | Headscale Deployment |
| Create | `clusters/hop/apps/headscale/manifests/service.yaml` | ClusterIP Service (gRPC + HTTP) |
| Create | `clusters/hop/apps/headscale/manifests/configmap.yaml` | Headscale config.yaml |
| Create | `clusters/hop/apps/headscale/manifests/pvc.yaml` | PVC for Headscale DB (bound to static PV) |

### Headplane

| Action | Path | Purpose |
|--------|------|---------|
| Create | `clusters/hop/apps/headplane/manifests/deployment.yaml` | Headplane Deployment |
| Create | `clusters/hop/apps/headplane/manifests/service.yaml` | ClusterIP Service |

### Caddy

| Action | Path | Purpose |
|--------|------|---------|
| Create | `clusters/hop/apps/caddy/manifests/deployment.yaml` | Caddy Deployment (hostPort 80/443) |
| Create | `clusters/hop/apps/caddy/manifests/configmap.yaml` | Caddyfile with all routes |
| Create | `clusters/hop/apps/caddy/manifests/pvc.yaml` | PVC for Caddy data/certs |

### Blog

| Action | Path | Purpose |
|--------|------|---------|
| Create | `clusters/hop/apps/blog/manifests/deployment.yaml` | Blog Deployment (Hugo static container) |
| Create | `clusters/hop/apps/blog/manifests/service.yaml` | ClusterIP Service |

### Landing Page

| Action | Path | Purpose |
|--------|------|---------|
| Create | `clusters/hop/apps/landing/manifests/deployment.yaml` | Landing page Deployment |
| Create | `clusters/hop/apps/landing/manifests/service.yaml` | ClusterIP Service |
| Create | `clusters/hop/apps/landing/manifests/configmap.yaml` | HTML content for landing page |

### Storage

| Action | Path | Purpose |
|--------|------|---------|
| Create | `clusters/hop/apps/storage/manifests/pv.yaml` | Static PV backed by Hetzner Volume mount |
| Create | `clusters/hop/apps/storage/manifests/storageclass.yaml` | Local StorageClass for static provisioning |

### Blog CI Pipeline

| Action | Path | Purpose |
|--------|------|---------|
| Create | `blog/Dockerfile` | Multi-stage: Hugo build → Caddy static server |
| Modify | `.github/workflows/deploy-blog.yml` | Add job to build + push container image to GHCR |

### Secrets (out-of-band)

| Action | Path | Purpose |
|--------|------|---------|
| Create | `secrets/hop/headscale-private-key.yaml` | SOPS-encrypted Headscale noise private key |

### Documentation

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `CLAUDE.md` | Add Hop cluster to Architecture, Nodes, Services sections |

---

## Chunk 1: Infrastructure Provisioning

### Task 1: Packer Image Build

**Files:**
- Create: `clusters/hop/packer/hetzner-talos.pkr.hcl`
- Create: `clusters/hop/packer/variables.pkr.hcl`
- Create: `clusters/hop/packer/.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/packer
```

- [ ] **Step 2: Create Packer variables file**

Create `clusters/hop/packer/variables.pkr.hcl`:

```hcl
variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "talos_image_path" {
  type        = string
  description = "Local path to the Talos raw image downloaded from Omni dashboard (Hetzner variant)"
}

variable "location" {
  type    = string
  default = "fsn1"
}

variable "server_type" {
  type    = string
  default = "cx22"
}

variable "snapshot_name" {
  type    = string
  default = "talos-omni-hop"
}
```

- [ ] **Step 3: Create Packer template**

Create `clusters/hop/packer/hetzner-talos.pkr.hcl`:

```hcl
packer {
  required_plugins {
    hcloud = {
      source  = "github.com/hetznercloud/hcloud"
      version = ">= 1.6.0"
    }
  }
}

source "hcloud" "talos" {
  token       = var.hcloud_token
  location    = var.location
  server_type = var.server_type
  image       = "ubuntu-24.04"
  snapshot_name = var.snapshot_name
  ssh_username  = "root"

  rescue = "linux64"
}

build {
  sources = ["source.hcloud.talos"]

  # The server boots into rescue mode (Linux live environment).
  # We dd the Talos image directly onto the disk, overwriting Ubuntu.
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

- [ ] **Step 4: Create .gitignore**

Create `clusters/hop/packer/.gitignore`:

```
# Packer cache
.packer_cache/
packer_cache/

# Downloaded Talos images
*.raw
*.raw.xz
*.iso

# Packer crash logs
crash.log
```

- [ ] **Step 5: Validate Packer template**

```bash
cd clusters/hop/packer
packer init .
packer validate -var "hcloud_token=dummy" -var "talos_image_path=/tmp/talos.raw.xz" .
```

Expected: Template is valid

- [ ] **Step 6: Commit**

```bash
git add clusters/hop/packer/
git commit -m "feat(hop): add Packer template for Hetzner Talos image build"
```

### Task 2: Provision Hetzner Server and Omni Registration

This task involves manual steps — the Packer build, Hetzner server creation, and Omni cluster allocation. These are documented as a `# manual-operation` block since they require credentials and Omni dashboard interaction.

- [ ] **Step 1: Document the provisioning procedure**

The following steps are executed manually (not in Git):

```yaml
# manual-operation
id: phaseXX-hop-hetzner-provision
phase: XX
app: hop-infrastructure
plan: docs/superpowers/plans/2026-03-16-phaseXX-hop-public-edge.md
when: "After Task 1 — Packer template is committed"
why_manual: "Requires Hetzner API token, Omni dashboard image download, and cluster allocation"
commands:
  - "Download Talos Hetzner image from Omni dashboard (Infrastructure → Download Installation Media → Hetzner Cloud)"
  - "packer build -var 'hcloud_token=<TOKEN>' -var 'talos_image_path=<PATH_TO_DOWNLOADED_IMAGE>' clusters/hop/packer/"
  - "hcloud volume create --name hop-data --size 10 --location fsn1"
  - "hcloud server create --name hop-1 --type cx22 --location fsn1 --image <SNAPSHOT_ID> --volume hop-data"
  - "In Omni dashboard: allocate the new machine to a cluster named 'hop' as control-plane + worker"
  - "hcloud firewall create --name hop-fw"
  - "hcloud firewall add-rule hop-fw --direction in --protocol tcp --port 80 --source-ips 0.0.0.0/0 --source-ips ::/0"
  - "hcloud firewall add-rule hop-fw --direction in --protocol tcp --port 443 --source-ips 0.0.0.0/0 --source-ips ::/0"
  - "hcloud firewall add-rule hop-fw --direction in --protocol udp --port 3478 --source-ips 0.0.0.0/0 --source-ips ::/0"
  - "hcloud firewall apply-to-resource hop-fw --type server --server hop-1"
verify:
  - "omnictl get machines  # should show hop-1 registered"
  - "omnictl get clusters  # should show 'hop' cluster"
  - "kubectl --kubeconfig <HOP_KUBECONFIG> get nodes  # should show hop-1 Ready"
  - "hcloud volume list  # should show hop-data attached to hop-1"
status: pending
```

- [ ] **Step 2: Create Talos machine config patch for Hetzner Volume mount**

After the server is running in Omni, apply a machine config patch to mount the Hetzner Volume. The volume device path is typically `/dev/disk/by-id/scsi-0HC_Volume_<VOLUME_ID>`.

```yaml
# manual-operation
id: phaseXX-hop-volume-mount-patch
phase: XX
app: hop-infrastructure
plan: docs/superpowers/plans/2026-03-16-phaseXX-hop-public-edge.md
when: "After hop-1 is registered in Omni and hop-data volume is attached"
why_manual: "Requires Omni machine config patch with actual Hetzner Volume device ID"
commands:
  - |
    # First, format the volume (one-time via Talos machine config disk partition)
    # Then mount it using kubelet extraMounts so pods can access it
    cat <<'EOF' > /tmp/hop-volume-patch.yaml
    machine:
      disks:
        - device: /dev/disk/by-id/scsi-0HC_Volume_<VOLUME_ID>
          partitions:
            - mountpoint: /var/mnt/hop-data
              size: 0
      kubelet:
        extraMounts:
          - destination: /var/mnt/hop-data
            type: bind
            source: /var/mnt/hop-data
            options: ["bind", "rshared", "rw"]
    EOF
  - "omnictl apply -f /tmp/hop-volume-patch.yaml  # apply as cluster-level or machine-level patch for hop"
verify:
  - "talosctl --nodes <HOP_IP> read /proc/mounts | grep hop-data"
status: pending
```

- [ ] **Step 3: Set up DNS records**

```yaml
# manual-operation
id: phaseXX-hop-dns-records
phase: XX
app: hop-infrastructure
plan: docs/superpowers/plans/2026-03-16-phaseXX-hop-public-edge.md
when: "After hop-1 has a public IP"
why_manual: "Cloudflare DNS changes via UI or API — depends on user's Cloudflare setup"
commands:
  - "Create A record: *.hop.derio.net → <HETZNER_PUBLIC_IP> (DNS only, no proxy)"
  - "Create A record: blog.derio.net → <HETZNER_PUBLIC_IP> (DNS only, no proxy)"
  - "Create A record: www.derio.net → <HETZNER_PUBLIC_IP> (DNS only, no proxy)"
verify:
  - "dig +short *.hop.derio.net  # should return Hetzner IP"
  - "dig +short blog.derio.net  # should return Hetzner IP"
  - "dig +short www.derio.net  # should return Hetzner IP"
status: pending
```

- [ ] **Step 4: Commit the manual-operation blocks to the plan**

These blocks are already in this plan file. After the manual steps are executed, update their `status:` fields to `done`.

---

## Chunk 2: Hop ArgoCD Bootstrap

### Task 3: Hop App-of-Apps Root Chart

**Files:**
- Create: `clusters/hop/apps/root/Chart.yaml`
- Create: `clusters/hop/apps/root/values.yaml`
- Create: `clusters/hop/apps/root/templates/project.yaml`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/root/templates
```

- [ ] **Step 2: Create Chart.yaml**

Create `clusters/hop/apps/root/Chart.yaml`:

```yaml
apiVersion: v2
name: hop-infrastructure
version: 1.0.0
description: App-of-Apps for hop edge cluster infrastructure
```

- [ ] **Step 3: Create values.yaml**

Create `clusters/hop/apps/root/values.yaml`:

```yaml
# Git repo containing Helm values for each app
repoURL: https://github.com/derio-net/frank.git
targetRevision: main

# Cluster destination
destination:
  server: https://kubernetes.default.svc
```

- [ ] **Step 4: Create AppProject**

Create `clusters/hop/apps/root/templates/project.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: hop-infrastructure
  namespace: argocd
spec:
  description: Hop edge cluster infrastructure
  sourceRepos:
    - "https://github.com/derio-net/frank.git"
    - "https://argoproj.github.io/argo-helm"
  destinations:
    - namespace: "*"
      server: https://kubernetes.default.svc
  clusterResourceWhitelist:
    - group: "*"
      kind: "*"
```

- [ ] **Step 5: Commit**

```bash
git add clusters/hop/apps/root/
git commit -m "feat(hop): add app-of-apps root chart for Hop cluster"
```

### Task 4: Bootstrap ArgoCD on Hop

ArgoCD must be installed on Hop before the app-of-apps can work. This is a bootstrap manual step.

- [ ] **Step 1: Create ArgoCD values for Hop**

Create `clusters/hop/apps/argocd/values.yaml`:

```yaml
## ArgoCD Helm values for Hop (minimal single-replica)
## Chart: argo-cd (argo/argo-cd)
## Repo: https://argoproj.github.io/argo-helm

# Single-replica minimal install for edge node
controller:
  replicas: 1
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      memory: 512Mi

server:
  replicas: 1
  extraArgs:
    - --insecure
  # No external LoadBalancer — ArgoCD is cluster-internal only
  service:
    type: ClusterIP
  resources:
    requests:
      cpu: 50m
      memory: 128Mi
    limits:
      memory: 256Mi

repoServer:
  replicas: 1
  resources:
    requests:
      cpu: 50m
      memory: 128Mi
    limits:
      memory: 256Mi

redis:
  enabled: true
  resources:
    requests:
      cpu: 50m
      memory: 64Mi
    limits:
      memory: 128Mi

dex:
  enabled: false

applicationSet:
  enabled: false

notifications:
  enabled: false
```

- [ ] **Step 2: Create ArgoCD Application CR template**

Create `clusters/hop/apps/root/templates/argocd.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argocd
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: hop-infrastructure
  sources:
    - repoURL: https://argoproj.github.io/argo-helm
      chart: argo-cd
      targetRevision: "9.4.6"
      helm:
        releaseName: argocd
        valueFiles:
          - $values/clusters/hop/apps/argocd/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: argocd
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - CreateNamespace=false
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      namespace: argocd
      jsonPointers:
        - /data
```

- [ ] **Step 3: Document ArgoCD bootstrap procedure**

```yaml
# manual-operation
id: phaseXX-hop-argocd-bootstrap
phase: XX
app: argocd (hop)
plan: docs/superpowers/plans/2026-03-16-phaseXX-hop-public-edge.md
when: "After Task 3 — Hop root chart is committed and hop-1 is Ready"
why_manual: "ArgoCD must be Helm-installed before it can manage itself"
commands:
  - "export KUBECONFIG=<HOP_KUBECONFIG>"
  - "kubectl create namespace argocd"
  - "helm repo add argo https://argoproj.github.io/argo-helm"
  - "helm install argocd argo/argo-cd --version 9.4.6 --namespace argocd -f clusters/hop/apps/argocd/values.yaml"
  - |
    kubectl apply -f - <<'EOF'
    apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
      name: root
      namespace: argocd
    spec:
      project: default
      source:
        repoURL: https://github.com/derio-net/frank.git
        targetRevision: main
        path: clusters/hop/apps/root
      destination:
        server: https://kubernetes.default.svc
        namespace: argocd
      syncPolicy:
        automated:
          prune: false
          selfHeal: true
    EOF
verify:
  - "kubectl -n argocd get pods  # all pods Running"
  - "kubectl -n argocd get app root  # should show Synced/Healthy"
  - "# Note: root app initially uses project:default (AppProject hop-infrastructure doesn't exist yet). After first sync creates the AppProject, update: argocd app set root --project hop-infrastructure"
status: pending
```

- [ ] **Step 4: Commit**

```bash
git add clusters/hop/apps/argocd/ clusters/hop/apps/root/templates/argocd.yaml
git commit -m "feat(hop): add ArgoCD values and Application CR for Hop"
```

---

## Chunk 3: Storage and Headscale

### Task 5: Static Storage (PV + StorageClass)

**Files:**
- Create: `clusters/hop/apps/root/templates/storage.yaml`
- Create: `clusters/hop/apps/storage/manifests/storageclass.yaml`
- Create: `clusters/hop/apps/storage/manifests/pv-headscale.yaml`
- Create: `clusters/hop/apps/storage/manifests/pv-caddy.yaml`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/storage/manifests
```

- [ ] **Step 2: Create StorageClass**

Create `clusters/hop/apps/storage/manifests/storageclass.yaml`:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: hetzner-volume
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: Immediate
```

- [ ] **Step 3: Create static PV for Headscale**

Create `clusters/hop/apps/storage/manifests/pv-headscale.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: headscale-data
spec:
  capacity:
    storage: 2Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: hetzner-volume
  local:
    path: /var/mnt/hop-data/headscale
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: Exists
```

- [ ] **Step 4: Create static PV for Caddy**

Create `clusters/hop/apps/storage/manifests/pv-caddy.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: caddy-data
spec:
  capacity:
    storage: 1Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: hetzner-volume
  local:
    path: /var/mnt/hop-data/caddy
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: Exists
```

- [ ] **Step 5: Create Application CR for storage**

Create `clusters/hop/apps/root/templates/storage.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: storage
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: hop-infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: clusters/hop/apps/storage/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: default
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
```

- [ ] **Step 6: Commit**

```bash
git add clusters/hop/apps/storage/ clusters/hop/apps/root/templates/storage.yaml
git commit -m "feat(hop): add static PVs and StorageClass for Hetzner Volume"
```

### Task 6: Headscale Deployment

**Files:**
- Create: `clusters/hop/apps/root/templates/ns-headscale.yaml`
- Create: `clusters/hop/apps/root/templates/headscale.yaml`
- Create: `clusters/hop/apps/headscale/manifests/configmap.yaml`
- Create: `clusters/hop/apps/headscale/manifests/pvc.yaml`
- Create: `clusters/hop/apps/headscale/manifests/deployment.yaml`
- Create: `clusters/hop/apps/headscale/manifests/service.yaml`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/headscale/manifests
```

- [ ] **Step 2: Create namespace template**

Create `clusters/hop/apps/root/templates/ns-headscale.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: headscale-system
  labels:
    pod-security.kubernetes.io/enforce: baseline
```

- [ ] **Step 3: Create Headscale ConfigMap**

Create `clusters/hop/apps/headscale/manifests/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: headscale-config
  namespace: headscale-system
data:
  config.yaml: |
    server_url: https://headscale.hop.derio.net
    listen_addr: 0.0.0.0:8080
    metrics_listen_addr: 0.0.0.0:9090
    grpc_listen_addr: 0.0.0.0:50443
    grpc_allow_insecure: false

    database:
      type: sqlite
      sqlite:
        path: /var/lib/headscale/db.sqlite

    noise:
      private_key_path: /var/lib/headscale/noise_private.key

    prefixes:
      v4: 100.64.0.0/10
      v6: fd7a:115c:a1e0::/48
      allocation: sequential

    derp:
      server:
        enabled: true
        region_id: 999
        region_code: hop
        region_name: "Hop DERP"
        stun_listen_addr: 0.0.0.0:3478
      urls:
        - https://controlplane.tailscale.com/derpmap/default
      paths: []
      auto_update_enabled: false

    dns:
      base_domain: mesh.hop.derio.net
      magic_dns: true
      nameservers:
        global:
          - 1.1.1.1
          - 8.8.8.8

    log:
      level: info

    policy:
      mode: file
      path: /etc/headscale/acl.yaml

  acl.yaml: |
    # Headscale ACL policy
    # Allow all traffic within the mesh for now — tighten later
    acls:
      - action: accept
        src:
          - "*"
        dst:
          - "*:*"
```

- [ ] **Step 4: Create Headscale PVC**

Create `clusters/hop/apps/headscale/manifests/pvc.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: headscale-data
  namespace: headscale-system
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: hetzner-volume
  resources:
    requests:
      storage: 2Gi
  volumeName: headscale-data
```

- [ ] **Step 5: Create Headscale Deployment**

Create `clusters/hop/apps/headscale/manifests/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: headscale
  namespace: headscale-system
  labels:
    app.kubernetes.io/name: headscale
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: headscale
  template:
    metadata:
      labels:
        app.kubernetes.io/name: headscale
    spec:
      containers:
        - name: headscale
          image: headscale/headscale:0.25.1
          command: ["headscale", "serve"]
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
            - name: grpc
              containerPort: 50443
              protocol: TCP
            - name: metrics
              containerPort: 9090
              protocol: TCP
            - name: stun
              containerPort: 3478
              protocol: UDP
              hostPort: 3478
          volumeMounts:
            - name: config
              mountPath: /etc/headscale
              readOnly: true
            - name: data
              mountPath: /var/lib/headscale
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              memory: 256Mi
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
      volumes:
        - name: config
          configMap:
            name: headscale-config
        - name: data
          persistentVolumeClaim:
            claimName: headscale-data
```

- [ ] **Step 6: Create Headscale Service**

Create `clusters/hop/apps/headscale/manifests/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: headscale
  namespace: headscale-system
spec:
  selector:
    app.kubernetes.io/name: headscale
  ports:
    - name: http
      port: 8080
      targetPort: http
      protocol: TCP
    - name: grpc
      port: 50443
      targetPort: grpc
      protocol: TCP
```

- [ ] **Step 7: Create Application CR for Headscale**

Create `clusters/hop/apps/root/templates/headscale.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: headscale
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: hop-infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: clusters/hop/apps/headscale/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: headscale-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

- [ ] **Step 8: Commit**

```bash
git add clusters/hop/apps/headscale/ clusters/hop/apps/root/templates/ns-headscale.yaml clusters/hop/apps/root/templates/headscale.yaml
git commit -m "feat(hop): add Headscale deployment with embedded DERP"
```

### Task 7: Headplane Deployment

**Files:**
- Create: `clusters/hop/apps/root/templates/headplane.yaml`
- Create: `clusters/hop/apps/headplane/manifests/deployment.yaml`
- Create: `clusters/hop/apps/headplane/manifests/service.yaml`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/headplane/manifests
```

- [ ] **Step 2: Create Headplane Deployment**

Create `clusters/hop/apps/headplane/manifests/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: headplane
  namespace: headscale-system
  labels:
    app.kubernetes.io/name: headplane
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: headplane
  template:
    metadata:
      labels:
        app.kubernetes.io/name: headplane
    spec:
      serviceAccountName: headplane
      containers:
        - name: headplane
          image: ghcr.io/tale/headplane:0.5.5
          ports:
            - name: http
              containerPort: 3000
              protocol: TCP
          env:
            - name: HEADSCALE_URL
              value: "http://headscale.headscale-system.svc:8080"
            - name: HEADSCALE_INTEGRATION
              value: "kubernetes"
            - name: KUBERNETES_NAMESPACE
              value: "headscale-system"
            - name: KUBERNETES_POD_LABEL
              value: "app.kubernetes.io/name=headscale"
            - name: KUBERNETES_CONTAINER
              value: "headscale"
          resources:
            requests:
              cpu: 25m
              memory: 64Mi
            limits:
              memory: 128Mi
```

- [ ] **Step 3: Create Headplane Service**

Create `clusters/hop/apps/headplane/manifests/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: headplane
  namespace: headscale-system
spec:
  selector:
    app.kubernetes.io/name: headplane
  ports:
    - name: http
      port: 3000
      targetPort: http
      protocol: TCP
```

- [ ] **Step 4: Create RBAC for Headplane's Kubernetes integration**

Create `clusters/hop/apps/headplane/manifests/rbac.yaml`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: headplane
  namespace: headscale-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: headplane
  namespace: headscale-system
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: headplane
  namespace: headscale-system
subjects:
  - kind: ServiceAccount
    name: headplane
    namespace: headscale-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: headplane
```

The `serviceAccountName: headplane` is already included in the deployment YAML from Step 2.

- [ ] **Step 5: Create Application CR for Headplane**

Create `clusters/hop/apps/root/templates/headplane.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: headplane
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: hop-infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: clusters/hop/apps/headplane/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: headscale-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
```

- [ ] **Step 6: Commit**

```bash
git add clusters/hop/apps/headplane/ clusters/hop/apps/root/templates/headplane.yaml
git commit -m "feat(hop): add Headplane web UI for Headscale management"
```

---

## Chunk 4: Caddy, Blog, and Landing Page

### Task 8: Caddy Reverse Proxy

**Files:**
- Create: `clusters/hop/apps/root/templates/ns-caddy.yaml`
- Create: `clusters/hop/apps/root/templates/caddy.yaml`
- Create: `clusters/hop/apps/caddy/manifests/configmap.yaml`
- Create: `clusters/hop/apps/caddy/manifests/pvc.yaml`
- Create: `clusters/hop/apps/caddy/manifests/deployment.yaml`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/caddy/manifests
```

- [ ] **Step 2: Create namespace template**

Create `clusters/hop/apps/root/templates/ns-caddy.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: caddy-system
  labels:
    pod-security.kubernetes.io/enforce: baseline
```

- [ ] **Step 3: Create Caddyfile ConfigMap**

Create `clusters/hop/apps/caddy/manifests/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: caddy-config
  namespace: caddy-system
data:
  Caddyfile: |
    # Global options
    {
      email admin@derio.net
      acme_dns cloudflare {env.CF_API_TOKEN}
    }

    # --- Public routes ---

    # Headscale coordination server (public — clients must reach it)
    headscale.hop.derio.net {
      reverse_proxy headscale.headscale-system.svc:8080
    }

    # Blog (public)
    blog.derio.net {
      handle /frank* {
        reverse_proxy blog.blog-system.svc:8080
      }
      handle {
        redir https://blog.derio.net/frank{uri} permanent
      }
    }

    # Portfolio / personal site (public — placeholder for now)
    www.derio.net {
      respond "Coming soon." 200
    }

    # --- Private routes (Tailscale mesh only) ---

    # Headplane (Headscale admin UI)
    headplane.hop.derio.net {
      @not_mesh not remote_ip 100.64.0.0/10
      respond @not_mesh "Forbidden" 403
      reverse_proxy headplane.headscale-system.svc:3000
    }

    # Private landing page
    entry.hop.derio.net {
      @not_mesh not remote_ip 100.64.0.0/10
      respond @not_mesh "Forbidden" 403
      reverse_proxy landing.landing-system.svc:8080
    }

    # Note: DERP relay traffic goes through the main headscale.hop.derio.net
    # block above — Headscale handles /derp paths internally. No separate
    # route block needed.
```

- [ ] **Step 4: Create Caddy PVC**

Create `clusters/hop/apps/caddy/manifests/pvc.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: caddy-data
  namespace: caddy-system
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: hetzner-volume
  resources:
    requests:
      storage: 1Gi
  volumeName: caddy-data
```

- [ ] **Step 5: Create Caddy Deployment**

Create `clusters/hop/apps/caddy/manifests/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: caddy
  namespace: caddy-system
  labels:
    app.kubernetes.io/name: caddy
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: caddy
  template:
    metadata:
      labels:
        app.kubernetes.io/name: caddy
    spec:
      containers:
        - name: caddy
          image: ghcr.io/derio-net/caddy-cloudflare:2.9
          ports:
            - name: http
              containerPort: 80
              hostPort: 80
              protocol: TCP
            - name: https
              containerPort: 443
              hostPort: 443
              protocol: TCP
          env:
            - name: CF_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: caddy-cloudflare
                  key: api-token
          volumeMounts:
            - name: config
              mountPath: /etc/caddy
              readOnly: true
            - name: data
              mountPath: /data
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              memory: 256Mi
          readinessProbe:
            httpGet:
              path: /
              port: http
              scheme: HTTP
              httpHeaders:
                - name: Host
                  value: www.derio.net
            initialDelaySeconds: 5
            periodSeconds: 10
      volumes:
        - name: config
          configMap:
            name: caddy-config
        - name: data
          persistentVolumeClaim:
            claimName: caddy-data
```

**Note:** The deployment uses `ghcr.io/derio-net/caddy-cloudflare:2.9` — a custom Caddy image with the Cloudflare DNS plugin. This image must be built and pushed (Task 12) before Caddy can deploy. Task 12 is in Chunk 5 but should be run first if deploying Caddy.

- [ ] **Step 6: Create Caddy Cloudflare secret**

```yaml
# manual-operation
id: phaseXX-hop-caddy-cloudflare-secret
phase: XX
app: caddy
plan: docs/superpowers/plans/2026-03-16-phaseXX-hop-public-edge.md
when: "Before Caddy deployment — needs Cloudflare API token"
why_manual: "SOPS-encrypted secret applied out-of-band"
commands:
  - |
    cat <<'EOF' > /tmp/caddy-cloudflare.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: caddy-cloudflare
      namespace: caddy-system
    type: Opaque
    stringData:
      api-token: "<CLOUDFLARE_API_TOKEN_WITH_DNS_EDIT>"
    EOF
  - "sops --encrypt --age <AGE_PUBLIC_KEY> /tmp/caddy-cloudflare.yaml > secrets/hop/caddy-cloudflare.yaml"
  - "sops --decrypt secrets/hop/caddy-cloudflare.yaml | kubectl --kubeconfig <HOP_KUBECONFIG> apply -f -"
  - "rm /tmp/caddy-cloudflare.yaml"
verify:
  - "kubectl --kubeconfig <HOP_KUBECONFIG> -n caddy-system get secret caddy-cloudflare"
status: pending
```

- [ ] **Step 7: Create Application CR for Caddy**

Create `clusters/hop/apps/root/templates/caddy.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: caddy
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: hop-infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: clusters/hop/apps/caddy/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: caddy-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

- [ ] **Step 8: Commit**

```bash
git add clusters/hop/apps/caddy/ clusters/hop/apps/root/templates/ns-caddy.yaml clusters/hop/apps/root/templates/caddy.yaml
git commit -m "feat(hop): add Caddy reverse proxy with Cloudflare DNS challenge"
```

### Task 9: Blog Container and Deployment

**Files:**
- Create: `clusters/hop/apps/root/templates/ns-blog.yaml`
- Create: `clusters/hop/apps/root/templates/blog.yaml`
- Create: `clusters/hop/apps/blog/manifests/deployment.yaml`
- Create: `clusters/hop/apps/blog/manifests/service.yaml`
- Create: `blog/Dockerfile`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/blog/manifests
```

- [ ] **Step 2: Create namespace template**

Create `clusters/hop/apps/root/templates/ns-blog.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: blog-system
  labels:
    pod-security.kubernetes.io/enforce: baseline
```

- [ ] **Step 3: Create blog Dockerfile**

Create `blog/Dockerfile`:

```dockerfile
# Stage 1: Build Hugo site
FROM hugomods/hugo:exts-0.157.0 AS builder
WORKDIR /src
COPY . .
RUN hugo --minify --baseURL https://blog.derio.net

# Stage 2: Serve with Caddy
FROM caddy:2.9-alpine
COPY --from=builder /src/public /usr/share/caddy
RUN printf ':8080 {\n    root * /usr/share/caddy\n    file_server\n    try_files {path} {path}/ /frank/index.html\n    header Cache-Control "public, max-age=3600"\n}\n' > /etc/caddy/Caddyfile
EXPOSE 8080
```

- [ ] **Step 4: Create Blog Deployment**

Create `clusters/hop/apps/blog/manifests/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: blog
  namespace: blog-system
  labels:
    app.kubernetes.io/name: blog
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: blog
  template:
    metadata:
      labels:
        app.kubernetes.io/name: blog
    spec:
      containers:
        - name: blog
          image: ghcr.io/derio-net/blog:latest
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              memory: 64Mi
          readinessProbe:
            httpGet:
              path: /frank/
              port: http
            initialDelaySeconds: 3
            periodSeconds: 10
```

- [ ] **Step 5: Create Blog Service**

Create `clusters/hop/apps/blog/manifests/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: blog
  namespace: blog-system
spec:
  selector:
    app.kubernetes.io/name: blog
  ports:
    - name: http
      port: 8080
      targetPort: http
      protocol: TCP
```

- [ ] **Step 6: Create Application CR for Blog**

Create `clusters/hop/apps/root/templates/blog.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: blog
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: hop-infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: clusters/hop/apps/blog/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: blog-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
```

- [ ] **Step 7: Commit**

```bash
git add blog/Dockerfile clusters/hop/apps/blog/ clusters/hop/apps/root/templates/ns-blog.yaml clusters/hop/apps/root/templates/blog.yaml
git commit -m "feat(hop): add blog container and ArgoCD deployment"
```

### Task 10: Landing Page

**Files:**
- Create: `clusters/hop/apps/root/templates/landing.yaml`
- Create: `clusters/hop/apps/landing/manifests/deployment.yaml`
- Create: `clusters/hop/apps/landing/manifests/service.yaml`
- Create: `clusters/hop/apps/landing/manifests/configmap.yaml`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/landing/manifests
```

- [ ] **Step 2: Create landing page HTML**

Create `clusters/hop/apps/landing/manifests/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: landing-html
  namespace: landing-system
data:
  index.html: |
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Hop — Entry Point</title>
      <style>
        body { font-family: system-ui, sans-serif; max-width: 600px; margin: 50px auto; padding: 0 20px; color: #e0e0e0; background: #1a1a2e; }
        h1 { color: #64ffda; }
        a { color: #82b1ff; }
        .services { list-style: none; padding: 0; }
        .services li { padding: 8px 0; border-bottom: 1px solid #2a2a3e; }
      </style>
    </head>
    <body>
      <h1>🐰 Hop — Entry Point</h1>
      <p>Welcome to the homelab mesh. You're connected via Tailscale.</p>
      <h2>Services</h2>
      <ul class="services">
        <li><a href="https://headplane.hop.derio.net">Headplane</a> — Mesh management</li>
        <li><a href="https://argocd.frank.derio.net">ArgoCD</a> — Frank cluster</li>
        <li><a href="https://grafana.frank.derio.net">Grafana</a> — Monitoring</li>
        <li><a href="https://longhorn.frank.derio.net">Longhorn</a> — Storage</li>
        <li><a href="https://blog.derio.net/frank">Blog</a> — Frank blog</li>
      </ul>
    </body>
    </html>
```

- [ ] **Step 3: Create Landing Deployment**

Create `clusters/hop/apps/landing/manifests/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: landing
  namespace: landing-system
  labels:
    app.kubernetes.io/name: landing
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: landing
  template:
    metadata:
      labels:
        app.kubernetes.io/name: landing
    spec:
      containers:
        - name: landing
          image: caddy:2.9-alpine
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          volumeMounts:
            - name: html
              mountPath: /usr/share/caddy
              readOnly: true
            - name: caddyfile
              mountPath: /etc/caddy
              readOnly: true
          resources:
            requests:
              cpu: 5m
              memory: 16Mi
            limits:
              memory: 32Mi
      volumes:
        - name: html
          configMap:
            name: landing-html
        - name: caddyfile
          configMap:
            name: landing-caddy
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: landing-caddy
  namespace: landing-system
data:
  Caddyfile: |
    :8080 {
      root * /usr/share/caddy
      file_server
    }
```

- [ ] **Step 4: Create Landing Service**

Create `clusters/hop/apps/landing/manifests/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: landing
  namespace: landing-system
spec:
  selector:
    app.kubernetes.io/name: landing
  ports:
    - name: http
      port: 8080
      targetPort: http
      protocol: TCP
```

- [ ] **Step 5: Create namespace template**

Create `clusters/hop/apps/root/templates/ns-landing.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: landing-system
  labels:
    pod-security.kubernetes.io/enforce: baseline
```

- [ ] **Step 6: Create Application CR**

Create `clusters/hop/apps/root/templates/landing.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: landing
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: hop-infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: clusters/hop/apps/landing/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: landing-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
```

- [ ] **Step 7: Commit**

```bash
git add clusters/hop/apps/landing/ clusters/hop/apps/root/templates/ns-landing.yaml clusters/hop/apps/root/templates/landing.yaml
git commit -m "feat(hop): add private landing page for mesh members"
```

---

## Chunk 5: CI Pipeline, Caddy Image, and Blog Migration

### Task 11: Update Blog CI Pipeline

**Files:**
- Modify: `.github/workflows/deploy-blog.yml`

- [ ] **Step 1: Update workflow to build and push container image**

Modify `.github/workflows/deploy-blog.yml` to add a container build job alongside the existing GitHub Pages deployment (parallel during transition):

```yaml
name: Deploy Blog

on:
  push:
    branches: [main]
    paths:
      - "blog/**"
  workflow_dispatch:

concurrency:
  group: "blog-deploy"
  cancel-in-progress: false

jobs:
  # Keep GitHub Pages deployment during transition
  build-pages:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          submodules: recursive

      - name: Setup Hugo
        uses: peaceiris/actions-hugo@75d2e84710de30f6ff7268e08f310b60ef14033f # v3.0.0
        with:
          hugo-version: "0.157.0"
          extended: true

      - name: Build
        working-directory: blog
        run: hugo --minify

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: blog/public

  deploy-pages:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build-pages
    permissions:
      pages: write
      id-token: write
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4

  # New: build and push container image for Hop
  build-container:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          submodules: recursive

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push blog image
        uses: docker/build-push-action@v6
        with:
          context: blog
          push: true
          tags: |
            ghcr.io/derio-net/blog:latest
            ghcr.io/derio-net/blog:${{ github.sha }}
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/deploy-blog.yml
git commit -m "feat(hop): add container build job to blog CI pipeline"
```

### Task 12: Build Custom Caddy Image with Cloudflare Plugin

**Files:**
- Create: `clusters/hop/apps/caddy/Dockerfile`
- Create: `.github/workflows/build-caddy.yml`

- [ ] **Step 1: Create Caddy Dockerfile**

Create `clusters/hop/apps/caddy/Dockerfile`:

```dockerfile
FROM caddy:2.9-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2.9-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

- [ ] **Step 2: Create CI workflow for Caddy image**

Create `.github/workflows/build-caddy.yml`:

```yaml
name: Build Caddy Cloudflare

on:
  push:
    branches: [main]
    paths:
      - "clusters/hop/apps/caddy/Dockerfile"
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: clusters/hop/apps/caddy
          push: true
          tags: |
            ghcr.io/derio-net/caddy-cloudflare:2.9
            ghcr.io/derio-net/caddy-cloudflare:latest
```

- [ ] **Step 3: Update Caddy deployment to use custom image**

In `clusters/hop/apps/caddy/manifests/deployment.yaml`, change the image from `caddy:2.9-alpine` to `ghcr.io/derio-net/caddy-cloudflare:2.9`.

- [ ] **Step 4: Commit**

```bash
git add clusters/hop/apps/caddy/Dockerfile .github/workflows/build-caddy.yml clusters/hop/apps/caddy/manifests/deployment.yaml
git commit -m "feat(hop): add custom Caddy image with Cloudflare DNS plugin"
```

---

## Chunk 6: Secrets, Verification, and Documentation

### Task 13: SOPS-Encrypted Secrets

**Files:**
- Create: `secrets/hop/` directory

- [ ] **Step 1: Create secrets directory**

```bash
mkdir -p secrets/hop
```

- [ ] **Step 2: Document all secrets that need out-of-band application**

```yaml
# manual-operation
id: phaseXX-hop-secrets-bootstrap
phase: XX
app: hop-infrastructure
plan: docs/superpowers/plans/2026-03-16-phaseXX-hop-public-edge.md
when: "Before deploying Headscale and Caddy"
why_manual: "SOPS-encrypted secrets must be applied before the workloads start"
commands:
  - "mkdir -p secrets/hop"
  - |
    # Caddy Cloudflare API token (for ACME DNS challenge)
    cat <<'EOF' > /tmp/caddy-cloudflare.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: caddy-cloudflare
      namespace: caddy-system
    type: Opaque
    stringData:
      api-token: "<CLOUDFLARE_API_TOKEN>"
    EOF
    sops --encrypt --age <AGE_PUBLIC_KEY> /tmp/caddy-cloudflare.yaml > secrets/hop/caddy-cloudflare.yaml
    sops --decrypt secrets/hop/caddy-cloudflare.yaml | kubectl --kubeconfig <HOP_KUBECONFIG> apply -f -
    rm /tmp/caddy-cloudflare.yaml
verify:
  - "kubectl --kubeconfig <HOP_KUBECONFIG> -n caddy-system get secret caddy-cloudflare"
status: pending
```

**Note on Headscale noise private key:** Headscale auto-generates its noise private key on first boot and stores it in `/var/lib/headscale/noise_private.key` (on the PVC). This key is backed up by the daily CronJob (Task 14). If the volume is lost, a new key is generated and all clients must re-register. No pre-provisioning needed.

- [ ] **Step 3: Commit secrets directory**

```bash
echo "# SOPS-encrypted secrets for Hop cluster" > secrets/hop/README.md
git add secrets/hop/README.md
git commit -m "feat(hop): add secrets directory for Hop cluster"
```

### Task 14: Headscale DB Backup CronJob

**Files:**
- Create: `clusters/hop/apps/headscale/manifests/backup-cronjob.yaml`

- [ ] **Step 1: Create backup CronJob**

Create `clusters/hop/apps/headscale/manifests/backup-cronjob.yaml`:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: headscale-backup
  namespace: headscale-system
spec:
  schedule: "0 3 * * *"  # Daily at 3am UTC
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: alpine:3.20
              command:
                - /bin/sh
                - -c
                - |
                  apk add --no-cache sqlite
                  # Use SQLite .backup for a consistent copy (not just cp)
                  sqlite3 /var/lib/headscale/db.sqlite ".backup '/backup/headscale-$(date +%Y%m%d).db'"
                  # Keep only last 7 backups
                  ls -t /backup/headscale-*.db | tail -n +8 | xargs rm -f 2>/dev/null || true
                  echo "Backup complete: /backup/headscale-$(date +%Y%m%d).db"
              volumeMounts:
                - name: data
                  mountPath: /var/lib/headscale
                  readOnly: true
                - name: backup
                  mountPath: /backup
          volumes:
            - name: data
              persistentVolumeClaim:
                claimName: headscale-data
            - name: backup
              hostPath:
                path: /var/mnt/hop-data/backups/headscale
                type: DirectoryOrCreate
```

**Note:** This stores backups locally on the Hetzner Volume. For off-site backups (S3/NAS), enhance later with `rclone` or a similar tool once the mesh is operational.

- [ ] **Step 2: Commit**

```bash
git add clusters/hop/apps/headscale/manifests/backup-cronjob.yaml
git commit -m "feat(hop): add daily Headscale DB backup CronJob"
```

### Task 15: End-to-End Verification

- [ ] **Step 1: Verify all pods are running**

```bash
export KUBECONFIG=<HOP_KUBECONFIG>
kubectl get pods -A
```

Expected: All pods in `argocd`, `headscale-system`, `caddy-system`, `blog-system`, `landing-system` namespaces are `Running`.

- [ ] **Step 2: Verify ArgoCD apps are synced**

```bash
kubectl -n argocd get applications
```

Expected: All apps show `Synced` and `Healthy`.

- [ ] **Step 3: Verify public endpoints**

```bash
# Blog
curl -sI https://blog.derio.net/frank/ | head -5

# Headscale
curl -sI https://headscale.hop.derio.net/health | head -5

# www placeholder
curl -s https://www.derio.net
```

Expected: 200 OK responses.

- [ ] **Step 4: Verify private endpoint enforcement**

```bash
# From a non-mesh IP, headplane should return 403
curl -sI https://headplane.hop.derio.net | head -5
```

Expected: 403 Forbidden.

- [ ] **Step 5: Test Headscale client registration**

```yaml
# manual-operation
id: phaseXX-hop-headscale-first-client
phase: XX
app: headscale
plan: docs/superpowers/plans/2026-03-16-phaseXX-hop-public-edge.md
when: "After all Hop services are verified running"
why_manual: "Requires interactive Tailscale client setup on a personal device"
commands:
  - "kubectl --kubeconfig <HOP_KUBECONFIG> -n headscale-system exec -it deploy/headscale -- headscale users create default"
  - "kubectl --kubeconfig <HOP_KUBECONFIG> -n headscale-system exec -it deploy/headscale -- headscale preauthkeys create --user default --reusable --expiration 24h"
  - "# On client device: tailscale up --login-server https://headscale.hop.derio.net --authkey <PREAUTH_KEY>"
verify:
  - "kubectl --kubeconfig <HOP_KUBECONFIG> -n headscale-system exec -it deploy/headscale -- headscale nodes list"
status: pending
```

### Task 16: Update Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add Hop to Architecture section in CLAUDE.md**

Add to the Architecture code block:

```
clusters/
  hop/                   # Hop edge cluster (Hetzner CX22)
    apps/                # Hop ArgoCD App-of-Apps
      root/              # Entry point for Hop's Application CRs
      argocd/            # ArgoCD values (minimal single-replica)
      headscale/         # Headscale mesh coordination
      headplane/         # Headscale web UI
      caddy/             # Reverse proxy + TLS
      blog/              # Hugo blog container
      landing/           # Private landing page
      storage/           # Static PVs for Hetzner Volume
    packer/              # Packer template for Hetzner image
```

- [ ] **Step 2: Add Hop node to Nodes table**

```
| hop-1 | <HETZNER_IP> | control-plane+worker | Edge (Hetzner) | CX22, 2 vCPU, 4GB |
```

- [ ] **Step 3: Add Hop services to Services table**

```
| Headscale | headscale.hop.derio.net | Caddy (public) |
| Headplane | headplane.hop.derio.net | Caddy (mesh only) |
| Blog | blog.derio.net/frank | Caddy (public) |
| Landing | entry.hop.derio.net | Caddy (mesh only) |
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Hop cluster to CLAUDE.md architecture and service tables"
```

---

## Chunk 7: Repo Restructure (Deferrable)

> **This chunk is optional and deferrable.** It can be skipped entirely or executed as a separate phase after Hop is fully operational. Only proceed if you're confident in the rollback plan.

### Task 17: Restructure to Multi-Cluster Monorepo

**Files:**
- Move: `apps/` → `clusters/frank/apps/`
- Move: `patches/` → `clusters/frank/patches/`
- Modify: All 41 Application CR templates in `clusters/frank/apps/root/templates/`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Disable Frank ArgoCD auto-sync**

```bash
source .env
argocd app set root --sync-policy none --port-forward --port-forward-namespace argocd
```

- [ ] **Step 2: Move directories**

```bash
mkdir -p clusters/frank
git mv apps clusters/frank/apps
git mv patches clusters/frank/patches
```

- [ ] **Step 3: Update all Application CR template paths**

Every template in `clusters/frank/apps/root/templates/` that references `apps/<app>/values.yaml` or `apps/<app>/manifests` needs the path prefixed with `clusters/frank/`.

For Helm-based apps (using `$values` ref):
```
$values/apps/<app>/values.yaml  →  $values/clusters/frank/apps/<app>/values.yaml
```

For raw manifest apps (using `path`):
```
path: apps/<app>/manifests  →  path: clusters/frank/apps/<app>/manifests
```

Update all 41 templates. Use a script:

```bash
cd clusters/frank/apps/root/templates
# Fix $values/ references
sed -i '' 's|\$values/apps/|\$values/clusters/frank/apps/|g' *.yaml
# Fix path: references
sed -i '' 's|path: apps/|path: clusters/frank/apps/|g' *.yaml
```

Verify with:
```bash
grep -r 'apps/' clusters/frank/apps/root/templates/ | grep -v 'clusters/frank/apps/'
```

Expected: No output (all paths updated).

- [ ] **Step 4: Update Frank root app in ArgoCD**

The root Application's source path changes from `apps/root` to `clusters/frank/apps/root`:

```bash
argocd app set root --source-path clusters/frank/apps/root --port-forward --port-forward-namespace argocd
```

- [ ] **Step 5: Update Omni config patch paths**

```bash
# List current patches
omnictl get configpatches

# For each patch, export, update path references, and re-apply
# Example for one patch:
# omnictl get configpatch <PATCH_ID> -o yaml > /tmp/patch.yaml
# (edit path if needed)
# omnictl apply -f /tmp/patch.yaml
```

- [ ] **Step 6: Update CLAUDE.md**

Update the Architecture section to reflect the new structure. Update all path references throughout the file.

- [ ] **Step 7: Update blog posts with repo structure references**

Search blog posts for references to `apps/` or `patches/` and update them.

```bash
grep -rn 'apps/' blog/content/ | grep -v 'clusters/frank'
grep -rn 'patches/' blog/content/ | grep -v 'clusters/frank'
```

- [ ] **Step 8: Update CI workflows**

Check and update any workflow references:

```bash
grep -rn 'apps/' .github/workflows/
grep -rn 'patches/' .github/workflows/
```

- [ ] **Step 9: Commit the restructure as a single atomic commit**

```bash
git add -A
git commit -m "refactor: restructure repo to multi-cluster monorepo (apps/ → clusters/frank/apps/)"
```

- [ ] **Step 10: Push and verify Frank ArgoCD sync**

```bash
git push
# Manually trigger sync
argocd app sync root --port-forward --port-forward-namespace argocd
# Check all apps reconciled
argocd app list --port-forward --port-forward-namespace argocd
```

Expected: All apps `Synced` and `Healthy`.

- [ ] **Step 11: Re-enable auto-sync**

```bash
argocd app set root --sync-policy automated --self-heal --port-forward --port-forward-namespace argocd
```

- [ ] **Step 12: Commit any fixups**

If any paths were missed, fix them and commit:

```bash
git add -A
git commit -m "fix: correct remaining path references after repo restructure"
```
