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

### Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| OS | Talos Linux | Immutable, API-driven |
| Management | Sidero Omni | Cluster lifecycle + Talos upgrades |
| Networking | Cilium CNI | eBPF kube-proxy replacement, L2 LoadBalancer, Hubble UI |
| Storage | Longhorn | Distributed block storage, 3-replica default + GPU-local StorageClass |
| GitOps | ArgoCD | App-of-Apps pattern, annotation-based tracking |
| GPU (NVIDIA) | GPU Operator | RTX 5070 on gpu-1, driver-less (host driver) |
| GPU (Intel) | Intel GPU Resource Driver | DRA-based iGPU sharing on mini-1/2/3 (K8s 1.35) |
| Metrics | VictoriaMetrics | VMSingle + Alertmanager + node/kube-state exporters |
| Logs | VictoriaLogs + Fluent Bit | Centralised log aggregation and querying |
| Dashboards | Grafana | Pre-provisioned datasources (VictoriaMetrics, VictoriaLogs) |
| Backup | Longhorn → Cloudflare R2 | Daily + weekly PVC backup, SOPS-encrypted credentials |
| Secrets | Infisical + External Secrets Operator | Self-hosted secret store, ExternalSecret → K8s Secret sync |
| RGB | OpenRGB | GitOps-managed LED control on gpu-1 via USB HID |
| Local Inference | Ollama | LLM serving on gpu-1's RTX 5070 (qwen3.5:9b, deepseek-coder:6.7b) |
| API Gateway | LiteLLM | Unified OpenAI-compatible proxy routing to Ollama + OpenRouter cloud models |
| Agentic Control Plane | Sympozium | K8s-native agents — every agent is a Pod, every policy a CRD, every execution a Job |
| Certificate Management | cert-manager | Automated TLS certificate lifecycle for webhooks and internal services |

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
│   ├── gpu-operator/values.yaml
│   ├── intel-gpu-driver/values.yaml + chart/  # Vendored, K8s 1.35 patches
│   ├── openrgb/manifests/
│   ├── victoria-metrics/values.yaml + manifests/  # Metrics, alerting, Grafana
│   ├── fluent-bit/values.yaml                     # Log shipping
│   ├── external-secrets/values.yaml              # ESO operator
│   ├── infisical/values.yaml + manifests/         # Infisical + ClusterSecretStore
│   ├── infisical-postgresql/values.yaml
│   ├── infisical-redis/values.yaml
│   ├── ollama/values.yaml                       # Ollama LLM server on gpu-1
│   ├── litellm/values.yaml + manifests/         # LiteLLM gateway + model config
│   ├── cert-manager/values.yaml                 # cert-manager for webhook TLS
│   ├── sympozium/values.yaml                    # Sympozium agentic control plane
│   └── sympozium-extras/manifests/              # Policies, PersonaPacks, LB Service
├── patches/
│   ├── phase01-node-config/   # Node labels, scheduling
│   ├── phase02-cilium/        # CNI swap to Cilium
│   ├── phase03-longhorn/      # iSCSI tools, extra disks
│   ├── phase04-gpu/           # NVIDIA extensions + GPU taint
│   └── phase05-mini-config/   # Intel i915 + iGPU DRA extensions
├── secrets/                   # SOPS/age-encrypted bootstrap secrets (applied out-of-band)
├── blog/                      # Hugo blog (PaperMod theme)
│   ├── hugo.toml
│   ├── content/posts/         # 12 posts documenting the build
│   └── layouts/shortcodes/    # Custom shortcodes (cluster-roadmap, etc.)
├── docs/
│   ├── plans/                 # Architecture and implementation plans
│   └── runbooks/              # Manual operations registry
├── omni/                      # Omni-specific configs
└── scripts/                   # Utility scripts
```

## Environment Setup

```bash
source .env          # Sets KUBECONFIG + TALOSCONFIG
source .env_devops   # Sets OMNI_ENDPOINT + OMNI_SERVICE_ACCOUNT_KEY
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
| gpu-operator | gpu-operator | RTX 5070 on gpu-1 |
| intel-gpu-driver | intel-gpu-resource-driver | DRA driver on mini-1/2/3 |
| openrgb | openrgb | LED control on gpu-1 via USB HID |
| victoria-metrics | monitoring | VMSingle, Grafana, Alertmanager, kube-state-metrics |
| fluent-bit | monitoring | Log shipping to VictoriaLogs |
| victoria-logs | monitoring | VictoriaLogs standalone |
| external-secrets | external-secrets | ESO 2.1.0 operator |
| infisical-postgresql | infisical | PostgreSQL backend for Infisical |
| infisical-redis | infisical | Redis backend for Infisical |
| infisical | infisical | Infisical v0.151.0 secret store (192.168.55.204:8080) |
| infisical-extras | external-secrets | ClusterSecretStore (infisical provider) |
| ollama | ollama | LLM inference on gpu-1 (RTX 5070) |
| litellm | litellm | Unified OpenAI-compatible API gateway |
| litellm-extras | litellm | Model router config + ExternalSecret for API keys |
| cert-manager | cert-manager | TLS certificate automation for webhooks |
| sympozium | sympozium-system | Agentic control plane (controller, apiserver, webhook, NATS, OTel) |
| sympozium-extras | sympozium-system | PersonaPacks, SympoziumPolicies, ExternalSecret, LB Service |

## Adding a New Application

1. Add Helm values to `apps/<name>/values.yaml`
2. Add an Application template to `apps/root/templates/<name>.yaml`
3. Commit and push — ArgoCD auto-syncs the root app and creates the child Application

## References

- [Talos Linux Docs](https://www.talos.dev/)
- [Sidero Omni Docs](https://omni.siderolabs.com/)
- [ArgoCD Docs](https://argo-cd.readthedocs.io/)
- [Longhorn Docs](https://longhorn.io/docs/)
- [Cilium Docs](https://docs.cilium.io/)
- [Intel GPU Resource Driver](https://github.com/intel/intel-resource-drivers-for-kubernetes)
