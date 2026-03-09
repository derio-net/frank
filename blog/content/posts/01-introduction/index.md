---
title: "Why Build a Kubernetes Homelab?"
date: 2026-03-06
draft: false
tags: ["introduction", "architecture"]
summary: "The motivation behind Frank, the Talos Cluster — learning enterprise infrastructure and building interesting projects on your own hardware."
weight: 2
cover:
  image: cover.png
  alt: "Frank the cluster monster sketching blueprints at his workbench"
  relative: true
---

## Why?

Two reasons drove me to build this cluster.

### Reason 1: Learning by Doing

Cloud-managed Kubernetes (EKS, GKE) abstracts away the parts I wanted to understand: CNI networking, storage orchestration, GPU scheduling, immutable OS operation, and GitOps at the infrastructure layer. You can read about eBPF kube-proxy replacement or DRA-based GPU sharing all day — or you can break it, fix it, and actually learn it.

The goal was never "run a production cluster at home." It was to build one that *could* be production, so the skills transfer directly.

### Reason 2: Self-hosted Infrastructure

As a solo builder, I want self-hosted infrastructure for:

- **AI/ML workloads** — local inference with GPUs, fine-tuning, experiments
- **Self-hosted services** — things I'd otherwise pay SaaS for
- **Product prototyping** — test deployments before going to cloud

The hardware was already sitting around. The cluster turns idle machines into a platform.

## The Hardware

The cluster spans 4 zones of heterogeneous hardware:

### Zone A: Management

- **raspi-omni** (Raspberry Pi 5, 8GB) — Runs Sidero Omni, Authentik SSO, Traefik. The management plane lives outside the cluster.

### Zone B: Core HA

- **mini-1, mini-2, mini-3** (ASUS NUC, Intel Ultra 5 225H, 64GB RAM, 1TB NVMe) — Three identical nodes forming the HA control plane. Each has an Intel Arc iGPU for future media/AI workloads.

### Zone C: AI Compute

- **gpu-1** (Custom desktop, i9, 128GB RAM, RTX 5070, 2x4TB SSD) — The heavy lifter. Dedicated GPU storage via Longhorn. Tainted for GPU-only workloads.

### Zone D: Edge

- **pc-1** (Legacy desktop, 64GB SSD + 3x HDD) — General purpose worker.
- **raspi-1, raspi-2** (Raspberry Pi 4, 32GB SD) — Low-power edge nodes.

## Architecture

![Omni cluster dashboard showing CPU, pods, memory, and node status for the frank cluster](omni-cluster.png)

The cluster uses a **two-layer management model**:

- **Layer 1 (Machine Config):** Sidero Omni manages Talos Linux machine configurations — OS extensions, kernel modules, disk mounts, network settings. Applied via `omnictl`.
- **Layer 2 (Workloads):** ArgoCD manages everything running *on* Kubernetes — CNI, storage, GPU drivers, applications. GitOps via the same repo you're reading.

This separation means Omni never touches workloads, and ArgoCD never touches machine config. Clean boundaries, no conflicts.

## What's Next

The rest of this series walks through each capability layer:

{{< cluster-roadmap >}}

Let's start building.

## References

- [Talos Linux](https://www.talos.dev/) — Immutable, secure, minimal Kubernetes OS
- [Sidero Omni](https://www.siderolabs.com/omni/) — SaaS-simple Kubernetes cluster management for Talos Linux
- [Kubernetes](https://kubernetes.io/) — Production-grade container orchestration
- [ArgoCD](https://argo-cd.readthedocs.io/en/stable/) — Declarative GitOps continuous delivery for Kubernetes
- [Cilium](https://docs.cilium.io/en/stable/) — eBPF-based networking, observability, and security for Kubernetes
- [Longhorn](https://longhorn.io/) — Cloud-native distributed block storage for Kubernetes
- [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/) — Automated GPU management in Kubernetes
- [Intel Resource Drivers for Kubernetes](https://github.com/intel/intel-resource-drivers-for-kubernetes) — DRA-based resource drivers for Intel GPUs
- [eBPF](https://ebpf.io/) — Technology for programmable networking, observability, and security in the Linux kernel
