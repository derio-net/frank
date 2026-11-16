# Derived speaches image with a Blackwell-capable CTranslate2.
#
# Why derived: the upstream image (0.9.0-rc.3-cuda, CUDA 12.9 base) ships
# CTranslate2 4.5.0, built on CUDA 12.2 with no sm_120 kernels, so the
# faster-whisper STT path is not established on the RTX 5070 Ti. CTranslate2
# 4.6.2 added the sm_120 handling and 4.6.3 the CUDA 12.8 build.
# ctranslate2 4.6.3 has cp312 manylinux wheels (the upstream venv is
# Python 3.12) and faster-whisper 1.1.1 only requires ctranslate2 >=4.0,<5.
#
# Base is pinned by the digest measured on 2026-11-16 for tag 0.9.0-rc.3-cuda.
FROM ghcr.io/speaches-ai/speaches:0.9.0-rc.3-cuda@sha256:f4eb14d1c53b19c5bd1f76d10ea9fc10288ceaf82dca09506d3f0ef92ee943de

# Verified 2026-11-16 against the upstream Dockerfile at tag v0.9.0-rc.3
# (raw.githubusercontent.com/speaches-ai/speaches/v0.9.0-rc.3/Dockerfile):
#   - uv is copied to /bin/uv (on PATH); the project venv is
#     /home/ubuntu/speaches/.venv (built by `uv sync --frozen`), WORKDIR
#     /home/ubuntu/speaches, user ubuntu (uid 1000);
#   - the venv bin is on PATH and CMD is plain
#     ["uvicorn","--factory","speaches.main:create_app"] — NOT `uv run`, so
#     nothing re-syncs ctranslate2 back to the locked 4.5.0 at start-up.
# UV_NO_SYNC is set anyway so an operator `uv run` inside the container cannot
# silently undo the override either.
ARG CTRANSLATE2_VERSION=4.6.3
ENV UV_NO_SYNC=1

USER ubuntu
RUN uv pip install --python /home/ubuntu/speaches/.venv/bin/python \
      "ctranslate2==${CTRANSLATE2_VERSION}" \
 && /home/ubuntu/speaches/.venv/bin/python -c \
      "import ctranslate2 as c; v=tuple(int(p) for p in c.__version__.split('.')[:3]); assert v >= (4, 6, 3), c.__version__; print('ctranslate2', c.__version__, 'cpu compute types:', sorted(c.get_supported_compute_types('cpu')))" \
 && /home/ubuntu/speaches/.venv/bin/python -c "import faster_whisper; print('faster_whisper', faster_whisper.__version__)"
