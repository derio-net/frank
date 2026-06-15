FROM nvidia/cuda:12.8.0-devel-ubuntu22.04

# Version pins — passed as build args from CI, with defaults for local builds
ARG COMFYUI_REF=v0.9.2
ARG MANAGER_REF=4.0.5
ARG PYTORCH_VERSION=2.10.0
ARG TORCHVISION_VERSION=0.25.0
ARG CUDA_VERSION_PIP=cu128

# ── stoa custom-node refs ──────────────────────────────────────────
# Pinned to commit SHAs (these repos publish no release tags) so the image is
# reproducible. Bump deliberately + bump STOA_NODES with it.
ARG LTXVIDEO_REF=229437c6b65796d6a7a63ae34be2bd5ba31fa543
ARG GGUF_REF=6ea2651e7df66d7585f6ffee804b20e92fb38b8a
ARG WANVIDEO_REF=088128b224242e110d3906c6750e9a3a348a659b
ARG KOKORO_REF=cfb59b5605b351e196182c836f0b48c1a784e52f
ARG FISHSPEECH_REF=6d6cd7c0b00f07a057d9b799eeca80866a0d5ff7

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
# Pin torchaudio to torch's version — unpinned, pip resolves a NEWER torchaudio
# (e.g. 2.11.0 vs torch 2.10.0) whose libtorchaudio.abi3.so fails to load,
# silently breaking ComfyUI's audio nodes + WanVideoWrapper + FishSpeech.
RUN pip install --no-cache-dir \
    torch==${PYTORCH_VERSION} \
    torchvision==${TORCHVISION_VERSION} \
    torchaudio==${PYTORCH_VERSION} \
    --index-url https://download.pytorch.org/whl/${CUDA_VERSION_PIP}

# ── ComfyUI ──────────────────────────────────────────────────────────
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app \
    && cd /app && git checkout ${COMFYUI_REF}

WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt

# ── ComfyUI-Manager (pip package, not custom_nodes) ─────────────────
# Manager 4.x is a proper Python package imported by ComfyUI via
# `import comfyui_manager`. It must NOT live in custom_nodes/ —
# ComfyUI's custom_nodes loader expects __init__.py at root which
# Manager 4.x doesn't have. Pip install makes it globally importable.
RUN pip install --no-cache-dir \
    comfyui-manager==${MANAGER_REF}

# ── stoa custom nodes (baked to a staging dir; entrypoint seeds PVC) ─
# The runtime mounts the comfyui-custom-nodes PVC at /app/custom_nodes, which
# SHADOWS anything baked there — so stage under /opt and have entrypoint.sh
# seed the PVC on boot. Python deps install into the image env here; only the
# node FILES are seeded at runtime. Refs pinned via ARGs (CONFIRM-AT-CI).
RUN mkdir -p /opt/stoa-custom-nodes && cd /opt/stoa-custom-nodes \
    && git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git \
    && git -C ComfyUI-LTXVideo checkout ${LTXVIDEO_REF} \
    # kornia 0.8.3 dropped `pad` from kornia.geometry.transform.pyramid; the node
    # still imports it (upstream bug) -> ImportError. Its calls match torch's
    # F.pad signature, so source `pad` from torch instead.
    && sed -i '/^    pad,$/d' ComfyUI-LTXVideo/pyramid_blending.py \
    && sed -i '/^import torch.nn.functional as F$/a from torch.nn.functional import pad' ComfyUI-LTXVideo/pyramid_blending.py \
    && pip install --no-cache-dir -r ComfyUI-LTXVideo/requirements.txt \
    && git clone https://github.com/city96/ComfyUI-GGUF.git \
    && git -C ComfyUI-GGUF checkout ${GGUF_REF} \
    && pip install --no-cache-dir -r ComfyUI-GGUF/requirements.txt \
    && git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git \
    && git -C ComfyUI-WanVideoWrapper checkout ${WANVIDEO_REF} \
    && pip install --no-cache-dir -r ComfyUI-WanVideoWrapper/requirements.txt \
    && git clone https://github.com/stavsap/comfyui-kokoro.git ComfyUI-Kokoro \
    && git -C ComfyUI-Kokoro checkout ${KOKORO_REF} \
    && pip install --no-cache-dir -r ComfyUI-Kokoro/requirements.txt \
    && git clone https://github.com/AIFSH/ComfyUI-FishSpeech.git \
    && git -C ComfyUI-FishSpeech checkout ${FISHSPEECH_REF} \
    && pip install --no-cache-dir -r ComfyUI-FishSpeech/requirements.txt

# ── Non-root user ───────────────────────────────────────────────────
RUN groupadd -g 1000 comfyui \
    && useradd -u 1000 -g comfyui -d /app -s /bin/bash comfyui \
    && chown -R comfyui:comfyui /app

# ComfyUI-FishSpeech's __init__.py writes a `fish_speech.pth` into site-packages
# at import — fails as the non-root comfyui user (root-owned dir). Pre-create the
# file owned by comfyui so the runtime open("w") (rewrite) succeeds.
RUN SP="$(python -c 'import site; print(site.getsitepackages()[0])')" \
    && touch "$SP/fish_speech.pth" \
    && chown comfyui:comfyui "$SP/fish_speech.pth"

# ── Entrypoint ──────────────────────────────────────────────────────
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER comfyui

EXPOSE 8188

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--listen", "0.0.0.0", "--port", "8188", "--enable-manager", "--enable-manager-legacy-ui"]
