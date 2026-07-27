"""Tripwire: no {{< abbr >}} marker may sit inside mermaid diagram source.

THE FAILURE. `glossary_apply.py` skips code fences, headings, links and existing
shortcodes when it inserts markers — but the body of `{{< papers/landscape >}}`
is none of those. It is prose-shaped text that Hugo hands to mermaid as a
quadrantChart definition. Marking an abbreviation there expands to a whole
`<button popovertarget>` + `<span popover>` tree inside a chart axis:

    x-axis <button type=button class=abbr-trigger ...><abbr title="Open Source
    Software">OSS</abbr></button>... --> Commercial

which mermaid cannot parse: `Lexical error on line 4. Unrecognized text.`

WHY A TRIPWIRE RATHER THAN A FIX IN PLACE. Stripping the markers is not
durable — `glossary_apply` is idempotent and marks the FIRST occurrence of a
registry term per post, so the next `/glossary` sweep puts them straight back in
the same four places. Nothing in the tool knows those lines are diagram source.
Reported upstream (blog-craft); until it lands, this test is what makes the
regression loud instead of a red CI run nobody connects to a glossary sweep.

WHERE IT ACTUALLY BIT. The blog-craft mermaid gate was opted out in this repo
(`quality.mermaid_syntax: false`, deferred over a 50-error subgraph-edge
backlog), so the local run was green. The failure surfaced only in
`deploy-blog.yml`'s `node scripts/validate-mermaid.mjs blog/public`, which
validates the RENDERED output and is not governed by that flag. Turning a gate
off hid a defect the same sweep introduced.

NOTE ON SCOPE. `{{< papers/capability-matrix data="vendors" >}}` is
SELF-CLOSING — it reads its rows from a data file and has no body, so nothing
can be marked inside it. Only `papers/landscape` is a paired shortcode whose
body is mermaid source. Treating capability-matrix as paired makes every line
after it look like diagram source, which turns 4 real hits into 116 false ones.
"""
from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
POSTS = sorted((REPO / "blog/content/docs").glob("*/*/index.md"))

_OPEN = re.compile(r"\{\{<\s*papers/landscape\b")
_CLOSE = re.compile(r"\{\{<\s*/\s*papers/landscape\s*>\}\}")
_FENCE = re.compile(r"^```+\s*(\w+)?")
_ABBR = re.compile(r"\{\{<\s*abbr\b")


def _mermaid_source_lines(text: str) -> list[tuple[int, str]]:
    """Line numbers whose content Hugo will hand to mermaid."""
    out, fence, inside = [], None, False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        m = _FENCE.match(stripped)
        if m and fence is None:
            fence = m.group(1) or ""
        elif stripped.startswith("```") and fence is not None:
            fence = None
        if fence is None:
            if _CLOSE.search(stripped):
                inside = False
            elif _OPEN.search(stripped):
                inside = True
        if inside or fence == "mermaid":
            out.append((i, line))
    return out


@pytest.mark.parametrize("post", POSTS, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_no_abbr_marker_in_mermaid_source(post: pathlib.Path) -> None:
    offenders = [
        f"{post.relative_to(REPO)}:{n}  {line.strip()[:80]}"
        for n, line in _mermaid_source_lines(post.read_text(encoding="utf-8"))
        if _ABBR.search(line)
    ]
    assert not offenders, (
        "abbr marker inside mermaid diagram source — the shortcode expands to HTML "
        "that mermaid cannot parse, failing the build:\n  " + "\n  ".join(offenders)
    )
