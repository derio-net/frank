"""Tripwire: a body line starting with `+ ` must not interrupt a paragraph.

THE FAILURE. Prose like "Headscale + Caddy" or "hostPort + RollingUpdate" gets
hard-wrapped at the `+`, leaving a line that begins `+ Caddy, or …`. CommonMark
lets a bullet list interrupt a paragraph, so Hugo renders the tail of the
sentence as a list item: the paragraph breaks mid-sentence and a bullet
appears (Paper 20's TL;DR, live since #376; the same wrap in Papers 01, 09
and 14). Nothing in the quality gates saw it — the markdown is valid, the
build is green, and the sentence reads fine in the source.

THE RULE. Outside code fences, a line that starts with `+ ` may only follow a
blank line or another list item. A `+` that belongs to the sentence goes at the
END of the previous line, where a wrap cannot turn it into a marker.
"""
import glob
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTENT = os.path.join(REPO, "blog", "content")
LIST_ITEM = re.compile(r"^\s*([+*-]|\d+[.)])\s")


def _body_lines(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    i = 0
    if lines and lines[0] == "---":
        i = 1
        while i < len(lines) and lines[i] != "---":
            i += 1
        i += 1
    return i, lines


def _offenders():
    out = []
    for path in sorted(glob.glob(os.path.join(CONTENT, "**", "*.md"), recursive=True)):
        start, lines = _body_lines(path)
        in_fence = False
        for n in range(start, len(lines)):
            line = lines[n]
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not line.startswith("+ "):
                continue
            prev = lines[n - 1] if n else ""
            if prev.strip() and not LIST_ITEM.match(prev):
                out.append(f"{os.path.relpath(path, REPO)}:{n + 1}: …{prev[-30:]!r} ⏎ {line[:40]!r}")
    return out


def test_no_plus_marker_interrupts_a_paragraph():
    bad = _offenders()
    assert not bad, (
        "a wrapped `+` became a bullet — move the `+` to the end of the previous line:\n  "
        + "\n  ".join(bad)
    )
