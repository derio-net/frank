# ArgoCD Infrastructure — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Flux/Pulumi with ArgoCD to manage all Kubernetes workloads (Cilium, Longhorn, GPU Operator) while Omni continues managing the Talos/machine layer.

**Architecture:** Install ArgoCD v3.x, create an App-of-Apps Helm chart in `apps/root/` that bootstraps multi-source Applications for each infrastructure component. Each Application references its upstream Helm chart + local values from `apps/{name}/values.yaml`. ArgoCD adopts the existing Cilium and Longhorn releases in-place (no reinstall).

**Tech Stack:** ArgoCD v3.3, Helm, kubectl, omnictl (Layer 1 unchanged)

**Prereqs:** All commands assume `source .env` (loads KUBECONFIG + TALOSCONFIG) or `source .env_devops` (loads OMNI_ENDPOINT + OMNI_SERVICE_ACCOUNT_KEY) has been run.

**Git remote:** `https://github.com/derio-net/frank.git` (SSH: `git@github.com:derio-net/frank.git`)

---

## Phase A: Cleanup

### Task 1: Remove Flux CD

**Files:**
- None (cluster operations only)

**Context:** Flux CD is running but broken. Four controllers are in the `flux-system` namespace. There are 12 Flux CRDs installed. The `flux-system` kustomization shows `False` (path not found). This task removes everything.

**Step 1: Delete Flux custom resources**

```bash
source .env
kubectl delete kustomizations.kustomize.toolkit.fluxcd.io --all -n flux-system
kubectl delete gitrepositories.source.toolkit.fluxcd.io --all -n flux-system
kubectl delete helmreleases.helm.toolkit.fluxcd.io --all -A
kubectl delete helmrepositories.source.toolkit.fluxcd.io --all -A
```

Expected: All Flux custom resources deleted. Some may show "No resources found" — that's fine.

**Step 2: Delete Flux controllers**

```bash
source .env
kubectl delete deployment helm-controller kustomize-controller notification-controller source-controller -n flux-system
```

Expected: All 4 deployments deleted.

**Step 3: Delete Flux namespace**

```bash
source .env
kubectl delete namespace flux-system
```

Expected: Namespace terminating → deleted.

**Step 4: Delete Flux CRDs**

```bash
source .env
kubectl delete crd \
  alerts.notification.toolkit.fluxcd.io \
  buckets.source.toolkit.fluxcd.io \
  externalartifacts.source.toolkit.fluxcd.io \
  gitrepositories.source.toolkit.fluxcd.io \
  helmcharts.source.toolkit.fluxcd.io \
  helmreleases.helm.toolkit.fluxcd.io \
  helmrepositories.source.toolkit.fluxcd.io \
  kustomizations.kustomize.toolkit.fluxcd.io \
  ocirepositories.source.toolkit.fluxcd.io \
  providers.notification.toolkit.fluxcd.io \
  receivers.notification.toolkit.fluxcd.io
```

Expected: All 11 CRDs deleted (some may not exist — use `--ignore-not-found` if needed).

**Step 5: Verify Flux is completely gone**

```bash
source .env
kubectl get ns flux-system 2>&1
# Expected: Error from server (NotFound): namespaces "flux-system" not found

kubectl get crd | grep fluxcd 2>&1
# Expected: (empty output — no Flux CRDs remaining)
```

**Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove Flux CD controllers, CRDs, and namespace"
```

---

### Task 2: Remove Pulumi Artifacts and Deprecate Old Docs

**Files:**
- Delete: `infrastructure/pulumi/` (entire directory)
- Modify: `docs/plans/2026-03-02-pulumi-cluster-provisioning-design.md:1-6`
- Modify: `docs/plans/2026-03-02-pulumi-cluster-provisioning-plan.md:1-10`
- Modify: `.gitignore`

**Step 1: Delete the Pulumi directory**

```bash
rm -rf infrastructure/pulumi/
rmdir infrastructure/ 2>/dev/null  # Remove parent if empty
```

Expected: `infrastructure/` directory gone.

**Step 2: Add deprecation header to old design doc**

Prepend to `docs/plans/2026-03-02-pulumi-cluster-provisioning-design.md`:

```markdown
> **DEPRECATED (2026-03-02):** This Pulumi approach was abandoned. No Pulumi provider exists
> for Sidero Omni. See `2026-03-02-argocd-infrastructure-design.md` for the current approach.

```

**Step 3: Add deprecation header to old plan doc**

Prepend to `docs/plans/2026-03-02-pulumi-cluster-provisioning-plan.md`:

```markdown
> **DEPRECATED (2026-03-02):** This plan was never executed. The Pulumi approach was abandoned
> in favor of ArgoCD. See `2026-03-02-argocd-infrastructure-plan.md` for the current plan.

```

**Step 4: Clean up .gitignore — remove Pulumi-specific entries**

Remove these lines from `.gitignore`:

```
# Talos machine secrets (extracted from cluster, imported into Pulumi)
infrastructure/pulumi/secrets.yaml

# Pulumi stack config (may contain secrets)
infrastructure/pulumi/Pulumi.frank.yaml
```

Keep the general `.pulumi/` entry (it's fine to leave as a catch-all).

**Step 5: Verify**

```bash
ls infrastructure/ 2>&1
# Expected: No such file or directory

head -3 docs/plans/2026-03-02-pulumi-cluster-provisioning-design.md
# Expected: > **DEPRECATED...**
```

**Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove Pulumi scaffolding and deprecate stale plan docs"
```

---

## Phase B: ArgoCD Configuration Files

### Task 3: Create apps/ Directory Structure and Move Helm Values

**Files:**
- Create: `apps/cilium/values.yaml` (moved from `patches/phase2-cilium/cilium-values.yaml`)
- Create: `apps/longhorn/values.yaml` (moved from `patches/phase3-longhorn/longhorn-values.yaml`)
- Create: `apps/longhorn/manifests/gpu-local-sc.yaml` (moved from `patches/phase3-longhorn/longhorn-gpu-local-sc.yaml`)
- Create: `apps/gpu-operator/values.yaml` (moved from `patches/phase4-gpu/gpu-operator-values.yaml`)

**Context:** The Helm values files currently live in `patches/phase{N}-*/`. We're moving them to `apps/` where ArgoCD will reference them. The original files in `patches/` stay as historical reference (they document what was originally applied). Remove the header comments referencing manual `helm install` commands — ArgoCD handles installation now.

**Step 1: Create directory structure**

```bash
mkdir -p apps/cilium apps/longhorn/manifests apps/gpu-operator apps/argocd apps/root/templates
```

**Step 2: Create Cilium values**

Create `apps/cilium/values.yaml`:

```yaml
ipam:
  mode: kubernetes

kubeProxyReplacement: true
k8sServiceHost: 127.0.0.1
k8sServicePort: 7445

securityContext:
  capabilities:
    ciliumAgent:
      - CHOWN
      - KILL
      - NET_ADMIN
      - NET_RAW
      - IPC_LOCK
      - SYS_ADMIN
      - SYS_RESOURCE
      - DAC_OVERRIDE
      - FOWNER
      - SETGID
      - SETUID
    cleanCiliumState:
      - NET_ADMIN
      - SYS_ADMIN
      - SYS_RESOURCE

cgroup:
  autoMount:
    enabled: false
  hostRoot: /sys/fs/cgroup

hubble:
  enabled: true
  relay:
    enabled: true
  ui:
    enabled: true

operator:
  replicas: 2
```

**Step 3: Create Longhorn values**

Create `apps/longhorn/values.yaml`:

```yaml
defaultSettings:
  defaultReplicaCount: 3
  storageMinimalAvailablePercentage: 15
  nodeDownPodDeletionPolicy: delete-both-statefulset-and-deployment-pod
  defaultDataLocality: best-effort

persistence:
  defaultClassReplicaCount: 3
  defaultClass: true
```

**Step 4: Create Longhorn GPU-local StorageClass manifest**

Create `apps/longhorn/manifests/gpu-local-sc.yaml`:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn-gpu-local
provisioner: driver.longhorn.io
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
parameters:
  numberOfReplicas: "1"
  dataLocality: strict-local
  diskSelector: "gpu-local"
```

**Step 5: Create GPU Operator values**

Create `apps/gpu-operator/values.yaml`:

```yaml
driver:
  enabled: false

toolkit:
  enabled: false

operator:
  defaultRuntime: containerd
```

**Step 6: Verify files exist**

```bash
find apps/ -type f | sort
```

Expected:
```
apps/cilium/values.yaml
apps/gpu-operator/values.yaml
apps/longhorn/manifests/gpu-local-sc.yaml
apps/longhorn/values.yaml
```

**Step 7: Commit**

```bash
git add apps/
git commit -m "feat(argocd): add Helm values and manifests for infrastructure apps"
```

---

### Task 4: Create ArgoCD Helm Values

**Files:**
- Create: `apps/argocd/values.yaml`

**Context:** These are the Helm values for ArgoCD itself. We use the official `argo-cd` chart. Keep it minimal — homelab doesn't need HA or advanced features.

**Step 1: Create ArgoCD values**

Create `apps/argocd/values.yaml`:

```yaml
## ArgoCD Helm values
## Chart: argo-cd (argo/argo-cd)
## Repo: https://argoproj.github.io/argo-helm

# Single-replica for homelab (no HA needed)
controller:
  replicas: 1

server:
  replicas: 1
  # Disable TLS on server (Traefik handles TLS termination if needed)
  extraArgs:
    - --insecure

repoServer:
  replicas: 1

redis:
  enabled: true

# Disable dex (using built-in auth for now)
dex:
  enabled: false

configs:
  params:
    # Allow ArgoCD to manage resources in any namespace
    server.insecure: true
  cm:
    # Resource tracking via annotation (avoids conflicts with Helm labels)
    application.resourceTrackingMethod: annotation
```

**Step 2: Commit**

```bash
git add apps/argocd/values.yaml
git commit -m "feat(argocd): add ArgoCD Helm values for homelab deployment"
```

---

### Task 5: Create Root App-of-Apps Chart

**Files:**
- Create: `apps/root/Chart.yaml`
- Create: `apps/root/values.yaml`
- Create: `apps/root/templates/project.yaml`
- Create: `apps/root/templates/ns-longhorn.yaml`
- Create: `apps/root/templates/ns-gpu-operator.yaml`

**Context:** The root chart is a Helm chart that ArgoCD renders to produce child Application resources. It uses multi-source Applications: each child references an upstream Helm chart repo + this git repo for values.

**Step 1: Create Chart.yaml**

Create `apps/root/Chart.yaml`:

```yaml
apiVersion: v2
name: frank-infrastructure
version: 1.0.0
description: App-of-Apps for frank cluster infrastructure
```

**Step 2: Create values.yaml**

Create `apps/root/values.yaml`:

```yaml
# Git repo containing Helm values for each app
repoURL: https://github.com/derio-net/frank.git
targetRevision: main

# Cluster destination
destination:
  server: https://kubernetes.default.svc
```

**Step 3: Create AppProject template**

Create `apps/root/templates/project.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: infrastructure
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  description: Frank cluster infrastructure components
  sourceRepos:
    - '*'
  destinations:
    - namespace: '*'
      server: {{ .Values.destination.server }}
  clusterResourceWhitelist:
    - group: '*'
      kind: '*'
  namespaceResourceWhitelist:
    - group: '*'
      kind: '*'
```

**Step 4: Create Longhorn namespace template (with PSS labels)**

Create `apps/root/templates/ns-longhorn.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: longhorn-system
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: privileged
    pod-security.kubernetes.io/warn: privileged
```

**Step 5: Create GPU Operator namespace template (with PSS labels)**

Create `apps/root/templates/ns-gpu-operator.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: gpu-operator
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: privileged
    pod-security.kubernetes.io/warn: privileged
```

**Step 6: Verify chart renders**

```bash
helm template frank-infra apps/root/
```

Expected: Renders the AppProject and both Namespace YAML documents without errors.

**Step 7: Commit**

```bash
git add apps/root/Chart.yaml apps/root/values.yaml apps/root/templates/
git commit -m "feat(argocd): create root App-of-Apps chart with project and namespaces"
```

---

### Task 6: Create Cilium Application Template

**Files:**
- Create: `apps/root/templates/cilium.yaml`

**Context:** This Application adopts the existing Cilium Helm release (currently `cilium` in `kube-system`, chart v1.17.0, revision 1). ArgoCD uses `helm template` — it will detect the existing resources and manage them. The Application name MUST match the existing release name (`cilium`).

Multi-source: source 1 is the Helm chart, source 2 is this git repo (ref: values) for the values file.

**Step 1: Create Cilium Application template**

Create `apps/root/templates/cilium.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: cilium
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://helm.cilium.io/
      chart: cilium
      targetRevision: "1.17.0"
      helm:
        releaseName: cilium
        valueFiles:
          - $values/apps/cilium/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: kube-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

**Step 2: Verify renders**

```bash
helm template frank-infra apps/root/ | grep -A 5 "name: cilium"
```

Expected: Shows the Cilium Application with correct chart and values references.

**Step 3: Commit**

```bash
git add apps/root/templates/cilium.yaml
git commit -m "feat(argocd): add Cilium Application template (adopts existing release)"
```

---

### Task 7: Create Longhorn Application Templates

**Files:**
- Create: `apps/root/templates/longhorn.yaml`
- Create: `apps/root/templates/longhorn-extras.yaml`

**Context:** Longhorn has two parts: (1) the Helm chart, (2) the GPU-local StorageClass (a raw manifest not part of the chart). We create two Applications: one for the Helm release, one for the extra manifests directory.

**Step 1: Create Longhorn Helm Application template**

Create `apps/root/templates/longhorn.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: longhorn
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://charts.longhorn.io
      chart: longhorn
      targetRevision: "1.11.0"
      helm:
        releaseName: longhorn
        valueFiles:
          - $values/apps/longhorn/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: longhorn-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
```

**Step 2: Create Longhorn extras Application template**

Create `apps/root/templates/longhorn-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: longhorn-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/longhorn/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: longhorn-system
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
```

**Step 3: Verify renders**

```bash
helm template frank-infra apps/root/ | grep "name: longhorn"
```

Expected: Shows both `longhorn` and `longhorn-extras` Applications.

**Step 4: Commit**

```bash
git add apps/root/templates/longhorn.yaml apps/root/templates/longhorn-extras.yaml
git commit -m "feat(argocd): add Longhorn Application templates (Helm + extras)"
```

---

### Task 8: Create GPU Operator Application Template

**Files:**
- Create: `apps/root/templates/gpu-operator.yaml`

**Context:** The GPU Operator is NOT yet installed (blocked by GPU hardware not being detected on PCIe bus). This Application will be created but will NOT auto-sync initially. When the GPU hardware is fixed, enable auto-sync and it will install cleanly.

**Step 1: Create GPU Operator Application template**

Create `apps/root/templates/gpu-operator.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: gpu-operator
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
  annotations:
    argocd.argoproj.io/sync-wave: "10"
spec:
  project: infrastructure
  sources:
    - repoURL: https://helm.ngc.nvidia.com/nvidia
      chart: gpu-operator
      targetRevision: "v25.10.1"
      helm:
        releaseName: gpu-operator
        valueFiles:
          - $values/apps/gpu-operator/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: gpu-operator
  syncPolicy:
    # Manual sync — GPU hardware not yet detected
    # Change to automated after GPU is working:
    #   automated:
    #     prune: false
    #     selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
```

**Step 2: Verify renders**

```bash
helm template frank-infra apps/root/ | grep "name: gpu-operator"
```

Expected: Shows the GPU Operator Application.

**Step 3: Commit**

```bash
git add apps/root/templates/gpu-operator.yaml
git commit -m "feat(argocd): add GPU Operator Application template (manual sync until GPU fixed)"
```

---

## GATE 1: Operator Approval

**Pause here.** All configuration files are committed to git. Nothing has been applied to the cluster yet.

Review:
- `apps/` directory structure
- All Application templates render correctly (`helm template frank-infra apps/root/`)
- Values files match what's currently deployed

Push to remote before proceeding:
```bash
git push origin
```

---

## Phase C: ArgoCD Bootstrap

### Task 9: Install ArgoCD via Helm

**Context:** ArgoCD cannot manage its own initial installation (chicken-and-egg). We install it manually via Helm, then it can self-manage upgrades later. The chart is `argo-cd` from the official Argo Helm repo.

**Step 1: Create ArgoCD namespace**

```bash
source .env
kubectl create namespace argocd
```

Expected: `namespace/argocd created`

**Step 2: Add Argo Helm repo**

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
```

Expected: Repo added and updated.

**Step 3: Check latest ArgoCD chart version**

```bash
helm search repo argo/argo-cd --versions | head -5
```

Expected: Shows available versions. Note the latest v3.x version.

**Step 4: Install ArgoCD**

```bash
source .env
helm install argocd argo/argo-cd \
  --namespace argocd \
  -f apps/argocd/values.yaml
```

Expected: ArgoCD installed. Notes printed with initial admin password instructions.

**Step 5: Wait for ArgoCD to be ready**

```bash
source .env
kubectl -n argocd rollout status deploy/argocd-server --timeout=120s
kubectl -n argocd rollout status deploy/argocd-repo-server --timeout=120s
kubectl -n argocd rollout status deploy/argocd-application-controller --timeout=120s
```

Expected: All deployments rolled out successfully.

**Step 6: Verify all ArgoCD pods are running**

```bash
source .env
kubectl get pods -n argocd
```

Expected: All pods Running (server, repo-server, application-controller, redis).

**Step 7: Get initial admin password**

```bash
source .env
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
echo  # newline
```

Expected: Prints the initial admin password. Save it.

**Step 8: Test ArgoCD CLI login**

```bash
argocd login localhost:8080 \
  --port-forward \
  --port-forward-namespace argocd \
  --username admin \
  --password "$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)"
```

Expected: `'admin:login' logged in successfully`

If `argocd` CLI is not installed:
```bash
brew install argocd
```

**Step 9: Commit (no file changes — just noting state)**

No git commit needed for this task (cluster-only operation).

---

### Task 10: Configure ArgoCD Repository Access

**Context:** ArgoCD needs to access `https://github.com/derio-net/frank.git` to read the `apps/` directory. Since this is a private repo, we need to add credentials. Options: GitHub PAT, SSH deploy key, or GitHub App.

**Step 1: Add the git repository to ArgoCD**

Option A — Using HTTPS + GitHub PAT:
```bash
argocd repo add https://github.com/derio-net/frank.git \
  --port-forward --port-forward-namespace argocd \
  --username <github-username> \
  --password <github-pat>
```

Option B — Using SSH key:
```bash
argocd repo add git@github.com:derio-net/frank.git \
  --port-forward --port-forward-namespace argocd \
  --ssh-private-key-path ~/.ssh/id_ed25519
```

**HUMAN CHECKPOINT: The operator must provide GitHub credentials. Choose option A or B.**

Expected: `Repository 'https://github.com/derio-net/frank.git' added`

**Step 2: Verify repo is connected**

```bash
argocd repo list --port-forward --port-forward-namespace argocd
```

Expected: Shows the repo with `STATUS: Successful`.

---

## Phase D: Adoption

### Task 11: Push Config to Remote and Apply Root Application

**Context:** The root Application is the single entry point. It's applied manually once. ArgoCD then renders the Helm chart in `apps/root/` and creates all child Applications automatically.

**Step 1: Push all commits to remote**

```bash
git push origin
```

Expected: All commits pushed. ArgoCD can now read `apps/` from the repo.

**Step 2: Apply the root Application**

```bash
source .env
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
    path: apps/root
    targetRevision: main
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
EOF
```

Expected: `application.argoproj.io/root created`

**Step 3: Wait for root app to sync**

```bash
argocd app wait root \
  --port-forward --port-forward-namespace argocd \
  --timeout 120
```

Expected: Root app synced. Child Applications created.

**Step 4: Verify all applications exist**

```bash
argocd app list --port-forward --port-forward-namespace argocd
```

Expected:
```
NAME             CLUSTER                         NAMESPACE        PROJECT          STATUS   HEALTH    SYNCPOLICY
argocd/root      https://kubernetes.default.svc  argocd           default          Synced   Healthy   Auto-Prune
argocd/cilium    https://kubernetes.default.svc  kube-system      infrastructure   OutOfSync ...      Auto
argocd/longhorn  https://kubernetes.default.svc  longhorn-system  infrastructure   OutOfSync ...      Auto
argocd/longhorn-extras  ...                      longhorn-system  infrastructure   OutOfSync ...      Auto
argocd/gpu-operator     ...                      gpu-operator     infrastructure   ...       ...      <none>
```

Note: Child apps show `OutOfSync` initially — this is expected. ArgoCD's tracking annotations are missing from existing resources.

---

### Task 12: Sync and Verify Cilium Adoption

**Context:** Cilium is already running (Helm release `cilium` in `kube-system`, chart v1.17.0). When ArgoCD syncs, it will add tracking annotations to existing resources. No pods should restart as long as the rendered manifests match.

**Step 1: Check the diff before syncing**

```bash
argocd app diff cilium --port-forward --port-forward-namespace argocd
```

Expected: Shows differences — mostly tracking annotations being added. Review carefully. There should be NO changes to Deployment specs, DaemonSet specs, or ConfigMaps (values should match).

**HUMAN CHECKPOINT: Review the diff. If it shows changes beyond annotations, STOP and investigate. The values in `apps/cilium/values.yaml` may not match what was originally installed.**

**Step 2: Sync Cilium**

```bash
argocd app sync cilium --port-forward --port-forward-namespace argocd
```

Expected: Sync succeeds. ArgoCD adds tracking annotations.

**Step 3: Verify Cilium is still healthy**

```bash
source .env
kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium
# Expected: All cilium pods Running, no recent restarts

cilium status
# Expected: All agents healthy, kube-proxy replacement active
```

**Step 4: Verify ArgoCD shows Cilium as Synced + Healthy**

```bash
argocd app get cilium --port-forward --port-forward-namespace argocd
```

Expected: `Status: Synced`, `Health: Healthy`

---

### Task 13: Sync and Verify Longhorn Adoption

**Context:** Longhorn is already running (Helm release `longhorn` in `longhorn-system`, chart v1.11.0). Same adoption process as Cilium.

**Step 1: Check the diff before syncing**

```bash
argocd app diff longhorn --port-forward --port-forward-namespace argocd
```

Expected: Mostly tracking annotations. Review carefully.

**Step 2: Sync Longhorn**

```bash
argocd app sync longhorn --port-forward --port-forward-namespace argocd
```

Expected: Sync succeeds.

**Step 3: Sync Longhorn extras (GPU-local StorageClass)**

```bash
argocd app sync longhorn-extras --port-forward --port-forward-namespace argocd
```

Expected: Sync succeeds. StorageClass `longhorn-gpu-local` is now managed by ArgoCD.

**Step 4: Verify Longhorn is still healthy**

```bash
source .env
kubectl get pods -n longhorn-system | grep -c Running
# Expected: ~30+ pods running (manager, driver, engine, CSI)

kubectl get sc
# Expected: longhorn (default), longhorn-gpu-local, longhorn-static
```

**Step 5: Verify with a test PVC**

```bash
source .env
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: argocd-test-pvc
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
EOF

# Wait ~30s
kubectl get pvc argocd-test-pvc
# Expected: STATUS = Bound

# Clean up
kubectl delete pvc argocd-test-pvc
```

**Step 6: Verify ArgoCD shows Longhorn as Synced + Healthy**

```bash
argocd app get longhorn --port-forward --port-forward-namespace argocd
argocd app get longhorn-extras --port-forward --port-forward-namespace argocd
```

Expected: Both `Synced` and `Healthy`.

---

### Task 14: GPU Operator (Deferred — Manual Sync When Ready)

**Context:** The GPU Operator Application was created with NO automated sync policy (manual sync). The RTX 5070 is not detected on the PCIe bus (BIOS/hardware issue). This task documents what to do when the GPU hardware is fixed.

**When GPU hardware is detected (BIOS shows PCIEX16 populated):**

**Step 1: Verify GPU is on PCIe bus**

```bash
source .env
talosctl -n 192.168.55.31 dmesg | grep -i nvidia | head -5
# Expected: nvidia module loaded successfully (not "No NVIDIA GPU found")

talosctl -n 192.168.55.31 read /proc/bus/pci/devices | head
# Expected: Shows nvidia PCI device
```

**Step 2: Sync GPU Operator**

```bash
argocd app sync gpu-operator --port-forward --port-forward-namespace argocd
```

Expected: GPU Operator Helm chart installed in `gpu-operator` namespace.

**Step 3: Wait for GPU Operator pods**

```bash
source .env
kubectl get pods -n gpu-operator -w
# Wait until all pods Running (may take 2-3 minutes)
```

**Step 4: Verify GPU is allocatable**

```bash
source .env
kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
echo
# Expected: 1
```

**Step 5: Run nvidia-smi test**

```bash
source .env
kubectl run nvidia-test --rm -it --restart=Never \
  --image=nvcr.io/nvidia/cuda:12.8.0-base-ubuntu24.04 \
  --overrides='{"spec":{"runtimeClassName":"nvidia","tolerations":[{"key":"nvidia.com/gpu","operator":"Exists","effect":"NoSchedule"}],"nodeSelector":{"accelerator":"nvidia"}}}' \
  -- nvidia-smi
```

Expected: Shows RTX 5070, driver version, CUDA version.

**Step 6: Enable automated sync**

Update `apps/root/templates/gpu-operator.yaml` — uncomment the automated sync policy:

```yaml
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
```

Commit and push:
```bash
git add apps/root/templates/gpu-operator.yaml
git commit -m "feat(argocd): enable automated sync for GPU Operator (GPU detected)"
git push origin
```

Expected: ArgoCD auto-syncs the updated Application template.

---

## GATE 2: Final Verification

### Task 15: Full Cluster Verification

**Step 1: ArgoCD dashboard — all apps healthy**

```bash
argocd app list --port-forward --port-forward-namespace argocd
```

Expected:
```
NAME                    STATUS   HEALTH
argocd/root             Synced   Healthy
argocd/cilium           Synced   Healthy
argocd/longhorn         Synced   Healthy
argocd/longhorn-extras  Synced   Healthy
argocd/gpu-operator     OutOfSync  Missing  (expected until GPU hardware fixed)
```

**Step 2: All nodes Ready**

```bash
source .env
kubectl get nodes -L zone,tier,accelerator
```

Expected: All 7 nodes Ready with correct labels.

**Step 3: Cilium healthy**

```bash
cilium status
```

Expected: All OK.

**Step 4: Storage healthy**

```bash
source .env
kubectl get sc
kubectl -n longhorn-system get nodes.longhorn.io
```

Expected: 3 StorageClasses. All Longhorn nodes schedulable.

**Step 5: No Flux remnants**

```bash
source .env
kubectl get crd | grep flux
kubectl get ns flux-system 2>&1
```

Expected: No Flux CRDs. flux-system namespace not found.

**Step 6: No Pulumi remnants**

```bash
ls infrastructure/ 2>&1
```

Expected: No such file or directory.

**Step 7: Update patches/README.md with ArgoCD status**

Add to `patches/README.md`:

```markdown
## ArgoCD (Layer 2: Kubernetes Workloads)

Infrastructure Helm releases are managed by ArgoCD. See `apps/` for Application manifests and values.

| Application | Chart | Version | Namespace | Status |
|-------------|-------|---------|-----------|--------|
| cilium | cilium/cilium | 1.17.0 | kube-system | Adopted |
| longhorn | longhorn/longhorn | 1.11.0 | longhorn-system | Adopted |
| longhorn-extras | — (raw manifests) | — | longhorn-system | Synced |
| gpu-operator | nvidia/gpu-operator | v25.10.1 | gpu-operator | Pending (GPU hardware) |
```

**Step 8: Final commit**

```bash
git add -A
git commit -m "docs: update README with ArgoCD status, complete migration"
git push origin
```

---

## Rollback Procedures

### ArgoCD removal (full rollback):
```bash
# Delete all ArgoCD Applications (this does NOT delete the managed resources)
source .env
kubectl delete applications --all -n argocd

# Uninstall ArgoCD
helm uninstall argocd -n argocd
kubectl delete namespace argocd

# The underlying Cilium, Longhorn, and GPU Operator releases remain running
# They just won't be managed by ArgoCD anymore
```

### Individual app rollback:
```bash
# Remove ArgoCD management of a specific app (keeps the app running)
argocd app delete <app-name> --port-forward --port-forward-namespace argocd --cascade=false
```

### If Cilium adoption breaks networking:
```bash
# ArgoCD may be unreachable. Use kubectl directly:
source .env
kubectl delete application cilium -n argocd
# Cilium pods stay running — only ArgoCD management is removed
```
