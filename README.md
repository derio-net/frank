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
| C — AI Compute | Desktop (i9, 128GB, RTX 5070, 2x4TB SSD) | GPU worker | gpu-1 | 192.168.55.31 |
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
| Dashboards | Grafana | Pre-provisioned datasources (VictoriaMetrics, VictoriaLogs), Feature Health dashboard + Telegram alerting |
| Health Probes | Blackbox Exporter | HTTP endpoint probing for feature health (n8n, Paperclip, Grafana, Blog) |
| Heartbeat Ingestion | Pushgateway | Receives heartbeat metrics from cron jobs, scraped by VictoriaMetrics |
| Backup | Longhorn → Cloudflare R2 | Daily + weekly PVC backup, SOPS-encrypted credentials |
| Secrets | Infisical + External Secrets Operator | Self-hosted secret store, ExternalSecret → K8s Secret sync |
| RGB | OpenRGB | GitOps-managed LED control on gpu-1 via USB HID (IT5701 V3.5.14.0 firmware lock under investigation) |
| Local Inference | Ollama | LLM serving on gpu-1's RTX 5070 (qwen3.5:9b, deepseek-coder:6.7b) |
| API Gateway | LiteLLM | Unified OpenAI-compatible proxy routing to Ollama + OpenRouter cloud models |
| Agentic Control Plane | Sympozium | K8s-native agents — every agent is a Pod, every policy a CRD, every execution a Job |
| Identity & Auth | Authentik | Self-hosted IdP — OIDC SSO for ArgoCD, Grafana; forward-auth proxy for Longhorn, Hubble, Sympozium |
| Multi-tenancy | vCluster | Virtual K8s clusters inside Frank — disposable sandboxes via ArgoCD |
| Agent Orchestrator | Paperclip | Company-model AI agents — org charts, budgets, delegation chains routing through LiteLLM |
| Media Generation | ComfyUI | Diffusion models (LTX-2.3 video, SDXL image, Stable Audio) on gpu-1, time-shared with Ollama |
| GPU Switching | GPU Switcher | Custom Go dashboard for one-click GPU time-sharing between Ollama and ComfyUI |
| Certificate Management | cert-manager | Automated TLS certificate lifecycle for webhooks and internal services |
| Public Edge | Hop (Hetzner CX23) | Single-node Talos cluster — public-facing edge for mesh networking and blog hosting |
| Mesh Networking | Headscale + Tailscale | WireGuard mesh — remote homelab access, MagicDNS split-DNS |
| Edge Ingress | Caddy | Automatic TLS (Cloudflare DNS challenge), public/mesh routing on Hop |
| Progressive Delivery | Argo Rollouts | Canary (LiteLLM + Cilium traffic split + VictoriaMetrics analysis), blue-green (Sympozium + HTTP healthcheck) |
| Workflow Automation | n8n | Per-user instances on gpu-1, Authentik forward-auth, dedicated PostgreSQL, Prometheus metrics |
| Secure Agent Pod | Kali Linux + VibeKanban | Hardened non-root coding agent workstation on gpu-1, Cilium egress controls, ESO secrets, SSH + VibeKanban UI |

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
│   ├── paperclip-db/values.yaml                 # Bitnami PostgreSQL for Paperclip
│   ├── paperclip/manifests/                     # Paperclip Deployment, ExternalSecrets, PVC, LB Service
│   ├── comfyui/manifests/                       # ComfyUI diffusion model server (time-shared GPU)
│   ├── argo-rollouts/values.yaml               # Argo Rollouts controller
│   ├── argo-rollouts-extras/manifests/          # Cilium plugin config + RBAC
│   ├── gpu-switcher/manifests/ + app/           # GPU Switcher Go app + K8s manifests
│   ├── n8n-01/manifests/                       # n8n workflow automation (gpu-1, 192.168.55.216)
│   ├── n8n-01-postgresql/values.yaml           # Bitnami PostgreSQL for n8n-01
│   └── secure-agent-pod/manifests/             # Secure coding agent pod (gpu-1, SSH + VibeKanban)
│       ├── template/values.yaml                 # Base config (SQLite, policies, sync)
│       └── experiments/values.yaml              # First sandbox instance
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
│   └── phase13-auth/          # kube-apiserver OIDC flags for Authentik
├── secrets/                   # SOPS/age-encrypted bootstrap secrets (applied out-of-band)
├── blog/                      # Hugo blog (PaperMod theme)
│   ├── hugo.toml
│   ├── content/building/       # 20 posts documenting the build
│   ├── content/operating/      # 13 companion operations guides
│   └── layouts/shortcodes/    # Custom shortcodes (cluster-roadmap, etc.)
├── docs/
│   ├── plans/                 # Architecture and implementation plans
│   └── runbooks/              # Manual operations registry
├── omni/                      # Omni-specific configs
└── scripts/                   # Utility scripts
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
| Authentik | http://192.168.55.211:9000 | 192.168.55.211 |
| Paperclip | http://192.168.55.212:3100 | 192.168.55.212 |
| ComfyUI | http://192.168.55.213:8188 | 192.168.55.213 |
| GPU Switcher | http://192.168.55.214:8080 | 192.168.55.214 |
| Secure Agent Pod (SSH) | ssh claude@192.168.55.215 | 192.168.55.215 |
| n8n-01 | http://192.168.55.216:5678 | 192.168.55.216 |
| Secure Agent Pod (VibeKanban) | http://192.168.55.218:8081 | 192.168.55.218 |

### Hop Cluster (Public Edge)

| Service | Domain | Access |
|---------|--------|--------|
| Headscale | headscale.hop.derio.net | Public |
| Headplane | headplane.hop.derio.net | Mesh only |
| Blog | blog.derio.net/frank | Public |
| Landing | entry.hop.derio.net | Mesh only |

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
| authentik | authentik | Authentik IdP (192.168.55.211:9000), OIDC providers for ArgoCD, Grafana, Infisical |
| authentik-extras | authentik | K8s RBAC ClusterRoleBindings mapping Authentik groups to cluster roles |
| vcluster-experiments | vcluster-experiments | Disposable virtual K8s cluster (SQLite-backed, resource-quoted sandbox) |
| paperclip-db | paperclip-system | Bitnami PostgreSQL 14.1.10 (GCR mirror), Longhorn 5Gi |
| paperclip | paperclip-system | Paperclip v0.3.1 AI agent orchestrator (192.168.55.212:3100) |
| comfyui | comfyui | ComfyUI diffusion model server (192.168.55.213:8188), replicas managed by GPU Switcher |
| gpu-switcher | gpu-switcher | GPU time-sharing dashboard (192.168.55.214:8080), custom Go app (ghcr.io/derio-net/gpu-switcher:v0.1.1) |
| secure-agent-pod | secure-agent-pod | Hardened coding agent workstation on gpu-1 (SSH :22, VibeKanban :8081), non-root, Cilium egress, ESO secrets |
| argo-rollouts | argo-rollouts | Progressive delivery controller + Cilium traffic router plugin |
| argo-rollouts-extras | argo-rollouts | Cilium plugin ConfigMap + supplemental RBAC for CiliumEnvoyConfig |
| n8n-01 | n8n-01 | n8n workflow automation on gpu-1 (192.168.55.216:5678), Authentik forward-auth |
| n8n-01-postgresql | n8n-01 | Bitnami PostgreSQL 14.1.10 for n8n-01 |
| blackbox-exporter | monitoring | HTTP endpoint probes for feature health (VMProbe → VictoriaMetrics) |
| pushgateway | monitoring | Heartbeat metric ingestion from Willikins cron jobs (VMServiceScrape) |

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
