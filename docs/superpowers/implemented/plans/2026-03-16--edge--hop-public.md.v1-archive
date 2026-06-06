# Hop: Public Edge Entrypoint — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a Hetzner Cloud CX23 running Talos Linux as "Hop" — a public-facing single-node Kubernetes cluster managed via `talosctl`, providing Headscale mesh networking for remote homelab access, Caddy reverse proxy with TLS, a Hugo blog, and a private landing page.

**Architecture:** Hop is a standalone Talos cluster living in `clusters/hop/` within the existing frank-cluster monorepo. Packer builds a Hetzner Cloud snapshot from the official Talos hcloud image. ArgoCD on Hop manages all workloads via an independent app-of-apps. Caddy handles all ingress via hostPort 80/443. Hetzner Volume provides persistent storage via Talos `machine.disks` config + static PV. A kernel-mode Tailscale DaemonSet gives hop-1 a mesh IP, enabling Caddy to distinguish mesh vs public traffic. MagicDNS `extra_records` provide split-DNS for mesh-only services.

**Tech Stack:** Talos Linux, talosctl, Packer (HCL), Hetzner Cloud (`hcloud` CLI), ArgoCD (Helm), Headscale, Headplane, Tailscale, Caddy, Hugo, Flannel CNI

**Status:** Deployed

**Notes:** Deployed 2026-03-18, plan finalized 2026-03-20. Post-deploy fixes applied 2026-03-21 (Deviations #11-14). All services healthy.

**Spec:** `docs/superpowers/specs/2026-03-16--edge--hop-public-design.md`

**Execution notes:** Chunks 1-6 (Tasks 1-15) were executed autonomously on 2026-03-18. Several manual steps failed or required adaptation, leading to an extended interactive debugging session. Deviations from the original plan are annotated inline at each affected step and collected in the [Deployment Deviations](#deployment-deviations-2026-03-18) section after Chunk 6.

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

### Task 1: Packer Image Build ✅

**Files:**
- Create: `clusters/hop/packer/hetzner-talos.pkr.hcl`
- Create: `clusters/hop/packer/variables.pkr.hcl`
- Create: `clusters/hop/packer/.gitignore`

- [x] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/packer
```

- [x] **Step 2: Create Packer variables file**

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

- [x] **Step 3: Create Packer template**

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

- [x] **Step 4: Create .gitignore**

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

- [x] **Step 5: Validate Packer template**

```bash
cd clusters/hop/packer
packer init .
packer validate -var "hcloud_token=dummy" -var "talos_image_path=/tmp/talos.raw.xz" .
```

Expected: Template is valid

- [x] **Step 6: Commit**

```bash
git add clusters/hop/packer/
git commit -m "feat(hop): add Packer template for Hetzner Talos image build"
```

> **Executed as planned.** All three files created and committed.

### Task 2: Provision Hetzner Server and Omni Registration ✅ DEVIATED

> **⚠️ Major deviation:** Omni was unreachable from Hetzner (`omni.frank.derio.net` is internal-only). Entire task executed via standalone `talosctl` instead. Used `talosctl gen config`, `talosctl apply-config --insecure`, and `talosctl bootstrap` directly. Server type changed from CX22 → CX23 (Hetzner renamed it). Firewall also opened TCP 6443 (K8s API) and TCP 50000 (talosctl) as break-glass recovery ports (both require mTLS). Talosconfig stored at `clusters/hop/talosconfig/` (gitignored). See [Deviation #1](#1-standalone-talos-not-omni), [#2](#2-server-type-cx23), [#7](#7-control-plane-scheduling), [#8](#8-hetzner-firewall-ports).

This task involves manual steps — the Packer build, Hetzner server creation, and ~~Omni cluster allocation~~ talosctl bootstrap. These are documented as a `# manual-operation` block since they require credentials and ~~Omni dashboard~~ CLI interaction.

- [x] **Step 1: Document the provisioning procedure**

The following steps are executed manually (not in Git):

```yaml
# manual-operation
id: edge-hop-hetzner-provision
layer: edge
app: hop-infrastructure
plan: docs/superpowers/plans/2026-03-16--edge--hop-public.md
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
status: done  # executed via talosctl instead of Omni — see deviation note above
```

- [x] **Step 2: Create Talos machine config patch for Hetzner Volume mount**

After the server is running ~~in Omni~~ via talosctl, apply a machine config patch to mount the Hetzner Volume. The volume device path is typically `/dev/disk/by-id/scsi-0HC_Volume_<VOLUME_ID>`.

```yaml
# manual-operation
id: edge-hop-volume-mount-patch
layer: edge
app: hop-infrastructure
plan: docs/superpowers/plans/2026-03-16--edge--hop-public.md
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
  - "talosctl apply-config --config-patch @/tmp/hop-volume-patch.yaml  # applied via talosctl, not omnictl"
verify:
  - "talosctl --nodes <HOP_IP> read /proc/mounts | grep hop-data"
status: done
```

- [x] **Step 3: Set up DNS records**

```yaml
# manual-operation
id: edge-hop-dns-records
layer: edge
app: hop-infrastructure
plan: docs/superpowers/plans/2026-03-16--edge--hop-public.md
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
status: done
```

- [x] **Step 4: Commit the manual-operation blocks to the plan**

These blocks are already in this plan file. After the manual steps are executed, update their `status:` fields to `done`.

> **Executed with deviations.** Standalone talosctl bootstrap instead of Omni. CX23 instead of CX22. Additional firewall ports (6443, 50000) opened. Control-plane taint removed manually. `.env_hop` created for Hop-specific environment variables.

---

## Chunk 2: Hop ArgoCD Bootstrap

### Task 3: Hop App-of-Apps Root Chart ✅

**Files:**
- Create: `clusters/hop/apps/root/Chart.yaml`
- Create: `clusters/hop/apps/root/values.yaml`
- Create: `clusters/hop/apps/root/templates/project.yaml`

- [x] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/root/templates
```

- [x] **Step 2: Create Chart.yaml**

Create `clusters/hop/apps/root/Chart.yaml`:

```yaml
apiVersion: v2
name: hop-infrastructure
version: 1.0.0
description: App-of-Apps for hop edge cluster infrastructure
```

- [x] **Step 3: Create values.yaml**

Create `clusters/hop/apps/root/values.yaml`:

```yaml
# Git repo containing Helm values for each app
repoURL: https://github.com/derio-net/frank.git
targetRevision: main

# Cluster destination
destination:
  server: https://kubernetes.default.svc
```

- [x] **Step 4: Create AppProject**

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

- [x] **Step 5: Commit**

```bash
git add clusters/hop/apps/root/
git commit -m "feat(hop): add app-of-apps root chart for Hop cluster"
```

### Task 4: Bootstrap ArgoCD on Hop ✅

ArgoCD must be installed on Hop before the app-of-apps can work. This is a bootstrap manual step.

- [x] **Step 1: Create ArgoCD values for Hop**

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

- [x] **Step 2: Create ArgoCD Application CR template**

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

- [x] **Step 3: Document ArgoCD bootstrap procedure**

```yaml
# manual-operation
id: edge-hop-argocd-bootstrap
layer: edge
app: argocd (hop)
plan: docs/superpowers/plans/2026-03-16--edge--hop-public.md
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

- [x] **Step 4: Commit**

```bash
git add clusters/hop/apps/argocd/ clusters/hop/apps/root/templates/argocd.yaml
git commit -m "feat(hop): add ArgoCD values and Application CR for Hop"
```

---

## Chunk 3: Storage and Headscale

### Task 5: Static Storage (PV + StorageClass) ✅

**Files:**
- Create: `clusters/hop/apps/root/templates/storage.yaml`
- Create: `clusters/hop/apps/storage/manifests/storageclass.yaml`
- Create: `clusters/hop/apps/storage/manifests/pv-headscale.yaml`
- Create: `clusters/hop/apps/storage/manifests/pv-caddy.yaml`

- [x] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/storage/manifests
```

- [x] **Step 2: Create StorageClass**

Create `clusters/hop/apps/storage/manifests/storageclass.yaml`:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: hetzner-volume
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: Immediate
```

- [x] **Step 3: Create static PV for Headscale**

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

- [x] **Step 4: Create static PV for Caddy**

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

- [x] **Step 5: Create Application CR for storage**

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

- [x] **Step 6: Commit**

```bash
git add clusters/hop/apps/storage/ clusters/hop/apps/root/templates/storage.yaml
git commit -m "feat(hop): add static PVs and StorageClass for Hetzner Volume"
```

### Task 6: Headscale Deployment ✅ DEVIATED

> **⚠️ Deviations:** (1) Added `tailscale-client.yaml` — kernel-mode Tailscale DaemonSet (`hostNetwork: true`, `privileged: true`) with ServiceAccount + Role + RoleBinding, giving hop-1 a real mesh IP so Caddy can distinguish mesh vs public traffic. (2) Added `extra_records` to Headscale DNS config for split-DNS (`headplane.hop.derio.net` → `100.64.0.4`, `entry.hop.derio.net` → `100.64.0.4`). (3) Namespace label changed from `baseline` → `privileged` for hostPort/privileged containers. See [Deviation #3](#3-tailscale-daemonset-for-mesh-routing), [#4](#4-magicdns-with-extra_records), [#5](#5-podsecurity-namespace-labels).

**Files:**
- Create: `clusters/hop/apps/root/templates/ns-headscale.yaml`
- Create: `clusters/hop/apps/root/templates/headscale.yaml`
- Create: `clusters/hop/apps/headscale/manifests/configmap.yaml`
- Create: `clusters/hop/apps/headscale/manifests/pvc.yaml`
- Create: `clusters/hop/apps/headscale/manifests/deployment.yaml`
- Create: `clusters/hop/apps/headscale/manifests/service.yaml`
- Create: `clusters/hop/apps/headscale/manifests/tailscale-client.yaml` *(added — not in original plan)*

- [x] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/headscale/manifests
```

- [x] **Step 2: Create namespace template**

Create `clusters/hop/apps/root/templates/ns-headscale.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: headscale-system
  labels:
    pod-security.kubernetes.io/enforce: baseline  # ACTUAL: changed to `privileged` (Deviation #5)
```

- [x] **Step 3: Create Headscale ConfigMap** *(actual: added `extra_records` for split-DNS — Deviation #4)*

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

- [x] **Step 4: Create Headscale PVC**

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

- [x] **Step 5: Create Headscale Deployment**

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

- [x] **Step 6: Create Headscale Service**

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

- [x] **Step 7: Create Application CR for Headscale**

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

- [x] **Step 8: Commit**

```bash
git add clusters/hop/apps/headscale/ clusters/hop/apps/root/templates/ns-headscale.yaml clusters/hop/apps/root/templates/headscale.yaml
git commit -m "feat(hop): add Headscale deployment with embedded DERP"
```

> **Executed with deviations.** All planned files created. Additionally: `tailscale-client.yaml` added (DaemonSet + RBAC), `extra_records` added to ConfigMap for split-DNS, namespace label changed to `privileged`.

### Task 7: Headplane Deployment ✅ DEVIATED

> **⚠️ Deviations:** Headplane v0.5.5 required far more than env vars. Added `configmap.yaml` (server config with `cookie_secret`, `config_path`, `config_strict: false`), `rbac.yaml` (ServiceAccount + Role + RoleBinding), API key injection via `HEADPLANE_HEADSCALE_API_KEY` env var from Secret. Removed `integration.kubernetes` (crashed trying to exec into Headscale pod). Headplane serves at `/admin/` base path — Caddy redirect added in Task 8. See [Deviation #6](#6-headplane-v055--config-base-path-and-api-key).

**Files:**
- Create: `clusters/hop/apps/root/templates/headplane.yaml`
- Create: `clusters/hop/apps/headplane/manifests/deployment.yaml`
- Create: `clusters/hop/apps/headplane/manifests/service.yaml`
- Create: `clusters/hop/apps/headplane/manifests/configmap.yaml` *(added — not in original plan)*
- Create: `clusters/hop/apps/headplane/manifests/rbac.yaml` *(added — not in original plan)*

- [x] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/headplane/manifests
```

- [x] **Step 2: Create Headplane Deployment** *(actual: env vars replaced with config file mount + API key Secret ref — Deviation #6)*

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

- [x] **Step 3: Create Headplane Service**

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

- [x] **Step 4: Create RBAC for Headplane's Kubernetes integration**

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

- [x] **Step 5: Create Application CR for Headplane**

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

- [x] **Step 6: Commit**

```bash
git add clusters/hop/apps/headplane/ clusters/hop/apps/root/templates/headplane.yaml
git commit -m "feat(hop): add Headplane web UI for Headscale management"
```

> **Executed with major deviations.** Env-var-only approach didn't work with Headplane v0.5.5. Required iterative debugging across multiple commits to add config file, remove K8s integration, set `config_strict: false`, inject API key, and handle `/admin/` base path. This was the most time-consuming deviation of the entire deployment.

---

## Chunk 4: Caddy, Blog, and Landing Page

### Task 8: Caddy Reverse Proxy ✅ DEVIATED

> **⚠️ Deviations:** (1) `caddy-system` namespace label changed from `baseline` → `privileged` for hostPort binding. (2) Caddyfile modified: added `redir / /admin/ permanent` for Headplane's `/admin/` base path. (3) Blog reverse proxy uses path stripping — Hugo outputs to root `/`, Caddy strips `/frank` prefix. See [Deviation #5](#5-podsecurity-namespace-labels), [#6](#6-headplane-v055--config-base-path-and-api-key), [#9](#9-blog-path-handling).

**Files:**
- Create: `clusters/hop/apps/root/templates/ns-caddy.yaml`
- Create: `clusters/hop/apps/root/templates/caddy.yaml`
- Create: `clusters/hop/apps/caddy/manifests/configmap.yaml`
- Create: `clusters/hop/apps/caddy/manifests/pvc.yaml`
- Create: `clusters/hop/apps/caddy/manifests/deployment.yaml`

- [x] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/caddy/manifests
```

- [x] **Step 2: Create namespace template**

Create `clusters/hop/apps/root/templates/ns-caddy.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: caddy-system
  labels:
    pod-security.kubernetes.io/enforce: baseline  # ACTUAL: changed to `privileged` (Deviation #5)
```

- [x] **Step 3: Create Caddyfile ConfigMap** *(actual: added `/admin/` redirect for Headplane, blog path stripping — Deviations #6, #9)*

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

- [x] **Step 4: Create Caddy PVC**

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

- [x] **Step 5: Create Caddy Deployment**

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

- [x] **Step 6: Create Caddy Cloudflare secret**

```yaml
# manual-operation
id: edge-hop-caddy-cloudflare-secret
layer: edge
app: caddy
plan: docs/superpowers/plans/2026-03-16--edge--hop-public.md
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

- [x] **Step 7: Create Application CR for Caddy**

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

- [x] **Step 8: Commit**

```bash
git add clusters/hop/apps/caddy/ clusters/hop/apps/root/templates/ns-caddy.yaml clusters/hop/apps/root/templates/caddy.yaml
git commit -m "feat(hop): add Caddy reverse proxy with Cloudflare DNS challenge"
```

### Task 9: Blog Container and Deployment ✅ DEVIATED

> **⚠️ Deviation:** Hugo outputs to root `/` regardless of `baseURL`. The Dockerfile's internal Caddyfile was modified to handle `/frank/*` routing at root and redirect `/frank` → `/frank/`. The external Caddy reverse proxy strips the `/frank` prefix before forwarding. See [Deviation #9](#9-blog-path-handling).

**Files:**
- Create: `clusters/hop/apps/root/templates/ns-blog.yaml`
- Create: `clusters/hop/apps/root/templates/blog.yaml`
- Create: `clusters/hop/apps/blog/manifests/deployment.yaml`
- Create: `clusters/hop/apps/blog/manifests/service.yaml`
- Create: `blog/Dockerfile`

- [x] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/blog/manifests
```

- [x] **Step 2: Create namespace template**

Create `clusters/hop/apps/root/templates/ns-blog.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: blog-system
  labels:
    pod-security.kubernetes.io/enforce: baseline
```

- [x] **Step 3: Create blog Dockerfile**

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

- [x] **Step 4: Create Blog Deployment**

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

- [x] **Step 5: Create Blog Service**

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

- [x] **Step 6: Create Application CR for Blog**

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

- [x] **Step 7: Commit**

```bash
git add blog/Dockerfile clusters/hop/apps/blog/ clusters/hop/apps/root/templates/ns-blog.yaml clusters/hop/apps/root/templates/blog.yaml
git commit -m "feat(hop): add blog container and ArgoCD deployment"
```

### Task 10: Landing Page ✅

**Files:**
- Create: `clusters/hop/apps/root/templates/landing.yaml`
- Create: `clusters/hop/apps/landing/manifests/deployment.yaml`
- Create: `clusters/hop/apps/landing/manifests/service.yaml`
- Create: `clusters/hop/apps/landing/manifests/configmap.yaml`

- [x] **Step 1: Create directory structure**

```bash
mkdir -p clusters/hop/apps/landing/manifests
```

- [x] **Step 2: Create landing page HTML**

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

- [x] **Step 3: Create Landing Deployment**

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

- [x] **Step 4: Create Landing Service**

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

- [x] **Step 5: Create namespace template**

Create `clusters/hop/apps/root/templates/ns-landing.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: landing-system
  labels:
    pod-security.kubernetes.io/enforce: baseline
```

- [x] **Step 6: Create Application CR**

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

- [x] **Step 7: Commit**

```bash
git add clusters/hop/apps/landing/ clusters/hop/apps/root/templates/ns-landing.yaml clusters/hop/apps/root/templates/landing.yaml
git commit -m "feat(hop): add private landing page for mesh members"
```

---

## Chunk 5: CI Pipeline, Caddy Image, and Blog Migration

### Task 11: Update Blog CI Pipeline ✅

**Files:**
- Modify: `.github/workflows/deploy-blog.yml`

- [x] **Step 1: Update workflow to build and push container image**

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

- [x] **Step 2: Commit**

```bash
git add .github/workflows/deploy-blog.yml
git commit -m "feat(hop): add container build job to blog CI pipeline"
```

### Task 12: Build Custom Caddy Image with Cloudflare Plugin ✅

**Files:**
- Create: `clusters/hop/apps/caddy/Dockerfile`
- Create: `.github/workflows/build-caddy.yml`

- [x] **Step 1: Create Caddy Dockerfile**

Create `clusters/hop/apps/caddy/Dockerfile`:

```dockerfile
FROM caddy:2.9-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2.9-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

- [x] **Step 2: Create CI workflow for Caddy image**

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

- [x] **Step 3: Update Caddy deployment to use custom image**

In `clusters/hop/apps/caddy/manifests/deployment.yaml`, change the image from `caddy:2.9-alpine` to `ghcr.io/derio-net/caddy-cloudflare:2.9`.

- [x] **Step 4: Commit**

```bash
git add clusters/hop/apps/caddy/Dockerfile .github/workflows/build-caddy.yml clusters/hop/apps/caddy/manifests/deployment.yaml
git commit -m "feat(hop): add custom Caddy image with Cloudflare DNS plugin"
```

---

## Chunk 6: Secrets, Verification, and Documentation

### Task 13: SOPS-Encrypted Secrets ⏭️ SKIPPED

> **⚠️ Deviation:** SOPS encryption was skipped entirely. All secrets (Caddy Cloudflare token, Tailscale auth key, Headplane API key) were applied as plain Kubernetes Secrets via `kubectl create secret` out-of-band. The `secrets/hop/` directory contains only a README. This is acceptable for a single-node edge cluster but should be revisited if the cluster grows.

**Files:**
- Create: `secrets/hop/` directory

- [x] **Step 1: Create secrets directory**

```bash
mkdir -p secrets/hop
```

- [x] **Step 2: Document all secrets that need out-of-band application**

```yaml
# manual-operation
id: edge-hop-secrets-bootstrap
layer: edge
app: hop-infrastructure
plan: docs/superpowers/plans/2026-03-16--edge--hop-public.md
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

- [x] **Step 3: Commit secrets directory**

```bash
echo "# SOPS-encrypted secrets for Hop cluster" > secrets/hop/README.md
git add secrets/hop/README.md
git commit -m "feat(hop): add secrets directory for Hop cluster"
```

### Task 14: Headscale DB Backup CronJob ✅

**Files:**
- Create: `clusters/hop/apps/headscale/manifests/backup-cronjob.yaml`

- [x] **Step 1: Create backup CronJob**

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

- [x] **Step 2: Commit**

```bash
git add clusters/hop/apps/headscale/manifests/backup-cronjob.yaml
git commit -m "feat(hop): add daily Headscale DB backup CronJob"
```

### Task 15: End-to-End Verification ✅

- [x] **Step 1: Verify all pods are running**

```bash
export KUBECONFIG=<HOP_KUBECONFIG>
kubectl get pods -A
```

Expected: All pods in `argocd`, `headscale-system`, `caddy-system`, `blog-system`, `landing-system` namespaces are `Running`.

- [x] **Step 2: Verify ArgoCD apps are synced**

```bash
kubectl -n argocd get applications
```

Expected: All apps show `Synced` and `Healthy`.

- [x] **Step 3: Verify public endpoints**

```bash
# Blog
curl -sI https://blog.derio.net/frank/ | head -5

# Headscale
curl -sI https://headscale.hop.derio.net/health | head -5

# www placeholder
curl -s https://www.derio.net
```

Expected: 200 OK responses.

- [x] **Step 4: Verify private endpoint enforcement**

```bash
# From a non-mesh IP, headplane should return 403
curl -sI https://headplane.hop.derio.net | head -5
```

Expected: 403 Forbidden.

- [x] **Step 5: Test Headscale client registration**

```yaml
# manual-operation
id: edge-hop-headscale-first-client
layer: edge
app: headscale
plan: docs/superpowers/plans/2026-03-16--edge--hop-public.md
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

### Task 16: Update Documentation ✅

**Files:**
- Modify: `CLAUDE.md`

- [x] **Step 1: Add Hop to Architecture section in CLAUDE.md**

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

- [x] **Step 2: Add Hop node to Nodes table**

```
| hop-1 | <HETZNER_IP> | control-plane+worker | Edge (Hetzner) | CX22, 2 vCPU, 4GB |
```

- [x] **Step 3: Add Hop services to Services table**

```
| Headscale | headscale.hop.derio.net | Caddy (public) |
| Headplane | headplane.hop.derio.net | Caddy (mesh only) |
| Blog | blog.derio.net/frank | Caddy (public) |
| Landing | entry.hop.derio.net | Caddy (mesh only) |
```

- [x] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Hop cluster to CLAUDE.md architecture and service tables"
```

---

## Deployment Deviations (2026-03-18)

Chunks 1-6 were executed autonomously on 2026-03-18. The autonomous run completed the file creation and commits, but several manual steps and runtime behaviors didn't match the plan. This triggered an extended interactive debugging session, primarily around Headplane (Deviation #6). The deviations below are cross-referenced from the inline annotations in each task above.

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

**Original:** Not addressed — `baseline` in plan.
**Actual:** `caddy-system` and `headscale-system` namespaces required `pod-security.kubernetes.io/enforce: privileged` label for hostPort and privileged containers. Changed from `baseline` → `privileged` in namespace templates.

### 6. Headplane v0.5.5 — Config, Base Path, and API Key

**Original:** Environment variables only, UI expected at root `/`.
**Actual:** Multiple issues discovered and fixed iteratively across several commits:

- Headplane 0.5.5 requires a `config.yaml` file (ConfigMap with `headscale.url`, `server.cookie_secret` exactly 32 chars).
- K8s integration (`integration.kubernetes`) must be removed entirely — it tries to exec into the Headscale pod to find the process PID and crashes when it can't.
- `config_path` must point to a mounted Headscale config file, AND `config_strict: false` is required (strict mode silently drops the HTTP listener with Headscale v0.25.1 due to unknown config fields).
- Headplane's React Router build uses `basename="/admin/"` — all routes live under `/admin/*`. Added Caddy redirect from `/` → `/admin/`.
- API key must be injected via `HEADPLANE_HEADSCALE_API_KEY` env var from a K8s Secret (created with `headscale apikeys create`).
- Headplane binds IPv4 only — `wget localhost:3000` fails (resolves to `::1`); use `wget 127.0.0.1:3000` to test.

**Lesson learned:** This was the most time-consuming deviation. The root cause was that Headplane's documentation doesn't cover the v0.5.5 config changes adequately, and `config_strict: true` (the default) caused a silent failure during initial debugging. However, `config_strict: false` was later corrected back to `true` (see Deviation #13) — the strict mode issue was transient and the Headscale config no longer triggers it.

### 7. Control Plane Scheduling

**Original:** Not addressed (single-node cluster assumed to work).
**Actual:** Talos applies `NoSchedule` taint to control-plane nodes by default. Required `kubectl taint nodes hop-1 node-role.kubernetes.io/control-plane:NoSchedule-` and permanent fix via `cluster.allowSchedulingOnControlPlanes: true` in Talos config patch.

### 8. Hetzner Firewall Ports

**Original:** TCP 80, TCP 443, UDP 3478 only.
**Actual:** Also opened TCP 6443 (K8s API) and TCP 50000 (talosctl API) — needed since Omni is not managing the cluster. Both APIs require mutual TLS (client certificates), so unauthenticated access is not possible. Ports are left open as a break-glass recovery path in case the Tailscale mesh goes down. Prefer mesh IP (`100.64.0.4`) for daily management.

### 9. Blog Path Handling

**Original:** Hugo builds with `baseURL: https://blog.derio.net/frank`, content at `/frank/` in container.
**Actual:** Hugo outputs to root `/` in the container regardless of baseURL. The Dockerfile's internal Caddyfile handles `/frank/*` routing, and the external Caddy reverse proxy strips the `/frank` path prefix before forwarding.

### 10. Env File Structure

**Original:** `.env` only.
**Actual:** Added `.env_hop` for Hop-specific vars (KUBECONFIG, CF_API_TOKEN). Critical: sourcing `.env` overrides KUBECONFIG to Frank — never source it when working on Hop.

### 11. Caddy Deployment Strategy (post-deploy fix, 2026-03-21)

**Original:** Default `RollingUpdate` strategy.
**Actual:** `RollingUpdate` deadlocks on a single-node cluster when using `hostPort` — the new pod can't bind ports 80/443 while the old pod still holds them. The new pod stays `Pending` forever. Changed to `strategy: Recreate`, which kills the old pod first. Brief downtime (~5s) is acceptable for a single-node edge cluster.
**Impact:** Updated `clusters/hop/apps/caddy/manifests/deployment.yaml`.

### 12. Caddy Cloudflare Secret Emptied (post-deploy fix, 2026-03-21)

**Original:** Cloudflare API token stored in `caddy-cloudflare` Secret, applied out-of-band.
**Actual:** After a `rollout restart`, the new Caddy pod crashed with `API token '' appears invalid`. The secret existed but contained an empty value. The old pod survived because env vars from `secretKeyRef` are injected at pod creation and never refreshed. The secret was recreated with the correct token.
**Lesson learned:** Running pods mask broken secrets. Verify secrets after any out-of-band changes — a `rollout restart` is the moment the truth surfaces.

### 13. Headplane config_strict Corrected (post-deploy fix, 2026-03-21)

**Original:** `config_strict: false` (set during Deviation #6 debugging).
**Actual:** During the original debugging session, strict mode was also working at some point — non-strict just happened to be active when the listener issue was resolved, so it stuck. Changed back to `config_strict: true`. The Headscale v0.25.1 config no longer contains unknown fields that would trip strict parsing. Eliminates the warning spam about forfeiting GitHub issue support.
**Impact:** Updated `clusters/hop/apps/headplane/manifests/configmap.yaml` and CLAUDE.md gotcha.

### 14. Caddy Redirect Robustness (post-deploy fix, 2026-03-21)

**Original:** `redir / /admin/ permanent` — only matches exact root path `/`.
**Actual:** Changed to `@not_admin not path /admin /admin/*` matcher + `redir @not_admin /admin/ permanent`. This catches any path that isn't already under `/admin*` and redirects to `/admin/`, preventing 404s from stale bookmarks or typos.
**Impact:** Updated `clusters/hop/apps/caddy/manifests/configmap.yaml`.

---

## Task Completion Summary

| Task | Status | Key Files | Notes |
| ------ | -------- | ----------- | ------- |
| 1. Packer Image Build | ✅ Done | `clusters/hop/packer/hetzner-talos.pkr.hcl`, `variables.pkr.hcl`, `.gitignore` | Executed as planned |
| 2. Provision Server | ✅ Done | `clusters/hop/talosconfig/` (gitignored), `.env_hop` (gitignored) | **Deviated:** talosctl instead of Omni, CX23 instead of CX22, extra firewall ports (6443, 50000), control-plane taint removed |
| 3. Root Chart | ✅ Done | `clusters/hop/apps/root/` — Chart.yaml, values.yaml, 12 templates (project, 4 namespaces, 7 Application CRs) | Executed as planned |
| 4. Bootstrap ArgoCD | ✅ Done | `clusters/hop/apps/argocd/values.yaml`, `root/templates/argocd.yaml` | Helm install + root app apply, minimal single-replica |
| 5. Static Storage | ✅ Done | `clusters/hop/apps/storage/manifests/` — storageclass.yaml, pv-headscale.yaml, pv-caddy.yaml | Hetzner Volume at `/var/mnt/hop-data/`, local StorageClass |
| 6. Headscale | ✅ Done | `clusters/hop/apps/headscale/manifests/` — deployment, service, configmap, pvc, backup-cronjob, **tailscale-client.yaml** | **Deviated:** +Tailscale DaemonSet (kernel mode, hostNetwork, privileged), +MagicDNS `extra_records` for split-DNS, namespace → `privileged` |
| 7. Headplane | ✅ Done | `clusters/hop/apps/headplane/manifests/` — deployment, service, **configmap.yaml**, **rbac.yaml** | **Deviated heavily:** env vars → config file, +API key Secret, removed K8s integration, `config_strict: false`, `/admin/` base path. Most debugging time spent here. |
| 8. Caddy | ✅ Done | `clusters/hop/apps/caddy/manifests/` — deployment, configmap (Caddyfile), pvc, Dockerfile | **Deviated:** namespace → `privileged`, +`/admin/` redirect for Headplane, blog path stripping. Cloudflare secret applied out-of-band. |
| 9. Blog | ✅ Done | `clusters/hop/apps/blog/manifests/` — deployment, service; `blog/Dockerfile` | **Deviated:** Hugo outputs to root `/`, internal Caddyfile handles routing, external Caddy strips `/frank` prefix |
| 10. Landing Page | ✅ Done | `clusters/hop/apps/landing/manifests/` — deployment, service, configmap (HTML) | Executed as planned |
| 11. Blog CI | ✅ Done | `.github/workflows/deploy-blog.yml` | Added `build-container` job alongside existing GitHub Pages deploy |
| 12. Custom Caddy Image | ✅ Done | `clusters/hop/apps/caddy/Dockerfile`, `.github/workflows/build-caddy.yml` | `ghcr.io/derio-net/caddy-cloudflare:2.9` with Cloudflare DNS plugin |
| 13. SOPS Secrets | ⏭️ Skipped | `secrets/hop/README.md` only | SOPS encryption skipped — all secrets applied as plain K8s Secrets via `kubectl create secret` out-of-band |
| 14. Backup CronJob | ✅ Done | `clusters/hop/apps/headscale/manifests/backup-cronjob.yaml` | Daily 3am UTC, SQLite `.backup`, 7-day retention, local hostPath |
| 15. E2E Verification | ✅ Done | — | All pods Running, all ArgoCD apps Synced/Healthy, public endpoints 200 OK, private endpoints 403 from non-mesh |
| 16. Update Documentation | ✅ Done | `CLAUDE.md` | Added Hop cluster to Architecture, Nodes, Services sections + Hop gotchas |
| 17. Scrub Public IP | ✅ Done | — | `git filter-repo --replace-text` replaced IP with `<HOP_PUBLIC_IP>` + force push |

> **Repo Restructure** was extracted to its own plan: `docs/superpowers/plans/2026-03-20--repo--multi-cluster-restructure.md`
