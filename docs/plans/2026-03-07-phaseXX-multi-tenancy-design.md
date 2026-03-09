# Phase 10: Multi-tenancy — Design

**Date:** 2026-03-07

## Overview

Deploy vCluster to enable disposable, fully isolated virtual Kubernetes clusters inside Frank. Each vCluster is a complete K8s API server running as a pod in the host cluster, with its own namespaces, RBAC, and workloads. Provisioned via ArgoCD apps — GitOps-managed, reproducible, easy to create and destroy.

Primary use case: isolated experiment environments and controlled access for external users.

## Stack

| Component | Tool | Chart |
|-----------|------|-------|
| Virtual cluster engine | vCluster | `loft-sh/vcluster` |

## Architecture

Each vCluster runs in its own namespace on the host cluster. Inside the vCluster, tenants see a full K8s API (pods, deployments, services, etc.) with no visibility into the host cluster or other vClusters.

```
Frank (host cluster)
├── namespace: vcluster-experiments
│   └── vCluster "experiments" (full K8s API)
│       ├── tenant pods → scheduled on host nodes
│       └── tenant namespaces, RBAC, resources
├── namespace: vcluster-alice
│   └── vCluster "alice" (full K8s API)
└── ...
```

Host cluster resources (Longhorn storage, GPU nodes) can be exposed to vClusters selectively via vCluster's sync configuration.

### Provisioning Pattern

Each vCluster follows the existing ArgoCD App-of-Apps pattern:

```
apps/vclusters/<name>/values.yaml     # vCluster config
apps/root/templates/vcluster-<name>.yaml  # ArgoCD Application CR
```

To create a new vCluster: add values + Application CR, commit, push — ArgoCD deploys it.
To destroy: delete the ArgoCD app (with prune enabled per-app for vClusters).

### Access

Connect to a vCluster via:
```bash
vcluster connect <name> -n vcluster-<name>
```

This generates a kubeconfig for the virtual cluster. Share with external users for isolated access without any host cluster privileges.

## ArgoCD Apps

vClusters are provisioned on demand. A base `vcluster-template` values file will be maintained in `apps/vclusters/` as a starting point for new vClusters.

No persistent ArgoCD app for vCluster itself — the `loft-sh/vcluster` chart is referenced directly in each per-vCluster Application CR.

## Storage

vClusters use Longhorn-backed PVCs for their virtual etcd state. Default: 5Gi per vCluster. Tenant workloads that need persistent volumes will consume Longhorn storage from the host cluster (passed through via vCluster sync).

## Exposure

No persistent UI. vCluster access is kubeconfig-based (`vcluster connect`). Each vCluster's LoadBalancer services get IPs from the shared Cilium L2 pool (192.168.55.200–254).

## Blog Post

**Title:** "Phase 10 — Multi-tenancy: Disposable Kubernetes Clusters with vCluster"

**Angle:** "Kubernetes inside Kubernetes" — how vCluster works, why it's better than namespace isolation for experiments, how we manage it GitOps-style with ArgoCD. Demonstrate spinning up a vCluster, deploying a test workload, and tearing it down. Show giving external access via kubeconfig without any host cluster exposure.
