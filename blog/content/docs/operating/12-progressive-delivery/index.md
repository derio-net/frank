---
title: "Operating on Progressive Delivery"
series: ["operating"]
layer: deploy
date: 2026-03-27
draft: false
tags: ["operations", "argo-rollouts", "canary", "blue-green", "litellm", "sympozium"]
summary: "Day-to-day commands for managing Argo Rollouts — promoting canary steps, switching blue-green, inspecting analysis results, and handling sparse-traffic pauses."
weight: 13
---

This is the operational companion to [Progressive Delivery with Argo Rollouts]({{< relref "/docs/building/19-progressive-delivery" >}}). That post explains the architecture and deployment. This one is the day-to-day runbook for promoting rollouts, interpreting analysis results, and recovering from stuck or failed states.

> **Update: 2026-05-04** — The litellm canary sections were rewritten twice in one day. First rewrite was for the replica-count canary with `AnalysisRun` between each pause. Second rewrite is for **pause-only canary** (no AnalysisRun) — because the AnalysisTemplate referenced a metric (`litellm_request_total`) that doesn't exist on this cluster (LiteLLM's Prometheus integration is an Enterprise-paid feature; the OSS image we run doesn't emit it). All sample outputs below are now real captured output from the 2026-05-04 rehearsal, not typed-up reconstructions of expected shape. The sympozium blue-green sections are unchanged. Full postmortem with all five latent bugs in the [building post]({{< relref "/docs/building/19-progressive-delivery#update-2026-05-04--the-canary-that-wasnt" >}}). The Path B spec for restoring metric-gated promotion is at `docs/superpowers/specs/2026-05-04--deploy--litellm-canary-metric-source-design.md`.

## What "Healthy" Looks Like

The progressive delivery stack is healthy when:
- The `argo-rollouts` controller pod is running in the `argo-rollouts` namespace and its log tail is free of `failed to get traffic router plugin` errors
- LiteLLM Rollout shows `Status: Healthy` with **5/5 pods Ready** under one ReplicaSet (the current stable). `Step` is *not* shown — at-rest Rollouts have no current step
- Sympozium Rollout shows `Status: Healthy` with the active service serving at `192.168.55.207:8080`
- No `Degraded` or `Paused` rollouts exist (unless you're mid-rollout)

## Observing State

### Controller Health

```bash
# Check the controller is running
kubectl get pods -n argo-rollouts

# Check the controller has clean reconciliation (no plugin / RBAC / sync errors).
# After 2026-05-04 we no longer load any traffic-router plugin — clean log.
kubectl logs -n argo-rollouts deploy/argo-rollouts --tail=50 | grep -iE "error|fail|plugin" | head -20
# Expected: empty, or only benign "informer cache synced" / startup lines.
# RED FLAG: "failed to get traffic router plugin" — see the building-post postmortem.
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

A **healthy at-rest** litellm Rollout looks like this — one ReplicaSet active, 5 pods Ready, `Step: 4/4` (the post-promote terminal state) (real capture, 2026-05-04 17:54):

```console
$ kubectl argo rollouts get rollout litellm -n litellm
Name:            litellm
Namespace:       litellm
Status:          ✔ Healthy
Strategy:        Canary
  Step:          4/4
  SetWeight:     100
  ActualWeight:  100
Images:          ghcr.io/berriai/litellm-database:main-v1.82.3-stable (stable)
Replicas:
  Desired:       5
  Current:       5
  Updated:       5
  Ready:         5
  Available:     5

NAME                                 KIND        STATUS        AGE  INFO
⟳ litellm                            Rollout     ✔ Healthy
├──# revision:N
│  └──⧉ litellm-<current-hash>       ReplicaSet  ✔ Healthy          stable
│     └──[5 pods, one per node — mini-1, mini-2, mini-3, gpu-1, pc-1]
└──# revision:N-1
   └──⧉ litellm-<previous-hash>      ReplicaSet  • ScaledDown
```

The previous-revision RS may linger as `ScaledDown` (0 replicas) for a while — that's fine. It's GC'd eventually.

A Rollout **mid-canary at the first pause** looks like this — two active ReplicaSets, 4 stable + 1 canary pod, paused on Step 1 of 4 (real capture, 2026-05-04 17:53):

```console
$ kubectl argo rollouts get rollout litellm -n litellm
Status:          ॥ Paused
Message:         CanaryPauseStep
Strategy:        Canary
  Step:          1/4
  SetWeight:     20
  ActualWeight:  20
Replicas:
  Desired:       5
  Current:       5
  Updated:       1   ← canary pod, freshly come up
  Ready:         5
  Available:     5

NAME                                 KIND         STATUS     AGE  INFO
⟳ litellm                            Rollout      ॥ Paused
├──# revision:N+1
│  └──⧉ litellm-<newhash>   ReplicaSet  ✔ Healthy        canary
└──# revision:N
   └──⧉ litellm-<oldhash>   ReplicaSet  ✔ Healthy        stable
```

A Rollout **at the second pause (Step 3/4, SetWeight: 50)** has the surprising property of running **6 pods, not 5** (real capture, 2026-05-04 17:57):

```console
$ kubectl argo rollouts get rollout litellm -n litellm
Status:          ॥ Paused
Message:         CanaryPauseStep
Strategy:        Canary
  Step:          3/4
  SetWeight:     50
  ActualWeight:  50
Replicas:
  Desired:       5
  Current:       6     ← 6, not 5! maxSurge transient
  Updated:       3
  Ready:         6
  Available:     6

NAME                                 KIND         STATUS     AGE    INFO
⟳ litellm                            Rollout      ॥ Paused
├──# revision:N+1
│  └──⧉ litellm-<newhash>            ReplicaSet   ✔ Healthy        canary
│     └──[3 pods]
└──# revision:N
   └──⧉ litellm-<oldhash>            ReplicaSet   ✔ Healthy        stable
      └──[3 pods]
```

Default `maxSurge: 25%` (= 2 with replicas=5) brings the canary RS up to 3 *before* the controller scales the stable RS down — at this moment in the cycle, `total = 3 + 3 = 6`. `ActualWeight: 50` is computed as `canary_count / total_count` (3/6 = 50%), not `canary_count / desired_replicas` (would read 60%). This is the property that makes the canary "no traffic loss" — every promote-step's first action is to bring up new pods, only after they're Ready does the old ReplicaSet shed pods. Once the operator promotes again, the canary RS scales 3 → 5 and the old stable RS scales 3 → 0.

> **Historical note:** between 2026-03-26 and 2026-05-04 this section showed the *broken* state (`Status: Progressing, Step: 0/6, Desired: 1, Current: 0, ScaledDown ReplicaSet`) as the example, because the original Cilium plugin design left the Rollout permanently stuck there and we didn't realise it was the failure mode rather than the steady state. If you ever see *that* shape again on a healthy-looking app, you have a controller that can't advance reconciliation — most likely a missing or unloadable traffic-router plugin, or RBAC missing for the controller's ServiceAccount. Look at the controller pod logs.

### Analysis Results (vestigial in pause-only mode, but useful for inspecting historical AnalysisRuns)

The current litellm canary doesn't spawn AnalysisRuns (no `analysis` step in the Rollout — see the building post's Postscript on Bug #5 for why). These commands are still useful for inspecting *historical* AnalysisRuns from prior canary cycles, and for the sympozium blue-green which still uses an HTTP healthcheck AnalysisTemplate.

```bash
# List analysis runs across all namespaces (litellm should typically be empty
# of new ones; sympozium spawns one per blue-green cycle)
kubectl get analysisrun -A --sort-by=.metadata.creationTimestamp

# Check a specific analysis run's results
kubectl get analysisrun -n <ns> <name> -o yaml | grep -A20 "status:"

# Check if AnalysisTemplates exist (litellm-error-rate is kept as a scaffold
# pending Path B implementation; sympozium-health is in active use)
kubectl get analysistemplate -A
```

## Canary Operations (LiteLLM)

For end-to-end observation of a real LiteLLM canary (image bump, model-list change, etc.), use the dedicated [LiteLLM Canary Observation runbook](https://github.com/derio-net/frank/blob/main/docs/runbooks/litellm-canary-observation.md). The reference below is the day-to-day command surface; the runbook is the full three-terminal flow with synthetic-traffic generation and per-step verification.

### Triggering a Canary

A canary starts automatically when the LiteLLM Deployment spec changes. The typical trigger is bumping the image tag in `apps/litellm/values.yaml`:

```yaml
image:
  tag: "main-v1.83.14-stable"  # was main-v1.82.3-stable
```

Commit, push, and ArgoCD syncs the Deployment. The Rollout controller detects the spec change and begins the canary by bringing up new pods alongside the existing ones (replica-count canary — see the [building post]({{< relref "/docs/building/19-progressive-delivery#update-2026-05-04--the-canary-that-wasnt" >}})).

### Promoting Through Steps

With `replicas: 5`, the **pause-only** canary follows this sequence (no AnalysisRun between pauses; promotion is fully manual):

```
Step 1/4 — setWeight 20 → 1 canary + 4 stable → pause indefinitely
                                              → operator promote →
Step 3/4 — setWeight 50 → 3 canary + 3 stable (mid-state, maxSurge transient)
                                              → pause indefinitely
                                              → operator promote →
Step 4/4 — 5 canary, 0 stable (old RS scaled to 0) → Healthy
```

The mid-state at SetWeight 50 has **6 pods**, not 5. Default `maxSurge: 25%` (= 2 with replicas=5) brings up the canary RS *before* scaling stable down. `ActualWeight: 50` is computed as `canary_count / total_count` (3/6), which is why it reads 50 even though `canary / desired_replicas` is 60%. This is the property that makes the canary "no traffic loss."

```bash
# Advance past the current pause step
kubectl argo rollouts promote litellm -n litellm

# Skip ALL remaining steps and promote to 100% immediately
kubectl argo rollouts promote litellm -n litellm --full
```

### What if I see a stale `⚠ AnalysisRun` in the tree?

Cosmetic only. AnalysisRun objects from prior canary cycles persist until the ReplicaSet they're tied to is garbage-collected. The `⚠` count next to them is from a *prior* aborted attempt, not the current one. The current pause-only canary doesn't spawn AnalysisRuns at all (no `analysis` step in the Rollout spec).

```bash
# Optional cleanup after a current rollout completes:
kubectl get analysisrun -n litellm
kubectl delete analysisrun -n litellm <old-name>
```

If you see an AnalysisRun with `phase: Error` and message `reflect: slice index out of range`, that's a regression — the Rollout has been reverted to the metric-gated design but the metric source still doesn't exist. See [the Path B spec](https://github.com/derio-net/frank/blob/main/docs/superpowers/specs/2026-05-04--deploy--litellm-canary-metric-source-design.md) for restoring metric-gated promotion properly.

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

<!-- MEDIA: screenshot | Argo Rollouts dashboard showing a blue-green switch on Sympozium | Run `kubectl argo rollouts dashboard` and navigate to the sympozium-apiserver rollout during a blue-green promotion, capture the blue/green pair with analysis status -->
<!-- {{</* screenshot src="sympozium-bluegreen-promote.png" caption="Argo Rollouts dashboard during a Sympozium blue-green promotion" */>}} -->

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
```

### Rollout Stuck at Step 0/6 with No Progress

This is the failure shape we lived with for 39 days on litellm. The Rollout reports `Status: Progressing` and `Step: 0/6`, but `Desired: N, Current: 0, Updated: 0` and the controller never makes any move. Almost always means the controller can't advance reconciliation past traffic-router init or RBAC validation.

```bash
# 1. Check the controller log for the actual error
kubectl logs -n argo-rollouts deploy/argo-rollouts --tail=100 | grep -iE "error|failed" | tail -20

# 2. Common culprits, in order of frequency:
#    a. trafficRouting plugin referenced in the Rollout but not configured in
#       argo-rollouts-config CM. Check the Rollout spec:
kubectl get rollout <name> -n <ns> -o yaml | grep -A 3 trafficRouting
#       If it lists a plugin, that plugin must appear in:
kubectl get cm argo-rollouts-config -n argo-rollouts -o yaml | grep -A 3 trafficRouterPlugins
#    b. Missing RBAC for the controller's ServiceAccount on a CRD it tries
#       to create (e.g. CiliumEnvoyConfig, VirtualService, etc.).
#    c. workloadRef points at a Deployment that doesn't exist.

# 3. The Helm-managed Deployment will be at replicas: N (NOT 0) in this state
#    because the controller never invoked workloadRef-scaling. You're getting
#    a vanilla RollingUpdate, not a canary. Check:
kubectl get deploy -n <ns> -l app.kubernetes.io/name=<app> -o wide
```

## References

- [Argo Rollouts kubectl plugin](https://argoproj.github.io/argo-rollouts/features/kubectl-plugin/)
- [Analysis and progressive delivery](https://argoproj.github.io/argo-rollouts/features/analysis/)
- [Troubleshooting guide](https://argoproj.github.io/argo-rollouts/FAQ/)
