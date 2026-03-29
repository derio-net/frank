# CI/CD Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a K8s-native CI/CD platform — Gitea (git forge mirroring GitHub), Tekton (pipeline engine), Zot (OCI registry) with cosign signing — all on pc-1.

**Architecture:** Gitea mirrors GitHub repos locally. Tekton Triggers receive Gitea webhooks and create PipelineRuns. Pipelines clone, test, build images, push to Zot, sign with cosign, and report status back to Gitea PRs. All components are ArgoCD-managed following Frank's App-of-Apps pattern.

**Tech Stack:** ArgoCD, Helm, Longhorn, Cilium L2, Infisical + ExternalSecrets, Tekton Pipelines/Triggers/Dashboard, Gitea, Zot, cosign, cert-manager

**Design doc:** `docs/superpowers/specs/2026-03-29--cicd--platform-design.md`
**Status:** Not Started

---

## Prerequisites

- pc-1 is online and showing `Ready` in `kubectl get nodes`
- Existing infrastructure operational: Longhorn, Cilium L2, Infisical, ExternalSecrets, cert-manager, Authentik
- IPs `.209`, `.210`, `.217` are unallocated (verified 2026-03-29)

---

## Task 1: StorageClass and Node Labels

**Files:**
- Create: `apps/longhorn/manifests/storageclass-longhorn-cicd.yaml`

- [ ] **Step 1: Create the StorageClass manifest**

Create `apps/longhorn/manifests/storageclass-longhorn-cicd.yaml`:

```yaml
# Longhorn-CICD StorageClass — single replica for pc-1 CI/CD workloads
# Used by: Gitea repos, Zot image blobs, Tekton pipeline workspaces
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
  nodeSelector: "kubernetes.io/hostname:pc-1"
```

- [ ] **Step 2: Commit**

```bash
git add apps/longhorn/manifests/storageclass-longhorn-cicd.yaml
git commit -m "feat(cicd): add longhorn-cicd StorageClass for single-replica CI/CD PVCs"
```

- [ ] **Step 3: Push and verify StorageClass syncs**

```bash
git push
# Wait for ArgoCD longhorn-extras to sync
kubectl get storageclass longhorn-cicd
# Expect: longhorn-cicd listed with provisioner driver.longhorn.io
```

- [ ] **Step 4: Add role=cicd label to pc-1 via Omni**

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

Verify:

```bash
kubectl get node pc-1 --show-labels | grep role=cicd
# Expect: role=cicd in the label list
```

---

## Task 2: Gitea Deployment

**Files:**
- Create: `apps/gitea/values.yaml`
- Create: `apps/gitea/manifests/externalsecret-gitea.yaml`
- Create: `apps/root/templates/gitea.yaml`
- Create: `apps/root/templates/gitea-extras.yaml`

- [ ] **Step 1: Create Infisical secrets and Authentik OIDC provider**

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
id: cicd-authentik-gitea-oidc
layer: cicd
app: gitea
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before Gitea deploy — OIDC provider must exist in Authentik"
why_manual: "Authentik provider/application creation requires API token"
commands:
  - "Run: bash scripts/tmp/setup-authentik-cicd-oidc.sh (creates both Gitea and Zot providers+apps)"
  - "Store printed GITEA_OIDC_CLIENT_SECRET in Infisical"
verify:
  - "curl -H 'Authorization: Bearer $AK_TOKEN' http://192.168.55.211:9000/api/v3/providers/oauth2/ | jq '.results[].name' — includes Gitea"
  - "Infisical → GITEA_OIDC_CLIENT_SECRET exists"
status: done
```

- [ ] **Step 2: Research Gitea Helm chart**

```bash
helm repo add gitea-charts https://dl.gitea.com/charts/
helm show values gitea-charts/gitea > /tmp/gitea-defaults.yaml
```

Review `/tmp/gitea-defaults.yaml` for: `persistence`, `postgresql`, `gitea.config`, `service`, `nodeSelector`, `gitea.admin`, and `gitea.oauth`. Find the exact key paths for OIDC config and admin secret. Also check: `helm search repo gitea-charts/gitea --versions | head -5` to pin the chart version.

- [ ] **Step 3: Create ExternalSecret**

Create `apps/gitea/manifests/externalsecret-gitea.yaml`:

```yaml
# Syncs Gitea secrets from Infisical.
# admin-password: bootstrap admin account
# oidc-client-secret: Authentik OIDC integration
# github-mirror-token: GitHub PAT for pull mirrors
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: gitea-secrets
  namespace: gitea
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: gitea-secrets
    creationPolicy: Owner
  data:
    - secretKey: admin-password
      remoteRef:
        key: GITEA_ADMIN_PASSWORD
    - secretKey: oidc-client-secret
      remoteRef:
        key: GITEA_OIDC_CLIENT_SECRET
    - secretKey: github-mirror-token
      remoteRef:
        key: GITHUB_MIRROR_TOKEN
```

- [ ] **Step 4: Create Helm values**

Create `apps/gitea/values.yaml`. Adjust key paths based on Step 2 research. This is the target structure:

```yaml
# Gitea — self-hosted Git forge, GitHub mirror
# Exposed at 192.168.55.209:3000 (HTTP) and :2222 (SSH)
# Runs on pc-1 with Longhorn-CICD storage (single replica)

gitea:
  admin:
    existingSecret: gitea-secrets
    # Keys: admin-password (from ExternalSecret)

  config:
    server:
      DOMAIN: 192.168.55.209
      ROOT_URL: http://192.168.55.209:3000/
      SSH_DOMAIN: 192.168.55.209
      SSH_PORT: 2222
      LFS_START_SERVER: true

    oauth2:
      ENABLE: true

    openid:
      ENABLE_OPENID_SIGNIN: true

    service:
      DISABLE_REGISTRATION: false
      ALLOW_ONLY_EXTERNAL_REGISTRATION: true
      SHOW_REGISTRATION_BUTTON: false

    repository:
      DEFAULT_BRANCH: main

    mirror:
      ENABLED: true
      DEFAULT_INTERVAL: 10m

  oauth:
    - name: authentik
      provider: openidConnect
      existingSecret: gitea-secrets
      # Keys will depend on chart version — research in Step 2
      # Typically: key (client ID) and secret (client secret)
      autoDiscoverUrl: "http://192.168.55.211:9000/application/o/gitea/.well-known/openid-configuration"
      iconUrl: "https://goauthentik.io/img/icon.png"
      scopes: "openid email profile"
      groupClaimName: "groups"
      adminGroup: "authentik Admins"

service:
  http:
    type: LoadBalancer
    port: 3000
    annotations:
      lbipam.cilium.io/ips: "192.168.55.209"
  ssh:
    type: LoadBalancer
    port: 2222
    annotations:
      lbipam.cilium.io/ips: "192.168.55.209"

persistence:
  enabled: true
  size: 10Gi
  storageClass: longhorn-cicd
  accessModes:
    - ReadWriteOnce

strategy:
  type: Recreate

# SQLite — no PostgreSQL needed for single-user homelab
postgresql:
  enabled: false

postgresql-ha:
  enabled: false

nodeSelector:
  kubernetes.io/hostname: pc-1
```

Note: The `gitea.oauth` section syntax varies between chart versions. Key points to verify in Step 2:
- The `existingSecret` key for OAuth may use `key` (client ID) and `secret` (client secret) as subkeys
- The client ID is not sensitive — it can be hardcoded in values.yaml if the chart supports separate `key`/`existingSecret` fields. If the chart requires both in the secret, add `GITEA_OIDC_CLIENT_ID` to Infisical and the ExternalSecret
- The Authentik auto-discovery URL follows the pattern `http://<authentik-ip>:9000/application/o/<slug>/.well-known/openid-configuration`

- [ ] **Step 5: Create ArgoCD Application CR for Helm chart**

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
      targetRevision: "11.0.0"  # Pin to latest stable — verify in Step 2
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

- [ ] **Step 6: Create ArgoCD Application CR for extras (manifests)**

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

- [ ] **Step 7: Commit**

```bash
git add apps/gitea/ apps/root/templates/gitea.yaml apps/root/templates/gitea-extras.yaml
git commit -m "feat(cicd): add Gitea git forge with Authentik OIDC"
```

- [ ] **Step 8: Push and verify**

```bash
git push
# Wait for ArgoCD sync
argocd app get gitea --port-forward --port-forward-namespace argocd
argocd app get gitea-extras --port-forward --port-forward-namespace argocd
kubectl get pods -n gitea
# Expect: gitea-0 Running (or gitea-<hash> if Deployment, not StatefulSet)
curl -s http://192.168.55.209:3000/api/v1/version
# Expect: {"version":"..."}
```

- [ ] **Step 9: Verify Authentik OIDC login**

1. Open `http://192.168.55.209:3000` in a browser
2. Click "Sign in with authentik" (or similar OIDC button)
3. Authenticate via Authentik
4. Verify account is auto-created in Gitea

If OIDC fails, check:
- Authentik provider redirect URI matches exactly
- Gitea logs: `kubectl logs -n gitea deploy/gitea` (or statefulset)
- Auto-discovery URL is reachable from within the Gitea pod: `kubectl exec -n gitea <pod> -- wget -qO- http://192.168.55.211:9000/application/o/gitea/.well-known/openid-configuration`

---

## Task 3: Gitea Post-Deploy Configuration

- [ ] **Step 1: Create service account and API token**

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

- [ ] **Step 2: Mirror test repo from GitHub**

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

- [ ] **Step 3: Verify SSH clone works**

```bash
# From a machine that can reach pc-1
GIT_SSH_COMMAND="ssh -p 2222" git clone git@192.168.55.209:<owner>/<test-repo>.git /tmp/test-clone
# Expect: successful clone
rm -rf /tmp/test-clone
```

---

## Task 4: Tekton Core Deployment

**Files:**
- Create: `apps/tekton/vendor/pipelines/release.yaml` (vendored)
- Create: `apps/tekton/vendor/dashboard/release.yaml` (vendored)
- Create: `apps/tekton/manifests/dashboard-service.yaml`
- Create: `apps/root/templates/tekton-pipelines.yaml`
- Create: `apps/root/templates/tekton-dashboard.yaml`

- [ ] **Step 1: Download and vendor Tekton Pipelines release YAML**

```bash
mkdir -p apps/tekton/vendor/pipelines apps/tekton/vendor/triggers apps/tekton/vendor/dashboard

# Check latest stable versions
curl -sL https://api.github.com/repos/tektoncd/pipeline/releases/latest | jq -r '.tag_name'
# Note the version (e.g., v0.65.0)

# Download and vendor
TEKTON_PIPELINE_VERSION="v0.65.0"  # Replace with actual latest
curl -sL "https://storage.googleapis.com/tekton-releases/pipeline/previous/${TEKTON_PIPELINE_VERSION}/release.yaml" \
  -o apps/tekton/vendor/pipelines/release.yaml

# Verify the file is valid YAML and contains expected resources
grep -c "^kind:" apps/tekton/vendor/pipelines/release.yaml
# Expect: 50+ resources (CRDs, Deployments, Services, etc.)
```

- [ ] **Step 2: Download and vendor Tekton Dashboard release YAML**

```bash
TEKTON_DASHBOARD_VERSION=$(curl -sL https://api.github.com/repos/tektoncd/dashboard/releases/latest | jq -r '.tag_name')
echo "Dashboard version: $TEKTON_DASHBOARD_VERSION"

curl -sL "https://storage.googleapis.com/tekton-releases/dashboard/previous/${TEKTON_DASHBOARD_VERSION}/release.yaml" \
  -o apps/tekton/vendor/dashboard/release.yaml

grep -c "^kind:" apps/tekton/vendor/dashboard/release.yaml
# Expect: 15+ resources
```

- [ ] **Step 3: Create Dashboard LoadBalancer Service**

Create `apps/tekton/manifests/dashboard-service.yaml`:

```yaml
# Tekton Dashboard — exposed on 192.168.55.217:9097
# Overrides the ClusterIP service from the vendored release YAML
apiVersion: v1
kind: Service
metadata:
  name: tekton-dashboard-lb
  namespace: tekton-pipelines
  annotations:
    lbipam.cilium.io/ips: "192.168.55.217"
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/component: dashboard
    app.kubernetes.io/part-of: tekton-dashboard
  ports:
    - name: http
      port: 9097
      targetPort: 9097
      protocol: TCP
```

Note: Check the vendored Dashboard YAML for the exact label selectors (`app.kubernetes.io/component` and `app.kubernetes.io/part-of`). Adjust `selector` if they differ.

- [ ] **Step 4: Create ArgoCD Application for Tekton Pipelines**

Create `apps/root/templates/tekton-pipelines.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: tekton-pipelines
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/tekton/vendor/pipelines
  destination:
    server: {{ .Values.destination.server }}
    namespace: tekton-pipelines
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 5: Create ArgoCD Application for Tekton Dashboard**

Create `apps/root/templates/tekton-dashboard.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: tekton-dashboard
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/tekton/vendor/dashboard
  destination:
    server: {{ .Values.destination.server }}
    namespace: tekton-pipelines
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 6: Create ArgoCD Application for Tekton extras (manifests)**

Create `apps/root/templates/tekton-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: tekton-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/tekton
    directory:
      recurse: true
      exclude: "vendor/**"
  destination:
    server: {{ .Values.destination.server }}
    namespace: tekton-pipelines
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

Note: `directory.recurse: true` with `exclude: "vendor/**"` picks up all YAML in `apps/tekton/manifests/`, `apps/tekton/pipelines/`, `apps/tekton/tasks/`, and `apps/tekton/triggers/` while excluding the vendored release YAMLs (those are managed by separate ArgoCD apps).

- [ ] **Step 7: Commit**

```bash
git add apps/tekton/ apps/root/templates/tekton-pipelines.yaml apps/root/templates/tekton-dashboard.yaml apps/root/templates/tekton-extras.yaml
git commit -m "feat(cicd): add Tekton Pipelines and Dashboard (vendored release YAMLs)"
```

- [ ] **Step 8: Push and verify**

```bash
git push
# Wait for ArgoCD sync — this may take a minute due to CRD creation
argocd app get tekton-pipelines --port-forward --port-forward-namespace argocd
argocd app get tekton-dashboard --port-forward --port-forward-namespace argocd
kubectl get pods -n tekton-pipelines
# Expect: tekton-pipelines-controller, tekton-pipelines-webhook, tekton-dashboard Running
curl -s http://192.168.55.217:9097
# Expect: Tekton Dashboard HTML
```

- [ ] **Step 9: Run a manual hello-world PipelineRun**

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  generateName: hello-world-
  namespace: tekton-pipelines
spec:
  pipelineSpec:
    tasks:
      - name: hello
        taskSpec:
          steps:
            - name: echo
              image: alpine:3
              command: ["echo"]
              args: ["Hello from Tekton on Frank!"]
EOF

# Watch the PipelineRun
kubectl get pipelinerun -n tekton-pipelines -w
# Expect: Succeeded after ~30s

# Check logs
tkn pipelinerun logs -n tekton-pipelines --last
# Or: kubectl logs -n tekton-pipelines <pod-name> -c step-echo
# Expect: "Hello from Tekton on Frank!"
```

If `tkn` CLI is not installed: `brew install tektoncd-cli` (or download from GitHub releases).

---

## Task 5: Tekton Triggers Deployment

**Files:**
- Create: `apps/tekton/vendor/triggers/release.yaml` (vendored)
- Create: `apps/tekton/triggers/eventlistener.yaml`
- Create: `apps/tekton/triggers/triggerbinding.yaml`
- Create: `apps/tekton/triggers/triggertemplate.yaml`
- Create: `apps/tekton/manifests/externalsecret-webhook.yaml`
- Create: `apps/root/templates/tekton-triggers.yaml`

- [ ] **Step 1: Create Infisical webhook secret**

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

- [ ] **Step 2: Download and vendor Tekton Triggers release YAML**

```bash
TEKTON_TRIGGERS_VERSION=$(curl -sL https://api.github.com/repos/tektoncd/triggers/releases/latest | jq -r '.tag_name')
echo "Triggers version: $TEKTON_TRIGGERS_VERSION"

curl -sL "https://storage.googleapis.com/tekton-releases/triggers/previous/${TEKTON_TRIGGERS_VERSION}/release.yaml" \
  -o apps/tekton/vendor/triggers/release.yaml

# Also download the interceptors (required for CEL filtering)
curl -sL "https://storage.googleapis.com/tekton-releases/triggers/previous/${TEKTON_TRIGGERS_VERSION}/interceptors.yaml" \
  -o apps/tekton/vendor/triggers/interceptors.yaml

grep -c "^kind:" apps/tekton/vendor/triggers/release.yaml
# Expect: 15+ resources
```

- [ ] **Step 3: Create ExternalSecret for webhook secret**

Create `apps/tekton/manifests/externalsecret-webhook.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: gitea-webhook-secret
  namespace: tekton-pipelines
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: gitea-webhook-secret
    creationPolicy: Owner
  data:
    - secretKey: secret
      remoteRef:
        key: GITEA_WEBHOOK_SECRET
```

- [ ] **Step 4: Create ExternalSecret for Gitea API token**

Create `apps/tekton/manifests/externalsecret-gitea-token.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: gitea-api-token
  namespace: tekton-pipelines
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: gitea-api-token
    creationPolicy: Owner
  data:
    - secretKey: token
      remoteRef:
        key: GITEA_API_TOKEN
```

- [ ] **Step 5: Create TriggerBinding**

Create `apps/tekton/triggers/triggerbinding.yaml`:

```yaml
# Extracts fields from Gitea webhook payloads
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerBinding
metadata:
  name: gitea-push-binding
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-url
      value: $(body.repository.clone_url)
    - name: revision
      value: $(body.after)
    - name: repo-full-name
      value: $(body.repository.full_name)
    - name: branch
      value: $(extensions.branch_name)
```

Note: Gitea webhook payload structure should be verified during implementation. The field paths may differ from GitHub's — check `https://gitea.com/gitea/gitea/wiki/Webhook` or inspect a test delivery payload from Gitea.

- [ ] **Step 6: Create TriggerTemplate**

Create `apps/tekton/triggers/triggertemplate.yaml`:

```yaml
# Creates a PipelineRun from Gitea webhook data
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: gitea-pipeline-template
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-url
    - name: revision
    - name: repo-full-name
    - name: branch
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: gitea-ci-
        namespace: tekton-pipelines
      spec:
        pipelineRef:
          name: gitea-ci
        params:
          - name: repo-url
            value: $(tt.params.repo-url)
          - name: revision
            value: $(tt.params.revision)
          - name: repo-full-name
            value: $(tt.params.repo-full-name)
          - name: branch
            value: $(tt.params.branch)
        workspaces:
          - name: shared-workspace
            volumeClaimTemplate:
              spec:
                accessModes:
                  - ReadWriteOnce
                storageClassName: longhorn-cicd
                resources:
                  requests:
                    storage: 1Gi
```

- [ ] **Step 7: Create EventListener**

Create `apps/tekton/triggers/eventlistener.yaml`:

```yaml
# Receives Gitea webhooks, validates HMAC signature, routes to trigger
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata:
  name: gitea-listener
  namespace: tekton-pipelines
spec:
  serviceAccountName: tekton-triggers-sa
  triggers:
    - name: gitea-push
      interceptors:
        - ref:
            name: "github"
          params:
            - name: "secretRef"
              value:
                secretName: gitea-webhook-secret
                secretKey: secret
            - name: "eventTypes"
              value: ["push"]
        - ref:
            name: "cel"
          params:
            - name: "overlays"
              value:
                - key: branch_name
                  expression: "body.ref.split('/')[2]"
        - ref:
            name: "cel"
          params:
            - name: "filter"
              value: >-
                extensions.branch_name != ''
      bindings:
        - ref: gitea-push-binding
      template:
        ref: gitea-pipeline-template
  resources:
    kubernetesResource:
      spec:
        template:
          spec:
            nodeSelector:
              kubernetes.io/hostname: pc-1
```

Note: Gitea webhook payloads use the same HMAC-SHA256 signature format as GitHub (`X-Hub-Signature-256` header). The built-in `github` interceptor validates this signature using the `secretRef`. If Gitea uses a different header name (`X-Gitea-Signature`), the `github` interceptor may not work — in that case, fall back to a CEL-based HMAC check or verify that the interceptor handles it. Test with a Gitea webhook delivery during Step 13.

- [ ] **Step 8: Create RBAC for Tekton Triggers**

The EventListener needs a ServiceAccount with permissions to create PipelineRuns. Check if the vendored Triggers release YAML already creates a `tekton-triggers-sa` ServiceAccount. If not, create one:

Create `apps/tekton/manifests/triggers-rbac.yaml`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: tekton-triggers-sa
  namespace: tekton-pipelines
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: tekton-triggers-binding
  namespace: tekton-pipelines
subjects:
  - kind: ServiceAccount
    name: tekton-triggers-sa
    namespace: tekton-pipelines
roleRef:
  kind: ClusterRole
  name: tekton-triggers-eventlistener-roles
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: tekton-triggers-binding
subjects:
  - kind: ServiceAccount
    name: tekton-triggers-sa
    namespace: tekton-pipelines
roleRef:
  kind: ClusterRole
  name: tekton-triggers-eventlistener-clusterroles
  apiGroup: rbac.authorization.k8s.io
```

Note: The ClusterRole names (`tekton-triggers-eventlistener-roles`, `tekton-triggers-eventlistener-clusterroles`) come from the vendored Triggers release YAML. Verify they exist: `grep "tekton-triggers-eventlistener" apps/tekton/vendor/triggers/release.yaml`.

- [ ] **Step 9: Create ArgoCD Application for Tekton Triggers**

Create `apps/root/templates/tekton-triggers.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: tekton-triggers
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/tekton/vendor/triggers
  destination:
    server: {{ .Values.destination.server }}
    namespace: tekton-pipelines
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 10: Commit**

```bash
git add apps/tekton/ apps/root/templates/tekton-triggers.yaml
git commit -m "feat(cicd): add Tekton Triggers with Gitea EventListener"
```

- [ ] **Step 11: Push and verify**

```bash
git push
argocd app get tekton-triggers --port-forward --port-forward-namespace argocd
kubectl get pods -n tekton-pipelines
# Expect: tekton-triggers-controller, tekton-triggers-core-interceptors Running
kubectl get eventlistener -n tekton-pipelines
# Expect: gitea-listener with ADDRESS
kubectl get svc -n tekton-pipelines | grep el-gitea-listener
# Expect: el-gitea-listener ClusterIP on port 8080
```

- [ ] **Step 12: Configure Gitea webhook**

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

- [ ] **Step 13: Test webhook triggers a PipelineRun**

Push a commit to the test repo (or use Gitea's "test delivery" button):

```bash
# After pushing a commit to the mirrored test repo
kubectl get pipelinerun -n tekton-pipelines
# Expect: a new gitea-ci-XXXXX PipelineRun (it will fail because the gitea-ci Pipeline doesn't exist yet — that's OK)
# The point is verifying the EventListener → TriggerBinding → TriggerTemplate chain works
```

If no PipelineRun is created, debug:
- Check EventListener pod logs: `kubectl logs -n tekton-pipelines -l app.kubernetes.io/part-of=tekton-triggers -c tekton-triggers-eventlistener`
- Check webhook delivery in Gitea UI → Webhooks → Recent Deliveries

---

## Task 6: Zot Registry Deployment

**Files:**
- Create: `apps/zot/values.yaml`
- Create: `apps/zot/manifests/externalsecret-zot.yaml`
- Create: `apps/zot/manifests/certificate.yaml`
- Create: `apps/zot/manifests/clusterissuer-selfsigned.yaml` (if not exists)
- Create: `apps/root/templates/zot.yaml`
- Create: `apps/root/templates/zot-extras.yaml`

- [ ] **Step 1: Create Infisical secrets and Authentik OIDC provider**

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
id: cicd-authentik-zot-oidc
layer: cicd
app: zot
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before Zot deploy — OIDC provider must exist in Authentik"
why_manual: "Authentik provider/application creation requires API token"
commands:
  - "Run: bash scripts/tmp/setup-authentik-cicd-oidc.sh (creates both Gitea and Zot providers+apps)"
  - "Store printed ZOT_OIDC_CLIENT_SECRET in Infisical"
verify:
  - "curl -H 'Authorization: Bearer $AK_TOKEN' http://192.168.55.211:9000/api/v3/providers/oauth2/ | jq '.results[].name' — includes Zot"
  - "Infisical → ZOT_OIDC_CLIENT_SECRET exists"
status: done
```

- [ ] **Step 2: Research Zot Helm chart**

```bash
helm repo add zotregistry https://zotregistry.dev/helm-charts/
helm show values zotregistry/zot > /tmp/zot-defaults.yaml
helm search repo zotregistry/zot --versions | head -5
```

Review `/tmp/zot-defaults.yaml` for: `persistence`, `service`, `configFiles`, TLS configuration, htpasswd auth, and OIDC settings.

- [ ] **Step 3: Create self-signed ClusterIssuer (if not exists)**

Check if a self-signed ClusterIssuer already exists:

```bash
kubectl get clusterissuer
```

If none exists, create `apps/zot/manifests/clusterissuer-selfsigned.yaml`:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-issuer
spec:
  selfSigned: {}
```

Note: This may be better placed in `apps/cert-manager/manifests/` if it's a cluster-wide resource. Check if there's an existing cert-manager extras app. If not, place it in `apps/zot/manifests/` for now and move later.

- [ ] **Step 4: Create Certificate for Zot TLS**

Create `apps/zot/manifests/certificate.yaml`:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: zot-tls
  namespace: zot
spec:
  secretName: zot-tls
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
  ipAddresses:
    - "192.168.55.210"
  dnsNames:
    - "zot.frank.local"
```

- [ ] **Step 5: Create ExternalSecret**

Create `apps/zot/manifests/externalsecret-zot.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: zot-secrets
  namespace: zot
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: zot-secrets
    creationPolicy: Owner
  data:
    - secretKey: push-password
      remoteRef:
        key: ZOT_PUSH_PASSWORD
    - secretKey: oidc-client-secret
      remoteRef:
        key: ZOT_OIDC_CLIENT_SECRET
```

- [ ] **Step 6: Create Helm values**

Create `apps/zot/values.yaml`. Adjust based on Step 2 research:

```yaml
# Zot — OCI container and artifact registry
# Exposed at 192.168.55.210:5000 (HTTPS)
# Runs on pc-1 with Longhorn-CICD storage

persistence:
  enabled: true
  storageClassName: longhorn-cicd
  size: 50Gi

# TLS via cert-manager
# Certificate is created in apps/zot/manifests/certificate.yaml
# The Zot chart should be configured to use the zot-tls secret

nodeSelector:
  kubernetes.io/hostname: pc-1
```

Note: The exact values structure for Zot depends heavily on the chart version. Key areas to configure from the chart research:
- `configFiles.config.json` — Zot's main config (storage, htpasswd, OIDC)
- TLS secret reference
- Service type and port
- The htpasswd file with the push user credential

The htpasswd entry for the push user must be generated:
```bash
htpasswd -nbB tekton-push "$(kubectl get secret zot-secrets -n zot -o jsonpath='{.data.push-password}' | base64 -d)"
```

This will need to be a ConfigMap or embedded in the Zot config. The exact approach depends on the chart.

- [ ] **Step 7: Create ArgoCD Application CRs**

Create `apps/root/templates/zot.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: zot
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://zotregistry.dev/helm-charts/
      chart: zot
      targetRevision: "0.1.0"  # Pin to latest stable — verify in Step 2
      helm:
        releaseName: zot
        valueFiles:
          - $values/apps/zot/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: zot
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

Create `apps/root/templates/zot-extras.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: zot-extras
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/zot/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: zot
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 8: Commit**

```bash
git add apps/zot/ apps/root/templates/zot.yaml apps/root/templates/zot-extras.yaml
git commit -m "feat(cicd): add Zot OCI registry with cert-manager TLS"
```

- [ ] **Step 9: Push and verify**

```bash
git push
argocd app get zot --port-forward --port-forward-namespace argocd
argocd app get zot-extras --port-forward --port-forward-namespace argocd
kubectl get pods -n zot
# Expect: zot-0 (or zot-<hash>) Running
kubectl get certificate -n zot
# Expect: zot-tls Ready=True
curl -sk https://192.168.55.210:5000/v2/
# Expect: {} or {"repositories":[]}
```

- [ ] **Step 10: Test image push/pull**

```bash
# Tag and push a test image
docker pull alpine:3
docker tag alpine:3 192.168.55.210:5000/test/alpine:latest
docker push 192.168.55.210:5000/test/alpine:latest
# Expect: successful push (may need docker login first with the htpasswd creds)

# Verify via API
curl -sk https://192.168.55.210:5000/v2/_catalog
# Expect: {"repositories":["test/alpine"]}
```

- [ ] **Step 11: Apply containerd mirror Talos patch**

```yaml
# manual-operation
id: cicd-talos-containerd-mirror
layer: cicd
app: zot
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "After Zot is deployed and verified"
why_manual: "Omni config patch requires UI or omnictl interaction; triggers node reboot"
commands:
  - "Apply Omni cluster-wide config patch with containerd mirror for 192.168.55.210:5000 (with or without insecureSkipVerify depending on cert-manager IP SAN support)"
  - "Verify nodes reboot and come back Ready"
verify:
  - "talosctl -n 192.168.55.21 get machineconfig -o yaml | grep 192.168.55.210"
  - "kubectl get nodes — all nodes Ready"
  - "crictl pull 192.168.55.210:5000/test/alpine:latest (on any node)"
status: pending
```

---

## Task 7: Pipeline Stage A — Clone, Test, Report Status

**Files:**
- Create: `apps/tekton/tasks/git-clone.yaml` (vendored from Tekton catalog)
- Create: `apps/tekton/tasks/run-tests.yaml`
- Create: `apps/tekton/tasks/gitea-status.yaml`
- Create: `apps/tekton/pipelines/gitea-ci.yaml`

- [ ] **Step 1: Vendor git-clone Task from Tekton catalog**

```bash
curl -sL "https://raw.githubusercontent.com/tektoncd/catalog/main/task/git-clone/0.9/git-clone.yaml" \
  -o apps/tekton/tasks/git-clone.yaml

# Verify
grep "^kind:" apps/tekton/tasks/git-clone.yaml
# Expect: Task
```

Note: Check the Tekton catalog for the latest version of git-clone. The URL path includes the version number.

- [ ] **Step 2: Create run-tests Task**

Create `apps/tekton/tasks/run-tests.yaml`:

```yaml
# Runs a configurable test command in the cloned workspace
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: run-tests
  namespace: tekton-pipelines
spec:
  params:
    - name: test-command
      type: string
      default: "echo 'No tests configured'"
      description: "Command to run for testing"
  workspaces:
    - name: source
      description: "The git repo"
  steps:
    - name: test
      image: alpine:3
      workingDir: $(workspaces.source.path)
      script: |
        #!/bin/sh
        set -e
        echo "Running tests..."
        $(params.test-command)
        echo "Tests passed."
```

- [ ] **Step 3: Create gitea-status Task**

Create `apps/tekton/tasks/gitea-status.yaml`:

```yaml
# Reports commit status (success/failure) back to Gitea PR
# Used in the `finally` block of pipelines
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: gitea-status
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-full-name
      type: string
      description: "Full repo name (e.g., owner/repo)"
    - name: revision
      type: string
      description: "Git commit SHA"
    - name: state
      type: string
      description: "success, pending, failure, or error"
    - name: description
      type: string
      default: "Tekton CI"
    - name: context
      type: string
      default: "tekton-ci"
    - name: gitea-url
      type: string
      default: "http://gitea-http.gitea.svc.cluster.local:3000"
  steps:
    - name: report
      image: alpine:3
      env:
        - name: GITEA_TOKEN
          valueFrom:
            secretKeyRef:
              name: gitea-api-token
              key: token
      script: |
        #!/bin/sh
        apk add --no-cache curl
        STATUS_URL="$(params.gitea-url)/api/v1/repos/$(params.repo-full-name)/statuses/$(params.revision)"
        curl -s -X POST "$STATUS_URL" \
          -H "Authorization: token $GITEA_TOKEN" \
          -H "Content-Type: application/json" \
          -d "{
            \"state\": \"$(params.state)\",
            \"description\": \"$(params.description)\",
            \"context\": \"$(params.context)\"
          }"
        echo "Reported status '$(params.state)' for $(params.revision)"
```

Note: The Gitea internal service name (`gitea-http.gitea.svc.cluster.local`) depends on the Helm chart's service naming. Verify after Gitea deployment: `kubectl get svc -n gitea`.

- [ ] **Step 4: Create the gitea-ci Pipeline**

Create `apps/tekton/pipelines/gitea-ci.yaml`:

```yaml
# Main CI pipeline triggered by Gitea webhooks
# Stage A: clone → test → report status
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: gitea-ci
  namespace: tekton-pipelines
spec:
  params:
    - name: repo-url
      type: string
    - name: revision
      type: string
    - name: repo-full-name
      type: string
    - name: branch
      type: string
    - name: test-command
      type: string
      default: "echo 'No tests configured — pipeline works!'"
  workspaces:
    - name: shared-workspace
  tasks:
    - name: clone
      taskRef:
        name: git-clone
      params:
        - name: url
          value: $(params.repo-url)
        - name: revision
          value: $(params.revision)
      workspaces:
        - name: output
          workspace: shared-workspace
    - name: test
      runAfter: ["clone"]
      taskRef:
        name: run-tests
      params:
        - name: test-command
          value: $(params.test-command)
      workspaces:
        - name: source
          workspace: shared-workspace
  finally:
    - name: report-success
      when:
        - input: $(tasks.status)
          operator: in
          values: ["Succeeded"]
      taskRef:
        name: gitea-status
      params:
        - name: repo-full-name
          value: $(params.repo-full-name)
        - name: revision
          value: $(params.revision)
        - name: state
          value: "success"
        - name: description
          value: "All checks passed"
    - name: report-failure
      when:
        - input: $(tasks.status)
          operator: notin
          values: ["Succeeded"]
      taskRef:
        name: gitea-status
      params:
        - name: repo-full-name
          value: $(params.repo-full-name)
        - name: revision
          value: $(params.revision)
        - name: state
          value: "failure"
        - name: description
          value: "Pipeline failed"
```

- [ ] **Step 5: Commit**

```bash
git add apps/tekton/tasks/ apps/tekton/pipelines/
git commit -m "feat(cicd): add Stage A pipeline — clone, test, report status to Gitea"
```

- [ ] **Step 6: Push and verify end-to-end**

```bash
git push
# Wait for tekton-extras ArgoCD app to sync
argocd app get tekton-extras --port-forward --port-forward-namespace argocd

# Verify Tasks and Pipeline exist
kubectl get task -n tekton-pipelines
# Expect: git-clone, run-tests, gitea-status
kubectl get pipeline -n tekton-pipelines
# Expect: gitea-ci
```

- [ ] **Step 7: Test the full webhook → pipeline → status flow**

Push a commit to the test repo in Gitea (or trigger via mirror sync), then:

```bash
kubectl get pipelinerun -n tekton-pipelines -w
# Expect: gitea-ci-XXXXX → Running → Succeeded

# Check logs
tkn pipelinerun logs -n tekton-pipelines --last
# Expect: "No tests configured — pipeline works!" and "Reported status 'success'"

# Check Gitea: the commit should show a green check mark
curl -s -H "Authorization: token <GITEA_API_TOKEN>" \
  "http://192.168.55.209:3000/api/v1/repos/<owner>/<repo>/statuses/<sha>" | jq '.[0].state'
# Expect: "success"
```

---

## Task 8: Pipeline Stage B — Build Image and Push to Zot

**Files:**
- Create: `apps/tekton/tasks/build-push.yaml`
- Modify: `apps/tekton/pipelines/gitea-ci.yaml`
- Create: `apps/tekton/manifests/externalsecret-zot-push.yaml`

- [ ] **Step 1: Create ExternalSecret for Zot push credentials**

Create `apps/tekton/manifests/externalsecret-zot-push.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: zot-push-creds
  namespace: tekton-pipelines
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: zot-push-creds
    creationPolicy: Owner
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {"auths":{"192.168.55.210:5000":{"username":"tekton-push","password":"{{ .push_password }}"}}}
  data:
    - secretKey: push_password
      remoteRef:
        key: ZOT_PUSH_PASSWORD
```

Note: Kaniko uses `kubernetes.io/dockerconfigjson` type secrets for registry auth. The ExternalSecret template renders the push password into the dockerconfig format.

- [ ] **Step 2: Create build-push Task**

Create `apps/tekton/tasks/build-push.yaml`:

```yaml
# Builds a container image and pushes to Zot
# Default: Kaniko (no Docker daemon required, Talos-compatible)
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: build-push
  namespace: tekton-pipelines
spec:
  params:
    - name: image
      type: string
      description: "Full image reference (e.g., 192.168.55.210:5000/myapp:latest)"
    - name: dockerfile
      type: string
      default: "Dockerfile"
    - name: context
      type: string
      default: "."
  workspaces:
    - name: source
      description: "The git repo with Dockerfile"
    - name: dockerconfig
      description: "Docker config.json for registry auth"
  steps:
    - name: build-and-push
      image: gcr.io/kaniko-project/executor:latest
      args:
        - "--dockerfile=$(params.dockerfile)"
        - "--context=$(workspaces.source.path)/$(params.context)"
        - "--destination=$(params.image)"
        - "--skip-tls-verify"
      env:
        - name: DOCKER_CONFIG
          value: $(workspaces.dockerconfig.path)
```

Note: The `dockerconfig` workspace is bound to the `zot-push-creds` Secret (type `kubernetes.io/dockerconfigjson`) via the Pipeline's workspace binding. Kaniko reads `$(DOCKER_CONFIG)/config.json` for registry auth. `--skip-tls-verify` handles the self-signed cert — remove if cert-manager cert is trusted.

- [ ] **Step 3: Extend the gitea-ci Pipeline with build-push**

Add the build-push task to `apps/tekton/pipelines/gitea-ci.yaml` after the `test` task. Add new params:

```yaml
    # Add to spec.params:
    - name: image
      type: string
      default: ""
      description: "Image to build and push (empty = skip build)"

    # Add to spec.tasks, after 'test':
    - name: build-push
      runAfter: ["test"]
      when:
        - input: $(params.image)
          operator: notin
          values: [""]
      taskRef:
        name: build-push
      params:
        - name: image
          value: $(params.image)
      workspaces:
        - name: source
          workspace: shared-workspace
        - name: dockerconfig
          workspace: docker-credentials

    # Add to spec.workspaces (after shared-workspace):
    - name: docker-credentials
      optional: true
      description: "Docker config.json for registry auth (bound to zot-push-creds Secret)"
```

Note: The `when` clause makes the build step optional — if `image` param is empty, it's skipped. This keeps Stage A pipelines (test-only) working.

Also update the TriggerTemplate to pass the `docker-credentials` workspace:

```yaml
    # Add to TriggerTemplate resourcetemplates[0].spec.workspaces:
    - name: docker-credentials
      secret:
        secretName: zot-push-creds
```

- [ ] **Step 4: Commit**

```bash
git add apps/tekton/tasks/build-push.yaml apps/tekton/manifests/externalsecret-zot-push.yaml apps/tekton/pipelines/gitea-ci.yaml apps/tekton/triggers/triggertemplate.yaml
git commit -m "feat(cicd): add Stage B — Kaniko image build and push to Zot"
```

- [ ] **Step 5: Push and verify**

```bash
git push
# Create a test repo in Gitea with a Dockerfile, then trigger a pipeline with image param set
# Or test manually:
cat <<'EOF' | kubectl apply -f -
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  generateName: test-build-
  namespace: tekton-pipelines
spec:
  pipelineRef:
    name: gitea-ci
  params:
    - name: repo-url
      value: "http://gitea-http.gitea.svc.cluster.local:3000/<owner>/<repo>.git"
    - name: revision
      value: "main"
    - name: repo-full-name
      value: "<owner>/<repo>"
    - name: branch
      value: "main"
    - name: image
      value: "192.168.55.210:5000/test/myapp:latest"
  workspaces:
    - name: shared-workspace
      volumeClaimTemplate:
        spec:
          accessModes: ["ReadWriteOnce"]
          storageClassName: longhorn-cicd
          resources:
            requests:
              storage: 1Gi
    - name: docker-credentials
      secret:
        secretName: zot-push-creds
EOF

kubectl get pipelinerun -n tekton-pipelines -w
# Expect: Succeeded

# Verify image in Zot
curl -sk https://192.168.55.210:5000/v2/_catalog
# Expect: "test/myapp" in the repositories list
```

---

## Task 9: Pipeline Stage C — Cosign Image Signing

**Files:**
- Create: `apps/tekton/tasks/cosign-sign.yaml`
- Create: `apps/tekton/manifests/externalsecret-cosign.yaml`
- Modify: `apps/tekton/pipelines/gitea-ci.yaml`

- [ ] **Step 1: Generate cosign key pair and store in Infisical**

```yaml
# manual-operation
id: cicd-cosign-keypair
layer: cicd
app: tekton
plan: docs/superpowers/plans/2026-03-29--cicd--platform.md
when: "Before Pipeline Stage C"
why_manual: "Key generation must be done securely, then stored in Infisical"
commands:
  - "COSIGN_PASSWORD='' cosign generate-key-pair (empty password — the Task uses COSIGN_PASSWORD='')"
  - "Store cosign.key (private) in Infisical as COSIGN_KEY"
  - "Store cosign.pub (public) in repo at apps/tekton/cosign.pub"
verify:
  - "Infisical → COSIGN_KEY exists"
  - "cosign.pub committed to repo"
status: pending
```

- [ ] **Step 2: Create ExternalSecret for cosign key**

Create `apps/tekton/manifests/externalsecret-cosign.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: cosign-key
  namespace: tekton-pipelines
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: cosign-key
    creationPolicy: Owner
  data:
    - secretKey: cosign.key
      remoteRef:
        key: COSIGN_KEY
```

- [ ] **Step 3: Create cosign-sign Task**

Create `apps/tekton/tasks/cosign-sign.yaml`:

```yaml
# Signs an OCI image with cosign
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: cosign-sign
  namespace: tekton-pipelines
spec:
  params:
    - name: image
      type: string
      description: "Full image reference to sign (with digest)"
  steps:
    - name: sign
      image: bitnami/cosign:latest
      env:
        - name: COSIGN_KEY
          value: /cosign/cosign.key
        - name: COSIGN_PASSWORD
          value: ""
      command: ["cosign"]
      args:
        - "sign"
        - "--key"
        - "/cosign/cosign.key"
        - "--tlog-upload=false"
        - "--allow-insecure-registry"
        - "$(params.image)"
      volumeMounts:
        - name: cosign-key
          mountPath: /cosign
          readOnly: true
  volumes:
    - name: cosign-key
      secret:
        secretName: cosign-key
```

Note: `--tlog-upload=false` disables transparency log upload (Rekor) since this is a private registry. `--allow-insecure-registry` handles the self-signed cert. Remove if cert is trusted.

- [ ] **Step 4: Extend gitea-ci Pipeline with cosign-sign**

Add to `apps/tekton/pipelines/gitea-ci.yaml`, after `build-push`:

```yaml
    # Add to spec.tasks, after 'build-push':
    - name: sign
      runAfter: ["build-push"]
      when:
        - input: $(params.image)
          operator: notin
          values: [""]
      taskRef:
        name: cosign-sign
      params:
        - name: image
          value: $(params.image)
```

Note: Ideally the cosign-sign task should use the image digest (not tag) for signing. The build-push task should output the digest as a result, and the sign task should consume it. This requires adding a `results` field to the build-push task. Implement this refinement during execution — for now, the tag-based signing works.

- [ ] **Step 5: Commit**

```bash
git add apps/tekton/tasks/cosign-sign.yaml apps/tekton/manifests/externalsecret-cosign.yaml apps/tekton/pipelines/gitea-ci.yaml apps/tekton/cosign.pub
git commit -m "feat(cicd): add Stage C — cosign image signing after push to Zot"
```

- [ ] **Step 6: Push and verify**

```bash
git push
# Trigger a pipeline with image param set (same as Task 8 test)
# After pipeline succeeds:
cosign verify --key apps/tekton/cosign.pub --insecure-ignore-tlog --allow-insecure-registry \
  192.168.55.210:5000/test/myapp:latest
# Expect: Verified OK (or similar success message)
```

---

## Summary of Manual Operations

| ID | Layer | When | What |
|----|-------|------|------|
| `cicd-pc1-role-label` | cicd | Before Task 2 | Add role=cicd label to pc-1 via Omni |
| `cicd-infisical-gitea-secrets` | cicd | Before Task 2 | Create Gitea secrets in Infisical |
| `cicd-authentik-gitea-oidc` | cicd | Before Task 2 | ~~Create Authentik OIDC provider for Gitea~~ DONE (via script) |
| `cicd-gitea-service-account` | cicd | After Task 2 | Create Gitea service account + API token |
| `cicd-gitea-mirror-test-repo` | cicd | After Task 2 | Mirror test repo from GitHub |
| `cicd-infisical-webhook-secret` | cicd | Before Task 5 | Create webhook secret in Infisical |
| `cicd-gitea-webhook` | cicd | After Task 5 | Configure Gitea webhook for test repo |
| `cicd-infisical-zot-secrets` | cicd | Before Task 6 | Create Zot secrets in Infisical |
| `cicd-authentik-zot-oidc` | cicd | Before Task 6 | ~~Create Authentik OIDC provider for Zot~~ DONE (via script) |
| `cicd-talos-containerd-mirror` | cicd | After Task 6 | Apply containerd mirror Talos patch |
| `cicd-cosign-keypair` | cicd | Before Task 9 | Generate cosign key pair |

---

## Open Items for Implementation

- **Helm chart versions**: All `targetRevision` values are placeholders. Pin to latest stable at implementation time.
- **Tekton release versions**: Download latest stable from GitHub releases at implementation time.
- **Gitea chart OIDC syntax**: The `gitea.oauth` section varies between chart versions — verify during Step 2 research.
- **Gitea internal service name**: Verify `gitea-http.gitea.svc.cluster.local` matches the actual service name after deployment.
- **Zot chart config**: The Zot Helm chart structure needs research — TLS, htpasswd, and OIDC config paths will be determined in Task 6 Step 2.
- **Webhook secret validation**: The CEL interceptor for HMAC validation of Gitea webhooks may need a `secretRef` — verify against Tekton Triggers docs.
- **Cosign digest-based signing**: The initial implementation signs by tag. Refine to use image digest from build-push results.
- **cert-manager IP SAN**: Test whether the self-signed ClusterIssuer supports IP addresses in SANs for the Zot TLS cert.
