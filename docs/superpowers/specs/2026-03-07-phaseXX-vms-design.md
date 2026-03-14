# Phase 11: VMs — Design

**Date:** 2026-03-07

## Overview

Deploy KubeVirt to enable running virtual machines alongside containers in Frank. Adds CDI (Containerized Data Importer) for importing VM disk images, and KubeVirt Manager as a web UI for VM management. Initial goal is to have the capability working with a demo Linux VM — specific use cases will emerge from experimentation.

## Stack

| Component | Tool | Notes |
|-----------|------|-------|
| VM engine | KubeVirt | CNCF project, runs VMs as K8s pods |
| Disk importer | CDI (Containerized Data Importer) | Imports cloud images into PVCs |
| Web UI | KubeVirt Manager | Open source VM management dashboard |

## Architecture

KubeVirt extends Kubernetes with `VirtualMachine` and `VirtualMachineInstance` CRDs. VMs run as pods under the hood (using KVM/QEMU), but are managed as first-class K8s resources.

CDI enables importing standard cloud images (`.qcow2`, `.img`) from URLs or container registries into `DataVolume` PVCs, which VMs boot from.

```
VirtualMachine CR
    └── DataVolume (Longhorn PVC, imported via CDI)
    └── VirtualMachineInstance (running pod with KVM)
            └── Exposed via K8s Service (SSH, VNC, etc.)
```

### Demo VM

A Debian or Ubuntu cloud image imported via CDI DataVolume. Accessible via `virtctl console` or VNC through KubeVirt Manager.

## ArgoCD Apps

**`kubevirt`** (namespace: `kubevirt`)
- KubeVirt operator deployed via manifests (GitHub releases)
- CDI operator deployed via manifests
- Values: `apps/kubevirt/manifests/`

**`kubevirt-manager`** (namespace: `kubevirt-manager`)
- Chart or manifests from `kubevirt-manager/kubevirt-manager`
- LoadBalancer IP: `192.168.55.205`

## Storage

VM disk images stored as Longhorn PVCs via CDI DataVolumes.

| Component | Size | Notes |
|-----------|------|-------|
| Demo VM disk | 20Gi | Longhorn, imported from cloud image |

## Exposure

| Service | IP | Notes |
|---------|----|-------|
| KubeVirt Manager UI | `192.168.55.205` | Cilium L2 LoadBalancer |
| VM console/VNC | Via KubeVirt Manager | Per-VM, no dedicated IP |
| VM SSH | NodePort or LoadBalancer per VM | Configured per VM |

## Node Scheduling

KubeVirt requires hardware virtualisation (KVM). All mini nodes and pc-1 support KVM. Raspberry Pi nodes do **not** support KVM — VMs must be scheduled away from raspi-1 and raspi-2 via node selectors or tolerations.

## Blog Post

**Title:** "Phase 11 — VMs: Running Virtual Machines in Kubernetes with KubeVirt"

**Angle:** Why run VMs in K8s at all? Walk through the KubeVirt architecture (VMs as pods), CDI image import pipeline, and managing VMs via KubeVirt Manager. Spin up a demo Debian VM, SSH in, show it running alongside containers. Mention future possibilities: GPU passthrough, Windows VMs, network appliances.
