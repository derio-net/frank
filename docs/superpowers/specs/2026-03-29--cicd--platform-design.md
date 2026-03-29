# CI/CD Platform — Design

**Date:** 2026-03-29
**Status:** Design
**Layer:** cicd (19)

## Overview

Deploy a K8s-native CI/CD platform on Frank: Gitea (local git forge mirroring GitHub), Tekton (pipeline engine), Zot (OCI registry), with cosign image signing. All workloads run on pc-1. The platform serves both human-driven and agent-driven (Paperclip/Sympozium) development workflows through a unified PR-based model.

## Goals

- Self-hosted CI/CD infrastructure — gain operational experience deploying and managing the full stack
- PR-driven pipelines — agents and humans follow the same workflow: push branch → open PR → Tekton runs pipeline → commit status reported
- Local registry with supply chain security — images built, stored, and signed on-cluster
- GitHub stays source of truth — Gitea mirrors repos locally so pipelines don't depend on internet access or hit rate limits

## Non-Goals (for this layer)

- Pipeline definitions for specific workloads (frank-cluster linting, app builds) — those are separate follow-up work
- Admission enforcement for signed images (Kyverno/policy-controller) — add as a future layer
- Multi-node CI/CD (spreading across raspis or minis) — start on pc-1 alone
- Auth on Tekton Dashboard — open on LB for now; add Authentik forward-auth as a follow-up

## Architecture

```
GitHub (source of truth)
    │ pull mirror (periodic, every 10 min)
    ▼
Gitea (192.168.55.209:3000 web, :22 SSH)
    │ webhook on push/PR
    ▼
Tekton EventListener (cluster-internal)
    │ TriggerBinding extracts repo/branch/sha/pr
    ▼
TriggerTemplate → creates PipelineRun
    │
    ▼
Tekton Pipeline (ephemeral pods on pc-1)
    ├─ git-clone (Tekton catalog Task)
    ├─ run-tests (custom Task)
    ├─ build-image (Kaniko or Stacker — builder-agnostic, param-driven)
    ├─ push-to-zot → Zot (192.168.55.210:5000)
    ├─ cosign-sign
    └─ gitea-status (finally block — reports pass/fail to PR)
         │
         ▼
    Tekton Dashboard (192.168.55.217:9097) — visibility
```

## IP Allocations

| IP | Service | Port |
|---|---|---|
| `192.168.55.209` | Gitea (web + SSH) | 3000, 22 |
| `192.168.55.210` | Zot registry | 5000 |
| `192.168.55.217` | Tekton Dashboard | 9097 |

These IPs were verified as unallocated on 2026-03-29 via `kubectl get svc -A | grep LoadBalancer`. IPs .209 and .210 were previously reserved by the now-deleted agents infrastructure plan but were never deployed. IP .216 was allocated by a parallel session.

## Components

### Gitea — Local Git Forge

**Chart:** `gitea-charts/gitea` (Helm, ArgoCD multi-source)

**Namespace:** `gitea`

**Service:**
- `192.168.55.209:3000` — Web UI + API (LoadBalancer via Cilium L2)
- `192.168.55.209:22` — SSH (same LoadBalancer IP)

Note: Talos does not run an SSH daemon, so port 22 on the host is free — no conflict. The Gitea Helm chart defaults SSH to port 2222; override to 22 via `service.ssh.port=22` and `gitea.config.server.SSH_PORT=22` in values.

**Database:** Embedded SQLite. Single-user homelab doesn't need PostgreSQL overhead. Migration to Postgres is straightforward if needed later. SQLite uses file locking, which requires single-writer access — combined with the RWO PVC constraint, `strategy: Recreate` is mandatory (both for volume detach and to avoid concurrent SQLite writers).

**Auth:** Authentik OIDC from day one. Gitea supports OIDC natively via `gitea.config.oauth2`. Local admin account created for bootstrap/emergency access only. Auto-registration enabled so Authentik users get Gitea accounts on first login. Local registration disabled.

**Mirroring:** Gitea's built-in pull mirror feature, configured per-repo via Gitea API after deployment. GitHub PAT stored in Infisical for private repo access.

**Storage:** Single Longhorn PVC (`longhorn-cicd` StorageClass, `numberOfReplicas: 1`). RWO + `strategy: Recreate`.

**Secrets (Infisical → ExternalSecret):**
- `GITEA_ADMIN_PASSWORD` — bootstrap admin password
- `GITEA_OIDC_CLIENT_SECRET` — Authentik OIDC client secret
- `GITHUB_MIRROR_TOKEN` — GitHub PAT for mirroring private repos

**ArgoCD Applications:**
- `gitea` — Helm chart (multi-source: upstream chart + `$values/apps/gitea/values.yaml`)
- `gitea-extras` — Raw manifests (`apps/gitea/manifests/`)

### Tekton — Pipeline Engine

**Installation:** Vendor official release YAMLs into the repo (same pattern as `intel-gpu-driver` which vendors a Helm chart). This keeps pinned, auditable copies in git and avoids the issue that ArgoCD cannot use a raw HTTPS URL as a source.

Vendored files in separate subdirectories (ArgoCD sources work at directory level, not file level):
```
apps/tekton/vendor/
  pipelines/release-vX.Y.Z.yaml   # from storage.googleapis.com/tekton-releases/pipeline/
  triggers/release-vX.Y.Z.yaml    # from storage.googleapis.com/tekton-releases/triggers/
  dashboard/release-vX.Y.Z.yaml   # from storage.googleapis.com/tekton-releases/dashboard/
```

Three separate ArgoCD Applications for independent lifecycle:

1. **Tekton Pipelines** — core controller, CRDs, webhook
2. **Tekton Triggers** — EventListener controller, TriggerBinding/Template CRDs
3. **Tekton Dashboard** — web UI

**CRD upgrade path:** Tekton CRDs are bundled inside the release YAMLs. ArgoCD with ServerSideApply handles initial install fine. On version upgrades, CRDs must be applied first (before the controller). Use ArgoCD sync-wave annotations: CRD resources at wave -1, controllers at wave 0. If sync-wave ordering proves unreliable, apply CRDs out-of-band before syncing the new version (`kubectl apply -f` the CRD subset).

**Namespace:** `tekton-pipelines` (Tekton's default, used by all three components)

**Service:**
- Tekton Dashboard: `192.168.55.217:9097` (LoadBalancer via Cilium L2)
- EventListener: ClusterIP only (`el-gitea-listener.tekton-pipelines.svc.cluster.local:8080`) — Gitea webhook URL must use this full internal DNS name

**Pipeline workspace:** VolumeClaimTemplate — Tekton creates and cleans up PVCs automatically per PipelineRun. Uses `longhorn-cicd` StorageClass. Note: Longhorn PVC creation adds ~2-3s to pipeline startup time — acceptable.

**ArgoCD Applications:**
- `tekton-pipelines` — raw manifests (`apps/tekton/vendor/pipelines/`)
- `tekton-triggers` — raw manifests (`apps/tekton/vendor/triggers/`)
- `tekton-dashboard` — raw manifests (`apps/tekton/vendor/dashboard/`)
- `tekton-extras` — raw manifests (`apps/tekton/pipelines/`, `apps/tekton/tasks/`, `apps/tekton/triggers/`)

### Tekton Trigger Wiring

**Gitea → Tekton flow:**

```
Gitea webhook (push/PR events)
    │ POST to http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080
    ▼
EventListener (el-gitea-listener)
    │ CEL interceptor validates webhook secret + filters/extracts fields
    ▼
TriggerBinding
    │ maps: repo_url, branch, commit_sha, pr_number
    ▼
TriggerTemplate
    │ creates PipelineRun with params + VolumeClaimTemplate workspace
    ▼
PipelineRun executes on pc-1
```

The Gitea webhook URL is the cluster-internal DNS name: `http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080`. No external exposure needed — Gitea runs in the same cluster.

**Webhook secret:** Gitea signs webhooks with a shared secret. Stored in Infisical → ExternalSecret, configured in both Gitea (webhook config) and the EventListener (CEL interceptor validation).

### Pipeline Stages (Incremental)

Pipelines are built incrementally. Each stage extends the previous and is a separate task in the implementation plan.

**Stage A — clone → test → report status:**
- `git-clone` — Tekton catalog Task (vendored into `apps/tekton/tasks/`)
- `run-tests` — custom Task, runs a configurable test command
- `gitea-status` — custom Task in `finally` block, POSTs commit status to Gitea API (`/api/v1/repos/{owner}/{repo}/statuses/{sha}`). Runs on both success and failure. Requires `GITEA_API_TOKEN`.

**Stage B — add image build + push:**
- `build-image` — builder-agnostic Task (Kaniko or Stacker selected via pipeline parameter)
- `push-to-zot` — pushes OCI image to `192.168.55.210:5000`

**Stage C — add cosign signing:**
- `cosign-sign` — signs the image digest in Zot. Cosign key pair stored in Infisical → ExternalSecret.

**File layout:**
```
apps/tekton/
  vendor/              # Vendored Tekton release YAMLs
  pipelines/           # Pipeline definitions
  tasks/               # Custom + vendored catalog Task definitions
  triggers/            # EventListener, TriggerBinding, TriggerTemplate
```

### Zot — OCI Registry

**Chart:** `zotregistry/zot` (Helm, ArgoCD multi-source)

**Namespace:** `zot`

**Service:** `192.168.55.210:5000` (LoadBalancer via Cilium L2) — registry API + built-in search UI

**Auth:**
- Web UI: Authentik OIDC (Zot supports OIDC natively)
- Machine access (Tekton push, containerd pull): htpasswd-based credentials
- Push credential stored in Infisical → ExternalSecret

**Storage:** Longhorn PVC (`longhorn-cicd` StorageClass, `numberOfReplicas: 1`), 50Gi (expandable). Durability via Longhorn backup-to-R2.

**TLS:** Self-signed cert initially. Containerd mirror config on all nodes with `insecureSkipVerify: true`. Replace with cert-manager issued cert later.

**Cosign support:** Native — Zot stores cosign signatures as OCI reference artifacts alongside images. No additional configuration.

**Containerd mirror config (Talos machine patch, cluster-wide via Omni):**

Containerd uses the mirror hostname `192.168.55.210:5000` directly — no DNS alias needed. The mirror config maps this to the Zot endpoint:

```yaml
machine:
  registries:
    config:
      "192.168.55.210:5000":
        tls:
          insecureSkipVerify: true
```

**Secrets (Infisical → ExternalSecret):**
- `ZOT_PUSH_PASSWORD` — htpasswd credential for Tekton
- `ZOT_OIDC_CLIENT_SECRET` — Authentik OIDC client secret

**ArgoCD Applications:**
- `zot` — Helm chart (multi-source: upstream chart + `$values/apps/zot/values.yaml`)
- `zot-extras` — Raw manifests (`apps/zot/manifests/`)

## Node Topology

All workloads on pc-1. Use `kubernetes.io/hostname: pc-1` as the nodeSelector (same pattern as ComfyUI uses `kubernetes.io/hostname: gpu-1`).

**Prerequisite:** Add `role: cicd` label to pc-1 via Omni config patch as documentation marker (the nodeSelector uses hostname, but the label aids `kubectl` queries like `kubectl get pods -l role=cicd`).

**Steady-state resource estimate:**

| Component | Pods | CPU req | Memory req | Storage |
|---|---|---|---|---|
| Gitea | 1 | 250m | 512Mi | 10Gi PVC |
| Tekton controller | 1 | 100m | 256Mi | — |
| Tekton Triggers | 1 | 50m | 128Mi | — |
| Tekton Dashboard | 1 | 50m | 128Mi | — |
| Zot | 1 | 100m | 256Mi | 50Gi PVC |
| **Total (steady)** | **5** | **~550m** | **~1.3 GiB** | **60Gi** |

Pipeline TaskRun pods are ephemeral (~1-2 CPU, 2-4 GiB RAM per run). Plenty of headroom on pc-1 (~4 CPU, ~31 GiB).

**Storage:** Create a `longhorn-cicd` StorageClass in `apps/longhorn/manifests/` (paralleling `longhorn-gpu-local`):

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn-cicd
provisioner: driver.longhorn.io
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
parameters:
  numberOfReplicas: "1"
  dataLocality: best-effort
```

Single replica — only pc-1 hosts CI/CD PVCs. Data durability via Longhorn backup-to-R2 (already configured cluster-wide).

Note: The existing `longhorn-extras` ArgoCD Application already watches `apps/longhorn/manifests/` — adding `longhorn-cicd.yaml` there will be picked up automatically on next sync.

## Secrets Summary

| Secret | Source | Used by | When to create |
|---|---|---|---|
| `GITEA_ADMIN_PASSWORD` | Infisical | Gitea bootstrap | Before Gitea deploy |
| `GITEA_OIDC_CLIENT_SECRET` | Infisical | Gitea ↔ Authentik | Before Gitea deploy |
| `GITHUB_MIRROR_TOKEN` | Infisical | Gitea GitHub mirroring | Before configuring mirror |
| `GITEA_WEBHOOK_SECRET` | Infisical | Gitea ↔ Tekton EventListener | Before wiring triggers |
| `GITEA_API_TOKEN` | Infisical | Tekton → Gitea commit status | After Gitea deploy (create service account in Gitea, generate token) |
| `ZOT_PUSH_PASSWORD` | Infisical | Tekton → Zot push | Before Zot deploy |
| `ZOT_OIDC_CLIENT_SECRET` | Infisical | Zot ↔ Authentik | Before Zot deploy |
| `COSIGN_KEY` | Infisical | Tekton cosign signing (Stage C) | Before Stage C |

## ArgoCD Applications Summary

| App Name | Type | Source | Namespace |
|---|---|---|---|
| `gitea` | Helm (multi-source) | `gitea-charts/gitea` | `gitea` |
| `gitea-extras` | Raw manifests | `apps/gitea/manifests/` | `gitea` |
| `tekton-pipelines` | Raw manifests | `apps/tekton/vendor/pipelines/` | `tekton-pipelines` |
| `tekton-triggers` | Raw manifests | `apps/tekton/vendor/triggers/` | `tekton-pipelines` |
| `tekton-dashboard` | Raw manifests | `apps/tekton/vendor/dashboard/` | `tekton-pipelines` |
| `tekton-extras` | Raw manifests | `apps/tekton/{pipelines,tasks,triggers}/` | `tekton-pipelines` |
| `zot` | Helm (multi-source) | `zotregistry/zot` | `zot` |
| `zot-extras` | Raw manifests | `apps/zot/manifests/` | `zot` |

## Implementation Order

1. **Prerequisites** — Create `longhorn-cicd` StorageClass, add `role=cicd` label to pc-1
2. **Gitea** — deploy, verify web UI + SSH, configure Authentik OIDC
3. **Gitea post-deploy** — create service account + API token, mirror test repo from GitHub
4. **Tekton core** — vendor release YAMLs, deploy Pipelines controller + Dashboard, run manual hello-world PipelineRun
5. **Tekton Triggers** — wire Gitea webhooks → EventListener, verify push triggers a PipelineRun
6. **Zot** — deploy registry, apply containerd mirror Talos patch, verify push/pull
7. **Pipeline Stage A** — clone → test → report commit status to Gitea PR
8. **Pipeline Stage B** — build image → push to Zot
9. **Pipeline Stage C** — cosign sign image after push

## Manual Operations

```yaml
# manual-operation
id: cicd-authentik-gitea-oidc
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before Gitea deploy — OIDC provider must exist in Authentik"
why_manual: "Authentik provider/application creation requires UI or API interaction"
commands:
  - "Authentik Admin → Applications → Create Provider → OAuth2/OIDC"
  - "Name: Gitea, Redirect URI: http://192.168.55.209:3000/user/oauth2/authentik/callback"
  - "Authentik Admin → Applications → Create Application → name: Gitea, provider: Gitea"
  - "Copy Client ID and Client Secret → store in Infisical as GITEA_OIDC_CLIENT_SECRET"
verify:
  - "Authentik Admin → Applications → Gitea shows active provider"
  - "Infisical → GITEA_OIDC_CLIENT_SECRET exists"
status: pending
```

```yaml
# manual-operation
id: cicd-infisical-gitea-secrets
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before Gitea deploy"
why_manual: "Infisical secret creation requires UI/API interaction"
commands:
  - "Create in Infisical: GITEA_ADMIN_PASSWORD (generate strong password)"
  - "Create in Infisical: GITHUB_MIRROR_TOKEN (GitHub PAT with repo read scope)"
verify:
  - "Infisical → GITEA_ADMIN_PASSWORD exists"
  - "Infisical → GITHUB_MIRROR_TOKEN exists"
status: pending
```

```yaml
# manual-operation
id: cicd-gitea-service-account
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "After Gitea is deployed and Authentik OIDC works"
why_manual: "Service account and API token must be created via Gitea UI/API"
commands:
  - "Gitea UI → Site Administration → User Accounts → Create (username: tekton-bot, email: tekton@frank.local)"
  - "Gitea UI → tekton-bot → Settings → Applications → Generate Token (name: tekton-ci, scopes: repo, issue)"
  - "Store token in Infisical as GITEA_API_TOKEN"
verify:
  - "curl -H 'Authorization: token <TOKEN>' http://192.168.55.209:3000/api/v1/user → returns tekton-bot"
  - "Infisical → GITEA_API_TOKEN exists"
status: pending
```

```yaml
# manual-operation
id: cicd-gitea-mirror-test-repo
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "After Gitea is deployed"
why_manual: "Mirror creation is a one-time Gitea API/UI operation"
commands:
  - "Gitea UI → + → New Migration → GitHub → URL of test repo → check 'Mirror' → interval 10m"
  - "Or via API: POST /api/v1/repos/migrate with mirror=true"
verify:
  - "Gitea → repo shows 'Mirror' badge, last synced within 10 minutes"
status: pending
```

```yaml
# manual-operation
id: cicd-gitea-webhook
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "After Tekton Triggers are deployed and EventListener is running"
why_manual: "Webhook creation is per-repo configuration in Gitea"
commands:
  - "Gitea → test repo → Settings → Webhooks → Add Webhook → Gitea"
  - "URL: http://el-gitea-listener.tekton-pipelines.svc.cluster.local:8080"
  - "Secret: (value from Infisical GITEA_WEBHOOK_SECRET)"
  - "Events: Push, Pull Request"
verify:
  - "Gitea → Webhooks → test delivery → returns 2xx from EventListener"
status: pending
```

```yaml
# manual-operation
id: cicd-infisical-webhook-secret
layer: cicd
app: tekton
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before wiring Tekton Triggers"
why_manual: "Infisical secret creation requires UI/API interaction"
commands:
  - "Create in Infisical: GITEA_WEBHOOK_SECRET (generate random string)"
verify:
  - "Infisical → GITEA_WEBHOOK_SECRET exists"
status: pending
```

```yaml
# manual-operation
id: cicd-authentik-zot-oidc
layer: cicd
app: zot
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before Zot deploy — OIDC provider must exist in Authentik"
why_manual: "Authentik provider/application creation requires UI or API interaction"
commands:
  - "Authentik Admin → Applications → Create Provider → OAuth2/OIDC"
  - "Name: Zot, Redirect URI: http://192.168.55.210:5000/auth/callback"
  - "Authentik Admin → Applications → Create Application → name: Zot, provider: Zot"
  - "Copy Client ID and Client Secret → store in Infisical as ZOT_OIDC_CLIENT_SECRET"
verify:
  - "Authentik Admin → Applications → Zot shows active provider"
  - "Infisical → ZOT_OIDC_CLIENT_SECRET exists"
status: pending
```

```yaml
# manual-operation
id: cicd-infisical-zot-secrets
layer: cicd
app: zot
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before Zot deploy"
why_manual: "Infisical secret creation requires UI/API interaction"
commands:
  - "Create in Infisical: ZOT_PUSH_PASSWORD (generate strong password)"
verify:
  - "Infisical → ZOT_PUSH_PASSWORD exists"
status: pending
```

```yaml
# manual-operation
id: cicd-talos-containerd-mirror
layer: cicd
app: zot
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "After Zot is deployed and verified"
why_manual: "Omni config patch requires UI or omnictl interaction; triggers node reboot"
commands:
  - "Apply Omni cluster-wide config patch with containerd mirror for 192.168.55.210:5000"
  - "Verify nodes reboot and come back Ready"
verify:
  - "talosctl -n 192.168.55.21 get machineconfig -o yaml | grep 192.168.55.210"
  - "kubectl get nodes — all nodes Ready"
  - "crictl pull 192.168.55.210:5000/test:latest (after pushing a test image)"
status: pending
```

```yaml
# manual-operation
id: cicd-cosign-keypair
layer: cicd
app: tekton
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before Pipeline Stage C"
why_manual: "Key generation must be done securely, then stored in Infisical"
commands:
  - "cosign generate-key-pair"
  - "Store cosign.key (private) in Infisical as COSIGN_KEY"
  - "Store cosign.pub (public) in repo at apps/tekton/cosign.pub"
verify:
  - "Infisical → COSIGN_KEY exists"
  - "cosign.pub committed to repo"
status: pending
```

```yaml
# manual-operation
id: cicd-pc1-role-label
layer: cicd
app: longhorn
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before any CI/CD workload deployment"
why_manual: "Omni config patch requires UI or omnictl interaction"
commands:
  - "Apply Omni machine config patch for pc-1: nodeLabels: role=cicd"
verify:
  - "kubectl get node pc-1 --show-labels | grep role=cicd"
status: pending
```

## Gotchas

- Gitea Helm chart defaults SSH to port 2222 — must override to 22 in values (`service.ssh.port` and `gitea.config.server.SSH_PORT`). Safe on Talos (no host SSH daemon).
- Gitea with SQLite on Longhorn RWO requires `strategy: Recreate` for two reasons: (1) RWO volume can't be mounted by two pods simultaneously, (2) SQLite file locking doesn't support concurrent writers.
- Tekton CRDs are bundled in release YAMLs — on version upgrades, use sync-wave annotations (CRDs at wave -1, controllers at wave 0) or apply CRDs out-of-band first.
- Tekton release YAMLs are vendored into the repo (not fetched from URLs) because ArgoCD doesn't support raw HTTPS URLs as sources.
- VolumeClaimTemplate PVCs add ~2-3s Longhorn provisioning latency to pipeline startup.
- Containerd mirror Talos patch triggers node reboots — schedule during maintenance window.
- `GITEA_API_TOKEN` can only be created after Gitea is deployed — implementation order must account for this dependency.
