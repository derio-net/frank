"""Frank adopts blog-craft #14's WebP image pipeline (blog-craft @ 78ab274).

Pure-python invariants (config + drop-divergence) always run; the build check
needs Hugo Extended (WebP encode) and is skipped otherwise.

See docs/superpowers/specs/2026-07-04--repo--frank-image-optimization-adoption-design.md
"""
import glob
import os
import re
import shutil
import subprocess

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOG = os.path.join(REPO, "blog")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "blog-craft-78ab274")


def test_config_opts_into_optimization():
    with open(os.path.join(REPO, ".blog-craft.yaml")) as f:
        cfg = yaml.safe_load(f)
    opt = (cfg.get("image") or {}).get("optimize") or {}
    assert opt.get("enabled") is True, "image.optimize.enabled must be true"
    assert opt.get("format") == "webp"
    assert cfg.get("blog_craft_version") == "78ab274", "must pin blog-craft #14 SHA"


def test_mechanism_templates_match_blog_craft():
    """opt-image + render-image track blog-craft@78ab274 (no frank divergence)."""
    for name, dest in (("opt-image.html", "partials/opt-image.html"),
                       ("render-image.html", "_markup/render-image.html")):
        live = open(os.path.join(BLOG, "layouts", dest), "rb").read()
        ref = open(os.path.join(FIX, name), "rb").read()
        assert live == ref, f"blog/layouts/{dest} diverges from blog-craft@78ab274"


def test_banners_relocated_to_assets():
    assets = sorted(os.path.basename(p) for p in glob.glob(os.path.join(BLOG, "assets", "images", "banner-*.png")))
    assert assets, "no banners under blog/assets/images/ (Hugo can't process static/)"
    stale = glob.glob(os.path.join(BLOG, "static", "images", "banner-*.png"))
    assert not stale, f"banners still in static/images (unprocessable): {stale}"


_hugo = shutil.which("hugo")
_extended = _hugo and "+extended" in subprocess.run([_hugo, "version"], capture_output=True, text=True).stdout
_BUILD = {}


def _build():
    if "dest" not in _BUILD:
        dest = subprocess.run(["mktemp", "-d"], capture_output=True, text=True).stdout.strip()
        r = subprocess.run(["hugo", "--minify", "--destination", dest, "--logLevel", "error"],
                           cwd=BLOG, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        _BUILD["dest"] = dest
    return _BUILD["dest"]


@pytest.mark.skipif(not _extended, reason="Hugo Extended required for WebP encode")
def test_build_emits_webp():
    dest = _build()
    # a post with a cover + inline image
    hits = glob.glob(os.path.join(dest, "**", "building", "01-introduction", "index.html"), recursive=True)
    assert hits, "intro post not built"
    html = open(hits[0]).read()
    # quote-agnostic: production build is --minify (strips attribute quotes)
    assert re.search(r'src=["\']?[^"\'>\s]+\.webp', html), "no webp <img> on the intro post"
    assert "srcset=" in html and ".webp" in html
    # banners become webp too (banner rendered on section/home pages)
    assert glob.glob(os.path.join(dest, "**", "*.webp"), recursive=True), "no webp derivatives generated"
