"""Frank adopts blog-craft #14's WebP image pipeline (blog-craft @ 5dc31f8).

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
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "blog-craft-5dc31f8")


def test_config_opts_into_optimization():
    with open(os.path.join(REPO, ".blog-craft.yaml")) as f:
        cfg = yaml.safe_load(f)
    opt = (cfg.get("image") or {}).get("optimize") or {}
    assert opt.get("enabled") is True, "image.optimize.enabled must be true"
    assert opt.get("format") == "webp"
    # a recorded pin is what update.py needs for a real 3-way base; the exact
    # release moves (was the #14 SHA, then v0.9.0, now v0.10.0+) — don't freeze it
    assert cfg.get("blog_craft_version"), "blog_craft_version pin must be recorded"


def test_mechanism_templates_match_blog_craft():
    """render-image tracks blog-craft@5dc31f8 (no frank divergence).

    opt-image.html is a RECORDED divergence — pinned by the next test.
    """
    for name, dest in (("render-image.html", "_markup/render-image.html"),):
        live = open(os.path.join(BLOG, "layouts", dest), "rb").read()
        ref = open(os.path.join(FIX, name), "rb").read()
        assert live == ref, f"blog/layouts/{dest} diverges from blog-craft@5dc31f8"


def test_opt_image_diverges_from_blog_craft_only_in_the_srcset_clamp():
    """opt-image.html carries ONE deliberate fix ahead of blog-craft@5dc31f8.

    Upstream builds the srcset from `slice 480 960 $maxW` and clamps each
    candidate with `le $w $maxW` — comparing the cap against itself instead of
    against the primary actually emitted. Whenever the SOURCE is narrower than
    the cap (frank's banners are 2169w against a 2560 cap, covers 1424w against
    1600) the top candidate is dropped and nothing in the srcset matches the
    primary. Since the HTML spec removes `src` from the candidate list as soon
    as a srcset uses `w` descriptors, the full-resolution file becomes
    unreachable and every banner renders upscaled from 960w — measured at 2.0x
    on a 1512px Retina viewport, and worse on wider screens.

    That is an upstream defect, not a frank preference, so it belongs in
    blog-craft. Until it lands there and frank re-syncs, this test pins the
    divergence to exactly that hunk, so no OTHER drift can hide behind it.
    """
    live = open(os.path.join(BLOG, "layouts", "partials", "opt-image.html")).read()
    ref = open(os.path.join(FIX, "opt-image.html")).read()

    assert "(slice 480 960 $maxW)" in ref, (
        "fixture is no longer the upstream copy this divergence was recorded "
        "against — re-check whether blog-craft has fixed it upstream"
    )
    assert "(slice 480 960 $maxW)" not in live, (
        "opt-image.html regressed to the upstream srcset clamp — banners will "
        "silently render upscaled from 960w again"
    )
    assert "$topW := $primary.Width" in live, (
        "the srcset's top candidate must be the primary's real width"
    )

    # Nothing outside the srcset loop may differ. Compare the parts either side
    # of it: a change anywhere else is unrecorded drift, not this fix.
    marker = "{{- if $primary -}}"
    assert live.split(marker)[1] == ref.split(marker)[1], (
        "opt-image.html diverges from blog-craft@5dc31f8 in its EMIT block — "
        "that drift is not recorded anywhere"
    )
    preamble = "{{- /* decode the source width defensively"
    assert live.split(preamble)[0] == ref.split(preamble)[0], (
        "opt-image.html diverges from blog-craft@5dc31f8 in its preamble"
    )


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
