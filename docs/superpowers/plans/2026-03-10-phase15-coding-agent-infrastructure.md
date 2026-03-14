# Phase 15 — Autonomous Coding Agent Infrastructure — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy a full autonomous coding agent pipeline — Aider Jobs orchestrated by n8n, backed by Gitea (git + CI/CD) and Harbor (registry), with the CI/CD zone running on pc-1/pc-2 desktop workers.

**Architecture:** Aider runs as ephemeral K8s Jobs on gpu-1, calling Ollama via LiteLLM for inference. n8n orchestrates task assignment and monitoring from the minis. Gitea hosts repos and runs GitHub Actions-compatible CI via act_runner on pc-1/pc-2. Harbor stores container images and artifacts on the same nodes. All apps are ArgoCD-managed following Frank's App-of-Apps pattern.

**Tech Stack:** ArgoCD, Helm, Longhorn, Cilium L2, Infisical + ExternalSecrets, Talos Linux, Gitea, Harbor, n8n, Aider

**Design doc:** `docs/superpowers/plans/2026-03-10-phase15-coding-agent-infrastructure-design.md`

---

## Prerequisites

- pc-1 and pc-2 are online, adopted into the cluster via Omni, and showing `Ready` in `kubectl get nodes`
- Disk capacity on pc-1/pc-2 has been audited (`lsblk` via `talosctl`)
- Disks formatted and mounted via Talos machine config patches
- Existing Phase 10 stack operational (Ollama, LiteLLM, Infisical, ExternalSecrets)

---

## Task 1: Longhorn-HDD StorageClass

**Files:**
- Create: `apps/longhorn/manifests/storageclass-longhorn-hdd.yaml`
- Create: `apps/root/templates/longhorn-extras.yaml` (if no extras app exists yet — check first)

**Step 1: Tag pc-1/pc-2 disks in Longhorn**

Via Longhorn UI (`192.168.55.201`):
1. Navigate to Node → pc-1 → Edit Disks
2. Add HDD disk(s), set disk tag: `hdd`
3. Repeat for pc-2

```yaml
# manual-operation
id: phase15-longhorn-disk-tags
phase: 15
app: longhorn
plan: docs/superpowers/plans/2026-03-10-phase15-coding-agent-infrastructure.md
when: "Before Task 1 Step 2 — Longhorn needs disk tags before StorageClass can schedule"
why_manual: "Longhorn disk tagging requires UI or API interaction"
commands:
  - "Longhorn UI → Node → pc-1 → Edit Node → Add Disk → path: /var/mnt/hdd1 → Tag: hdd"
  - "Longhorn UI → Node → pc-2 → Edit Node → Add Disk → path: /var/mnt/hdd1 → Tag: hdd"
verify:
  - "Longhorn UI → Node → pc-1 → disk shows tag 'hdd' and status 'Schedulable'"
  - "Longhorn UI → Node → pc-2 → disk shows tag 'hdd' and status 'Schedulable'"
status: pending
```

**Step 2: Create the StorageClass manifest**

Create `apps/longhorn/manifests/storageclass-longhorn-hdd.yaml`:

```yaml
# Longhorn-HDD StorageClass for CI/CD zone (pc-1, pc-2)
# 2 replicas across desktop workers with HDD-tagged disks
# Used by: Gitea repos, Harbor blobs, CI artifacts
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn-hdd
provisioner: driver.longhorn.io
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
parameters:
  numberOfReplicas: "2"
  dataLocality: best-effort
  diskSelector: "hdd"
  nodeSelector: "zone=cicd"
```

**Step 3: Create ArgoCD Application for longhorn extras (if needed)**

Check if `apps/root/templates/longhorn-extras.yaml` exists. If not, create it following Pattern D (raw manifests):

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
    syncOptions:
      - ServerSideApply=true
```

**Step 4: Add node labels for pc-1/pc-2**

Create Talos machine config patches for pc-1 and pc-2 node labels (following the existing pattern in `patches/phase01-node-config/`):

```yaml
# patches/phase15-cicd-zone/200-labels-pc-1.yaml
metadata:
    namespace: default
    type: ConfigPatches.omni.sidero.dev
    id: 200-labels-pc-1
    labels:
        omni.sidero.dev/cluster: frank
        omni.sidero.dev/cluster-machine: <pc-1-machine-id>
spec:
    data: |
        machine:
            nodeLabels:
                zone: cicd
                tier: standard
```

```yaml
# patches/phase15-cicd-zone/200-labels-pc-2.yaml
metadata:
    namespace: default
    type: ConfigPatches.omni.sidero.dev
    id: 200-labels-pc-2
    labels:
        omni.sidero.dev/cluster: frank
        omni.sidero.dev/cluster-machine: <pc-2-machine-id>
spec:
    data: |
        machine:
            nodeLabels:
                zone: cicd
                tier: standard
```

Look up machine IDs with: `omnictl get machines`

**Step 5: Commit**

```bash
git add apps/longhorn/manifests/storageclass-longhorn-hdd.yaml patches/phase15-cicd-zone/
git add apps/root/templates/longhorn-extras.yaml  # if created
git commit -m "feat(phase15): add longhorn-hdd StorageClass and CI/CD zone node labels"
```

**Step 6: Verify**

```bash
# After ArgoCD sync
kubectl get storageclass longhorn-hdd
kubectl get nodes --show-labels | grep -E "pc-1|pc-2"
# Expect: zone=cicd label on both nodes
```

---

## Task 2: Gitea Deployment

**Files:**
- Create: `apps/gitea/values.yaml`
- Create: `apps/gitea/manifests/externalsecret-gitea.yaml`
- Create: `apps/root/templates/gitea.yaml`

**Step 1: Research the Gitea Helm chart**

```bash
helm repo add gitea-charts https://dl.gitea.com/charts/
helm show values gitea-charts/gitea > /tmp/gitea-defaults.yaml
```

Review defaults for: `persistence`, `postgresql`, `gitea.config`, `service`, `nodeSelector`, `tolerations`.

**Step 2: Create Infisical secrets**

```yaml
# manual-operation
id: phase15-gitea-infisical-secrets
phase: 15
app: gitea
plan: docs/superpowers/plans/2026-03-10-phase15-coding-agent-infrastructure.md
when: "Before deploying gitea — ExternalSecret needs Infisical source"
why_manual: "Infisical secret creation requires UI/API interaction"
commands:
  - "Create in Infisical: GITEA_ADMIN_PASSWORD (generate strong password)"
  - "Create in Infisical: GITEA_ADMIN_USER (value: gitea_admin)"
verify:
  - "Infisical UI → Secrets → GITEA_ADMIN_PASSWORD exists"
  - "Infisical UI → Secrets → GITEA_ADMIN_USER exists"
status: pending
```

**Step 3: Create ExternalSecret**

Create `apps/gitea/manifests/externalsecret-gitea.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: gitea-admin-secret
  namespace: gitea
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: gitea-admin-secret
    creationPolicy: Owner
  data:
    - secretKey: username
      remoteRef:
        key: GITEA_ADMIN_USER
    - secretKey: password
      remoteRef:
        key: GITEA_ADMIN_PASSWORD
```

**Step 4: Create Helm values**

Create `apps/gitea/values.yaml`:

```yaml
# Gitea — self-hosted Git forge for the CI/CD zone
# Exposed at 192.168.55.209:3000 (HTTP) and :22 (SSH)
# Runs on pc-1/pc-2 with Longhorn-HDD storage

gitea:
  admin:
    existingSecret: gitea-admin-secret
    # Keys: username, password (from ExternalSecret)

  config:
    server:
      DOMAIN: 192.168.55.209
      ROOT_URL: http://192.168.55.209:3000/
      SSH_DOMAIN: 192.168.55.209
      SSH_PORT: 22
      LFS_START_SERVER: true

    actions:
      ENABLED: true

    repository:
      DEFAULT_BRANCH: main

    service:
      DISABLE_REGISTRATION: true
      REQUIRE_SIGNIN_VIEW: false

service:
  http:
    type: LoadBalancer
    port: 3000
    annotations:
      lbipam.cilium.io/ips: "192.168.55.209"
  ssh:
    type: LoadBalancer
    port: 22
    annotations:
      lbipam.cilium.io/ips: "192.168.55.209"

persistence:
  enabled: true
  size: 50Gi
  storageClass: longhorn-hdd
  accessModes:
    - ReadWriteOnce

postgresql:
  enabled: true
  primary:
    persistence:
      enabled: true
      size: 5Gi
      storageClass: longhorn-hdd

nodeSelector:
  zone: cicd

tolerations: []
```

**Step 5: Create ArgoCD Application CR**

Create `apps/root/templates/gitea.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: gitea
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://dl.gitea.com/charts/
      chart: gitea
      targetRevision: "11.0.0"
      helm:
        releaseName: gitea
        valueFiles:
          - $values/apps/gitea/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: gitea
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

Note: Pin `targetRevision` to the latest stable version at implementation time. Run `helm search repo gitea-charts/gitea --versions | head -5` to find it.

**Step 6: Create ArgoCD Application for Gitea extras (manifests)**

Create `apps/root/templates/gitea-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: gitea-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/gitea/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: gitea
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

**Step 7: Commit**

```bash
git add apps/gitea/ apps/root/templates/gitea.yaml apps/root/templates/gitea-extras.yaml
git commit -m "feat(phase15): add Gitea git forge for CI/CD zone"
```

**Step 8: Push and verify**

```bash
git push
# Wait for ArgoCD sync
argocd app get gitea --port-forward --port-forward-namespace argocd
argocd app get gitea-extras --port-forward --port-forward-namespace argocd
kubectl get pods -n gitea
# Expect: gitea-0 Running, gitea-postgresql-0 Running
curl -s http://192.168.55.209:3000/api/v1/version
# Expect: {"version":"..."}
```

---

## Task 3: Gitea Actions Runners

**Files:**
- Create: `apps/gitea/manifests/act-runner-config.yaml`
- Create: `apps/gitea/manifests/act-runner-deployment.yaml`
- Create: `apps/gitea/manifests/externalsecret-runner-token.yaml`

**Step 1: Generate runner registration token**

```yaml
# manual-operation
id: phase15-gitea-runner-token
phase: 15
app: gitea
plan: docs/superpowers/plans/2026-03-10-phase15-coding-agent-infrastructure.md
when: "After Gitea is running — runner needs registration token"
why_manual: "Runner token is generated via Gitea admin API"
commands:
  - "curl -X POST http://192.168.55.209:3000/api/v1/user/actions/runners/registration-token -H 'Authorization: token <GITEA_ADMIN_TOKEN>' | jq -r '.token'"
  - "Store token in Infisical: GITEA_RUNNER_REGISTRATION_TOKEN"
verify:
  - "Infisical UI → Secrets → GITEA_RUNNER_REGISTRATION_TOKEN exists"
status: pending
```

**Step 2: Create ExternalSecret for runner token**

Create `apps/gitea/manifests/externalsecret-runner-token.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: gitea-runner-token
  namespace: gitea
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: gitea-runner-token
    creationPolicy: Owner
  data:
    - secretKey: token
      remoteRef:
        key: GITEA_RUNNER_REGISTRATION_TOKEN
```

**Step 3: Create runner ConfigMap**

Create `apps/gitea/manifests/act-runner-config.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: act-runner-config
  namespace: gitea
data:
  config.yaml: |
    log:
      level: info
    runner:
      capacity: 2
      timeout: 30m
      labels:
        - "ubuntu-latest:docker://node:20-bookworm"
        - "ubuntu-22.04:docker://node:20-bookworm"
    container:
      network: ""
      privileged: true
```

**Step 4: Create runner Deployment**

Create `apps/gitea/manifests/act-runner-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: act-runner
  namespace: gitea
spec:
  replicas: 2
  selector:
    matchLabels:
      app: act-runner
  template:
    metadata:
      labels:
        app: act-runner
    spec:
      nodeSelector:
        zone: cicd
      containers:
        - name: runner
          image: gitea/act_runner:latest
          command: ["sh", "-c"]
          args:
            - |
              act_runner register \
                --instance http://gitea-http.gitea.svc.cluster.local:3000 \
                --token "$(cat /secrets/token)" \
                --name "$(HOSTNAME)" \
                --labels "ubuntu-latest:docker://node:20-bookworm,ubuntu-22.04:docker://node:20-bookworm" \
                --no-interactive && \
              act_runner daemon --config /config/config.yaml
          env:
            - name: DOCKER_HOST
              value: tcp://localhost:2376
            - name: DOCKER_TLS_VERIFY
              value: "1"
            - name: DOCKER_CERT_PATH
              value: /certs/client
          volumeMounts:
            - name: runner-token
              mountPath: /secrets
              readOnly: true
            - name: config
              mountPath: /config
              readOnly: true
            - name: docker-certs
              mountPath: /certs
              readOnly: true
            - name: runner-data
              mountPath: /data
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              memory: 2Gi
        - name: docker
          image: docker:27-dind
          securityContext:
            privileged: true
          env:
            - name: DOCKER_TLS_CERTDIR
              value: /certs
          volumeMounts:
            - name: docker-certs
              mountPath: /certs
            - name: docker-data
              mountPath: /var/lib/docker
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              memory: 4Gi
      volumes:
        - name: runner-token
          secret:
            secretName: gitea-runner-token
        - name: config
          configMap:
            name: act-runner-config
        - name: docker-certs
          emptyDir: {}
        - name: docker-data
          emptyDir: {}
        - name: runner-data
          emptyDir: {}
```

Note: This uses DinD sidecar for container execution. The `privileged: true` is scoped to the CI/CD zone nodes only. Test on Talos during implementation — if DinD doesn't work, fall back to host-mode runner without container isolation.

**Step 5: Commit**

```bash
git add apps/gitea/manifests/act-runner-*.yaml apps/gitea/manifests/externalsecret-runner-token.yaml
git commit -m "feat(phase15): add Gitea Actions runners with DinD sidecar"
```

**Step 6: Push and verify**

```bash
git push
kubectl get pods -n gitea -l app=act-runner
# Expect: 2 runner pods Running
# Verify in Gitea UI: Site Administration → Runners → 2 runners Online
```

**Step 7: Test CI pipeline**

Create a test repo in Gitea UI, add a workflow:

```yaml
# .gitea/workflows/test.yaml
name: Test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "Hello from Gitea Actions on Frank!"
```

Push and verify the workflow runs successfully in the Gitea UI → Actions tab.

---

## Task 4: Harbor Registry

**Files:**
- Create: `apps/harbor/values.yaml`
- Create: `apps/harbor/manifests/externalsecret-harbor.yaml`
- Create: `apps/root/templates/harbor.yaml`
- Create: `apps/root/templates/harbor-extras.yaml`
- Create: `patches/phase15-cicd-zone/containerd-mirror.yaml`

**Step 1: Research Harbor Helm chart**

```bash
helm repo add harbor https://helm.goharbor.io
helm show values harbor/harbor > /tmp/harbor-defaults.yaml
```

**Step 2: Create Infisical secrets**

```yaml
# manual-operation
id: phase15-harbor-infisical-secrets
phase: 15
app: harbor
plan: docs/superpowers/plans/2026-03-10-phase15-coding-agent-infrastructure.md
when: "Before deploying Harbor"
why_manual: "Infisical secret creation requires UI/API interaction"
commands:
  - "Create in Infisical: HARBOR_ADMIN_PASSWORD (generate strong password)"
  - "Create in Infisical: HARBOR_SECRET_KEY (generate 16-char random string)"
verify:
  - "Infisical UI → Secrets → HARBOR_ADMIN_PASSWORD exists"
  - "Infisical UI → Secrets → HARBOR_SECRET_KEY exists"
status: pending
```

**Step 3: Create ExternalSecret**

Create `apps/harbor/manifests/externalsecret-harbor.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: harbor-admin-secret
  namespace: harbor
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: harbor-admin-secret
    creationPolicy: Owner
  data:
    - secretKey: HARBOR_ADMIN_PASSWORD
      remoteRef:
        key: HARBOR_ADMIN_PASSWORD
    - secretKey: secretKey
      remoteRef:
        key: HARBOR_SECRET_KEY
```

**Step 4: Create Harbor Helm values**

Create `apps/harbor/values.yaml`:

```yaml
# Harbor — container and artifact registry for CI/CD zone
# Exposed at 192.168.55.210:443 (HTTPS)
# Runs on pc-1/pc-2 with Longhorn-HDD storage

expose:
  type: loadBalancer
  tls:
    enabled: true
    certSource: auto
  loadBalancer:
    name: harbor
    annotations:
      lbipam.cilium.io/ips: "192.168.55.210"

externalURL: https://192.168.55.210

harborAdminPassword: ""  # Overridden by existingSecretAdminPassword
existingSecretAdminPassword: harbor-admin-secret
existingSecretAdminPasswordKey: HARBOR_ADMIN_PASSWORD
existingSecretSecretKey: harbor-admin-secret

persistence:
  enabled: true
  persistentVolumeClaim:
    registry:
      storageClass: longhorn-hdd
      size: 100Gi
    database:
      storageClass: longhorn-hdd
      size: 5Gi
    redis:
      storageClass: longhorn-hdd
      size: 1Gi
    trivy:
      storageClass: longhorn-hdd
      size: 5Gi

trivy:
  enabled: true

nodeSelector:
  zone: cicd

# Internal components
database:
  type: internal
redis:
  type: internal
```

Note: Review `helm show values harbor/harbor` during implementation for exact key names for `existingSecretAdminPassword` — Harbor chart versions vary.

**Step 5: Create ArgoCD Application CRs**

Create `apps/root/templates/harbor.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: harbor
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://helm.goharbor.io
      chart: harbor
      targetRevision: "1.16.0"
      helm:
        releaseName: harbor
        valueFiles:
          - $values/apps/harbor/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: harbor
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

Create `apps/root/templates/harbor-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: harbor-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/harbor/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: harbor
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

Pin `targetRevision` to latest stable at implementation time.

**Step 6: Configure containerd mirrors on all nodes**

Create a cluster-wide Talos machine patch so all nodes pull from Harbor:

```yaml
# patches/phase15-cicd-zone/containerd-harbor-mirror.yaml
metadata:
    namespace: default
    type: ConfigPatches.omni.sidero.dev
    id: 300-containerd-harbor-mirror
    labels:
        omni.sidero.dev/cluster: frank
spec:
    data: |
        machine:
            registries:
                mirrors:
                    harbor.frank.local:
                        endpoints:
                            - https://192.168.55.210
                config:
                    "192.168.55.210":
                        tls:
                            insecureSkipVerify: true
```

Note: `insecureSkipVerify` because Harbor uses a self-signed cert. Replace with proper CA trust if cert-manager issues a real cert later.

**Step 7: Commit**

```bash
git add apps/harbor/ apps/root/templates/harbor.yaml apps/root/templates/harbor-extras.yaml patches/phase15-cicd-zone/containerd-harbor-mirror.yaml
git commit -m "feat(phase15): add Harbor container registry with containerd mirrors"
```

**Step 8: Push and verify**

```bash
git push
# Wait for ArgoCD sync + Talos patch apply (nodes will reboot for containerd config)
argocd app get harbor --port-forward --port-forward-namespace argocd
kubectl get pods -n harbor
# Expect: harbor-core, harbor-registry, harbor-database, harbor-redis, harbor-trivy Running
curl -sk https://192.168.55.210/api/v2.0/health
# Expect: {"status":"healthy"}
```

---

## Task 5: n8n Workflow Orchestrator

**Files:**
- Create: `apps/n8n/values.yaml`
- Create: `apps/n8n/manifests/externalsecret-n8n.yaml`
- Create: `apps/root/templates/n8n.yaml`
- Create: `apps/root/templates/n8n-extras.yaml`

**Step 1: Research n8n Helm chart**

```bash
helm repo add n8n https://n8n-io.github.io/n8n-helm/
# OR the 8gears chart:
helm repo add open-8gears https://8gears.container-registry.com/chartrepo/library
helm show values open-8gears/n8n > /tmp/n8n-defaults.yaml
```

Determine which chart is more actively maintained at implementation time. Both are viable.

**Step 2: Create Infisical secrets**

```yaml
# manual-operation
id: phase15-n8n-infisical-secrets
phase: 15
app: n8n
plan: docs/superpowers/plans/2026-03-10-phase15-coding-agent-infrastructure.md
when: "Before deploying n8n"
why_manual: "Infisical secret creation requires UI/API interaction"
commands:
  - "Create in Infisical: N8N_ENCRYPTION_KEY (generate 32-char random string)"
verify:
  - "Infisical UI → Secrets → N8N_ENCRYPTION_KEY exists"
status: pending
```

**Step 3: Create ExternalSecret**

Create `apps/n8n/manifests/externalsecret-n8n.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: n8n-secrets
  namespace: n8n
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: n8n-secrets
    creationPolicy: Owner
  data:
    - secretKey: N8N_ENCRYPTION_KEY
      remoteRef:
        key: N8N_ENCRYPTION_KEY
```

**Step 4: Create Helm values**

Create `apps/n8n/values.yaml`:

```yaml
# n8n — workflow automation and agent orchestration dashboard
# Exposed at 192.168.55.208:5678
# Runs on minis (Core zone) for reliability

n8n:
  encryption_key:
    existingSecret: n8n-secrets
    existingSecretKey: N8N_ENCRYPTION_KEY

config:
  generic:
    WEBHOOK_URL: http://192.168.55.208:5678/
    N8N_HOST: 192.168.55.208
    N8N_PORT: "5678"
    N8N_PROTOCOL: http
    EXECUTIONS_MODE: regular
    # Enable Execute Command node for K8s Job creation
    NODES_INCLUDE: "n8n-nodes-base.executeCommand"

service:
  type: LoadBalancer
  port: 5678
  annotations:
    lbipam.cilium.io/ips: "192.168.55.208"

persistence:
  enabled: true
  size: 5Gi
  storageClass: longhorn

postgresql:
  enabled: true
  primary:
    persistence:
      enabled: true
      size: 5Gi
      storageClass: longhorn
```

Note: Chart value structure varies between the official n8n chart and 8gears chart. Adjust key names during implementation based on which chart is selected.

**Step 5: Create ArgoCD Application CRs**

Create `apps/root/templates/n8n.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: n8n
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://n8n-io.github.io/n8n-helm/
      chart: n8n
      targetRevision: "1.0.0"
      helm:
        releaseName: n8n
        valueFiles:
          - $values/apps/n8n/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: n8n
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

Create `apps/root/templates/n8n-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: n8n-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/n8n/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: n8n
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

Pin `targetRevision` to latest stable at implementation time.

**Step 6: Commit**

```bash
git add apps/n8n/ apps/root/templates/n8n.yaml apps/root/templates/n8n-extras.yaml
git commit -m "feat(phase15): add n8n workflow orchestrator"
```

**Step 7: Push and verify**

```bash
git push
argocd app get n8n --port-forward --port-forward-namespace argocd
kubectl get pods -n n8n
# Expect: n8n-0 Running, n8n-postgresql-0 Running
curl -s http://192.168.55.208:5678/healthz
# Expect: {"status":"ok"}
# Open http://192.168.55.208:5678 in browser — n8n setup wizard should appear
```

---

## Task 6: Aider Job Template

**Files:**
- Create: `apps/aider/manifests/namespace.yaml`
- Create: `apps/aider/manifests/externalsecret-aider.yaml`
- Create: `apps/aider/manifests/configmap-aider.yaml`
- Create: `apps/aider/manifests/serviceaccount.yaml`
- Create: `apps/aider/manifests/role.yaml`
- Create: `apps/aider/manifests/job-template.yaml`
- Create: `apps/root/templates/aider.yaml`

**Step 1: Create Infisical secrets**

```yaml
# manual-operation
id: phase15-aider-infisical-secrets
phase: 15
app: aider
plan: docs/superpowers/plans/2026-03-10-phase15-coding-agent-infrastructure.md
when: "Before deploying Aider resources"
why_manual: "Infisical secret creation + LiteLLM key generation"
commands:
  - "Generate LiteLLM virtual key: curl -X POST http://192.168.55.206:4000/key/generate -H 'Authorization: Bearer <MASTER_KEY>' -d '{\"key_alias\": \"aider\"}'"
  - "Store in Infisical: AIDER_LITELLM_KEY (the generated key)"
  - "Generate Gitea API token for the Aider service account in Gitea UI"
  - "Store in Infisical: AIDER_GITEA_TOKEN"
verify:
  - "Infisical UI → Secrets → AIDER_LITELLM_KEY exists"
  - "Infisical UI → Secrets → AIDER_GITEA_TOKEN exists"
status: pending
```

**Step 2: Create namespace**

Create `apps/aider/manifests/namespace.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: aider
```

**Step 3: Create ExternalSecret**

Create `apps/aider/manifests/externalsecret-aider.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: aider-secrets
  namespace: aider
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: aider-secrets
    creationPolicy: Owner
  data:
    - secretKey: OPENAI_API_KEY
      remoteRef:
        key: AIDER_LITELLM_KEY
    - secretKey: GITEA_TOKEN
      remoteRef:
        key: AIDER_GITEA_TOKEN
```

**Step 4: Create ConfigMap**

Create `apps/aider/manifests/configmap-aider.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: aider-config
  namespace: aider
data:
  OPENAI_API_BASE: "http://litellm.litellm.svc.cluster.local:4000/v1"
  AIDER_MODEL: "openai/qwen3.5"
  AIDER_YES: "true"
  AIDER_AUTO_COMMITS: "true"
  AIDER_NO_STREAM: "true"
  AIDER_NO_PRETTY: "true"
  GITEA_URL: "http://gitea-http.gitea.svc.cluster.local:3000"
  GIT_AUTHOR_NAME: "Aider Agent"
  GIT_AUTHOR_EMAIL: "aider@frank.local"
  GIT_COMMITTER_NAME: "Aider Agent"
  GIT_COMMITTER_EMAIL: "aider@frank.local"
```

**Step 5: Create Job template**

Create `apps/aider/manifests/job-template.yaml`:

```yaml
# This is a TEMPLATE — not applied directly by ArgoCD.
# n8n creates Jobs from this template, substituting REPO_URL, BRANCH, and TASK.
# Stored here for version control and reference.
#
# n8n substitutes: {{REPO_URL}}, {{BRANCH}}, {{TASK}}, {{JOB_NAME}}
apiVersion: batch/v1
kind: Job
metadata:
  name: "aider-{{JOB_NAME}}"
  namespace: aider
  labels:
    app: aider
    managed-by: n8n
spec:
  ttlSecondsAfterFinished: 86400  # cleanup after 24h
  backoffLimit: 0  # no retries — fail fast
  template:
    spec:
      nodeSelector:
        kubernetes.io/hostname: gpu-1
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      restartPolicy: Never
      initContainers:
        - name: git-clone
          image: alpine/git:latest
          command: ["sh", "-c"]
          args:
            - |
              git clone --branch {{BRANCH}} \
                http://aider:$(GITEA_TOKEN)@gitea-http.gitea.svc.cluster.local:3000/{{REPO_URL}}.git \
                /workspace
          envFrom:
            - secretRef:
                name: aider-secrets
          volumeMounts:
            - name: workspace
              mountPath: /workspace
      containers:
        - name: aider
          image: paulgauthier/aider-full:latest
          workingDir: /workspace
          command: ["sh", "-c"]
          args:
            - |
              git config user.name "$GIT_AUTHOR_NAME"
              git config user.email "$GIT_AUTHOR_EMAIL"
              git checkout -b aider/{{JOB_NAME}}

              aider --message "{{TASK}}"

              # Push branch and create PR via Gitea API
              git push origin aider/{{JOB_NAME}}
              curl -s -X POST \
                "$GITEA_URL/api/v1/repos/{{REPO_URL}}/pulls" \
                -H "Authorization: token $(cat /secrets/GITEA_TOKEN)" \
                -H "Content-Type: application/json" \
                -d "{
                  \"title\": \"[Aider] {{TASK}}\",
                  \"head\": \"aider/{{JOB_NAME}}\",
                  \"base\": \"{{BRANCH}}\"
                }"
          envFrom:
            - configMapRef:
                name: aider-config
            - secretRef:
                name: aider-secrets
          volumeMounts:
            - name: workspace
              mountPath: /workspace
          resources:
            requests:
              cpu: 2000m
              memory: 4Gi
            limits:
              memory: 8Gi
      volumes:
        - name: workspace
          emptyDir:
            sizeLimit: 5Gi
```

**Step 6: Create ArgoCD Application**

Create `apps/root/templates/aider.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: aider
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/aider/manifests
    directory:
      exclude: "job-template.yaml"
  destination:
    server: {{ .Values.destination.server }}
    namespace: aider
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

Note: `job-template.yaml` is excluded from ArgoCD sync — it's a reference template, not a live resource. n8n creates actual Jobs via the K8s API.

**Step 7: Commit**

```bash
git add apps/aider/ apps/root/templates/aider.yaml
git commit -m "feat(phase15): add Aider coding agent Job template and config"
```

**Step 8: Push and verify**

```bash
git push
argocd app get aider --port-forward --port-forward-namespace argocd
kubectl get configmap,externalsecret -n aider
# Expect: aider-config ConfigMap, aider-secrets ExternalSecret (SecretSynced)
```

**Step 9: Test a manual Aider Job**

Create a test repo in Gitea first, then:

```bash
# Substitute template vars manually for a test run
kubectl create job aider-test --namespace aider \
  --from=jobs/none -- echo "test"
# Better: copy job-template.yaml, substitute vars, apply manually
# This validates: git clone, aider execution, PR creation
```

Verify:
- Job completes successfully
- Branch pushed to Gitea
- PR created in Gitea UI

---

## Task 7: n8n Workflow — Aider Integration

**Files:**
- Create: `apps/n8n/manifests/rbac-job-creator.yaml`
- n8n workflow created via UI, then exported to `apps/n8n/workflows/aider-task.json`

**Step 1: Create RBAC for n8n to create Jobs**

Create `apps/n8n/manifests/rbac-job-creator.yaml`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: n8n-job-creator
  namespace: n8n
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: aider-job-manager
  namespace: aider
rules:
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["create", "get", "list", "watch", "delete"]
  - apiGroups: [""]
    resources: ["pods", "pods/log"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: n8n-aider-job-manager
  namespace: aider
subjects:
  - kind: ServiceAccount
    name: n8n-job-creator
    namespace: n8n
roleRef:
  kind: Role
  name: aider-job-manager
  apiGroup: rbac.authorization.k8s.io
```

**Step 2: Build the n8n workflow via UI**

Open n8n at `http://192.168.55.208:5678` and create the workflow:

1. **Trigger node** — Webhook (receives `{repo, branch, task}` payload)
2. **Set node** — Generate job name from timestamp + sanitized task
3. **HTTP Request node** — POST to K8s API (`https://kubernetes.default.svc/apis/batch/v1/namespaces/aider/jobs`) with the Job manifest (templated from `job-template.yaml` pattern)
4. **Wait node** — Poll job status every 30s
5. **IF node** — Check job succeeded or failed
6. **HTTP Request node** — Send Telegram notification with result + PR link

```yaml
# manual-operation
id: phase15-n8n-workflow-setup
phase: 15
app: n8n
plan: docs/superpowers/plans/2026-03-10-phase15-coding-agent-infrastructure.md
when: "After n8n and Aider are both deployed and verified"
why_manual: "Initial workflow creation is done via n8n UI, then exported to JSON"
commands:
  - "Create workflow in n8n UI following the pattern above"
  - "Test with a sample task"
  - "Export workflow JSON: n8n UI → Workflow → Download"
  - "Save to apps/n8n/workflows/aider-task.json in the repo"
verify:
  - "Trigger webhook with test payload → Aider Job created → PR opened in Gitea"
status: pending
```

**Step 3: Commit RBAC and exported workflow**

```bash
git add apps/n8n/manifests/rbac-job-creator.yaml
git add apps/n8n/workflows/  # after exporting from UI
git commit -m "feat(phase15): add n8n-to-Aider workflow and RBAC"
```

---

## Task 8: End-to-End Integration Test

**Step 1: Create a test project in Gitea**

1. Gitea UI → New Repository: `test-aider-project`
2. Add a simple `README.md` and a Python file with an obvious bug
3. Create a Gitea Actions workflow (`.gitea/workflows/test.yaml`) that runs `python -m pytest`

**Step 2: Trigger via n8n**

```bash
curl -X POST http://192.168.55.208:5678/webhook/aider-task \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "gitea_admin/test-aider-project",
    "branch": "main",
    "task": "Fix the bug in app.py — the function returns the wrong value"
  }'
```

**Step 3: Verify the full pipeline**

1. n8n dashboard: workflow execution shows success
2. Gitea: new branch `aider/<job-name>` exists
3. Gitea: PR created with descriptive title
4. Gitea Actions: CI ran on the PR branch
5. PR shows green check (tests pass after Aider's fix)

**Step 4: Document results**

Note any issues, workarounds, or configuration adjustments needed. Update values files and re-commit if changes were required.

---

## Summary of Manual Operations

| ID | Phase | When | What |
|----|-------|------|------|
| `phase15-longhorn-disk-tags` | 15 | Before Task 1.2 | Tag HDD disks in Longhorn UI |
| `phase15-gitea-infisical-secrets` | 15 | Before Task 2 | Create Gitea admin creds in Infisical |
| `phase15-gitea-runner-token` | 15 | After Task 2 | Generate runner registration token |
| `phase15-harbor-infisical-secrets` | 15 | Before Task 4 | Create Harbor admin creds in Infisical |
| `phase15-n8n-infisical-secrets` | 15 | Before Task 5 | Create n8n encryption key in Infisical |
| `phase15-aider-infisical-secrets` | 15 | Before Task 6 | Create Aider LiteLLM key + Gitea token |
| `phase15-n8n-workflow-setup` | 15 | After Tasks 5+6 | Build n8n workflow via UI |

---

## Open Items for Implementation

- **Helm chart versions**: All `targetRevision` values are placeholders. Pin to latest stable at implementation time.
- **n8n chart selection**: Choose between official n8n chart and 8gears chart based on maintenance status.
- **DinD on Talos**: Test privileged DinD sidecar on pc-1/pc-2. If it fails, explore host-mode runners or Kaniko.
- **Harbor TLS**: Self-signed cert with `insecureSkipVerify` is a starting point. Consider cert-manager ClusterIssuer later.
- **pc-1/pc-2 disk paths**: Replace `/var/mnt/hdd1` with actual mount paths after Talos disk audit.
- **Gitea SSH port**: May conflict with Talos node SSH. Test and adjust if needed.
