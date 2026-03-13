---
title: "Operating on GPU Compute"
date: 2026-03-13
draft: false
tags: ["operations", "gpu", "nvidia", "intel", "talos"]
summary: "Day-to-day commands for managing NVIDIA and Intel GPUs, checking utilization, and debugging GPU container issues on Talos."
weight: 104
cover:
  image: cover.png
  alt: "Frank performing surgery on his GPU arm with precision robotic tools"
  relative: true
---

The cluster has two GPU paths: an NVIDIA RTX 5070 Ti on `gpu-1` managed by the GPU Operator, and Intel Arc iGPUs on the three mini nodes exposed through DRA (Dynamic Resource Allocation). Both are operational, both have Talos-specific quirks, and both need different tools to inspect and troubleshoot.

This post covers the day-to-day commands for checking GPU state, managing workloads, and debugging the issues you will eventually hit. For the build story, see [GPU Compute — NVIDIA and Intel]({{< relref "/building/04-gpu-compute" >}}) and [GPU Containers on Talos — The Validation Fix]({{< relref "/building/12-gpu-talos-fix" >}}).

## Observing State

### NVIDIA GPU (gpu-1)

The GPU Operator runs several pods on `gpu-1`. Check that they are all healthy:

```bash
kubectl get pods -n gpu-operator -o wide
```

You should see pods for the device plugin, feature discovery, DCGM exporter, and the validation markers DaemonSet — all `Running` and `1/1`. If any pod is stuck at `Init:0/1`, the validation markers are likely missing (see [Debugging](#debugging) below).

To run `nvidia-smi`, exec into the DCGM exporter pod (it has the nvidia tools available):

```bash
kubectl exec -n gpu-operator $(kubectl get pod -n gpu-operator \
  -l app=nvidia-dcgm-exporter -o jsonpath='{.items[0].metadata.name}') \
  -- nvidia-smi
```

For a quick check of what the node reports as allocatable:

```bash
kubectl describe node gpu-1 | grep -A 10 "Allocated resources"
```

Look for `nvidia.com/gpu` in the capacity and allocatable fields:

```bash
kubectl get node gpu-1 -o jsonpath='{.status.capacity.nvidia\.com/gpu}'
# Should return: 1
```

### Intel iGPU (mini nodes)

The Intel DRA driver runs as a DaemonSet — one pod per mini node:

```bash
kubectl get pods -n intel-gpu-resource-driver -o wide
```

Check that ResourceSlices are published for each node:

```bash
kubectl get resourceslice -o wide
```

You should see three slices, one per mini node, all with driver `gpu.intel.com`. The DeviceClass should also exist:

```bash
kubectl get deviceclass gpu.intel.com
```

To see active ResourceClaims (pods currently using an Intel GPU):

```bash
kubectl get resourceclaim -A
```

## Routine Operations

### Check GPU Utilization

For NVIDIA, the quickest way to see what is running on the GPU:

```bash
# GPU utilization, memory usage, running processes
kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- nvidia-smi

# Or just check Ollama's model status
kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- ollama ps
```

The `ollama ps` output tells you the model name, size, processor allocation (look for `100% GPU`), and context window size.

### Check Which Pods Use the GPU

```bash
# NVIDIA — find pods requesting nvidia.com/gpu
kubectl get pods -A -o json | jq -r '
  .items[] | select(.spec.containers[].resources.limits."nvidia.com/gpu" != null)
  | "\(.metadata.namespace)/\(.metadata.name)"'

# Intel DRA — find pods with ResourceClaims
kubectl get pods -A -o json | jq -r '
  .items[] | select(.spec.resourceClaims != null)
  | "\(.metadata.namespace)/\(.metadata.name)"'
```

### Pull Models via kubectl exec

On Talos with NVIDIA, postStart lifecycle hooks fail due to the nvidia-container-cli exec hook. Models must be pulled manually after the pod is running:

```bash
kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- ollama pull qwen3.5:9b

kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- ollama pull deepseek-coder:6.7b
```

Models persist on the Longhorn PVC, so this is a one-time operation unless the PVC is lost.

### Manage GPU Memory

If Ollama holds a model in VRAM that you want to unload:

```bash
# List loaded models
kubectl exec -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}') -- ollama ps

# Unload by running a different model, or restart the pod
kubectl delete pod -n ollama $(kubectl get pod -n ollama \
  -o jsonpath='{.items[0].metadata.name}')
```

The pod will be recreated by the Deployment. Models on the PVC remain available — they just need to be loaded back into VRAM on the next request.

## Debugging

### GPU Not Allocating

If a pod requesting `nvidia.com/gpu` stays `Pending`:

```bash
# 1. Check that the device plugin registered the GPU
kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
# Should return 1. If empty or 0, the device plugin is not running.

# 2. Check GPU Operator pods
kubectl get pods -n gpu-operator -o wide
# All should be Running. Look for Init:0/1 or CrashLoopBackOff.

# 3. Check validation markers
kubectl exec -n gpu-operator $(kubectl get pod -n gpu-operator \
  -l app=nvidia-validation-markers -o jsonpath='{.items[0].metadata.name}') \
  -- ls -la /run/nvidia/validations/
# Should show driver-ready and toolkit-ready files
```

If the markers are missing, check that the `nvidia-validation-markers` DaemonSet is running. If it is running but the files are gone, the node may have rebooted (files are on tmpfs). The DaemonSet loop recreates them within 30 seconds.

### Containerd Issues on Talos

If GPU pods are stuck at `ContainerCreating` with `PodReadyToStartContainers: False`:

```bash
# Check containerd runtime config on gpu-1
talosctl -n 192.168.55.31 read /etc/cri/conf.d/20-customization.part
```

The file should contain the nvidia runtime as default **and** the `base_runtime_spec`:

```toml
[plugins."io.containerd.cri.v1.runtime"]
  cdi_spec_dirs = ["/var/cdi/static", "/var/cdi/dynamic"]
  [plugins."io.containerd.cri.v1.runtime".containerd]
    default_runtime_name = "nvidia"
  [plugins."io.containerd.cri.v1.runtime".containerd.runtimes.nvidia]
    base_runtime_spec = "/etc/cri/conf.d/base-spec.json"
```

If `base_runtime_spec` is missing, kubelet cannot track the GPU container lifecycle. See the [Talos validation fix]({{< relref "/building/12-gpu-talos-fix" >}}) for the full story.

### Talos Reboot Loops from Conflicting Patches

If a node enters a ~35-minute reboot loop after applying a config patch, the likely cause is two patches creating the same file at `/etc/cri/conf.d/20-customization.part`. Talos cannot merge them and throws:

```
resource EtcFileSpecs.files.talos.dev(files/cri/conf.d/20-customization.part@undefined) already exists
```

The fix: each node must have its own machine-specific patch. Delete the cluster-wide patch **before** applying machine-specific ones. To recover a looping node:

```bash
# Remove the conflicting cluster-wide patch from Omni
omnictl delete configpatch <cluster-wide-patch-id>

# Watch the node recover (it will complete its current reboot cycle)
kubectl get node <node-name> -w
```

### Force-Delete GPU Pods Carefully

Force-deleting a GPU pod (`kubectl delete pod --force --grace-period=0`) leaves stale containers holding the GPU allocation inside containerd. The device plugin still sees the GPU as allocated. New GPU pods will stay `Pending` with `Insufficient nvidia.com/gpu`.

If you must force-delete:

```bash
# Force delete (last resort)
kubectl delete pod -n <namespace> <pod> --force --grace-period=0

# Check if the GPU is still shown as allocated
kubectl describe node gpu-1 | grep -A 5 "Allocated resources"

# If GPU is still stuck as allocated, a clean node reboot clears it
talosctl -n 192.168.55.31 reboot
```

A clean reboot is the only reliable way to clear stale GPU allocations from containerd. Budget about 90 seconds for Talos to come back Ready.

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

## References

- [NVIDIA GPU Operator docs](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/) — Official GPU Operator documentation
- [Intel Resource Drivers for Kubernetes](https://github.com/intel/intel-resource-drivers-for-kubernetes) — DRA-based driver for Intel GPUs
- [Talos NVIDIA GPU guide](https://docs.siderolabs.com/talos/v1.9/configure-your-talos-cluster/hardware-and-drivers/nvidia-gpu-proprietary) — Extensions and kernel modules for NVIDIA on Talos
- [Kubernetes DRA](https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/) — Dynamic Resource Allocation documentation
- [GPU Compute — NVIDIA and Intel]({{< relref "/building/04-gpu-compute" >}}) — Building post: deploying both GPU stacks
- [GPU Containers on Talos — The Validation Fix]({{< relref "/building/12-gpu-talos-fix" >}}) — Building post: debugging containerd and validation issues
