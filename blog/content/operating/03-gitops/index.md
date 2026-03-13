---
title: "Operating on GitOps"
date: 2026-03-13
draft: false
tags: ["operations", "argocd", "gitops"]
summary: "Day-to-day commands for managing ArgoCD applications, syncing, debugging drift, and handling degraded apps."
weight: 103
cover:
  image: cover.png
  alt: "Frank conducting robotic arms that manage his application orchestra"
  relative: true
---

This post covers the day-to-day commands for working with ArgoCD on the frank cluster. If you want to understand how the App-of-Apps pattern was set up and why, see [GitOps Everything with ArgoCD]({{< relref "/building/05-gitops" >}}).

## Overview

ArgoCD runs at `192.168.55.200` on a Cilium L2 LoadBalancer. It manages itself and every workload on the cluster through the App-of-Apps pattern. A single root Application in `apps/root/` renders child Application CRs for each component — Cilium, Longhorn, the GPU Operator, LiteLLM, Sympozium, and everything else.

All ArgoCD CLI commands use port-forwarding since there is no public ingress:

```bash
argocd app list --port-forward --port-forward-namespace argocd
```

Every command in this post includes those flags. If you get tired of typing them, alias it:

```bash
alias argocd='argocd --port-forward --port-forward-namespace argocd'
```

## Observing State

### List All Applications

```bash
argocd app list --port-forward --port-forward-namespace argocd
```

This shows every application, its sync status (`Synced`, `OutOfSync`), health status (`Healthy`, `Degraded`, `Progressing`), and the target revision.

### Inspect a Single Application

```bash
argocd app get cilium --port-forward --port-forward-namespace argocd
```

This returns the full resource tree: every Deployment, DaemonSet, Service, ConfigMap, and Secret that ArgoCD tracks for that application. Resources with sync issues are flagged individually, which tells you exactly which object is drifting.

### Watch Sync Events

```bash
argocd app get cilium --port-forward --port-forward-namespace argocd --show-operation
```

The `--show-operation` flag shows the last sync operation result, including which resources were created, updated, or pruned and how long the operation took.

## Routine Operations

### Force Sync an Application

When you push a change and do not want to wait for the polling interval:

```bash
argocd app sync cilium --port-forward --port-forward-namespace argocd
```

For all applications at once, sync the root app:

```bash
argocd app sync root --port-forward --port-forward-namespace argocd
```

This re-renders the root Helm chart, which may discover new child Applications or updated chart versions. Each child then syncs on its own.

### Hard Refresh

ArgoCD caches the Git repo and Helm chart index. If you need it to re-read everything immediately:

```bash
argocd app get cilium --port-forward --port-forward-namespace argocd --hard-refresh
```

Useful when you have pushed a commit but ArgoCD still shows the old state.

### Check Diff Before Syncing

See what ArgoCD would change without applying anything:

```bash
argocd app diff cilium --port-forward --port-forward-namespace argocd
```

This is the GitOps equivalent of `terraform plan`. Review the diff, then sync if it looks right.

### Add a New Application

Adding a new workload follows the App-of-Apps pattern:

1. Create `apps/<app-name>/values.yaml` with Helm values.
2. Create `apps/root/templates/<app-name>.yaml` with the Application CR.
3. Optionally add `apps/<app-name>/manifests/` for raw Kubernetes manifests.
4. Commit, push, and sync the root app.

ArgoCD discovers the new Application CR from the root chart and begins syncing it automatically.

### Manage ArgoCD Itself

ArgoCD manages its own Helm values through the same Git repo. After editing `apps/argocd/values.yaml`:

```bash
argocd app sync argocd --port-forward --port-forward-namespace argocd
```

Since ArgoCD is updating itself, watch for the server to restart. The CLI connection will drop momentarily and reconnect.

## Debugging

### Application Stuck in Degraded

An app showing `Degraded` usually means one or more of its resources failed to reach a healthy state. Start with the resource tree:

```bash
argocd app get <app> --port-forward --port-forward-namespace argocd
```

Look for resources marked `Degraded` or `Missing`. Then check the Kubernetes events:

```bash
kubectl describe deployment <name> -n <namespace>
kubectl get events -n <namespace> --sort-by=.lastTimestamp | tail -20
```

Common causes: image pull failures, resource limits too low, missing secrets, or nodes lacking the right taints/tolerations.

### Sync Failed

When a sync operation fails, get the details:

```bash
argocd app get <app> --port-forward --port-forward-namespace argocd --show-operation
```

The operation result shows exactly which resource failed and why. Two frequent culprits:

- **Annotation size limit.** Kubernetes has a 256KB limit on annotation values. Large CRDs (like Cilium's) can exceed this with client-side apply. The fix is `ServerSideApply=true` in syncOptions, which the frank cluster uses on every application.
- **Finalizer deadlocks.** A resource with a finalizer that references a deleted controller will hang forever. Check `metadata.finalizers` and remove the offending entry if the controller is genuinely gone.

### OutOfSync but Correct

Some resources appear OutOfSync even though the live state is correct. This happens when a controller mutates the resource after ArgoCD applies it. Kubernetes Secrets are the classic example — controllers encode or rotate secret data, causing a permanent diff.

The fix is `ignoreDifferences` in the Application spec:

```yaml
ignoreDifferences:
  - group: ""
    kind: Secret
    jsonPointers:
      - /data
```

The frank cluster already applies this to applications that manage auto-generated secrets (Cilium, cert-manager). If you see a new case, add the appropriate `ignoreDifferences` entry to the Application template in `apps/root/templates/`.

### Orphaned Resources

With `prune: false` (the default on this cluster), ArgoCD never deletes resources that disappear from Git. This is intentional — accidental deletion of a CNI DaemonSet or a storage controller would be catastrophic.

To find resources ArgoCD no longer tracks:

```bash
argocd app resources <app> --port-forward --port-forward-namespace argocd --orphaned
```

Review the list and delete manually if you are sure:

```bash
kubectl delete <kind> <name> -n <namespace>
```

## Quick Reference

| Task | Command |
|------|---------|
| List all apps | `argocd app list --port-forward --port-forward-namespace argocd` |
| Get app detail | `argocd app get <app> --port-forward --port-forward-namespace argocd` |
| Sync one app | `argocd app sync <app> --port-forward --port-forward-namespace argocd` |
| Sync everything | `argocd app sync root --port-forward --port-forward-namespace argocd` |
| Check diff | `argocd app diff <app> --port-forward --port-forward-namespace argocd` |
| Hard refresh | `argocd app get <app> --port-forward --port-forward-namespace argocd --hard-refresh` |
| Show last sync | `argocd app get <app> --port-forward --port-forward-namespace argocd --show-operation` |
| List orphans | `argocd app resources <app> --port-forward --port-forward-namespace argocd --orphaned` |
| App logs | `argocd app logs <app> --port-forward --port-forward-namespace argocd` |
| Delete an app | `argocd app delete <app> --port-forward --port-forward-namespace argocd` |

## References

- [ArgoCD Documentation](https://argo-cd.readthedocs.io/en/stable/) — Official reference for all CLI commands and concepts
- [ArgoCD Sync Options](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/) — ServerSideApply, selfHeal, prune, and ignoreDifferences
- [GitOps Everything with ArgoCD]({{< relref "/building/05-gitops" >}}) — How the App-of-Apps was built on this cluster
