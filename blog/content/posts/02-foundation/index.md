---
title: "Building the Foundation — Talos, Nodes, and Cilium"
date: 2026-03-06
draft: true
tags: ["talos", "cilium", "networking", "bootstrap"]
summary: "Bootstrapping a Talos Linux cluster with Omni, configuring node labels and zones, and replacing Flannel with Cilium's eBPF networking."
weight: 3
---

This post covers the first three steps of building Frank Cluster: bootstrapping Talos Linux via Omni, organizing nodes into labeled zones, and installing Cilium as the CNI with eBPF kube-proxy replacement.

## Why Talos Linux?

*Content to be written — covers: immutable OS, API-driven config, no SSH, security posture, comparison with Ubuntu/k3s/Flatcar.*

## Bootstrapping with Omni

*Content to be written — covers: Omni setup on raspi-omni, machine enrollment, initial cluster creation, machine configs.*

## Phase 1: Node Configuration

*Content to be written — covers: node labels (zone, tier, accelerator), scheduling strategy (control-plane workers), removing NoSchedule taints.*

### Key Config: Cluster-Wide Scheduling

<!-- Reference: patches/phase01-node-config/01-cluster-wide-scheduling.yaml -->

*Content to be written — explain the patch and why control planes also run workloads in a homelab.*

### Key Config: Node Labels

<!-- Reference: patches/phase01-node-config/03-labels-*.yaml -->

*Content to be written — explain the labeling scheme and zone architecture.*

## Phase 2: Cilium CNI

*Content to be written — covers: why Cilium over Flannel/Calico, eBPF kube-proxy replacement, L2 announcements, Hubble.*

### Removing Flannel

<!-- Reference: patches/phase02-cilium/02-cluster-wide-cni-none.yaml -->

*Content to be written — the careful dance of removing default CNI.*

### Installing Cilium

<!-- Reference: apps/cilium/values.yaml -->

*Content to be written — Helm values walkthrough, L2 LoadBalancer IP pool, Hubble setup.*

### Gotchas

*Content to be written — things that went wrong and how they were fixed.*

## What We Have Now

At this point the cluster has:
- 7 nodes running Talos Linux, managed by Omni
- Labeled zones (Core, AI Compute, Edge) for workload placement
- Cilium CNI with eBPF kube-proxy replacement
- L2 LoadBalancer (192.168.55.200-210) for service exposure
- Hubble for network observability

**Next: [Persistent Storage with Longhorn]({{< relref "/posts/03-storage" >}})**
