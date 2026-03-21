# Intel iGPU (Arc) Stack for mini-{1..3} — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable the Intel Arc iGPU (i915) on mini-{1..3} as a schedulable Kubernetes resource via Dynamic Resource Allocation (DRA), managed through the existing Omni + ArgoCD GitOps pipeline.

**Architecture:** Three-step approach: (1) Omni `ExtensionsConfiguration` patches add `i915` and `intel-ucode` Talos extensions to each mini node's image schematic, triggering a rolling reboot; (2) an Omni `ConfigPatch` enables CDI device discovery in containerd (cluster-wide, harmless on other nodes); (3) the Intel GPU Resource Driver (DRA) runs as a kubelet plugin DaemonSet via ArgoCD, exposing GPUs via `ResourceSlice` objects for Kubernetes DRA scheduling. Workloads use `ResourceClaim` instead of `resources.limits` — enabling fine-grained, multitenant GPU sharing.

**Tech Stack:** `omnictl` (Talos/Omni patches), ArgoCD GitOps, Intel GPU Resource Driver Helm chart (`intel/intel-gpu-resource-driver`, K8s DRA GA since 1.32)

**Why DRA over device plugin:** K8s 1.35 has DRA GA. DRA provides namespace-scoped `ResourceClaim` objects, quota integration, and fine-grained sharing — essential for future multitenancy.

**Note on iGPU workloads:** Intel Arc iGPUs share system RAM (no dedicated VRAM), making them unsuitable for LLM inference where memory bandwidth is the bottleneck. Their strengths are media/vision workloads: hardware video transcode (Quick Sync), object detection (OpenVINO/Frigate), computer vision, and OpenCL compute. LLM inference runs on gpu-1's RTX 5070 via the Ollama + LiteLLM stack (see `docs/superpowers/specs/2026-03-09--infer--ollama-litellm-design.md`).

**Prereqs:** All commands assume `source .env` (KUBECONFIG) or `source .env_devops` (OMNI) has been run. Layer 1 (node labels) and Layer 2 (Cilium) must be complete.

---

## Differences from Nvidia GPU Layer

| Aspect | Nvidia (GPU layer) | Intel Arc (GPU layer — mini nodes) |
|--------|-------------------|----------------------|
| Extensions | nvidia-container-toolkit, nvidia-open-gpu-kernel-modules | i915, intel-ucode |
| Kernel modules patch | Yes (loads nvidia, nvidia_uvm, etc.) | Not needed (i915 loaded by extension) |
| CDI containerd patch | Not needed | Yes (required for CDI device enumeration) |
| Helm chart | nvidia/gpu-operator | intel/intel-gpu-resource-driver |
| Namespace | gpu-operator | intel-gpu-resource-driver |
| K8s scheduling | Device plugin (`resources.limits`) | DRA (`ResourceClaim` / `ResourceClaimTemplate`) |

---

## Label Discrepancy — Read Before Starting

The existing label patches in `patches/phase01-node-config/03-labels-mini-*.yaml` set `accelerator: amd-igpu` and `igpu: radeon-780m`. These are incorrect for machines running Intel Ultra 5 225H with Arc iGPU. **Task 1 corrects them.** If you're unsure about the hardware, first run:

```bash
source .env
kubectl get node mini-1 -o json | jq '.status.nodeInfo'
# Look for: "architecture", vendor info in kernel version string
talosctl -n 192.168.55.21 get extensions
# To see what extensions are currently active
```

---

## Task 1: Fix mini node labels (amd-igpu → intel-igpu)

**Files:**
- Modify: `patches/phase01-node-config/03-labels-mini-1.yaml`
- Modify: `patches/phase01-node-config/03-labels-mini-2.yaml`
- Modify: `patches/phase01-node-config/03-labels-mini-3.yaml`

**Step 1: Update labels in all three files**

Change these two fields in each file (same change for all three):

```yaml
        machine:
            nodeLabels:
                zone: core
                tier: standard
                accelerator: intel-igpu    # was: amd-igpu
                igpu: intel-arc            # was: radeon-780m
```

**Step 2: Apply updated labels (no reboot — labels are hot-applied)**

```bash
source .env_devops
omnictl apply -f patches/phase01-node-config/03-labels-mini-1.yaml
omnictl apply -f patches/phase01-node-config/03-labels-mini-2.yaml
omnictl apply -f patches/phase01-node-config/03-labels-mini-3.yaml
```

**Step 3: Verify labels**

```bash
source .env
kubectl get nodes -l accelerator=intel-igpu --show-labels
# Expected: mini-1, mini-2, mini-3 listed
```

**Step 4: Commit**

```bash
git add patches/phase01-node-config/03-labels-mini-1.yaml \
        patches/phase01-node-config/03-labels-mini-2.yaml \
        patches/phase01-node-config/03-labels-mini-3.yaml
git commit -m "fix(mini): update iGPU labels from AMD to Intel Arc"
```

---

## Task 2: Create Omni ExtensionsConfiguration patches for i915

**Files:**
- Delete: `patches/phase05-mini-config/mini-extensions.yml` (wrong format — Talos Image Factory schematic, not Omni resource)
- Create: `patches/phase05-mini-config/500-mini1-i915-extensions.yaml`
- Create: `patches/phase05-mini-config/501-mini2-i915-extensions.yaml`
- Create: `patches/phase05-mini-config/502-mini3-i915-extensions.yaml`

**NOTE:** Per-machine `ExtensionsConfiguration` **overrides** (does NOT merge with) the cluster-wide `400-cluster-iscsi-tools` config. `iscsi-tools` must be included here to avoid dropping it from mini nodes (same reason as layer 04's Nvidia patch).

**Step 1: Delete the draft file (wrong format)**

```bash
git rm patches/phase05-mini-config/mini-extensions.yml
```

**Step 2: Create mini-1 extension patch**

`patches/phase05-mini-config/500-mini1-i915-extensions.yaml`:
```yaml
## Add Intel Arc iGPU extensions to mini-1's Talos image schematic
## NOTE: This triggers an image rebuild and reboot of mini-1
## Includes iscsi-tools to prevent overriding the cluster-wide extension config
metadata:
    namespace: default
    type: ExtensionsConfigurations.omni.sidero.dev
    id: 500-mini1-i915-extensions
    labels:
        omni.sidero.dev/cluster: frank
        omni.sidero.dev/cluster-machine: ce4d0d52-6c10-bdc9-746c-88aedd67681b
spec:
    extensions:
        - siderolabs/iscsi-tools
        - siderolabs/i915
        - siderolabs/intel-ucode
```

**Step 3: Create mini-2 extension patch**

`patches/phase05-mini-config/501-mini2-i915-extensions.yaml`:
```yaml
## Add Intel Arc iGPU extensions to mini-2's Talos image schematic
## NOTE: This triggers an image rebuild and reboot of mini-2
## Includes iscsi-tools to prevent overriding the cluster-wide extension config
metadata:
    namespace: default
    type: ExtensionsConfigurations.omni.sidero.dev
    id: 501-mini2-i915-extensions
    labels:
        omni.sidero.dev/cluster: frank
        omni.sidero.dev/cluster-machine: 6ea7c1c6-6ba6-b59d-c77a-88aedd676447
spec:
    extensions:
        - siderolabs/iscsi-tools
        - siderolabs/i915
        - siderolabs/intel-ucode
```

**Step 4: Create mini-3 extension patch**

`patches/phase05-mini-config/502-mini3-i915-extensions.yaml`:
```yaml
## Add Intel Arc iGPU extensions to mini-3's Talos image schematic
## NOTE: This triggers an image rebuild and reboot of mini-3
## Includes iscsi-tools to prevent overriding the cluster-wide extension config
metadata:
    namespace: default
    type: ExtensionsConfigurations.omni.sidero.dev
    id: 502-mini3-i915-extensions
    labels:
        omni.sidero.dev/cluster: frank
        omni.sidero.dev/cluster-machine: d1f01c97-d17e-e3ef-12ee-88aedd6768b6
spec:
    extensions:
        - siderolabs/iscsi-tools
        - siderolabs/i915
        - siderolabs/intel-ucode
```

**Step 5: Commit**

```bash
git add patches/phase05-mini-config/500-mini1-i915-extensions.yaml \
        patches/phase05-mini-config/501-mini2-i915-extensions.yaml \
        patches/phase05-mini-config/502-mini3-i915-extensions.yaml
git commit -m "feat(mini): add Omni i915+intel-ucode extension patches for mini-{1..3}"
```

---

## Task 3: Apply extensions (triggers rolling reboot of mini nodes)

**Files:** None (cluster operations only)

**WARNING:** Each extension apply triggers an image rebuild and reboot. Apply one node at a time to maintain control-plane quorum (all three mini nodes are control-plane nodes — losing quorum means the cluster becomes read-only).

**Step 1: Apply mini-1 and wait for Ready**

```bash
source .env_devops
omnictl apply -f patches/phase05-mini-config/500-mini1-i915-extensions.yaml

source .env
kubectl get node mini-1 -w
# Wait until STATUS = Ready (may take 3–5 minutes for reboot)
```

**Step 2: Verify mini-1 extensions loaded**

```bash
source .env
talosctl -n 192.168.55.21 get extensions
# Expected: iscsi-tools, i915, intel-ucode listed

talosctl -n 192.168.55.21 ls /dev/dri
# Expected: card0, renderD128 (or similar)
# If /dev/dri is missing: extension not loaded — check talosctl dmesg for errors
```

**Step 3: Apply mini-2 and wait for Ready**

```bash
source .env_devops
omnictl apply -f patches/phase05-mini-config/501-mini2-i915-extensions.yaml

source .env
kubectl get node mini-2 -w
# Wait until STATUS = Ready
```

**Step 4: Verify mini-2**

```bash
source .env
talosctl -n 192.168.55.22 get extensions
talosctl -n 192.168.55.22 ls /dev/dri
```

**Step 5: Apply mini-3 and wait for Ready**

```bash
source .env_devops
omnictl apply -f patches/phase05-mini-config/502-mini3-i915-extensions.yaml

source .env
kubectl get node mini-3 -w
# Wait until STATUS = Ready
```

**Step 6: Verify mini-3**

```bash
source .env
talosctl -n 192.168.55.23 get extensions
talosctl -n 192.168.55.23 ls /dev/dri
```

---

## Task 4: Create and apply CDI containerd patch

**Files:**
- Create: `patches/phase05-mini-config/05-mini-cdi-containerd.yaml`

CDI (Container Device Interface) must be enabled in containerd so the Intel GPU Device Plugin can inject `/dev/dri` devices into pods. This patch is applied cluster-wide — it's harmless on nodes without Intel GPU (containerd just finds no CDI devices to enumerate).

**Note:** This does NOT require a node reboot. Talos will restart containerd after applying.

**Step 1: Create the patch file**

`patches/phase05-mini-config/05-mini-cdi-containerd.yaml`:
```yaml
## Enable CDI device discovery in containerd for Intel GPU Device Plugin
## Applied cluster-wide (harmless on nodes without Intel GPU)
## Does NOT require a node reboot — containerd restarts automatically
metadata:
    namespace: default
    type: ConfigPatches.omni.sidero.dev
    id: 303-cluster-cdi-containerd
    labels:
        omni.sidero.dev/cluster: frank
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

**Step 2: Apply the patch**

```bash
source .env_devops
omnictl apply -f patches/phase05-mini-config/05-mini-cdi-containerd.yaml
```

**Step 3: Verify containerd restarted (wait ~30s)**

```bash
source .env
talosctl -n 192.168.55.21 services
# Look for containerd — it should show a recent start time
# All nodes should come back healthy (no reboot, just service restart)
kubectl get nodes
# Expected: all 7 nodes still Ready
```

**Step 4: Commit**

```bash
git add patches/phase05-mini-config/05-mini-cdi-containerd.yaml
git commit -m "feat(mini): enable CDI containerd support for Intel GPU Device Plugin"
```

---

## Task 5: Create phase05 README

**Files:**
- Create: `patches/phase05-mini-config/README.md`

`patches/phase05-mini-config/README.md`:
```markdown
# Intel iGPU (Arc) Stack for mini-{1..3}

**Tools:** `omnictl apply -f` + ArgoCD
**Status:** TODO

## What This Does

1. Fixes mini node labels (`accelerator: intel-igpu`, `igpu: intel-arc`)
2. Adds Intel Arc iGPU Talos extensions (`i915` + `intel-ucode`) to mini-{1..3} image schematics (triggers rolling reboot, one node at a time)
3. Enables CDI device discovery in containerd (cluster-wide config patch, no reboot)
4. Deploys the Intel GPU Device Plugin via ArgoCD to expose `gpu.intel.com/i915` as a schedulable resource

## Prerequisites

- Layer 1 complete (mini nodes labeled)
- Layer 2 complete (Cilium CNI running)
- Layer 3 complete (Longhorn running — not strictly required but keeps cluster stable)

## Files

| File | Tool | Purpose |
|------|------|---------|
| `500-mini1-i915-extensions.yaml` | omnictl | Adds i915+intel-ucode to mini-1 (triggers reboot) |
| `501-mini2-i915-extensions.yaml` | omnictl | Adds i915+intel-ucode to mini-2 (triggers reboot) |
| `502-mini3-i915-extensions.yaml` | omnictl | Adds i915+intel-ucode to mini-3 (triggers reboot) |
| `05-mini-cdi-containerd.yaml` | omnictl | Enables CDI in containerd (cluster-wide, no reboot) |

ArgoCD Application and values: `apps/intel-gpu-plugin/`

## Apply Order

1. Fix labels (Task 1) — no reboot
2. Apply extension patches one at a time (Tasks 2–3) — one reboot per node
3. Apply CDI containerd patch (Task 4) — containerd restart only
4. Push to git, sync `intel-gpu-plugin` ArgoCD app (Task 6)

See `docs/superpowers/plans/2026-03-04-intel-igpu-stack-mini.md` for full step-by-step commands.

## Rollback

```bash
# Remove Intel GPU Device Plugin via ArgoCD
source .env
argocd app delete intel-gpu-plugin --cascade

# Remove CDI containerd patch
source .env_devops
omnictl delete configpatch 303-cluster-cdi-containerd

# Remove i915 extensions (triggers reboots, one per node)
omnictl delete extensionsconfiguration 500-mini1-i915-extensions
omnictl delete extensionsconfiguration 501-mini2-i915-extensions
omnictl delete extensionsconfiguration 502-mini3-i915-extensions
```
```

**Step 1: Commit**

```bash
git add patches/phase05-mini-config/README.md
git commit -m "docs(mini): add phase05 README for Intel iGPU stack"
```

---

## Task 6: ArgoCD — Intel GPU Resource Driver (DRA)

**Files:**
- Create: `apps/intel-gpu-driver/values.yaml`
- Create: `apps/root/templates/intel-gpu-driver.yaml`

These files are already created at the versions below (chart `0.7.0` confirmed via `helm search repo`).

`apps/intel-gpu-driver/values.yaml`:
```yaml
# Intel GPU Resource Driver — DRA driver for mini-{1..3} Intel Arc iGPU
# Workloads use ResourceClaim / ResourceClaimTemplate instead of resources.limits

kubeletPlugin:
  nodeSelector:
    accelerator: intel-igpu
  # Default tolerations already cover control-plane nodes (mini-{1..3} are control-plane)

# Node Feature Discovery not needed — labels managed via Omni/Talos directly
nfd:
  enabled: false
```

`apps/root/templates/intel-gpu-driver.yaml`:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: intel-gpu-driver
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://intel.github.io/helm-charts
      chart: intel-gpu-resource-driver
      targetRevision: "0.7.0"
      helm:
        releaseName: intel-gpu-driver
        valueFiles:
          - $values/apps/intel-gpu-driver/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: intel-gpu-resource-driver
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

### Step 1: Commit

```bash
git add apps/intel-gpu-driver/values.yaml \
        apps/root/templates/intel-gpu-driver.yaml
git commit -m "feat(mini): add ArgoCD DRA app for Intel GPU Resource Driver"
```

### Step 2: Push and sync

```bash
git push

source .env
argocd app sync root           # re-renders App-of-Apps to pick up new Application
argocd app sync intel-gpu-driver
argocd app get intel-gpu-driver
# Expected: Synced / Healthy
```

---

## Task 7: Verify end-to-end

**Files:** None (verification only)

**NOTE:** DRA is fundamentally different from device plugins. GPU resources do NOT appear in `node.status.allocatable`. Instead, the driver publishes `ResourceSlice` objects (one per node) listing available devices. Workloads request them via `ResourceClaim`.

**Step 1: Check driver pods are running on mini nodes**

```bash
source .env
kubectl get pods -n intel-gpu-resource-driver -o wide
# Expected: 3 kubelet-plugin pods (one per mini node), all Running
```

**Step 2: Check ResourceSlices — driver has discovered GPUs**

```bash
source .env
kubectl get resourceslice -o wide
# Expected: one ResourceSlice per mini node, driver=gpu.intel.com
# Each slice should list the i915 device for that node

kubectl get resourceslice -o json | jq '.items[] | {node: .spec.nodeName, devices: [.spec.devices[].name]}'
# Expected: mini-1, mini-2, mini-3 each with an intel GPU device
```

**Step 3: Check DeviceClass was created**

```bash
source .env
kubectl get deviceclass
# Expected: a DeviceClass named something like gpu.intel.com
# This is what ResourceClaims reference to request an Intel GPU
```

**Step 4: Smoke test — create a ResourceClaim and a test pod**

```bash
source .env

# Get the exact DeviceClass name first
DEVICE_CLASS=$(kubectl get deviceclass -o jsonpath='{.items[0].metadata.name}')
echo "DeviceClass: $DEVICE_CLASS"

kubectl apply -f - <<EOF
apiVersion: resource.k8s.io/v1beta1
kind: ResourceClaim
metadata:
  name: intel-gpu-test-claim
  namespace: default
spec:
  devices:
    requests:
    - name: gpu
      deviceClassName: ${DEVICE_CLASS}
---
apiVersion: v1
kind: Pod
metadata:
  name: intel-gpu-test
  namespace: default
spec:
  nodeSelector:
    accelerator: intel-igpu
  resourceClaims:
  - name: gpu
    resourceClaimName: intel-gpu-test-claim
  containers:
  - name: test
    image: ubuntu:22.04
    command: ["sh", "-c", "ls -la /dev/dri && echo GPU OK && sleep 5"]
    resources:
      claims:
      - name: gpu
  restartPolicy: Never
EOF

kubectl wait pod/intel-gpu-test --for=condition=Succeeded --timeout=60s
kubectl logs intel-gpu-test
# Expected: lists /dev/dri/card0 and renderD128, prints "GPU OK"

# Cleanup
kubectl delete pod intel-gpu-test
kubectl delete resourceclaim intel-gpu-test-claim
```

**Step 5: Confirm ResourceClaim allocation shows the bound node**

```bash
source .env
# During Step 4, while pod is running:
kubectl get resourceclaim intel-gpu-test-claim -o json | jq '.status.allocation.devices.results'
# Expected: shows the allocated device and node
```

**Step 6: (Reference) How workloads will request GPUs going forward**

With otwld/ollama-helm and `ollama.gpu.draEnabled: true`, the chart handles ResourceClaimTemplate creation automatically. The pod spec will look like this (the chart generates it):

```yaml
resourceClaims:
  - name: gpu
    resourceClaimTemplateName: ollama-gpu-claim-template
containers:
  - name: ollama
    resources:
      claims:
        - name: gpu
```

No `resources.limits` with device plugin resource names. The DRA scheduler extension handles placement.
