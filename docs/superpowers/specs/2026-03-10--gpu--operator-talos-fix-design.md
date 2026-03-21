# GPU Operator Talos Validation Fix — Design

**Goal:** Unblock GPU Operator DaemonSet pods on Talos Linux by creating the validation marker files that the disabled toolkit DaemonSet would normally produce.

**Layer:** gpu (extends GPU Stack)

## Problem

The NVIDIA GPU Operator v25.10.1 has hardcoded init containers in every workload DaemonSet (device-plugin, feature-discovery, dcgm-exporter, validator) that poll for `/run/nvidia/validations/toolkit-ready`:

```sh
until [ -f /run/nvidia/validations/toolkit-ready ]; do
  echo waiting for nvidia container stack to be setup; sleep 5
done
```

On Talos Linux, the NVIDIA driver and container toolkit are provided by system extensions (`nvidia-open-gpu-kernel-modules-production` and `nvidia-container-toolkit-production`), so the GPU Operator's own `toolkit` and `driver` DaemonSets are disabled (`toolkit.enabled: false`, `driver.enabled: false`). This means the toolkit DaemonSet that normally creates the `toolkit-ready` file never runs, and all downstream pods are stuck in `Init:0/N` forever.

This is a confirmed gap in the operator source code — `transformValidationInitContainer()` in `controllers/object_controls.go` removes init containers for disabled `plugin` and `cc-manager` components but **not** for `toolkit`. GitHub issue [#1460](https://github.com/NVIDIA/gpu-operator/issues/1460) requested a fix but was frozen without resolution.

## Current State

- gpu-1: PCIe Gen 4 confirmed (16.0 GT/s) after BIOS F6 update
- NVIDIA driver 570.211.01 loaded via Talos extension
- GPU Operator pods stuck: device-plugin, feature-discovery, dcgm-exporter, validator all in `Init:0/1`
- Only `node-feature-discovery-worker` runs (no toolkit-ready dependency)
- Ollama pod `Pending` — `Insufficient nvidia.com/gpu` (device-plugin never registered the GPU)

## Solution

Deploy a busybox DaemonSet that creates the validation marker files on the host filesystem, then sleeps. This is the same pattern used by [mitchross/talos-argocd-proxmox](https://github.com/mitchross/talos-argocd-proxmox).

### Validation Markers DaemonSet

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-validation-markers
  namespace: gpu-operator
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: nvidia-validation-markers
  template:
    metadata:
      labels:
        app.kubernetes.io/name: nvidia-validation-markers
    spec:
      nodeSelector:
        nvidia.com/gpu.present: "true"
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      containers:
        - name: marker
          image: busybox:1.37
          securityContext:
            privileged: true
          command: ["/bin/sh", "-c"]
          args:
            - |
              mkdir -p /host-run/nvidia/validations
              touch /host-run/nvidia/validations/driver-ready
              touch /host-run/nvidia/validations/toolkit-ready
              echo "Validation markers created"
              sleep infinity
          volumeMounts:
            - name: host-run
              mountPath: /host-run
      volumes:
        - name: host-run
          hostPath:
            path: /run
            type: Directory
```

Key properties:
- `nodeSelector: nvidia.com/gpu.present: "true"` — only targets GPU nodes (currently gpu-1)
- Tolerates the `nvidia.com/gpu:NoSchedule` taint on gpu-1
- Creates both `driver-ready` and `toolkit-ready` (some init containers check both)
- `/run` is tmpfs — files disappear on reboot, but the DaemonSet recreates them automatically
- Privileged required for hostPath `/run` write access

### ArgoCD Wiring

New `gpu-operator-extras` app following the established `-extras` pattern:

- `apps/gpu-operator-extras/manifests/validation-markers.yaml` — the DaemonSet
- `apps/root/templates/gpu-operator-extras.yaml` — Application CR (raw manifests source)

No changes to existing `apps/gpu-operator/values.yaml`.

## Alternatives Considered

**One-shot Job**: Simpler but fragile. `/run` is tmpfs, so files disappear on reboot. The Job wouldn't re-run automatically, requiring manual intervention after every gpu-1 restart.

**Re-enable `toolkit.enabled: true`**: Risky on Talos. The toolkit DaemonSet expects a mutable `/etc` to configure the container runtime. Talos has a read-only `/etc`. Could conflict with the extension-provided toolkit.

**Standalone nvidia-device-plugin**: Would bypass the validation chain entirely but loses DCGM metrics, feature discovery, and operator lifecycle management.

## Success Criteria

1. All GPU Operator DaemonSet pods on gpu-1 reach `Running`
2. `nvidia.com/gpu: 1` appears in `kubectl describe node gpu-1` allocatable resources
3. Ollama pod schedules on gpu-1 and starts serving models
4. DCGM exporter runs and GPU metrics are scrapable

## Scope

This is an extension of the GPU layer, not a new layer. File naming follows the convention: `gpu--operator-talos-fix`.
