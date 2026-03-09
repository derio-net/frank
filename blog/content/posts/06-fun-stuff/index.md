---
title: "Fun Stuff — Controlling Case LEDs from Kubernetes"
date: 2026-03-06
draft: false
tags: ["openrgb", "hardware"]
summary: "The most over-engineered RGB setup — controlling ARGB case fans from a Kubernetes DaemonSet via USB HID."
weight: 7
cover:
  image: cover.png
  alt: "Frank the cluster monster admiring his RGB-lit fans in a mirror"
  relative: true
---

Every serious infrastructure project needs a completely unnecessary feature. This is ours: controlling the ARGB LED fans on gpu-1 from a Kubernetes DaemonSet, managed by ArgoCD, triggered by a git push. GitOps for RGB. Because we have standards.

## The Hardware

The gpu-1 node lives in a FOIFKIN F1 case, which ships with six pre-installed PWM ARGB fans connected through an internal hub. The hub has a button on it, but that button does nothing useful in a headless rack environment. The fans light up on boot in whatever rainbow pattern the hub feels like, and they stay that way forever unless you take software control.

The motherboard is a Gigabyte Z790 Eagle AX. Buried on it is an ITE IT5701 USB RGB controller (vendor `048D`, product `5702`) that manages the motherboard's addressable LED headers — and therefore the fans connected through the hub. This controller exposes itself as a USB HID device at `/dev/hidraw0`, which turns out to be the key detail.

## USB HID vs I2C: A Brief Detour

The original plan was to use the I2C/SMBus path. Gigabyte boards typically expose their RGB controllers on the SMBus, and OpenRGB supports that route well. The plan called for loading `i2c-dev` and `i2c-i801` kernel modules via a Talos machine config patch, adding `acpi_enforce_resources=lax` as a kernel argument (Gigabyte boards need this), and probing the I2C bus.

That plan lasted about ten minutes. Talos Linux does not compile `CONFIG_I2C_CHARDEV` into the kernel, so `i2c-dev` simply cannot load. No `/dev/i2c-*` devices, no SMBus access, end of story.

Fortunately, while checking `dmesg` output for I2C clues, the USB HID device was staring right back:

```text
hid-generic 0003:048D:5702.0001: hidraw0: USB HID v1.12 Device [ITE Tech. Inc. ITE Device]
```

Talos ships with `CONFIG_HIDRAW=y` and `CONFIG_USB_HID=y` built-in. No kernel modules to load, no Talos patches required. The device is just *there*, at `/dev/hidraw0`, ready to be poked by OpenRGB. The USB HID path is also safer than I2C — no risk of accidentally probing dangerous SMBus addresses.

## Discovery

Before writing any manifests, we needed to know what OpenRGB would actually detect. A one-shot discovery pod on gpu-1 did the trick:

```bash
kubectl run openrgb-discovery --rm -it --restart=Never \
  --image=swensorm/openrgb:release_0.9 \
  --overrides='{
    "spec": {
      "nodeSelector": {"kubernetes.io/hostname": "gpu-1"},
      "tolerations": [{"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"}],
      "containers": [{
        "name": "openrgb-discovery",
        "image": "swensorm/openrgb:release_0.9",
        "command": ["/usr/app/openrgb", "--list-devices"],
        "securityContext": {"privileged": true},
        "volumeMounts": [{"name": "dev", "mountPath": "/dev"}]
      }],
      "volumes": [{"name": "dev", "hostPath": {"path": "/dev"}}]
    }
  }' -- /usr/app/openrgb --list-devices
```

This revealed one device — `Z790 EAGLE AX (IT5701-GIGABYTE)` at device index 0 — with three zones (D_LED1 Bottom, D_LED2 Top, Motherboard), eight LEDs total, and a handful of modes: Direct, Static, Breathing, Blinking, Color Cycle, and Flashing. Enough to work with.

## The OpenRGB DaemonSet

The deployment is a DaemonSet pinned to gpu-1. The architecture is a single container: it
runs `openrgb --noautoconnect $OPENRGB_ARGS` to apply the LED config at startup, then
`sleep infinity` to keep the pod alive.

The `--noautoconnect` flag is the key detail. It runs OpenRGB in standalone mode without
starting a local server. This matters because of a subtle hardware behavior: the IT5701
controller saves its last color to non-volatile memory, and when OpenRGB starts a server, the
server's device initialization sequence restores that saved state — overwriting whatever the
config just applied. Standalone mode applies the config and exits cleanly, with nothing to
undo it afterward.

The pod runs privileged with `/dev` mounted from the host, giving it access to the HID device
(currently at `/dev/hidraw2` — the device path can shift after hardware changes, but OpenRGB
uses device index `-d 0`, not the hidraw path directly). The gpu-1 node carries a
`nvidia.com/gpu=present:NoSchedule` taint, so the DaemonSet needs a matching toleration.

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: openrgb
  namespace: openrgb
spec:
  selector:
    matchLabels:
      app: openrgb
  template:
    spec:
      nodeSelector:
        kubernetes.io/hostname: gpu-1
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      containers:
        - name: openrgb
          image: swensorm/openrgb:release_0.9
          command: ["/bin/sh", "-c"]
          args:
            - |
              /usr/app/openrgb --noautoconnect $OPENRGB_ARGS
              sleep infinity
          env:
            - name: OPENRGB_ARGS
              valueFrom:
                configMapKeyRef:
                  name: openrgb-config
                  key: OPENRGB_ARGS
          securityContext:
            privileged: true
          volumeMounts:
            - name: dev
              mountPath: /dev
          resources:
            requests:
              memory: "32Mi"
              cpu: "10m"
            limits:
              memory: "128Mi"
      volumes:
        - name: dev
          hostPath:
            path: /dev
```

A note on the image: `swensorm/openrgb:release_0.9` puts the binary at `/usr/app/openrgb`,
not on the PATH. There is no `latest` tag.

### The Server Detour

The original implementation used a two-container design: an init container to apply the LED
config, and a main container running `openrgb --server` as a keepalive. It appeared to work.

It stopped appearing to work during an unrelated hardware session — reseating the RTX 5070,
resetting the CMOS battery, and rebooting the node several times. The LEDs came back as green,
then blue, then lila. Each reboot a different color. The server was the culprit: it
reinitializes the device every time the pod starts, and initialization restores the
controller's non-volatile saved state from the *last write* — which varied depending on which
OpenRGB invocation had touched it most recently.

The fix is the design above. The server was added speculatively as a keepalive and never used
as a remote control interface. `sleep infinity` does the same job without touching the device.

## ConfigMap-Driven LED Config

The entire LED configuration lives in a single ConfigMap value — the CLI arguments passed to OpenRGB:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: openrgb-config
  namespace: openrgb
data:
  # Device 0: Z790 EAGLE AX (IT5701-GIGABYTE) at /dev/hidraw0
  # Zones: D_LED1 Bottom, D_LED2 Top, Motherboard
  # 8 LEDs total. Modes: Direct, Static, Breathing, Blinking, Color Cycle, Flashing
  OPENRGB_ARGS: "-d 0 -m Static -c 000000"
```

The `-d 0` selects the device, `-m Static` sets the mode, and `-c 000000` sets the color — in this case, black (LEDs off). Change `000000` to `ff0000` for red, `00ff00` for green, or whatever you want. Swap `Static` for `Breathing` or `Color Cycle` to get fancier.

The workflow to change the LED color on a live cluster:

1. Edit the `OPENRGB_ARGS` value in `apps/openrgb/manifests/configmap.yaml`
2. Commit and push
3. ArgoCD detects the change and syncs
4. The DaemonSet pod restarts, the container applies the new config on startup
5. The fans change color

That is a five-stage pipeline to change an LED color. We could have used the button on the hub, except it does not work. So really this is the *only* option. (We tell ourselves this.)

## ArgoCD Integration

The ArgoCD side follows the same plain-manifests pattern used by `longhorn-extras` — no Helm chart, just a directory of YAML files. The Application template in the root App-of-Apps points at `apps/openrgb/manifests`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: openrgb
  namespace: argocd
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

Self-heal is enabled, so if someone manually messes with the LED config on the node, ArgoCD will restore the DaemonSet to the declared state. Your LED colors are now protected by GitOps. You are welcome.

## Was It Worth It?

Let us take stock. To control six case fans, we: ran a discovery pod, wrote a DaemonSet and a ConfigMap, registered an ArgoCD Application, set up a namespace with Pod Security Admission labels, and built a five-step CI/CD pipeline that terminates in changing an LED color.

The pod requests 10 millicores of CPU and 32Mi of memory. The ConfigMap is twelve lines long. The entire deployment exists so that the fans on one machine are black instead of rainbow.

Absolutely not worth it. But the fans look great, the pod is Synced/Healthy in ArgoCD, and if anyone ever asks whether our homelab has GitOps-managed RGB, the answer is yes.

## References

- [OpenRGB](https://openrgb.org/) — Open-source RGB lighting control across manufacturers
- [OpenRGB GitLab Repository](https://gitlab.com/CalcProgrammer1/OpenRGB) — Source code and device compatibility information
- [OpenRGB Supported Devices Wiki](https://gitlab.com/OpenRGBDevelopers/OpenRGB-Wiki) — Device detection, compatibility, and protocol documentation
- [Linux HID Subsystem](https://www.kernel.org/doc/html/latest/hid/index.html) — Kernel documentation for USB HID and hidraw devices
- [Kubernetes DaemonSet](https://kubernetes.io/docs/concepts/workloads/controllers/daemonset/) — Official DaemonSet documentation for node-level workloads
