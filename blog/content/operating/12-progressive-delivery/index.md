---
title: "Operating on Progressive Delivery"
date: 2026-03-27
draft: false
tags: ["operations", "argo-rollouts", "canary", "blue-green", "litellm", "sympozium"]
summary: "Day-to-day commands for managing Argo Rollouts — promoting canary steps, switching blue-green, inspecting analysis results, and handling sparse-traffic pauses."
weight: 112
cover:
  image: cover.png
  alt: "Frank monitoring rollout dashboards and directing traffic between pod versions"
  relative: true
---

This is the operational companion to [Progressive Delivery with Argo Rollouts]({{< relref "/building/19-progressive-delivery" >}}). That post explains the architecture and deployment. This one is the day-to-day runbook for promoting rollouts, interpreting analysis results, and recovering from stuck or failed states.

## What "Healthy" Looks Like

The progressive delivery stack is healthy when:
- The `argo-rollouts` controller pod is running in the `argo-rollouts` namespace
- LiteLLM Rollout shows `phase: Healthy` with pods serving at `192.168.55.206:4000`
- Sympozium Rollout shows `phase: Healthy` with pods serving at `192.168.55.207:8080`
- No `Degraded` or `Paused` rollouts exist (unless you're mid-rollout)

## Observing State

### Controller Health

```bash
# Check the controller is running
kubectl get pods -n argo-rollouts

# Check the Cilium plugin loaded successfully (look for plugin registration in logs)
kubectl logs -n argo-rollouts deploy/argo-rollouts --tail=20 | grep -i plugin
```

### Rollout Status (All Namespaces)

```bash
# Quick overview of all rollouts
kubectl get rollout -A

# Detailed status with the kubectl plugin
kubectl argo rollouts get rollout litellm -n litellm
kubectl argo rollouts get rollout sympozium-apiserver -n sympozium-system

# Watch a rollout in real-time (live-updating dashboard)
kubectl argo rollouts get rollout litellm -n litellm --watch
```

### Analysis Results

```bash
# List recent analysis runs
kubectl get analysisrun -n litellm --sort-by=.metadata.creationTimestamp

# Check a specific analysis run's results
kubectl get analysisrun -n litellm <name> -o yaml | grep -A20 "status:"

# Check if AnalysisTemplates exist
kubectl get analysistemplate -A
```

## Canary Operations (LiteLLM)

### Triggering a Canary

A canary starts automatically when the LiteLLM Deployment spec changes. The typical trigger is bumping the image tag in `apps/litellm/values.yaml`:

```yaml
image:
  tag: "main-v1.83.0-stable"  # was main-v1.82.3-stable
```

Commit, push, and ArgoCD syncs the Deployment. The Rollout controller detects the spec change and begins the canary.

### Promoting Through Steps

The canary follows this sequence:

```
20% traffic → pause → 5-min VictoriaMetrics analysis →
50% traffic → pause → 5-min analysis →
100% (full promotion)
```

Each `pause` step waits for manual promotion:

```bash
# Advance past the current pause step
kubectl argo rollouts promote litellm -n litellm

# Skip ALL remaining steps and promote to 100% immediately
kubectl argo rollouts promote litellm -n litellm --full
```

### Handling Inconclusive Analysis

In a homelab with bursty traffic, the VictoriaMetrics error-rate query often returns NaN (zero requests in the window). Argo Rollouts treats NaN as **inconclusive** — it matches neither the success nor failure condition. After 3 consecutive inconclusive results (15 minutes), the analysis aborts.

When analysis is inconclusive:

```bash
# Check the analysis run status
kubectl get analysisrun -n litellm -l rollouts-pod-template-hash --sort-by=.metadata.creationTimestamp | tail -3

# Option 1: Generate some traffic, then promote to re-trigger analysis
curl http://192.168.55.206:4000/v1/models -H "Authorization: Bearer $LITELLM_KEY"
kubectl argo rollouts promote litellm -n litellm

# Option 2: Force promote if you're confident the release is fine
kubectl argo rollouts promote litellm -n litellm --full
```

### Aborting a Canary

```bash
# Abort — reverts traffic to 100% stable, scales down canary pods
kubectl argo rollouts abort litellm -n litellm

# After aborting, the Rollout is in a "Degraded" state. To retry:
kubectl argo rollouts retry rollout litellm -n litellm
```

## Blue-Green Operations (Sympozium)

### Triggering a Blue-Green

Like the canary, a blue-green starts when the Deployment spec changes. Bump the image tag in `apps/sympozium/values.yaml` or update the chart `targetRevision` in `apps/root/templates/sympozium.yaml`.

### Promotion Flow

1. Argo Rollouts creates the green (preview) ReplicaSet
2. Pre-promotion analysis runs (HTTP health check on `/healthz` via the preview service)
3. If health passes → Rollout waits for manual promotion
4. You promote → traffic switches atomically from blue to green

```bash
# Watch the rollout (shows blue/green ReplicaSets and analysis state)
kubectl argo rollouts get rollout sympozium-apiserver -n sympozium-system --watch

# Smoke-test the preview stack before promoting
kubectl port-forward svc/sympozium-apiserver-preview -n sympozium-system 9090:8080
# Visit http://localhost:9090 — this hits the green stack only

# Promote green to active
kubectl argo rollouts promote sympozium-apiserver -n sympozium-system
```

### Aborting a Blue-Green

```bash
# Abort — keeps blue as active, tears down green ReplicaSet
kubectl argo rollouts abort sympozium-apiserver -n sympozium-system
```

## Troubleshooting

### Rollout Stuck in "Degraded"

This usually means the Rollout spec references something that doesn't exist:

```bash
# Check the Rollout status message
kubectl get rollout <name> -n <ns> -o yaml | grep -A5 "phase:"

# Common causes:
# - AnalysisTemplate not found (ArgoCD hasn't synced it yet)
# - Service not found (preview service missing)
# - workloadRef Deployment not found
```

Fix: ensure all referenced resources exist, then the controller self-heals.

### ArgoCD Shows Deployment at 0 Replicas

This is **expected behavior** when using `workloadRef`. The Rollout controller scales the Helm chart's Deployment to 0 and manages pods directly. The `ignoreDifferences` on `spec.replicas` prevents ArgoCD from fighting this.

If ArgoCD shows the Deployment as `OutOfSync` on replicas, check that `ignoreDifferences` is configured in the Application CR.

### Rollout Pods Not Starting

```bash
# Check the Rollout's ReplicaSets
kubectl get rs -n <ns> -l rollouts-pod-template-hash

# Check pod events
kubectl describe pod -n <ns> -l rollouts-pod-template-hash=<hash>

# For canary: check if the canary service exists and has the right selector
kubectl get svc litellm-canary -n litellm -o yaml | grep -A5 selector
```

### CiliumEnvoyConfig Not Created (Canary)

```bash
# Check if the Cilium plugin is loaded
kubectl logs -n argo-rollouts deploy/argo-rollouts | grep -i cilium

# Check for CiliumEnvoyConfig objects
kubectl get ciliumenvoyconfig -A

# Check RBAC — controller needs access to cilium.io CRDs
kubectl auth can-i create ciliumenvoyconfigs --as=system:serviceaccount:argo-rollouts:argo-rollouts
```

## References

- [Argo Rollouts kubectl plugin](https://argoproj.github.io/argo-rollouts/features/kubectl-plugin/)
- [Analysis and progressive delivery](https://argoproj.github.io/argo-rollouts/features/analysis/)
- [Troubleshooting guide](https://argoproj.github.io/argo-rollouts/FAQ/)
