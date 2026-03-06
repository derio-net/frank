---
title: "GitOps Everything with ArgoCD"
date: 2026-03-06
draft: true
tags: ["argocd", "gitops"]
summary: "Migrating from Flux to ArgoCD with an App-of-Apps pattern — adopting existing workloads without downtime."
weight: 6
---

This post covers the migration from Flux CD to ArgoCD, the Pulumi detour that didn't work out, and building an App-of-Apps Helm chart to manage all cluster workloads via GitOps.

## The Pulumi Detour

*Content to be written — tried Pulumi first, no Sidero Omni provider, conflicts with Omni's machine management. Abandoned.*

## Why ArgoCD Over Flux?

*Content to be written — Flux was already deployed but broken. ArgoCD: better UI, App-of-Apps pattern, multi-source applications, cleaner adoption of existing workloads.*

## Removing Flux CD

*Content to be written — cleaning up Flux CRDs, controllers, and source artifacts without disrupting running workloads.*

## App-of-Apps Pattern

<!-- Reference: apps/root/ -->

*Content to be written — root Helm chart renders child Application CRs. Single apply bootstraps everything.*

### Root Chart Structure

<!-- Reference: apps/root/Chart.yaml, values.yaml, templates/ -->

*Content to be written — Chart.yaml, values with repo URL/revision, namespace templates with PSA labels.*

### Multi-Source Applications

<!-- Reference: apps/root/templates/cilium.yaml (example) -->

*Content to be written — each Application has two sources: upstream Helm chart + local values from apps/{name}/values.yaml.*

## Adopting Existing Workloads

*Content to be written — Cilium and Longhorn were already running. ArgoCD adoption without downtime: annotation-based resource tracking, replace=true for CRDs.*

## Self-Managing ArgoCD

<!-- Reference: apps/argocd/values.yaml -->

*Content to be written — ArgoCD managing its own Helm values. Bootstrap once, then it watches itself.*

## What We Have Now

At this point the cluster has:
- Full GitOps via ArgoCD App-of-Apps
- All workloads (Cilium, Longhorn, GPU drivers, OpenRGB) managed declaratively
- Self-healing: ArgoCD detects and corrects drift automatically
- Single repo as source of truth for both machine config and workloads

**Next: [Fun Stuff — Controlling Case LEDs from Kubernetes]({{< relref "/posts/06-fun-stuff" >}})**
