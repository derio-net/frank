# 2026-07-06 cluster status drift

## Symptom & reproduction

`kubectl get nodes` showed all seven Frank nodes `Ready`, but the status check had three noisy classes of issues:

- ArgoCD applications repeatedly reported `OutOfSync` while `Healthy`: `longhorn-extras`, `stoa-live-mirror-sync`, `sympozium-extras`, `tekton-extras`, and `vcluster-experiments`.
- `tekton-pipelines` had old failed task pods and one long-lived `pipelinerun-ttl-gc-29646990-m2dhv` pod stuck in image pull.
- Recent events showed ArgoCD repeatedly self-healing partial sync drift.

Reproduction commands used during diagnosis:

```bash
kubectl get applications -n argocd -o 'custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
kubectl -n tekton-pipelines get pod pipelinerun-ttl-gc-29646990-m2dhv -o json
```

## Evidence

Live ArgoCD resource status identified these drift resources:

```text
longhorn-extras BackupTarget longhorn-system/default OutOfSync
sympozium-extras PersonaPack sympozium-system/developer-team OutOfSync
sympozium-extras PersonaPack sympozium-system/devops-essentials OutOfSync
tekton-extras Pipeline/Task/EventListener resources OutOfSync
tekton-extras old TriggerTemplates requiresPruning=true
vcluster-experiments StatefulSet vcluster-experiments/experiments OutOfSync
```

The stuck GC pod was owned by `Job/pipelinerun-ttl-gc-29646990` and used:

```text
bitnami/kubectl:1.35.3
```

The container runtime reported that `docker.io/bitnami/kubectl:1.35.3` was not found.

Longhorn live `BackupTarget/default` contained controller-written fields not present in Git:

```yaml
spec:
  pollInterval: 5m0s
  syncRequestedAt: "2026-07-06T13:19:44Z"
```

Sympozium live disabled PersonaPacks remained `status.phase: Inactive`, but the controller normalized away `spec.enabled` and `spec.authRefs`, causing ArgoCD to keep trying to restore them.

vCluster live `StatefulSet/experiments` contained runtime/defaulted fields such as `kubectl.kubernetes.io/restartedAt` and `persistentVolumeClaimRetentionPolicy.whenDeleted` that were not ignored.

Tekton live embedded `taskSpec`s had defaulted empty fields such as `metadata: {}`, `spec: null`, and empty `computeResources: {}` maps.

## Root cause

The cluster was healthy, but ArgoCD was noisy because several controllers normalize their CRs after apply, and the Application ignore rules did not cover those controller-owned/defaulted fields. The pending Tekton pod existed because the daily PipelineRun TTL GC CronJob pinned a removed image tag, `bitnami/kubectl:1.35.3`.

## Fix

- Changed the PipelineRun TTL GC CronJob image to `bitnamilegacy/kubectl:1.33.4`, preserving bash, GNU date, and kubectl behavior while using the post-Bitnami-migration namespace.
- Canonicalized Longhorn `pollInterval` to `5m0s` and ignored controller-written `/spec/syncRequestedAt` for `BackupTarget/default`.
- Ignored Sympozium controller-normalized `PersonaPack` fields `/spec/enabled` and `/spec/authRefs`.
- Extended vCluster StatefulSet ignores to runtime/defaulted `restartedAt` and `whenDeleted` fields.
- Added narrow Tekton Pipeline `jqPathExpressions` for defaulted empty embedded `taskSpec` fields.

The live old failed Tekton pods and old failed GC job are historical objects. The repo fix prevents new GC jobs from failing; deleting historical pods/jobs is a one-time cluster cleanup rather than declarative source repair.

## Rejected hypotheses

- Node or kubelet failure: rejected because all seven Kubernetes nodes were `Ready`, Talos health passed etcd/apid/kubelet/boot/disk/memory checks, and no Deployment/StatefulSet/DaemonSet was under-ready.
- Pending storage or LoadBalancer exhaustion: rejected because PVCs and LoadBalancer services had no pending rows.
- Missing Sympozium CRD fields: rejected because the live CRD schema includes `enabled` and `authRefs`; the fields are controller-normalized, not API-pruned.
- Repo source for the stuck image outside this repository: rejected after finding `apps/tekton/manifests/pipelinerun-ttl-gc.yaml` pins the exact failing image.
