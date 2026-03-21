---
title: "Media Generation — ComfyUI and GPU Time-Sharing"
date: 2026-03-14
draft: false
tags: ["comfyui", "diffusion", "gpu", "time-sharing", "video", "image", "audio", "go"]
summary: "Running ComfyUI for video, image, and audio generation on the same GPU as Ollama — with a custom GPU Switcher dashboard to manage time-sharing."
weight: 17
cover:
  image: cover.png
  alt: "Frank the cluster monster juggling video frames and audio waves between ComfyUI and Ollama"
  relative: true
---

The cluster has one GPU. Layer 10 gave it to Ollama for LLM inference. This layer adds a second GPU consumer — ComfyUI for diffusion-based media generation — and a mechanism to share the hardware between them.

## The Constraint: One GPU, Two Workloads

The RTX 5070 Ti on gpu-1 has 16GB of GDDR7 VRAM. That's enough for one heavy workload at a time, but not two simultaneously. LTX-2.3 (the video diffusion model) needs 8-12GB of VRAM for inference. Ollama with a 9B parameter model uses 6-7GB. Running both means neither has enough memory for useful context or batch sizes.

Time-sharing is the answer: scale one workload to zero replicas, let the other use the full GPU, then swap when needed. Both Deployments request `nvidia.com/gpu: 1`, so Kubernetes won't schedule them concurrently — the GPU is a discrete resource. Only the workload with `replicas: 1` actually runs.

## Architecture

```
gpu-1 (RTX 5070 Ti, 16GB VRAM)
├── ollama (replicas: 1, default active)
│   └── LLM inference — qwen3.5:9b, deepseek-coder:6.7b
└── comfyui (replicas: 0, scaled up on demand)
    └── Diffusion models — LTX-2.3 (video), SDXL (image), Stable Audio

gpu-switcher (any amd64 node)
└── Web dashboard at 192.168.55.214:8080
    ├── Shows which workload owns the GPU
    ├── One-click activate/deactivate
    └── Patches Deployment replicas via K8s API
```

Three ArgoCD apps, all using raw manifests (no upstream Helm chart):

| App | Namespace | IP | Purpose |
|-----|-----------|-----|---------|
| `comfyui` | comfyui | 192.168.55.213:8188 | ComfyUI web UI + API |
| `gpu-switcher` | gpu-switcher | 192.168.55.214:8080 | GPU time-sharing dashboard |
| `ollama` | ollama | _(existing)_ | Modified: `ignoreDifferences` on replicas |

## ComfyUI

[ComfyUI](https://github.com/comfyanonymous/ComfyUI) is a node-based visual editor for diffusion model pipelines. It supports text-to-video (LTX-2.3), text-to-image (SDXL, Flux), and text-to-audio (Stable Audio). The web UI runs a graph editor where you wire model nodes, samplers, and output nodes together. It also exposes a REST API for programmatic use.

The Deployment:

```yaml
containers:
  - name: comfyui
    image: ghcr.io/ai-dock/comfyui:latest
    resources:
      requests:
        nvidia.com/gpu: 1
      limits:
        nvidia.com/gpu: 1
```

Key decisions:

- **100Gi PVC** on Longhorn `gpu-local` StorageClass — models are large (LTX-2.3 alone is ~4GB, SDXL is ~7GB). This volume mounts at `/workspace` and persists across pod restarts.
- **Starts at 0 replicas** — Ollama is the default active workload. ComfyUI only starts when explicitly switched via the GPU Switcher.
- **Node affinity** to gpu-1 — the only node with a discrete GPU.

## GPU Switcher

The GPU Switcher is a custom Go web application that provides a dashboard for managing GPU time-sharing. It runs as a lightweight pod (50m CPU, 32Mi memory) on any amd64 node — it doesn't need a GPU itself.

### How It Works

The application reads a `WORKLOADS` environment variable that defines the managed workloads:

```
WORKLOADS=ollama:ollama:ollama,comfyui:comfyui:comfyui
```

Format: `name:namespace:deployment` — so `ollama:ollama:ollama` means "the workload called `ollama` is the Deployment named `ollama` in the `ollama` namespace".

On each status check, it queries the Kubernetes API for each Deployment's replica count and pod status. The dashboard shows which workload currently owns the GPU. Activating a workload scales it to 1 replica and scales all others to 0.

### The ArgoCD Problem

ArgoCD's self-heal feature normally detects drift between the Git state and the live cluster, then corrects it. If Git says `replicas: 0` for ComfyUI but the GPU Switcher just scaled it to 1, ArgoCD would scale it back to 0 within minutes.

The fix: `ignoreDifferences` on `spec.replicas` in both the ComfyUI and Ollama Application CRs:

```yaml
spec:
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas
```

This tells ArgoCD to ignore replica count differences — the GPU Switcher is the authority for that field, not Git.

### RBAC

The GPU Switcher's ServiceAccount needs cross-namespace access:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: gpu-switcher
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "patch"]
  - apiGroups: ["apps"]
    resources: ["deployments/scale"]
    verbs: ["get", "patch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
```

A ClusterRole (not a namespaced Role) because it patches Deployments in both the `ollama` and `comfyui` namespaces.

### Building the Image

The GPU Switcher is a static Go binary in a distroless container. Building on an arm64 Mac for amd64 cluster nodes required some care:

```bash
# Cross-compile natively (no QEMU)
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o gpu-switcher-linux-amd64 .

# Package into amd64 distroless runtime
docker buildx build --platform linux/amd64 \
  -t ghcr.io/derio-net/gpu-switcher:v0.1.1 \
  --push .
```

The first build attempt used Docker's `--platform` flag on the full multi-stage build, which tried to run the Go compiler under QEMU emulation — and crashed with a SIGSEGV in the Go runtime's garbage collector. The working approach: compile the Go binary natively on the host (arm64) with `GOARCH=amd64`, then use a single-stage Dockerfile that just copies the pre-built binary into a `--platform linux/amd64` distroless image.

The second attempt pushed an image with `arm64` in its OCI manifest despite containing an amd64 binary — Docker inherits the manifest platform from the build host, not from `FROM --platform`. Using `docker buildx build --push` with explicit `--platform linux/amd64` on a single-stage Dockerfile (no emulated build steps) fixed the manifest.

## Model Downloads

ComfyUI models must be downloaded into the PVC after first deployment. This is a manual operation — the models are large and require specific placement:

```bash
# After switching GPU to ComfyUI via the Switcher
kubectl exec -it -n comfyui deploy/comfyui -- bash

# Inside the pod — download models to the persistent volume
cd /workspace/ComfyUI/models
# LTX-2.3 video model
wget -P video_models/ https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors
# SDXL base
wget -P checkpoints/ https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors
```

This step is documented in the manual operations runbook.

## What's Running

After deployment:

- **Ollama** holds the GPU (replicas: 1) — the default state
- **ComfyUI** is idle (replicas: 0) — waiting to be activated
- **GPU Switcher** shows the dashboard at `192.168.55.214:8080`

To generate a video: open the GPU Switcher, click "Activate" on ComfyUI (which deactivates Ollama), wait for the pod to start (~30s), then open ComfyUI at `192.168.55.213:8188`. When done, switch back to Ollama.

The cluster now has both LLM inference and media generation on a single GPU, with clean time-sharing managed through a web dashboard.
