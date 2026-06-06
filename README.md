# Frank, the Talos Cluster — AI-Hybrid Kubernetes Homelab

[![Deploy Blog](https://github.com/derio-net/frank/actions/workflows/deploy-blog.yml/badge.svg)](https://github.com/derio-net/frank/actions/workflows/deploy-blog.yml)

Enterprise-grade Kubernetes cluster on Talos Linux across heterogeneous hardware, managed with GitOps via ArgoCD.

**Blog:** [Building Frank, the Talos Cluster](https://derio-net.github.io/frank/) — A tutorial series documenting the build process.

## Architecture

### Physical Zones

| Zone | Hardware | Role | Hostname(s) | IP(s) |
|------|----------|------|-------------|-------|
| A — Management | Raspberry Pi 5 (8GB) | Sidero Omni, Authentik, Traefik | raspi-omni | 192.168.55.1 |
| B — Core HA | 3x ASUS NUC (Intel Ultra 5, 64GB, 1TB NVMe, Arc iGPU) | Control-plane + worker | mini-1/2/3 | 192.168.55.21-23 |
| C — AI Compute | Desktop (i9, 128GB, RTX 5070 Ti 16GB, 2x4TB SSD) | GPU worker | gpu-1 | 192.168.55.31 |
| D — Edge | 2x RPi 4 + 1x legacy desktop | General workers | raspi-1/2, pc-1 | 192.168.55.41-42, .71 |
| E — Public Edge | Hetzner CX23 (2 vCPU, 4GB) | Hop cluster (standalone talosctl) | hop-1 | Hetzner public IP |

### Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| OS | Talos Linux | Immutable, API-driven |
| Management | Sidero Omni | Cluster lifecycle + Talos upgrades |
| Networking | Cilium CNI | eBPF kube-proxy replacement, L2 LoadBalancer, Hubble UI |
| Storage | Longhorn | Distributed block storage, 3-replica default + GPU-local StorageClass |
| GitOps | ArgoCD | App-of-Apps pattern, annotation-based tracking |
| GPU (NVIDIA) | GPU Operator | RTX 5070 Ti on gpu-1, driver-less (host driver), validation markers DaemonSet |
| GPU (Intel) | Intel GPU Resource Driver | DRA-based iGPU sharing on mini-1/2/3 (K8s 1.35) |
| Metrics | VictoriaMetrics | VMSingle + Alertmanager + node/kube-state exporters |
| Logs | VictoriaLogs + Fluent Bit | Centralised log aggregation and querying |
| Dashboards | Grafana | Pre-provisioned datasources (VictoriaMetrics, VictoriaLogs, GoatCounter via Infinity), Feature Health + Blog Edge dashboards, Telegram alerting |
| Blog Analytics | GoatCounter | Cookieless, single-binary; mesh-only admin at counter.cluster.derio.net, public beacon at counter.derio.net (LB 192.168.55.224, Caddy reverse-proxy from Hop) |
| Edge HTTP Security | CrowdSec | Agent on Hop tailing Caddy access logs; caddy-crowdsec-bouncer enforces decisions at the edge (no Frank dep on request path) |
| Runtime Security | Falco (modern_ebpf) + Falcosidekick | DaemonSet on Hop; syscall events → VictoriaLogs (Loki protocol) + direct Telegram for priority:critical |
| AI Alert Helper | ai-alert-helper (FastAPI) | LiteLLM-backed digest/investigate/surge-check + Telegram trace-analyst (0.2.0): ad-hoc security Q&A over VictoriaLogs/CrowdSec evidence, allowlisted chat, long-poll consumer |
| Health Probes | Blackbox Exporter | HTTP endpoint probing for feature health (n8n, Paperclip, Grafana, Blog) |
| Heartbeat Ingestion | Pushgateway | Receives heartbeat metrics from cron jobs, scraped by VictoriaMetrics |
| Alert Bridge | Health Bridge | Grafana webhook → GitHub Project lifecycle state updates (healthy/degraded/dead); v0.3.0 auto-closes healed bug issues |
| Backup | Longhorn → Cloudflare R2 | Daily + weekly PVC backup, SOPS-encrypted credentials |
| Secrets | Infisical + External Secrets Operator | Self-hosted secret store, ExternalSecret → K8s Secret sync |
| RGB | OpenRGB | GitOps-managed LED control on gpu-1 via USB HID (IT5701 V3.5.14.0 firmware lock under investigation) |
| Local Inference | Ollama | LLM serving on gpu-1's RTX 5070 Ti 16GB — multimodal (Gemma 4 12B, Qwen2.5-VL 7B), general (Mistral Small 3.2 24B, Qwen3 14B), code (Qwen2.5-Coder 14B), MoE flagship (Qwen3.6 35B-A3B, CPU-offloaded experts) |
| API Gateway | LiteLLM | Unified OpenAI-compatible proxy routing to local Ollama models (local-only since 2026-06-04; 14 aliases incl. 64k-context + no-think variants), amd64-pinned pods + migrations Job |
| Agentic Control Plane | Sympozium | K8s-native agents — every agent is a Pod, every policy a CRD, every execution a Job |
| Identity & Auth | Authentik | Self-hosted IdP — OIDC SSO for ArgoCD, Grafana; forward-auth proxy for Longhorn, Hubble, Sympozium |
| Multi-tenancy | vCluster | Virtual K8s clusters inside Frank — disposable sandboxes via ArgoCD |
| Agent Orchestrator | Paperclip | Company-model AI agents — org charts, budgets, delegation chains routing through LiteLLM, with `paperclip-shell` sidecar (SSH+Mosh on `192.168.55.221`, ConfigMap-driven tool inventory) for 24/7 operator access |
| Swarm Orchestrator | Ruflo (claude-flow + ruvocal) | Hybrid pod (ruvocal SSR + agent-shell-base sidecar), zero direct frontier-LLM keys, SSH+Mosh shell on `192.168.55.222`, web UI at `ruflo.cluster.derio.net` |
| Media Generation | ComfyUI | Diffusion models (LTX-2.3 video, SDXL image, Stable Audio) on gpu-1, time-shared with Ollama |
| GPU Switching | GPU Switcher | Custom Go dashboard for one-click GPU time-sharing between Ollama and ComfyUI |
| Certificate Management | cert-manager | Automated TLS certificate lifecycle for webhooks and internal services |
| Public Edge | Hop (Hetzner CX23) | Single-node Talos cluster — public-facing edge for mesh networking and blog hosting |
| Mesh Networking | Headscale + Tailscale | WireGuard mesh — remote homelab access, MagicDNS split-DNS |
| Edge Ingress | Caddy | Automatic TLS (Cloudflare DNS challenge), public/mesh routing on Hop |
| Progressive Delivery | Argo Rollouts | Canary (LiteLLM, replica-count weighting, manual pause gating; metric-source replacement spec'd at `docs/superpowers/specs/2026-05-04--deploy--litellm-canary-metric-source-design.md`), blue-green (Sympozium + HTTP healthcheck) |
| Workflow Automation | n8n | Per-user instances on gpu-1, Authentik forward-auth, dedicated PostgreSQL, Prometheus metrics |
| Secure Agent Pod | Kali Linux (sidecar: VibeKanban) | Hardened non-root coding agent workstation on gpu-1; two-container pod (kali + vk-local) sharing `/home/claude` PVC; **s6-overlay-supervised** sshd + supercronic, **tmux-continuum-restored** layout across restarts; Cilium egress, ESO secrets, SSH + VibeKanban UI + mosh/tmux persistent shells (UDP 60000-60015 on a sibling LB IP) |
| Agent Images | `derio-net/agent-images` (shared base) | Multi-image repo: `agent-base` (debian:bookworm + common toolchain) → `agent-shell-base` (s6-overlay v3 + sshd + supercronic + tmux/mosh + tmux-resurrect/continuum) → `secure-agent-kali`; sibling `vk-local` from `agent-base`; matrix CI + cross-repo `repository_dispatch` → frank lockstep bumper |
| Hermes Agent Shell | Hermes Agent (Nous Research) | Standalone SSH/Mosh shell pod on gpu-1 (`hermes-agent-shell` image), BYOK → in-cluster LiteLLM virtual key; sshd env-scrub bridged via profile.d shim; provider pinned in `~/.hermes/config.yaml` (PVC state, manual-op) |
| ArgoCD Notifications | Native ArgoCD subsystem | Telegram alerts on agent-pod sync events (image bumps, manual rollouts) — operator gets ~30s heads-up before mosh sessions die |
| VK Remote (self-hosted) | PostgreSQL 16 + ElectricSQL + Rust/Axum | Self-hosted VibeKanban kanban API server, local JWT auth, Authentik SSO via Traefik |
| VK Relay | VK Relay Server (sidecar) | WebSocket relay tunneling browser API calls to local VK agent server via yamux multiplexing, SPAKE2 pairing |
| In-Cluster Ingress | Traefik v3 | Wildcard TLS (`*.cluster.derio.net`) via ACME + Cloudflare DNS-01, Authentik forward-auth, raspi edge nodes |
| CI/CD Platform | Gitea + Tekton + Zot | Self-hosted git forge (GitHub mirror), K8s-native pipelines, OCI registry with cosign signing — all on pc-1 |
| Cluster Dashboard | gethomepage.dev | Service catalog at `master.cluster.derio.net` with HTTP health indicators and custom bookmarks |
| The Frank Papers | Third blog series (research) | Hugo section with dossier-gate pre-commit hook, Mermaid Frank theme, five `papers/` shortcodes, render-time cross-series backlinks (zero-retrofit) |
| Ansible Automation | AWX | Operator-managed upstream Ansible controller (the `auto` layer) — the imperative counterweight reaching non-Talos home-lab hosts; native OIDC SSO via Authentik; Job Templates pull playbooks from a Gitea repo |

## Repository Structure

```
frank/
├── apps/
│   ├── root/                  # App-of-Apps Helm chart (ArgoCD entry point)
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/         # One Application CR per infrastructure component
│   ├── argocd/values.yaml
│   ├── cilium/values.yaml + manifests/
│   ├── longhorn/values.yaml + manifests/
│   ├── gpu-operator/values.yaml + manifests/  # GPU Operator values
│   ├── gpu-operator-extras/manifests/         # Validation markers DaemonSet
│   ├── intel-gpu-driver/values.yaml + chart/  # Vendored, K8s 1.35 patches
│   ├── openrgb/manifests/
│   ├── victoria-metrics/values.yaml + manifests/  # Metrics, alerting, Grafana
│   ├── blackbox-exporter/manifests/               # HTTP endpoint probes (Feature Health)
│   ├── pushgateway/manifests/                     # Heartbeat metric ingestion from cron jobs
│   ├── grafana-alerting/manifests/                  # File-provisioned alerting (rules, contacts, policy, dashboard)
│   ├── health-bridge/manifests/                   # Grafana alert → GitHub lifecycle bridge
│   ├── ai-alert-helper/manifests/                 # LLM digest/surge-check + Telegram trace-analyst
│   ├── fluent-bit/values.yaml                     # Log shipping
│   ├── external-secrets/values.yaml              # ESO operator
│   ├── infisical/values.yaml + manifests/         # Infisical + ClusterSecretStore
│   ├── infisical-postgresql/values.yaml
│   ├── infisical-redis/values.yaml
│   ├── ollama/values.yaml                       # Ollama LLM server on gpu-1
│   ├── litellm/values.yaml + manifests/         # LiteLLM gateway + canary Rollout + analysis template
│   ├── cert-manager/values.yaml                 # cert-manager for webhook TLS
│   ├── sympozium/values.yaml                    # Sympozium agentic control plane
│   ├── sympozium-extras/manifests/              # Policies, PersonaPacks, LB Service, blue-green Rollout
│   ├── authentik/values.yaml + manifests/       # Authentik IdP + blueprints
│   ├── authentik-extras/manifests/              # K8s RBAC bindings for OIDC groups
│   ├── vclusters/                               # Per-vCluster Helm values
│   │   ├── template/values.yaml                 # Base config (SQLite, policies, sync)
│   │   └── experiments/values.yaml              # First sandbox instance
│   ├── paperclip-db/values.yaml                 # Bitnami PostgreSQL for Paperclip
│   ├── paperclip/manifests/                     # Paperclip Deployment + paperclip-shell sidecar, ConfigMap inventory, two PVCs, two LB Services
│   ├── ruflo-db/values.yaml                     # Bitnami PostgreSQL (parked) for ruflo
│   ├── ruflo/manifests/                         # Ruflo hybrid pod: ruvocal SSR + ruflo-shell sidecar, ConfigMap inventory, three PVCs, Traefik route
│   ├── comfyui/manifests/                       # ComfyUI diffusion model server (time-shared GPU)
│   ├── argo-rollouts/values.yaml               # Argo Rollouts controller (no traffic-router plugin — see building/19)
│   ├── argo-rollouts-extras/manifests/          # Currently empty (cilium RBAC removed 2026-05-04)
│   ├── gpu-switcher/manifests/ + app/           # GPU Switcher Go app + K8s manifests
│   ├── n8n-01/manifests/                       # n8n workflow automation (gpu-1, 192.168.55.216)
│   ├── n8n-01-postgresql/values.yaml           # Bitnami PostgreSQL for n8n-01
│   ├── secure-agent-pod/manifests/             # Secure coding agent pod (gpu-1, SSH + VibeKanban)
│   ├── hermes-agent-shell/manifests/           # Standalone hermes agent shell pod (gpu-1, SSH+Mosh, BYOK → LiteLLM)
│   ├── vk-remote/manifests/                   # VK remote web UI + relay sidecar (agents namespace)
│   ├── traefik/values.yaml + manifests/        # Traefik ingress (192.168.55.220), middlewares, IngressRoutes
│   ├── homepage/manifests/                     # gethomepage.dev dashboard (master.cluster.derio.net)
│   ├── gitea/values.yaml + manifests/          # Gitea git forge (192.168.55.209), GitHub mirrors, Authentik OIDC
│   ├── zot/values.yaml + manifests/            # Zot OCI registry (192.168.55.210), cert-manager TLS, cosign
│   ├── awx/values.yaml + manifests/            # AWX Operator + AWX CR — Ansible controller (auto layer), OIDC SSO
│   └── tekton/                                 # Tekton CI/CD platform on pc-1
│       ├── vendor/                             # Vendored releases (Pipelines, Triggers, Dashboard)
│       ├── tasks/                              # CI Tasks (git-clone, run-tests, build-push, cosign-sign, gitea-status)
│       ├── pipelines/                          # gitea-ci Pipeline (clone → test → build → sign → report)
│       ├── triggers/                           # EventListener, TriggerBinding, TriggerTemplate for Gitea webhooks
│       └── manifests/                          # ExternalSecrets, RBAC, Dashboard LB Service
├── clusters/
│   └── hop/                   # Hop edge cluster (Hetzner CX23, standalone talosctl)
│       ├── apps/              # Hop ArgoCD App-of-Apps
│       │   ├── root/          # Entry point — 7 Application CRs
│       │   ├── argocd/        # Minimal single-replica ArgoCD
│       │   ├── headscale/     # Headscale + Tailscale DaemonSet
│       │   ├── headplane/     # Headscale web UI
│       │   ├── caddy/         # Reverse proxy + TLS (Cloudflare DNS)
│       │   ├── blog/          # Hugo blog container
│       │   ├── landing/       # Private landing page (mesh-only)
│       │   └── storage/       # Static PVs for Hetzner Volume
│       ├── packer/            # Packer template for Hetzner Talos image
│       └── talosconfig/       # Talos client config (gitignored)
├── patches/                   # Talos machine config patches (legacy phaseNN- naming)
│   ├── phase01-node-config/   # Node labels, scheduling
│   ├── phase02-cilium/        # CNI swap to Cilium
│   ├── phase03-longhorn/      # iSCSI tools, extra disks
│   ├── phase04-gpu/           # NVIDIA extensions + GPU taint
│   ├── phase05-mini-config/   # Intel i915 + iGPU DRA extensions
│   ├── phase06-cicd/          # Containerd registry mirror for Zot
│   └── phase13-auth/          # kube-apiserver OIDC flags for Authentik
├── secrets/                   # SOPS/age-encrypted bootstrap secrets (applied out-of-band)
├── blog/                      # Hugo blog (Hextra theme)
│   ├── hugo.toml
│   ├── content/docs/building/       # 33 posts documenting the build
│   ├── content/docs/operating/      # 28 companion operations guides
│   ├── content/docs/papers/         # Frank Papers — research-grade landscape reviews (gated)
│   ├── assets/js/mermaid-frank.js   # Mermaid Frank theme (loads on .paper-post pages)
│   ├── layouts/partials/papers-*    # papers-backlink + papers-forwardlinks (cross-series)
│   └── layouts/shortcodes/          # Custom shortcodes (cluster-roadmap, papers/*)
├── docs/
│   ├── papers-dossiers/        # Frank Papers research dossiers (one per paper, gate-validated)
│   └── superpowers/
│       ├── plans/             # Active implementation plans
│       ├── archived-plans/    # Completed/deployed plans
│       ├── specs/             # Design specifications
│   └── runbooks/              # Manual operations registry
├── omni/                      # Omni-specific configs
├── scripts/                   # Utility scripts (plan-status.sh, validate-plans.sh, scaffold-paper.sh, validate-dossier.py)
└── .githooks/                 # Git hooks (plan header + agent-config + Papers dossier gate)
```

## Environment Setup

```bash
# Frank cluster
source .env          # Sets KUBECONFIG + TALOSCONFIG
source .env_devops   # Sets OMNI_ENDPOINT + OMNI_SERVICE_ACCOUNT_KEY

# Hop cluster (CAUTION: overrides KUBECONFIG)
source .env_hop      # Sets KUBECONFIG → clusters/hop/talosconfig/kubeconfig
```

## Service Access

The following UIs are exposed via Cilium L2 LoadBalancer with fixed IPs:

| Service | URL | IP |
|---------|-----|-----|
| ArgoCD | http://192.168.55.200 | 192.168.55.200 |
| Longhorn UI | http://192.168.55.201 | 192.168.55.201 |
| Hubble UI | http://192.168.55.202 | 192.168.55.202 |
| Grafana | http://192.168.55.203 | 192.168.55.203 |
| Infisical | http://192.168.55.204:8080 | 192.168.55.204 |
| LiteLLM Gateway | http://192.168.55.206:4000 | 192.168.55.206 |
| Sympozium Web UI | http://192.168.55.207:8080 | 192.168.55.207 |
| Gitea | http://192.168.55.209:3000 | 192.168.55.209 |
| Zot OCI Registry | https://192.168.55.210:5000 | 192.168.55.210 |
| Authentik | http://192.168.55.211:9000 | 192.168.55.211 |
| Paperclip | http://192.168.55.212:3100 | 192.168.55.212 |
| ComfyUI | http://192.168.55.213:8188 | 192.168.55.213 |
| GPU Switcher | http://192.168.55.214:8080 | 192.168.55.214 |
| Secure Agent Pod (SSH) | ssh claude@192.168.55.215 | 192.168.55.215 |
| n8n-01 | http://192.168.55.216:5678 | 192.168.55.216 |
| Tekton Dashboard | http://192.168.55.217:9097 | 192.168.55.217 |
| Secure Agent Pod (VibeKanban) | http://192.168.55.218:8081 | 192.168.55.218 |
| Secure Agent Pod (Mosh) | mosh + tmux persistent sessions — see [operating post](blog/content/docs/operating/14-secure-agent-pod/index.md#persistent-shells-with-mosh--tmux) | 192.168.55.219 |
| Traefik Ingress | https://*.cluster.derio.net | 192.168.55.220 |
| Paperclip Shell (SSH+Mosh) | ssh agent@192.168.55.221 — mosh UDP 60000-60015 | 192.168.55.221 |
| Ruflo Web UI | https://ruflo.cluster.derio.net | (via Traefik) |
| Ruflo Shell (SSH+Mosh) | ssh agent@192.168.55.222 — mosh UDP 60016-60031 | 192.168.55.222 |
| GitHub webhook receiver (`el-github-listener`) | reached via `webhooks.hop.derio.net` (Caddy on Hop → Tailscale mesh); receives PR + push events for `agentic-stoa/*` | 192.168.55.223 |
| GoatCounter | https://counter.cluster.derio.net (mesh) + https://counter.derio.net (public via Hop) | 192.168.55.224 |
| VictoriaLogs (LB) | http://192.168.55.225:9428 (cross-cluster ingest from Hop fluent-bit) | 192.168.55.225 |
| Hermes Agent Shell (SSH+Mosh) | ssh agent@192.168.55.226 — mosh UDP 60032-60047 | 192.168.55.226 |
| VK Remote | https://vk.cluster.derio.net | (via Traefik) |
| Homepage Dashboard | https://master.cluster.derio.net | (via Traefik) |
| AWX | https://awx.cluster.derio.net | (via Traefik) |

### Hop Cluster (Public Edge)

| Service | Domain | Access |
|---------|--------|--------|
| Headscale | headscale.hop.derio.net | Public |
| Headplane | headplane.hop.derio.net | Mesh only |
| Blog | blog.derio.net/frank | Public |
| Landing | entry.hop.derio.net | Mesh only |
| GitHub webhooks relay | webhooks.hop.derio.net | Public (forwards to Frank's `el-github-listener` at 192.168.55.223 over the Tailscale mesh; HMAC-validated by both Caddy and the EventListener) |

ArgoCD CLI access:

```bash
argocd login 192.168.55.200 --plaintext --username admin

# List all apps
argocd app list
```

## Current Status

| Application | Namespace | Notes |
|------------|-----------|-------|
| cilium | kube-system | 7/7 agents, eBPF kube-proxy replacement |
| cilium-config | kube-system | L2 pool + announcement policy |
| longhorn | longhorn-system | All 7 nodes schedulable |
| longhorn-extras | longhorn-system | GPU-local StorageClass, BackupTarget (R2), RecurringJobs |
| gpu-operator | gpu-operator | RTX 5070 Ti on gpu-1, nvidia.com/gpu: 1 allocatable |
| gpu-operator-extras | gpu-operator | Validation markers DaemonSet for Talos |
| intel-gpu-driver | intel-gpu-resource-driver | DRA driver on mini-1/2/3 |
| openrgb | openrgb | LED control on gpu-1 via USB HID (firmware V3.5.14.0 write lock; fans currently rainbow) |
| victoria-metrics | monitoring | VMSingle, Grafana (OIDC SSO via Authentik), Alertmanager, kube-state-metrics |
| fluent-bit | monitoring | Log shipping to VictoriaLogs |
| victoria-logs | monitoring | VictoriaLogs standalone |
| external-secrets | external-secrets | ESO 2.1.0 operator |
| infisical-postgresql | infisical | PostgreSQL backend for Infisical |
| infisical-redis | infisical | Redis backend for Infisical |
| infisical | infisical | Infisical v0.151.0 secret store (192.168.55.204:8080) |
| infisical-extras | external-secrets | ClusterSecretStore (infisical provider) |
| ollama | ollama | LLM inference on gpu-1 (RTX 5070 Ti, 100% GPU) |
| litellm | litellm | Unified OpenAI-compatible API gateway |
| litellm-extras | litellm | Model router config, ExternalSecret for API keys, canary Rollout + AnalysisTemplate |
| cert-manager | cert-manager | TLS certificate automation for webhooks |
| sympozium | sympozium-system | Agentic control plane (controller, apiserver, webhook, NATS, OTel) |
| sympozium-extras | sympozium-system | PersonaPacks, Policies, ExternalSecret, LB Service, blue-green Rollout + AnalysisTemplate |
| argocd | argocd | Self-managed via App-of-Apps, OIDC SSO via Authentik |
| argocd-notifications | argocd | Telegram bump alerts via webhook service (subscribes secure-agent-pod on-sync-running/succeeded) |
| authentik | authentik | Authentik IdP (192.168.55.211:9000), OIDC providers for ArgoCD, Grafana, Infisical |
| authentik-extras | authentik | K8s RBAC ClusterRoleBindings mapping Authentik groups to cluster roles |
| vcluster-experiments | vcluster-experiments | Disposable virtual K8s cluster (SQLite-backed, resource-quoted sandbox) |
| paperclip-db | paperclip-system | Bitnami PostgreSQL 14.1.10 (GCR mirror), Longhorn 5Gi |
| paperclip | paperclip-system | Hybrid pod: Paperclip AI agent orchestrator (192.168.55.212:3100, 12Gi memory limit, defensive nvidia.com/gpu toleration) + paperclip-shell sidecar (`ghcr.io/derio-net/paperclip-shell`), ConfigMap-driven tool inventory, SSH+Mosh on 192.168.55.221 |
| ruflo-db | ruflo-system | Bitnami PostgreSQL 14.1.10 (GCR mirror), Longhorn 20Gi — parked (ruvocal at pinned SHA uses RVF JSON store, not Postgres) |
| ruflo | ruflo-system | Hybrid pod: ruvocal SSR (`ghcr.io/derio-net/ruflo-server`) + agent-shell-base sidecar (`ghcr.io/derio-net/ruflo-shell`), 3 PVCs, web UI at `ruflo.cluster.derio.net`, SSH+Mosh on 192.168.55.222 |
| comfyui | comfyui | ComfyUI diffusion model server (192.168.55.213:8188), replicas managed by GPU Switcher |
| gpu-switcher | gpu-switcher | GPU time-sharing dashboard (192.168.55.214:8080), custom Go app (ghcr.io/derio-net/gpu-switcher:v0.1.1) |
| secure-agent-pod | secure-agent-pod | Hardened coding agent workstation on gpu-1: 2-container pod (kali + vk-local sidecar) sharing `/home/claude` PVC, SSH :22, VibeKanban :8081, non-root, Cilium egress, ESO secrets |
| vk-remote | agents | Self-hosted VK kanban API (PG 16 + ElectricSQL + Rust/Axum) + relay sidecar (vk.cluster.derio.net), Authentik SSO |
| hermes-agent-shell | hermes-agent-shell | Standalone hermes agent shell on gpu-1 (SSH :22 + mosh UDP 60032-60047 on 192.168.55.226), BYOK → LiteLLM, home PVC |
| argo-rollouts | argo-rollouts | Progressive delivery controller (no traffic-router plugin; replica-count canary for LiteLLM, blue-green for Sympozium) |
| argo-rollouts-extras | argo-rollouts | Currently empty — held the broken Cilium plugin config + CiliumEnvoyConfig RBAC, both removed 2026-05-04 |
| n8n-01 | n8n-01 | n8n workflow automation on gpu-1 (192.168.55.216:5678), Authentik forward-auth |
| n8n-01-postgresql | n8n-01 | Bitnami PostgreSQL 14.1.10 for n8n-01 |
| blackbox-exporter | monitoring | HTTP endpoint probes for feature health (VMProbe → VictoriaMetrics) |
| pushgateway | monitoring | Heartbeat metric ingestion from Willikins cron jobs (VMServiceScrape) |
| grafana-alerting | monitoring | File-provisioned alerting: 5 rules, 2 contact points, notification policy, Feature Health dashboard |
| health-bridge | monitoring | Grafana webhook → GitHub Project lifecycle updates + healed-issue auto-close (ghcr.io/derio-net/health-bridge:v0.3.0) |
| traefik | traefik-system | In-cluster ingress controller (192.168.55.220), ACME wildcard TLS for `*.cluster.derio.net` |
| traefik-extras | traefik-system | Middleware CRDs (security headers, IP allowlist, Authentik forward-auth) + 16 IngressRoutes |
| homepage | homepage | Cluster dashboard at `master.cluster.derio.net`, HTTP health indicators, service catalog |
| gitea | gitea | Git forge with GitHub pull-mirror (192.168.55.209:3000), Authentik OIDC SSO |
| gitea-extras | gitea | ExternalSecret for admin password, OIDC client secret, GitHub mirror token |
| zot | zot | OCI container/artifact registry (192.168.55.210:5000), self-signed TLS via cert-manager |
| zot-extras | zot | Certificate, ClusterIssuer, ExternalSecret for push password and OIDC |
| tekton-pipelines | tekton-pipelines | Tekton Pipelines controller + webhook (vendored release) |
| tekton-triggers | tekton-pipelines | Tekton Triggers controller + interceptors (vendored release) |
| tekton-dashboard | tekton-pipelines | Tekton Dashboard (192.168.55.217:9097, vendored release) |
| tekton-extras | tekton-pipelines | CI Tasks, gitea-ci Pipeline, Gitea EventListener, ExternalSecrets, RBAC |
| longhorn-cicd | longhorn-system | Single-replica StorageClass for CI/CD workloads on pc-1 |
| goatcounter | goatcounter-system | Blog analytics (arp242/goatcounter:2.7.0); LB 192.168.55.224, mesh-only admin via Authentik forward-auth |
| ai-alert-helper | ai-alert-helper-system | FastAPI service (0.2.0) — daily digest CronJob + surge-check + Grafana webhook receiver + Telegram trace-analyst (single replica, Recreate — one getUpdates consumer per bot token) |
| awx | awx | AWX Operator + AWX CR (Ansible controller); OIDC SSO via Authentik; smoke-ping Job Template green vs non-Talos home-lab hosts |

### Hop Cluster Applications

| Application | Namespace | Notes |
|------------|-----------|-------|
| argocd | argocd | Self-managed, minimal single-replica |
| headscale | headscale-system | Mesh coordination server + Tailscale DaemonSet (kernel mode) |
| headplane | headscale-system | Headscale web UI at /admin/ (mesh-only access) |
| caddy | caddy-system | Reverse proxy + TLS, hostPort 80/443, Cloudflare DNS challenge |
| blog | blog-system | Hugo static site (ghcr.io/derio-net/frank-blog:latest) |
| landing | landing-system | Private landing page (mesh-only) |
| storage | kube-system | Local StorageClass + static PVs on Hetzner Volume |
| fluent-bit | monitoring | Log shipping to Frank VictoriaLogs LB IP (192.168.55.225) via Tailscale subnet route |
| crowdsec | crowdsec-system | Agent tails Caddy logs + LAPI; caddy-crowdsec-bouncer enforces decisions at edge (postStart re-registers bouncer key from Secret since no PVC) |
| falco | falco-system | modern_ebpf DaemonSet + Falcosidekick → Loki output to Frank VictoriaLogs + direct Telegram for priority:critical |

## Adding a New Application

### Frank Cluster

1. Add Helm values to `apps/<name>/values.yaml`
2. Add an Application template to `apps/root/templates/<name>.yaml`
3. Commit and push — ArgoCD auto-syncs the root app and creates the child Application

### Hop Cluster

1. Add raw manifests to `clusters/hop/apps/<name>/manifests/`
2. Add an Application template to `clusters/hop/apps/root/templates/<name>.yaml`
3. Commit and push — Hop's ArgoCD auto-syncs

## References

- [Talos Linux Docs](https://www.talos.dev/)
- [Sidero Omni Docs](https://omni.siderolabs.com/)
- [ArgoCD Docs](https://argo-cd.readthedocs.io/)
- [Longhorn Docs](https://longhorn.io/docs/)
- [Cilium Docs](https://docs.cilium.io/)
- [Intel GPU Resource Driver](https://github.com/intel/intel-resource-drivers-for-kubernetes)
- [Headscale](https://github.com/juanfont/headscale) — Open-source Tailscale control server
- [Caddy](https://caddyserver.com/) — Automatic HTTPS web server
- [Hetzner Cloud](https://www.hetzner.com/cloud) — European cloud provider
