# ArgoCD Drift Cleanup Design

**Layer:** gitops
**Type:** Investigation + fix (extension of layer 6, GitOps)

## Problem

20 of Frank's ArgoCD apps (~33 %) are permanently OutOfSync. The chronic-drift
state is hiding real reconciliation failures (4 apps are stuck in
`Progressing` health) and erodes trust in the sync signal.

## Root causes identified

Seven independent drift classes with different blast radius and fix shape:

| Class | Cause | Apps |
|-------|-------|------|
| A | ExternalSecret CRD schema defaults injected into live objects but absent from git | 10 apps, 16 ES manifests |
| B | `automated.prune: false` stripped from Application CRs as schema default | root → 12 child Applications |
| C | CRDs installed out-of-band without `argocd.argoproj.io/tracking-id` | argo-rollouts (5), tekton-pipelines (6), tekton-dashboard (1) |
| D | Helm subcharts once enabled, now disabled; orphan config resources kept by `prune: false` | gitea (redis-cluster), infisical (nginx+mongodb+redis) |
| E | Namespace owned by two apps (tracking-id conflict) | sympozium-extras ↔ sympozium |
| F | Terminal Job/PipelineRun still tracked by ArgoCD | Job/postgres-vk-init-electric, PipelineRun/test-build-sign-5qtn4 |
| G | Chart-render vs cluster-state spec drift (no live-controller mutation) | victoria-metrics, gpu-operator, vcluster-experiments, infisical-postgresql |

## Design principles

1. **Low-risk first.** Mechanical fixes (E, F, B) run first to drain the noise
   and build confidence. Investigations (G) come last.
2. **Rollback ready.** Every kubectl delete is preceded by a YAML dump to
   `/tmp/argocd-drift/`, restorable via `kubectl apply -f`. Every git change
   is revertible via `git revert`.
3. **Verify between phases.** Don't start the next drift class until the
   previous one has settled (Synced/Healthy for at least 60 s).
4. **Narrowest possible fix.** Prefer ignoreDifferences with JSON pointers
   over kind-wide exclusions. Prefer explicit manifest fields over
   ignoreDifferences where the defaults are stable (class A).

## Non-goals

- Not migrating any chart to a different vendor/version
- Not changing ArgoCD's default sync options project-wide
- Not eliminating `prune: false` as the project default (it's deliberate — manual pruning only)

## Related plan

`docs/superpowers/plans/2026-04-15--gitops--argocd-drift-cleanup.md`

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| ArgoCD Drift Cleanup Design Implementation Plan | derio-net/superpowers-for-vk | `docs/superpowers/archived-plans/2026-04-15--gitops--argocd-drift-cleanup/` | — |
