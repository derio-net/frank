# Frank, the Talos Cluster

AI-hybrid Kubernetes homelab managed via two-tier IaC: Omni (machine config) + ArgoCD (workloads).

## Standard Phase Workflow

Every phase follows this sequence:

1. **Brainstorm** — `/brainstorming` (Superpowers plugin) to explore requirements, refine scope, and design the approach via Socratic dialogue
2. **Deploy** — Implement the ArgoCD app (values, Application CR, manifests)
3. **Blog** — Write a Hugo blog post documenting the phase
4. **Review** — Verify deployment health and blog accuracy

## Commands

```bash
# Environment
source .env          # General (KUBECONFIG, TALOSCONFIG, OMNICONFIG)
source .env_devops   # DevOps (OMNI_ENDPOINT, service account key)

# Cluster operations
kubectl get nodes -o wide
talosctl health --nodes $CONTROL_PLANE_IP_1
omnictl get machines

# ArgoCD
argocd app list --port-forward --port-forward-namespace argocd
argocd app sync root --port-forward --port-forward-namespace argocd

# Blog
cd blog && hugo server --buildDrafts   # or use preview_start "hugo-dev"
hugo --minify                          # Production build
```

## Adding a New ArgoCD App

1. Create `apps/<app-name>/values.yaml` with Helm values
2. Create `apps/root/templates/<app-name>.yaml` with the Application CR
3. (Optional) Create `apps/<app-name>/manifests/` for raw manifests
4. Commit and push — ArgoCD auto-syncs via the root App-of-Apps

### Application Template Pattern

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <app-name>
  namespace: argocd
spec:
  project: infrastructure
  sources:
    - repoURL: <upstream-helm-repo>
      chart: <chart>
      targetRevision: "<version>"
      helm:
        releaseName: <release>
        valueFiles:
          - $values/apps/<app-name>/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: main
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: <namespace>
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
```

For raw manifests (no upstream chart), use `path: apps/<app-name>/manifests` instead of `chart`.

## Blog Post Pattern

Posts use Hugo page bundles with PaperMod theme:

```
blog/content/posts/NN-slug/
  index.md       # Post content
  cover.png      # Cover image
  *.png          # Inline images
```

Frontmatter:
```yaml
---
title: "Post Title"
date: 2026-MM-DD
draft: false
tags: ["tag1", "tag2"]
summary: "One-sentence summary for cards"
weight: <NN>    # Sort order matches post number
cover:
  image: cover.png
  alt: "Descriptive alt text"
  relative: true
---
```

## Architecture

```
apps/                  # ArgoCD App-of-Apps (Helm chart + per-app values)
  root/                # Entry point — templates all Application CRs
  <app>/values.yaml    # Per-app Helm values
  <app>/manifests/     # Raw K8s manifests (when no upstream chart)
patches/               # Talos machine config patches (per phase)
  phase01-node-config/ # Node labels, scheduling
  phase02-cilium/      # CNI, eBPF kube-proxy
  phase03-longhorn/    # Distributed storage
  phase04-gpu/         # NVIDIA GPU operator
  phase05-mini-config/ # Intel iGPU DRA
blog/                  # Hugo static site (PaperMod theme)
omni/                  # Sidero Omni self-hosted config
docs/plans/            # Design and implementation plans
scripts/               # Utility scripts
```

## Nodes

| Host | IP | Role | Zone | Key Hardware |
|------|-----|------|------|-------------|
| mini-1 | 192.168.55.21 | control-plane | Core HA | Intel Ultra 5, 64GB, iGPU |
| mini-2 | 192.168.55.22 | control-plane | Core HA | Intel Ultra 5, 64GB, iGPU |
| mini-3 | 192.168.55.23 | control-plane | Core HA | Intel Ultra 5, 64GB, iGPU |
| gpu-1 | 192.168.55.31 | worker | AI Compute | i9, 128GB, RTX 5070 |
| pc-1 | 192.168.55.71 | worker | Edge | 64GB, general purpose |
| raspi-1 | 192.168.55.41 | worker | Edge | RPi 4, low-power |
| raspi-2 | 192.168.55.42 | worker | Edge | RPi 4, low-power |

## Services

| Service | IP | Exposed Via |
|---------|-----|-------------|
| ArgoCD | 192.168.55.200 | Cilium L2 LoadBalancer |
| Longhorn UI | 192.168.55.201 | Cilium L2 LoadBalancer |
| Hubble UI | 192.168.55.202 | Cilium L2 LoadBalancer |

## Gotchas

- Always use `ServerSideApply=true` in ArgoCD sync options (avoids annotation size limits)
- Ignore Secret data diffs in ArgoCD (`ignoreDifferences` on `/data` jsonPointer)
- `prune: false` in syncPolicy — manual pruning only to avoid accidental deletion
- Blog images must be co-located in the page bundle directory (not in `/static/images/`)
- Intel GPU Resource Driver uses vendored chart with K8s 1.35 DRA patches
- GPU-1 has a NoSchedule taint — only GPU workloads schedule there
- SOPS/age encryption for secrets — never commit plaintext secrets
- Longhorn default replicaCount: 3 (matches 3 control-plane nodes)
