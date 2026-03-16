FROM nvidia/cuda:12.8.0-devel-ubuntu22.04

# Version pins — passed as build args from CI, with defaults for local builds
ARG COMFYUI_REF=v0.9.2
ARG MANAGER_REF=4.0.5
ARG PYTORCH_VERSION=2.10.0
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
