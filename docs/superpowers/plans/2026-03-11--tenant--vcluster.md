# Multi-tenancy — vCluster Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy vCluster to enable disposable, fully isolated virtual Kubernetes clusters inside Frank, managed GitOps-style via ArgoCD.

**Architecture:** Each vCluster runs as a StatefulSet inside its own host namespace (`vcluster-<name>`). The vCluster control plane (virtual API server + syncer + embedded etcd) runs as pods in that namespace. Tenant workloads are synced to the host cluster for actual scheduling. A template values file provides sensible defaults; new vClusters are created by adding a values file + Application CR and committing.

**Tech Stack:** vCluster v0.32.1 (Helm chart from `https://charts.loft.sh`), ArgoCD App-of-Apps, Longhorn storage (etcd backing), Cilium L2 LoadBalancer (vCluster API exposure).

**Design doc:** `docs/superpowers/specs/2026-03-07--tenant--vcluster-design.md`

---

## File Structure

```
apps/
  vclusters/
    template/
      values.yaml              # Base vCluster values (sensible defaults, reusable)
    experiments/
      values.yaml              # First concrete vCluster instance (overrides template)
  root/
    templates/
      ns-vcluster-experiments.yaml   # Namespace with pod-security labels
      vcluster-experiments.yaml      # ArgoCD Application CR for "experiments" vCluster
```

Each new vCluster adds two files: `apps/vclusters/<name>/values.yaml` + `apps/root/templates/vcluster-<name>.yaml` (and optionally a namespace template if custom labels are needed).

---

## Chunk 1: Template Values and First vCluster

### Task 1: Create the vCluster template values file

This is the reusable base configuration. Individual vClusters override specific fields.

**Files:**
- Create: `apps/vclusters/template/values.yaml`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p apps/vclusters/template
```

- [ ] **Step 2: Write the template values file**

Create `apps/vclusters/template/values.yaml`:

```yaml
# vCluster template values — sensible defaults for Frank cluster
# Individual vClusters import these and override as needed.
#
# Chart: loft-sh/vcluster v0.32.1
# Repo:  https://charts.loft.sh

# Syncer configuration — what gets synced between host and virtual cluster
sync:
  toHost:
    pods:
      enabled: true
    services:
      enabled: true
    configmaps:
      enabled: true
    secrets:
      enabled: true
    endpoints:
      enabled: true
    persistentvolumeclaims:
      enabled: true
    ingresses:
      enabled: true
  fromHost:
    nodes:
      enabled: true
    storageClasses:
      enabled: true

# Backing store — embedded etcd with Longhorn persistence
controlPlane:
  backingStore:
    etcd:
      embedded:
        enabled: true
  statefulSet:
    persistence:
      volumeClaim:
        enabled: true
        storageClass: longhorn
        size: 5Gi
        retentionPolicy: Delete
    resources:
      requests:
        cpu: 100m
        memory: 256Mi
      limits:
        cpu: 500m
        memory: 512Mi

# Networking — no built-in ingress, access via vcluster connect
networking:
  service:
    type: ClusterIP

# Isolation — deny host cluster access from tenant workloads
isolation:
  enabled: true
  podSecurityStandard: baseline
  resourceQuota:
    enabled: true
    quota:
      requests.cpu: "4"
      requests.memory: 8Gi
      limits.cpu: "8"
      limits.memory: 16Gi
      pods: "50"
      services: "20"
      persistentvolumeclaims: "10"
  limitRange:
    enabled: true
    default:
      cpu: 500m
      memory: 512Mi
    defaultRequest:
      cpu: 100m
      memory: 128Mi
  networkPolicy:
    enabled: true
```

- [ ] **Step 3: Commit**

```bash
git add apps/vclusters/template/values.yaml
git commit -m "feat(phase12): add vCluster template values

Sensible defaults for disposable virtual clusters:
- Embedded etcd on Longhorn (5Gi)
- Baseline pod security
- Resource quotas (4 CPU / 8Gi request, 50 pods)
- Network policies enabled"
```

---

### Task 2: Create the "experiments" vCluster namespace

**Files:**
- Create: `apps/root/templates/ns-vcluster-experiments.yaml`

- [ ] **Step 1: Write namespace manifest**

Create `apps/root/templates/ns-vcluster-experiments.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: vcluster-experiments
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

- [ ] **Step 2: Commit**

```bash
git add apps/root/templates/ns-vcluster-experiments.yaml
git commit -m "feat(phase12): add vcluster-experiments namespace

Baseline pod security enforcement, restricted audit/warn."
```

---

### Task 3: Create the "experiments" vCluster values (overrides only)

The Application CR (Task 4) loads `template/values.yaml` first, then `experiments/values.yaml`. Helm deep-merges them in order — later files override earlier ones. So this file should **only** contain instance-specific overrides; everything else inherits from the template.

For the first "experiments" vCluster, the template defaults are fine as-is. The values file exists as the per-instance override point and documents which instance this is.

**Files:**
- Create: `apps/vclusters/experiments/values.yaml`

- [ ] **Step 1: Create directory**

```bash
mkdir -p apps/vclusters/experiments
```

- [ ] **Step 2: Write values file (overrides only)**

Create `apps/vclusters/experiments/values.yaml`:

```yaml
# vCluster "experiments" — disposable sandbox environment
# Base values come from apps/vclusters/template/values.yaml (loaded first in ArgoCD).
# This file contains only instance-specific overrides.
#
# Chart: loft-sh/vcluster v0.32.1
# Namespace: vcluster-experiments

# Currently using all template defaults.
# To override, add only the keys that differ. Examples:
#
# controlPlane:
#   statefulSet:
#     persistence:
#       volumeClaim:
#         size: 10Gi      # Larger etcd for long-lived experiments
#
# isolation:
#   resourceQuota:
#     quota:
#       pods: "100"       # Allow more pods in this vCluster
```

- [ ] **Step 3: Commit**

```bash
git add apps/vclusters/experiments/values.yaml
git commit -m "feat(phase12): add experiments vCluster override values

First concrete vCluster instance — sandbox for experiments.
Inherits all defaults from template/values.yaml."
```

---

### Task 4: Create the ArgoCD Application CR for "experiments"

The Application CR loads two valueFiles in order: template first, then instance overrides. Helm deep-merges them — later files win on conflicts. This is the core pattern for adding new vClusters: copy this CR, change the name/namespace/values path.

**Files:**
- Create: `apps/root/templates/vcluster-experiments.yaml`

- [ ] **Step 1: Write the Application CR**

Create `apps/root/templates/vcluster-experiments.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: vcluster-experiments
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://charts.loft.sh
      chart: vcluster
      targetRevision: "0.32.1"
      helm:
        releaseName: experiments
        valueFiles:
          # Template first (base defaults), then instance overrides
          - $values/apps/vclusters/template/values.yaml
          - $values/apps/vclusters/experiments/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: vcluster-experiments
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

- [ ] **Step 2: Commit**

```bash
git add apps/root/templates/vcluster-experiments.yaml
git commit -m "feat(phase12): add ArgoCD app for experiments vCluster

Deploys loft-sh/vcluster 0.32.1 into vcluster-experiments namespace.
ServerSideApply + selfHeal, Secret data ignored."
```

---

### Task 5: Push and verify ArgoCD sync

- [ ] **Step 1: Push all commits**

```bash
git push origin main
```

- [ ] **Step 2: Wait for ArgoCD to pick up changes**

```bash
# Check root app sees the new application
argocd app list --port-forward --port-forward-namespace argocd | grep vcluster
```

Expected: `vcluster-experiments` appears in the app list.

- [ ] **Step 3: Sync if not auto-synced**

```bash
argocd app sync root --port-forward --port-forward-namespace argocd
```

- [ ] **Step 4: Wait for vCluster to become healthy**

```bash
# Watch the vCluster pods come up
kubectl get pods -n vcluster-experiments -w
```

Expected: `experiments-0` pod reaches `Running` + `Ready` state (may take 1-2 minutes for etcd init).

- [ ] **Step 5: Verify ArgoCD app health**

```bash
argocd app get vcluster-experiments --port-forward --port-forward-namespace argocd
```

Expected: Status `Synced`, Health `Healthy`.

- [ ] **Step 6: Commit nothing — this is a verification step only**

---

### Task 6: Connect to vCluster and validate

- [ ] **Step 1: Install vcluster CLI (if not present)**

```bash
if ! command -v vcluster &> /dev/null; then
  curl -L -o vcluster "https://github.com/loft-sh/vcluster/releases/download/v0.32.1/vcluster-linux-amd64"
  chmod +x vcluster
  sudo mv vcluster /usr/local/bin/
  vcluster --version
else
  echo "vcluster CLI already installed: $(vcluster --version)"
fi
```

Expected: `vcluster version 0.32.1` (or similar).

- [ ] **Step 2: Connect to the experiments vCluster**

```bash
vcluster connect experiments -n vcluster-experiments
```

Expected: A kubeconfig is generated and the current context is switched to the virtual cluster.

- [ ] **Step 3: Verify the virtual cluster is functional**

```bash
# Inside the vCluster context:
kubectl get nodes
kubectl get namespaces
kubectl create namespace test-sandbox
kubectl run nginx --image=nginx:alpine -n test-sandbox
kubectl get pods -n test-sandbox -w
```

Expected: Nodes are visible (synced from host), nginx pod reaches `Running`.

- [ ] **Step 4: Verify host-side isolation**

```bash
# Switch back to host context
vcluster disconnect

# The nginx pod should appear in the host namespace (synced)
kubectl get pods -n vcluster-experiments | grep nginx

# But the pod should NOT be visible in other namespaces
kubectl get pods -A | grep test-sandbox
# Expected: no results (virtual namespace doesn't exist on host)
```

- [ ] **Step 5: Clean up test workload**

```bash
vcluster connect experiments -n vcluster-experiments
kubectl delete namespace test-sandbox
vcluster disconnect
```

- [ ] **Step 6: Commit nothing — verification only**

---

## Chunk 2: Documentation and Design File Update

### Task 7: Rename design file (COMPLETED — already renamed to layer-based naming)

The design file has been renamed to `docs/superpowers/specs/2026-03-07--tenant--vcluster-design.md` as part of the layer naming convention update.

---

### Task 8: Update CLAUDE.md services table

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update Architecture directory tree in CLAUDE.md**

vCluster access is kubeconfig-based (`vcluster connect`), not exposed via a LoadBalancer UI. No entry needed in the Services table.

In the `## Architecture` section's directory tree, add the `vclusters/` entry under `apps/`. Find the line `<app>/manifests/     # Raw K8s manifests (when no upstream chart)` and add after it:

```
  vclusters/             # Per-vCluster Helm values (multi-tenancy)
    template/            # Base values template
    <name>/values.yaml   # Per-instance overrides
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add vclusters directory to CLAUDE.md architecture

Documents the per-vCluster values pattern under apps/."
```

---

### Task 9: Follow standard layer workflow — Blog, README, Runbook

Per the Standard Layer Workflow in CLAUDE.md:

- [ ] **Step 1: Blog post** — Run `/blog-post` skill. Title: "Multi-tenancy: Disposable Kubernetes Clusters with vCluster". Update the series index (`blog/content/posts/00-overview/index.md`) and roadmap shortcode (`blog/layouts/shortcodes/cluster-roadmap.html`).

- [ ] **Step 2: Update README** — Run `/update-readme` to sync Technology Stack, Repository Structure, Service Access, and Current Status.

- [ ] **Step 3: Sync runbook** — Run `/sync-runbook` if any `# manual-operation` blocks exist in this plan. (This plan has none — vCluster CLI install is a developer tool, not a cluster operation.)

- [ ] **Step 4: Review** — Verify deployment health and blog accuracy.
