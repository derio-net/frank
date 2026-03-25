# Argo Rollouts — Progressive Delivery Platform

**Date:** 2026-03-25
**Status:** Design
**Layer:** deploy (18)

## Overview

Install Argo Rollouts as a cluster-wide progressive delivery controller, and migrate two workloads to demonstrate each major deployment strategy:

- **LiteLLM Gateway** → canary with Cilium-native traffic splitting and VictoriaMetrics metric-gated analysis
- **Paperclip** → blue-green with manual promotion gate and pre-promotion healthcheck

The goal is to add safe, observable rollout primitives to the platform — not automation for its own sake. In a homelab with bursty or paused traffic, the human operator remains in the loop; metric analysis acts as a safety net when traffic is flowing, not a hard gate when the cluster is quiet.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  argo-rollouts namespace                                         │
│                                                                  │
│  ┌─────────────────────────────────┐                            │
│  │  argo-rollouts controller       │                            │
│  │  + Cilium traffic router plugin │                            │
│  └──────────┬──────────────────────┘                            │
│             │ watches Rollout CRDs cluster-wide                  │
└─────────────┼───────────────────────────────────────────────────┘
              │
    ┌─────────┴──────────────────────────────────────┐
    │                                                 │
    ▼                                                 ▼
┌──────────────────────────┐         ┌──────────────────────────────┐
│  litellm namespace        │         │  paperclip-system namespace   │
│                           │         │                               │
│  Rollout/litellm          │         │  Rollout/paperclip            │
│  (workloadRef →           │         │  (replaces Deployment)        │
│   Deployment/litellm)     │         │                               │
│                           │         │  strategy: blueGreen          │
│  strategy: canary         │         │  autoPromotionEnabled: false  │
│  steps:                   │         │                               │
│  - setWeight: 20          │         │  active svc  → LB 55.212     │
│  - pause: {}              │         │  preview svc → ClusterIP      │
│  - analysis               │         │                               │
│  - setWeight: 50          │         │  pre-promotion: HTTP probe    │
│  - pause: {}              │         │  on preview svc               │
│  - analysis               │         └──────────────────────────────┘
│  - setWeight: 100         │
│                           │
│  stableService: litellm   │  ◀── existing Helm svc (LB 55.206)
│  canaryService: litellm-c │  ◀── new ClusterIP svc (manifests)
│                           │
│  plugin: Cilium           │  ──▶ CiliumEnvoyConfig (traffic weights)
│                           │
│  AnalysisTemplate         │  ──▶ VictoriaMetrics (Prometheus API)
│  (error rate < 5%)        │       inconclusiveCondition: rate < 10 req
└──────────────────────────┘
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

The Argo Rollouts controller loads traffic router plugins at startup via a `ConfigMap` named `argo-rollouts-config` in the `argo-rollouts` namespace. The Cilium plugin (`argoproj-labs/rollouts-plugin-trafficrouter-cilium`) is referenced by download URL — the controller fetches and caches it on first run.

Plugin config manifest: `apps/argo-rollouts/manifests/plugin-config.yaml`

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

**Inconclusive behaviour:** the Rollout pauses and waits rather than failing. The operator checks the situation (Is Ollama up? Are consumers active?) and either manually promotes or aborts.

### New Manifests

Added to `apps/litellm/manifests/` (deployed by existing `litellm-extras` ArgoCD app):

| File | Resource |
|------|----------|
| `rollout.yaml` | `Rollout/litellm` with `workloadRef`, canary strategy, service refs |
| `service-canary.yaml` | `Service/litellm-canary` (ClusterIP) |
| `analysis-template.yaml` | `AnalysisTemplate/litellm-error-rate` |

## Phase 3: Paperclip Blue-Green

### Migration

Paperclip uses raw manifests — no Helm chart. Replace `apps/paperclip/manifests/deployment.yaml` directly with an Argo Rollouts `Rollout` resource (same spec, `kind: Rollout`, `apiVersion: argoproj.io/v1alpha1`).

### Strategy

```yaml
strategy:
  blueGreen:
    activeService: paperclip        # existing LB service (55.212)
    previewService: paperclip-preview  # new ClusterIP service
    autoPromotionEnabled: false     # always require manual promote
    prePromotionAnalysis:
      templates:
        - templateName: paperclip-health
```

Add `apps/paperclip/manifests/service-preview.yaml` for the preview ClusterIP service.

### Pre-Promotion Analysis

A lightweight `AnalysisTemplate/paperclip-health` that issues an HTTP GET to the preview service's healthcheck endpoint. No VictoriaMetrics dependency — works regardless of LiteLLM/Ollama state.

If the green stack fails the health probe, the Rollout stays on blue and the operator investigates before re-promoting.

### Database Migration Discipline

Blue-green provides instant cutover but does not solve schema migration safety automatically. The required discipline for any Paperclip version that touches the DB schema:

1. **Expand** — v(N) adds new columns/tables without removing old ones. Both v(N-1) and v(N) can read/write the DB.
2. **Deploy** — blue-green cutover to v(N). If rollback needed, v(N-1) still works with the expanded schema.
3. **Contract** — v(N+1) removes the old columns/tables once v(N) is confirmed stable.

This is not enforced by tooling in this layer — it is a documented requirement for future Paperclip version upgrades.

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

### Blue-Green (Paperclip)

```bash
# Watch rollout status
kubectl argo rollouts get rollout paperclip -n paperclip-system --watch

# Promote green to active (after manual verification on preview svc)
kubectl argo rollouts promote paperclip -n paperclip-system

# Abort — keeps blue as active, tears down green
kubectl argo rollouts abort paperclip -n paperclip-system
```

## Gotchas

- **Cilium plugin downloads at controller startup** — first boot requires internet access from the `argo-rollouts` pod; subsequent restarts use the cached binary
- **`workloadRef` scales the source Deployment to 0** — after applying the LiteLLM Rollout, the Helm chart's Deployment will show 0/0 replicas; this is expected and correct
- **ArgoCD sees the Deployment at 0 replicas** — add an `ignoreDifferences` entry on the Deployment's `spec.replicas` field in the `litellm` app to prevent ArgoCD from fighting with the Rollout controller
- **LiteLLM image tag must be pinned** — `main-stable` with `pullPolicy: Always` makes canary non-deterministic; pin to a semver tag before enabling the Rollout
- **VictoriaMetrics internal URL** — the AnalysisTemplate must use the in-cluster service URL for VMSingle (not Grafana's LB IP)
- **`inconclusiveLimit`** — set to a reasonable value (e.g., 3) to prevent infinite inconclusive loops if VictoriaMetrics is down
- **Blue-green preview service** — Paperclip's `PAPERCLIP_PUBLIC_URL` configmap references the LB IP; the preview stack is only accessible via `kubectl port-forward` or direct pod IP for smoke testing

## Out of Scope

- Argo Rollouts dashboard UI (the kubectl plugin is sufficient for now)
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
