# OpenRGB Server Regression Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the OpenRGB DaemonSet so LEDs reliably turn off on every cold boot, then merge the fix and its backstory seamlessly into the OpenRGB blog post.

**Architecture:** Replace the two-container pod (init `apply-leds` + main `openrgb-server`) with a single container that runs `openrgb --noautoconnect $OPENRGB_ARGS && sleep infinity`. Verify live before touching the blog post. The fix is a bugfix, not a new layer — the blog post absorbs it as a natural continuation of the OpenRGB story.

**Tech Stack:** kubectl, ArgoCD, OpenRGB, Hugo (blog)

**Design doc:** `docs/superpowers/specs/2026-03-09--fun--openrgb-server-regression-fix-design.md`
**Status:** Deployed

---

### Task 1: Fix the DaemonSet

**Files:**
- Modify: `apps/openrgb/manifests/daemonset.yaml`

**Step 1: Replace the entire file contents**

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

**Step 2: Commit**

```bash
git add apps/openrgb/manifests/daemonset.yaml
git commit -m "fix(openrgb): replace server+init with single container to fix LED regression

The --server container reinitializes the HID device on startup, restoring
the hardware's saved color state and overwriting the init container's config.
Single container applies --noautoconnect then sleeps. No interference."
```

**Step 3: Push and wait for ArgoCD to sync**

```bash
git push
argocd app get openrgb --port-forward --port-forward-namespace argocd
```

The old pod will terminate; a new one starts with the single-container spec.

---

### Task 2: Verify the Fix

**Step 1: Confirm the new pod is running**

```bash
kubectl get pods -n openrgb -o wide
```

Expected: one pod on `gpu-1`, status `Running`, `READY 1/1`.

**Step 2: Check logs confirm standalone execution**

```bash
kubectl logs -n openrgb <pod-name>
```

Expected: OpenRGB detection output + udev warning (informational) but **no** "Connection attempt failed" or `--server` output.

**Step 3: Confirm LEDs are off on gpu-1**

Physically observe the machine. LEDs should be off.

**Step 4: Force a pod restart to verify persistence**

```bash
kubectl delete pod -n openrgb <pod-name>
kubectl get pods -n openrgb -w   # wait for replacement to reach Running
```

Observe gpu-1 — LEDs should go off again after the new pod starts.

**Step 5: Only proceed to Task 3 if LEDs are confirmed off after the restart.**

If LEDs show any color other than off, stop here and investigate before touching the blog.

---

### Task 3: Update the OpenRGB Blog Post

**Files:**
- Modify: `blog/content/posts/06-fun-stuff/index.md`

The blog post must read as a single coherent narrative — not a patch log. Weave the fix and its discovery story naturally into the existing post. The tone is already self-deprecating and dry; keep it.

**Step 1: Replace the "The OpenRGB DaemonSet" section**

Find the line `## The OpenRGB DaemonSet` and replace everything from that heading through the line `There is no \`latest\` tag.` with the following:

````markdown
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
````

**Step 2: Update the workflow line in "ConfigMap-Driven LED Config"**

Find:
```
4. The DaemonSet pod restarts, the init container applies the new config
```

Replace with:
```
4. The DaemonSet pod restarts, the container applies the new config on startup
```

**Step 3: Commit**

```bash
git add blog/content/posts/06-fun-stuff/index.md
git commit -m "docs(blog): merge OpenRGB server regression fix into phase06 post

Replaces two-container architecture with single-container design,
explains --noautoconnect, adds 'The Server Detour' section documenting
the regression discovered during the PCIe fix session."
```

---

### Task 4: Final Verification

**Step 1: Confirm git log looks clean**

```bash
git log --oneline -5
```

**Step 2: Build the blog locally**

```bash
cd blog && hugo --minify
```

Expected: build completes with 0 errors, 0 warnings.

**Step 3: Push**

```bash
git push
```
