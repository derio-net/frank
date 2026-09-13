"""Tripwire: frank's local fixes to blog-craft FRAMEWORK-class templates are present.

blog-craft's updater (`tools/update.py`) classifies every path via
`templates/manifest.yaml`: `framework` paths are REPLACED wholesale on the
next `/blog-craft:update`, `merged` paths are three-way merged, `content`
paths are left alone. Seven fixes made in frank#787 live in framework-class
files, so an update that runs before they land upstream (blog-craft#86)
silently reverts them — no conflict, no diff on the merge, ArgoCD green.

This test pins the fixes by shape so a revert fails the tripwires job. Since
the v0.22.2 re-sync (2026-09-13) every one of them is upstream (blog-craft#86
and #87) and frank carries no local edit to a framework-owned file; the
assertions now guard against a regression on EITHER side landing here through
an update. (blog-craft#88 tracks making consumer divergence first-class.)
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOG = os.path.join(REPO, "blog")


def _read(rel):
    with open(os.path.join(BLOG, rel), encoding="utf-8") as f:
        return f.read()


def test_reader_home_keeps_hextra_sidebar_container():
    # menu.js dereferences .hextra-sidebar-container unconditionally; without
    # the partial the home page has no mobile nav and no footer theme toggle.
    src = _read("layouts/reader-home.html")
    assert 'partial "sidebar.html" (dict "context" . "disableSidebar" true)' in src


def test_operating_posts_show_their_cover():
    # v0.22.x renders the reader cover from the shared reader/header.html partial.
    src = _read("layouts/partials/reader/header.html")
    assert 'if not (in .Params.series "operating")' not in src, (
        "reader/header.html regressed to the 0.22.0 hardcoded operating-series cover exclusion"
    )
    assert "site.Params.reader.coverless" in src  # 0.22.2: the operator's list, empty on frank
    assert 'class="post-cover"' in src


def test_series_tiles_are_image_aware():
    src = _read("layouts/shortcodes/reader-home.html")
    assert "reader-series-card" in src and 'with .image' in src


def test_site_banner_covers_top_level_sections():
    src = _read("layouts/partials/site-banner.html")
    assert 'printf "images/banner-%s.png" (index $parts 0)' in src


def test_reader_head_has_single_og_image_source():
    src = _read("layouts/partials/reader/head.html")
    assert "or .Params.images site.Params.images" in src


def test_export_content_fixes():
    src = _read("scripts/export-content.py")
    assert "newline = '' if source.endswith('\\n') else '\\n'" in src, "PEP 701 f-string is back (breaks Python 3.11)"
    assert "h1.text().strip()==article['title'].strip()" in src, "fallback path no longer strips the duplicate title H1"
    assert "read_text(encoding='utf-8')" in src and "write_text(result,encoding='utf-8')" in src


def test_build_site_rejects_arguments():
    src = _read("scripts/build-site.py")
    assert "if sys.argv[1:]:" in src and "*sys.argv[1:]" not in src
