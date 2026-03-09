# OpenRGB Server Regression Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the OpenRGB DaemonSet so LEDs reliably turn off on every cold boot by removing the `--server` container that was overwriting the init container's color config.

**Architecture:** Replace the two-container pod (init `apply-leds` + main `openrgb-server`) with a single container that runs `openrgb --noautoconnect $OPENRGB_ARGS && sleep infinity`. No server takes device ownership after config is applied, so the color persists. Verify live before updating documentation.

**Tech Stack:** kubectl, ArgoCD, OpenRGB, Hugo (blog)

**Design doc:** `docs/plans/2026-03-09-openrgb-server-regression-fix-design.md`

---

### Task 1: Fix the DaemonSet

**Files:**
- Modify: `apps/openrgb/manifests/daemonset.yaml`

**Step 1: Replace the two-container spec with a single container**

The entire `initContainers` block is removed. The `containers` block is replaced:

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

The --server container was reinitializing the HID device after the init
container applied the LED config, restoring the hardware's saved color
state (lila/green) instead of the configured color (off).

Single container applies config standalone (--noautoconnect) then sleeps.
No server takes device ownership afterward."
```

**Step 3: Push and wait for ArgoCD to sync**

```bash
git push
```

Watch ArgoCD sync the `openrgb` app:
```bash
argocd app get openrgb --port-forward --port-forward-namespace argocd
```

The old pod will be terminated and a new one created. The new pod has no init container — the single container starts, applies the config, and enters `sleep infinity`.

---

### Task 2: Verify the Fix

**Step 1: Confirm the new pod is running**

```bash
kubectl get pods -n openrgb -o wide
```

Expected: one pod on `gpu-1` with status `Running` and `READY 1/1`.

**Step 2: Check the pod logs confirm the config was applied**

```bash
kubectl logs -n openrgb <pod-name>
```

Expected output includes the udev warning (informational only) but no "Connection attempt failed" lines — and crucially, no server output.

**Step 3: Confirm LEDs are off**

Physically observe `gpu-1`. LEDs should be off.

**Step 4: Force a pod restart to verify persistence across restarts**

```bash
kubectl delete pod -n openrgb <pod-name>
```

Wait for the replacement pod to start:
```bash
kubectl get pods -n openrgb -w
```

Observe `gpu-1` — LEDs should go off again after the new pod starts.

**Step 5: Only proceed to Task 3 if LEDs are confirmed off after restart.**

If LEDs are still wrong color, stop here and investigate before touching documentation.

---

### Task 3: Update the Phase 6 Design Doc

**Files:**
- Modify: `docs/plans/2026-03-03-phase06-openrgb-led-control-design.md`

**Step 1: Update the Architecture section**

Find the two-container architecture description (around line 37-41) and replace it with:

```markdown
### Architecture

- **DaemonSet** pinned to gpu-1 via `nodeSelector: kubernetes.io/hostname: gpu-1`
- **Tolerates** the `nvidia.com/gpu=present:NoSchedule` taint
- **Single privileged container** with `/dev` hostPath mount for USB HID device access
- Runs `openrgb --noautoconnect $OPENRGB_ARGS` on startup, then `sleep infinity` as keepalive
- **ConfigMap** holds the OpenRGB CLI arguments for all devices

> **Note (2026-03-09):** The original design used an init container + `--server` main container.
> The server was added as a keepalive but caused a regression: it reinitializes the HID device
> on startup, overwriting the init container's color config with the hardware's saved state.
> Replaced with a single container using `--noautoconnect` + `sleep infinity`.
```

**Step 2: Commit**

```bash
git add docs/plans/2026-03-03-phase06-openrgb-led-control-design.md
git commit -m "docs(plans): update phase06 design doc with corrected single-container architecture"
```

---

### Task 4: Update the Phase 6 Implementation Plan

**Files:**
- Modify: `docs/plans/2026-03-03-phase06-openrgb-led-control.md`

**Step 1: Find the DaemonSet manifest task**

Locate the task that contains the two-container DaemonSet YAML (the `initContainers` + `openrgb-server` block, around lines 60-130).

**Step 2: Replace the DaemonSet YAML**

Replace the two-container spec with the single-container spec from Task 1 Step 1 above.

Also update any descriptive text that mentions "init container", "apply-leds", or "openrgb-server". Replace with the single-container description.

Add a note at the top of that task:

```markdown
> **Updated 2026-03-09:** Original design used init container + server. Replaced with single
> container — see `docs/plans/2026-03-09-openrgb-server-regression-fix-design.md`.
```

**Step 3: Commit**

```bash
git add docs/plans/2026-03-03-phase06-openrgb-led-control.md
git commit -m "docs(plans): update phase06 plan with corrected single-container daemonset"
```

---

### Task 5: Update the Phase 6 Blog Post

**Files:**
- Modify: `blog/content/posts/06-fun-stuff/index.md`

**Step 1: Find the DaemonSet architecture description**

Locate lines 65-66 and the surrounding section describing the two-container approach:
```
1. An **init container** that applies the LED configuration on startup and exits.
2. A **main container** running `openrgb --server` on port 6742...
```

**Step 2: Replace with the corrected architecture**

Replace the two-container description with:

```markdown
The pod uses a single container: it runs `openrgb --noautoconnect $OPENRGB_ARGS` to apply
the config at startup, then `sleep infinity` to keep the pod alive. The `--noautoconnect`
flag runs standalone without starting a local server — this is important because a running
server reinitializes the HID device on startup and restores the hardware's saved color state,
overwriting whatever the config applied. Standalone mode applies and exits cleanly.
```

**Step 3: Add a "Lessons Learned" or inline note about the regression**

After the architecture description, add a callout (wherever it fits naturally in the post):

```markdown
> **A note on the server:** The original implementation used an `openrgb --server` main
> container as a keepalive. This worked initially but caused an intermittent regression
> discovered during later hardware maintenance: the server's device initialization sequence
> restores the IT5701 controller's non-volatile saved state, overwriting the configured
> color. The fix — running standalone with `--noautoconnect` — is simpler and more reliable.
```

**Step 4: Update any DaemonSet YAML snippet in the post** to match the single-container spec.

**Step 5: Commit**

```bash
git add blog/content/posts/06-fun-stuff/index.md
git commit -m "docs(blog): update phase06 post with corrected single-container OpenRGB architecture"
```

---

### Task 6: Final Verification

**Step 1: Confirm all changes look clean**

```bash
git log --oneline -5
```

**Step 2: Build the blog locally to check for rendering issues**

```bash
cd blog && hugo --minify
```

Expected: `| EN` build completes with 0 errors.
