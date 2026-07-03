#!/usr/bin/env python3
"""Validate paper frontmatter + the weight invariant (config-driven).

weight == paper_number + content_types.papers.weight_offset (default 1).

Library: `validate_paper(fm: dict, weight_offset: int = 1, papers_key: str = "papers") -> list[str]`
CLI:     `validate_papers.py --config <.blog-craft.yaml> <index.md> [<index.md> ...]`
"""
from __future__ import annotations

import re
import sys

REQUIRED_FIELDS = ["title", "date", "draft", "weight", "series", "layer",
                   "paper_number", "publish_order", "status", "tldr"]


def parse_frontmatter(text: str) -> dict:
    import yaml
    if not text.startswith("---"):
        raise ValueError("missing opening `---` frontmatter")
    rest = text.split("\n", 1)[1]
    m = re.search(r"^---\s*$", rest, re.MULTILINE)
    if m is None:
        raise ValueError("missing closing `---` frontmatter")
    data = yaml.safe_load(rest[: m.start()])
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    return data


def _series_contains(series_field, key: str) -> bool:
    if isinstance(series_field, str):
        return series_field == key or key in [s.strip() for s in series_field.split(",")]
    if isinstance(series_field, list):
        return any(s == key for s in series_field if isinstance(s, str))
    return False


def validate_paper(fm: dict, weight_offset: int = 1, papers_key: str = "papers") -> list[str]:
    f: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in fm:
            f.append(f"missing required field: {field}")
    pn = fm.get("paper_number")
    if pn is not None and (not isinstance(pn, int) or pn < 0):
        f.append(f"paper_number must be a non-negative integer, got {pn!r}")
    weight = fm.get("weight")
    if isinstance(pn, int) and pn >= 0:
        expected = pn + weight_offset
        if not isinstance(weight, int):
            f.append(f"weight must be an integer, got {weight!r}")
        elif weight != expected:
            f.append(f"weight invariant: paper_number={pn}, weight={weight}, "
                     f"expected {expected} (weight = paper_number + {weight_offset})")
    if "series" in fm and not _series_contains(fm["series"], papers_key):
        f.append(f"series must contain '{papers_key}', got {fm['series']!r}")
    return f


def _main(argv):
    import argparse
    import yaml
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)
    papers = ((yaml.safe_load(open(a.config)).get("content_types") or {}).get("papers") or {})
    offset = int(papers.get("weight_offset", 1))
    failed = {}
    for p in a.paths:
        try:
            fm = parse_frontmatter(open(p).read())
            fails = validate_paper(fm, offset)
        except (ValueError, Exception) as e:  # noqa: BLE001
            fails = [f"parse error: {e}"]
        if fails:
            failed[p] = fails
    if failed:
        print("PAPER FRONTMATTER VALIDATION FAILED", file=sys.stderr)
        for p, fs in failed.items():
            print(f"  {p}:", file=sys.stderr)
            for x in fs:
                print(f"    x {x}", file=sys.stderr)
        return 1
    print(f"PAPER FRONTMATTER OK: {len(a.paths)} paper(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
