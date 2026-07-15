---
title: "Operating on GPU Compute"
series: ["operating"]
layer: gpu
date: 2026-03-13
draft: false
tags: ["operations", "gpu", "nvidia", "intel", "talos", "troubleshooting"]
summary: "Day-to-day commands for managing NVIDIA and Intel GPUs, checking utilization, and debugging GPU container issues on Talos."
weight: 5
reader_goal: "Check GPU health, manage GPU workloads, and debug common failures (GPU not allocating, containerd config corruption, stale allocations, reboot loops) on both NVIDIA and Intel GPU stacks on Talos."
diataxis: [how-to, reference]
last_updated: 2026-07-15
last_updated_commit: https://github.com/derio-net/frank/commit/a8bed9a1d358b7ad87bb6dcaa9b0162e5fb0e127
---

{{< last-updated >}}

The cluster has two GPU paths: an NVIDIA RTX 5070 Ti on `gpu-1` managed by the GPU Operator, and Intel Arc iGPUs on the three mini nodes exposed through DRA (Dynamic Resource Allocation). Both have Talos-specific quirks, and both need different tools to inspect and troubleshoot.

This post covers day-to-day commands for checking GPU state, managing workloads, and debugging the issues you will eventually hit. For the build story, see [GPU Compute — NVIDIA and Intel]({{< relref "/docs/building/04-gpu-compute" >}}) and [GPU Containers on Talos — The Validation Fix]({{< relref "/docs/building/12-gpu-talos-fix" >}}).

Source your environment before running commands:

```bash
source .env   # sets KUBECONFIG
```

## Overview

Frank runs two GPU stacks side by side:

- **NVIDIA (gpu-1):** GPU Operator managing the RTX 5070 Ti. Deployment is via `gpu-operator` Helm chart with Talos-specific extensions and containerd runtime config.
- **Intel (mini-1/2/3):** Intel Resource Drivers for Kubernetes using DRA. One DaemonSet per node, no special containerd config needed.

### Verify

```bash
# NVIDIA — device plugin registered
kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
# Should return: 1

# Intel — ResourceSlices published
kubectl get resourceslice -o wide
# Should show three slices, one per mini node
```

## Observing State

### NVIDIA GPU (gpu-1)

The GPU Operator runs several pods on `gpu-1`. Check they are all healthy:

```bash
kubectl get pods -n gpu-operator -o wide
```

You should see pods for the device plugin, feature discovery, DCGM exporter, and validation markers DaemonSet — all `Running` and `1/1`.

To run `nvidia-smi`, exec into the DCGM exporter pod:

```bash
POD=$(kubectl get pod -n gpu-operator -l app=nvidia-dcgm-exporter \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n gpu-operator "$POD" -- nvidia-smi
```

```console
$ POD=$(kubectl get pod -n gpu-operator -l app=nvidia-dcgm-exporter -o jsonpath='{.items[0].metadata.name}'); kubectl exec -n gpu-operator "$POD" -- nvidia-smi
Mon Apr 20 16:55:31 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 570.211.01             Driver Version: 570.211.01     CUDA Version: 12.8     |
|-----------------------------------------+------------------------+----------------------+
|   0  NVIDIA GeForce RTX 5070 Ti     Off |   00000000:01:00.0 Off |                  N/A |
|  0%   33C    P8             19W /  300W |    7956MiB /  16303MiB |      0%      Default |
+-----------------------------------------------------------------------------------------+
```

For a quick view of allocatable resources:

```bash
kubectl describe node gpu-1 | grep -A 10 "Allocated resources"
```

### Intel iGPU (mini nodes)

The Intel DRA driver runs as a DaemonSet:

```bash
kubectl get pods -n intel-gpu-resource-driver -o wide
```

Check that ResourceSlices are published:

```bash
kubectl get resourceslice -o wide
```

```console
$ kubectl get resourceslice -o wide
NAME                         NODE     DRIVER          POOL     AGE
mini-1-gpu.intel.com-wnt98   mini-1   gpu.intel.com   mini-1   28d
mini-2-gpu.intel.com-ssz5r   mini-2   gpu.intel.com   mini-2   28d
mini-3-gpu.intel.com-ch2jg   mini-3   gpu.intel.com   mini-3   28d
```

To see active ResourceClaims (pods currently using an Intel GPU):

```bash
kubectl get resourceclaim -A
```

## Routine Operations

### Check GPU Utilization

```bash
# GPU utilization, memory, running processes
kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- nvidia-smi

# Ollama model status
kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- ollama ps
```

The `ollama ps` output shows model name, size, processor allocation (look for `100% GPU`), and context window.

### Check Which Pods Use the GPU

```bash
# NVIDIA — pods requesting nvidia.com/gpu
kubectl get pods -A -o json | jq -r '
  .items[] | select(.spec.containers[].resources.limits."nvidia.com/gpu" != null)
  | "\(.metadata.namespace)/\(.metadata.name)"'

# Intel DRA — pods with ResourceClaims
kubectl get pods -A -o json | jq -r '
  .items[] | select(.spec.resourceClaims != null)
  | "\(.metadata.namespace)/\(.metadata.name)"'
```

### Pull Models via kubectl exec

PostStart lifecycle hooks fail on Talos with NVIDIA due to the `nvidia-container-cli` exec hook. Models must be pulled manually:

```bash
kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- ollama pull qwen3.5:9b

kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- ollama pull deepseek-coder:6.7b
```

Models persist on the Longhorn PVC — one-time operation unless the PVC is lost.

### Manage GPU Memory

```bash
# List loaded models
kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- ollama ps

# Unload — delete the pod; Deployment recreates it
kubectl delete pod -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}')
```

Models on the PVC remain available and load back into VRAM on the next request.

## Runbook

### GPU Not Allocating

If a pod requesting `nvidia.com/gpu` stays `Pending`:

1. **Check device plugin registration:**
   ```bash
   kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
   ```
   Should return `1`. If empty or `0`, the device plugin is not running.

2. **Check GPU Operator pods:**
   ```bash
   kubectl get pods -n gpu-operator -o wide
   ```
   All should be `Running`. Look for `Init:0/1` or `CrashLoopBackOff`.

3. **Check validation markers:**
   ```bash
   kubectl exec -n gpu-operator $(kubectl get pod -n gpu-operator \
     -l app=nvidia-validation-markers -o jsonpath='{.items[0].metadata.name}') \
     -- ls -la /run/nvidia/validations/
   ```
   Should show `driver-ready` and `toolkit-ready` files. If missing, the node may have rebooted (files are on tmpfs). The DaemonSet recreates them within 30 seconds.

#### Recovery: containerd config corruption

If GPU pods are stuck at `ContainerCreating` with `PodReadyToStartContainers: False`:

```bash
talosctl -n 192.168.55.31 read /etc/cri/conf.d/20-customization.part
```

The file should contain:

```toml
[plugins."io.containerd.cri.v1.runtime"]
  cdi_spec_dirs = ["/var/cdi/static", "/var/cdi/dynamic"]
  [plugins."io.containerd.cri.v1.runtime".containerd]
    default_runtime_name = "nvidia"
  [plugins."io.containerd.cri.v1.runtime".containerd.runtimes.nvidia]
    base_runtime_spec = "/etc/cri/conf.d/base-spec.json"
```

If `base_runtime_spec` is missing, kubelet cannot track the GPU container lifecycle. See the [Talos validation fix]({{< relref "/docs/building/12-gpu-talos-fix" >}}) for the full story.

### Talos Reboot Loops from Conflicting Patches

If a node enters a ~35-minute reboot loop after applying a config patch, the cause is two patches creating the same file at `/etc/cri/conf.d/20-customization.part`:

```
resource EtcFileSpecs.files.talos.dev(files/cri/conf.d/20-customization.part@undefined) already exists
```

Recovery:

```bash
omnictl delete configpatch <cluster-wide-patch-id>
kubectl get node <node-name> -w
```

Each node must have its own machine-specific patch. Delete the cluster-wide patch before applying machine-specific ones.

### Stale GPU Allocations from Force-Delete

Force-deleting a GPU pod (`kubectl delete pod --force --grace-period=0`) leaves stale containers holding the GPU allocation. The device plugin still sees the GPU as allocated, and new GPU pods stay `Pending` with `Insufficient nvidia.com/gpu`.

Recovery:

```bash
# Check if GPU is stuck allocated
kubectl describe node gpu-1 | grep -A 5 "Allocated resources"

# Clean reboot clears it
talosctl -n 192.168.55.31 reboot
```

A clean reboot is the only reliable way to clear stale GPU allocations. Budget about 90 seconds for Talos to come back `Ready`. Avoid force-deleting GPU pods — scale the workload to 0 instead.

## Missteps

| What we assumed | Why it was wrong | What it cost |
|-----------------|------------------|-------------|
| PostStart lifecycle hooks work on Talos with NVIDIA | The `nvidia-container-cli` exec hook conflicts with Talos's containerd config — the hook runs before the container runtime is fully initialized | All model pulls must happen manually via `kubectl exec` after the pod is running. |
| A single cluster-wide containerd patch works for all nodes | GPU-1 needs a different `20-customization.part` than non-GPU nodes. Two patches creating the same file throw `EtcFileSpecs` conflict | ~35-minute reboot loop on gpu-1 until the cluster-wide patch was deleted. |
| `kubectl delete pod --force` is safe for GPU workloads | Stale containerd containers hold the GPU allocation — the device plugin never releases it | GPU appears allocated but unusable until a clean node reboot. |
| Validation markers persist across reboots | Files live on tmpfs — a node reboot wipes them | DaemonSet recreates them within 30 seconds, but operators panic when they disappear. |

## Quick Reference

| Task | Command |
|------|---------|
| GPU Operator health | `kubectl get pods -n gpu-operator -o wide` |
| nvidia-smi | `kubectl exec -n gpu-operator $(kubectl get pod -n gpu-operator -l app=nvidia-dcgm-exporter -o jsonpath='{.items[0].metadata.name}') -- nvidia-smi` |
| Ollama model status | `kubectl exec -n ollama $(kubectl get pod -n ollama -o jsonpath='{.items[0].metadata.name}') -- ollama ps` |
| Pull a model | `kubectl exec -n ollama $(kubectl get pod -n ollama -o jsonpath='{.items[0].metadata.name}') -- ollama pull <model>` |
| Node GPU capacity | `kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'` |
| Intel DRA pods | `kubectl get pods -n intel-gpu-resource-driver -o wide` |
| Intel ResourceSlices | `kubectl get resourceslice -o wide` |
| Active ResourceClaims | `kubectl get resourceclaim -A` |
| Validation markers | `kubectl exec -n gpu-operator $(kubectl get pod -n gpu-operator -l app=nvidia-validation-markers -o jsonpath='{.items[0].metadata.name}') -- ls /run/nvidia/validations/` |
| Containerd config | `talosctl -n 192.168.55.31 read /etc/cri/conf.d/20-customization.part` |
| Reboot gpu-1 | `talosctl -n 192.168.55.31 reboot` |
| Find GPU-using pods (NVIDIA) | `kubectl get pods -A -o json \| jq -r '.items[] \| select(.spec.containers[].resources.limits."nvidia.com/gpu" != null) \| "\(.metadata.namespace)/\(.metadata.name)"'` |

## Explanation

This post covers both GPU paths on Frank because they fail differently. The NVIDIA stack has Talos-specific containerd quirks (missing `base_runtime_spec`, postStart hook conflicts, stale allocations from force-delete). The Intel DRA stack is simpler — it Just Works — but requires understanding the ResourceSlice/ResourceClaim model. The building posts cover why each stack was chosen and how it was deployed; this post covers what to do when they break.

## References

- [NVIDIA GPU Operator docs](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/) — Official GPU Operator documentation
- [Intel Resource Drivers for Kubernetes](https://github.com/intel/intel-resource-drivers-for-kubernetes) — DRA-based driver for Intel GPUs
- [Talos NVIDIA GPU guide](https://docs.siderolabs.com/talos/v1.9/configure-your-talos-cluster/hardware-and-drivers/nvidia-gpu-proprietary) — Extensions and kernel modules for NVIDIA on Talos
- [Kubernetes DRA](https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/) — Dynamic Resource Allocation documentation
- [GPU Compute — NVIDIA and Intel]({{< relref "/docs/building/04-gpu-compute" >}}) — Building post: deploying both GPU stacks
- [GPU Containers on Talos — The Validation Fix]({{< relref "/docs/building/12-gpu-talos-fix" >}}) — Building post: debugging containerd and validation issues
