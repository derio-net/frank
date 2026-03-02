# Phase 1: Node Labels & Control Plane Scheduling

**Tool:** `omnictl apply -f`
**Status:** DONE (applied 2026-03-02)

## What This Does

1. Removes the `NoSchedule` taint from control plane nodes so workloads can run on mini-{1,2,3}
2. Applies zone/tier/accelerator labels to all 7 nodes

## Files

| File | Target | Omni Patch ID |
| ---- | ------ | ------------- |
| `01-cluster-wide-scheduling.yaml` | cluster-wide | `100-cluster-allow-cp-scheduling` |
| `03-labels-mini-1.yaml` | mini-1 | `200-labels-mini-1` |
| `03-labels-mini-2.yaml` | mini-2 | `200-labels-mini-2` |
| `03-labels-mini-3.yaml` | mini-3 | `200-labels-mini-3` |
| `03-labels-gpu-1.yaml` | gpu-1 | `200-labels-gpu-1` |
| `03-labels-pc-1.yaml` | pc-1 | `200-labels-pc-1` |
| `03-labels-raspi-1.yaml` | raspi-1 | `200-labels-raspi-1` |
| `03-labels-raspi-2.yaml` | raspi-2 | `200-labels-raspi-2` |

## Apply

```bash
source .env_devops
omnictl apply -f patches/phase1-node-config/01-cluster-wide-scheduling.yaml
for f in patches/phase1-node-config/03-labels-*.yaml; do omnictl apply -f "$f"; done
```

## Verify

```bash
source .env

# Control plane taints removed
kubectl describe node mini-1 | grep -A 2 "Taints:"
# Expected: Taints: <none>

# Labels applied
kubectl get nodes -L zone,tier,accelerator,igpu,model-server
```

Expected output:

```
NAME      ROLES           zone         tier        accelerator   igpu          model-server
gpu-1     <none>          ai-compute   standard    nvidia                      true
mini-1    control-plane   core         standard    amd-igpu      radeon-780m
mini-2    control-plane   core         standard    amd-igpu      radeon-780m
mini-3    control-plane   core         standard    amd-igpu      radeon-780m
pc-1      <none>          edge         standard
raspi-1   <none>          edge         low-power
raspi-2   <none>          edge         low-power
```

## Rollback

```bash
source .env_devops
omnictl delete configpatch 100-cluster-allow-cp-scheduling
omnictl delete configpatch 200-labels-mini-1
omnictl delete configpatch 200-labels-mini-2
omnictl delete configpatch 200-labels-mini-3
omnictl delete configpatch 200-labels-gpu-1
omnictl delete configpatch 200-labels-pc-1
omnictl delete configpatch 200-labels-raspi-1
omnictl delete configpatch 200-labels-raspi-2
```
