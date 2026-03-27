---
title: "Progressive Delivery with Argo Rollouts"
date: 2026-03-27
draft: false
tags: ["argo-rollouts", "canary", "blue-green", "cilium", "victoria-metrics", "litellm", "sympozium"]
summary: "Adding canary and blue-green deployment strategies to the cluster with Argo Rollouts, Cilium traffic splitting, and VictoriaMetrics metric-gated analysis."
weight: 20
cover:
  image: cover.png
  alt: "Frank the cluster monster at a traffic control tower directing pods between canary and blue-green lanes"
  relative: true
---

Every previous deployment on Frank has been a leap of faith. Push YAML, ArgoCD syncs, the old pod dies, the new pod starts. If the new version is broken, you find out when users hit errors. For a homelab that's fine — the "users" are just me. But the whole point of this project is to learn production patterns, and production doesn't deploy by prayer.

This post adds **progressive delivery** — the ability to gradually shift traffic to a new version (canary) or run two versions simultaneously and switch atomically (blue-green). Argo Rollouts provides both strategies. Cilium handles the traffic splitting. VictoriaMetrics gates promotions on real error rates. And when traffic is sparse (which is most of the time in a homelab), the system pauses and waits for the operator rather than blindly promoting or aborting.

## What Is Progressive Delivery?

Traditional Kubernetes deployments are binary: old version off, new version on. Progressive delivery adds intermediate states:

**Canary** shifts a percentage of traffic to the new version. If metrics look good, the percentage increases. If metrics are bad, traffic reverts to the old version. The old version stays live the entire time — users on the stable path never notice.

**Blue-green** runs two full environments simultaneously. The "blue" (active) environment serves all traffic while the "green" (preview) environment starts up and gets smoke-tested. When you're confident in green, traffic switches atomically. If green is broken, blue is still there — instant rollback.

Both strategies require something a standard Deployment can't do: manage two ReplicaSets simultaneously with traffic control between them.

## Architecture

Argo Rollouts installs as a controller in its own namespace. It watches `Rollout` CRDs cluster-wide and manages pod lifecycles, traffic splitting, and metric-gated promotions.

```
argo-rollouts namespace
  └── argo-rollouts controller + Cilium traffic router plugin

litellm namespace
  └── Rollout/litellm (canary via workloadRef → Deployment/litellm)
      ├── stable service: litellm (LB 192.168.55.206)
      ├── canary service: litellm-canary (ClusterIP)
      ├── Cilium CiliumEnvoyConfig (traffic weights)
      └── AnalysisTemplate: VictoriaMetrics error rate

sympozium-system namespace
  └── Rollout/sympozium-apiserver (blue-green via workloadRef)
      ├── active service: sympozium-apiserver-lb (LB 192.168.55.207)
      ├── preview service: sympozium-apiserver-preview (ClusterIP)
      └── AnalysisTemplate: HTTP healthcheck on /healthz
```

## Phase 1: Controller Install

The controller is a standard Helm chart from the Argo project:

```yaml
# apps/argo-rollouts/values.yaml
controller:
  replicas: 1
dashboard:
  enabled: false
notifications:
  enabled: false
```

Two ArgoCD Applications handle deployment: `argo-rollouts` for the Helm chart and `argo-rollouts-extras` for supplemental manifests (plugin config and RBAC).

### Cilium Traffic Router Plugin

Argo Rollouts uses plugins for traffic management. The Cilium plugin creates `CiliumEnvoyConfig` objects that split traffic between stable and canary services at the L7/Envoy level. The controller downloads the plugin binary on first startup from a pinned GitHub release URL:

```yaml
# apps/argo-rollouts-extras/manifests/plugin-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argo-rollouts-config
  namespace: argo-rollouts
data:
  trafficRouterPlugins: |-
    - name: "argoproj-labs/cilium"
      location: "https://github.com/argoproj-labs/rollouts-plugin-trafficrouter-cilium/releases/download/v0.4.1/..."
```

The default Helm chart RBAC doesn't include Cilium CRD permissions, so a supplemental `ClusterRole` grants the controller access to `ciliumenvoyconfigs`:

```yaml
# apps/argo-rollouts-extras/manifests/cilium-rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: argo-rollouts-cilium
rules:
  - apiGroups: ["cilium.io"]
    resources: ["ciliumenvoyconfigs"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
```

## Phase 2: LiteLLM Canary

### The workloadRef Pattern

LiteLLM is deployed via a Helm chart that owns its `Deployment`. Rather than forking the chart to add Rollout support, we use Argo Rollouts' `workloadRef` feature: a `Rollout` object references the Helm chart's Deployment by name. The Rollout controller reads the pod template from the Deployment, scales the Deployment to 0, and takes over pod management.

This is the key insight: **the Helm chart stays the source of truth for application configuration**. The Rollout adds progressive delivery on top without modifying the chart at all. When the chart's Deployment spec changes (e.g., a version bump in `values.yaml`), the Rollout detects it and initiates a canary.

### Image Tag Pinning

The original `values.yaml` used `tag: main-stable` with `pullPolicy: Always`. This makes canary deployment non-deterministic — the "new" version might be the same image as the "old" version, just re-pulled. Pinning to a specific tag (`main-v1.82.3-stable`) makes each version change explicit and trackable.

### Canary Steps

```yaml
strategy:
  canary:
    stableService: litellm
    canaryService: litellm-canary
    trafficRouting:
      plugins:
        argoproj-labs/cilium: {}
    steps:
      - setWeight: 20
      - pause: {}
      - analysis:
          templates:
            - templateName: litellm-error-rate
      - setWeight: 50
      - pause: {}
      - analysis:
          templates:
            - templateName: litellm-error-rate
```

Each `pause: {}` step waits for manual promotion (`kubectl argo rollouts promote litellm -n litellm`). This is intentional for a homelab: you wait until consumers (Paperclip, Sympozium) are actually generating traffic before running the analysis step. In a production environment with constant traffic, you'd replace these with timed pauses.

### VictoriaMetrics Analysis

The `AnalysisTemplate` queries VictoriaMetrics (which exposes a Prometheus-compatible API) for the LiteLLM error rate:

```yaml
spec:
  metrics:
    - name: error-rate
      interval: 1m
      count: 5
      inconclusiveLimit: 3
      successCondition: "result[0] < 0.05"
      failureCondition: "result[0] >= 0.05"
      provider:
        prometheus:
          address: "http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack.monitoring.svc.cluster.local:8428"
          query: |
            sum(rate(litellm_request_total{status=~"5.."}[5m]))
            /
            sum(rate(litellm_request_total[5m]))
```

If the error rate exceeds 5%, the canary aborts and traffic reverts to the stable version. If there's zero traffic (the query returns NaN), the result matches neither `successCondition` nor `failureCondition` — Argo Rollouts treats this as **inconclusive**. After 3 consecutive inconclusive results (15 minutes of silence), the analysis aborts and the Rollout pauses indefinitely. The operator then decides: wait for traffic, force-promote, or abort.

### ArgoCD Integration

The `workloadRef` pattern requires one ArgoCD configuration: the Rollout controller scales the Helm chart's Deployment to 0 replicas, but ArgoCD sees the desired replica count from the chart values and tries to reconcile it back. Adding `ignoreDifferences` on `spec.replicas` for the Deployment prevents this fight:

```yaml
ignoreDifferences:
  - group: apps
    kind: Deployment
    name: litellm
    namespace: litellm
    jsonPointers:
      - /spec/replicas
```

## Phase 3: Sympozium Blue-Green

### Why Sympozium

Sympozium's API server is fully stateless — all persistent state lives in the NATS JetStream StatefulSet. The web UI pod serves on port 8080 with no local storage, making it an ideal blue-green candidate.

Paperclip was originally considered but has a RWO PVC that prevents running two copies simultaneously. Argo Rollouts has no `recreate` strategy either — only `canary` and `blueGreen` — so Paperclip stays as a plain Deployment. See the gotchas section for details.

### Blue-Green Strategy

```yaml
strategy:
  blueGreen:
    activeService: sympozium-apiserver-lb
    previewService: sympozium-apiserver-preview
    autoPromotionEnabled: false
    prePromotionAnalysis:
      templates:
        - templateName: sympozium-health
```

The Rollout controller starts the green stack, runs a pre-promotion health analysis (HTTP GET on `/healthz` via the preview service), and then waits for manual promotion. The active LB service continues serving blue the entire time.

Unlike canary, blue-green also requires `ignoreDifferences` on the service selectors — the Rollout controller adds a `rollouts-pod-template-hash` label to the active and preview service selectors to route traffic to the correct ReplicaSet.

## Operating Rollouts

### Canary Commands (LiteLLM)

```bash
# Watch rollout status
kubectl argo rollouts get rollout litellm -n litellm --watch

# Advance past a pause step
kubectl argo rollouts promote litellm -n litellm

# Abort and roll back to stable
kubectl argo rollouts abort litellm -n litellm

# Force promote to 100% (skip remaining steps)
kubectl argo rollouts promote litellm -n litellm --full
```

### Blue-Green Commands (Sympozium)

```bash
# Watch rollout status
kubectl argo rollouts get rollout sympozium-apiserver -n sympozium-system --watch

# Promote green to active
kubectl argo rollouts promote sympozium-apiserver -n sympozium-system

# Abort — keeps blue as active, tears down green
kubectl argo rollouts abort sympozium-apiserver -n sympozium-system
```

## Manual Operations

### Install kubectl-argo-rollouts Plugin

```yaml
# manual-operation
id: deploy-install-kubectl-plugin
layer: deploy
app: argo-rollouts
plan: docs/superpowers/specs/2026-03-25--deploy--argo-rollouts-design.md
when: After controller is deployed — before operating any rollouts
why_manual: CLI plugin is a local developer tool, not a cluster resource
commands:
  - "curl -LO https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-darwin-amd64"
  - "chmod +x kubectl-argo-rollouts-darwin-amd64 && sudo mv kubectl-argo-rollouts-darwin-amd64 /usr/local/bin/kubectl-argo-rollouts"
verify:
  - "kubectl argo rollouts version"
status: done
```

## Gotchas

- **Argo Rollouts only supports `canary` and `blueGreen`** — there is no `recreate` strategy. Stateful apps with RWO PVCs that need Recreate behavior must stay as plain Deployments.
- **`AnalysisTemplate` has no `inconclusiveCondition` field** — NaN results implicitly match neither `successCondition` nor `failureCondition` and are automatically treated as inconclusive. We discovered this the hard way when the ServerSideApply rejected the manifest.
- **Prometheus conditions use `result[0]`** — scalar query results require array indexing syntax, not bare `result`.
- **`workloadRef` scales the Deployment to 0** — this is expected. The Rollout controller manages pods directly. ArgoCD needs `ignoreDifferences` on `spec.replicas` to avoid fighting.
- **Blue-green modifies service selectors** — the Rollout controller adds `rollouts-pod-template-hash` labels. ArgoCD needs `ignoreDifferences` on `spec.selector` for the service resources plus `RespectIgnoreDifferences=true` in the sync options.
- **Cilium plugin downloads at controller startup** — requires internet access on first boot. Subsequent restarts use the cached binary.
- **Pin the image tag** — `pullPolicy: Always` with a mutable tag makes canary non-deterministic.

## References

- [Argo Rollouts documentation](https://argoproj.github.io/argo-rollouts/)
- [Cilium traffic router plugin](https://github.com/argoproj-labs/rollouts-plugin-trafficrouter-cilium)
- [workloadRef feature](https://argoproj.github.io/argo-rollouts/features/workload-references/)
- [AnalysisTemplate spec](https://argoproj.github.io/argo-rollouts/features/analysis/)
