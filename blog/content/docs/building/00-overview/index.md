---
title: "Frank, the Talos Cluster: Overview & Roadmap"
date: 2026-03-06
draft: false
tags: ["overview", "roadmap"]
summary: "A living overview of Frank, the Talos Cluster — an AI-hybrid Kubernetes homelab. Technology roadmap, capabilities, and cluster state."
weight: 1
reader_goal: "Understand Frank's capability layers and how they map to hardware zones"
diataxis: reference
last_updated: 2026-07-15
---

This is the overview post for the **Frank, the Talos Cluster** series — a tutorial-style walkthrough of building an AI-hybrid Kubernetes homelab from scratch.

This post is a **living document**: it gets updated as new technologies and capabilities are added to the cluster.

## Roadmap

{{< roadmap >}}

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
| **The Frank Papers** | Third blog series — research-grade landscape reviews framed as decisions; dossier gate (`validate-dossier.py` + pre-commit hook), Mermaid Frank theme, five `papers/` shortcodes, render-time cross-series backlinks. **Prologue published 2026-05-18:** [Why Run Your Own Cluster in 2026?](/docs/papers/00-why-homelab-in-2026) |
| **GoatCounter** | Cookieless blog analytics — public beacon via Hop's Caddy at `counter.derio.net`, mesh-only admin at `counter.cluster.derio.net` with Authentik forward-auth (`192.168.55.224`) |
| **CrowdSec + caddy-crowdsec-bouncer** | Edge HTTP security — agent tails Caddy logs on Hop, Caddy bouncer enforces decisions locally without round-tripping to Frank |
| **Falco (modern_ebpf) + Falcosidekick** | Container runtime security on Talos — Loki output to VictoriaLogs (Loki push protocol) + direct Telegram for `priority:critical` |
| **ai-alert-helper** | FastAPI service — daily blog digest, alert-time LLM enrichment, surge detection (hour-of-day baseline computed in Python because LogsQL has no `quantile_over_time`); LiteLLM-backed swap contract for future Sympozium |
| **AWX** | Ansible automation controller — the imperative arm reaching non-Talos home-lab hosts over SSH; operator + `AWX` CR (two-layer reconcile), native OIDC SSO via Authentik, Gitea-backed Job Templates |
| **hermes (Nous Research)** | Terminal-native agent CLI in a dedicated `agent-shell-base` pod on gpu-1 — BYOK to LiteLLM (provider pinned via `config.yaml` mapping), profile.d shim defeating the sshd env-scrub, SSH+Mosh on `192.168.55.226` |

## Cluster State

| Node | Zone | Role | Hardware |
|------|------|------|----------|
| mini-1/2/3 | Core (B) | Control-plane + Worker | Intel Ultra 5, 64GB RAM, 1TB NVMe, Arc iGPU |
| gpu-1 | AI Compute (C) | Worker | i9, 128GB RAM, RTX 5070, 2x4TB SSD |
| pc-1 | Edge (D) | Worker | Legacy desktop, 64GB SSD + 3x HDD |
| raspi-1/2 | Edge (D) | Worker | Raspberry Pi 4, 32GB SD |

## Missteps

The roadmap has evolved significantly since the cluster was first built. Here are the decisions that got revised:

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---------------|-----------------|-----------------|--------|
| **Initial roadmap used a flat numbered list** — each new capability was slotted in by hand, making reordering and insertion painful | No structured layer model meant the sequence kept shifting as we discovered missing prerequisites | Adopted the 12-layer model from `docs/layers.yaml` and the `{{< roadmap >}}` shortcode, auto-generated from plan weight ordering | `cfb7dd1e` |
| **Blog series was a single flat directory** — operating and building content were mixed, making cross-referencing confusing | No clear separation between "how I built it" (building) and "how to operate it" (operating) | Split into `building/` and `operating/` series with cross-series backlinks, each with its own weight-ordered index | `39cfcec4` |
| **Papers prologue used `relref` to a draft building post** — build failed at CI because Hugo refuses to resolve `relref` targets with `draft: true` | Assumed `relref` would silently skip draft targets; Hugo returns a hard error | Replaced `relref` with plain `/docs/building/NN-slug` path — Hugo allows absolute document paths to drafts even when `relref` does not | `bd0415e6` |
| **Original bootstrap documented a manual Talos install** — SSH-based kubeadm flow described in the draft | Omni support was added after the initial bootstrap post was written, making the documented flow obsolete | Rewrote to describe the Omni-based bootstrap as the primary path, with a footnote that manual Talos installs are possible but not recommended | `ce2fcd9e` |
