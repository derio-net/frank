# Argo Rollouts — Progressive Delivery Platform

**Date:** 2026-03-25
**Status:** Design
**Layer:** deploy (18)

## Overview

Install Argo Rollouts as a cluster-wide progressive delivery controller, and migrate two workloads to demonstrate each major deployment strategy:

- **LiteLLM Gateway** → canary with Cilium-native traffic splitting and VictoriaMetrics metric-gated analysis
- **Sympozium** → blue-green with manual promotion gate and pre-promotion HTTP healthcheck (stateless API server — all state in NATS JetStream StatefulSet)

The goal is to add safe, observable rollout primitives to the platform — not automation for its own sake. In a homelab with bursty or paused traffic, the human operator remains in the loop; metric analysis acts as a safety net when traffic is flowing, not a hard gate when the cluster is quiet.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  argo-rollouts namespace                                        │
│                                                                 │
│  ┌─────────────────────────────────┐                            │
│  │  argo-rollouts controller       │                            │
│  │  + Cilium traffic router plugin │                            │
│  └──────────┬──────────────────────┘                            │
│             │ watches Rollout CRDs cluster-wide                 │
└─────────────┼───────────────────────────────────────────────────┘
              │
    ┌─────────┴──────────────────────────────────────┐
    │                                                │
    ▼                                                ▼
┌───────────────────────────┐         ┌───────────────────────────────┐
│  litellm namespace        │         │  paperclip-system namespace   │
│                           │         │                               │
│  Rollout/litellm          │         │  Rollout/paperclip            │
│  (workloadRef →           │         │  (replaces Deployment)        │
│   Deployment/litellm)     │         │                               │
│                           │         │  strategy: blueGreen          │
│  strategy: canary         │         │  autoPromotionEnabled: false  │
│  steps:                   │         │                               │
│  - setWeight: 20          │         │  active svc  → LB 55.212      │
│  - pause: {}              │         │  preview svc → ClusterIP      │
│  - analysis               │         │                               │
│  - setWeight: 50          │         │  pre-promotion: HTTP probe    │
│  - pause: {}              │         │  on preview svc               │
│  - analysis               │         └───────────────────────────────┘
│  - setWeight: 100         │
│                           │
│  stableService: litellm   │  ◀── existing Helm svc (LB 55.206)
│  canaryService: litellm-c │  ◀── new ClusterIP svc (manifests)
│                           │
│  plugin: Cilium           │  ──▶ CiliumEnvoyConfig (traffic weights)
│                           │
│  AnalysisTemplate         │  ──▶ VictoriaMetrics (Prometheus API)
│  (error rate < 5%)        │       inconclusiveCondition: rate < 10 req
└───────────────────────────┘
```

## Phase 1: Controller Install

### ArgoCD Application

New app: `apps/argo-rollouts/values.yaml` + `apps/root/templates/argo-rollouts.yaml`

| Field | Value |
|-------|-------|
| Chart | `argo-rollouts` from `https://argoproj.github.io/argo-helm` |
| Namespace | `argo-rollouts` |
| Sync options | `ServerSideApply=true`, `prune: false`, `selfHeal: true` |

### Cilium Traffic Router Plugin

The Argo Rollouts controller loads traffic router plugins at startup via a `ConfigMap` named `argo-rollouts-config` in the `argo-rollouts` namespace. The Cilium plugin (`argoproj-labs/rollouts-plugin-trafficrouter-cilium`) is referenced by a **pinned download URL** (specific release tag, not `latest`) — the controller fetches and caches it on first boot. Subsequent restarts use the cached binary from the controller pod's filesystem.

**Accepted risk:** the controller requires internet access on first startup to download the plugin. This is acceptable for a homelab but must be noted for air-gapped environments. Pin the URL to a specific version in the ConfigMap to ensure reproducibility.

Plugin config manifest: `apps/argo-rollouts/manifests/plugin-config.yaml`

### RBAC for CiliumEnvoyConfig

The Argo Rollouts controller must be able to create/update/delete `CiliumEnvoyConfig` objects (a Cilium CRD). The default Helm chart RBAC does not include Cilium CRD permissions. A supplemental `ClusterRole` and `ClusterRoleBinding` must be added to `apps/argo-rollouts/manifests/` granting the controller's ServiceAccount access to `cilium.io/ciliumenvoyconfigs`.

### Layer Registration

Add to `docs/layers.yaml`:
```yaml
- code: deploy
  number: 18
  name: Progressive Delivery
  description: Argo Rollouts, canary and blue-green deployment strategies
```

### Manual Operations

**Install kubectl plugin (local):**
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
status: pending
```

## Phase 2: LiteLLM Canary

### Challenge: Helm-Managed Deployment

The LiteLLM Helm chart owns its `Deployment`. Rather than modifying chart internals, we use Argo Rollouts' `workloadRef` feature: a `Rollout` object references the Helm chart's `Deployment` by name. The Rollout controller scales the Deployment to 0 and takes over pod management. When the chart's `Deployment` spec changes (e.g., a chart version bump updates the image), the Rollout detects it and initiates a canary.

This keeps the Helm chart as the source of truth for LiteLLM configuration while adding progressive delivery on top.

### Image Tag Pinning

The current `values.yaml` uses `tag: main-stable` with `pullPolicy: Always`. For reproducible canary demos, pin to a specific version (e.g., `v1.x.y`). Bumping the tag in `values.yaml` and committing is the trigger for a rollout.

### Service Topology

| Service | Type | IP | Managed By |
|---------|------|----|------------|
| `litellm` | LoadBalancer | 192.168.55.206 | Helm chart (stable) |
| `litellm-canary` | ClusterIP | internal | New manifest (canary) |

The Rollout spec references both. The Cilium plugin creates a `CiliumEnvoyConfig` that splits traffic between them according to the current canary weight.

**Cilium L2 LB + CiliumEnvoyConfig compatibility:** The Cilium traffic router plugin intercepts traffic at the ClusterIP/eBPF level, which should work regardless of whether the stable service has `type: LoadBalancer`. However, this is an uncommon configuration in the plugin's documented examples (which show ClusterIP pairs). During implementation, verify that the `CiliumEnvoyConfig` correctly intercepts external traffic arriving via the L2 LB IP. If not, the fallback is to change the stable service to `ClusterIP` and add a separate `LoadBalancer` service (following the Sympozium pattern) to hold the static IP.

### Canary Steps

```
20% → pause (manual) → analysis (5 min) →
50% → pause (manual) → analysis (5 min) →
promote to 100%
```

Manual `pause` steps require `kubectl argo rollouts promote litellm -n litellm` to advance. This is intentional: in a homelab, you wait until consumers (Paperclip, Sympozium) are active before running analysis.

### Analysis Template

Metric provider: Prometheus (VictoriaMetrics exposes a Prometheus-compatible API at its internal service URL in the `monitoring` namespace).

**Primary metric — error rate:**
```promql
sum(rate(litellm_request_total{status=~"5.."}[5m]))
/
sum(rate(litellm_request_total[5m]))
```
- `successCondition`: `result < 0.05` (less than 5% errors)
- `failureCondition`: `result >= 0.05`
- `inconclusiveCondition`: `isNaN(result) || sum(rate(litellm_request_total[5m])) < 10` — if fewer than 10 requests in the window, mark inconclusive rather than aborting
- `inconclusiveLimit: 3` — after 3 consecutive inconclusive results (15 min of sparse traffic), the analysis aborts and the Rollout pauses indefinitely

**Inconclusive behaviour:** when an AnalysisRun returns `Inconclusive`, the Rollout pauses and waits. The operator checks the situation (Is Ollama up? Are consumers active?) then either:

- **Resume:** wait for traffic to pick up, then re-run analysis via `kubectl argo rollouts promote litellm -n litellm`
- **Force promote:** skip remaining analysis with `--full` if confident the release is healthy
- **Abort:** roll back to stable with `kubectl argo rollouts abort`

**VictoriaMetrics address:** the AnalysisTemplate `provider.prometheus.address` must be set to the in-cluster VMSingle service URL (e.g., `http://victoria-metrics-victoria-metrics-single-server.monitoring.svc.cluster.local:8428`). Determine the exact service name during implementation via `kubectl get svc -n monitoring`.

### New Manifests

Added to `apps/litellm/manifests/` (deployed by existing `litellm-extras` ArgoCD app):

| File | Resource |
|------|----------|
| `rollout.yaml` | `Rollout/litellm` with `workloadRef`, canary strategy, service refs |
| `service-canary.yaml` | `Service/litellm-canary` (ClusterIP) |
| `analysis-template.yaml` | `AnalysisTemplate/litellm-error-rate` |

## Phase 3: Sympozium Blue-Green

### Why Sympozium

Sympozium's API server pod is fully stateless — all persistent state lives in the NATS JetStream StatefulSet (separate component with its own PVC). The API server serves the web UI and API on port 8080 with no local storage. This makes it an ideal blue-green candidate.

Paperclip was originally considered but dropped: Argo Rollouts has no `recreate` strategy, and the RWO PVC prevents `blueGreen`. Paperclip stays as a plain Deployment.

### Architecture

Like LiteLLM, Sympozium uses a Helm chart. The Rollout uses `workloadRef` to reference the chart's `Deployment/sympozium-apiserver`, scaling it to 0 while the Rollout controller manages pods directly.

| Service | Type | IP | Role |
|---------|------|----|------|
| `sympozium-apiserver-lb` | LoadBalancer | 192.168.55.207 | Active (blue) |
| `sympozium-apiserver-preview` | ClusterIP | internal | Preview (green) |

### Strategy

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

### Pre-Promotion Analysis

`AnalysisTemplate/sympozium-health` — HTTP GET on the preview service's `/healthz` endpoint. 3 checks at 10-second intervals. No VictoriaMetrics dependency — works regardless of cluster traffic. If the green stack fails the health probe, the Rollout stays on blue.

### ArgoCD Configuration

- `sympozium` Application: add `ignoreDifferences` on `spec.replicas` for `Deployment/sympozium-apiserver` (Rollout controller scales it to 0)
- `sympozium-extras` Application: add `ignoreDifferences` on `spec.selector` for `Service` kind (Rollout controller adds `rollouts-pod-template-hash` to service selectors) + `RespectIgnoreDifferences=true`

### New Manifests

Added to `apps/sympozium-extras/manifests/`:

| File | Resource |
|------|----------|
| `rollout.yaml` | `Rollout/sympozium-apiserver` with `workloadRef`, blue-green strategy |
| `service-preview.yaml` | `Service/sympozium-apiserver-preview` (ClusterIP) |
| `analysis-health.yaml` | `AnalysisTemplate/sympozium-health` (HTTP healthcheck) |

## Operating Rollouts

### Canary (LiteLLM)

```bash
# Watch rollout status
kubectl argo rollouts get rollout litellm -n litellm --watch

# Advance past a pause step (when consumers are active)
kubectl argo rollouts promote litellm -n litellm

# Abort and roll back to stable
kubectl argo rollouts abort litellm -n litellm

# Force promote to 100% (skip remaining steps)
kubectl argo rollouts promote litellm -n litellm --full
```

### Blue-Green (Sympozium)

```bash
# Watch rollout status
kubectl argo rollouts get rollout sympozium-apiserver -n sympozium-system --watch

# Promote green to active (after pre-promotion analysis passes)
kubectl argo rollouts promote sympozium-apiserver -n sympozium-system

# Abort — keeps blue as active, tears down green
kubectl argo rollouts abort sympozium-apiserver -n sympozium-system
```

## Gotchas

- **Argo Rollouts only supports `canary` and `blueGreen`** — there is no `recreate` strategy. Stateful apps with RWO PVCs that need Recreate behavior must stay as plain Deployments.
- **Cilium plugin downloads at controller startup** — first boot requires internet access from the `argo-rollouts` pod; subsequent restarts use the cached binary
- **`workloadRef` scales the source Deployment to 0** — after applying the LiteLLM Rollout, the Helm chart's Deployment will show 0/0 replicas; this is expected and correct
- **ArgoCD fights `workloadRef` on `spec.replicas`** — the Rollout controller scales the Helm chart's Deployment to 0; ArgoCD tries to reconcile it back to the chart's replica count. Add `ignoreDifferences` on `spec.replicas` (`jsonPointers: [/spec/replicas]`) in the `litellm` ArgoCD Application. Only `spec.replicas` needs ignoring — the Rollout reads but does not modify `spec.template` in the Deployment, so ArgoCD and the Rollout controller do not conflict there
- **LiteLLM image tag must be pinned** — `main-stable` with `pullPolicy: Always` makes canary non-deterministic; pin to a semver tag before enabling the Rollout
- **VictoriaMetrics internal URL** — the AnalysisTemplate must use the in-cluster service URL for VMSingle (not Grafana's LB IP)
- **`inconclusiveLimit`** — set to a reasonable value (e.g., 3) to prevent infinite inconclusive loops if VictoriaMetrics is down
- **`inconclusiveCondition` does not exist** — the AnalysisTemplate CRD has no such field. NaN results implicitly match neither `successCondition` nor `failureCondition` and are automatically inconclusive.
- **Prometheus `successCondition`/`failureCondition` use `result[0]`** — scalar query results require array indexing syntax, not bare `result`.

## Out of Scope

- Argo Rollouts dashboard UI and Grafana dashboard (the kubectl plugin is sufficient; the official Argo Rollouts Grafana dashboard can be added later as a ConfigMap to the monitoring stack)
- Migrating other workloads (Authentik, Ollama, Infisical are stateful and singleton — blue-green adds complexity without benefit)
- Automated image tag bumps via Argo CD Image Updater (separate concern)
- Istio/Gateway API traffic management (Cilium is already the CNI)
- Multi-cluster rollouts

## References

- [Argo Rollouts documentation](https://argoproj.github.io/argo-rollouts/)
- [Argo Rollouts Helm chart](https://github.com/argoproj/argo-helm/tree/main/charts/argo-rollouts)
- [Cilium traffic router plugin](https://github.com/argoproj-labs/rollouts-plugin-trafficrouter-cilium)
- [workloadRef feature](https://argoproj.github.io/argo-rollouts/features/workload-references/)
- [AnalysisTemplate spec](https://argoproj.github.io/argo-rollouts/features/analysis/)
- [LiteLLM design](docs/superpowers/specs/2026-03-09--infer--ollama-litellm-design.md)
- [Paperclip design](docs/superpowers/specs/2026-03-14--orch--paperclip-design.md)
