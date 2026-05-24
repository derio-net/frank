---
title: "Frank, the Talos Cluster: Overview & Roadmap"
date: 2026-03-06
draft: false
tags: ["overview", "roadmap"]
summary: "A living overview of Frank, the Talos Cluster — an AI-hybrid Kubernetes homelab. Technology roadmap, capabilities, and series index."
weight: 1
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
| **Hop (Hetzner Edge)** | Public-facing single-node Talos cluster — Headscale mesh, Caddy reverse proxy, blog hosting, split-DNS |
| **Headscale + Tailscale** | WireGuard mesh networking — remote homelab access from any device, MagicDNS for split-DNS |
| **Caddy** | Automatic TLS (Cloudflare DNS challenge), public/mesh routing, path rewriting |
| **Secure Agent Pod** | Hardened non-root coding agent workstation — Cilium egress, dropped capabilities, VibeKanban orchestration, SSH (`192.168.55.215`) + UI (`192.168.55.218`) |
| **Argo Rollouts** | Progressive delivery — canary (Cilium traffic splitting + VictoriaMetrics analysis) and blue-green (preview + atomic cutover) |
| **n8n** | Per-user workflow automation — 400+ integrations, visual node editor, webhook triggers, Authentik forward-auth (`192.168.55.216`) |
| **Blackbox Exporter + Pushgateway** | Feature-level health monitoring — HTTP endpoint probes, cron heartbeat ingestion, Grafana alerting to Telegram |
| **Health Bridge** | Grafana alert → GitHub Project lifecycle state bridge — automatic degraded/dead/healthy transitions, issue comments, bug issue creation |
| **Traefik (in-cluster)** | In-cluster ingress controller, wildcard TLS (`*.cluster.derio.net`), ACME via Cloudflare DNS-01, Authentik forward-auth for 12 services (`192.168.55.220`) |
| **VK Remote (self-hosted)** | Self-hosted VibeKanban kanban API — PostgreSQL 16, ElectricSQL real-time sync, Rust/Axum server, local JWT auth, Authentik SSO ingress (`vk.cluster.derio.net`) |
| **VK Relay** | WebSocket relay sidecar tunneling browser API calls to local VK agent server via yamux multiplexing, SPAKE2 pairing, Ed25519 request signing |
| **gethomepage.dev** | Cluster dashboard at `master.cluster.derio.net` — service catalog with HTTP health indicators, custom bookmarks |
| **Gitea** | Self-hosted git forge with GitHub pull-mirror, Authentik OIDC SSO (`192.168.55.209`) |
| **Tekton** | K8s-native CI/CD pipelines — webhook-driven clone, test, build, sign, report status on pc-1 |
| **Zot** | OCI container/artifact registry with cert-manager TLS and cosign image signing (`192.168.55.210`) |
| **agent-images** | Shared base image + per-pod children repo — `agent-base` toolchain + `secure-agent-kali` / `vk-local` children, matrix CI, cross-repo `repository_dispatch`, lockstep bumper PR |
| **Ruflo (claude-flow + ruvocal)** | Swarm-style AI orchestrator — hybrid pod (ruvocal SSR + agent-shell-base sidecar), LiteLLM-only egress, SSH+Mosh shell on `192.168.55.222`, web UI at `ruflo.cluster.derio.net` |
| **The Frank Papers** | Third blog series — research-grade landscape reviews framed as decisions; dossier gate (`validate-dossier.py` + pre-commit hook), Mermaid Frank theme, five `papers/` shortcodes, render-time cross-series backlinks. **Prologue published 2026-05-18:** [Why Run Your Own Cluster in 2026?]({{< relref "/docs/papers/00-why-homelab-in-2026" >}}) |
| **GoatCounter** | Cookieless blog analytics — public beacon via Hop's Caddy at `counter.derio.net`, mesh-only admin at `counter.cluster.derio.net` with Authentik forward-auth (`192.168.55.224`) |
| **CrowdSec + caddy-crowdsec-bouncer** | Edge HTTP security — agent tails Caddy logs on Hop, Caddy bouncer enforces decisions locally without round-tripping to Frank |
| **Falco (modern_ebpf) + Falcosidekick** | Container runtime security on Talos — Loki output to VictoriaLogs (Loki push protocol) + direct Telegram for `priority:critical` |
| **ai-alert-helper** | FastAPI service — daily blog digest, alert-time LLM enrichment, surge detection (hour-of-day baseline computed in Python because LogsQL has no `quantile_over_time`); LiteLLM-backed swap contract for future Sympozium |

## Cluster State

| Node | Zone | Role | Hardware |
|------|------|------|----------|
| mini-1/2/3 | Core (B) | Control-plane + Worker | Intel Ultra 5, 64GB RAM, 1TB NVMe, Arc iGPU |
| gpu-1 | AI Compute (C) | Worker | i9, 128GB RAM, RTX 5070, 2x4TB SSD |
| pc-1 | Edge (D) | Worker | Legacy desktop, 64GB SSD + 3x HDD |
| raspi-1/2 | Edge (D) | Worker | Raspberry Pi 4, 32GB SD |

## Series Index

1. [Introduction — Why Build a Kubernetes Homelab?]({{< relref "/docs/building/01-introduction" >}})
2. [Building the Foundation — Talos, Nodes, and Cilium]({{< relref "/docs/building/02-foundation" >}})
3. [Persistent Storage with Longhorn]({{< relref "/docs/building/03-storage" >}})
4. [GPU Compute — NVIDIA and Intel]({{< relref "/docs/building/04-gpu-compute" >}})
5. [GitOps Everything with ArgoCD]({{< relref "/docs/building/05-gitops" >}})
6. [Fun Stuff — Controlling Case LEDs from Kubernetes]({{< relref "/docs/building/06-fun-stuff" >}})
7. [Observability — VictoriaMetrics, Grafana, and Fluent Bit]({{< relref "/docs/building/07-observability" >}})
8. [Backup — Longhorn to Cloudflare R2]({{< relref "/docs/building/08-backup" >}})
9. [Secrets Management — Infisical + External Secrets Operator]({{< relref "/docs/building/09-secrets" >}})
10. [Local Inference — Ollama, LiteLLM, and OpenRouter]({{< relref "/docs/building/10-local-inference" >}})
11. [Agentic Control Plane — Sympozium]({{< relref "/docs/building/11-agentic-control-plane" >}})
12. [GPU Containers on Talos — The Validation Fix]({{< relref "/docs/building/12-gpu-talos-fix" >}})
13. [Unified Auth — Authentik SSO for the Entire Cluster]({{< relref "/docs/building/13-unified-auth" >}})
14. [Multi-tenancy — Disposable Kubernetes Clusters with vCluster]({{< relref "/docs/building/14-multi-tenancy" >}})
15. [Paperclip — An AI Agent Orchestrator on Frank]({{< relref "/docs/building/15-paperclip" >}})
16. [Media Generation — ComfyUI and GPU Time-Sharing]({{< relref "/docs/building/16-media-generation" >}})
17. [Hopping Through the Portal — A Public Edge Cluster]({{< relref "/docs/building/17-public-edge" >}})
18. [Persistent Agent — A Kali Workstation on Kubernetes]({{< relref "/docs/building/18-persistent-agent" >}})
19. [Progressive Delivery with Argo Rollouts]({{< relref "/docs/building/19-progressive-delivery" >}})
20. [Workflow Automation with n8n]({{< relref "/docs/building/20-workflow-automation" >}})
21. [Secure Agent Pod — Hardening an AI Coding Workstation]({{< relref "/docs/building/21-secure-agent-pod" >}})
22. [Health Monitoring — Feature Probes, Heartbeats, and Telegram Alerts]({{< relref "/docs/building/22-health-monitoring" >}})
23. [Health Bridge — Closing the Loop from Grafana Alerts to GitHub Issues]({{< relref "/docs/building/23-health-bridge" >}})
24. [In-Cluster Ingress — Traefik, Wildcard TLS, and a Homepage Dashboard]({{< relref "/docs/building/24-in-cluster-ingress" >}})
25. [VK Relay — Tunneling the Browser to a Local Agent Server]({{< relref "/docs/building/25-vk-relay" >}})
26. [VK Remote — Self-Hosting the Kanban Backend Before the Cloud Dies]({{< relref "/docs/building/26-vk-remote-self-host" >}})
27. [CI/CD Platform — Gitea, Tekton, Zot, and Cosign]({{< relref "/docs/building/27-cicd-platform" >}})
28. [Agent Images and the VK-Local Sidecar — Unbaking VibeKanban]({{< relref "/docs/building/28-agent-images-sidecar" >}})
29. [Ruflo — A Swarm Orchestrator Next to Paperclip]({{< relref "/docs/building/29-ruflo" >}})
30. [Building The Frank Papers — Research Infrastructure for a Third Series]({{< relref "/docs/building/30-frank-papers" >}})
31. [Building Edge Observability — Watching Frank's Edge Without Watching Frank's Edge Burn]({{< relref "/docs/building/31-edge-observability" >}})

- Virtual Machines with KubeVirt _(planned)_

## Operating on Frank — Series Index

Companion series with day-to-day commands, health checks, and debugging guides.

1. [Operating on Cluster & Nodes]({{< relref "/docs/operating/01-cluster-nodes" >}})
2. [Operating on Storage & Backups]({{< relref "/docs/operating/02-storage-backups" >}})
3. [Operating on GitOps]({{< relref "/docs/operating/03-gitops" >}})
4. [Operating on GPU Compute]({{< relref "/docs/operating/04-gpu-compute" >}})
5. [Operating on Observability]({{< relref "/docs/operating/05-observability" >}})
6. [Operating on Secrets]({{< relref "/docs/operating/06-secrets" >}})
7. [Operating on Local Inference]({{< relref "/docs/operating/07-inference" >}})
8. [Operating on Authentication]({{< relref "/docs/operating/08-auth" >}})
9. [Operating on Multi-tenancy]({{< relref "/docs/operating/09-multi-tenancy" >}})
10. [Operating on Media Generation]({{< relref "/docs/operating/10-media-generation" >}})
11. [Operating on Hop — Single-Node Talos Edge Cluster]({{< relref "/docs/operating/11-public-edge" >}})
12. [Operating on Progressive Delivery]({{< relref "/docs/operating/12-progressive-delivery" >}})
13. [Operating on Workflow Automation]({{< relref "/docs/operating/13-workflow-automation" >}})
14. [Operating on Secure Agent Pod]({{< relref "/docs/operating/14-secure-agent-pod" >}})
15. [Operating on Health Monitoring]({{< relref "/docs/operating/15-health-monitoring" >}})
16. [Operating on Health Bridge]({{< relref "/docs/operating/16-health-bridge" >}})
17. [Operating on In-Cluster Ingress]({{< relref "/docs/operating/17-ingress" >}})
18. [Operating on Paperclip]({{< relref "/docs/operating/18-paperclip" >}})
19. [Git Credentials Without a Shell]({{< relref "/docs/operating/19-git-credentials-without-a-shell" >}})
20. [Operating on VK Relay]({{< relref "/docs/operating/20-vk-relay" >}})
21. [Operating on VK Remote]({{< relref "/docs/operating/21-vk-remote" >}})
22. [Operating on CI/CD Platform]({{< relref "/docs/operating/22-cicd-platform" >}})
23. [Operating on ArgoCD Drift]({{< relref "/docs/operating/23-argocd-drift-detective" >}})
24. [Operating on Ruflo]({{< relref "/docs/operating/24-ruflo" >}})
