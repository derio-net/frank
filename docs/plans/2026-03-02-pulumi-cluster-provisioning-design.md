# Pulumi Cluster Provisioning — Import & Evolve

**Date:** 2026-03-02
**Status:** Approved
**Approach:** Import existing cluster state into Pulumi, then incrementally evolve toward target architecture.

## Current Cluster Snapshot (2026-03-02)

| Node | IP | Role | Arch | CNI | Storage | GPU | Labels |
|------|----|------|------|-----|---------|-----|--------|
| mini-1 | 192.168.55.21 | control-plane | amd64 | Flannel | none | Radeon 780M (iGPU) | default only |
| mini-2 | 192.168.55.22 | control-plane | amd64 | Flannel | none | Radeon 780M (iGPU) | default only |
| mini-3 | 192.168.55.23 | control-plane | amd64 | Flannel | none | Radeon 780M (iGPU) | default only |
| gpu-1 | 192.168.55.31 | worker | amd64 | Flannel | none | RTX 5070 | default only |
| pc-1 | 192.168.55.71 | worker | amd64 | Flannel | none | none | default only |
| raspi-1 | 192.168.55.41 | worker | arm64 | Flannel | none | none | default only |
| raspi-2 | 192.168.55.42 | worker | arm64 | Flannel | none | none | default only |

- **Talos version:** v1.12.4
- **Kubernetes version:** v1.35.2
- **Management:** Sidero Omni at `https://omni.frank.derio.net` (dashboard/multi-cluster only)
- **IaC:** None — configs were applied manually through Omni
- **Flux CD:** Running in cluster but manifests deleted from git ("remove naive approach")
- **GitOps:** Deferred — focus on Pulumi for cluster provisioning first

## Target Architecture

### Pulumi Scope
- Talos machine secrets, configs, and lifecycle (via `@pulumiverse/talos` provider)
- Kubernetes resources: CNI (Cilium), storage (Longhorn), GPU (Nvidia Operator)
- Node labels, taints, and scheduling configuration
- State backend: local filesystem initially, S3-compatible (self-hosted) later

### Node Target State

| Node | Zone | Labels | Taints | Extensions |
|------|------|--------|--------|------------|
| mini-{1,2,3} | core | `zone=core`, `tier=standard`, `accelerator=amd-igpu`, `igpu=radeon-780m` | none (scheduling allowed) | — |
| gpu-1 | ai-compute | `zone=ai-compute`, `accelerator=nvidia`, `model-server=true`, `tier=standard` | `nvidia.com/gpu=present:NoSchedule` | nvidia-container-toolkit, nvidia-open-gpu-kernel-modules |
| pc-1 | edge | `zone=edge`, `tier=standard` | — | — |
| raspi-{1,2} | edge | `zone=edge`, `tier=low-power` | — | — |

### Infrastructure Stack
- **CNI:** Cilium (replaces Flannel, with kube-proxy replacement)
- **Storage:** Longhorn — dual pools:
  - `longhorn` (default): 3 replicas across mini-{1,2,3} NVMe drives
  - `longhorn-gpu-local`: 1 replica on gpu-1's 2x4TB SSDs (AI data, models, datasets)
- **GPU:** Nvidia extensions in Talos + GPU Operator in Kubernetes
- **AMD iGPU (NUCs):** Labels applied now, ROCm stack deferred to future phase

## Design Sections

### 1. Secret Extraction & Pulumi Project Bootstrap

Extract existing Talos machine secrets from the running cluster and establish the Pulumi project.

**Pulumi project at `infrastructure/pulumi/`:**
```
infrastructure/pulumi/
├── Pulumi.yaml
├── Pulumi.frank.yaml
├── package.json
├── tsconfig.json
├── index.ts
├── config/
│   ├── nodes.ts
│   └── patches/
│       ├── controlplane.ts
│       ├── gpu-worker.ts
│       ├── edge-worker.ts
│       └── common.ts
└── secrets.yaml          (gitignored)
```

**Bootstrap sequence:**
1. Extract running machine config via `talosctl`
2. Format into `secrets.yaml`
3. Initialize Pulumi project
4. Import secrets: `pulumi import talos:machine/secrets:Secrets cluster-secrets ./secrets.yaml`
5. Import bootstrap marker: `pulumi import talos:machine/bootstrap:Bootstrap cluster-bootstrap already-done`

### 2. Node Configuration Architecture

Typed node inventory in `config/nodes.ts`. Config patches are layered:
- `common.ts` — all nodes (cluster name, endpoint, networking)
- Zone-specific patches — per-zone labels, scheduling, disk mounts
- Node-specific patches — hostname, IP, extensions

`ConfigurationApply` per node with `applyMode: "staged_if_needing_reboot"`.

Control planes get `allowSchedulingOnControlPlanes: true` to remove the current `NoSchedule` taint.

### 3. CNI Migration (Flannel → Cilium)

Rip-and-replace strategy:
1. Update Talos configs: `cluster.network.cni.name: none`
2. Delete Flannel DaemonSet
3. Deploy Cilium via Helm (Pulumi K8s provider)
4. Remove kube-proxy DaemonSet (Cilium replaces it with `kubeProxyReplacement: true`)

Brief network outage expected (~5 minutes). Acceptable for homelab.

**Key Cilium settings:** `kubeProxyReplacement: true`, Hubble enabled, operator replicas: 2.

### 4. Storage (Longhorn)

**Main pool (NUCs):**
- Longhorn Helm chart deployed via Pulumi
- 3 replicas, NVMe-backed on mini-{1,2,3}
- Talos machine config patches to mount data partitions
- `longhorn` StorageClass as default

**GPU storage pool (gpu-1):**
- 2x4TB SSDs mounted via Talos machine config
- `longhorn-gpu-local` StorageClass with `numberOfReplicas: 1`, `dataLocality: strict-local`
- nodeSelector: `zone=ai-compute`

### 5. GPU Configuration (Nvidia RTX 5070)

**Talos layer:**
- Image Factory schematic with `nvidia-container-toolkit` and `nvidia-open-gpu-kernel-modules`
- Kernel modules: `nvidia`, `nvidia_uvm`, `nvidia_modeset`, `nvidia_drm`
- Different schematic from other nodes

**Kubernetes layer:**
- Nvidia GPU Operator via Helm (driver disabled — Talos handles drivers)
- Creates `RuntimeClass: nvidia` and exposes `nvidia.com/gpu` resource

### 6. Verification & Testing Strategy

Every change has a verification command. No task completes without passing verification.

| Phase | Change | Verification | Expected |
|-------|--------|-------------|----------|
| 1a | Secrets imported | `pulumi preview` | No changes |
| 1b | Bootstrap imported | `pulumi preview` | No changes |
| 2a | Node labels | `kubectl get nodes -L zone,tier,accelerator` | Labels match |
| 2b | CP scheduling | `kubectl describe node mini-1 \| grep Taint` | No NoSchedule |
| 2c | GPU taint | `kubectl describe node gpu-1 \| grep Taint` | nvidia taint present |
| 3a | Flannel removed | `kubectl get ds -n kube-system` | No kube-flannel |
| 3b | Cilium deployed | `cilium status` | All OK |
| 3c | kube-proxy removed | `kubectl get ds -n kube-system` | No kube-proxy |
| 3d | Connectivity | `cilium connectivity test` | Pass |
| 4a | Longhorn deployed | `kubectl get sc` | longhorn (default) |
| 4b | PVC test | Create + bind PVC | PV bound, 3 replicas |
| 4c | GPU storage | `kubectl get sc longhorn-gpu-local` | Exists |
| 5a | Nvidia extensions | `talosctl -n .31 get extensions` | nvidia toolkit |
| 5b | GPU Operator | `kubectl get pods -n gpu-operator` | All Running |
| 5c | GPU allocatable | node capacity JSON | `"1"` |
| 5d | nvidia-smi test | Run test pod | RTX 5070 visible |

**Parallelization:**
```
Phase 1 (sequential): Pulumi setup + secrets import
    ↓
Phase 2 (sequential): Node configs + labels/taints
    ↓
Phase 3-5 (parallel after CNI is up):
  Stream C: CNI migration
  Stream D: Longhorn storage (after CNI healthy)
  Stream E: GPU stack (after CNI healthy)
```

**Human-in-the-loop:** Operator approval required between phases. Failed verification → stop, diagnose, present options.

**Rollback per phase:**
- Phase 1-2: `pulumi destroy` or revert config patches
- Phase 3: Re-deploy Flannel, remove Cilium
- Phase 4: `helm uninstall longhorn`
- Phase 5: Remove GPU Operator, revert schematic

## Deferred Work

- GitOps tool selection (ArgoCD vs Flux) — decided later
- AMD ROCm stack for NUC iGPUs — labels applied now, stack deferred
- S3-compatible Pulumi state backend — local for now
- Zone D edge node optimization — handled by same Pulumi code but not prioritized
