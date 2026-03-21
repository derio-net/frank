# Blog Series Design: Building an AI-Hybrid Kubernetes Homelab

**Date:** 2026-03-06
**Status:** Approved

## Overview

A series of tutorial-style blog posts documenting the construction of the frankocluster — an enterprise-grade, AI-hybrid Kubernetes homelab running Talos Linux across heterogeneous hardware. Posts are capability-centric, grouping related layers into cohesive narratives.

## Goals

1. Document the cluster build as a learning resource for intermediate K8s practitioners
2. Serve as a living portfolio for infrastructure work
3. Keep blog source in the same repo as the infrastructure code
4. Deploy independently via GitHub Pages (or Netlify)

## Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Static site generator | Hugo | Fast, single binary, excellent Markdown/code support |
| Theme | PaperMod | Clean, fast, dark mode, search, widely used for tech blogs |
| Theme install | Git submodule | Tracks upstream updates, no vendoring |
| Roadmap visualization | roadmap.sh (iframe embed) | Interactive, maintained separately, auto-updates |
| Deployment | GitHub Pages via Actions | Free, simple, triggered on blog/ changes |
| Fallback deployment | Netlify (via netlify.toml) | Zero-code switch if needed |

## Directory Structure

```
blog/
├── hugo.toml
├── content/
│   └── posts/
│       ├── 00-overview/
│       │   └── index.md
│       ├── 01-introduction/
│       │   └── index.md
│       ├── 02-foundation/
│       │   └── index.md
│       ├── 03-storage/
│       │   └── index.md
│       ├── 04-gpu-compute/
│       │   └── index.md
│       ├── 05-gitops/
│       │   └── index.md
│       └── 06-fun-stuff/
│           └── index.md
├── layouts/
│   └── shortcodes/
│       └── roadmap.html
├── static/
│   └── images/
├── themes/
│   └── PaperMod/               (git submodule)
└── netlify.toml
```

Each post uses Hugo page bundles (directory with `index.md`) for co-located images and assets.

## Post Plan

### Post 0: Overview & Roadmap (living document)

- Embedded roadmap.sh interactive roadmap
- Technology → Capability mapping table
- Current cluster state summary (nodes, versions)
- Links to each post in the series
- Updated continuously as new technologies are added
- Tags: `overview`, `roadmap`

### Post 1: Introduction — Why Build a Kubernetes Homelab?

- Motivation 1: Learning enterprise-grade infra (Talos, GitOps, GPU scheduling, DRA)
- Motivation 2: Self-hosted infrastructure — self-hosted AI/ML, services, products
- Hardware inventory with photos/specs (zones A-D)
- High-level architecture diagram (4 zones, 2 management layers)
- What makes this cluster different (heterogeneous hardware, AI-hybrid, Talos)
- Tags: `introduction`, `architecture`

### Post 2: Building the Foundation (Bootstrap + Layer 1 + Layer 2)

- Talos Linux — why not Ubuntu/k3s, what Omni brings
- Bootstrapping the cluster via Omni (initial node enrollment, machine configs)
- Node configuration — labels, zones, scheduling strategy (Layer 1)
- Cilium CNI — migrating from Flannel, eBPF kube-proxy replacement, L2 LoadBalancer (Layer 2)
- Gotchas: removing Flannel safely, kube-proxy replacement prerequisites
- Tags: `talos`, `cilium`, `networking`, `bootstrap`

### Post 3: Persistent Storage with Longhorn (Layer 3)

- Why Longhorn over Rook-Ceph for a homelab
- Distributed 3-replica storage across heterogeneous disks
- GPU-local StorageClass for high-performance AI workloads
- iscsi-tools extension on Talos
- Mounting extra disks on gpu-1 (2x4TB SSDs)
- Tags: `longhorn`, `storage`

### Post 4: GPU Compute — NVIDIA and Intel (Layer 4 + Layer 5)

- The NVIDIA story: RTX 5070, GPU Operator, Talos extensions, hardware saga
- Intel iGPU: i915 on mini nodes, DRA vs device plugins
- K8s 1.35 DRA (ResourceSlice/ResourceClaim) — the new way to share GPUs
- Chart vendoring and API version patching for bleeding-edge K8s
- CDI containerd configuration on Talos (read-only rootfs gotcha)
- Tags: `gpu`, `nvidia`, `intel`, `dra`

### Post 5: GitOps Everything with ArgoCD (ArgoCD migration)

- Why ArgoCD over Flux (and the Pulumi detour)
- App-of-Apps pattern with Helm
- Multi-source Applications (upstream chart + local values)
- Adopting existing workloads without downtime
- Self-managing ArgoCD
- Tags: `argocd`, `gitops`

### Post 6: Fun Stuff — Controlling Case LEDs from Kubernetes (OpenRGB)

- The FOIFKIN F1 case and its ARGB fans
- USB HID vs I2C (and why Talos made the choice for us)
- Privileged DaemonSet with ConfigMap-driven LED config
- "The most over-engineered RGB setup" narrative
- Tags: `openrgb`, `hardware`

## Roadmap.sh Integration

The roadmap is a vertical flow on roadmap.sh. Each node is a Technology with child nodes showing unlocked Capabilities:

```
Talos Linux + Omni
  → Immutable OS, declarative machine config, secure bootstrap
    ↓
Cilium (eBPF)
  → Kube-proxy replacement, L2 LoadBalancer, Hubble observability
    ↓
Longhorn
  → Distributed block storage, GPU-local StorageClass, 3-replica HA
    ↓
ArgoCD
  → GitOps, App-of-Apps, self-healing, drift detection
    ↓
NVIDIA GPU Operator
  → GPU scheduling, AI/ML workloads, container toolkit
    ↓
Intel GPU DRA Driver
  → iGPU sharing via DRA, namespace-scoped GPU access
    ↓
OpenRGB
  → LED control from K8s
    ↓
[Future: KubeRay, JupyterHub, Ollama, ...]
  → AI inference, notebooks, LLM serving
```

Embedded via a Hugo shortcode (`{{< roadmap "https://roadmap.sh/r/..." >}}`) that renders a responsive iframe. Updated on roadmap.sh; the overview post picks up changes automatically.

## CI/CD

### GitHub Actions (primary)

- **Trigger:** Push to `main` when `blog/**` files change
- **Steps:** Checkout → Setup Hugo → Build (`hugo --minify`) → Deploy to `gh-pages` branch
- **Action:** `peaceiris/actions-hugo` for Hugo setup, `peaceiris/actions-gh-pages` for deploy
- **Site URL:** `https://derio-net.github.io/frank/` (configurable)

### Netlify (fallback)

- `netlify.toml` in `blog/` with build command and publish directory
- Connect repo on Netlify, set base directory to `blog/` — works without code changes

### Local Development

```bash
cd blog && hugo server -D
```

## Tone & Audience

- **Audience:** Intermediate Kubernetes practitioners who want to build something similar
- **Tone:** Tutorial/guide — step-by-step walkthroughs, explains each decision
- **Style:** "Here is what I did, why, and what went wrong along the way"
- **Code:** Config snippets inline, with references to repo files for full context

## Future Extensibility

- New cluster layers become new posts (or updates to existing posts)
- Post 0 (Overview) is updated with each new technology
- Roadmap.sh diagram is updated independently
- Series ordering uses numeric prefixes (`00-`, `01-`, ...) for natural sort
