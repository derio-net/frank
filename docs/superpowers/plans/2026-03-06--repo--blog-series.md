# Blog Series Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up a Hugo blog at `blog/` with PaperMod theme, 7 post stubs, a roadmap shortcode, GitHub Actions deployment, and Netlify fallback config.

**Architecture:** Hugo static site in `blog/` subdirectory, PaperMod theme as git submodule, page bundles for posts, GitHub Actions CI/CD targeting GitHub Pages with path filter on `blog/**`.

**Tech Stack:** Hugo v0.157.0, PaperMod theme, GitHub Actions, GitHub Pages

---

### Task 1: Scaffold Hugo Site

**Files:**
- Create: `blog/hugo.toml`
- Create: `blog/content/_index.md`
- Create: `blog/.gitkeep` (for `static/images/`)

**Step 1: Create the Hugo site skeleton**

Run from repo root:

```bash
hugo new site blog --format toml
```

This creates the full Hugo directory structure at `blog/`.

**Step 2: Remove default scaffolding we don't need**

```bash
rm -f blog/hugo.toml
rm -rf blog/content blog/archetypes
mkdir -p blog/content/posts
mkdir -p blog/static/images
```

**Step 3: Write `hugo.toml`**

Create `blog/hugo.toml` with this content:

```toml
baseURL = "https://derio-net.github.io/frank/"
languageCode = "en-us"
title = "Building frankocluster"
theme = "PaperMod"

[params]
  env = "production"
  description = "Building an AI-hybrid Kubernetes homelab with Talos Linux"
  author = "Ioannis Dermitzakis"
  defaultTheme = "auto"
  ShowReadingTime = true
  ShowShareButtons = false
  ShowPostNavLinks = true
  ShowBreadCrumbs = true
  ShowCodeCopyButtons = true
  ShowToc = true
  TocOpen = false

  [params.homeInfoParams]
    Title = "frankocluster"
    Content = "A tutorial series on building an AI-hybrid Kubernetes homelab from scratch with Talos Linux, Cilium, Longhorn, ArgoCD, and GPU compute."

  [[params.socialIcons]]
    name = "github"
    url = "https://github.com/derio-net/frank"

[menu]
  [[menu.main]]
    identifier = "posts"
    name = "Posts"
    url = "/posts/"
    weight = 10
  [[menu.main]]
    identifier = "tags"
    name = "Tags"
    url = "/tags/"
    weight = 20

[outputs]
  home = ["HTML", "RSS", "JSON"]

[markup]
  [markup.highlight]
    codeFences = true
    lineNos = false
    style = "monokai"
  [markup.goldmark.renderer]
    unsafe = true
```

**Step 4: Verify Hugo builds**

```bash
cd blog && hugo --minify 2>&1 | head -20
```

Expected: Build succeeds (warnings about missing theme are OK at this point).

**Step 5: Commit**

```bash
git add blog/
git commit -m "feat(blog): scaffold Hugo site with PaperMod config"
```

---

### Task 2: Add PaperMod Theme as Git Submodule

**Files:**
- Create: `blog/themes/PaperMod/` (submodule)

**Step 1: Add the submodule**

```bash
git submodule add --depth=1 https://github.com/adityatelange/hugo-PaperMod.git blog/themes/PaperMod
```

**Step 2: Verify Hugo builds with theme**

```bash
cd blog && hugo --minify
```

Expected: Build succeeds, output in `blog/public/`.

**Step 3: Commit**

```bash
git add .gitmodules blog/themes/PaperMod
git commit -m "feat(blog): add PaperMod theme as git submodule"
```

---

### Task 3: Create Roadmap Shortcode

**Files:**
- Create: `blog/layouts/shortcodes/roadmap.html`

**Step 1: Create the shortcode**

Create `blog/layouts/shortcodes/roadmap.html`:

```html
{{- $url := .Get 0 -}}
{{- $height := .Get 1 | default "600px" -}}
<div style="width: 100%; overflow: hidden;">
  <iframe
    src="{{ $url }}"
    width="100%"
    height="{{ $height }}"
    style="border: none;"
    loading="lazy"
    title="frankocluster roadmap">
  </iframe>
</div>
```

Usage in posts: `{{</* roadmap "https://roadmap.sh/r/your-roadmap-id" "800px" */>}}`

**Step 2: Commit**

```bash
git add blog/layouts/shortcodes/roadmap.html
git commit -m "feat(blog): add roadmap.sh iframe shortcode"
```

---

### Task 4: Create Post 0 — Overview & Roadmap

**Files:**
- Create: `blog/content/posts/00-overview/index.md`

**Step 1: Write the post**

Create `blog/content/posts/00-overview/index.md`:

```markdown
---
title: "frankocluster: Overview & Roadmap"
date: 2026-03-06
draft: false
tags: ["overview", "roadmap"]
summary: "A living overview of the frankocluster — an AI-hybrid Kubernetes homelab. Technology roadmap, capabilities, and series index."
weight: 1
---

This is the overview post for the **frankocluster** series — a tutorial-style walkthrough of building an AI-hybrid Kubernetes homelab from scratch.

This post is a **living document**: it gets updated as new technologies and capabilities are added to the cluster.

## Roadmap

<!-- Replace with your roadmap.sh URL once created -->
<!-- {{</* roadmap "https://roadmap.sh/r/your-roadmap-id" "700px" */>}} -->

*Roadmap embed coming soon — to be created on [roadmap.sh](https://roadmap.sh).*

## Technology → Capability Map

| Technology | Capabilities Unlocked |
|------------|----------------------|
| **Talos Linux + Omni** | Immutable OS, declarative machine config, secure bootstrap |
| **Cilium (eBPF)** | Kube-proxy replacement, L2 LoadBalancer, Hubble observability |
| **Longhorn** | Distributed block storage, GPU-local StorageClass, 3-replica HA |
| **ArgoCD** | GitOps, App-of-Apps, self-healing, drift detection |
| **NVIDIA GPU Operator** | GPU scheduling, AI/ML workloads, container toolkit |
| **Intel GPU DRA Driver** | iGPU sharing via DRA, namespace-scoped GPU access |
| **OpenRGB** | LED control from K8s (just for fun) |

## Cluster State

| Node | Zone | Role | Hardware |
|------|------|------|----------|
| mini-1/2/3 | Core (B) | Control-plane + Worker | Intel Ultra 5, 64GB RAM, 1TB NVMe, Arc iGPU |
| gpu-1 | AI Compute (C) | Worker | i9, 128GB RAM, RTX 5070, 2x4TB SSD |
| pc-1 | Edge (D) | Worker | Legacy desktop, 64GB SSD + 3x HDD |
| raspi-1/2 | Edge (D) | Worker | Raspberry Pi 4, 32GB SD |

## Series Index

1. [Introduction — Why Build a Kubernetes Homelab?](/posts/01-introduction/)
2. [Building the Foundation — Talos, Nodes, and Cilium](/posts/02-foundation/)
3. [Persistent Storage with Longhorn](/posts/03-storage/)
4. [GPU Compute — NVIDIA and Intel](/posts/04-gpu-compute/)
5. [GitOps Everything with ArgoCD](/posts/05-gitops/)
6. [Fun Stuff — Controlling Case LEDs from Kubernetes](/posts/06-fun-stuff/)
```

**Step 2: Verify it renders**

```bash
cd blog && hugo server -D &
# Open http://localhost:1313/frank/posts/00-overview/ in browser
# Kill server after verification
kill %1
```

**Step 3: Commit**

```bash
git add blog/content/posts/00-overview/
git commit -m "feat(blog): add Post 0 — overview and roadmap"
```

---

### Task 5: Create Post 1 — Introduction

**Files:**
- Create: `blog/content/posts/01-introduction/index.md`

**Step 1: Write the post**

Create `blog/content/posts/01-introduction/index.md`:

```markdown
---
title: "Why Build a Kubernetes Homelab?"
date: 2026-03-06
draft: false
tags: ["introduction", "architecture"]
summary: "The motivation behind frankocluster — learning enterprise infrastructure and building interesting projects on your own hardware."
weight: 2
---

## Why?

Two reasons drove me to build this cluster.

### Reason 1: Learning by Doing

Cloud-managed Kubernetes (EKS, GKE) abstracts away the parts I wanted to understand: CNI networking, storage orchestration, GPU scheduling, immutable OS operation, and GitOps at the infrastructure layer. You can read about eBPF kube-proxy replacement or DRA-based GPU sharing all day — or you can break it, fix it, and actually learn it.

The goal was never "run a production cluster at home." It was to build one that *could* be production, so the skills transfer directly.

### Reason 2: Self-hosted Infrastructure

As a solo builder, I want self-hosted infrastructure for:

- **AI/ML workloads** — local inference with GPUs, fine-tuning, experiments
- **Self-hosted services** — things I'd otherwise pay SaaS for
- **Product prototyping** — test deployments before going to cloud

The hardware was already sitting around. The cluster turns idle machines into a platform.

## The Hardware

The cluster spans 4 zones of heterogeneous hardware:

### Zone A: Management

- **raspi-omni** (Raspberry Pi 5, 8GB) — Runs Sidero Omni, Authentik SSO, Traefik. The management plane lives outside the cluster.

### Zone B: Core HA

- **mini-1, mini-2, mini-3** (ASUS NUC, Intel Ultra 5 225H, 64GB RAM, 1TB NVMe) — Three identical nodes forming the HA control plane. Each has an Intel Arc iGPU for future media/AI workloads.

### Zone C: AI Compute

- **gpu-1** (Custom desktop, i9, 128GB RAM, RTX 5070, 2x4TB SSD) — The heavy lifter. Dedicated GPU storage via Longhorn. Tainted for GPU-only workloads.

### Zone D: Edge

- **pc-1** (Legacy desktop, 64GB SSD + 3x HDD) — General purpose worker.
- **raspi-1, raspi-2** (Raspberry Pi 4, 32GB SD) — Low-power edge nodes.

## Architecture

The cluster uses a **two-layer management model**:

- **Layer 1 (Machine Config):** Sidero Omni manages Talos Linux machine configurations — OS extensions, kernel modules, disk mounts, network settings. Applied via `omnictl`.
- **Layer 2 (Workloads):** ArgoCD manages everything running *on* Kubernetes — CNI, storage, GPU drivers, applications. GitOps via the same repo you're reading.

This separation means Omni never touches workloads, and ArgoCD never touches machine config. Clean boundaries, no conflicts.

## What's Next

The rest of this series walks through each capability layer:

{{< cluster-roadmap >}}

Let's start building.
```

**Step 2: Commit**

```bash
git add blog/content/posts/01-introduction/
git commit -m "feat(blog): add Post 1 — introduction and motivation"
```

---

### Task 6: Create Post 2 — Building the Foundation

**Files:**
- Create: `blog/content/posts/02-foundation/index.md`

**Step 1: Write the post**

Create `blog/content/posts/02-foundation/index.md`:

```markdown
---
title: "Building the Foundation — Talos, Nodes, and Cilium"
date: 2026-03-06
draft: true
tags: ["talos", "cilium", "networking", "bootstrap"]
summary: "Bootstrapping a Talos Linux cluster with Omni, configuring node labels and zones, and replacing Flannel with Cilium's eBPF networking."
weight: 3
---

This post covers the first three steps of building frankocluster: bootstrapping Talos Linux via Omni, organizing nodes into labeled zones, and installing Cilium as the CNI with eBPF kube-proxy replacement.

## Why Talos Linux?

*Content to be written — covers: immutable OS, API-driven config, no SSH, security posture, comparison with Ubuntu/k3s/Flatcar.*

## Bootstrapping with Omni

*Content to be written — covers: Omni setup on raspi-omni, machine enrollment, initial cluster creation, machine configs.*

## Layer 1: Node Configuration

*Content to be written — covers: node labels (zone, tier, accelerator), scheduling strategy (control-plane workers), removing NoSchedule taints.*

### Key Config: Cluster-Wide Scheduling

<!-- Reference: patches/phase01-node-config/01-cluster-wide-scheduling.yaml -->

*Content to be written — explain the patch and why control planes also run workloads in a homelab.*

### Key Config: Node Labels

<!-- Reference: patches/phase01-node-config/03-labels-*.yaml -->

*Content to be written — explain the labeling scheme and zone architecture.*

## Layer 2: Cilium CNI

*Content to be written — covers: why Cilium over Flannel/Calico, eBPF kube-proxy replacement, L2 announcements, Hubble.*

### Removing Flannel

<!-- Reference: patches/phase02-cilium/02-cluster-wide-cni-none.yaml -->

*Content to be written — the careful dance of removing default CNI.*

### Installing Cilium

<!-- Reference: apps/cilium/values.yaml -->

*Content to be written — Helm values walkthrough, L2 LoadBalancer IP pool, Hubble setup.*

### Gotchas

*Content to be written — things that went wrong and how they were fixed.*

## What We Have Now

At this point the cluster has:
- 7 nodes running Talos Linux, managed by Omni
- Labeled zones (Core, AI Compute, Edge) for workload placement
- Cilium CNI with eBPF kube-proxy replacement
- L2 LoadBalancer (192.168.55.200-254) for service exposure
- Hubble for network observability

**Next: [Persistent Storage with Longhorn](/posts/03-storage/)**
```

**Step 2: Commit**

```bash
git add blog/content/posts/02-foundation/
git commit -m "feat(blog): add Post 2 stub — foundation (bootstrap, nodes, Cilium)"
```

---

### Task 7: Create Post 3 — Storage

**Files:**
- Create: `blog/content/posts/03-storage/index.md`

**Step 1: Write the post**

Create `blog/content/posts/03-storage/index.md`:

```markdown
---
title: "Persistent Storage with Longhorn"
date: 2026-03-06
draft: true
tags: ["longhorn", "storage"]
summary: "Setting up Longhorn distributed block storage across heterogeneous disks, including a GPU-local StorageClass for AI workloads."
weight: 4
---

This post covers installing Longhorn for distributed block storage — including handling Talos's immutable OS, heterogeneous disk sizes, and creating a dedicated GPU-local StorageClass.

## Why Longhorn?

*Content to be written — covers: Longhorn vs Rook-Ceph for homelab, simplicity, Rancher ecosystem, replica management.*

## Prerequisites: iscsi-tools on Talos

<!-- Reference: patches/phase03-longhorn/400-cluster-iscsi-tools.yaml -->

*Content to be written — Talos needs iscsi-tools extension for Longhorn. How to add it cluster-wide.*

## Mounting Extra Disks on gpu-1

<!-- Reference: patches/phase03-longhorn/401-gpu1-extra-disks.yaml -->

*Content to be written — gpu-1 has 2x4TB SSDs for dedicated GPU storage. Talos disk mount config.*

## Installing Longhorn

<!-- Reference: apps/longhorn/values.yaml -->

*Content to be written — Helm values walkthrough, replica settings, data locality.*

## GPU-Local StorageClass

<!-- Reference: apps/longhorn/manifests/gpu-local-sc.yaml -->

*Content to be written — strict-local data locality for performance, single replica, disk tag selection.*

## What We Have Now

At this point the cluster has:
- Distributed 3-replica block storage across all 7 nodes
- GPU-local StorageClass for high-performance single-node workloads on gpu-1
- Automatic volume rebalancing and health monitoring

**Next: [GPU Compute — NVIDIA and Intel](/posts/04-gpu-compute/)**
```

**Step 2: Commit**

```bash
git add blog/content/posts/03-storage/
git commit -m "feat(blog): add Post 3 stub — Longhorn storage"
```

---

### Task 8: Create Post 4 — GPU Compute

**Files:**
- Create: `blog/content/posts/04-gpu-compute/index.md`

**Step 1: Write the post**

Create `blog/content/posts/04-gpu-compute/index.md`:

```markdown
---
title: "GPU Compute — NVIDIA and Intel"
date: 2026-03-06
draft: true
tags: ["gpu", "nvidia", "intel", "dra"]
summary: "Adding GPU compute to the cluster — the NVIDIA RTX 5070 saga, Intel Arc iGPU via DRA, and patching charts for bleeding-edge Kubernetes."
weight: 5
---

This post covers two GPU stories: the NVIDIA RTX 5070 (and its hardware troubles), and the Intel Arc iGPU on the mini nodes using Kubernetes 1.35's Dynamic Resource Allocation.

## Part 1: NVIDIA GPU Operator (Layer 4)

### Talos Extensions for NVIDIA

<!-- Reference: patches/phase04-gpu/402-gpu1-nvidia-extensions.yaml -->
<!-- Reference: patches/phase04-gpu/04-gpu-nvidia-modules.yaml -->

*Content to be written — nvidia-toolkit, nvidia-gpu-kernel-modules, kernel module loading on Talos.*

### GPU Operator Helm Values

<!-- Reference: apps/gpu-operator/values.yaml -->

*Content to be written — driver disabled (Talos provides), toolkit disabled, containerd runtime config.*

### The Hardware Saga

*Content to be written — RTX 5070 not detected on PCIe bus, BIOS investigation, manual sync strategy, current status.*

## Part 2: Intel Arc iGPU via DRA (Layer 5)

### Why DRA Over Device Plugins?

*Content to be written — K8s 1.35 DRA (ResourceSlice/ResourceClaim), namespace-scoped sharing, future of GPU in K8s.*

### i915 Extensions on Talos

<!-- Reference: patches/phase05-mini-config/500-mini1-i915-extensions.yaml (and 501, 502) -->

*Content to be written — rolling extension install preserving CP quorum, i915 + intel-ucode.*

### CDI Containerd Configuration

<!-- Reference: patches/phase05-mini-config/05-mini-cdi-containerd.yaml -->

*Content to be written — Talos read-only rootfs, /var/cdi instead of /etc/cdi, cluster-wide containerd patch.*

### Chart Vendoring for K8s 1.35

<!-- Reference: apps/intel-gpu-driver/chart/ -->

*Content to be written — upstream chart uses v1beta1 APIs removed in K8s 1.35. Vendored chart with patches: DeviceClass v1, ValidatingAdmissionPolicy v1, PSA labels, CDI path fix, image update to v0.9.1.*

### Verifying It Works

*Content to be written — ResourceSlice per node, smoke test pod with ResourceClaim, card0 + renderD128 visible.*

## What We Have Now

At this point the cluster has:
- Intel Arc iGPU exposed on mini-1/2/3 via DRA (ResourceSlice/ResourceClaim)
- NVIDIA GPU Operator ready (manual sync, awaiting RTX 5070 hardware fix)
- GPU-local Longhorn storage on gpu-1 for AI workloads

**Next: [GitOps Everything with ArgoCD](/posts/05-gitops/)**
```

**Step 2: Commit**

```bash
git add blog/content/posts/04-gpu-compute/
git commit -m "feat(blog): add Post 4 stub — GPU compute (NVIDIA + Intel DRA)"
```

---

### Task 9: Create Post 5 — GitOps

**Files:**
- Create: `blog/content/posts/05-gitops/index.md`

**Step 1: Write the post**

Create `blog/content/posts/05-gitops/index.md`:

```markdown
---
title: "GitOps Everything with ArgoCD"
date: 2026-03-06
draft: true
tags: ["argocd", "gitops"]
summary: "Migrating from Flux to ArgoCD with an App-of-Apps pattern — adopting existing workloads without downtime."
weight: 6
---

This post covers the migration from Flux CD to ArgoCD, the Pulumi detour that didn't work out, and building an App-of-Apps Helm chart to manage all cluster workloads via GitOps.

## The Pulumi Detour

*Content to be written — tried Pulumi first, no Sidero Omni provider, conflicts with Omni's machine management. Abandoned.*

## Why ArgoCD Over Flux?

*Content to be written — Flux was already deployed but broken. ArgoCD: better UI, App-of-Apps pattern, multi-source applications, cleaner adoption of existing workloads.*

## Removing Flux CD

*Content to be written — cleaning up Flux CRDs, controllers, and source artifacts without disrupting running workloads.*

## App-of-Apps Pattern

<!-- Reference: apps/root/ -->

*Content to be written — root Helm chart renders child Application CRs. Single apply bootstraps everything.*

### Root Chart Structure

<!-- Reference: apps/root/Chart.yaml, values.yaml, templates/ -->

*Content to be written — Chart.yaml, values with repo URL/revision, namespace templates with PSA labels.*

### Multi-Source Applications

<!-- Reference: apps/root/templates/cilium.yaml (example) -->

*Content to be written — each Application has two sources: upstream Helm chart + local values from apps/{name}/values.yaml.*

## Adopting Existing Workloads

*Content to be written — Cilium and Longhorn were already running. ArgoCD adoption without downtime: annotation-based resource tracking, replace=true for CRDs.*

## Self-Managing ArgoCD

<!-- Reference: apps/argocd/values.yaml -->

*Content to be written — ArgoCD managing its own Helm values. Bootstrap once, then it watches itself.*

## What We Have Now

At this point the cluster has:
- Full GitOps via ArgoCD App-of-Apps
- All workloads (Cilium, Longhorn, GPU drivers, OpenRGB) managed declaratively
- Self-healing: ArgoCD detects and corrects drift automatically
- Single repo as source of truth for both machine config and workloads

**Next: [Fun Stuff — Controlling Case LEDs from Kubernetes](/posts/06-fun-stuff/)**
```

**Step 2: Commit**

```bash
git add blog/content/posts/05-gitops/
git commit -m "feat(blog): add Post 5 stub — ArgoCD GitOps migration"
```

---

### Task 10: Create Post 6 — Fun Stuff

**Files:**
- Create: `blog/content/posts/06-fun-stuff/index.md`

**Step 1: Write the post**

Create `blog/content/posts/06-fun-stuff/index.md`:

```markdown
---
title: "Fun Stuff — Controlling Case LEDs from Kubernetes"
date: 2026-03-06
draft: true
tags: ["openrgb", "hardware"]
summary: "The most over-engineered RGB setup — controlling ARGB case fans from a Kubernetes DaemonSet via USB HID."
weight: 7
---

Every serious infrastructure project needs a completely unnecessary feature. This is ours: controlling the ARGB LED fans on gpu-1 from a Kubernetes DaemonSet.

## The Hardware

*Content to be written — FOIFKIN F1 case, 6 PWM ARGB fans, internal hub, Gigabyte Z790 Eagle AX motherboard, ITE IT5701 USB RGB controller.*

## USB HID vs I2C

*Content to be written — originally tried I2C path, Talos kernel lacks CONFIG_I2C_CHARDEV, pivoted to USB HID (simpler, safer, already available via /dev/hidraw0).*

## The OpenRGB DaemonSet

<!-- Reference: apps/openrgb/manifests/daemonset.yaml -->

*Content to be written — privileged pod, /dev mount for USB HID access, nodeSelector for gpu-1 only, one-shot LED config on startup.*

## ConfigMap-Driven LED Config

<!-- Reference: apps/openrgb/manifests/configmap.yaml -->

*Content to be written — change OPENRGB_ARGS in the ConfigMap, push to git, ArgoCD syncs, LEDs change. GitOps for RGB.*

## Was It Worth It?

Absolutely not. But the fans look great.
```

**Step 2: Commit**

```bash
git add blog/content/posts/06-fun-stuff/
git commit -m "feat(blog): add Post 6 stub — OpenRGB LED control"
```

---

### Task 11: GitHub Actions Deployment Workflow

**Files:**
- Create: `.github/workflows/deploy-blog.yml`

**Step 1: Write the workflow**

Create `.github/workflows/deploy-blog.yml`:

```yaml
name: Deploy Blog

on:
  push:
    branches: [main]
    paths:
      - "blog/**"
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          submodules: recursive

      - name: Setup Hugo
        uses: peaceiris/actions-hugo@v3
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

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

**Step 2: Commit**

```bash
git add .github/workflows/deploy-blog.yml
git commit -m "ci(blog): add GitHub Actions workflow for Hugo deployment"
```

---

### Task 12: Netlify Fallback Config

**Files:**
- Create: `blog/netlify.toml`

**Step 1: Write the Netlify config**

Create `blog/netlify.toml`:

```toml
[build]
  command = "hugo --minify"
  publish = "public"

[build.environment]
  HUGO_VERSION = "0.157.0"

[context.production.environment]
  HUGO_ENV = "production"
```

**Step 2: Commit**

```bash
git add blog/netlify.toml
git commit -m "ci(blog): add Netlify fallback config"
```

---

### Task 13: Verify Full Build and Local Preview

**Step 1: Build the site**

```bash
cd blog && hugo --minify
```

Expected: Build succeeds, output in `blog/public/`, 7 posts generated (1 non-draft + 6 drafts if using `-D`).

**Step 2: Local preview**

```bash
cd blog && hugo server -D
```

Expected: Site at http://localhost:1313/frank/ — verify:
- Homepage with site description
- All 7 posts listed
- Post 0 (Overview) renders with table and series index
- Post 1 (Introduction) renders with full content
- Posts 2-6 render as draft stubs with placeholder sections
- Code blocks highlight correctly
- Dark mode toggle works

**Step 3: Final commit if any fixes needed**

```bash
git add -A blog/
git commit -m "fix(blog): post-build adjustments"
```

---

### Task 14: Update .gitignore

**Files:**
- Modify: `.gitignore`

**Step 1: Add Hugo build output to .gitignore**

Append to `.gitignore`:

```
# Hugo
blog/public/
blog/resources/_gen/
blog/.hugo_build.lock
```

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add Hugo build artifacts to .gitignore"
```

Note: Task 14 should be done early (before Task 1's commit) to avoid committing build artifacts. The executor should reorder this to run first.
