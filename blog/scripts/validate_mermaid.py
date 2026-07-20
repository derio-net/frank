#!/usr/bin/env python3
"""Lint ```mermaid fences for common syntax errors before render (#27).

A regex linter (no node/mmdc toolchain) that catches high-confidence, dead-on-
render mistakes with file:line:

  - subgraph-targeting edge   an edge endpoint is a declared subgraph id
  - bare <br>                 Hextra's bundled Mermaid wants <br/> (self-closed)
  - unbalanced brackets       [] () {} outside quotes must balance per block

Opt-out with `quality.mermaid_syntax: false` (absent => on). Blocking when on.

Library:
  find_mermaid_blocks(md) -> list[(start_line, src)]
  lint_mermaid_block(src) -> list[(offset, message)]
  validate_file(path, md) -> list[str]   ("path:line: message")
CLI:
  validate_mermaid.py --config <.blog-craft.yaml> <index.md> [<index.md> ...]
"""
from __future__ import annotations

import re
import sys

_EDGE_OPS = re.compile(r"-{2,3}>|-\.->|-\.-|={2,3}>|={3}|-{3}|--[ox]|<-->|o--o|x--x")
_SUBGRAPH = re.compile(r"^\s*subgraph\s+([A-Za-z0-9_-]+)")
_EDGE_LABEL = re.compile(r"\|[^|]*\|")
_BARE_BR = re.compile(r"<br\s*>")   # <br> / <br > — NOT <br/> or <br />


def find_mermaid_blocks(md: str) -> list[tuple[int, str]]:
    """Return (start_line, block_src) per ```mermaid fence.

    start_line is the 1-based line of the first content line inside the fence."""
    blocks: list[tuple[int, str]] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*(`{3,}|~{3,})\s*mermaid\s*$", lines[i])
        if m:
            fence = m.group(1)[0]
            buf, j = [], i + 1
            while j < len(lines) and not re.match(rf"^\s*{re.escape(fence)}{{3,}}\s*$", lines[j]):
                buf.append(lines[j])
                j += 1
            blocks.append((i + 2, "\n".join(buf)))
            i = j + 1
        else:
            i += 1
    return blocks


def _strip_quoted(s: str) -> str:
    return re.sub(r'"[^"]*"', "", s)


def _endpoint_ids(line: str) -> list[str]:
    """Node ids referenced as edge endpoints on this line (quotes/labels removed)."""
    cleaned = _EDGE_LABEL.sub(" ", _strip_quoted(line))
    if not _EDGE_OPS.search(cleaned):
        return []
    ids = []
    for part in _EDGE_OPS.split(cleaned):
        m = re.match(r"\s*([A-Za-z0-9_-]+)", part)
        if m:
            ids.append(m.group(1))
    return ids


def lint_mermaid_block(src: str) -> list[tuple[int, str]]:
    issues: list[tuple[int, str]] = []
    lines = src.splitlines()

    subgraph_ids = {m.group(1) for ln in lines if (m := _SUBGRAPH.match(ln))}

    for idx, line in enumerate(lines):
        # R1 — edge whose endpoint is a subgraph id
        if subgraph_ids:
            for eid in _endpoint_ids(line):
                if eid in subgraph_ids:
                    issues.append((idx, f"edge targets subgraph id '{eid}' — edges "
                                        f"must connect nodes, not subgraphs"))
                    break
        # R2 — bare <br>
        if _BARE_BR.search(line):
            issues.append((idx, "bare <br> — use <br/> (self-closed) for the bundled Mermaid"))

    # R3 — unbalanced brackets across the block (quoted spans removed)
    stripped = _strip_quoted(src)
    for open_c, close_c, name in (("[", "]", "square"), ("(", ")", "round"), ("{", "}", "curly")):
        if stripped.count(open_c) != stripped.count(close_c):
            issues.append((0, f"unbalanced {name} brackets '{open_c}{close_c}' — an "
                              f"unquoted bracket in a label breaks the parse"))

    issues.sort()
    return issues


def validate_file(path: str, md: str) -> list[str]:
    out: list[str] = []
    for start, src in find_mermaid_blocks(md):
        for offset, msg in lint_mermaid_block(src):
            out.append(f"{path}:{start + offset}: {msg}")
    return out


# --------------------------------------------------------------------------- CLI

def _main(argv):
    import argparse
    import yaml
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)

    cfg = yaml.safe_load(open(a.config)) or {}
    if (cfg.get("quality") or {}).get("mermaid_syntax", True) is False:
        print("mermaid syntax check disabled (quality.mermaid_syntax: false)")
        return 0

    failed: dict[str, list[str]] = {}
    checked = 0
    for p in a.paths:
        try:
            md = open(p).read()
        except OSError as e:  # noqa: BLE001
            failed[p] = [f"{p}: could not read: {e}"]
            continue
        checked += 1
        fails = validate_file(p, md)
        if fails:
            failed[p] = fails

    if failed:
        print("MERMAID SYNTAX CHECK FAILED", file=sys.stderr)
        for fs in failed.values():
            for x in fs:
                print(f"  {x}", file=sys.stderr)
        print("\n  Fix the diagram(s), or set `quality.mermaid_syntax: false` to "
              "opt out.", file=sys.stderr)
        return 1
    print(f"MERMAID SYNTAX OK: {checked} file(s) checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
