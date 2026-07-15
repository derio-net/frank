---
title: "Operating on Multi-tenancy"
series: ["operating"]
layer: tenant
date: 2026-03-13
draft: false
tags: ["operations", "vcluster", "multi-tenancy", "troubleshooting"]
summary: "Day-to-day commands for managing vCluster virtual clusters, checking tenant health, and debugging isolation issues."
weight: 10
reader_goal: "Create, connect to, and troubleshoot vCluster virtual clusters — check sync health, manage resource quotas, and debug API server or networking issues."
diataxis: [how-to, reference]
last_updated: 2026-07-15
last_updated_commit: https://github.com/derio-net/frank/commit/a8bed9a1d358b7ad87bb6dcaa9b0162e5fb0e127
---

{{< last-updated >}}

This is the operational companion to [Multi-tenancy — Disposable Kubernetes Clusters with vCluster]({{< relref "/docs/building/14-multi-tenancy" >}}). That post covers the architecture and template pattern. This one is the day-to-day runbook for creating, connecting to, and troubleshooting virtual clusters.

Source your environment:

```bash
source .env
```

## What "Healthy" Looks Like

Multi-tenancy is healthy when all vCluster StatefulSets are running, each virtual cluster's API server is responding, and resources are syncing correctly.

### Verify

```bash
vcluster list
kubectl get statefulset -A -l app=vcluster
```

All vClusters should show `STATUS: Running`. StatefulSets should show `READY: 1/1`.

## Observing State

### List Virtual Clusters

```bash
vcluster list
kubectl get pods -A -l app=vcluster
argocd app list --port-forward --port-forward-namespace argocd | grep vcluster
```

```console
$ vcluster list
       NAME     |      NAMESPACE       | STATUS  | VERSION | CONNECTED | AGE
  --------------+----------------------+---------+---------+-----------+------
    experiments | vcluster-experiments | Running | 0.32.1  |           | 39d

$ kubectl get statefulset -A -l app=vcluster
NAMESPACE              NAME          READY   AGE
vcluster-experiments   experiments   1/1     39d
```

### Connect to a Virtual Cluster

```bash
vcluster connect <name> --namespace <namespace>
kubectl get nodes
kubectl get namespaces
vcluster disconnect
```

### Check Synced Resources

```bash
kubectl logs -n <vcluster-namespace> <vcluster-pod> -c syncer --tail=50
kubectl get pods -n <vcluster-namespace> -l vcluster.loft.sh/managed-by
```

## Routine Operations

### Create a New Virtual Cluster

1. Copy the template: `cp -r apps/vclusters/template/ apps/vclusters/<new-name>/`
2. Customize `apps/vclusters/<new-name>/values.yaml` — name, resource quotas.
3. Add ArgoCD Application CR in `apps/root/templates/vcluster-<new-name>.yaml`.
4. Commit and push.

### Delete a Virtual Cluster

Since `prune: false`:

```bash
argocd app delete vcluster-<name> --port-forward --port-forward-namespace argocd
kubectl get ns <vcluster-namespace>
```

Then remove the files from `apps/vclusters/<name>/` and `apps/root/templates/`.

### Manage Resource Quotas

```bash
vcluster connect <name> --namespace <namespace>
kubectl get resourcequota -A
vcluster disconnect
kubectl top pods -n <vcluster-namespace>
```

## Runbook

### Virtual API Server Not Responding

```bash
kubectl get statefulset -n <vcluster-namespace>
kubectl describe statefulset -n <vcluster-namespace> <vcluster-name>
kubectl get pvc -n <vcluster-namespace>
kubectl logs -n <vcluster-namespace> <vcluster-pod> -c vcluster --tail=100
```

Common causes: PVC stuck pending, resource limits too low, host node under pressure.

### Resources Not Syncing

```bash
kubectl logs -n <vcluster-namespace> <vcluster-pod> -c syncer --tail=100 | grep -i error
kubectl get configmap -n <vcluster-namespace> -l app=vcluster -o yaml | grep -A 20 sync
```

### Resource Quota Exceeded

```bash
vcluster connect <name> --namespace <namespace>
kubectl describe resourcequota -A
kubectl top pods -A --sort-by=memory
vcluster disconnect
```

### Network Connectivity Issues

```bash
vcluster connect <name> --namespace <namespace>
kubectl run test --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default
kubectl run test --image=busybox --rm -it --restart=Never -- wget -qO- http://<host-service>
vcluster disconnect
```

## Quick Reference

| Command | What It Does |
|---------|-------------|
| `vcluster list` | List all virtual clusters |
| `vcluster connect <name> -n <ns>` | Switch kubectl to virtual cluster |
| `vcluster disconnect` | Return to host cluster context |
| `kubectl get pods -A -l app=vcluster` | Check vCluster pods on host |
| `kubectl logs -n <ns> <pod> -c syncer` | Check resource sync logs |
| `kubectl logs -n <ns> <pod> -c vcluster` | Check virtual API server logs |
| `kubectl get pvc -n <ns>` | Check virtual etcd storage |
| `argocd app list \| grep vcluster` | ArgoCD status for vClusters |

## References

- [vCluster Documentation](https://www.vcluster.com/docs)
- [vCluster CLI Reference](https://www.vcluster.com/docs/vcluster/reference/vcluster-cli)
- [Building Post — Multi-tenancy]({{< relref "/docs/building/14-multi-tenancy" >}})
