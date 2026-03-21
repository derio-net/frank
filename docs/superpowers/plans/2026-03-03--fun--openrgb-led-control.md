# OpenRGB LED Control — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy OpenRGB as a DaemonSet on gpu-1 to control ARGB LED fans, managed by ArgoCD.

**Architecture:** Talos patch loads I2C kernel modules on gpu-1. A privileged DaemonSet runs OpenRGB, applying LED config from a ConfigMap on startup. ArgoCD manages the deployment via the existing App-of-Apps pattern (plain manifests, like `longhorn-extras`).

**Tech Stack:** omnictl (Talos patches), kubectl (discovery/verification), ArgoCD (GitOps), OpenRGB (LED control)

**Prereqs:** All commands assume `source .env` (KUBECONFIG) or `source .env_devops` (OMNI) has been run.

**Design doc:** `docs/superpowers/plans/2026-03-03-openrgb-led-control-design.md`
**Status:** Deployed

---

## Task 1: Create the Talos I2C Patch

**Files:**
- Create: `patches/phase4-gpu/05-gpu1-i2c-modules.yaml`

**Step 1: Create the patch file**

```yaml
## I2C kernel modules for gpu-1 (OpenRGB LED control)
## Loads i2c-dev and i2c-i801 for SMBus access to the Gigabyte Z790 RGB controller.
## The acpi_enforce_resources=lax kernel param is required for Gigabyte boards.
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

**Step 2: Commit**

```bash
git add patches/phase4-gpu/05-gpu1-i2c-modules.yaml
git commit -m "feat(gpu-1): add I2C kernel modules patch for OpenRGB LED control"
```

---

## Task 2: Apply the Talos Patch and Reboot gpu-1

**Files:** None (cluster operations only)

**Step 1: Apply the patch**

```bash
source .env_devops
omnictl apply -f patches/phase4-gpu/05-gpu1-i2c-modules.yaml
```

**Step 2: Wait for gpu-1 to reboot and come back Ready**

```bash
source .env
kubectl get node gpu-1 -w
# Wait until STATUS = Ready
```

**Step 3: Verify I2C modules loaded**

```bash
source .env
talosctl -n 192.168.55.31 dmesg | grep -i i2c | head -20
# Expected: messages about i2c_i801 and i2c_dev loading
```

```bash
talosctl -n 192.168.55.31 ls /dev/i2c-*
# Expected: one or more /dev/i2c-N devices listed
```

If no `/dev/i2c-*` devices appear, check `talosctl -n 192.168.55.31 dmesg | grep -i acpi` for ACPI resource conflicts.

---

## Task 3: Run OpenRGB Discovery Pod

**Files:** None (one-shot pod, not committed)

This task discovers what RGB devices OpenRGB can see on gpu-1. The output determines the ConfigMap in Task 5.

**Step 1: Run the discovery pod**

```bash
source .env
kubectl run openrgb-discovery --rm -it --restart=Never \
  --image=swensorm/openrgb:latest \
  --overrides='{
    "spec": {
      "nodeSelector": {"kubernetes.io/hostname": "gpu-1"},
      "tolerations": [{"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"}],
      "containers": [{
        "name": "openrgb-discovery",
        "image": "swensorm/openrgb:latest",
        "command": ["openrgb", "--list-devices"],
        "securityContext": {"privileged": true},
        "volumeMounts": [{"name": "dev", "mountPath": "/dev"}]
      }],
      "volumes": [{"name": "dev", "hostPath": {"path": "/dev"}}]
    }
  }' \
  -- openrgb --list-devices
```

Expected output: a list of detected RGB devices with their index, name, type, zones, LEDs, and supported modes.

**Step 2: Record the output**

Save the discovery output — you need the device indices, LED counts, and mode names for Task 5.

Example output format:
```
Device 0: Gigabyte Z790 Eagle AX
  Zones:
    Zone 0: Motherboard  LEDs: 1
  Modes: Direct Static Breathing ...
Device 1: ...
```

**If no devices detected:** Check that `/dev/i2c-*` devices exist (Task 2 Step 3). If they exist but OpenRGB finds nothing, the `spd5118` kernel driver may be claiming I2C addresses — check `openrgb --list-devices --verbose` for details.

---

## Task 4: Create ArgoCD Application Templates

**Files:**
- Create: `apps/root/templates/ns-openrgb.yaml`
- Create: `apps/root/templates/openrgb.yaml`

**Step 1: Create the namespace template**

`apps/root/templates/ns-openrgb.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: openrgb
  labels:
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/audit: privileged
    pod-security.kubernetes.io/warn: privileged
```

**Step 2: Create the Application template**

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

**Step 3: Commit**

```bash
git add apps/root/templates/ns-openrgb.yaml apps/root/templates/openrgb.yaml
git commit -m "feat(argocd): add OpenRGB Application template and namespace"
```

---

## Task 5: Create OpenRGB Manifests

**Files:**
- Create: `apps/openrgb/manifests/configmap.yaml`
- Create: `apps/openrgb/manifests/daemonset.yaml`

**Depends on:** Task 3 output (device indices, LED counts, mode names)

**Step 1: Create the ConfigMap**

`apps/openrgb/manifests/configmap.yaml`:

Replace the `OPENRGB_ARGS` value with the actual device/color/mode args based on discovery output from Task 3.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: openrgb-config
  namespace: openrgb
data:
  # Populated from Task 3 discovery output.
  # Format: openrgb CLI args, one -d/-m/-c group per device.
  # To turn LEDs off, use -m Static -c 000000.
  # To change color, update and push — ArgoCD will sync.
  OPENRGB_ARGS: >-
    -d 0 -m Static -c ff0000
```

**Step 2: Create the DaemonSet**

`apps/openrgb/manifests/daemonset.yaml`:

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: openrgb
  namespace: openrgb
  labels:
    app: openrgb
spec:
  selector:
    matchLabels:
      app: openrgb
  template:
    metadata:
      labels:
        app: openrgb
    spec:
      nodeSelector:
        kubernetes.io/hostname: gpu-1
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      initContainers:
        - name: apply-leds
          image: swensorm/openrgb:latest
          command: ["/bin/sh", "-c"]
          args:
            - |
              echo "Waiting for I2C devices..."
              sleep 5
              echo "Applying LED config: $OPENRGB_ARGS"
              openrgb $OPENRGB_ARGS
              echo "LED config applied."
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
      containers:
        - name: openrgb-server
          image: swensorm/openrgb:latest
          command: ["openrgb", "--server"]
          ports:
            - containerPort: 6742
              name: openrgb
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

**Step 3: Commit**

```bash
git add apps/openrgb/manifests/configmap.yaml apps/openrgb/manifests/daemonset.yaml
git commit -m "feat(openrgb): add DaemonSet and ConfigMap for LED control on gpu-1"
```

---

## Task 6: Push and Verify ArgoCD Sync

**Files:** None (cluster operations only)

**Step 1: Push to remote**

```bash
git push origin main
```

**Step 2: Verify ArgoCD detects the new app**

```bash
source .env
kubectl get applications -n argocd
# Expected: openrgb appears in the list
```

**Step 3: Check sync status**

```bash
kubectl get application openrgb -n argocd -o jsonpath='{.status.sync.status}'
# Expected: Synced

kubectl get application openrgb -n argocd -o jsonpath='{.status.health.status}'
# Expected: Healthy
```

**Step 4: Verify the DaemonSet is running**

```bash
kubectl get pods -n openrgb
# Expected: openrgb-XXXXX pod Running on gpu-1
```

**Step 5: Check init container logs**

```bash
kubectl logs -n openrgb -l app=openrgb -c apply-leds
# Expected: "Applying LED config: ..." followed by "LED config applied."
```

**Step 6: Visually confirm LEDs changed on gpu-1**

Look at the machine — the fans should now display the configured color.

---

## Task 7: Update Layer 4 README

**Files:**
- Modify: `patches/phase4-gpu/README.md`

**Step 1: Add I2C patch to the README**

Add an entry to the Files table and an apply section for the I2C patch, following the existing format.

**Step 2: Commit**

```bash
git add patches/phase4-gpu/README.md
git commit -m "docs: add I2C patch to phase 4 README"
```

---

## Rollback

```bash
# Remove ArgoCD app (stops the DaemonSet)
source .env
kubectl delete application openrgb -n argocd
kubectl delete ns openrgb

# Remove Talos I2C patch
source .env_devops
omnictl delete configpatch 301-gpu1-i2c-modules

# Remove files from repo
git rm apps/root/templates/openrgb.yaml apps/root/templates/ns-openrgb.yaml
git rm -r apps/openrgb/
git rm patches/phase4-gpu/05-gpu1-i2c-modules.yaml
git commit -m "revert: remove OpenRGB LED control"
git push origin main
```
