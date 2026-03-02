# Pulumi Cluster Provisioning — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring the running frank cluster under Pulumi IaC management and evolve it to target architecture (Cilium, Longhorn, Nvidia GPU).

**Architecture:** Import existing Talos secrets → define typed node configs → apply incrementally with verification gates → deploy infrastructure Helm charts (Cilium, Longhorn, GPU Operator) via Pulumi K8s provider.

**Tech Stack:** Pulumi (TypeScript), `@pulumiverse/talos`, `@pulumi/kubernetes`, Talos v1.12.4, K8s v1.35.2

**Prereqs:** All commands assume `source .env` has been run (loads `KUBECONFIG` and `TALOSCONFIG`).

---

## Phase 1: Pulumi Project Bootstrap & Secret Import

### Task 1.1: Initialize the Pulumi Project

**Files:**
- Create: `infrastructure/pulumi/Pulumi.yaml`
- Create: `infrastructure/pulumi/package.json`
- Create: `infrastructure/pulumi/tsconfig.json`
- Create: `infrastructure/pulumi/index.ts` (empty entry point)
- Modify: `.gitignore` — add `infrastructure/pulumi/secrets.yaml`

**Step 1: Create directory structure**

```bash
mkdir -p infrastructure/pulumi/config/patches
```

**Step 2: Initialize Pulumi project**

```bash
cd infrastructure/pulumi
pulumi new typescript \
  --name frank-cluster \
  --description "Talos cluster provisioning for frank" \
  --stack frank \
  --yes
```

Expected: Creates `Pulumi.yaml`, `package.json`, `tsconfig.json`, `index.ts`.

**Step 3: Install dependencies**

```bash
cd infrastructure/pulumi
npm install @pulumiverse/talos @pulumi/kubernetes
```

Expected: Both packages added to `package.json` and installed.

**Step 4: Configure local state backend**

```bash
cd infrastructure/pulumi
pulumi login --local
```

Expected: Pulumi uses `~/.pulumi` for state storage.

**Step 5: Add secrets.yaml to .gitignore**

Append to `.gitignore`:
```
# Talos machine secrets (extracted from cluster, imported into Pulumi)
infrastructure/pulumi/secrets.yaml
```

**Step 6: Verify**

```bash
cd infrastructure/pulumi && pulumi stack ls
```

Expected: Shows `frank` stack.

**Step 7: Commit**

```bash
git add infrastructure/pulumi/Pulumi.yaml infrastructure/pulumi/package.json \
  infrastructure/pulumi/tsconfig.json infrastructure/pulumi/index.ts .gitignore
git commit -m "feat(pulumi): initialize Talos cluster provisioning project"
```

---

### Task 1.2: Extract Machine Secrets from Running Cluster

**Files:**
- Create: `infrastructure/pulumi/secrets.yaml` (gitignored)

**Step 1: Read machine config from a control plane node**

```bash
source .env
talosctl -n 192.168.55.21 get machineconfig -o yaml > /tmp/frank-cp-machineconfig.yaml
```

Expected: Full machine config YAML for mini-1 saved to temp file.

**Step 2: Generate secrets bundle from the running config**

```bash
source .env
talosctl gen secrets --from-controlplane-config /tmp/frank-cp-machineconfig.yaml \
  -o infrastructure/pulumi/secrets.yaml
```

Expected: `secrets.yaml` containing cluster CA, machine CA, etcd CA, bootstrap token, etc.

**Step 3: Verify secrets file structure**

```bash
cat infrastructure/pulumi/secrets.yaml | head -20
```

Expected: YAML with `cluster:`, `secrets:`, `trustdinfo:` top-level keys.

**Step 4: Clean up temp file**

```bash
rm /tmp/frank-cp-machineconfig.yaml
```

**Step 5: Verify secrets.yaml is gitignored**

```bash
git status infrastructure/pulumi/secrets.yaml
```

Expected: File not shown (gitignored).

---

### Task 1.3: Define Node Inventory

**Files:**
- Create: `infrastructure/pulumi/config/nodes.ts`

**Step 1: Write the typed node inventory**

```typescript
// infrastructure/pulumi/config/nodes.ts

export interface NodeConfig {
  name: string;
  ip: string;
  zone: "core" | "ai-compute" | "edge";
  role: "controlplane" | "worker";
  arch: "amd64" | "arm64";
  labels: Record<string, string>;
  taints?: { key: string; value: string; effect: string }[];
  diskMounts?: { device: string; mountpoint: string }[];
}

export const clusterName = "frank";
export const clusterEndpoint = "https://192.168.55.21:6443";
export const talosVersion = "v1.12.4";
export const kubernetesVersion = "v1.35.2";

export const nodes: NodeConfig[] = [
  // Zone B: Core HA Control Plane (3x ASUS NUCs)
  {
    name: "mini-1",
    ip: "192.168.55.21",
    zone: "core",
    role: "controlplane",
    arch: "amd64",
    labels: {
      "zone": "core",
      "tier": "standard",
      "accelerator": "amd-igpu",
      "igpu": "radeon-780m",
    },
  },
  {
    name: "mini-2",
    ip: "192.168.55.22",
    zone: "core",
    role: "controlplane",
    arch: "amd64",
    labels: {
      "zone": "core",
      "tier": "standard",
      "accelerator": "amd-igpu",
      "igpu": "radeon-780m",
    },
  },
  {
    name: "mini-3",
    ip: "192.168.55.23",
    zone: "core",
    role: "controlplane",
    arch: "amd64",
    labels: {
      "zone": "core",
      "tier": "standard",
      "accelerator": "amd-igpu",
      "igpu": "radeon-780m",
    },
  },
  // Zone C: AI Compute (GPU Desktop)
  {
    name: "gpu-1",
    ip: "192.168.55.31",
    zone: "ai-compute",
    role: "worker",
    arch: "amd64",
    labels: {
      "zone": "ai-compute",
      "tier": "standard",
      "accelerator": "nvidia",
      "model-server": "true",
    },
    taints: [
      { key: "nvidia.com/gpu", value: "present", effect: "NoSchedule" },
    ],
  },
  // Zone D: Edge / Burst
  {
    name: "pc-1",
    ip: "192.168.55.71",
    zone: "edge",
    role: "worker",
    arch: "amd64",
    labels: {
      "zone": "edge",
      "tier": "standard",
    },
  },
  {
    name: "raspi-1",
    ip: "192.168.55.41",
    zone: "edge",
    role: "worker",
    arch: "arm64",
    labels: {
      "zone": "edge",
      "tier": "low-power",
    },
  },
  {
    name: "raspi-2",
    ip: "192.168.55.42",
    zone: "edge",
    role: "worker",
    arch: "arm64",
    labels: {
      "zone": "edge",
      "tier": "low-power",
    },
  },
];

export const controlPlaneNodes = nodes.filter(n => n.role === "controlplane");
export const workerNodes = nodes.filter(n => n.role === "worker");
export const gpuNodes = nodes.filter(n => n.labels["accelerator"] === "nvidia");
```

**Step 2: Verify TypeScript compiles**

```bash
cd infrastructure/pulumi && npx tsc --noEmit config/nodes.ts
```

Expected: No errors.

**Step 3: Commit**

```bash
git add infrastructure/pulumi/config/nodes.ts
git commit -m "feat(pulumi): add typed node inventory for all cluster zones"
```

---

### Task 1.4: Write Config Patches

**Files:**
- Create: `infrastructure/pulumi/config/patches/common.ts`
- Create: `infrastructure/pulumi/config/patches/controlplane.ts`
- Create: `infrastructure/pulumi/config/patches/gpu-worker.ts`
- Create: `infrastructure/pulumi/config/patches/edge-worker.ts`

**Step 1: Write common patch (all nodes)**

```typescript
// infrastructure/pulumi/config/patches/common.ts

// Applied to ALL nodes — cluster-wide settings
export function commonPatch(hostname: string, ip: string): object {
  return {
    machine: {
      network: {
        hostname: hostname,
      },
      nodeLabels: {},  // per-node labels are applied via ConfigurationApply patches
    },
  };
}
```

**Step 2: Write control plane patch**

```typescript
// infrastructure/pulumi/config/patches/controlplane.ts

// Applied to control plane nodes — enables workload scheduling
export function controlplanePatch(): object {
  return {
    cluster: {
      allowSchedulingOnControlPlanes: true,
    },
  };
}
```

**Step 3: Write GPU worker patch**

```typescript
// infrastructure/pulumi/config/patches/gpu-worker.ts

// Applied to gpu-1 — Nvidia kernel modules and driver config
export function gpuWorkerPatch(): object {
  return {
    machine: {
      kernel: {
        modules: [
          { name: "nvidia" },
          { name: "nvidia_uvm" },
          { name: "nvidia_modeset" },
          { name: "nvidia_drm" },
        ],
      },
    },
  };
}
```

**Step 4: Write edge worker patch (placeholder)**

```typescript
// infrastructure/pulumi/config/patches/edge-worker.ts

// Applied to edge/burst nodes — currently no special config
export function edgeWorkerPatch(): object {
  return {};
}
```

**Step 5: Verify all patches compile**

```bash
cd infrastructure/pulumi && npx tsc --noEmit config/patches/*.ts
```

Expected: No errors.

**Step 6: Commit**

```bash
git add infrastructure/pulumi/config/patches/
git commit -m "feat(pulumi): add layered config patches for all node zones"
```

---

### Task 1.5: Write Pulumi Index — Secrets + Bootstrap Import

**Files:**
- Modify: `infrastructure/pulumi/index.ts`

**Step 1: Write the main Pulumi program with secrets and bootstrap**

```typescript
// infrastructure/pulumi/index.ts
import * as pulumi from "@pulumi/pulumi";
import * as talos from "@pulumiverse/talos";
import { nodes, clusterName, clusterEndpoint, talosVersion, kubernetesVersion, controlPlaneNodes } from "./config/nodes";
import { commonPatch } from "./config/patches/common";
import { controlplanePatch } from "./config/patches/controlplane";
import { gpuWorkerPatch } from "./config/patches/gpu-worker";
import { edgeWorkerPatch } from "./config/patches/edge-worker";

// --- Phase 1: Secrets & Bootstrap (imported from running cluster) ---

const secrets = new talos.machine.Secrets("cluster-secrets", {
  talosVersion: talosVersion,
});

const bootstrap = new talos.machine.Bootstrap("cluster-bootstrap", {
  node: controlPlaneNodes[0].ip,
  endpoint: controlPlaneNodes[0].ip,
  clientConfiguration: secrets.clientConfiguration,
});

// --- Phase 2: Machine Configs per Node ---

for (const node of nodes) {
  // Build patch list for this node
  const patches: string[] = [
    JSON.stringify(commonPatch(node.name, node.ip)),
  ];

  // Add node labels patch
  if (Object.keys(node.labels).length > 0) {
    patches.push(JSON.stringify({
      machine: { nodeLabels: node.labels },
    }));
  }

  // Add role-specific patches
  if (node.role === "controlplane") {
    patches.push(JSON.stringify(controlplanePatch()));
  } else if (node.labels["accelerator"] === "nvidia") {
    patches.push(JSON.stringify(gpuWorkerPatch()));
  } else if (node.zone === "edge") {
    patches.push(JSON.stringify(edgeWorkerPatch()));
  }

  // Generate machine config
  const machineConfig = talos.machine.getConfigurationOutput({
    clusterName: clusterName,
    machineType: node.role,
    clusterEndpoint: clusterEndpoint,
    machineSecrets: secrets.machineSecrets,
    talosVersion: talosVersion,
    kubernetesVersion: kubernetesVersion,
    configPatches: patches,
    docs: false,
    examples: false,
  });

  // Apply config to node
  const configApply = new talos.machine.ConfigurationApply(`config-${node.name}`, {
    clientConfiguration: secrets.clientConfiguration,
    machineConfigurationInput: machineConfig.machineConfiguration,
    node: node.ip,
    endpoint: node.ip,
    applyMode: "auto",
  }, {
    dependsOn: [bootstrap],
  });
}

// --- Outputs ---

const kubeconfig = new talos.cluster.Kubeconfig("kubeconfig", {
  clientConfiguration: secrets.clientConfiguration,
  node: controlPlaneNodes[0].ip,
}, {
  dependsOn: [bootstrap],
});

export const kubeconfigRaw = kubeconfig.kubeconfigRaw;
```

**Step 2: Verify TypeScript compiles**

```bash
cd infrastructure/pulumi && npx tsc --noEmit
```

Expected: No errors.

**Step 3: Commit**

```bash
git add infrastructure/pulumi/index.ts
git commit -m "feat(pulumi): main program with secrets, bootstrap, and per-node configs"
```

---

### Task 1.6: Import Existing Cluster State into Pulumi

**HUMAN CHECKPOINT: This task modifies Pulumi state. Operator must confirm.**

**Step 1: Import machine secrets**

```bash
cd infrastructure/pulumi
pulumi import talos:machine/secrets:Secrets cluster-secrets ./secrets.yaml --yes
```

Expected: `cluster-secrets` resource imported successfully.

**Step 2: Import bootstrap marker**

```bash
cd infrastructure/pulumi
pulumi import talos:machine/bootstrap:Bootstrap cluster-bootstrap cluster-bootstrap --yes
```

Expected: `cluster-bootstrap` resource imported.

**Step 3: Run pulumi preview to see what Pulumi wants to do**

```bash
cd infrastructure/pulumi && pulumi preview
```

Expected: Secrets and bootstrap show no changes. `ConfigurationApply` resources show as "create" (new — these will apply configs to the running nodes).

**Step 4: Verify**

The preview output tells us exactly what will happen. Review it carefully before proceeding. The `ConfigurationApply` resources for each node should show the config patches we defined.

---

## GATE 1: Operator Approval

**Pause here.** Present `pulumi preview` output to the operator.

Questions to answer before proceeding:
- Do the generated machine configs look correct for each node?
- Are the config patches applied in the right order?
- Is the operator comfortable with applying these configs to the running cluster?

---

## Phase 2: Apply Node Configurations

### Task 2.1: Apply Configs to All Nodes

**HUMAN CHECKPOINT: This modifies the running cluster.**

**Step 1: Apply Pulumi changes**

```bash
cd infrastructure/pulumi && pulumi up --yes
```

Expected: All `ConfigurationApply` resources created. Nodes receive updated configs.

**Step 2: Verify node labels**

```bash
source .env
kubectl get nodes -L zone,tier,accelerator,igpu,model-server
```

Expected:
```
NAME      STATUS   ROLES           zone         tier        accelerator   igpu          model-server
gpu-1     Ready    <none>          ai-compute   standard    nvidia                      true
mini-1    Ready    control-plane   core         standard    amd-igpu      radeon-780m
mini-2    Ready    control-plane   core         standard    amd-igpu      radeon-780m
mini-3    Ready    control-plane   core         standard    amd-igpu      radeon-780m
pc-1      Ready    <none>          edge         standard
raspi-1   Ready    <none>          edge         low-power
raspi-2   Ready    <none>          edge         low-power
```

**Step 3: Verify control plane scheduling (no taint)**

```bash
source .env
kubectl describe node mini-1 | grep -A 2 "Taints:"
```

Expected: `Taints: <none>` (the `NoSchedule` taint is removed because `allowSchedulingOnControlPlanes: true`).

**Step 4: Verify GPU taint**

```bash
source .env
kubectl describe node gpu-1 | grep -A 2 "Taints:"
```

Expected: `Taints: nvidia.com/gpu=present:NoSchedule`

**Step 5: Commit state confirmation**

```bash
git add -A infrastructure/pulumi/
git commit -m "feat(pulumi): apply node configs — labels, taints, CP scheduling"
```

---

## GATE 2: Operator Approval

**Pause here.** All nodes should have correct labels, taints, and configs.

Verify before proceeding to CNI migration (which will cause a brief network outage).

---

## Phase 3: CNI Migration (Flannel → Cilium)

### Task 3.1: Update Talos Configs to Disable Default CNI

**Files:**
- Modify: `infrastructure/pulumi/config/patches/common.ts`

**Step 1: Add CNI disable patch to common config**

Update `common.ts` to include:

```typescript
export function commonPatch(hostname: string, ip: string): object {
  return {
    machine: {
      network: {
        hostname: hostname,
      },
    },
    cluster: {
      network: {
        cni: {
          name: "none",
        },
      },
    },
  };
}
```

**Step 2: Apply the updated configs**

```bash
cd infrastructure/pulumi && pulumi up --yes
```

Expected: ConfigurationApply resources updated with new CNI config.

**Step 3: Commit**

```bash
git add infrastructure/pulumi/config/patches/common.ts
git commit -m "feat(pulumi): disable default CNI in Talos config (prep for Cilium)"
```

---

### Task 3.2: Remove Flannel and Deploy Cilium

**Files:**
- Modify: `infrastructure/pulumi/index.ts` — add Cilium Helm release

**Step 1: Add Kubernetes provider and Cilium Helm chart to index.ts**

Add after the node config loop in `index.ts`:

```typescript
import * as k8s from "@pulumi/kubernetes";

// --- Phase 3: Cilium CNI ---

const k8sProvider = new k8s.Provider("k8s", {
  kubeconfig: kubeconfig.kubeconfigRaw,
});

// Remove Flannel DaemonSet
// Note: This is done manually first:
//   kubectl delete daemonset kube-flannel -n kube-system
//   kubectl delete daemonset kube-proxy -n kube-system

const ciliumRelease = new k8s.helm.v3.Release("cilium", {
  chart: "cilium",
  version: "1.17.0",  // Verify latest stable for K8s v1.35
  namespace: "kube-system",
  repositoryOpts: {
    repo: "https://helm.cilium.io/",
  },
  values: {
    ipam: { mode: "kubernetes" },
    kubeProxyReplacement: true,
    k8sServiceHost: "127.0.0.1",  // Talos runs kube-apiserver on localhost
    k8sServicePort: 7445,          // Talos proxy port
    securityContext: {
      capabilities: {
        ciliumAgent: ["CHOWN", "KILL", "NET_ADMIN", "NET_RAW", "IPC_LOCK",
          "SYS_ADMIN", "SYS_RESOURCE", "DAC_OVERRIDE", "FOWNER", "SETGID",
          "SETUID"],
        cleanCiliumState: ["NET_ADMIN", "SYS_ADMIN", "SYS_RESOURCE"],
      },
    },
    cgroup: {
      autoMount: { enabled: false },
      hostRoot: "/sys/fs/cgroup",
    },
    hubble: {
      enabled: true,
      relay: { enabled: true },
      ui: { enabled: true },
    },
    operator: { replicas: 2 },
  },
}, { provider: k8sProvider });
```

**Step 2: Remove Flannel and kube-proxy manually (before Pulumi apply)**

**HUMAN CHECKPOINT: This causes network disruption. Confirm before proceeding.**

```bash
source .env
kubectl delete daemonset kube-flannel -n kube-system --ignore-not-found
kubectl delete daemonset kube-proxy -n kube-system --ignore-not-found
```

Expected: Both DaemonSets deleted. Nodes lose networking temporarily.

**Step 3: Apply Pulumi to deploy Cilium**

```bash
cd infrastructure/pulumi && pulumi up --yes
```

Expected: Cilium Helm release created. Cilium agents start on all nodes.

**Step 4: Verify Cilium is healthy**

```bash
source .env
cilium status --wait
```

Expected: All Cilium agents running, connected, healthy.

**Step 5: Verify all nodes are Ready**

```bash
source .env
kubectl get nodes
```

Expected: All 7 nodes in `Ready` status.

**Step 6: Run Cilium connectivity test**

```bash
source .env
cilium connectivity test
```

Expected: All tests pass. Pod-to-pod, pod-to-service connectivity working.

**Step 7: Commit**

```bash
git add infrastructure/pulumi/index.ts infrastructure/pulumi/package.json
git commit -m "feat(pulumi): deploy Cilium CNI replacing Flannel + kube-proxy"
```

---

## GATE 3: Operator Approval

**Pause here.** Cilium should be running and all connectivity tests passing.

Verify before proceeding to storage and GPU (which can now run in parallel).

---

## Phase 4: Longhorn Storage

### Task 4.1: Add Longhorn Disk Mount Patches for NUCs

**Files:**
- Modify: `infrastructure/pulumi/config/patches/controlplane.ts`
- Modify: `infrastructure/pulumi/config/nodes.ts` — add disk info

**Step 1: Discover NVMe device paths on NUCs**

```bash
source .env
talosctl -n 192.168.55.21 disks
```

Expected: Lists available disks. Note the NVMe device path (e.g., `/dev/nvme0n1`).

**Step 2: Add disk mount to controlplane patch**

Update `controlplane.ts`:

```typescript
export function controlplanePatch(nvmeDevice: string): object {
  return {
    cluster: {
      allowSchedulingOnControlPlanes: true,
    },
    machine: {
      disks: [
        {
          device: nvmeDevice,
          partitions: [
            {
              mountpoint: "/var/lib/longhorn",
              size: 0,  // Use all remaining space
            },
          ],
        },
      ],
    },
  };
}
```

**Step 3: Apply configs**

```bash
cd infrastructure/pulumi && pulumi up --yes
```

**Step 4: Verify mount on NUCs**

```bash
source .env
talosctl -n 192.168.55.21 mounts | grep longhorn
```

Expected: `/var/lib/longhorn` mounted.

**Step 5: Commit**

```bash
git add infrastructure/pulumi/config/patches/controlplane.ts
git commit -m "feat(pulumi): add Longhorn disk mount for NUC control planes"
```

---

### Task 4.2: Deploy Longhorn via Helm

**Files:**
- Modify: `infrastructure/pulumi/index.ts` — add Longhorn Helm release

**Step 1: Add Longhorn Helm release to index.ts**

```typescript
// --- Phase 4: Longhorn Storage ---

const longhornNs = new k8s.core.v1.Namespace("longhorn-system", {
  metadata: { name: "longhorn-system" },
}, { provider: k8sProvider });

const longhornRelease = new k8s.helm.v3.Release("longhorn", {
  chart: "longhorn",
  version: "1.8.0",  // Verify latest stable
  namespace: "longhorn-system",
  repositoryOpts: {
    repo: "https://charts.longhorn.io",
  },
  values: {
    defaultSettings: {
      defaultReplicaCount: 3,
      storageMinimalAvailablePercentage: 15,
      nodeDownPodDeletionPolicy: "delete-both-statefulset-and-deployment-pod",
      defaultDataLocality: "best-effort",
      createDefaultDiskLabeledNodes: true,
    },
    persistence: {
      defaultClassReplicaCount: 3,
      defaultClass: true,
    },
  },
}, { provider: k8sProvider, dependsOn: [ciliumRelease, longhornNs] });
```

**Step 2: Apply**

```bash
cd infrastructure/pulumi && pulumi up --yes
```

**Step 3: Verify Longhorn is running**

```bash
source .env
kubectl get pods -n longhorn-system
```

Expected: All Longhorn pods Running (manager, driver, UI, etc.).

**Step 4: Verify StorageClass**

```bash
source .env
kubectl get sc
```

Expected: `longhorn` StorageClass exists and is default.

**Step 5: Create a test PVC**

```bash
source .env
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: longhorn-test-pvc
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
EOF
```

**Step 6: Verify PVC is bound**

```bash
source .env
kubectl get pvc longhorn-test-pvc
```

Expected: STATUS = Bound.

**Step 7: Clean up test PVC**

```bash
source .env
kubectl delete pvc longhorn-test-pvc
```

**Step 8: Commit**

```bash
git add infrastructure/pulumi/index.ts
git commit -m "feat(pulumi): deploy Longhorn storage with 3-replica default pool"
```

---

### Task 4.3: Add GPU Local Storage Pool

**Files:**
- Modify: `infrastructure/pulumi/config/patches/gpu-worker.ts`
- Modify: `infrastructure/pulumi/index.ts` — add GPU StorageClass

**Step 1: Discover disk paths on gpu-1**

```bash
source .env
talosctl -n 192.168.55.31 disks
```

Expected: Shows 2x 4TB SSDs. Note device paths.

**Step 2: Add disk mounts to gpu-worker patch**

Update `gpu-worker.ts` to include disk mounts for both 4TB SSDs:

```typescript
export function gpuWorkerPatch(ssdDevice1: string, ssdDevice2: string): object {
  return {
    machine: {
      kernel: {
        modules: [
          { name: "nvidia" },
          { name: "nvidia_uvm" },
          { name: "nvidia_modeset" },
          { name: "nvidia_drm" },
        ],
      },
      disks: [
        {
          device: ssdDevice1,
          partitions: [{ mountpoint: "/var/lib/longhorn-gpu/disk1", size: 0 }],
        },
        {
          device: ssdDevice2,
          partitions: [{ mountpoint: "/var/lib/longhorn-gpu/disk2", size: 0 }],
        },
      ],
    },
  };
}
```

**Step 3: Add GPU StorageClass to index.ts**

```typescript
const gpuStorageClass = new k8s.storage.v1.StorageClass("longhorn-gpu-local", {
  metadata: { name: "longhorn-gpu-local" },
  provisioner: "driver.longhorn.io",
  reclaimPolicy: "Delete",
  volumeBindingMode: "Immediate",
  allowVolumeExpansion: true,
  parameters: {
    numberOfReplicas: "1",
    dataLocality: "strict-local",
    nodeSelector: "zone=ai-compute",
  },
}, { provider: k8sProvider, dependsOn: [longhornRelease] });
```

**Step 4: Apply**

```bash
cd infrastructure/pulumi && pulumi up --yes
```

**Step 5: Verify**

```bash
source .env
kubectl get sc longhorn-gpu-local
```

Expected: StorageClass exists.

**Step 6: Commit**

```bash
git add infrastructure/pulumi/config/patches/gpu-worker.ts infrastructure/pulumi/index.ts
git commit -m "feat(pulumi): add GPU local storage pool (2x4TB SSDs on gpu-1)"
```

---

## Phase 5: Nvidia GPU Stack

### Task 5.1: Create Nvidia Image Factory Schematic

**Files:**
- Modify: `infrastructure/pulumi/index.ts` — add Schematic resource

**Step 1: Add Image Factory schematic for GPU node**

Add to `index.ts`:

```typescript
// --- Phase 5: Nvidia GPU ---

const gpuSchematic = new talos.imageFactory.Schematic("gpu-schematic", {
  schematic: {
    customization: {
      systemExtensions: {
        officialExtensions: [
          "siderolabs/nvidia-container-toolkit",
          "siderolabs/nvidia-open-gpu-kernel-modules",
        ],
      },
    },
  },
});

export const gpuSchematicId = gpuSchematic.id;
```

**Step 2: Apply to get the schematic ID**

```bash
cd infrastructure/pulumi && pulumi up --yes
```

**Step 3: Verify schematic ID is output**

```bash
cd infrastructure/pulumi && pulumi stack output gpuSchematicId
```

Expected: A schematic hash string.

**Step 4: Commit**

```bash
git add infrastructure/pulumi/index.ts
git commit -m "feat(pulumi): create Nvidia GPU image factory schematic"
```

---

### Task 5.2: Apply GPU Schematic to gpu-1

**HUMAN CHECKPOINT: This will reboot gpu-1 to apply the new image with Nvidia extensions.**

**Step 1: Update gpu-1 ConfigurationApply to use the GPU schematic**

The gpu-1 node needs to be upgraded to use the schematic image that includes Nvidia extensions. This is done by updating the Talos machine config to reference the new installer image.

Add to the gpu-1 config patch in `index.ts`:

```typescript
// For GPU nodes, use the Nvidia schematic image
const gpuInstallerUrl = pulumi.interpolate`factory.talos.dev/installer/${gpuSchematic.id}:${talosVersion}`;

// Add to the gpu-1 ConfigurationApply configPatches:
configPatches: [
  pulumi.jsonStringify({
    machine: {
      install: {
        image: gpuInstallerUrl,
      },
    },
  }),
],
```

**Step 2: Apply**

```bash
cd infrastructure/pulumi && pulumi up --yes
```

Expected: gpu-1 receives new config with Nvidia installer image. May need reboot.

**Step 3: Verify Nvidia extensions are loaded**

```bash
source .env
talosctl -n 192.168.55.31 get extensions
```

Expected: Shows `nvidia-container-toolkit` and `nvidia-open-gpu-kernel-modules`.

**Step 4: Verify kernel modules**

```bash
source .env
talosctl -n 192.168.55.31 dmesg | grep -i nvidia | head -10
```

Expected: Nvidia driver initialization messages.

**Step 5: Commit**

```bash
git add infrastructure/pulumi/index.ts
git commit -m "feat(pulumi): apply Nvidia schematic to gpu-1 node"
```

---

### Task 5.3: Deploy Nvidia GPU Operator

**Files:**
- Modify: `infrastructure/pulumi/index.ts` — add GPU Operator Helm release

**Step 1: Add GPU Operator Helm release**

```typescript
const gpuOperatorNs = new k8s.core.v1.Namespace("gpu-operator", {
  metadata: { name: "gpu-operator" },
}, { provider: k8sProvider });

const gpuOperatorRelease = new k8s.helm.v3.Release("gpu-operator", {
  chart: "gpu-operator",
  namespace: "gpu-operator",
  repositoryOpts: {
    repo: "https://helm.ngc.nvidia.com/nvidia",
  },
  values: {
    driver: { enabled: false },       // Talos handles drivers via extensions
    toolkit: { enabled: false },      // Talos handles toolkit via extensions
    operator: {
      defaultRuntime: "containerd",
    },
  },
}, { provider: k8sProvider, dependsOn: [ciliumRelease, gpuOperatorNs] });
```

**Step 2: Apply**

```bash
cd infrastructure/pulumi && pulumi up --yes
```

**Step 3: Verify GPU Operator pods**

```bash
source .env
kubectl get pods -n gpu-operator
```

Expected: All GPU Operator pods Running.

**Step 4: Verify RuntimeClass**

```bash
source .env
kubectl get runtimeclass
```

Expected: `nvidia` RuntimeClass exists.

**Step 5: Verify GPU is allocatable**

```bash
source .env
kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
```

Expected: `1`

**Step 6: Run nvidia-smi test pod**

```bash
source .env
kubectl run nvidia-test --rm -it --restart=Never \
  --image=nvcr.io/nvidia/cuda:12.8.0-base-ubuntu24.04 \
  --overrides='{"spec":{"runtimeClassName":"nvidia","tolerations":[{"key":"nvidia.com/gpu","operator":"Exists","effect":"NoSchedule"}],"nodeSelector":{"accelerator":"nvidia"}}}' \
  -- nvidia-smi
```

Expected: Shows RTX 5070, driver version, CUDA version.

**Step 7: Commit**

```bash
git add infrastructure/pulumi/index.ts
git commit -m "feat(pulumi): deploy Nvidia GPU Operator with Talos extension integration"
```

---

## GATE 4: Final Verification

### Task 6.1: Full Cluster Verification

**Step 1: Node status and labels**

```bash
source .env
kubectl get nodes -L zone,tier,accelerator -o wide
```

Expected: All 7 nodes Ready with correct labels.

**Step 2: CNI verification**

```bash
source .env
cilium status
```

Expected: All agents healthy, kube-proxy replacement active.

**Step 3: Storage verification**

```bash
source .env
kubectl get sc
kubectl get pods -n longhorn-system | grep -c Running
```

Expected: Two StorageClasses (`longhorn`, `longhorn-gpu-local`). All Longhorn pods Running.

**Step 4: GPU verification**

```bash
source .env
kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
kubectl get runtimeclass nvidia
```

Expected: GPU count = 1, RuntimeClass exists.

**Step 5: Pulumi state is clean**

```bash
cd infrastructure/pulumi && pulumi preview
```

Expected: No pending changes.

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat(pulumi): complete cluster provisioning — all phases verified"
```

---

## Rollback Procedures

### Phase 2 (Node configs):
```bash
cd infrastructure/pulumi && pulumi destroy --yes
# Or revert specific config patches and re-apply
```

### Phase 3 (Cilium):
```bash
# Re-deploy Flannel
source .env
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
# Remove Cilium
helm uninstall cilium -n kube-system
```

### Phase 4 (Longhorn):
```bash
source .env
helm uninstall longhorn -n longhorn-system
kubectl delete ns longhorn-system
```

### Phase 5 (GPU):
```bash
source .env
helm uninstall gpu-operator -n gpu-operator
kubectl delete ns gpu-operator
# Revert gpu-1 to standard schematic via Pulumi config change
```
