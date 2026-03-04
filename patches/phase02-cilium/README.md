# Phase 2: CNI Migration (Flannel -> Cilium)

**Tools:** `omnictl apply -f` + `helm` + `kubectl`
**Status:** DONE (applied 2026-03-02)

## What This Does

1. Disables Talos's default Flannel CNI and kube-proxy via Omni config patch
2. Removes the Flannel and kube-proxy DaemonSets
3. Installs Cilium v1.17.0 as the sole CNI with eBPF kube-proxy replacement and Hubble observability

**CAUTION:** Steps 1-3 cause a brief network outage (~5 min) while Cilium images pull across all nodes.

## Files

| File | Tool | Purpose |
| ---- | ---- | ------- |
| `02-cluster-wide-cni-none.yaml` | omnictl | Omni config patch: disables Flannel CNI + kube-proxy in Talos |
| `cilium-values.yaml` | helm | Cilium Helm chart values (Talos-specific settings) |

## Apply

### Step 1: Disable default CNI in Talos config

```bash
source .env_devops
omnictl apply -f patches/phase2-cilium/02-cluster-wide-cni-none.yaml
```

### Step 2: Remove Flannel and kube-proxy

```bash
source .env
kubectl delete daemonset kube-flannel -n kube-system --ignore-not-found
kubectl delete daemonset kube-proxy -n kube-system --ignore-not-found
```

### Step 3: Install Cilium via Helm

```bash
helm repo add cilium https://helm.cilium.io/
helm repo update

helm install cilium cilium/cilium --version 1.17.0 \
  --namespace kube-system \
  -f patches/phase2-cilium/cilium-values.yaml
```

## Verify

```bash
source .env
cilium status --wait
kubectl get nodes
# All nodes should be Ready

# Optional: full connectivity test (~10 min)
cilium connectivity test
```

## Rollback

```bash
# Remove Cilium
source .env
helm uninstall cilium -n kube-system

# Re-enable Flannel (Talos will redeploy it automatically)
source .env_devops
omnictl delete configpatch 100-cluster-cni-none
```
