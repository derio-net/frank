---
title: "GPU Compute — NVIDIA and Intel"
date: 2026-03-06
draft: false
tags: ["gpu", "nvidia", "intel", "dra"]
summary: "Adding GPU compute to the cluster — the NVIDIA RTX 5070 saga, Intel Arc iGPU via DRA, and patching charts for bleeding-edge Kubernetes."
weight: 5
cover:
  image: cover.png
  alt: "Frank the cluster monster with a massive GPU arm and a smaller Intel iGPU arm"
  relative: true
---

This post covers two GPU stories with very different endings. The NVIDIA RTX 5070 in `gpu-1` should have been the crown jewel of the cluster, but a hardware issue turned it into a cautionary tale. Meanwhile, the Intel Arc iGPUs hiding inside the three mini nodes became fully operational through Kubernetes 1.35's Dynamic Resource Allocation — the new standard for GPU scheduling that replaces device plugins.

Both paths required Talos extensions, kernel-level config, and some chart surgery. Let's walk through them.

## Part 1: NVIDIA GPU Operator (Phase 4)

The plan for `gpu-1` was straightforward: install NVIDIA's Talos extensions, load the kernel modules, deploy the GPU Operator via Helm, and start scheduling CUDA workloads. The infrastructure side worked. The hardware had other ideas.

### Talos Extensions for NVIDIA

Talos Linux uses a read-only, immutable root filesystem. You cannot `apt install` or `modprobe` anything at runtime. Instead, you bake system extensions into the node's image schematic. For NVIDIA, two extensions are required:

- `nvidia-container-toolkit-production` — the container runtime hooks that let containers access the GPU
- `nvidia-open-gpu-kernel-modules-production` — the open-source NVIDIA kernel driver

On Sidero Omni, you declare extensions per machine using `ExtensionsConfigurations`:

```yaml
# patches/phase04-gpu/402-gpu1-nvidia-extensions.yaml
metadata:
    type: ExtensionsConfigurations.omni.sidero.dev
    id: 402-gpu1-nvidia-extensions
    labels:
        omni.sidero.dev/cluster: frank
        omni.sidero.dev/cluster-machine: 03ff0210-...
spec:
    extensions:
        - siderolabs/iscsi-tools
        - siderolabs/nvidia-container-toolkit-production
        - siderolabs/nvidia-open-gpu-kernel-modules-production
```

A critical gotcha here: per-machine `ExtensionsConfiguration` resources in Omni **override** the cluster-wide config entirely — they do not merge. If the cluster already has `iscsi-tools` (needed for Longhorn), you must re-include it in the per-machine config or `gpu-1` will lose iSCSI support and Longhorn will break on that node.

Applying the extension triggers an image rebuild and a reboot. Once the node comes back, the second patch loads the kernel modules:

```yaml
# patches/phase04-gpu/04-gpu-nvidia-modules.yaml (abbreviated)
spec:
    data: |
        machine:
            kernel:
                modules:
                    - name: nvidia
                    - name: nvidia_uvm
                    - name: nvidia_modeset
                    - name: nvidia_drm
```

The ordering matters: extensions must be in the image schematic *before* you try to load the modules. Apply the extension config first, wait for the node to come back Ready, then apply the module patch.

### GPU Operator Helm Values

With the driver and toolkit baked into Talos itself, the NVIDIA GPU Operator's job shrinks considerably. Most of its default components would try to install things that Talos already provides (and cannot modify anyway). The values file is deliberately minimal:

```yaml
# apps/gpu-operator/values.yaml
driver:
  enabled: false

toolkit:
  enabled: false

operator:
  defaultRuntime: containerd
```

`driver.enabled: false` because Talos provides the kernel modules. `toolkit.enabled: false` because Talos provides the container toolkit. The operator still handles device discovery, the device plugin, GPU feature discovery, and the DCGM exporter — all the Kubernetes-level plumbing.

The ArgoCD Application for the GPU Operator uses NVIDIA's official Helm chart at `v25.10.1`:

```yaml
# apps/root/templates/gpu-operator.yaml (abbreviated)
spec:
  sources:
    - repoURL: https://helm.ngc.nvidia.com/nvidia
      chart: gpu-operator
      targetRevision: "v25.10.1"
      helm:
        valueFiles:
          - $values/apps/gpu-operator/values.yaml
  syncPolicy:
    # Manual sync — GPU hardware not yet detected
```

Notice the sync policy: no `automated` block. This is intentional, and brings us to the hardware saga.

### The Hardware Saga

The RTX 5070 is physically installed in `gpu-1`. The Gigabyte Z790 Eagle AX motherboard has a PCIe 5.0 x16 slot. The card is seated, powered (dual 8-pin), and the fans spin on boot. The RGB on the case fans (controlled via a separate USB HID controller) works fine.

But `lspci` shows nothing. No NVIDIA device. No unknown PCI device. The card is invisible to the PCIe bus.

```
$ talosctl -n 192.168.55.31 dmesg | grep -i nvidia
# (silence)

$ talosctl -n 192.168.55.31 read /proc/bus/pci/devices | head
# No NVIDIA vendor ID (10de)
```

The NVIDIA kernel modules load without error — they simply find no hardware to bind to. The GPU Operator deploys, the validator pod runs, and everything reports healthy from a software perspective. There is just no GPU to operate on.

What has been tried:

- **Reseating the card** — removed and reinstalled in the x16 slot. No change.
- **BIOS settings** — confirmed PCIe is set to Auto/Gen5, CSM disabled, Above 4G Decoding enabled, Resizable BAR enabled.
- **Different BIOS versions** — the Z790 Eagle AX shipped with a BIOS from before the RTX 5070 existed. Updated to the latest available. No change.
- **Power supply** — the PSU provides adequate wattage. Rails are stable (verified with a multimeter on the PCIe power connectors).

The leading theories are a dead PCIe slot, a defective card, or an RTX 5070-specific BIOS incompatibility with this board. The RTX 50-series was brand new at the time of this build, and early BIOS support has been spotty across vendors.

The practical consequence: the `gpu-operator` ArgoCD application sits on manual sync. When the hardware issue is resolved, the fix is one command:

```bash
argocd app sync gpu-operator
```

Then update the Application template to enable automated sync. Until then, Phase 4 is infrastructure-complete but hardware-blocked.

This is the kind of thing that does not show up in architecture diagrams. You can plan every layer of the stack perfectly and still get stopped by a PCIe bus that refuses to enumerate a device. The cluster moves on — there are three other GPUs that work.

## Part 2: Intel Arc iGPU via DRA (Phase 5)

The three mini nodes (`mini-1`, `mini-2`, `mini-3`) each have an Intel Core Ultra with an integrated Intel Arc GPU. These are not powerhouse GPUs, but they handle video transcode (Quick Sync), light inference, and OpenCL workloads well. More importantly, they gave us a reason to implement DRA — the replacement for the Kubernetes device plugin model.

### Why DRA Over Device Plugins?

Kubernetes has used device plugins since v1.10 to expose hardware like GPUs. A device plugin runs on each node, advertises a resource (like `nvidia.com/gpu: 1`), and pods request it through `resources.limits`. It works, but it has real limitations:

- Devices are opaque integers in `resources.limits` — you cannot express "I want a GPU with at least 4GB VRAM" or "give me a GPU from the same NUMA node as my CPU allocation."
- Allocation is first-come-first-served with no structured claim semantics.
- There is no standard way for a device to be shared between containers in a pod, or between pods with different permission levels.

Dynamic Resource Allocation (DRA), which graduated to GA in Kubernetes 1.32 and uses `resource.k8s.io/v1`, introduces three new concepts:

**ResourceSlice** — Published by the driver on each node, a ResourceSlice advertises what devices are available. Think of it as the driver saying "this node has an Intel Arc GPU with these capabilities." Unlike device plugins, the slice can carry structured attributes (device model, memory, features) that schedulers can match against.

**DeviceClass** — A cluster-wide object that defines a class of devices. It uses CEL expressions to select which devices match. For Intel GPUs:

```yaml
apiVersion: resource.k8s.io/v1
kind: DeviceClass
metadata:
  name: gpu.intel.com
spec:
  selectors:
  - cel:
      expression: device.driver == "gpu.intel.com"
```

**ResourceClaim** — The pod-side object that requests a device. Instead of `resources.limits: gpu.intel.com/i915: 1`, a pod creates a ResourceClaim that references the DeviceClass. The scheduler finds a node whose ResourceSlice has a matching device, binds the claim, and the kubelet plugin injects the device into the container via CDI (Container Device Interface).

A smoke-test pod using DRA looks like this:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test
spec:
  containers:
  - name: test
    image: ubuntu
    command: ["ls", "-la", "/dev/dri/"]
    resources:
      claims:
      - name: gpu
  resourceClaims:
  - name: gpu
    deviceClassName: gpu.intel.com
```

No magic resource strings in `limits`. The claim is a first-class Kubernetes object with its own lifecycle, and the DeviceClass provides a layer of abstraction between "what the pod wants" and "what the node has."

### i915 Extensions on Talos

The Intel Arc iGPU needs the `i915` kernel driver and updated microcode. On Talos, these come as system extensions:

```yaml
# patches/phase05-mini-config/500-mini1-i915-extensions.yaml
metadata:
    type: ExtensionsConfigurations.omni.sidero.dev
    id: 500-mini1-i915-extensions
spec:
    extensions:
        - siderolabs/iscsi-tools
        - siderolabs/i915
        - siderolabs/intel-ucode
```

The same `iscsi-tools` gotcha from Phase 4 applies: per-machine extension configs override the cluster-wide list, so `iscsi-tools` must be re-included.

There are three separate files — one per mini node (`500-mini1`, `501-mini2`, `502-mini3`) — because all three mini nodes are control-plane members. Applying an extension triggers an image rebuild and reboot. If you apply all three simultaneously, you lose quorum and the cluster goes down.

The safe procedure is serial: apply to `mini-1`, watch it reboot and return to Ready, then apply to `mini-2`, wait again, then `mini-3`. With Talos reboots taking roughly 60-90 seconds each, the whole process takes about five minutes but the cluster never loses availability.

```bash
# One node at a time — never lose quorum
omnictl apply -f patches/phase05-mini-config/500-mini1-i915-extensions.yaml
kubectl get node mini-1 -w   # wait for Ready

omnictl apply -f patches/phase05-mini-config/501-mini2-i915-extensions.yaml
kubectl get node mini-2 -w   # wait for Ready

omnictl apply -f patches/phase05-mini-config/502-mini3-i915-extensions.yaml
kubectl get node mini-3 -w   # wait for Ready
```

After the extensions are loaded, each node exposes the GPU devices:

```
$ talosctl -n 192.168.55.21 ls /dev/dri
card0
renderD128
```

### CDI Containerd Configuration

DRA drivers inject devices into containers using the Container Device Interface (CDI). The driver writes a CDI spec file to a directory on the host, and containerd reads it when starting a container. By default, the Intel driver writes to `/etc/cdi/`.

On Talos, `/etc` is part of the read-only root filesystem. Writes to `/etc/cdi/` silently fail or error out. The fix: tell both containerd and the driver to use `/var/cdi/` instead, since `/var` is writable on Talos.

This is a cluster-wide Omni config patch (harmless on nodes without Intel GPUs):

```yaml
# patches/phase05-mini-config/05-mini-cdi-containerd.yaml
spec:
    data: |
        machine:
            files:
                - path: /etc/cri/conf.d/20-customization.part
                  op: create
                  content: |
                      [plugins."io.containerd.cri.v1.runtime"]
                        cdi_spec_dirs = ["/var/cdi/static", "/var/cdi/dynamic"]
```

Talos supports containerd config drop-ins at `/etc/cri/conf.d/`. By writing a customization part file, we override the CDI spec directories without modifying the main containerd config. Containerd restarts automatically when this file appears — no node reboot required.

### Chart Vendoring for K8s 1.35

The Intel GPU resource driver has an official Helm chart, but it was built for Kubernetes 1.32-1.34. Our cluster runs Kubernetes 1.35, which introduced a breaking change: the `resource.k8s.io/v1beta1` API was removed. The upstream chart uses `v1beta1` for its DeviceClass and references it in the ValidatingAdmissionPolicy.

Rather than maintaining a fragile set of Kustomize overlays or post-render hooks, I vendored the chart into the repo and patched it directly. The vendored chart lives at `apps/intel-gpu-driver/chart/` with version `0.7.0-k8s135` to distinguish it from upstream.

Five patches were needed:

**1. DeviceClass API version** — `resource.k8s.io/v1beta1` to `resource.k8s.io/v1`:

```yaml
# apps/intel-gpu-driver/chart/templates/device-class.yaml
apiVersion: resource.k8s.io/v1
kind: DeviceClass
metadata:
  name: gpu.intel.com
```

**2. ValidatingAdmissionPolicy** — both the policy API version and the ResourceSlice API version it watches:

```yaml
# apps/intel-gpu-driver/chart/templates/validating-admission-policy.yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
spec:
  matchConstraints:
    resourceRules:
    - apiGroups:   ["resource.k8s.io"]
      apiVersions: ["v1"]
      resources:   ["resourceslices"]
```

**3. Namespace PSA label** — the DRA driver DaemonSet uses `hostPath` volumes for `/var/lib/kubelet/plugins`, `/sys`, and the CDI directory. Kubernetes Pod Security Admission blocks this by default. The namespace needs the `privileged` enforcement level:

```yaml
# apps/intel-gpu-driver/chart/templates/resource-driver-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: intel-gpu-resource-driver
  labels:
    pod-security.kubernetes.io/enforce: privileged
```

**4. CDI hostPath** — the DaemonSet's `cdi` volume mount pointed to `/etc/cdi` on the host. Changed to `/var/cdi/dynamic` to match the containerd config patch:

```yaml
# In the DaemonSet template (resource-driver.yaml)
volumes:
- name: cdi
  hostPath:
    path: /var/cdi/dynamic    # was /etc/cdi
    type: DirectoryOrCreate
```

**5. Image update** — the upstream chart used `intel/intel-gpu-resource-driver:v0.7.0` from Docker Hub. Updated to `v0.9.1` from GitHub Container Registry, which is the version that supports `resource.k8s.io/v1`:

```yaml
# apps/intel-gpu-driver/values.yaml
image:
  repository: ghcr.io/intel/intel-resource-drivers-for-kubernetes
  name: intel-gpu-resource-driver
  tag: "v0.9.1"
```

The ArgoCD Application points directly at the vendored chart path in the Git repo:

```yaml
# apps/root/templates/intel-gpu-driver.yaml (abbreviated)
spec:
  sources:
    - repoURL: https://github.com/derio-net/frank.git
      path: apps/intel-gpu-driver/chart
      helm:
        releaseName: intel-gpu-driver
        valueFiles:
          - ../values.yaml
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
```

Because the chart is vendored, ArgoCD syncs it like any other Git-tracked resource. When Intel releases an upstream chart with `v1` support, we can re-vendor or switch back to the remote chart — but for now, this approach gives us full control and transparency over every API version in the templates.

### Verifying It Works

After ArgoCD syncs the intel-gpu-driver app, three DaemonSet pods should be running (one per mini node):

```bash
$ kubectl get pods -n intel-gpu-resource-driver -o wide
NAME                                            READY   NODE
intel-gpu-resource-driver-kubelet-plugin-xxxxx   1/1    mini-1
intel-gpu-resource-driver-kubelet-plugin-yyyyy   1/1    mini-2
intel-gpu-resource-driver-kubelet-plugin-zzzzz   1/1    mini-3
```

Each pod publishes a ResourceSlice for its node's GPU:

```bash
$ kubectl get resourceslice -o wide
NAME                       DRIVER         NODE
mini-1-gpu-intel-com-...   gpu.intel.com  mini-1
mini-2-gpu-intel-com-...   gpu.intel.com  mini-2
mini-3-gpu-intel-com-...   gpu.intel.com  mini-3
```

The DeviceClass should exist:

```bash
$ kubectl get deviceclass
NAME            AGE
gpu.intel.com   2d
```

To verify end-to-end, run a smoke-test pod that claims a GPU and lists the DRI devices:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-smoke-test
spec:
  containers:
  - name: test
    image: ubuntu:24.04
    command: ["ls", "-la", "/dev/dri/"]
    resources:
      claims:
      - name: gpu
  resourceClaims:
  - name: gpu
    deviceClassName: gpu.intel.com
  restartPolicy: Never
```

The pod gets scheduled onto one of the mini nodes, the ResourceClaim binds, and the CDI spec injects the GPU devices:

```
$ kubectl logs gpu-smoke-test
crw-rw---- 1 root video 226,   0 Mar  4 ... /dev/dri/card0
crw-rw---- 1 root render 226, 128 Mar  4 ... /dev/dri/renderD128
```

Both `card0` (display) and `renderD128` (compute/render) are present. The GPU is accessible to the container through the DRA pipeline: ResourceSlice advertised the device, DeviceClass matched it, ResourceClaim requested it, the kubelet plugin injected it via CDI.

## What We Have Now

At this point the cluster has:
- Intel Arc iGPU exposed on mini-1/2/3 via DRA (ResourceSlice/ResourceClaim)
- NVIDIA GPU Operator ready (manual sync, awaiting RTX 5070 hardware fix)
- GPU-local Longhorn storage on gpu-1 for AI workloads

The DRA stack on the Intel side is fully operational and demonstrates the future of GPU scheduling in Kubernetes. The NVIDIA side is infrastructure-complete, waiting on a PCIe bus that refuses to cooperate. When it does, enabling it is a single ArgoCD sync away.

**Next: [GitOps Everything with ArgoCD]({{< relref "/posts/05-gitops" >}})**
