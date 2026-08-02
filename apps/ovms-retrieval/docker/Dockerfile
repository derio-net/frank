# Model artifacts for the ovms-retrieval Deployment — an OpenVINO IR bundle,
# NOT a runtime image. The serving container stays STOCK
# openvino/model_server:2026.2.1-gpu (see the design spec's "Images" table);
# this image ships only the converted weights, tokenizers and graph configs
# that stock image needs to load them.
#
# WHY THIS EXISTS AT ALL (design spec: "The runtime gate" / "Model
# acquisition"). `ovms --pull` cannot produce a servable model here:
#   - without --weight-format it downloads raw HF safetensors that fail to
#     load ("openvino_tokenizer.xml was not provided");
#   - with --weight-format it needs optimum-intel, which no published OVMS
#     image (2026.2.1 / 2026.2.1-gpu) carries;
#   - the pre-converted `OpenVINO/` HF org only publishes English-only
#     bge variants, which is the exact problem this deployment exists to fix.
# So the IR is built ONCE here, in CI, using OVMS's OWN export_model.py (not
# raw optimum-cli) — it is the only tool that also emits the tokenizer XML,
# per-model graph.pbtxt AND the merged config.json in the layout OVMS expects.
#
# Multi-stage: the export stage carries optimum-intel/nncf/torch; the final
# stage copies out only the resulting model repository, so none of that
# toolchain — nor any HuggingFace egress at runtime — ever reaches the cluster.
#
# MODELS_REV moves the published image tag (see the build workflow) whenever
# these contents change, so a Deployment pin is a deliberate bump, not a
# `:latest` drift.

ARG MODELS_REV=1

# ── export stage ────────────────────────────────────────────────────────
FROM python:3.12.13-slim-bookworm AS export

# Pinned to the SAME release line as the stock serving image
# (openvino/model_server:2026.2.1-gpu), so the export tooling and the runtime
# that loads its output agree on IR format.
ARG MODEL_SERVER_REF=v2026.2.1
# optimum-intel has no stable PyPI release usable here — pin to the commit the
# model_server v2026.2.1 export demo itself pins.
ARG OPTIMUM_INTEL_REF=d4dd21a3aa89c0671d85b704847ac06a378e761c
ARG OPENVINO_VERSION=2026.2.0rc2
ARG OPENVINO_TOKENIZERS_VERSION=2026.2.0.0rc2

# The two model repositories this bundle serves. Multilingual pair —
# bge-reranker-v2-m3 is a true cross-encoder, unlike an LLM-style reranker.
ARG EMBEDDINGS_MODEL=BAAI/bge-m3
ARG EMBEDDINGS_MODEL_NAME=bge-m3
ARG RERANK_MODEL=BAAI/bge-reranker-v2-m3
ARG RERANK_MODEL_NAME=bge-reranker-v2-m3

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /export

# Same extra index URLs + pins as model_server's own
# demos/common/export_models/requirements.txt at MODEL_SERVER_REF — kept
# inline (rather than fetched) so the toolchain is reproducible even if that
# file's shape changes upstream.
RUN pip install \
    --extra-index-url "https://download.pytorch.org/whl/cpu" \
    --extra-index-url "https://storage.openvinotoolkit.org/simple/wheels/nightly" \
    --extra-index-url "https://storage.openvinotoolkit.org/simple/wheels/pre-release" \
    "optimum-intel@git+https://github.com/huggingface/optimum-intel.git@${OPTIMUM_INTEL_REF}" \
    "nncf" \
    "openvino==${OPENVINO_VERSION}" \
    "openvino-tokenizers==${OPENVINO_TOKENIZERS_VERSION}" \
    "sentence_transformers==5.3.0" \
    "sentencepiece" \
    "jinja2"

# OVMS's own exporter — emits IR + openvino_tokenizer.xml + graph.pbtxt +
# merged config.json, which is exactly what `ovms --pull` does not.
RUN curl -fsSL -o export_model.py \
    "https://raw.githubusercontent.com/openvinotoolkit/model_server/${MODEL_SERVER_REF}/demos/common/export_models/export_model.py"

# Two repositories — GPU and CPU — because target_device is baked into each
# servable's graph.pbtxt at export time, and the benchmark needs a CPU control
# arm to know whether the iGPU was worth claiming (spec Test Plan row 5/gap 3b).
# Both arms run byte-identical int8 weights.
RUN mkdir -p /out/gpu /out/cpu \
    && python export_model.py embeddings_ov \
        --source_model "${EMBEDDINGS_MODEL}" --model_name "${EMBEDDINGS_MODEL_NAME}" \
        --weight-format int8 --target_device GPU \
        --config_file_path /out/gpu/config.json --model_repository_path /out/gpu \
    && python export_model.py rerank_ov \
        --source_model "${RERANK_MODEL}" --model_name "${RERANK_MODEL_NAME}" \
        --weight-format int8 --target_device GPU \
        --config_file_path /out/gpu/config.json --model_repository_path /out/gpu \
    && python export_model.py embeddings_ov \
        --source_model "${EMBEDDINGS_MODEL}" --model_name "${EMBEDDINGS_MODEL_NAME}" \
        --weight-format int8 --target_device CPU \
        --config_file_path /out/cpu/config.json --model_repository_path /out/cpu \
    && python export_model.py rerank_ov \
        --source_model "${RERANK_MODEL}" --model_name "${RERANK_MODEL_NAME}" \
        --weight-format int8 --target_device CPU \
        --config_file_path /out/cpu/config.json --model_repository_path /out/cpu

# ── final stage — model artifacts only, nothing else ───────────────────
FROM busybox:1.38.0-uclibc

ARG MODELS_REV
LABEL org.opencontainers.image.description="ovms-retrieval model repository (embeddings + rerank, GPU/CPU) rev ${MODELS_REV}"

COPY --from=export /out /models-src
