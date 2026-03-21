# Frank, the Talos Cluster

AI-hybrid Kubernetes homelab managed via two-tier IaC: Omni (machine config) + ArgoCD (workloads).

## Standard Layer Workflow

Every layer follows this sequence:

1. **Brainstorm** — `/brainstorming` to explore requirements, refine scope, and design the approach via Socratic dialogue
2. **Plan** — `/writing-plans` to produce a step-by-step implementation plan. The layer code is chosen at this step (see `docs/layers.yaml` for the registry)
3. **Execute** — `/executing-plans` to implement the plan with review checkpoints
4. **Deploy** — Implement the ArgoCD app (values, Application CR, manifests)
5. **Blog** — Use the `/blog-post` skill to write the Hugo post. After creating the post, update `blog/content/building/00-overview/index.md` (Series Index + Capability Map) and `blog/layouts/shortcodes/cluster-roadmap.html` (add new roadmap layer)
6. **Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status in `README.md`
7. **Sync runbook** — Run `/sync-runbook` if the layer plan contains any `# manual-operation` blocks
8. **Sync Hop blog** — `source .env_hop && kubectl -n blog-system rollout restart deploy/blog` (GitHub Actions pushes the image but can't reach Hop's kubectl; manual rollout required until ArgoCD Image Updater is deployed)
9. **Review** — Verify deployment health and blog accuracy. Update the plan's `**Status:**` to `Deployed` (cluster workload) or `Complete` (repo/meta work)

## Layer Fix/Extension Workflow

When a deployed layer needs a bugfix or unplanned extension:

1. **Diagnose** — `/systematic-debugging` to identify root cause. Document findings in the existing layer plan as a new "Deviation" entry
2. **Fix** — Implement the fix in the original layer's ArgoCD app/manifests (not a new app)
3. **Update plan** — Add deviation notes inline at the affected task + append to the Deployment Deviations section
4. **Update blog** — Retroactively update the layer's building/ post (add gotcha or correction) and operating/ post (add new operational commands). Do NOT create a new post unless the fix is substantial enough to warrant its own narrative (e.g., the GPU Talos validation fix)
5. **Update CLAUDE.md gotchas** — If the fix reveals a non-obvious pattern, add it to the Gotchas section
6. **Sync Hop blog** — If blog content changed: `source .env_hop && kubectl -n blog-system rollout restart deploy/blog`

Use the layer code in commit messages: `fix(gpu): <description>` or `feat(edge): <description>`.

## Commands

```bash
# Environment — Frank cluster
source .env          # Frank (KUBECONFIG, TALOSCONFIG, OMNICONFIG)
source .env_devops   # DevOps (OMNI_ENDPOINT, service account key)

# Environment — Hop cluster (CAUTION: overrides KUBECONFIG)
source .env_hop      # Hop (KUBECONFIG → clusters/hop/talosconfig/kubeconfig)

# Frank cluster operations
kubectl get nodes -o wide
talosctl health --nodes $CONTROL_PLANE_IP_1
omnictl get machines

# Hop cluster operations (source .env_hop first)
export TALOSCONFIG=$(pwd)/clusters/hop/talosconfig/talosconfig
talosctl -n $HOP_IP health  # HOP_IP exported from .env_hop
kubectl -n argocd get applications

# ArgoCD (Frank)
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

Copy an existing template from `apps/root/templates/` and adapt. Key decisions:

- **Helm chart**: Multi-source — upstream chart + `$values/apps/<app>/values.yaml` ref
- **Raw manifests**: Single source — `path: apps/<app>/manifests`
- **Always include**: `ServerSideApply=true`, `prune: false`, `selfHeal: true`
- **Secrets**: Add `ignoreDifferences` on `/data` jsonPointer

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

Cover image generation prompts go in `blog/prompt_for_images.yaml` — one entry per post, following the existing YAML format (key, output, description, prompt, optional post_process). Insert prompts in their correct section (building prompts before `# --- Operating Series Covers`, operating prompts at end of operating section). Do NOT embed the prompt in the frontmatter `alt` field; `alt` should be a short human-readable description. Generate images with: `.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only <key>` (run `uv sync` first if the venv is stale)

## Architecture

```
apps/                  # ArgoCD App-of-Apps for Frank (Helm chart + per-app values)
  root/                # Entry point — templates all Application CRs
  <app>/values.yaml    # Per-app Helm values
  <app>/manifests/     # Raw K8s manifests (when no upstream chart)
  vclusters/           # Per-vCluster Helm values (multi-tenancy)
    template/          # Base values template
    <name>/values.yaml # Per-instance overrides
clusters/
  hop/                 # Hop edge cluster (Hetzner CX23, standalone talosctl)
    apps/              # Hop ArgoCD App-of-Apps
      root/            # Entry point for Hop's Application CRs
      argocd/          # ArgoCD values (minimal single-replica)
      headscale/       # Headscale mesh + Tailscale DaemonSet
      headplane/       # Headscale web UI
      caddy/           # Reverse proxy + TLS (Cloudflare DNS challenge)
      blog/            # Hugo blog container deployment
      landing/         # Private landing page (mesh-only)
      storage/         # Static PVs for Hetzner Volume
    packer/            # Packer template for Hetzner Talos image
    talosconfig/       # Talos client config (gitignored, contains secrets)
patches/               # Talos machine config patches (legacy phaseNN- naming)
  phase01-node-config/ # Node labels, scheduling
  phase02-cilium/      # CNI, eBPF kube-proxy
  phase03-longhorn/    # Distributed storage
  phase04-gpu/         # NVIDIA GPU operator
  phase05-mini-config/ # Intel iGPU DRA
blog/                  # Hugo static site (PaperMod theme, building/ + operating/ series)
omni/                  # Sidero Omni self-hosted config
docs/superpowers/plans/ # Implementation plans
docs/superpowers/specs/ # Design specs
docs/runbooks/         # Manual operations registry (manual-operations.yaml)
secrets/               # SOPS-encrypted bootstrap secrets (applied out-of-band)
  hop/                 # Hop cluster secrets
scripts/               # Utility scripts
```

### Plan Naming Convention

Plan and spec files follow: `YYYY-MM-DD--<layer>--<details>[-design].md`

- `<layer>` is the short code from `docs/layers.yaml` (e.g., `gpu`, `edge`, `auth`, `repo`)
- Multiple plans on the same layer share the code with different detail suffixes (e.g., `--gpu--intel-igpu-stack-mini` and `--gpu--operator-talos-fix`)
- The `repo` layer is for meta-tasks (blog infra, CI, restructuring)
- Bugfixes and extensions of existing layers use the same layer code. The relevant blog posts ('building' and 'operating' if appropriate) must be retroactively updated.

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

### Hop Cluster (Hetzner Cloud — standalone talosctl, not Omni)

| Host  | IP                     | Role                 | Zone                | Key Hardware       |
|-------|------------------------|----------------------|---------------------|--------------------|
| hop-1 | $HOP_IP (see .env_hop) | control-plane+worker | Edge (Hetzner fsn1) | CX23, 2 vCPU, 4GB |

## Services

### Frank Cluster

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
| Paperclip | 192.168.55.212 | Cilium L2 LoadBalancer (port 3100) |
| ComfyUI | 192.168.55.213 | Cilium L2 LoadBalancer (port 8188) |
| GPU Switcher | 192.168.55.214 | Cilium L2 LoadBalancer (port 8080) |

### Hop Cluster

| Service | Domain | Exposed Via |
|---------|--------|-------------|
| Headscale | headscale.hop.derio.net | Caddy (public) |
| Headplane | headplane.hop.derio.net | Caddy (mesh only) |
| Blog | blog.derio.net/frank | Caddy (public) |
| Landing | entry.hop.derio.net | Caddy (mesh only) |

## Declarative-Only Principle

**Every resource on the cluster must be reproducible from code in this repo.** No `helm install`, no ad-hoc `kubectl apply` for workloads or configuration.

- Frank workloads: ArgoCD App-of-Apps (`apps/`)
- Hop workloads: ArgoCD App-of-Apps (`clusters/hop/apps/`)
- All machine config: Talos patches (`patches/`)
- Hop machine config: `talosctl` with combined patch file (not Omni)
- The **only** accepted exception: bootstrap secrets that must exist before the secret store is running. Apply them manually and document as a `# manual-operation` block in the plan.
  - Frank: SOPS-encrypted secrets applied via `sops --decrypt <file> | kubectl apply -f -`
  - Hop: Plain Kubernetes Secrets applied via `kubectl create secret` (Caddy Cloudflare token, Tailscale auth key)

`helm repo add` and `helm show values` are fine as **local research tools** to discover chart schemas — they don't touch the cluster.

## Maintenance

### Superpowers plugin skills (vendored)

The superpowers skills in `.claude/skills/` and agents in `.claude/agents/` are vendored copies from the user-level plugin cache so they work in cloud/CI environments. They don't auto-update.

After updating the plugin locally (`claude plugin update superpowers@claude-plugins-official`), re-sync and commit:

```bash
./scripts/sync-superpowers.sh
git add .claude/skills/ .claude/agents/
git commit -m "chore: sync superpowers plugin skills"
```

Check for updates periodically (e.g., when starting a new layer).

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
- Authentik embedded outpost requires `AUTHENTIK_HOST` env var set to external URL (e.g., `https://auth.frank.derio.net`) — without it, forward-auth redirects use `0.0.0.0:9000`
- **Hop:** Never `source .env` when working on Hop — it overrides KUBECONFIG to Frank. Use `source .env_hop` instead
- **Hop:** Talos control-plane taint must be removed for single-node cluster (`allowSchedulingOnControlPlanes: true` in Talos config)
- **Hop:** PodSecurity namespaces (`caddy-system`, `headscale-system`) must be labeled `pod-security.kubernetes.io/enforce: privileged` for hostPort/privileged pods
- **Hop:** Deployments using `hostPort` (e.g., Caddy) must use `strategy: Recreate` — `RollingUpdate` deadlocks on a single-node cluster because the new pod can't bind ports while the old pod still holds them
- **Hop:** Headplane v0.5+ requires a `config.yaml` ConfigMap — env vars alone are insufficient
- **Hop:** Headscale `extra_records` in DNS config provides split-DNS for mesh-only services — add entries for any new mesh-only service
- **Hop:** `talosctl apply-config --config-patch` patches the base file, not the running config — all patches must be combined in one invocation
- **Hop:** Tailscale DaemonSet must run in kernel mode (`TS_USERSPACE=false`, `privileged: true`) for Caddy to see mesh source IPs
- **Hop:** Headplane v0.5.5 serves at `/admin/` base path (`basename="/admin/"`) — Caddy redirects all non-`/admin*` paths to `/admin/`
- **Hop:** Headplane requires `config_path` pointing to mounted Headscale config with `config_strict: true` — non-strict mode works but logs scary warnings and forfeits upstream support
- **Hop:** Headplane binds IPv4 only — `wget localhost:3000` fails (resolves to `::1`), use `wget 127.0.0.1:3000` to test
- **Hop:** Headplane API key must be injected via `HEADPLANE_HEADSCALE_API_KEY` env var from a Secret

## Manual Operations

Some steps cannot be declarative (SOPS secrets, UI-only config). Every such step must be:

1. Documented in the relevant plan as a fenced YAML block tagged `# manual-operation`
2. Synced to `docs/runbooks/manual-operations.yaml` via `/sync-runbook`

### Block format

Use fenced YAML with `# manual-operation` as first line. Required fields: `id`, `layer`, `app`, `plan`, `when`, `why_manual`, `commands`, `verify`, `status`. See `/sync-runbook` skill for the canonical schema.

### Central runbook

`docs/runbooks/manual-operations.yaml` — single source of truth for all manual ops across all layers. Run `/sync-runbook` to update it from plan files.
