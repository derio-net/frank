# argo-rollouts-extras (currently empty)

This directory exists for supplemental manifests around the argo-rollouts
controller (RBAC, plugin configs, notification routes, etc.) that aren't
shipped by the upstream Helm chart.

It is **intentionally empty** as of 2026-05-04.

## What used to live here

- `cilium-rbac.yaml` — `ClusterRole` + `ClusterRoleBinding` granting the
  `argo-rollouts` ServiceAccount `create/update/patch/delete` on
  `cilium.io/CiliumEnvoyConfig`. The grant existed for the
  `rollouts-plugin-trafficrouter-cilium` plugin referenced by the original
  litellm `Rollout`. That plugin was never published as a release artifact
  (the configured download URL 404s), so the controller never loaded it.
  The RBAC was removed when we migrated litellm to a replica-count canary
  on 2026-05-04. See `building/19-progressive-delivery` (Update section)
  for the full story.

## Manual cleanup required after merge

Removing the file from git does **not** remove the live ClusterRole /
ClusterRoleBinding (cluster-wide `prune: false` policy across the repo).
Run once after this PR is synced:

```bash
kubectl delete clusterrole argo-rollouts-cilium
kubectl delete clusterrolebinding argo-rollouts-cilium
```
