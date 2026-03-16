# Custom ComfyUI Docker Image — Design Spec

## Problem

The current `ghcr.io/ai-dock/comfyui:latest-cuda` image has fundamental issues that cannot be patched:

1. **Bundled services** — supervisord runs cloudflared tunnels, SSH, Jupyter, Syncthing, Caddy, service portal (none needed in K8s)
2. **Broken Caddy proxy** — template substitution fails, port 8188 never proxied to internal 18188
3. **Wrong env var names** — image uses `COMFYUI_ARGS`, not `COMFYUI_FLAGS` as documented
4. **Outdated ComfyUI** — v0.2.2 (Sept 2024), cannot load modern models (LTX-Video, Flux, etc.)
5. **Outdated PyTorch** — 2.4.1+cu121, no Blackwell/sm_120 support for RTX 5070 Ti
6. **Outdated ComfyUI-Manager** — v2.51.2, cannot download from current HuggingFace URLs
7. **Permission mismatch** — runs ComfyUI as uid 1000 but provides no fsGroup hint

## Solution

Build a lean, single-process custom image: `ghcr.io/derio-net/comfyui`.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Base image | `nvidia/cuda:12.8.0-runtime-ubuntu22.04` | CUDA 12.8 includes sm_120 (Blackwell) support |
| Python | 3.12 via deadsnakes PPA | Modern, well-supported, compatible with current PyTorch |
| PyTorch | Pinned version with sm_120 support | Stable 2.6.x if Blackwell-ready, nightly otherwise |
| ComfyUI version strategy | Pinned git ref, rebuild to update | Matches declarative-only principle |
| Custom nodes | ComfyUI-Manager baked in, nodes on PVC | Persistent installs without image rebuilds |
| Process model | Single process, no supervisord | `python main.py --listen 0.0.0.0 --port 8188` |
| Container user | `comfyui` (uid 1000, gid 1000) | Non-root, fsGroup handles PVC permissions |

## Image Architecture

### Dockerfile Layers

```
nvidia/cuda:12.8.0-runtime-ubuntu22.04
├── System deps (git, curl, libgl1, libglib2.0-0)
├── Python 3.12 (deadsnakes PPA)
├── PyTorch + torchvision + torchaudio (pip, pinned)
├── ComfyUI (git clone at pinned ref)
├── ComfyUI-Manager (git clone at pinned ref)
├── Python deps (requirements.txt from ComfyUI)
├── Non-root user: comfyui (1000:1000)
└── ENTRYPOINT: python main.py --listen 0.0.0.0 --port 8188
```

### Dockerfile Location

`apps/comfyui/docker/Dockerfile`

### Build Args

| Arg | Purpose | Example |
|-----|---------|---------|
| `COMFYUI_REF` | ComfyUI git ref (tag or commit SHA) | `v0.3.10` |
| `MANAGER_REF` | ComfyUI-Manager git ref | `2.58` |
| `PYTORCH_VERSION` | PyTorch pip version specifier | `2.6.0` |
| `CUDA_VERSION_PIP` | CUDA version for PyTorch pip index | `cu128` |

## Volume Strategy

Two Longhorn-backed PVCs:

| PVC | Mount Path | Purpose | Size | Access |
|-----|-----------|---------|------|--------|
| `comfyui-models` (existing) | `/app/models` | Checkpoints, LoRAs, VAEs, upscalers | 100Gi | RWO |
| `comfyui-custom-nodes` (new) | `/app/custom_nodes` | Manager-installed custom nodes | 10Gi | RWO |

### Path Migration

The existing `comfyui-models` PVC data is preserved — only the mount path changes from `/opt/ComfyUI/models` (ai-dock) to `/app/models` (our image). The PVC content is unchanged.

### Output / Input

Ephemeral (in-container). Generated images are downloaded from the UI. A third PVC can be added later if persistent output is needed.

## CI/CD

### GitHub Actions Workflow

File: `.github/workflows/build-comfyui.yml`

**Triggers:**
- Push to `main` when `apps/comfyui/docker/**` changes
- `workflow_dispatch` for manual rebuilds

**Registry:** `ghcr.io/derio-net/comfyui`

**Tag strategy:**
- Composite: `comfyui-<comfyui-version>-pt<pytorch-version>-cu<cuda-version>` (e.g., `comfyui-0.3.10-pt2.6.0-cu12.8`)
- `latest` always points to the most recent build

**Build matrix:** Single target — `linux/amd64` (gpu-1 is x86_64).

### Workflow Pattern

Follows the existing `build-openrgb.yml` pattern:
- Checkout → GHCR login → Docker Buildx setup → Build and push
- Build args passed for version pinning

## Kubernetes Deployment Changes

### Deployment Manifest

```yaml
containers:
  - name: comfyui
    image: ghcr.io/derio-net/comfyui:comfyui-0.3.10-pt2.6.0-cu12.8
    ports:
      - name: http
        containerPort: 8188
        protocol: TCP
    env: []  # No ai-dock env vars needed
    volumeMounts:
      - name: models
        mountPath: /app/models
      - name: custom-nodes
        mountPath: /app/custom_nodes
```

### Key Changes from ai-dock

| Aspect | ai-dock (before) | Custom image (after) |
|--------|------------------|---------------------|
| Image | `ghcr.io/ai-dock/comfyui:latest-cuda` | `ghcr.io/derio-net/comfyui:<pinned>` |
| Port | 18188 (internal, Caddy broken) | 8188 (native) |
| Env vars | `COMFYUI_ARGS`, `WEB_ENABLE_AUTH`, `CF_QUICK_TUNNELS` | None required |
| fsGroup | 1111 (ai-dock group) | 1000 (comfyui group) |
| Processes | ~10 via supervisord | 1 (ComfyUI) |
| Volumes | 1 (models) | 2 (models + custom_nodes) |

### Probes

```yaml
startupProbe:
  httpGet:
    path: /
    port: http
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 30  # 5 min max (reduced from 10 — no supervisord overhead)
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
```

### Services

No changes. ClusterIP (`comfyui:8188`) and LoadBalancer (`comfyui-lb:8188` at `192.168.55.213`) remain the same — they already use `targetPort: http` which resolves to the named container port.

## Risk: PyTorch Blackwell Support

The critical dependency is whether PyTorch stable (2.6.x) supports sm_120. If not, we use a nightly build. The implementation plan should include a verification step:

1. Build with stable PyTorch 2.6.x + CUDA 12.8
2. Test `torch.cuda.is_available()` and `torch.cuda.get_device_capability()` inside the container on gpu-1
3. If sm_120 is not supported, rebuild with PyTorch nightly index URL

## Out of Scope

- Custom node pre-installation (handled by Manager + PVC at runtime)
- Ingress/TLS (existing Cilium L2 LB is sufficient)
- Multi-GPU support (single RTX 5070 Ti)
- Auto-update mechanisms (declarative: pin version, rebuild to update)
