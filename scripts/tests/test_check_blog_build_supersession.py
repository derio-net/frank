"""check_blog_build.py must enforce BOTH halves of a tolerated inline script.

An entry in TOLERATED_INLINE_SCRIPTS says "this inline block is inert because an
external asset already does the work". Only the first half was ever checked: the
block was forgiven on a keyword match, and nothing asserted the replacement was
loaded. Removing the superseder's <script> tag therefore left the build GREEN
while the behaviour died — which is very nearly what the blog-craft v0.16.0
resync (#718) did to blog/assets/js/mermaid-init.js. It was caught by reading the
diff, not by this checker.

A tolerate-list that does not verify its own excuse is worse than no entry at
all: it converts a loud failure into a silent one, and reads as coverage.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_blog_build.py"

# The theme's inline mermaid init, keyed the way the checker keys it.
INLINE_THEME_MERMAID = (
    '<script>document.querySelectorAll(".mermaid").forEach((el)=>{'
    'el.dataset.original=el.innerHTML;});</script>'
)
SUPERSEDER = '<script src=/frank/js/mermaid-init.min.abc123.js defer></script>'


def _run(tmp_path, html, name="index.html"):
    site = tmp_path / "public"
    site.mkdir(exist_ok=True)
    (site / name).write_text("<!DOCTYPE html><html><body>%s</body></html>" % html)
    r = subprocess.run([sys.executable, str(CHECKER), str(site)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_tolerated_when_the_superseder_is_loaded(tmp_path):
    """The normal case: theme block present, external replacement present."""
    rc, out = _run(tmp_path, SUPERSEDER + INLINE_THEME_MERMAID)
    assert rc == 0, out
    assert "tolerated 1x" in out, out


def test_fails_when_the_superseder_is_missing(tmp_path):
    """The regression this test exists for. Same inline block, no replacement —
    previously reported OK, which is how a dead feature ships unnoticed."""
    rc, out = _run(tmp_path, INLINE_THEME_MERMAID)
    assert rc != 0, "a tolerated inline script with NO superseder must FAIL:\n" + out
    assert "supersedes it" in out or "silently dead" in out, out


def test_an_unrelated_external_script_does_not_satisfy_the_excuse(tmp_path):
    """The superseder is matched by name, not by 'some script exists'. Without
    this, any page with any <script src> would satisfy every tolerate entry."""
    rc, out = _run(
        tmp_path,
        '<script src=/frank/js/read-tracker.min.def456.js defer></script>'
        + INLINE_THEME_MERMAID,
    )
    assert rc != 0, "an unrelated external script must not satisfy the excuse:\n" + out


def test_order_does_not_matter(tmp_path):
    """The superseder loads from <head>; the theme's block can appear anywhere
    later. A single-pass check that only looked backwards would be order-fragile."""
    rc, out = _run(tmp_path, INLINE_THEME_MERMAID + SUPERSEDER)
    assert rc == 0, out


def test_an_untolerated_inline_script_still_fails(tmp_path):
    """The original invariant must survive the change."""
    rc, out = _run(tmp_path, "<script>alert(1)</script>")
    assert rc != 0, out
    assert "inline <script>" in out, out
