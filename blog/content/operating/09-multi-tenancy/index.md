---
title: "Operating on Multi-tenancy"
date: 2026-03-13
draft: false
tags: ["operations", "vcluster", "multi-tenancy"]
summary: "Day-to-day commands for managing vCluster virtual clusters, checking tenant health, and debugging isolation issues."
weight: 109
cover:
  image: cover.png
  alt: "Frank maintaining miniature cluster snow globes inside his own body"
  relative: true
---

This is the operational companion to [Multi-tenancy — Disposable Kubernetes Clusters with vCluster]({{< relref "/building/14-multi-tenancy" >}}). That post covers the architecture and template pattern. This one is the day-to-day runbook for creating, connecting to, and troubleshooting virtual clusters.

## What "Healthy" Looks Like

Multi-tenancy is healthy when all vCluster StatefulSets are running, each virtual cluster's API server is responding, and resources are syncing correctly between virtual and host clusters. The ArgoCD applications for each vCluster should show `Synced` and `Healthy`.

## Observing State

### List Virtual Clusters

```bash
# Using vcluster CLI
vcluster list

# Check vCluster pods on the host
kubectl get pods -A -l app=vcluster

# Check ArgoCD status for vCluster apps
argocd app list --port-forward --port-forward-namespace argocd | grep vcluster
```

### Connect to a Virtual Cluster

```bash
# Connect and switch kubectl context
vcluster connect <name> --namespace <namespace>

# Verify you are in the virtual cluster
kubectl get nodes
kubectl get namespaces

# Disconnect when done
vcluster disconnect
```

### Check Synced Resources

```bash
# From the host cluster, check what the syncer is doing
kubectl logs -n <vcluster-namespace> <vcluster-pod> -c syncer --tail=50

# Check resource sync status
kubectl get pods -n <vcluster-namespace> -l vcluster.loft.sh/managed-by
```

## Routine Operations

### Create a New Virtual Cluster

New vClusters follow the template pattern:

1. Copy the template values:
```bash
cp -r apps/vclusters/template/ apps/vclusters/<new-name>/
```

2. Customize `apps/vclusters/<new-name>/values.yaml` — set the name, resource quotas, and any specific configuration.

3. Add the ArgoCD Application CR in `apps/root/templates/vcluster-<new-name>.yaml` following the existing pattern.

4. Commit and push — ArgoCD picks it up automatically.

### Delete a Virtual Cluster

Since `prune: false`, removing a vCluster requires manual cleanup:

```bash
# Delete the ArgoCD application
argocd app delete vcluster-<name> --port-forward --port-forward-namespace argocd

# Verify the namespace is cleaned up
kubectl get ns <vcluster-namespace>
```

Then remove the files from `apps/vclusters/<name>/` and `apps/root/templates/vcluster-<name>.yaml`.

### Manage Resource Quotas

```bash
# Check current quotas from inside the virtual cluster
vcluster connect <name> --namespace <namespace>
kubectl get resourcequota -A

# Check host-level resource usage for the vCluster namespace
vcluster disconnect
kubectl top pods -n <vcluster-namespace>
```

To adjust quotas, update the values in `apps/vclusters/<name>/values.yaml` and let ArgoCD sync.

## Debugging

### Virtual API Server Not Responding

```bash
# Check the StatefulSet
kubectl get statefulset -n <vcluster-namespace>
kubectl describe statefulset -n <vcluster-namespace> <vcluster-name>

# Check the PVC for the virtual etcd
kubectl get pvc -n <vcluster-namespace>

# Check pod logs
kubectl logs -n <vcluster-namespace> <vcluster-pod> -c vcluster --tail=100
```

Common causes:
- PVC stuck pending (storage class issue)
- Resource limits too low for the API server
- Host node where the StatefulSet is scheduled is under pressure

### Resources Not Syncing

```bash
# Check syncer logs for errors
kubectl logs -n <vcluster-namespace> <vcluster-pod> -c syncer --tail=100 | grep -i error

# Verify sync configuration in values.yaml
kubectl get configmap -n <vcluster-namespace> -l app=vcluster -o yaml | grep -A 20 sync
```

### Resource Quota Exceeded

```bash
# Connect to the virtual cluster and check
vcluster connect <name> --namespace <namespace>
kubectl describe resourcequota -A

# Check which pods are consuming the most
kubectl top pods -A --sort-by=memory
vcluster disconnect
```

### Network Connectivity Issues

```bash
# Test DNS from inside the virtual cluster
vcluster connect <name> --namespace <namespace>
kubectl run test --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default

# Test connectivity to a host service
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
- [Building Post — Multi-tenancy]({{< relref "/building/14-multi-tenancy" >}})
