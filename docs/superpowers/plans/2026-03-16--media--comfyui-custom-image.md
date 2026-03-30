# Custom ComfyUI Docker Image Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the broken ai-dock ComfyUI image with a lean, single-process custom image (`ghcr.io/derio-net/comfyui`) that runs modern ComfyUI on PyTorch with CUDA 12.8 / Blackwell sm_120 support.

**Architecture:** A custom Dockerfile builds ComfyUI with pinned versions of PyTorch, ComfyUI, and ComfyUI-Manager on an NVIDIA CUDA 12.8 base. A GitHub Actions workflow builds and pushes the image to GHCR on changes to `apps/comfyui/docker/`. The existing Kubernetes manifests are updated to use the new image, correct the port/fsGroup, and add a second PVC for custom nodes.

**Tech Stack:** Docker, GitHub Actions, NVIDIA CUDA 12.8, Python 3.12, PyTorch 2.6.x, Kubernetes manifests, Longhorn PVCs

**Spec:** `docs/superpowers/specs/2026-03-16--media--comfyui-custom-image-design.md`

**Layer:** media (Media Generation Stack) — this is an extension/bugfix of the media layer, not a new layer.

**Blog update required:** After deployment, retroactively update the Media Generation blog post at `blog/content/building/16-media-generation/index.md` to document the custom image replacement (per CLAUDE.md convention for layer extensions).
**Status:** Deployed

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `apps/comfyui/docker/Dockerfile` | Multi-layer image: CUDA base → Python 3.12 → PyTorch → ComfyUI → Manager → entrypoint |
| Create | `apps/comfyui/docker/entrypoint.sh` | Seeds ComfyUI-Manager from baked-in default to PVC on first boot, then exec's ComfyUI |
| Create | `.github/workflows/build-comfyui.yml` | CI: builds and pushes image to GHCR on push to `apps/comfyui/docker/**` or manual dispatch |
| Create | `apps/comfyui/manifests/pvc-custom-nodes.yaml` | 10Gi Longhorn PVC for ComfyUI-Manager custom node installs |
| Modify | `apps/comfyui/manifests/deployment.yaml` | Switch image, port, fsGroup, env vars, volume mounts, probe thresholds |

---

## Chunk 1: Docker Image

### Task 1: Create the entrypoint script

**Files:**
- Create: `apps/comfyui/docker/entrypoint.sh`

- [x] **Step 1: Write the entrypoint script**

This script seeds ComfyUI-Manager into the `custom_nodes` PVC on first boot (since the PVC mount shadows the baked-in path), then exec's ComfyUI.

```bash
#!/bin/bash
set -e

# Seed ComfyUI-Manager into the PVC if not already present.
# The image bakes Manager into /app/default_custom_nodes/ComfyUI-Manager,
# but /app/custom_nodes is a PVC mount that shadows any baked-in content.
if [ ! -d /app/custom_nodes/ComfyUI-Manager ]; then
  echo "First boot: seeding ComfyUI-Manager into custom_nodes PVC..."
  cp -r /app/default_custom_nodes/ComfyUI-Manager /app/custom_nodes/
fi

exec python main.py "$@"
```

- [x] **Step 2: Set executable bit and commit**

```bash
chmod +x apps/comfyui/docker/entrypoint.sh
git add apps/comfyui/docker/entrypoint.sh
git commit -m "feat(comfyui): add entrypoint script for custom image

Seeds ComfyUI-Manager from baked-in default to PVC on first boot,
then exec's ComfyUI as PID 1."
```

---

### Task 2: Create the Dockerfile

**Files:**
- Create: `apps/comfyui/docker/Dockerfile`

- [x] **Step 1: Write the Dockerfile**

Key design choices (from spec):
- `nvidia/cuda:12.8.0-devel-ubuntu22.04` base — `devel` needed for custom nodes that compile CUDA extensions at install time; 12.8 includes sm_120 for RTX 5070 Ti Blackwell arch
- PyTorch installed before ComfyUI clone so the 2+ GB PyTorch layer caches across ComfyUI version bumps
- ComfyUI-Manager baked into `/app/default_custom_nodes/` (not `/app/custom_nodes/`) because `/app/custom_nodes` will be a PVC mount
- Non-root `comfyui` user (1000:1000) — `fsGroup: 1000` in the pod spec handles PVC permissions

```dockerfile
FROM nvidia/cuda:12.8.0-devel-ubuntu22.04

# Version pins — passed as build args from CI, with defaults for local builds
ARG COMFYUI_REF=v0.3.10
ARG MANAGER_REF=2.58
ARG PYTORCH_VERSION=2.6.0
ARG CUDA_VERSION_PIP=cu128

# Prevent interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive

# ── System dependencies ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl \
        libgl1 libglib2.0-0 \
        software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3.12-dev \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python \
    && rm -rf /var/lib/apt/lists/*

# ── PyTorch (cached layer — only rebuilds on version/CUDA change) ───
RUN pip install --no-cache-dir \
    torch==${PYTORCH_VERSION} \
    torchvision \
    torchaudio \
    --index-url https://download.pytorch.org/whl/${CUDA_VERSION_PIP}

# ── ComfyUI ──────────────────────────────────────────────────────────
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app \
    && cd /app && git checkout ${COMFYUI_REF}

WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt

# ── ComfyUI-Manager (baked into default location) ───────────────────
RUN git clone https://github.com/ltdrdata/ComfyUI-Manager.git \
        /app/default_custom_nodes/ComfyUI-Manager \
    && cd /app/default_custom_nodes/ComfyUI-Manager \
    && git checkout ${MANAGER_REF} \
    && if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# ── Non-root user ───────────────────────────────────────────────────
RUN groupadd -g 1000 comfyui \
    && useradd -u 1000 -g comfyui -d /app -s /bin/bash comfyui \
    && chown -R comfyui:comfyui /app

# ── Entrypoint ──────────────────────────────────────────────────────
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER comfyui

EXPOSE 8188

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--listen", "0.0.0.0", "--port", "8188"]
```

- [x] **Step 2: Commit**

```bash
git add apps/comfyui/docker/Dockerfile
git commit -m "feat(comfyui): add custom Dockerfile

CUDA 12.8 base with Python 3.12, PyTorch 2.6.x, pinned ComfyUI
and Manager refs. Single-process, non-root, no supervisord."
```

---

## Chunk 2: CI/CD

### Task 3: Create the GitHub Actions workflow

**Files:**
- Create: `.github/workflows/build-comfyui.yml`

- [x] **Step 1: Write the workflow**

Follows the existing `build-openrgb.yml` pattern. Version pins are workflow-level `env` vars so updating versions is a single-line change (no Dockerfile edit needed for version bumps).

Tag strategy: composite tag `comfyui-<comfyui>-pt<pytorch>-cu<cuda>` for pinned deployments + `latest` for convenience.

```yaml
name: Build ComfyUI Image

on:
  push:
    branches: [main]
    paths:
      - "apps/comfyui/docker/**"
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/comfyui
  COMFYUI_REF: "v0.3.10"
  MANAGER_REF: "2.58"
  PYTORCH_VERSION: "2.6.0"
  CUDA_VERSION_PIP: "cu128"

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: apps/comfyui/docker
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:comfyui-${{ env.COMFYUI_REF }}-pt${{ env.PYTORCH_VERSION }}-${{ env.CUDA_VERSION_PIP }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
          build-args: |
            COMFYUI_REF=${{ env.COMFYUI_REF }}
            MANAGER_REF=${{ env.MANAGER_REF }}
            PYTORCH_VERSION=${{ env.PYTORCH_VERSION }}
            CUDA_VERSION_PIP=${{ env.CUDA_VERSION_PIP }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [x] **Step 2: Commit**

```bash
git add .github/workflows/build-comfyui.yml
git commit -m "ci: add ComfyUI image build workflow

Triggers on push to apps/comfyui/docker/** or manual dispatch.
Pushes to ghcr.io/derio-net/comfyui with composite version tag."
```

---

## Chunk 3: Kubernetes Manifest Updates

### Task 4: Create the custom-nodes PVC

**Files:**
- Create: `apps/comfyui/manifests/pvc-custom-nodes.yaml`

- [x] **Step 1: Write the PVC manifest**

Follows the existing `pvc.yaml` pattern. 10Gi is sufficient for ComfyUI-Manager-installed custom nodes (Python packages + git repos).

```yaml
# Persistent storage for ComfyUI custom nodes (installed via ComfyUI-Manager)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: comfyui-custom-nodes
  namespace: comfyui
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 10Gi
```

- [x] **Step 2: Commit**

```bash
git add apps/comfyui/manifests/pvc-custom-nodes.yaml
git commit -m "feat(comfyui): add PVC for custom nodes

10Gi Longhorn volume for ComfyUI-Manager custom node installs,
mounted at /app/custom_nodes."
```

---

### Task 5: Update the Deployment manifest

**Files:**
- Modify: `apps/comfyui/manifests/deployment.yaml`

- [x] **Step 1: Update the deployment**

Changes from ai-dock to custom image:
- `image` → `ghcr.io/derio-net/comfyui:comfyui-v0.3.10-pt2.6.0-cu128`
- `containerPort` → `8188` (native, no Caddy proxy)
- Remove all `env` vars (`COMFYUI_ARGS`, `WEB_ENABLE_AUTH`, `CF_QUICK_TUNNELS`) — custom image needs none
- `fsGroup` → `1000` (comfyui user, was 1111/ai-dock)
- Models mount path → `/app/models` (was `/opt/ComfyUI/models`)
- Add `custom-nodes` volume mount at `/app/custom_nodes`
- Startup probe `failureThreshold` → `30` (5 min, was 60/10 min — no supervisord overhead)

The full updated file:

```yaml
# ComfyUI diffusion model server on gpu-1
# Starts at 0 replicas — activate via GPU Switcher
apiVersion: apps/v1
kind: Deployment
metadata:
  name: comfyui
  namespace: comfyui
  labels:
    app.kubernetes.io/name: comfyui
    app.kubernetes.io/component: server
spec:
  replicas: 0
  selector:
    matchLabels:
      app.kubernetes.io/name: comfyui
      app.kubernetes.io/component: server
  strategy:
    type: Recreate
  template:
    metadata:
      labels:
        app.kubernetes.io/name: comfyui
        app.kubernetes.io/component: server
    spec:
      nodeSelector:
        kubernetes.io/hostname: gpu-1
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      securityContext:
        fsGroup: 1000
      terminationGracePeriodSeconds: 30
      containers:
        - name: comfyui
          image: ghcr.io/derio-net/comfyui:comfyui-v0.3.10-pt2.6.0-cu128
          ports:
            - name: http
              containerPort: 8188
              protocol: TCP
          resources:
            requests:
              cpu: 4000m
              memory: 16Gi
              nvidia.com/gpu: "1"
            limits:
              memory: 24Gi
              nvidia.com/gpu: "1"
          volumeMounts:
            - name: models
              mountPath: /app/models
            - name: custom-nodes
              mountPath: /app/custom_nodes
          startupProbe:
            httpGet:
              path: /
              port: http
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /
              port: http
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /
              port: http
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
      volumes:
        - name: models
          persistentVolumeClaim:
            claimName: comfyui-models
        - name: custom-nodes
          persistentVolumeClaim:
            claimName: comfyui-custom-nodes
```

- [x] **Step 2: Verify services don't need changes**

Check that both services use `targetPort: http` (not a hardcoded port number). They do — see `apps/comfyui/manifests/service.yaml:18` and `apps/comfyui/manifests/service-lb.yaml:20`. No changes needed.

- [x] **Step 3: Commit**

```bash
git add apps/comfyui/manifests/deployment.yaml
git commit -m "feat(comfyui): switch deployment to custom image

Replaces ai-dock image with ghcr.io/derio-net/comfyui.
Changes: port 8188 (native), fsGroup 1000, /app/models mount path,
adds custom_nodes PVC mount, removes unused env vars,
reduces startup probe to 5 min."
```

---

## Chunk 4: Build, Deploy & Verify

### Task 6: Verify NVIDIA driver prerequisite

The spec requires NVIDIA driver 570.x+ on gpu-1 for CUDA 12.8 / sm_120 support. Verify this before building and deploying the new image.

- [x] **Step 1: Check host NVIDIA driver version**

```bash
kubectl exec -n ollama deploy/ollama -- nvidia-smi --query-gpu=driver_version --format=csv,noheader
```

Expected: `570.x` or higher. If the output shows a driver version below 570, **stop here** — the Talos NVIDIA extension must be updated first (separate task, out of scope for this plan).

- [x] **Step 2: Confirm sm_120 capability**

```bash
kubectl exec -n ollama deploy/ollama -- nvidia-smi --query-gpu=compute_cap --format=csv,noheader
```

Expected: `12.0` (Blackwell). If this shows a lower compute capability, the GPU is not Blackwell and the CUDA 12.8 / sm_120 justification doesn't apply (but the image will still work — sm_120 is additive).

---

### Task 7: Trigger the image build

- [x] **Step 1: Push to trigger CI**

```bash
git push origin main
```

The push includes changes to `apps/comfyui/docker/**` which triggers the `build-comfyui.yml` workflow.

- [x] **Step 2: Monitor the build**

```bash
gh run list --workflow=build-comfyui.yml --limit 1
# Watch the run (uses the latest run ID automatically)
gh run watch "$(gh run list --workflow=build-comfyui.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Expected: Build succeeds, image pushed to `ghcr.io/derio-net/comfyui:comfyui-v0.3.10-pt2.6.0-cu128` and `ghcr.io/derio-net/comfyui:latest`.

**Note:** The first build will take ~15-20 minutes due to PyTorch download (2+ GB) and CUDA compilation. Subsequent builds with the same PyTorch version will be faster thanks to GHA cache.

- [x] **Step 3: Verify image exists in registry**

```bash
# For org-owned repos (derio-net):
gh api orgs/derio-net/packages/container/comfyui/versions --jq '.[0].metadata.container.tags'
# If that 404s (personal repo), try:
# gh api user/packages/container/comfyui/versions --jq '.[0].metadata.container.tags'
```

Expected: `["comfyui-v0.3.10-pt2.6.0-cu128", "latest"]`

---

### Task 8: Verify ArgoCD sync and deployment health

- [x] **Step 1: Check ArgoCD sync status**

ArgoCD will auto-sync the manifest changes (new PVC, updated deployment). Verify:

```bash
argocd app get comfyui --port-forward --port-forward-namespace argocd
```

Expected: Synced, Healthy (with 0 replicas the deployment is healthy but idle).

- [x] **Step 2: Verify PVC was created**

```bash
kubectl get pvc -n comfyui
```

Expected output includes both:
- `comfyui-models` — 100Gi, Bound
- `comfyui-custom-nodes` — 10Gi, Bound (or Pending until first pod mounts it)

- [x] **Step 3: Activate ComfyUI via GPU Switcher**

Scale up ComfyUI to test the new image:

```bash
kubectl scale deployment comfyui -n comfyui --replicas=1
```

Or use the GPU Switcher UI at `http://192.168.55.214:8080` and click "Activate" on ComfyUI.

- [x] **Step 4: Watch pod startup**

```bash
kubectl logs -n comfyui -l app.kubernetes.io/name=comfyui -f
```

Expected log sequence:
1. `First boot: seeding ComfyUI-Manager into custom_nodes PVC...` (first run only)
2. ComfyUI startup messages (loading models, starting server)
3. `To see the GUI go to: http://0.0.0.0:8188`

- [x] **Step 5: Verify GPU/CUDA inside the container**

```bash
kubectl exec -n comfyui deploy/comfyui -- python -c "
import torch
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'Device: {torch.cuda.get_device_name(0)}')
print(f'Capability: {torch.cuda.get_device_capability(0)}')
print(f'PyTorch: {torch.__version__}')
"
```

Expected:
- `CUDA available: True`
- `Device: NVIDIA GeForce RTX 5070 Ti` (or similar)
- `Capability: (12, 0)` — sm_120 (Blackwell)
- `PyTorch: 2.6.0+cu128`

**If sm_120 is NOT reported or CUDA is unavailable:** The host NVIDIA driver on gpu-1 may be too old. Check with `kubectl exec -n comfyui deploy/comfyui -- nvidia-smi`. Driver must be 570.x+ for CUDA 12.8. If the driver is insufficient, this is a separate Talos NVIDIA extension update (out of scope for this plan).

**If PyTorch stable doesn't support sm_120:** Rebuild with nightly. Two changes required:

1. In `apps/comfyui/docker/Dockerfile`, change the PyTorch install line:

   ```dockerfile
   # Replace the stable index URL:
   RUN pip install --no-cache-dir \
       --pre torch torchvision torchaudio \
       --index-url https://download.pytorch.org/whl/nightly/${CUDA_VERSION_PIP}
   ```

2. In `.github/workflows/build-comfyui.yml`, update the version env vars:

   ```yaml
   env:
     PYTORCH_VERSION: "nightly"  # for tag only — actual version comes from nightly index
     # ... other vars unchanged
   ```

Rebuild and re-test: `gh workflow run build-comfyui.yml`

- [x] **Step 6: Access ComfyUI Web UI**

Open `http://192.168.55.213:8188` in a browser.

Expected: ComfyUI web interface loads. The default workflow should be visible. ComfyUI-Manager should be accessible from the Manager menu.

- [x] **Step 7: Deactivate ComfyUI**

Scale back to 0 when done testing:

```bash
kubectl scale deployment comfyui -n comfyui --replicas=0
```

- [x] **Step 8: Final commit (if any adjustments were needed)**

If any manifest tweaks were required during verification, commit them:

```bash
git add -A apps/comfyui/
git commit -m "fix(comfyui): adjustments from deployment verification"
git push origin main
```
