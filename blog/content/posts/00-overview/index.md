---
title: "Frank, the Talos Cluster: Overview & Roadmap"
date: 2026-03-06
draft: false
tags: ["overview", "roadmap"]
summary: "A living overview of Frank, the Talos Cluster — an AI-hybrid Kubernetes homelab. Technology roadmap, capabilities, and series index."
weight: 1
cover:
  image: cover.png
  alt: "Frank the cluster monster assembling himself from server parts"
  relative: true
---

This is the overview post for the **Frank, the Talos Cluster** series — a tutorial-style walkthrough of building an AI-hybrid Kubernetes homelab from scratch.

This post is a **living document**: it gets updated as new technologies and capabilities are added to the cluster.

## Roadmap

{{< cluster-roadmap >}}

## Technology → Capability Map

| Technology | Capabilities Unlocked |
|------------|----------------------|
| **Talos Linux + Omni** | Immutable OS, declarative machine config, secure bootstrap |
| **Cilium (eBPF)** | Kube-proxy replacement, L2 LoadBalancer, Hubble UI (`192.168.55.202`) |
| **Longhorn** | Distributed block storage, GPU-local StorageClass, 3-replica HA, UI (`192.168.55.201`) |
| **ArgoCD** | GitOps, App-of-Apps, self-healing, drift detection |
| **NVIDIA GPU Operator** | GPU scheduling, AI/ML workloads, container toolkit |
| **Intel GPU DRA Driver** | iGPU sharing via DRA, namespace-scoped GPU access |
| **OpenRGB** | LED control from K8s (just for fun) |
| **VictoriaMetrics + Grafana** | Cluster-wide metrics, alerting, dashboards, Grafana UI (`192.168.55.203`) |
| **VictoriaLogs + Fluent Bit** | Centralised log aggregation and querying |
| **Longhorn Backup + Cloudflare R2** | PVC backup/restore, daily + weekly schedules, offsite storage |
| **Infisical + External Secrets Operator** | Secret management with audit trail, ExternalSecret → K8s Secret sync (`192.168.55.204`) |

## Cluster State

| Node | Zone | Role | Hardware |
|------|------|------|----------|
| mini-1/2/3 | Core (B) | Control-plane + Worker | Intel Ultra 5, 64GB RAM, 1TB NVMe, Arc iGPU |
| gpu-1 | AI Compute (C) | Worker | i9, 128GB RAM, RTX 5070, 2x4TB SSD |
| pc-1 | Edge (D) | Worker | Legacy desktop, 64GB SSD + 3x HDD |
| raspi-1/2 | Edge (D) | Worker | Raspberry Pi 4, 32GB SD |

## Series Index

1. [Introduction — Why Build a Kubernetes Homelab?]({{< relref "/posts/01-introduction" >}})
2. [Building the Foundation — Talos, Nodes, and Cilium]({{< relref "/posts/02-foundation" >}})
3. [Persistent Storage with Longhorn]({{< relref "/posts/03-storage" >}})
4. [GPU Compute — NVIDIA and Intel]({{< relref "/posts/04-gpu-compute" >}})
5. [GitOps Everything with ArgoCD]({{< relref "/posts/05-gitops" >}})
6. [Fun Stuff — Controlling Case LEDs from Kubernetes]({{< relref "/posts/06-fun-stuff" >}})
7. [Observability — VictoriaMetrics, Grafana, and Fluent Bit]({{< relref "/posts/07-observability" >}})
8. [Backup — Longhorn to Cloudflare R2]({{< relref "/posts/08-backup" >}})
9. [Secrets Management — Infisical + External Secrets Operator]({{< relref "/posts/09-secrets" >}})
10. [Local Inference — Ollama, LiteLLM, and OpenRouter]({{< relref "/posts/10-local-inference" >}})
- Multi-tenancy with vCluster _(planned)_
- Virtual Machines with KubeVirt _(planned)_
