# Frank Cluster — AI-Hybrid Kubernetes Homelab

Enterprise-grade Kubernetes cluster on Talos Linux across heterogeneous hardware, managed with GitOps via ArgoCD.

## Architecture

### Physical Zones

| Zone | Hardware | Role | Hostname(s) | IP(s) |
|------|----------|------|-------------|-------|
| A — Management | Raspberry Pi 5 (8GB) | Sidero Omni, Authentik, Traefik | raspi-omni | 192.168.55.1 |
| B — Core HA | 3x ASUS NUC (64GB, 1TB nvme) | control-plane + worker | mini-1/2/3 | 192.168.55.21-23 |
| C — AI Compute | Desktop (i9, 128GB, RTX 5070, 1TB nvme) | GPU worker | gpu-1 | 192.168.55.31 |
| D — Edge/Burst | 3x RPi 4 + 2x legacy desktops | General workers | raspi-1/2, pc-1 | 192.168.55.41-42, .71 |

### Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| OS | Talos Linux | Immutable, API-driven |
| Management | Sidero Omni | Cluster lifecycle + Talos upgrades |
| Networking | Cilium CNI | kube-proxy replacement, Hubble UI |
| Storage | Longhorn | Distributed block storage, 3-replica default |
| GitOps | ArgoCD v3.x | App-of-Apps pattern |
| GPU | NVIDIA GPU Operator | Pending — RTX 5070 PCIe issue |

## Repository Structure

```
frankocluster/
├── apps/
│   ├── root/               # App-of-Apps Helm chart (ArgoCD entry point)
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/      # One Application per infrastructure component
│   ├── argocd/values.yaml  # ArgoCD Helm values
│   ├── cilium/values.yaml
│   ├── longhorn/
│   │   ├── values.yaml
│   │   └── manifests/      # Extra manifests (GPU-local StorageClass)
│   └── gpu-operator/values.yaml
├── patches/
│   ├── README.md           # Node reference + phase status
│   ├── phase1-node-config/ # Omni machine config patches
│   ├── phase2-cilium/      # Cilium install reference
│   ├── phase3-longhorn/    # Longhorn install reference
│   └── phase4-gpu/         # GPU stack reference
├── docs/plans/             # Architecture and implementation plans
├── omni/                   # Omni-specific configs
└── scripts/                # Utility scripts
```

## Environment Setup

```bash
source .env          # Sets KUBECONFIG + TALOSCONFIG
source .env_devops   # Sets OMNI_ENDPOINT + OMNI_SERVICE_ACCOUNT_KEY
```

## ArgoCD Access

```bash
# Port-forward (no ingress configured yet)
kubectl port-forward svc/argocd-server -n argocd 8080:443

# CLI login
argocd login localhost:8080 \
  --port-forward \
  --port-forward-namespace argocd \
  --username admin

# List all apps
argocd app list --port-forward --port-forward-namespace argocd
```

## Current Status

```bash
# All apps: root, cilium, longhorn, longhorn-extras = Synced/Healthy
# gpu-operator = OutOfSync/Missing (GPU PCIe hardware issue — manual sync when fixed)
argocd app list --port-forward --port-forward-namespace argocd
```

## Adding a New Application

1. Add Helm values to `apps/<name>/values.yaml`
2. Add an Application template to `apps/root/templates/<name>.yaml`
3. Commit and push — ArgoCD auto-syncs the root app and creates the child Application

## GPU Operator (Pending)

The RTX 5070 is not detected on the PCIe bus. When the hardware issue is resolved:

```bash
# Verify GPU detected
source .env
talosctl -n 192.168.55.31 dmesg | grep -i nvidia | head -5

# Sync the GPU Operator
argocd app sync gpu-operator --port-forward --port-forward-namespace argocd

# Then enable automated sync in apps/root/templates/gpu-operator.yaml
```

## References

- [Talos Linux Docs](https://www.talos.dev/)
- [Sidero Omni Docs](https://omni.siderolabs.com/)
- [ArgoCD Docs](https://argo-cd.readthedocs.io/)
- [Longhorn Docs](https://longhorn.io/docs/)
- [Cilium Docs](https://docs.cilium.io/)
