---
title: "GPU Compute — NVIDIA and Intel"
date: 2026-03-06
draft: true
tags: ["gpu", "nvidia", "intel", "dra"]
summary: "Adding GPU compute to the cluster — the NVIDIA RTX 5070 saga, Intel Arc iGPU via DRA, and patching charts for bleeding-edge Kubernetes."
weight: 5
---

This post covers two GPU stories: the NVIDIA RTX 5070 (and its hardware troubles), and the Intel Arc iGPU on the mini nodes using Kubernetes 1.35's Dynamic Resource Allocation.

## Part 1: NVIDIA GPU Operator (Phase 4)

### Talos Extensions for NVIDIA

<!-- Reference: patches/phase04-gpu/402-gpu1-nvidia-extensions.yaml -->
<!-- Reference: patches/phase04-gpu/04-gpu-nvidia-modules.yaml -->

*Content to be written — nvidia-toolkit, nvidia-gpu-kernel-modules, kernel module loading on Talos.*

### GPU Operator Helm Values

<!-- Reference: apps/gpu-operator/values.yaml -->

*Content to be written — driver disabled (Talos provides), toolkit disabled, containerd runtime config.*

### The Hardware Saga

*Content to be written — RTX 5070 not detected on PCIe bus, BIOS investigation, manual sync strategy, current status.*

## Part 2: Intel Arc iGPU via DRA (Phase 5)

### Why DRA Over Device Plugins?

*Content to be written — K8s 1.35 DRA (ResourceSlice/ResourceClaim), namespace-scoped sharing, future of GPU in K8s.*

### i915 Extensions on Talos

<!-- Reference: patches/phase05-mini-config/500-mini1-i915-extensions.yaml (and 501, 502) -->

*Content to be written — rolling extension install preserving CP quorum, i915 + intel-ucode.*

### CDI Containerd Configuration

<!-- Reference: patches/phase05-mini-config/05-mini-cdi-containerd.yaml -->

*Content to be written — Talos read-only rootfs, /var/cdi instead of /etc/cdi, cluster-wide containerd patch.*

### Chart Vendoring for K8s 1.35

<!-- Reference: apps/intel-gpu-driver/chart/ -->

*Content to be written — upstream chart uses v1beta1 APIs removed in K8s 1.35. Vendored chart with patches: DeviceClass v1, ValidatingAdmissionPolicy v1, PSA labels, CDI path fix, image update to v0.9.1.*

### Verifying It Works

*Content to be written — ResourceSlice per node, smoke test pod with ResourceClaim, card0 + renderD128 visible.*

## What We Have Now

At this point the cluster has:
- Intel Arc iGPU exposed on mini-1/2/3 via DRA (ResourceSlice/ResourceClaim)
- NVIDIA GPU Operator ready (manual sync, awaiting RTX 5070 hardware fix)
- GPU-local Longhorn storage on gpu-1 for AI workloads

**Next: [GitOps Everything with ArgoCD]({{< relref "/posts/05-gitops" >}})**
