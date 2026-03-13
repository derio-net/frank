# Frank, the Talos Cluster

AI-hybrid Kubernetes homelab managed via two-tier IaC: Omni (machine config) + ArgoCD (workloads).

## Standard Phase Workflow

Every phase follows this sequence:

1. **Brainstorm** — `/brainstorming` (Superpowers plugin) to explore requirements, refine scope, and design the approach via Socratic dialogue
2. **Deploy** — Implement the ArgoCD app (values, Application CR, manifests)
3. **Blog** — Use the `/blog-post` skill to write the Hugo post. After creating the post, update `blog/content/building/00-overview/index.md` (Series Index + Capability Map) and `blog/layouts/shortcodes/cluster-roadmap.html` (add new roadmap layer)
4. **Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status in `README.md`
5. **Sync runbook** — Run `/sync-runbook` if the phase plan contains any `# manual-operation` blocks
6. **Review** — Verify deployment health and blog accuracy

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
blog/content/building/NN-slug/   # "Building Frank" posts
blog/content/operating/NN-slug/  # "Operating on Frank" posts
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

Cover image generation prompts go in `blog/prompt_for_images.yaml` — one entry per post, following the existing YAML format (key, output, description, prompt, optional post_process). Do NOT embed the prompt in the frontmatter `alt` field; `alt` should be a short human-readable description. Generate images with: `.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only <key>`

## Architecture

```
apps/                  # ArgoCD App-of-Apps (Helm chart + per-app values)
  root/                # Entry point — templates all Application CRs
  <app>/values.yaml    # Per-app Helm values
  <app>/manifests/     # Raw K8s manifests (when no upstream chart)
  vclusters/           # Per-vCluster Helm values (multi-tenancy)
    template/          # Base values template
    <name>/values.yaml # Per-instance overrides
patches/               # Talos machine config patches (per phase)
  phase01-node-config/ # Node labels, scheduling
  phase02-cilium/      # CNI, eBPF kube-proxy
  phase03-longhorn/    # Distributed storage
  phase04-gpu/         # NVIDIA GPU operator
  phase05-mini-config/ # Intel iGPU DRA
blog/                  # Hugo static site (PaperMod theme, building/ + operating/ series)
omni/                  # Sidero Omni self-hosted config
docs/plans/            # Design and implementation plans
docs/runbooks/         # Manual operations registry (manual-operations.yaml)
secrets/               # SOPS-encrypted bootstrap secrets (applied out-of-band)
scripts/               # Utility scripts
```

### Plan Naming Convention

Plan files follow: `YYYY-MM-DD-phaseNN-<feature-name>[-design].md`

- **New phases** start as `phaseXX` (no number). They get a real number only once implementation begins.
- **Bugfixes and extensions** of existing phases use the original phase number (e.g., `phase04-gpu1-pcie-link-speed-fix` extends Phase 4 GPU Stack).

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
| Grafana | 192.168.55.203 | Cilium L2 LoadBalancer |
| Infisical | 192.168.55.204 | Cilium L2 LoadBalancer |
| LiteLLM Gateway | 192.168.55.206 | Cilium L2 LoadBalancer |
| Sympozium Web UI | 192.168.55.207 | Cilium L2 LoadBalancer |
| Authentik | 192.168.55.211 | Cilium L2 LoadBalancer (port 9000) |

## Declarative-Only Principle

**Every resource on the cluster must be reproducible from code in this repo.** No `helm install`, no ad-hoc `kubectl apply` for workloads or configuration.

- All workloads: ArgoCD App-of-Apps (`apps/`)
- All machine config: Talos patches (`patches/`)
- The **only** accepted exception: SOPS-encrypted bootstrap secrets that must exist before the secret store is running. Apply them manually via `sops --decrypt <file> | kubectl apply -f -` and document the exception as a `# manual-operation` block in the plan and sync the runbook.

`helm repo add` and `helm show values` are fine as **local research tools** to discover chart schemas — they don't touch the cluster.

## Gotchas

- Always use `ServerSideApply=true` in ArgoCD sync options (avoids annotation size limits)
- Ignore Secret data diffs in ArgoCD (`ignoreDifferences` on `/data` jsonPointer)
- `prune: false` in syncPolicy — manual pruning only to avoid accidental deletion
- Blog images must be co-located in the page bundle directory (not in `/static/images/`)
- Intel GPU Resource Driver uses vendored chart with K8s 1.35 DRA patches
- GPU-1 has a NoSchedule taint — only GPU workloads schedule there
- SOPS/age encryption for secrets — never commit plaintext secrets
- Longhorn default replicaCount: 3 (matches 3 control-plane nodes)
- SOPS + ArgoCD ServerSideApply don't mix — encrypted secrets must live outside ArgoCD-managed paths (see `secrets/` dir) and be applied out-of-band
- Sympozium Helm chart is Git-sourced (not OCI) — chart isn't published to any registry
- Sympozium chart service template doesn't support type/annotations — use separate LB Service in extras
- Sympozium image.tag must be overridden (chart appVersion lags behind latest fix releases)
- Authentik blueprints may not auto-discover from ConfigMaps — create providers/apps via API as fallback
- Authentik API requires Bearer token (not basic auth) — create token via Django ORM: `Token.objects.get_or_create(identifier="name", defaults={"user": user, "intent": TokenIntents.INTENT_API})`
- Authentik 2026.x requires `invalidation_flow` and `redirect_uris` as list format in API calls
- Authentik `global.env` applies env vars to both server + worker (avoids duplication)
- Grafana OIDC: secret key must be `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` for `envFromSecret` to work

## Manual Operations

Some steps cannot be declarative (SOPS secrets, UI-only config). Every such step must be:

1. Documented in the relevant plan as a fenced YAML block tagged `# manual-operation`
2. Synced to `docs/runbooks/manual-operations.yaml` via `/sync-runbook`

### Block format (in plans)

```yaml
# manual-operation
id: phaseNN-short-name        # unique across all plans
phase: NN
app: <argocd-app-name>
plan: docs/plans/<filename>.md
when: "After Task N — <trigger description>"
why_manual: "<reason this cannot be automated>"
commands:
  - <exact command or UI instruction>
verify:
  - <command or instruction to confirm success>
status: pending               # update to: done after execution
```

### Central runbook

`docs/runbooks/manual-operations.yaml` — single source of truth for all manual ops across all phases. Run `/sync-runbook` to update it from plan files.
