"""Parity tests for the page-derived series-index overviews (frank adoption).

Builds the real Hugo site and asserts each series overview's
``<table class="series-index">`` lists exactly its section's posts — ground truth
derived from the filesystem (never hardcoded), ordered by numeric prefix,
self-excluded — and that the retired marker-append push machinery is gone.

See docs/superpowers/specs/2026-07-04--repo--frank-series-index-adoption-design.md
"""
import os
import re
import shutil
import subprocess
import tempfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOG = os.path.join(REPO, "blog")

pytestmark = pytest.mark.skipif(shutil.which("hugo") is None, reason="hugo not installed")


def expected_slugs(series):
    """The NN-slug post bundles under content/docs/<series>/, excluding the
    overview, ordered by numeric prefix — the ground truth the index must match."""
    base = os.path.join(BLOG, "content", "docs", series)
    found = []
    for name in os.listdir(base):
        full = os.path.join(base, name)
        if name == "00-overview" or not os.path.isdir(full):
            continue
        if not os.path.exists(os.path.join(full, "index.md")):
            continue
        m = re.match(r"^(\d+)", name)
        if not m:
            continue
        found.append((int(m.group(1)), name))
    return [name for _, name in sorted(found)]


_BUILD = {}


def build_site():
    """Build the whole site once (cached across tests) into a temp destination."""
    if "dest" not in _BUILD:
        dest = tempfile.mkdtemp(prefix="frank-hugo-")
        # Match the production config (deploy-blog.yml / Dockerfile build with
        # --minify), so the parity assertions guard the actual deployed artifact.
        r = subprocess.run(
            ["hugo", "--minify", "--destination", dest, "--logLevel", "error"],
            cwd=BLOG, capture_output=True, text=True,
        )
        assert r.returncode == 0, f"hugo build failed:\n{r.stdout}\n{r.stderr}"
        _BUILD["dest"] = dest
    return _BUILD["dest"]


def rendered_overview(series):
    path = os.path.join(build_site(), "docs", series, "00-overview", "index.html")
    assert os.path.exists(path), f"no built overview for {series} at {path}"
    return open(path).read()


def series_index_table(html):
    # quote-agnostic: --minify strips attribute quotes (class=series-index)
    m = re.search(r'<table class="?series-index"?>.*?</table>', html, re.S)
    return m.group(0) if m else None


def _assert_parity(series):
    table = series_index_table(rendered_overview(series))
    assert table, f"{series} overview renders no series-index table"
    slugs = expected_slugs(series)
    assert slugs, f"no {series} posts found on disk — test setup wrong"

    positions = []
    for slug in slugs:
        needle = f"/docs/{series}/{slug}/"
        assert needle in table, f"{slug} not linked in the {series} index"
        positions.append(table.index(needle))
    # rows appear in numeric-prefix order
    assert positions == sorted(positions), f"{series} index not in numeric order"
    # the overview excludes itself, and there is exactly one body row per post
    assert "00-overview" not in table, f"{series} overview lists itself"
    assert table.count("<tr") == len(slugs) + 1, "row count != posts + header"


def test_building_series_index_parity():
    _assert_parity("building")


def test_operating_series_index_parity():
    _assert_parity("operating")


def test_no_stale_push_machinery():
    ov = open(os.path.join(BLOG, "content", "docs", "building", "00-overview", "index.md")).read()
    assert "auto-appends" not in ov, "stale #604 marker still in building/00-overview"
    assert "Operating on Frank — Series Index" not in ov, \
        "operating index still embedded in building/00-overview (should move to its own overview)"
