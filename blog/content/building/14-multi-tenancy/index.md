---
title: "Multi-tenancy — Disposable Kubernetes Clusters with vCluster"
date: 2026-03-11
draft: false
tags: ["vcluster", "multi-tenancy", "sandbox", "isolation", "argocd"]
summary: "Virtual Kubernetes clusters inside Frank — each one a disposable sandbox with its own control plane, resource quotas, and network policies, deployed via ArgoCD."
weight: 15
cover:
  image: cover.png
  alt: "Frank the cluster monster holding a snow globe containing a tiny Kubernetes cluster"
  relative: true
---

Every experiment on a shared cluster carries risk. Install a CRD that conflicts with something in production. Deploy a Helm chart that creates cluster-scoped resources you did not expect. Run a fuzz test that fills all available memory. On a homelab with one cluster, the blast radius is everything.

Layer 12 adds vCluster — virtual Kubernetes clusters that run inside Frank. Each one has its own API server, its own namespaces, its own resources. From the inside, it looks and feels like a real cluster. From the outside, it is a StatefulSet in a namespace.

## What vCluster Actually Is

[vCluster](https://www.vcluster.com/) runs a virtual Kubernetes control plane (API server + controller manager + backing store) as a StatefulSet. The virtual cluster has its own API endpoint, its own etcd (or SQLite), and its own set of namespaces. Workloads created inside the virtual cluster get synced to the host cluster for actual scheduling — the virtual cluster does not run its own kubelet or container runtime.

The key properties:

- **API isolation** — a tenant can install CRDs, create cluster-scoped resources, and run `kubectl` without affecting the host
- **Resource isolation** — quotas and limit ranges bound what the tenant can consume
- **Network isolation** — network policies restrict traffic between virtual cluster pods and the host
- **Lifecycle simplicity** — delete the namespace, everything is gone

## The Template Pattern

Adding a vCluster should be as simple as adding a Helm values file and an ArgoCD Application CR. To make this work, the values are split into two layers:

```
apps/vclusters/
  template/values.yaml        # Base defaults — all vClusters inherit this
  experiments/values.yaml     # Instance-specific overrides (can be empty)
```

The ArgoCD Application CR loads both files in order:

```yaml
helm:
  valueFiles:
    - $values/apps/vclusters/template/values.yaml
    - $values/apps/vclusters/experiments/values.yaml
```

Helm deep-merges them — the instance file overrides the template. To create a new vCluster, copy the Application CR, point it at a new values file, and push.

## Template Defaults

The template configures sensible defaults for a homelab sandbox:

**Backing store:** SQLite (embedded database). The open-source edition of vCluster does not support embedded etcd — that requires a Pro license. SQLite is fine for single-replica virtual clusters at homelab scale.

**Persistence:** 5Gi Longhorn volume for the backing store. The virtual cluster's state survives pod restarts.

**Resource quotas:** 4 CPU / 8Gi request limit, 50 pods, 20 services. Enough for experiments, bounded enough to prevent runaway workloads from starving the host.

**Network policies:** Enabled. Virtual cluster pods cannot reach host cluster services by default.

**Sync rules:** Pods, Services, ConfigMaps, Secrets, PVCs, and Ingresses sync from virtual to host. Nodes and StorageClasses sync from host to virtual.

## Chart Schema Gotchas

The vCluster chart v0.32.1 has a strict JSON schema. Three things the plan got wrong:

1. **`isolation` does not exist** — it is `policies` (with `resourceQuota`, `limitRange`, `networkPolicy`)
2. **`networking.service` does not exist** — the chart does not expose a top-level service type override
3. **Case sensitivity matters** — `configMaps` not `configmaps`, `persistentVolumeClaims` not `persistentvolumeclaims`

Any schema violation produces a template error during ArgoCD sync. The error message is clear, but discovering the correct field names required `helm show values` against the actual chart.

## The Result

Inside the virtual cluster:

```
$ kubectl get namespaces
NAME              STATUS   AGE
default           Active   3m
kube-node-lease   Active   3m
kube-public       Active   3m
kube-system       Active   3m

$ kubectl get nodes
NAME     STATUS   ROLES           AGE   VERSION
mini-3   Ready    control-plane   3m    v1.35.2

$ kubectl run nginx --image=nginx:alpine
pod/nginx created

$ kubectl get pods
NAME    READY   STATUS    RESTARTS   AGE
nginx   1/1     Running   0          10s
```

On the host cluster, the nginx pod appears in the `vcluster-experiments` namespace with a mangled name — the syncer translates between virtual and host namespaces. The pod is scheduled normally by the host's kubelet.

Adding the next vCluster is two files and a `git push`.
