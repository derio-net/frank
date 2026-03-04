# Phase 4: Nvidia GPU Stack

**Tools:** `omnictl apply -f` + `helm` + `kubectl` + `talosctl`
**Status:** TODO

## What This Does

1. Adds Nvidia Talos extensions to gpu-1's image schematic (via omnictl)
2. Loads Nvidia kernel modules on gpu-1 (via Omni config patch)
3. Installs the Nvidia GPU Operator to expose the RTX 5070 to Kubernetes

## Prerequisites

- Phase 1 complete (gpu-1 has `accelerator=nvidia` label)
- Phase 3 complete (Longhorn available for GPU Operator state)

## Files

| File | Tool | Purpose |
| ---- | ---- | ------- |
| `402-gpu1-nvidia-extensions.yaml` | omnictl | Adds nvidia extensions to gpu-1 (includes iscsi-tools — see note below) |
| `04-gpu-nvidia-modules.yaml` | omnictl | Loads nvidia kernel modules on gpu-1 |
| `gpu-operator-values.yaml` | helm | GPU Operator Helm values (driver/toolkit disabled — Talos provides them) |

## Apply

### Step 1: Add Nvidia extensions to gpu-1 (triggers reboot)

**NOTE:** Per-machine `ExtensionsConfiguration` **overrides** (not merges with) cluster-wide
configs. The file includes `iscsi-tools` alongside the nvidia extensions to avoid
dropping it from gpu-1.

```bash
source .env_devops
omnictl apply -f patches/phase4-gpu/402-gpu1-nvidia-extensions.yaml
```

Wait for gpu-1 to come back Ready:

```bash
source .env
kubectl get node gpu-1 -w
# Wait until Ready
```

### Step 2: Apply kernel module patch

```bash
source .env_devops
omnictl apply -f patches/phase4-gpu/04-gpu-nvidia-modules.yaml
```

### Step 3: Verify Nvidia extensions loaded

```bash
source .env
talosctl -n 192.168.55.31 get extensions
# Expected: iscsi-tools, nvidia-container-toolkit, nvidia-open-gpu-kernel-modules

talosctl -n 192.168.55.31 dmesg | grep -i nvidia | head -10
# Expected: nvidia module loaded messages
```

### Step 4: Label gpu-operator namespace for privileged PSS

```bash
source .env
kubectl create namespace gpu-operator
kubectl label namespace gpu-operator \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/enforce-version=latest \
  pod-security.kubernetes.io/audit=privileged \
  pod-security.kubernetes.io/warn=privileged
```

### Step 5: Install Nvidia GPU Operator via Helm

```bash
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
helm repo update

source .env
helm install gpu-operator nvidia/gpu-operator --version v25.10.1 \
  --namespace gpu-operator \
  -f patches/phase4-gpu/gpu-operator-values.yaml
```

### Step 6: Verify GPU is available

```bash
source .env
kubectl get pods -n gpu-operator
kubectl get runtimeclass
kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
# Expected: 1
```

### Step 7: Run nvidia-smi test

```bash
source .env
kubectl run nvidia-test --rm -it --restart=Never \
  --image=nvcr.io/nvidia/cuda:12.8.0-base-ubuntu24.04 \
  --overrides='{"spec":{"runtimeClassName":"nvidia","tolerations":[{"key":"nvidia.com/gpu","operator":"Exists","effect":"NoSchedule"}],"nodeSelector":{"accelerator":"nvidia"}}}' \
  -- nvidia-smi
```

## Rollback

```bash
# Remove GPU Operator
source .env
helm uninstall gpu-operator -n gpu-operator
kubectl delete ns gpu-operator

# Remove kernel module patch
source .env_devops
omnictl delete configpatch 300-gpu-nvidia-modules

# Remove Nvidia extensions
source .env_devops
omnictl delete extensionsconfiguration 402-gpu1-nvidia-extensions
```
