# OpenRGB LED Control for gpu-1 — Design Document

**Goal:** Control the ARGB LED fans on the gpu-1 machine (FOIFKIN F1 case, 6 PWM ARGB fans) via OpenRGB, deployed as a Kubernetes DaemonSet managed by ArgoCD. Set-and-forget: configure LED color/mode once in the repo, applied automatically on boot.

**Hardware:**
- Case: FOIFKIN F1 — 6 pre-installed PWM ARGB fans connected through an internal hub
- Motherboard: Gigabyte Z790 Eagle AX — ARGB headers, I2C/SMBus RGB controller
- Hub button: non-functional (software control required)

**Approach:** OpenRGB in a privileged DaemonSet, pinned to gpu-1, with LED config stored as a ConfigMap.

---

## Layer 1: Talos Machine Config (Phase 4 Patch)

### Kernel Modules

Load `i2c_dev` and `i2c_i801` on gpu-1 to expose the Intel Z790 SMBus controller as `/dev/i2c-*` devices.

### Kernel Parameter

Gigabyte boards have an ACPI conflict with the SMBus controller. The `acpi_enforce_resources=lax` kernel parameter bypasses this so the I2C controller is accessible.

### Patch File

`patches/phase4-gpu/05-gpu1-i2c-modules.yaml`:

```yaml
metadata:
    namespace: default
    type: ConfigPatches.omni.sidero.dev
    id: 301-gpu1-i2c-modules
    labels:
        omni.sidero.dev/cluster: frank
        omni.sidero.dev/cluster-machine: 03ff0210-04e0-05b0-ab06-300700080009
spec:
    data: |
        machine:
            kernel:
                modules:
                    - name: i2c_dev
                    - name: i2c_i801
            install:
                extraKernelArgs:
                    - acpi_enforce_resources=lax
```

Applied via: `omnictl apply -f patches/phase4-gpu/05-gpu1-i2c-modules.yaml`

Requires gpu-1 reboot to take effect.

---

## Layer 2: Kubernetes Manifests

### Container Image

`swensorm/openrgb` (server variant) — supports I2C devices and CLI profile loading.

### Architecture

- **DaemonSet** pinned to gpu-1 via `nodeSelector: kubernetes.io/hostname: gpu-1`
- **Tolerates** the `nvidia.com/gpu=present:NoSchedule` taint
- **Privileged** container with `/dev` hostPath mount for I2C device access
- **Init container** runs `openrgb $OPENRGB_ARGS` to apply LED config on startup
- **Main container** runs `openrgb --server` to keep the pod alive (re-applies on restart after reboot)
- **ConfigMap** holds the OpenRGB CLI arguments for all devices

### File Structure

```
apps/openrgb/
  manifests/
    namespace.yaml          # namespace: openrgb
    configmap.yaml          # LED color/mode/device config
    daemonset.yaml          # privileged DaemonSet
```

### ConfigMap

The `OPENRGB_ARGS` value is populated after running the discovery step (see Implementation Order below). Example:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: openrgb-config
  namespace: openrgb
data:
  OPENRGB_ARGS: >-
    -d 0 -m Static -c ff0000
    -d 1 -m Static -c ff0000
    -d 2 -m Static -c ff0000,ff0000,ff0000,ff0000
```

To change LED color: update the ConfigMap, push to git, ArgoCD syncs, pod restarts.

---

## Layer 3: ArgoCD Application

Follows the `longhorn-extras` pattern — plain manifests directory synced by ArgoCD.

### Application Template

`apps/root/templates/openrgb.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: openrgb
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/openrgb/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: openrgb
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
```

### Namespace Template

`apps/root/templates/ns-openrgb.yaml` (same pattern as `ns-longhorn.yaml`).

---

## Implementation Order

1. **Apply Talos patch** — Load I2C modules + kernel parameter on gpu-1. Reboot gpu-1.
2. **Verify I2C** — Confirm `/dev/i2c-*` devices appear on gpu-1 (privileged debug pod).
3. **Run discovery pod** — One-shot privileged pod on gpu-1 running `openrgb --list-devices`. Read logs to identify devices, zones, LEDs, and supported modes.
4. **Build manifests** — Create `apps/openrgb/manifests/` with namespace, ConfigMap (based on discovery output), and DaemonSet.
5. **Add ArgoCD app** — Create `apps/root/templates/openrgb.yaml` and `ns-openrgb.yaml`. Push to git.
6. **Verify** — ArgoCD syncs, DaemonSet starts on gpu-1, LEDs change to configured color.

Steps 1-3 are manual/interactive. Steps 4-6 are standard GitOps.

**Runtime dependency:** Step 3 (discovery) determines the exact ConfigMap contents. The LED config cannot be finalized until we see what OpenRGB detects.

---

## Safety Notes

- Gigabyte boards have reports of SMBus probing issues. OpenRGB's standard detection is safe; avoid raw `i2cdetect` dumps on unknown addresses.
- The `spd5118` kernel driver may claim I2C addresses for DDR5 RAM. If `openrgb --list-devices` shows missing controllers, this driver may need to be blocked.
- The DaemonSet runs privileged — scoped to gpu-1 only via nodeSelector.

---

## References

- [OpenRGB SMBus Access docs](https://github.com/CalcProgrammer1/OpenRGB/blob/master/Documentation/SMBusAccess.md)
- [OpenRGB supported devices](https://openrgb.org/devices.html)
- [swensorm/openrgb-docker](https://github.com/swensorm/openrgb-docker)
- [acpi_enforce_resources=lax discussion](https://bbs.archlinux.org/viewtopic.php?id=265939)
