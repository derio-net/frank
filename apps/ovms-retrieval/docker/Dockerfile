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
# NOTE: the export toolchain's own pins (optimum-intel commit, openvino and
# openvino-tokenizers versions) are NOT declared here. They live in upstream's
# requirements.txt, fetched below at ${MODEL_SERVER_REF}. Re-declaring them as
# ARGs would be dead configuration that reads as authoritative — two places to
# change, one of which does nothing. ${MODEL_SERVER_REF} is the single knob.

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

# Fetch the exporter AND its requirements from the SAME pinned ref.
#
# An earlier revision hand-copied the requirements inline, with a comment
# claiming parity with upstream. It was a SUBSET: it dropped `requests`
# (among others), and the build failed at 5s with
# `ModuleNotFoundError: No module named 'requests'` raised from inside
# optimum's own openvino export command. The likely reason it is needed
# explicitly at all is that recent huggingface_hub moved to httpx, so
# `requests` is no longer pulled in transitively — while optimum still
# imports it.
#
# Fetching both files from ${MODEL_SERVER_REF} removes the whole divergence
# class: the script and the dependency list can no longer disagree, and it is
# exactly as reproducible as the export_model.py fetch directly below, which
# already trusted this ref. `--extra-index-url` lines are part of that file.
RUN curl -fsSL -o export_model.py \
        "https://raw.githubusercontent.com/openvinotoolkit/model_server/${MODEL_SERVER_REF}/demos/common/export_models/export_model.py" \
    && curl -fsSL -o requirements.txt \
        "https://raw.githubusercontent.com/openvinotoolkit/model_server/${MODEL_SERVER_REF}/demos/common/export_models/requirements.txt" \
    && grep -q '^requests$' requirements.txt \
    && pip install -r requirements.txt \
    && pip install "jinja2"

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
