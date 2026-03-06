# Frank Cluster — AI-Hybrid Kubernetes Homelab

[![Deploy Blog](https://github.com/derio-net/frank/actions/workflows/deploy-blog.yml/badge.svg)](https://github.com/derio-net/frank/actions/workflows/deploy-blog.yml)

Enterprise-grade Kubernetes cluster on Talos Linux across heterogeneous hardware, managed with GitOps via ArgoCD.

**Blog:** [Building Frank Cluster](https://derio-net.github.io/frank/) — A tutorial series documenting the build process.

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
| RGB | OpenRGB | GitOps-managed LED control on gpu-1 via USB HID |

## Repository Structure

```
frank/
├── apps/
│   ├── root/                  # App-of-Apps Helm chart (ArgoCD entry point)
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/         # One Application CR per infrastructure component
│   ├── argocd/values.yaml     # ArgoCD Helm values
│   ├── cilium/
│   │   ├── values.yaml
│   │   └── manifests/         # L2 pool, announcement policy
│   ├── longhorn/
│   │   ├── values.yaml
│   │   └── manifests/         # GPU-local StorageClass
│   ├── gpu-operator/values.yaml
│   ├── intel-gpu-driver/
│   │   ├── values.yaml
│   │   └── chart/             # Vendored chart with K8s 1.35 / Talos patches
│   └── openrgb/manifests/     # DaemonSet + ConfigMap for LED control
├── patches/
│   ├── README.md              # Node reference + phase status
│   ├── phase01-node-config/   # Node labels, scheduling
│   ├── phase02-cilium/        # CNI swap to Cilium
│   ├── phase03-longhorn/      # iSCSI tools, extra disks
│   ├── phase04-gpu/           # NVIDIA extensions + GPU taint
│   └── phase05-mini-config/   # Intel i915 + iGPU DRA extensions
├── blog/                      # Hugo blog (PaperMod theme)
│   ├── hugo.toml
│   ├── content/posts/         # 7 posts documenting the build
│   └── layouts/shortcodes/    # Custom shortcodes (roadmap, etc.)
├── docs/plans/                # Architecture and implementation plans
├── omni/                      # Omni-specific configs
└── scripts/                   # Utility scripts
```

## Environment Setup

```bash
source .env          # Sets KUBECONFIG + TALOSCONFIG
source .env_devops   # Sets OMNI_ENDPOINT + OMNI_SERVICE_ACCOUNT_KEY
```

## ArgoCD Access

ArgoCD is exposed via Cilium L2 LoadBalancer:

```
http://192.168.55.200
```

CLI access:

```bash
argocd login 192.168.55.200 --plaintext --username admin

# List all apps
argocd app list
```

## Current Status

| Application | Status | Notes |
|------------|--------|-------|
| cilium | Synced/Healthy | 7/7 agents, eBPF kube-proxy replacement |
| cilium-config | Synced/Healthy | L2 pool + announcement policy |
| longhorn | Synced/Healthy | All 7 nodes schedulable |
| longhorn-extras | Synced/Healthy | GPU-local StorageClass |
| intel-gpu-driver | Synced/Healthy | DRA driver on mini-1/2/3 |
| openrgb | Synced/Healthy | LED control on gpu-1 |
| gpu-operator | Synced/Healthy | RTX 5070 on gpu-1 |

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
