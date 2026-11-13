"""Shared pytest setup for the life tests.

Rendering every Application means `helm template` of ~30 remote charts. Without a cache every
module (and every test that renders) pays that cost again. A session-scoped RENDER_CACHE
(honoured by scripts/render_all_images.py for remote renders only) makes the first render the
only one, in CI and locally; an operator-provided RENDER_CACHE is respected.
"""
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _render_cache(tmp_path_factory):
    if os.environ.get("RENDER_CACHE"):
        yield
        return
    path = tmp_path_factory.mktemp("render-cache")
    os.environ["RENDER_CACHE"] = str(path)
    try:
        yield
    finally:
        os.environ.pop("RENDER_CACHE", None)
