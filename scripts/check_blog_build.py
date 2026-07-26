#!/usr/bin/env python3
"""Build-output gate for the blog — the check Caddy's CSP comment assumes exists.

`clusters/hop/apps/caddy/manifests/files/Caddyfile` hardens blog.derio.net with a
CSP. Its own comment says the constraint "is pinned by the site's own build
check" — agentic-stoa/site has one, the blog did not, and on 2026-07-26 that gap
cost the blog every syntax-highlighted code block, all three card lists, and the
dark-mode wiring on 80 mermaid diagrams. Nothing alerted: a CSP violation is a
browser-side drop, so the page still returns 200 and ArgoCD stays green.

This script closes that gap by asserting invariants against the BUILT site, which
is the only place these defects are observable.

Invariant 1 — nothing the CSP will silently drop.
    script-src is 'self' plus the analytics origin, with NO 'unsafe-inline'.
    An inline <script> is therefore dead code that ships and never runs, and an
    external asset from an origin outside the allowlist never loads at all.

    Inline STYLES are deliberately not policed. style-src carries
    'unsafe-inline' for the blog because Hextra's templated CSS custom
    properties make a strict style-src unsatisfiable, so inline styles render
    correctly and are not a defect. This script asserts what the browser
    actually enforces — nothing more, or it would just generate busywork
    against upstream templates frank is supposed to track verbatim.

Invariant 2 — responsive images must be able to reach their own full resolution.
    Once a srcset carries `w` descriptors, the HTML spec drops `src` from the
    candidate list. So if every candidate is narrower than the primary named in
    `src`, the browser CANNOT select the full-resolution file the build just
    generated, and renders an upscaled one instead. That is invisible server-side:
    every variant returns 200.

Usage:  python3 scripts/check_blog_build.py blog/public
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

# Origins the CSP permits for scripts/styles. Keep in sync with the csp_blog
# snippet in clusters/hop/apps/caddy/manifests/files/Caddyfile.
ALLOWED_ORIGINS = {"counter.derio.net"}

# Inline scripts emitted by the PINNED upstream theme, which we cannot remove
# without forking it. Each is tolerated only because an external equivalent
# already does the work — the inline copy is inert, not load-bearing. Keyed by a
# substring that survives minification. Anything NOT listed here fails the build,
# so a theme bump that changes this markup surfaces as a failure and gets
# re-reviewed rather than silently regressing.
TOLERATED_INLINE_SCRIPTS = {
    "dataset.original": (
        "hextra _partials/scripts/mermaid.html — dropped by script-src; "
        "superseded by blog/assets/js/mermaid-init.js"
    ),
}

TAG_RE = re.compile(r"<(script|style|img|link)\b([^>]*)>", re.I | re.S)
ATTR_RE = re.compile(r"""([-\w:]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]*))""")
CANDIDATE_RE = re.compile(r"(\S+)\s+(\d+)w")


def attrs(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in ATTR_RE.finditer(raw):
        out[m.group(1).lower()] = m.group(2) or m.group(3) or m.group(4) or ""
    return out


def external_host(url: str) -> str | None:
    """Return the host if `url` points off-origin, else None."""
    if url.startswith(("//", "http://", "https://")):
        host = urlparse(url if "//" in url[:8] else "https:" + url).netloc
        return host or None
    return None


def check_page(path: Path, rel: str, problems: list[str], tolerated: Counter) -> None:
    html = path.read_text(encoding="utf-8", errors="replace")

    for m in TAG_RE.finditer(html):
        tag = m.group(1).lower()
        a = attrs(m.group(2))

        if tag == "script":
            src = a.get("src", "")
            if not src:
                # Inline script: shipped, parsed, and then dropped by script-src.
                body = html[m.end() : m.end() + 400]
                known = next(
                    (why for mark, why in TOLERATED_INLINE_SCRIPTS.items() if mark in body),
                    None,
                )
                if known:
                    tolerated[known] += 1
                    continue
                snippet = body[:90].replace("\n", " ").strip()
                problems.append(
                    f"{rel}: inline <script> is blocked by script-src 'self' "
                    f"(externalise it into blog/assets/js/) :: {snippet[:70]}"
                )
            elif (host := external_host(src)) and host not in ALLOWED_ORIGINS:
                problems.append(
                    f"{rel}: <script src> from off-origin host {host!r} is blocked by "
                    f"script-src (vendor it into blog/assets/, or widen the CSP)"
                )

        elif tag == "link" and "stylesheet" in a.get("rel", "").lower():
            if (host := external_host(a.get("href", ""))) and host not in ALLOWED_ORIGINS:
                problems.append(
                    f"{rel}: stylesheet from off-origin host {host!r} is blocked by "
                    f"style-src (vendor it into blog/assets/css/)"
                )

        elif tag == "img":
            srcset, width = a.get("srcset", ""), a.get("width", "")
            if not srcset or not width.isdigit():
                continue
            cands = [int(w) for _, w in CANDIDATE_RE.findall(srcset)]
            if not cands:
                continue  # density descriptors: src stays a candidate, fine
            primary = int(width)
            if max(cands) < primary:
                problems.append(
                    f"{rel}: <img> srcset tops out at {max(cands)}w but src is "
                    f"{primary}w — once a srcset uses w descriptors the browser "
                    f"cannot fall back to src, so the full-resolution image is "
                    f"unreachable and it renders upscaled "
                    f"({a.get('src', '?').rsplit('/', 1)[-1]})"
                )


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "blog/public")
    if not root.is_dir():
        print(f"error: built site not found at {root} — run `hugo --minify` first")
        return 2

    pages = sorted(root.rglob("*.html"))
    if not pages:
        print(f"error: no HTML under {root} — did the build produce output?")
        return 2

    problems: list[str] = []
    tolerated: Counter = Counter()
    for p in pages:
        check_page(p, str(p.relative_to(root)), problems, tolerated)

    for why, n in tolerated.most_common():
        print(f"note: tolerated {n}x — {why}")

    if not problems:
        print(f"OK: {len(pages)} pages — no CSP-dropped assets, no unreachable image variants")
        return 0

    # Collapse per-page repeats; the same defect on 111 pages is one defect.
    kinds = Counter(re.sub(r"^[^:]+: ", "", p).split(" ::")[0] for p in problems)
    print(f"FAIL: {len(problems)} problem(s) across {len(pages)} pages\n")
    for kind, n in kinds.most_common():
        print(f"  [{n:5d}x] {kind}")
    print("\nfirst 10 occurrences:")
    for p in problems[:10]:
        print(f"  - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
