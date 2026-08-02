# Phase 5: Intel iGPU (Arc) Stack for mini-{1..3}

**Tools:** `omnictl apply -f` + ArgoCD
**Status:** DONE (applied 2026-03-04)

## What This Does

1. Fixes mini node labels (`accelerator: intel-igpu`, `igpu: intel-arc`)
2. Adds Intel Arc iGPU Talos extensions (`i915` + `intel-ucode`) to mini-{1..3} image schematics via Omni (triggers rolling reboot, one node at a time)
3. Enables CDI device discovery in containerd (cluster-wide config patch, no reboot)
4. Deploys Intel's **DRA resource driver** (`resource.k8s.io/v1`, GA on this
   cluster) via ArgoCD, at `apps/intel-gpu-driver/`. It publishes a
   `ResourceSlice` per node under DeviceClass `gpu.intel.com` — **not** an
   extended resource. `gpu.intel.com/i915` does not exist; querying
   `node.status.allocatable` for it returns nothing. Workloads claim the iGPU
   with a `ResourceClaim`/`ResourceClaimTemplate` instead — see "Claiming the
   iGPU" below.

   **What this is NOT: the Intel GPU Device Plugin.** Until this document was
   corrected it described the Intel GPU Device Plugin — the pre-DRA model, in
   which a per-node plugin advertises the iGPU as an *extended resource* that
   pods then request through `resources.limits` — and pointed at a plugin app
   path that has since been removed from this repo. **That model is not
   deployed on Frank.** It is worth naming rather than hiding, because most
   Intel iGPU material online still describes it: if you find yourself
   expecting an `i915` entry under `node.status.allocatable`, or writing an
   extended-resource request into a pod's `resources.limits`, you are
   following the retired model and the pod will simply never schedule — with
   no event saying why. DRA replaced it; the claim idiom below is the
   replacement. Full history: `docs/runbooks/frank-gotchas/igpu-dra.md`.

## Prerequisites

- Phase 1 complete (mini nodes labeled — note: labels must be updated from `amd-igpu` to `intel-igpu`)
- Phase 2 complete (Cilium CNI running)

## Files

| File | Tool | Purpose |
|------|------|---------|
| `500-mini1-i915-extensions.yaml` | omnictl | Adds i915+intel-ucode to mini-1 (triggers reboot) |
| `501-mini2-i915-extensions.yaml` | omnictl | Adds i915+intel-ucode to mini-2 (triggers reboot) |
| `502-mini3-i915-extensions.yaml` | omnictl | Adds i915+intel-ucode to mini-3 (triggers reboot) |
| `05-mini-cdi-containerd.yaml` | omnictl | Enables CDI in containerd cluster-wide (no reboot) |

ArgoCD Application + values: `apps/intel-gpu-driver/`

## Apply Order

Apply extensions one node at a time to preserve control-plane quorum (all mini nodes are control-plane):

```bash
source .env_devops

# 1. Fix labels (no reboot)
omnictl apply -f patches/phase01-node-config/03-labels-mini-1.yaml
omnictl apply -f patches/phase01-node-config/03-labels-mini-2.yaml
omnictl apply -f patches/phase01-node-config/03-labels-mini-3.yaml

# 2. Extensions — one at a time, wait for Ready between each
omnictl apply -f patches/phase05-mini-config/500-mini1-i915-extensions.yaml
# kubectl get node mini-1 -w  →  wait until Ready

omnictl apply -f patches/phase05-mini-config/501-mini2-i915-extensions.yaml
# kubectl get node mini-2 -w  →  wait until Ready

omnictl apply -f patches/phase05-mini-config/502-mini3-i915-extensions.yaml
# kubectl get node mini-3 -w  →  wait until Ready

# 3. CDI containerd patch (cluster-wide, containerd restarts, no reboot)
omnictl apply -f patches/phase05-mini-config/05-mini-cdi-containerd.yaml
```

Then push to git and sync ArgoCD:

```bash
git push
source .env
argocd app sync root
argocd app sync intel-gpu-driver
```

## Verify

```bash
source .env
# Extensions
talosctl -n 192.168.55.21 get extensions  # i915, intel-ucode, iscsi-tools
talosctl -n 192.168.55.21 ls /dev/dri     # card0, renderD128

# DRA: driver pods and ResourceSlices. Do NOT look in node.status.allocatable —
# that is the retired Intel GPU Device Plugin model, not deployed here.
kubectl get pods -n intel-gpu-resource-driver -o wide
kubectl get resourceslice -o wide
kubectl get deviceclass
```

## Claiming the iGPU

A workload asks for the device with a `ResourceClaimTemplate` (per-pod
lifecycle — no shared claim to dangle) selecting DeviceClass `gpu.intel.com`,
then references it from a container's `resources.claims`. This is the real
shape in use on the cluster (`apps/ovms-retrieval/manifests/`):

```yaml
# resourceclaimtemplate.yaml
apiVersion: resource.k8s.io/v1
kind: ResourceClaimTemplate
metadata:
  name: ovms-igpu
  namespace: retrieval
spec:
  spec:
    devices:
      requests:
        - name: gpu
          exactly:
            deviceClassName: gpu.intel.com
            allocationMode: ExactCount
            count: 1
```

```yaml
# deployment.yaml (excerpt)
spec:
  template:
    spec:
      resourceClaims:
        - name: igpu
          resourceClaimTemplateName: ovms-igpu
      containers:
        - name: ovms
          resources:
            claims:
              - name: igpu
```

**No `capacity` selector.** The ResourceSlice advertises `capacity.memory:
"0"` — the iGPU has no dedicated VRAM, it borrows the node's 64 GB via i915 —
so a claim that requests GPU memory can never be satisfied; select the device
and nothing else, and use the container's `resources.limits.memory` as the
real backstop. `/dev/dri` arrives `crw-rw-rw- root:root`, so no
`supplementalGroups` render-GID hunting is needed. Full detail (including the
CDI-does-not-auto-inject negative control):
`docs/runbooks/frank-gotchas/igpu-dra.md`.

## Rollback

```bash
# Remove Intel GPU Resource Driver (DRA)
source .env
argocd app delete intel-gpu-driver --cascade

# Remove CDI containerd patch
source .env_devops
omnictl delete configpatch 303-cluster-cdi-containerd

# Remove i915 extensions (triggers reboots)
omnictl delete extensionsconfiguration 500-mini1-i915-extensions
omnictl delete extensionsconfiguration 501-mini2-i915-extensions
omnictl delete extensionsconfiguration 502-mini3-i915-extensions
```
