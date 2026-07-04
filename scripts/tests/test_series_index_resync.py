"""Re-sync guards — frank consumes blog-craft's standardized series-index (blog-craft
@ a7f2f7f, PR #12) instead of the hand-written #605 copies, with ZERO visual change.

These are pure-Python (no hugo) invariants:
  * colour parity   — the regenerated palette keeps the exact #605 colours (golden).
  * registry↔palette — every declared layer has a palette entry + matching name.
  * generator identity — frank's vendored generator == blog-craft's tool (a7f2f7f).
  * drop-divergence  — frank's series-index.html + roadmap.html == blog-craft's
                       shipped templates (frank no longer carries a divergent copy).
  * no-orphan-key    — every consumed layer key resolves in the alias-free palette.

Fixtures under scripts/tests/fixtures/ pin the blog-craft@a7f2f7f snapshot; a future
re-sync bumps them to the new SHA. See
docs/superpowers/specs/2026-07-04--repo--frank-series-index-resync-design.md
"""
import os
import re

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOG = os.path.join(REPO, "blog")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
BC = os.path.join(FIX, "blog-craft-a7f2f7f")

# frank's 21 layer codes (the series_index registry order; hues assigned by index)
CORE_CODES = ["hw", "os", "net", "stor", "gpu", "gitops", "fun", "obs", "backup",
              "secrets", "infer", "agents", "auth", "tenant", "orch", "media", "edge",
              "deploy", "cicd", "auto", "repo"]
COLOUR_KEYS = ("light", "dark", "lt", "dt")


def _load(path):
    with open(path) as f:
        return yaml.safe_load(f)


def _live_palette():
    return _load(os.path.join(BLOG, "data", "layer_palette.yaml"))["layers"]


def test_palette_colour_parity_with_605_golden():
    """The regenerated palette must keep the exact #605 colours for all 21 codes."""
    golden = _load(os.path.join(FIX, "layer_palette.605.golden.yaml"))["layers"]
    live = _live_palette()
    for code in CORE_CODES:
        assert code in live, f"{code} missing from regenerated palette"
        for k in COLOUR_KEYS:
            assert live[code][k] == golden[code][k], \
                f"{code}.{k}: {live[code][k]} != #605 golden {golden[code][k]}"


def test_registry_palette_name_consistency():
    """Every series_index.layers code has a palette entry with a matching name."""
    cfg = _load(os.path.join(REPO, ".blog-craft.yaml"))
    layers = ((cfg.get("series_index") or {}).get("layers")) or []
    assert layers, ".blog-craft.yaml has no series_index.layers registry"
    live = _live_palette()
    for entry in layers:
        code, name = entry["code"], entry["name"]
        assert code in live, f"registry code {code} absent from palette"
        assert live[code].get("name") == name, \
            f"{code} name mismatch: palette={live[code].get('name')!r} registry={name!r}"


def test_generator_is_blog_craft_standardized():
    """frank's vendored generator is byte-identical to blog-craft@a7f2f7f's tool."""
    live = open(os.path.join(BLOG, "scripts", "gen-layer-palette.py"), "rb").read()
    ref = open(os.path.join(BC, "gen-layer-palette.py"), "rb").read()
    assert live == ref, "blog/scripts/gen-layer-palette.py has diverged from blog-craft@a7f2f7f"


def test_shortcodes_dropped_divergence():
    """frank's series-index.html + roadmap.html == blog-craft's shipped templates."""
    for name in ("series-index.html", "roadmap.html"):
        live = open(os.path.join(BLOG, "layouts", "shortcodes", name), "rb").read()
        ref = open(os.path.join(BC, name), "rb").read()
        assert live == ref, f"blog/layouts/shortcodes/{name} diverges from blog-craft@a7f2f7f"


# Roadmap keys that are neutral BY DESIGN (no per-layer colour): `upcoming` marks
# future/unbuilt layers, greyed since #605. Not an alias-stranding orphan.
NEUTRAL_KEYS = {"upcoming"}


def test_no_orphan_layer_key():
    """Every colour-bearing layer key consumed by roadmap.yaml, papers.yaml, and
    posts resolves in the palette. Guards the alias retirement (inference/docs)
    against stranding a key — a stranded key renders a NEUTRAL card (colour loss),
    the exact zero-visual-change regression this re-sync must not introduce.
    Deliberately-neutral keys are allowlisted."""
    palette = _live_palette()
    orphans = []
    # roadmap.yaml layer keys
    roadmap = _load(os.path.join(BLOG, "data", "roadmap.yaml"))
    for layer in (roadmap.get("layers") or []):
        key = layer.get("key")
        if key and key not in palette and key not in NEUTRAL_KEYS:
            orphans.append(f"roadmap.yaml key:{key}")
    # papers.yaml entries' `layer:` (consumed by papers-roadmap.html, which reads
    # the DATA file, not post frontmatter — this is where the docs alias hid)
    papers = _load(os.path.join(BLOG, "data", "papers.yaml"))
    for entry in (papers.get("entries") or []):
        key = entry.get("layer")
        if key and key not in palette and key not in NEUTRAL_KEYS:
            orphans.append(f"papers.yaml entry {entry.get('number')} layer:{key}")
    # post frontmatter `layer:`
    for idx in _iter_post_indexes():
        m = re.search(r"(?m)^layer:\s*([A-Za-z0-9_-]+)", open(idx).read())
        if m and m.group(1) not in palette:
            orphans.append(f"{os.path.relpath(idx, REPO)} layer:{m.group(1)}")
    assert not orphans, "layer keys with no palette entry: " + ", ".join(orphans)


def _iter_post_indexes():
    for series in ("building", "operating"):
        base = os.path.join(BLOG, "content", "docs", series)
        for name in sorted(os.listdir(base)):
            idx = os.path.join(base, name, "index.md")
            if os.path.exists(idx):
                yield idx
