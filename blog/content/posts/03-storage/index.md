---
title: "Persistent Storage with Longhorn"
date: 2026-03-06
draft: true
tags: ["longhorn", "storage"]
summary: "Setting up Longhorn distributed block storage across heterogeneous disks, including a GPU-local StorageClass for AI workloads."
weight: 4
---

This post covers installing Longhorn for distributed block storage — including handling Talos's immutable OS, heterogeneous disk sizes, and creating a dedicated GPU-local StorageClass.

## Why Longhorn?

*Content to be written — covers: Longhorn vs Rook-Ceph for homelab, simplicity, Rancher ecosystem, replica management.*

## Prerequisites: iscsi-tools on Talos

<!-- Reference: patches/phase03-longhorn/400-cluster-iscsi-tools.yaml -->

*Content to be written — Talos needs iscsi-tools extension for Longhorn. How to add it cluster-wide.*

## Mounting Extra Disks on gpu-1

<!-- Reference: patches/phase03-longhorn/401-gpu1-extra-disks.yaml -->

*Content to be written — gpu-1 has 2x4TB SSDs for dedicated GPU storage. Talos disk mount config.*

## Installing Longhorn

<!-- Reference: apps/longhorn/values.yaml -->

*Content to be written — Helm values walkthrough, replica settings, data locality.*

## GPU-Local StorageClass

<!-- Reference: apps/longhorn/manifests/gpu-local-sc.yaml -->

*Content to be written — strict-local data locality for performance, single replica, disk tag selection.*

## What We Have Now

At this point the cluster has:
- Distributed 3-replica block storage across all 7 nodes
- GPU-local StorageClass for high-performance single-node workloads on gpu-1
- Automatic volume rebalancing and health monitoring

**Next: [GPU Compute — NVIDIA and Intel]({{< relref "/posts/04-gpu-compute" >}})**
