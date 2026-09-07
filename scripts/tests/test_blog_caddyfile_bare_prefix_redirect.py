"""Tripwire: blog/Caddyfile must redirect bare `/frank` with a top-level `redir`.

THE FAILURE. The image's original Caddyfile carried
`handle /frank { redir /frank/ permanent }` next to `handle_path /frank/* {…}`
and the redirect never fired: a Caddy path matcher ending in `/*` also matches
the path WITHOUT the wildcard segment, `handle` blocks are mutually exclusive
with the longest matcher winning, so `/frank` fell into `handle_path`, had its
prefix stripped to an empty path, and `file_server` answered **200 with an
empty body**. Measured on the live edge (`https://blog.derio.net/frank` →
`200`, `0B`) and reproduced in the built container on 2026-09-07. A blank
page for the site's most-typed URL, and no check noticed, because every probe
used the trailing slash.

THE FIX. A top-level `redir` with a named `path /frank` matcher. Caddy orders
`redir` before `handle`, so it runs first regardless of where it sits in the
file — which is also why a `handle /frank { redir … }` block, however
carefully placed, cannot be the fix. Guarded here by shape (pure-python, no
caddy binary): the redirect must be a `redir` directive, not a `handle`.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CADDYFILE = os.path.join(REPO, "blog", "Caddyfile")


def _lines():
    with open(CADDYFILE) as f:
        return [l.strip() for l in f]


def test_bare_prefix_redirect_is_a_top_level_redir_directive():
    lines = _lines()
    matcher = [l for l in lines if re.fullmatch(r"@\w+\s+path\s+/frank", l)]
    assert matcher, "no named `path /frank` matcher in blog/Caddyfile"
    name = matcher[0].split()[0]
    assert any(re.fullmatch(rf"redir\s+{re.escape(name)}\s+/frank/\s+permanent", l) for l in lines), (
        f"bare /frank must be redirected by a top-level `redir {name} /frank/ permanent`"
    )


def test_no_handle_block_pretends_to_redirect_bare_prefix():
    lines = _lines()
    assert not any(re.fullmatch(r"handle\s+/frank\s*\{", l) for l in lines), (
        "`handle /frank { … }` is dead code beside `handle_path /frank/*` — "
        "the /* matcher also matches bare /frank and wins; use a top-level redir"
    )
