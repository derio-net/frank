---
title: "Building the Foundation — Talos, Nodes, and Cilium"
date: 2026-03-06
draft: false
tags: ["talos", "cilium", "networking", "bootstrap"]
summary: "Bootstrapping a Talos Linux cluster with Omni, configuring node labels and zones, and replacing Flannel with Cilium's eBPF networking."
weight: 3
cover:
  image: cover.png
  alt: "Frank the cluster monster laying a foundation of server nodes connected by Cilium network threads"
  relative: true
---

This post covers the first three steps of building Frank Cluster: bootstrapping Talos Linux via Omni, organizing nodes into labeled zones, and installing Cilium as the CNI with eBPF kube-proxy replacement.

## Why Talos Linux?

Most Kubernetes homelab guides start with Ubuntu Server and kubeadm, or a turnkey distribution like k3s. Both are fine choices, but they carry an assumption: you will SSH into your nodes, install packages, edit files, and maintain a general-purpose Linux system alongside your cluster. Over time, that OS layer accumulates drift -- an apt upgrade here, a stale config file there -- and reproducing the state of any given node becomes an exercise in archaeology.

Talos Linux takes a different approach. It is a purpose-built, immutable operating system designed to run Kubernetes and nothing else. There is no SSH. There is no shell. There is no package manager. The entire OS is defined by a single machine configuration document, applied through a gRPC API (`talosctl`). If you want to change something about a node -- add a kernel argument, enable a system extension, set a static IP -- you modify the machine config and apply it. The node reconciles to match.

This gives you a few properties that matter for a homelab that you actually want to maintain:

- **Reproducibility.** Every node's state is fully described by its machine config. You can rebuild any node from scratch by re-applying the same document.
- **Security posture.** With no shell access and a read-only root filesystem, the attack surface is minimal. There is nothing to harden because there is nothing extra installed.
- **Declarative operations.** Updates, reboots, and configuration changes are all API calls. You can version-control the machine configs and treat them like any other infrastructure-as-code artifact.

The trade-off is real: when something goes wrong, you cannot SSH in and poke around. Debugging happens through `talosctl logs`, `talosctl dmesg`, and the Kubernetes API itself. It takes some adjustment, but once you internalize the workflow, the operational simplicity is worth it.

## Bootstrapping with Omni

Sidero Omni sits on `raspi-omni` in Zone A (the management zone) and handles machine lifecycle: enrollment, configuration, upgrades, and cluster creation. It is a SaaS-like control plane for Talos clusters -- you boot a machine with the Omni ISO, it phones home, and you assign it to a cluster through the Omni dashboard or API.

For Frank Cluster, the bootstrap sequence was straightforward:

1. Flash each machine (minis, gpu-1, pc-1, Raspberry Pis) with the Omni Talos ISO.
2. Machines appear in the Omni inventory as unallocated.
3. Create the `frank` cluster in Omni, assign `mini-1`, `mini-2`, `mini-3` as control planes, and the rest as workers.
4. Omni generates machine configs, pushes them to each node, and bootstraps etcd.

Omni lives outside this repo -- it is Zone A infrastructure, managed manually on `raspi-omni`. Everything from Phase 1 onward is applied as **config patches** through `omnictl`, which layer on top of the base machine configs that Omni generated. This is how you customize Talos nodes without touching the base config directly: each patch targets either the whole cluster or a specific machine by ID.

## Phase 1: Node Configuration

With the cluster bootstrapped and all seven nodes reporting Ready, the first order of business is making the cluster usable for a homelab workload mix. That means two things: letting workloads run on the control plane nodes, and labeling every node so we can target scheduling decisions later.

### Key Config: Cluster-Wide Scheduling

In a production environment, you keep workloads off the control plane. In a homelab with three control-plane nodes that are also your best hardware (Intel NUC-class minis with 64 GB RAM each), leaving them idle is wasteful. The following Omni config patch removes the default `NoSchedule` taint from all control-plane nodes:

```yaml
# patches/phase01-node-config/01-cluster-wide-scheduling.yaml
cluster:
    allowSchedulingOnControlPlanes: true
```

This is a cluster-scoped patch (note the `omni.sidero.dev/cluster: frank` label, no machine-specific selector). Talos handles this at the config level rather than requiring you to manually remove taints with `kubectl taint`. The result: `mini-1`, `mini-2`, and `mini-3` run both control-plane components and regular workloads, which is essential when those three nodes are also your Longhorn storage tier.

### Key Config: Node Labels

Every node gets a set of labels applied through per-machine config patches. The labeling scheme encodes the zone architecture described in Post 1:

```yaml
# patches/phase01-node-config/03-labels-mini-1.yaml (abbreviated)
machine:
    nodeLabels:
        zone: core
        tier: standard
        accelerator: intel-igpu
        igpu: intel-arc
```

```yaml
# patches/phase01-node-config/03-labels-gpu-1.yaml (abbreviated)
machine:
    nodeLabels:
        zone: ai-compute
        tier: standard
        accelerator: nvidia
        model-server: "true"
```

```yaml
# patches/phase01-node-config/03-labels-raspi-1.yaml (abbreviated)
machine:
    nodeLabels:
        zone: edge
        tier: low-power
```

The pattern across all seven nodes:

| Label | Values | Purpose |
|-------|--------|---------|
| `zone` | `core`, `ai-compute`, `edge` | Maps to the physical zone architecture (B, C, D) |
| `tier` | `standard`, `low-power` | Distinguishes capable nodes from Raspberry Pis |
| `accelerator` | `nvidia`, `intel-igpu` | Marks GPU-equipped nodes for device plugin scheduling |
| `igpu` | `intel-arc` | Specific iGPU model (used by Intel DRA driver) |
| `model-server` | `"true"` | Flags gpu-1 for future AI inference workloads |

These labels are applied via Talos machine config, not `kubectl label`. The difference matters: if a node reboots or is reprovisioned, the labels survive because they are part of the declarative machine state. Labels applied with `kubectl` are stored in the Kubernetes API and can drift if the node is recreated.

Each patch file targets a specific machine by its Omni machine ID (a UUID), ensuring the labels go to exactly the right node. The ID-based targeting in the Omni metadata looks like:

```yaml
metadata:
    labels:
        omni.sidero.dev/cluster: frank
        omni.sidero.dev/cluster-machine: ce4d0d52-6c10-bdc9-746c-88aedd67681b
```

## Phase 2: Cilium CNI

Talos ships with Flannel as the default CNI. Flannel works, but it is a minimal overlay network -- no network policy enforcement, no built-in observability, and no native LoadBalancer implementation. For a homelab that needs to expose services on the local network and wants visibility into pod-to-pod traffic, Cilium is a significant upgrade.

The key features that justified the switch:

- **eBPF kube-proxy replacement.** Cilium replaces kube-proxy entirely, handling service load balancing in eBPF at the kernel level rather than through iptables chains. This is faster and eliminates the kube-proxy DaemonSet.
- **L2 LoadBalancer announcements.** Cilium can announce LoadBalancer IPs via ARP on the local network, giving services real IPs on your home subnet without MetalLB.
- **Hubble.** Built-in network observability with a UI. You can see every flow between pods, which is invaluable for debugging connectivity issues in a mixed-architecture cluster.

### Removing Flannel

Swapping the CNI on a running Talos cluster is a careful two-step process. First, you tell Talos to stop managing the default CNI and to disable kube-proxy:

```yaml
# patches/phase02-cilium/02-cluster-wide-cni-none.yaml
cluster:
    network:
        cni:
            name: none
    proxy:
        disabled: true
```

This patch does two things: it sets `cni: none` so Talos does not install Flannel on new or rebooting nodes, and it disables the built-in kube-proxy. The order matters -- you need Cilium ready to deploy immediately after applying this patch, because the cluster will lose pod networking until the new CNI takes over.

Before applying the patch, you also need to manually clean up the existing Flannel and kube-proxy DaemonSets:

```bash
kubectl delete ds kube-flannel -n kube-system
kubectl delete ds kube-proxy -n kube-system
```

### Installing Cilium

Cilium is installed via its Helm chart (v1.17.0). The Helm values require several Talos-specific settings that are not obvious from the standard Cilium documentation:

```yaml
# apps/cilium/values.yaml (key sections)
kubeProxyReplacement: true
k8sServiceHost: 127.0.0.1
k8sServicePort: 7445

cgroup:
  autoMount:
    enabled: false
  hostRoot: /sys/fs/cgroup

hubble:
  enabled: true
  relay:
    enabled: true
  ui:
    enabled: true

operator:
  replicas: 2

l2announcements:
  enabled: true
externalIPs:
  enabled: true
```

A few values worth explaining:

- **`k8sServiceHost: 127.0.0.1` / `k8sServicePort: 7445`**: Talos runs a local API server proxy on every node at `127.0.0.1:7445`. Since Cilium is replacing kube-proxy, it needs to know how to reach the Kubernetes API directly, without relying on the `kubernetes.default` service (which kube-proxy would normally handle). This localhost proxy is a Talos-specific detail.
- **`cgroup.autoMount.enabled: false`**: Talos already mounts cgroups. Letting Cilium try to mount them again causes conflicts. You point it to the existing mount at `/sys/fs/cgroup` instead.
- **`operator.replicas: 2`**: With three control-plane nodes, running two operator replicas gives HA without consuming a third node's resources.
- **`l2announcements.enabled: true`**: This activates Cilium's native L2 aware LB mode, which replaces the need for MetalLB entirely.

Beyond the Helm values, two additional manifests complete the L2 LoadBalancer setup:

```yaml
# apps/cilium/manifests/lb-ippool.yaml
apiVersion: "cilium.io/v2alpha1"
kind: CiliumLoadBalancerIPPool
metadata:
  name: default-pool
spec:
  blocks:
    - start: "192.168.55.200"
      stop: "192.168.55.210"
```

```yaml
# apps/cilium/manifests/l2-policy.yaml
apiVersion: "cilium.io/v2alpha1"
kind: CiliumL2AnnouncementPolicy
metadata:
  name: default-l2-policy
spec:
  interfaces:
    - ^eth[0-9]+
    - ^en[a-z0-9]+
  externalIPs: true
  loadBalancerIPs: true
```

The IP pool reserves `192.168.55.200-210` on the home subnet for LoadBalancer services. The L2 announcement policy tells Cilium to respond to ARP requests for those IPs on any Ethernet interface matching the regex patterns -- this covers both `eth0` (Raspberry Pis) and `enp`-style names (the x86 machines). Any service of type `LoadBalancer` automatically gets an IP from this pool and becomes reachable from the local network.

### Gotchas

A few things that tripped me up during this phase:

1. **The CNI swap is not atomic.** There is a window between applying `cni: none` and Cilium becoming ready where pods cannot communicate. If you are doing this on a running cluster, expect a few minutes of downtime. On a fresh cluster it is less of an issue because you can apply the patch before deploying workloads.

2. **Talos-specific security capabilities.** The Cilium agent requires an explicit list of Linux capabilities to function on Talos. The default Cilium Helm values do not include all of them. If you see Cilium pods stuck in `CrashLoopBackOff` with permission errors, check that your `securityContext.capabilities.ciliumAgent` list includes `IPC_LOCK`, `SYS_RESOURCE`, and the other entries shown in the values above. The `cleanCiliumState` init container also needs its own capability set.

3. **cgroup auto-mount conflicts.** If you leave `cgroup.autoMount.enabled: true` (the default), Cilium will try to mount cgroupv2 and fail on Talos because it is already mounted and the root filesystem is read-only. The symptom is the Cilium agent pods failing to start with mount-related errors. Set it to `false` and point `hostRoot` to the existing mount.

4. **L2 announcement interface regex.** The interface pattern needs to match your actual node interfaces. A pattern like `^eth0$` will miss nodes that use `enp` naming. Using the broader regex patterns (`^eth[0-9]+` and `^en[a-z0-9]+`) covers the heterogeneous hardware in the cluster.

5. **kube-proxy cleanup.** Even after setting `proxy.disabled: true` in the Talos config, the existing kube-proxy DaemonSet does not automatically disappear. You need to delete it manually. If you forget, you will have both Cilium and kube-proxy fighting over iptables rules, which leads to confusing connectivity issues.

## What We Have Now

At this point the cluster has:
- 7 nodes running Talos Linux, managed by Omni
- Labeled zones (Core, AI Compute, Edge) for workload placement
- Cilium CNI with eBPF kube-proxy replacement
- L2 LoadBalancer (192.168.55.200-210) for service exposure
- Hubble for network observability

**Next: [Persistent Storage with Longhorn]({{< relref "/posts/03-storage" >}})**
