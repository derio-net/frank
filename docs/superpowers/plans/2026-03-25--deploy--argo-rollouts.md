# Argo Rollouts — Progressive Delivery Platform

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Argo Rollouts controller on Frank and migrate LiteLLM to canary (Cilium traffic splitting + VictoriaMetrics analysis) and Paperclip to a Recreate-strategy Rollout (with operational observability and rollback).

**Architecture:** Three-phase plan. Phase 1 installs the controller and verifies Cilium Envoy is enabled (required for `CiliumEnvoyConfig` traffic splitting). Phase 2 migrates LiteLLM via `workloadRef` — the Rollout takes over pod management from the Helm chart's Deployment. Phase 3 replaces Paperclip's Deployment with an Argo Rollouts Recreate Rollout.

> **Design correction vs. spec:** The spec proposed blue-green for Paperclip, but Paperclip's `/paperclip` PVC has `accessModes: ReadWriteOnce`. Blue-green requires two concurrent ReplicaSets (blue + green), which deadlocks on a RWO volume — the green pod can never mount while blue holds it. The strategy is changed to **Recreate** (kill blue, start green), which is compatible with RWO and matches Paperclip's existing Deployment strategy. This still adds Argo Rollouts observability and rollback capability over a plain Deployment.

**Tech Stack:** Argo Rollouts Helm chart (argoproj.github.io/argo-helm), Cilium traffic router plugin (argoproj-labs/rollouts-plugin-trafficrouter-cilium), VictoriaMetrics (Prometheus-compatible API), Argo Rollouts CRDs (Rollout, AnalysisTemplate).

**Design doc:** `docs/superpowers/specs/2026-03-25--deploy--argo-rollouts-design.md`
**Status:** Deployed (Phase 3 Paperclip Rollout reverted — runs as plain Deployment)

---

## File Map

| File | Action | Purpose |
| ---- | ------ | ------- |
| `docs/layers.yaml` | Modify | Add layer 18 (deploy) |
| `apps/argo-rollouts/values.yaml` | Create | Helm values for controller |
| `apps/argo-rollouts-extras/manifests/plugin-config.yaml` | Create | ConfigMap loading the Cilium plugin |
| `apps/argo-rollouts-extras/manifests/cilium-rbac.yaml` | Create | ClusterRole + ClusterRoleBinding for CiliumEnvoyConfig |
| `apps/root/templates/argo-rollouts.yaml` | Create | ArgoCD Application CR (Helm chart) |
| `apps/root/templates/argo-rollouts-extras.yaml` | Create | ArgoCD Application CR (extra manifests) |
| `apps/cilium/values.yaml` | Modify (if needed) | Enable Cilium Envoy proxy for CiliumEnvoyConfig |
| `apps/litellm/values.yaml` | Modify | Pin image tag (drop `main-stable`) |
| `apps/root/templates/litellm.yaml` | Modify | Add ignoreDifferences on Deployment spec.replicas |
| `apps/litellm/manifests/service-canary.yaml` | Create | ClusterIP canary service for Cilium traffic split |
| `apps/litellm/manifests/rollout.yaml` | Create | Rollout with workloadRef + canary strategy |
| `apps/litellm/manifests/analysis-template.yaml` | Create | VictoriaMetrics error-rate AnalysisTemplate |
| `apps/paperclip/manifests/deployment.yaml` | Rename → `rollout.yaml` | Convert to Recreate Rollout |

---

## Phase 1: Controller Install

### Task 1: Register layer and create values file

**Files:**

- Modify: `docs/layers.yaml`
- Create: `apps/argo-rollouts/values.yaml`

- [ ] **Step 1: Add layer 18 to docs/layers.yaml**

Append after the `edge` entry (before `repo`):

```yaml
  - code: deploy
    number: 18
    name: Progressive Delivery
    description: Argo Rollouts, canary and blue-green deployment strategies
```

- [ ] **Step 2: Create apps/argo-rollouts/values.yaml**

```yaml
# Argo Rollouts — progressive delivery controller
# Layer 18 (deploy)
# Cilium traffic router plugin loaded via argo-rollouts-extras manifests

controller:
  replicas: 1

# Dashboard UI is out of scope — kubectl plugin is sufficient
dashboard:
  enabled: false

notifications:
  enabled: false
```

- [ ] **Step 3: Commit**

```bash
git add docs/layers.yaml apps/argo-rollouts/values.yaml
git commit -m "feat(deploy): scaffold argo-rollouts layer and values"
```

---

### Task 2: ArgoCD Application CRs

**Files:**

- Create: `apps/root/templates/argo-rollouts.yaml`
- Create: `apps/root/templates/argo-rollouts-extras.yaml`

Reference pattern: `apps/root/templates/argocd.yaml` (Helm chart source) and `apps/root/templates/litellm-extras.yaml` (manifests source).

- [ ] **Step 1: Find the latest chart version**

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm search repo argo/argo-rollouts
# Pin targetRevision to the exact version shown — do NOT use "*" or "latest"
```

- [ ] **Step 2: Create apps/root/templates/argo-rollouts.yaml**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argo-rollouts
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "1"
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://argoproj.github.io/argo-helm
      chart: argo-rollouts
      targetRevision: "2.x.x"   # replace with version from Step 1
      helm:
        releaseName: argo-rollouts
        valueFiles:
          - $values/apps/argo-rollouts/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: argo-rollouts
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 3: Create apps/root/templates/argo-rollouts-extras.yaml**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argo-rollouts-extras
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "2"
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/argo-rollouts-extras/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: argo-rollouts
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

- [ ] **Step 4: Commit**

```bash
git add apps/root/templates/argo-rollouts.yaml apps/root/templates/argo-rollouts-extras.yaml
git commit -m "feat(deploy): add argo-rollouts and argo-rollouts-extras Application CRs"
```

---

### Task 3: Cilium plugin ConfigMap and RBAC

**Files:**

- Create: `apps/argo-rollouts-extras/manifests/plugin-config.yaml`
- Create: `apps/argo-rollouts-extras/manifests/cilium-rbac.yaml`

The controller reads `argo-rollouts-config` ConfigMap in its namespace at startup to discover traffic router plugins. The `argo-rollouts` ServiceAccount (created by the Helm chart) needs supplemental RBAC for `CiliumEnvoyConfig`.

- [ ] **Step 1: Find the latest Cilium plugin release**

```bash
# Visit https://github.com/argoproj-labs/rollouts-plugin-trafficrouter-cilium/releases
# Pin to the latest release tag — do NOT use "latest" in the URL
# Note the version (e.g., v0.4.1)
```

- [ ] **Step 2: Create plugin-config.yaml**

Replace `v0.x.y` with the actual release tag:

```yaml
# ConfigMap read by argo-rollouts controller at startup
# Downloads the Cilium traffic router plugin binary on first boot (requires internet access)
# Subsequent restarts use the cached binary
apiVersion: v1
kind: ConfigMap
metadata:
  name: argo-rollouts-config
  namespace: argo-rollouts
data:
  trafficRouterPlugins: |-
    - name: "argoproj-labs/cilium"
      location: "https://github.com/argoproj-labs/rollouts-plugin-trafficrouter-cilium/releases/download/v0.x.y/rollouts-plugin-trafficrouter-cilium-linux-amd64"
```

- [ ] **Step 3: Create cilium-rbac.yaml**

The ServiceAccount name matches the chart's `releaseName: argo-rollouts`.

```yaml
# Supplemental RBAC: grants argo-rollouts controller access to CiliumEnvoyConfig
# Required by the Cilium traffic router plugin — not included in chart defaults
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: argo-rollouts-cilium
rules:
  - apiGroups: ["cilium.io"]
    resources: ["ciliumenvoyconfigs"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: argo-rollouts-cilium
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: argo-rollouts-cilium
subjects:
  - kind: ServiceAccount
    name: argo-rollouts
    namespace: argo-rollouts
```

- [ ] **Step 4: Commit**

```bash
git add apps/argo-rollouts-extras/
git commit -m "feat(deploy): add Cilium plugin config and RBAC for argo-rollouts"
```

---

### Task 4: Verify Cilium Envoy is enabled

`CiliumEnvoyConfig` objects are only processed by Cilium when the Envoy proxy is active on nodes. This is a prerequisite for Phase 2 traffic splitting. Verify before proceeding.

- [ ] **Step 1: Check if Cilium Envoy DaemonSet is running**

```bash
source .env
kubectl get daemonset -n kube-system | grep -i envoy
# If cilium-envoy DaemonSet exists and is fully running → Envoy is already enabled. Skip to Step 4.
# If not found → continue to Step 2.
```

- [ ] **Step 2: Check current Cilium values**

```bash
cat apps/cilium/values.yaml | grep -A5 -i envoy
# Look for envoy.enabled or l7proxy settings
```

- [ ] **Step 3: Enable Envoy if not present**

If `cilium-envoy` DaemonSet does not exist, add to `apps/cilium/values.yaml`:

```yaml
envoy:
  enabled: true
```

Then sync Cilium and wait for the DaemonSet to roll out:

```bash
git add apps/cilium/values.yaml
git commit -m "feat(deploy): enable Cilium Envoy proxy for CiliumEnvoyConfig support"
git push
argocd app sync cilium --port-forward --port-forward-namespace argocd
kubectl rollout status daemonset/cilium-envoy -n kube-system
```

- [ ] **Step 4: Verify CiliumEnvoyConfig CRD exists**

```bash
kubectl get crd ciliumenvoyconfigs.cilium.io
# Expected: the CRD is found (registered by Cilium operator)
```

---

### Task 5: Deploy Phase 1 and verify

- [ ] **Step 1: Push and sync**

```bash
git push
source .env
argocd app sync argo-rollouts --port-forward --port-forward-namespace argocd
argocd app sync argo-rollouts-extras --port-forward --port-forward-namespace argocd
```

- [ ] **Step 2: Verify controller is running**

```bash
kubectl get pods -n argo-rollouts
# Expected: argo-rollouts-<hash> Running 1/1
```

- [ ] **Step 3: Verify Cilium plugin loaded**

```bash
kubectl logs -n argo-rollouts -l app.kubernetes.io/name=argo-rollouts | grep -i plugin
# Expected: log line confirming plugin "argoproj-labs/cilium" was downloaded/cached
```

- [ ] **Step 4: Verify CiliumEnvoyConfig RBAC**

```bash
kubectl auth can-i create ciliumenvoyconfigs \
  --as=system:serviceaccount:argo-rollouts:argo-rollouts \
  -n litellm
# Expected: yes
```

- [ ] **Step 5: Install kubectl-argo-rollouts CLI plugin locally (manual operation)**

```bash
# Check latest release version at https://github.com/argoproj/argo-rollouts/releases
curl -LO https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-darwin-amd64
chmod +x kubectl-argo-rollouts-darwin-amd64
sudo mv kubectl-argo-rollouts-darwin-amd64 /usr/local/bin/kubectl-argo-rollouts
kubectl argo rollouts version
# Expected: argo-rollouts: vX.Y.Z
```

---

## Phase 2: LiteLLM Canary

### Task 6: Pin image tag and fix ArgoCD ignoreDifferences

**Files:**

- Modify: `apps/litellm/values.yaml`
- Modify: `apps/root/templates/litellm.yaml`

`workloadRef` scales the Helm chart's Deployment to 0 replicas. Without `ignoreDifferences` on the Deployment's `spec.replicas`, ArgoCD will continuously try to restore the chart's replica count, fighting the Rollout controller.

- [ ] **Step 1: Find the current LiteLLM stable release**

```bash
# Check https://github.com/BerriAI/litellm/releases for the latest tagged release
# Use the tag that matches the current container image version, not main-stable
```

- [ ] **Step 2: Pin image tag in apps/litellm/values.yaml**

Change:

```yaml
image:
  repository: ghcr.io/berriai/litellm-database
  tag: main-stable
  pullPolicy: Always
```

To:

```yaml
image:
  repository: ghcr.io/berriai/litellm-database
  tag: "v1.x.x"    # replace with actual version from Step 1
  pullPolicy: IfNotPresent
```

- [ ] **Step 3: Add ignoreDifferences for Deployment spec.replicas**

In `apps/root/templates/litellm.yaml`, the existing `ignoreDifferences` covers Secrets. Add a second entry for the Deployment. The final `ignoreDifferences` block should read:

```yaml
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
    - group: apps
      kind: Deployment
      name: litellm
      namespace: litellm
      jsonPointers:
        - /spec/replicas
```

> **Note:** `group: apps` is required (not `group: ""`). Omitting it causes the rule to not match and ArgoCD continues fighting the Rollout controller.

- [ ] **Step 4: Commit**

```bash
git add apps/litellm/values.yaml apps/root/templates/litellm.yaml
git commit -m "feat(deploy): pin litellm tag and suppress spec.replicas ignoreDiff for workloadRef"
```

---

### Task 7: Discover service names and VictoriaMetrics URL

Gather the exact names needed before writing manifests — don't guess.

- [ ] **Step 1: Find the LiteLLM stable service name**

```bash
source .env
kubectl get svc -n litellm
# Note the service name (expected: "litellm") and the exact selector labels it uses
kubectl get svc litellm -n litellm -o yaml | grep -A5 selector
```

- [ ] **Step 2: Find LiteLLM pod labels**

```bash
kubectl get pods -n litellm --show-labels
# Note the exact label key=value pairs — the canary service selector must match these
```

- [ ] **Step 3: Find the VictoriaMetrics service URL**

```bash
kubectl get svc -n monitoring | grep -i victoria
# Look for the VMSingle server service
kubectl run vmtest --image=curlimages/curl --rm -it --restart=Never -- \
  curl -s "http://<service-name>.monitoring.svc.cluster.local:8428/api/v1/query?query=up"
# Expected: {"status":"success",...}
# Note the full URL for use in analysis-template.yaml
```

- [ ] **Step 4: Verify LiteLLM exposes metrics**

```bash
kubectl exec -n litellm deploy/litellm -- curl -s localhost:4000/metrics 2>/dev/null | grep litellm_request || echo "No metrics endpoint"
# If no metrics: LiteLLM may need PROMETHEUS_URL env var or metrics enabled in config
# Adjust the PromQL query in the analysis template accordingly
```

---

### Task 8: LiteLLM canary service and analysis template

**Files:**

- Create: `apps/litellm/manifests/service-canary.yaml`
- Create: `apps/litellm/manifests/analysis-template.yaml`

The `litellm-extras` ArgoCD app already watches `apps/litellm/manifests/` — these files deploy automatically on sync.

- [ ] **Step 1: Create service-canary.yaml**

Use the pod labels discovered in Task 7 Step 2. The Rollout controller will manage the selector (adding `rollouts-pod-template-hash`) — set the base labels only here.

```yaml
# ClusterIP canary service for LiteLLM
# Argo Rollouts manages selector to point at canary pods via rollouts-pod-template-hash
# The Cilium plugin creates a CiliumEnvoyConfig to split traffic between
# this service (canary) and the stable service (litellm, LB 55.206)
apiVersion: v1
kind: Service
metadata:
  name: litellm-canary
  namespace: litellm
spec:
  type: ClusterIP
  ports:
    - name: http
      port: 4000
      targetPort: 4000
      protocol: TCP
  selector:
    app: litellm   # verify against Task 7 Step 2 — use the chart's actual pod label
```

- [ ] **Step 2: Create analysis-template.yaml**

Replace `<vm-service-url>` with the URL from Task 7 Step 3:

```yaml
# AnalysisTemplate: LiteLLM error rate via VictoriaMetrics Prometheus API
# Runs 5 x 1-minute intervals (5 min total) at each canary step
# inconclusiveCondition: NaN result = 0 traffic (sparse homelab) → pause, not abort
# inconclusiveLimit: 3 = after 15 min with no traffic, abort and hold rollout
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: litellm-error-rate
  namespace: litellm
spec:
  metrics:
    - name: error-rate
      interval: 1m
      count: 5
      inconclusiveLimit: 3
      successCondition: "result < 0.05"
      failureCondition: "result >= 0.05"
      inconclusiveCondition: "isNaN(result)"
      provider:
        prometheus:
          address: "<vm-service-url>"
          query: |
            sum(rate(litellm_request_total{status=~"5.."}[5m]))
            /
            sum(rate(litellm_request_total[5m]))
```

- [ ] **Step 3: Commit**

```bash
git add apps/litellm/manifests/service-canary.yaml apps/litellm/manifests/analysis-template.yaml
git commit -m "feat(deploy): add litellm canary service and VictoriaMetrics analysis template"
```

---

### Task 9: LiteLLM Rollout with workloadRef

**Files:**

- Create: `apps/litellm/manifests/rollout.yaml`

- [ ] **Step 1: Create rollout.yaml**

Use the stable service name confirmed in Task 7 Step 1 (expected: `litellm`):

```yaml
# Argo Rollouts canary for LiteLLM Gateway
#
# workloadRef: Rollout reads pod template from the Helm chart's Deployment.
# The Deployment is scaled to 0 — this is expected and correct.
# ArgoCD ignoreDifferences on apps/Deployment/spec.replicas prevents fight.
#
# Canary steps:
#   20% → manual pause (wait for consumers to be active) → 5-min VictoriaMetrics analysis →
#   50% → manual pause → 5-min analysis →
#   100% (full promotion)
#
# Traffic: Cilium plugin creates CiliumEnvoyConfig weighting litellm:litellm-canary.
# If L2 LB + CiliumEnvoyConfig is incompatible (uncommon config), fallback:
#   change litellm service to ClusterIP + add separate LB service for 55.206 IP.
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: litellm
  namespace: litellm
spec:
  replicas: 1
  workloadRef:
    apiVersion: apps/v1
    kind: Deployment
    name: litellm
  strategy:
    canary:
      stableService: litellm       # Helm chart service, LoadBalancer 55.206
      canaryService: litellm-canary  # new ClusterIP service
      trafficRouting:
        plugins:
          argoproj-labs/cilium: {}
      steps:
        - setWeight: 20
        - pause: {}                    # advance: kubectl argo rollouts promote litellm -n litellm
        - analysis:
            templates:
              - templateName: litellm-error-rate
        - setWeight: 50
        - pause: {}
        - analysis:
            templates:
              - templateName: litellm-error-rate
```

- [ ] **Step 2: Commit**

```bash
git add apps/litellm/manifests/rollout.yaml
git commit -m "feat(deploy): add litellm Rollout with workloadRef and Cilium canary strategy"
```

---

### Task 10: Deploy and verify Phase 2

- [ ] **Step 1: Push and sync**

```bash
git push
source .env
argocd app sync litellm --port-forward --port-forward-namespace argocd
argocd app sync litellm-extras --port-forward --port-forward-namespace argocd
```

- [ ] **Step 2: Verify Deployment is at 0 and Rollout is healthy**

```bash
kubectl get deployment litellm -n litellm
# Expected: READY 0/0 (Rollout controller took over)
kubectl argo rollouts get rollout litellm -n litellm
# Expected: Phase: Healthy, pods running under Rollout
```

- [ ] **Step 3: Verify LiteLLM is still accessible**

```bash
curl -s http://192.168.55.206:4000/health
# Expected: 200 response
```

- [ ] **Step 4: Trigger a test canary**

```bash
# Bump image tag by one patch version to trigger a rollout
# Update tag in apps/litellm/values.yaml, commit, push, then:
kubectl argo rollouts get rollout litellm -n litellm --watch
# Expected: shows 20% canary weight, status: Paused

# Check CiliumEnvoyConfig was created
kubectl get ciliumenvoyconfig -n litellm
# Expected: one object created by the Cilium plugin

# When ready to advance (consumers active):
kubectl argo rollouts promote litellm -n litellm
# Analysis runs for 5 min — watch with --watch flag

# Abort if testing (returns to stable)
kubectl argo rollouts abort litellm -n litellm
```

> **If CiliumEnvoyConfig is created but traffic split is not working:**
> The L2 LB service may not be intercepted by the Envoy filter. Fallback:
> 1. Change `apps/litellm/manifests/` to add a new `Service/litellm-stable` (ClusterIP) and a `Service/litellm-lb` (LoadBalancer) pointing at the ClusterIP
> 2. Update `stableService: litellm-stable` in rollout.yaml
> 3. Update the LB IP annotation on the new LoadBalancer service

- [ ] **Step 5: Commit any fixes**

```bash
git add -p
git commit -m "fix(deploy): <describe what needed fixing>"
```

---

## Phase 3: Paperclip Rollout (Recreate)

> **Why not blue-green:** Paperclip's `/paperclip` PVC uses `accessModes: ReadWriteOnce`. Blue-green requires two concurrent ReplicaSets (active + preview). The preview pods could never mount the RWO volume while active pods hold it — they'd be permanently Pending. Using Argo Rollouts with `recreate` strategy instead: Rollout kills the old pods first, then starts the new ones. This is identical to the existing `strategy: Recreate` Deployment but adds Argo Rollouts observability and rollback via `kubectl argo rollouts abort`.

### Task 11: Manual Deployment deletion (prerequisite)

Kubernetes does not allow changing the `kind` of an existing resource. ArgoCD `prune: false` means the old Deployment won't be auto-deleted. The safe sequence:

- [ ] **Step 1: Scale Deployment to 0 first (avoids traffic gap)**

```bash
source .env
kubectl scale deployment paperclip --replicas=0 -n paperclip-system
kubectl get pods -n paperclip-system
# Wait until all paperclip pods are gone (Terminating → gone)
```

- [ ] **Step 2: Delete the Deployment object**

```bash
kubectl delete deployment paperclip -n paperclip-system
kubectl get deployment paperclip -n paperclip-system
# Expected: Error from server (NotFound)
```

> Paperclip is now offline. The next task commits the Rollout — ArgoCD will create it and bring Paperclip back up. Schedule this during a low-usage window.

---

### Task 12: Paperclip Rollout (Recreate strategy)

**Files:**

- Rename: `apps/paperclip/manifests/deployment.yaml` → `apps/paperclip/manifests/rollout.yaml`

Copy the full Deployment spec. Change `apiVersion`, `kind`, remove `spec.strategy` (Rollout has its own strategy field), add the Argo Rollouts strategy block.

- [ ] **Step 1: Create rollout.yaml from deployment.yaml spec**

```yaml
# Argo Rollouts Recreate for Paperclip AI Orchestrator
#
# Replaces deployment.yaml (deleted manually in Task 11).
# Strategy: Recreate — compatible with RWO PVC (/paperclip on Longhorn).
#   Blue-green is NOT possible: two concurrent ReplicaSets would deadlock on the RWO volume.
#
# Rollback: kubectl argo rollouts abort paperclip -n paperclip-system
#   (restores previous ReplicaSet — Argo Rollouts keeps it around until TTL)
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: paperclip
  namespace: paperclip-system
  labels:
    app.kubernetes.io/name: paperclip
    app.kubernetes.io/component: server
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: paperclip
      app.kubernetes.io/component: server
  template:
    metadata:
      labels:
        app.kubernetes.io/name: paperclip
        app.kubernetes.io/component: server
    spec:
      nodeSelector:
        zone: core
      securityContext:
        fsGroup: 1000
      imagePullSecrets:
        - name: paperclip-ghcr
      containers:
        - name: paperclip
          image: ghcr.io/derio-net/paperclip:v0.3.2
          ports:
            - name: http
              containerPort: 3100
              protocol: TCP
          envFrom:
            - configMapRef:
                name: paperclip-config
            - secretRef:
                name: paperclip-llm-key
            - secretRef:
                name: paperclip-auth
            - secretRef:
                name: paperclip-anthropic
                optional: true
          env:
            - name: PG_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: paperclip-db-postgresql
                  key: password
            - name: DATABASE_URL
              value: "postgres://paperclip:$(PG_PASSWORD)@paperclip-db-postgresql.paperclip-system.svc:5432/paperclip"
          volumeMounts:
            - name: data
              mountPath: /paperclip
          resources:
            requests:
              memory: 256Mi
              cpu: 250m
            limits:
              memory: 1Gi
              cpu: "1"
          readinessProbe:
            tcpSocket:
              port: http
            periodSeconds: 10
          livenessProbe:
            tcpSocket:
              port: http
            initialDelaySeconds: 30
            periodSeconds: 15
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: paperclip-data
  strategy:
    recreate: {}
```

- [ ] **Step 2: Remove deployment.yaml and commit rollout.yaml**

```bash
git rm apps/paperclip/manifests/deployment.yaml
git add apps/paperclip/manifests/rollout.yaml
git commit -m "feat(deploy): replace paperclip Deployment with Recreate Rollout (RWO PVC constraint)"
```

---

### Task 13: Deploy and verify Phase 3

- [ ] **Step 1: Push and sync**

```bash
git push
source .env
argocd app sync paperclip --port-forward --port-forward-namespace argocd
```

- [ ] **Step 2: Verify Rollout is healthy**

```bash
kubectl argo rollouts get rollout paperclip -n paperclip-system
# Expected: Strategy: Recreate, Phase: Healthy, 1 pod running
```

- [ ] **Step 3: Verify Paperclip is accessible**

```bash
curl -s http://192.168.55.212:3100/
# Expected: HTML response (Paperclip web UI)
```

- [ ] **Step 4: Test rollout and rollback**

```bash
# Trigger a rollout by bumping the image tag
kubectl argo rollouts set image paperclip paperclip=ghcr.io/derio-net/paperclip:v0.3.2 -n paperclip-system
kubectl argo rollouts get rollout paperclip -n paperclip-system --watch
# Expected: old pod terminates, new pod starts (Recreate: no concurrent pods)

# Test rollback
kubectl argo rollouts abort paperclip -n paperclip-system
# Rollout returns to previous ReplicaSet
kubectl argo rollouts get rollout paperclip -n paperclip-system
# Expected: Phase: Degraded (aborted) → undo: kubectl argo rollouts retry rollout paperclip -n paperclip-system
```

---

## Deployment Deviations

_Record any surprises here during implementation:_

---

## Operating Reference

### Canary (LiteLLM)

```bash
source .env

# Watch live status
kubectl argo rollouts get rollout litellm -n litellm --watch

# Advance past a manual pause (when consumers/Ollama are active)
kubectl argo rollouts promote litellm -n litellm

# Force-promote past all steps (skips analysis)
kubectl argo rollouts promote litellm -n litellm --full

# Abort — all traffic returns to stable, canary pods removed
kubectl argo rollouts abort litellm -n litellm

# Inspect analysis run
kubectl get analysisrun -n litellm
kubectl describe analysisrun -n litellm <name>
```

**Handling Inconclusive analysis:**

When analysis shows `Inconclusive` (no traffic / VictoriaMetrics unreachable):
1. Check traffic: `kubectl exec -n litellm <pod> -- curl -s localhost:4000/metrics | grep litellm_request_total`
2. If consumers are paused/Ollama is down: wait, then `kubectl argo rollouts promote litellm -n litellm` to re-run analysis
3. If VictoriaMetrics is down: use `--full` to bypass analysis
4. If something is genuinely broken: `kubectl argo rollouts abort litellm -n litellm`

### Recreate (Paperclip)

```bash
source .env

# Watch live status
kubectl argo rollouts get rollout paperclip -n paperclip-system --watch

# Abort — returns to previous ReplicaSet (brief downtime — Recreate kills old before new is ready)
kubectl argo rollouts abort paperclip -n paperclip-system

# Retry after abort
kubectl argo rollouts retry rollout paperclip -n paperclip-system
```
