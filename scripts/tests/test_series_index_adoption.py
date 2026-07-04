"""Structure + parity tests for the page-derived series-index cards (frank adoption).

The series index renders as papers-roadmap-style cards on each series' SECTION
ENTRYPOINT (docs/<series>/index.html, from _index.md) — colour-coded by the post's
`layer` via the single palette source blog/data/layer_palette.yaml. Building keeps its
00-overview (roadmap / capability map / cluster state, no index); operating's
00-overview is gone. Papers shares the same layer-name tag treatment.

Builds the real production (--minify) site and asserts against the rendered HTML.
See docs/superpowers/specs/2026-07-04--repo--frank-series-index-adoption-design.md
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOG = os.path.join(REPO, "blog")

pytestmark = pytest.mark.skipif(shutil.which("hugo") is None, reason="hugo not installed")


def expected_slugs(series):
    """The NN-slug post bundles under content/docs/<series>/, excluding the overview,
    ordered by numeric prefix — the ground truth the card index must match."""
    base = os.path.join(BLOG, "content", "docs", series)
    found = []
    for name in os.listdir(base):
        full = os.path.join(base, name)
        if name == "00-overview" or not os.path.isdir(full):
            continue
        if not os.path.exists(os.path.join(full, "index.md")):
            continue
        m = re.match(r"^(\d+)", name)
        if m:
            found.append((int(m.group(1)), name))
    return [name for _, name in sorted(found)]


_BUILD = {}


def build_site():
    """Build the whole site once (cached) with --minify, matching production."""
    if "dest" not in _BUILD:
        dest = tempfile.mkdtemp(prefix="frank-hugo-")
        r = subprocess.run(
            ["hugo", "--minify", "--destination", dest, "--logLevel", "error"],
            cwd=BLOG, capture_output=True, text=True,
        )
        assert r.returncode == 0, f"hugo build failed:\n{r.stdout}\n{r.stderr}"
        _BUILD["dest"] = dest
    return _BUILD["dest"]


def entry_html(series):
    """Rendered section entrypoint (docs/<series>/index.html — from _index.md)."""
    path = os.path.join(build_site(), "docs", series, "index.html")
    assert os.path.exists(path), f"no section entrypoint for {series} at {path}"
    return open(path).read()


# quote-agnostic (production build is minified): captures (number, url) per card, in
# document order. si-num is unique to the series-index cards, so this never matches
# Hextra's own section page-list links.
_CARD = re.compile(r'''si-num["']?>(\d+)</span><a href=["']?([^"'>\s]+)''')


def cards(series):
    return _CARD.findall(entry_html(series))


def _assert_parity(series):
    cs = cards(series)
    slugs = expected_slugs(series)
    assert slugs, f"no {series} posts on disk — test setup wrong"
    urls = [u for _, u in cs]
    nums = [n for n, _ in cs]

    for slug in slugs:
        assert any(f"/docs/{series}/{slug}/" in u for u in urls), f"{slug} not carded in {series} index"
    assert len(cs) == len(slugs), f"{series}: {len(cs)} cards but {len(slugs)} posts"
    assert not any("00-overview" in u for u in urls), f"{series} index lists an overview page"
    assert nums == sorted(nums, key=int), f"{series} cards not in numeric order"


def test_building_series_index_cards():
    _assert_parity("building")


def test_operating_series_index_cards():
    _assert_parity("operating")


def test_index_lives_on_section_entrypoint():
    # building keeps 00-overview (roadmap/capability/state) but with NO index on it
    ov = os.path.join(build_site(), "docs", "building", "00-overview", "index.html")
    assert os.path.exists(ov), "building/00-overview should still exist"
    assert 'class="si-card' not in open(ov).read(), "series-index leaked onto building/00-overview"
    # operating/00-overview is deleted outright
    assert not os.path.exists(os.path.join(BLOG, "content", "docs", "operating", "00-overview")), \
        "operating/00-overview should be removed"


def test_layer_colour_coding_and_name_tag():
    h = entry_html("building")
    assert "layer-stor" in h and "layer-agents" in h, "cards missing per-layer classes"
    assert "tag-layer" in h and "Storage" in h, "layer full-name tag missing"


def test_papers_uses_same_layer_name_tag():
    h = open(os.path.join(build_site(), "docs", "papers", "index.html")).read()
    assert "tag-layer" in h, "papers roadmap not using the shared layer-name tag"
    assert ">layer: " not in h, "papers still shows the old terse 'layer: <code>' tag"
    assert "Networking" in h or "Public Edge" in h, "papers layer name not rendered"


def test_no_stale_push_machinery():
    ov = open(os.path.join(BLOG, "content", "docs", "building", "00-overview", "index.md")).read()
    assert "auto-appends" not in ov, "stale #604 marker still in building/00-overview"
    assert "Operating on Frank — Series Index" not in ov, "operating index still embedded in building overview"
    assert "{{< series-index" not in ov, "series-index shortcode should be on _index.md, not 00-overview"


def test_palette_single_source_and_reproducible():
    # the committed data file must match the generator output (drift guard)
    gen = subprocess.run([sys.executable, os.path.join(BLOG, "scripts", "gen-layer-palette.py")],
                         capture_output=True, text=True)
    assert gen.returncode == 0, gen.stderr
    committed = open(os.path.join(BLOG, "data", "layer_palette.yaml")).read()
    assert gen.stdout == committed, "layer_palette.yaml is out of sync with gen-layer-palette.py — regenerate"
