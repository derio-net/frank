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
| **Ollama** | Local LLM inference on gpu-1's RTX 5070 (qwen3.5:9b, deepseek-coder:6.7b) |
| **LiteLLM** | Unified OpenAI-compatible gateway, virtual keys, spend tracking (`192.168.55.206`) |
| **OpenRouter** | Free-tier cloud model aggregation (DeepSeek R1, Gemini Flash, Llama 3.3 70B) |
| **Sympozium** | Kubernetes-native agentic control plane — agent=Pod, policy=CRD, execution=Job (`192.168.55.207`) |
| **cert-manager** | Automated TLS certificate lifecycle for webhooks and internal services |
| **Authentik** | Unified SSO — OIDC for ArgoCD, Grafana, Infisical; forward-auth proxy for Longhorn, Hubble, Sympozium (`192.168.55.211`) |
| **vCluster** | Virtual K8s clusters inside Frank — disposable sandboxes with own API server, resource quotas, network policies |
| **Paperclip** | AI agent orchestrator — virtual companies with org charts, budgets, and delegation chains; complements Sympozium (`192.168.55.212`) |
| **ComfyUI** | Diffusion model serving — video (LTX-2.3), image (SDXL), audio (Stable Audio), node-based workflow editor (`192.168.55.213`) |
| **GPU Switcher** | Custom Go dashboard for GPU time-sharing — one-click switching between Ollama and ComfyUI (`192.168.55.214`) |

## Cluster State

| Node | Zone | Role | Hardware |
|------|------|------|----------|
| mini-1/2/3 | Core (B) | Control-plane + Worker | Intel Ultra 5, 64GB RAM, 1TB NVMe, Arc iGPU |
| gpu-1 | AI Compute (C) | Worker | i9, 128GB RAM, RTX 5070, 2x4TB SSD |
| pc-1 | Edge (D) | Worker | Legacy desktop, 64GB SSD + 3x HDD |
| raspi-1/2 | Edge (D) | Worker | Raspberry Pi 4, 32GB SD |

## Series Index

1. [Introduction — Why Build a Kubernetes Homelab?]({{< relref "/building/01-introduction" >}})
2. [Building the Foundation — Talos, Nodes, and Cilium]({{< relref "/building/02-foundation" >}})
3. [Persistent Storage with Longhorn]({{< relref "/building/03-storage" >}})
4. [GPU Compute — NVIDIA and Intel]({{< relref "/building/04-gpu-compute" >}})
5. [GitOps Everything with ArgoCD]({{< relref "/building/05-gitops" >}})
6. [Fun Stuff — Controlling Case LEDs from Kubernetes]({{< relref "/building/06-fun-stuff" >}})
7. [Observability — VictoriaMetrics, Grafana, and Fluent Bit]({{< relref "/building/07-observability" >}})
8. [Backup — Longhorn to Cloudflare R2]({{< relref "/building/08-backup" >}})
9. [Secrets Management — Infisical + External Secrets Operator]({{< relref "/building/09-secrets" >}})
10. [Local Inference — Ollama, LiteLLM, and OpenRouter]({{< relref "/building/10-local-inference" >}})
11. [Agentic Control Plane — Sympozium]({{< relref "/building/11-agentic-control-plane" >}})
12. [GPU Containers on Talos — The Validation Fix]({{< relref "/building/12-gpu-talos-fix" >}})
13. [Unified Auth — Authentik SSO for the Entire Cluster]({{< relref "/building/13-unified-auth" >}})
14. [Multi-tenancy — Disposable Kubernetes Clusters with vCluster]({{< relref "/building/14-multi-tenancy" >}})
15. [Paperclip — An AI Agent Orchestrator on Frank]({{< relref "/building/15-paperclip" >}})
16. [Media Generation — ComfyUI and GPU Time-Sharing]({{< relref "/building/16-media-generation" >}})

- Virtual Machines with KubeVirt _(planned)_

## Operating on Frank — Series Index

Companion series with day-to-day commands, health checks, and debugging guides.

1. [Operating on Cluster & Nodes]({{< relref "/operating/01-cluster-nodes" >}})
2. [Operating on Storage & Backups]({{< relref "/operating/02-storage-backups" >}})
3. [Operating on GitOps]({{< relref "/operating/03-gitops" >}})
4. [Operating on GPU Compute]({{< relref "/operating/04-gpu-compute" >}})
5. [Operating on Observability]({{< relref "/operating/05-observability" >}})
6. [Operating on Secrets]({{< relref "/operating/06-secrets" >}})
7. [Operating on Local Inference]({{< relref "/operating/07-inference" >}})
8. [Operating on Authentication]({{< relref "/operating/08-auth" >}})
9. [Operating on Multi-tenancy]({{< relref "/operating/09-multi-tenancy" >}})
10. [Operating on Media Generation]({{< relref "/operating/10-media-generation" >}})
