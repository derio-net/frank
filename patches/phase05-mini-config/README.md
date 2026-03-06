# Phase 5: Intel iGPU (Arc) Stack for mini-{1..3}

**Tools:** `omnictl apply -f` + ArgoCD
**Status:** DONE (applied 2026-03-04)

## What This Does

1. Fixes mini node labels (`accelerator: intel-igpu`, `igpu: intel-arc`)
2. Adds Intel Arc iGPU Talos extensions (`i915` + `intel-ucode`) to mini-{1..3} image schematics via Omni (triggers rolling reboot, one node at a time)
3. Enables CDI device discovery in containerd (cluster-wide config patch, no reboot)
4. Deploys the Intel GPU Device Plugin via ArgoCD to expose `gpu.intel.com/i915` as a schedulable resource

## Prerequisites

- Phase 1 complete (mini nodes labeled — note: labels must be updated from `amd-igpu` to `intel-igpu`)
- Phase 2 complete (Cilium CNI running)

## Files

| File | Tool | Purpose |
|------|------|---------|
| `500-mini1-i915-extensions.yaml` | omnictl | Adds i915+intel-ucode to mini-1 (triggers reboot) |
| `501-mini2-i915-extensions.yaml` | omnictl | Adds i915+intel-ucode to mini-2 (triggers reboot) |
| `502-mini3-i915-extensions.yaml` | omnictl | Adds i915+intel-ucode to mini-3 (triggers reboot) |
| `05-mini-cdi-containerd.yaml` | omnictl | Enables CDI in containerd cluster-wide (no reboot) |

ArgoCD Application + values: `apps/intel-gpu-plugin/`

## Apply Order

Apply extensions one node at a time to preserve control-plane quorum (all mini nodes are control-plane):

```bash
source .env_devops

# 1. Fix labels (no reboot)
omnictl apply -f patches/phase01-node-config/03-labels-mini-1.yaml
omnictl apply -f patches/phase01-node-config/03-labels-mini-2.yaml
omnictl apply -f patches/phase01-node-config/03-labels-mini-3.yaml

# 2. Extensions — one at a time, wait for Ready between each
omnictl apply -f patches/phase05-mini-config/500-mini1-i915-extensions.yaml
# kubectl get node mini-1 -w  →  wait until Ready

omnictl apply -f patches/phase05-mini-config/501-mini2-i915-extensions.yaml
# kubectl get node mini-2 -w  →  wait until Ready

omnictl apply -f patches/phase05-mini-config/502-mini3-i915-extensions.yaml
# kubectl get node mini-3 -w  →  wait until Ready

# 3. CDI containerd patch (cluster-wide, containerd restarts, no reboot)
omnictl apply -f patches/phase05-mini-config/05-mini-cdi-containerd.yaml
```

Then push to git and sync ArgoCD:

```bash
git push
source .env
argocd app sync root
argocd app sync intel-gpu-driver
```

## Verify

```bash
source .env
# Extensions
talosctl -n 192.168.55.21 get extensions  # i915, intel-ucode, iscsi-tools
talosctl -n 192.168.55.21 ls /dev/dri     # card0, renderD128

# DRA: driver pods and ResourceSlices (not node.status.allocatable — that's device plugin)
kubectl get pods -n intel-gpu-resource-driver -o wide
kubectl get resourceslice -o wide
kubectl get deviceclass
```

## Rollback

```bash
# Remove Intel GPU Resource Driver (DRA)
source .env
argocd app delete intel-gpu-driver --cascade

# Remove CDI containerd patch
source .env_devops
omnictl delete configpatch 303-cluster-cdi-containerd

# Remove i915 extensions (triggers reboots)
omnictl delete extensionsconfiguration 500-mini1-i915-extensions
omnictl delete extensionsconfiguration 501-mini2-i915-extensions
omnictl delete extensionsconfiguration 502-mini3-i915-extensions
```
