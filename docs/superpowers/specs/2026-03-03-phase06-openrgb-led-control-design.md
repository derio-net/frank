# OpenRGB LED Control for gpu-1 — Design Document

**Goal:** Control the ARGB LED fans on the gpu-1 machine (FOIFKIN F1 case, 6 PWM ARGB fans) via OpenRGB, deployed as a Kubernetes DaemonSet managed by ArgoCD. Set-and-forget: configure LED color/mode once in the repo, applied automatically on boot.

**Hardware:**
- Case: FOIFKIN F1 — 6 pre-installed PWM ARGB fans connected through an internal hub
- Motherboard: Gigabyte Z790 Eagle AX — ITE IT5702 USB RGB controller (vendor `048D`, product `5702`)
- RGB controller interface: USB HID at `/dev/hidraw0` — no I2C/SMBus needed
- Hub button: non-functional (software control required)

**Approach:** OpenRGB in a privileged DaemonSet, pinned to gpu-1, with LED config stored as a ConfigMap.

---

## Layer 1: Talos Machine Config

**No Talos patches required.** The ITE IT5702 RGB controller is a USB HID device, and the Talos kernel has `CONFIG_HIDRAW=y` and `CONFIG_USB_HID=y` built-in. The device is already accessible at `/dev/hidraw0`.

### Discovery notes

Initial investigation attempted the I2C/SMBus path (`i2c-dev` + `i2c-i801` kernel modules), but `CONFIG_I2C_CHARDEV` is not compiled in the Talos kernel. USB HID discovery via `dmesg` revealed the ITE IT5702 controller:

```text
hid-generic 0003:048D:5702.0001: hidraw0: USB HID v1.12 Device [ITE Tech. Inc. ITE Device]
```

---

## Layer 2: Kubernetes Manifests

### Container Image

`swensorm/openrgb` (server variant) — supports USB HID devices and CLI profile loading.

### Architecture

- **DaemonSet** pinned to gpu-1 via `nodeSelector: kubernetes.io/hostname: gpu-1`
- **Tolerates** the `nvidia.com/gpu=present:NoSchedule` taint
- **Privileged** container with `/dev` hostPath mount for USB HID device access
- **Init container** runs `openrgb $OPENRGB_ARGS` to apply LED config on startup
- **Main container** runs `openrgb --server` to keep the pod alive (re-applies on restart after reboot)
- **ConfigMap** holds the OpenRGB CLI arguments for all devices

### File Structure

```
apps/openrgb/
  manifests/
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

1. **Run discovery pod** — One-shot privileged pod on gpu-1 running `openrgb --list-devices`. Read logs to identify devices, zones, LEDs, and supported modes.
2. **Build manifests** — Create `apps/openrgb/manifests/` with ConfigMap (based on discovery output) and DaemonSet.
3. **Add ArgoCD app** — Create `apps/root/templates/openrgb.yaml` and `ns-openrgb.yaml`. Push to git.
4. **Verify** — ArgoCD syncs, DaemonSet starts on gpu-1, LEDs change to configured color.

Step 1 is manual/interactive. Steps 2-4 are standard GitOps.

**Runtime dependency:** Step 1 (discovery) determines the exact ConfigMap contents. The LED config cannot be finalized until we see what OpenRGB detects.

---

## Safety Notes

- The DaemonSet runs privileged — scoped to gpu-1 only via nodeSelector.
- USB HID access is safer than I2C/SMBus — no risk of probing dangerous addresses.

---

## References

- [OpenRGB supported devices](https://openrgb.org/devices.html)
- [swensorm/openrgb-docker](https://github.com/swensorm/openrgb-docker)
- [ITE IT5702 USB RGB controller](https://github.com/CalcProgrammer1/OpenRGB)
