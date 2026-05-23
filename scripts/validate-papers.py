#!/usr/bin/env python3
"""Validate Frank Paper frontmatter against the schema and weight invariant.

Usage:
  python scripts/validate-papers.py <path1> <path2> ...   # specific files
  python scripts/validate-papers.py --all                  # scan every paper bundle
  python scripts/validate-papers.py --check                # alias for --all

Exit 0 = all papers pass. Exit 1 = at least one failure (prints per-file
failure summary).

Checks per paper:
  * `weight == paper_number + 1` (catches `weight: 0` and any drift).
  * `paper_number` exists and is a non-negative integer.
  * Required frontmatter fields present:
      title, date, draft, weight, series, layer, paper_number,
      publish_order, status, tldr.
  * `series` contains "papers" (string-membership or list-membership).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
PAPERS_GLOB = "blog/content/docs/papers/*/index.md"

REQUIRED_FIELDS = [
    "title",
    "date",
    "draft",
    "weight",
    "series",
    "layer",
    "paper_number",
    "publish_order",
    "status",
    "tldr",
]


def parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a Hugo Markdown bundle.

    Returns the parsed mapping, or raises ValueError if no frontmatter found.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        raise ValueError("missing opening `---` frontmatter delimiter")
    # Strip the leading delimiter and find the closing one — match a line that
    # is exactly `---` so a horizontal-rule literal in the body can't false-match.
    rest = text.split("\n", 1)[1]
    closer = re.search(r"^---\s*$", rest, re.MULTILINE)
    if closer is None:
        raise ValueError("missing closing `---` frontmatter delimiter")
    fm_text = rest[: closer.start()]
    data = yaml.safe_load(fm_text)
    if not isinstance(data, dict):
        raise ValueError(f"frontmatter did not parse as a mapping (got {type(data).__name__})")
    return data


def series_contains_papers(series_field) -> bool:
    """Match both `series: papers` (str) and `series: ["papers", ...]` (list)."""
    if isinstance(series_field, str):
        return series_field == "papers" or "papers" in [s.strip() for s in series_field.split(",")]
    if isinstance(series_field, list):
        return any(isinstance(s, str) and s == "papers" for s in series_field)
    return False


def validate_paper(path: Path) -> list[str]:
    """Return a list of failure strings (empty == pass)."""
    failures: list[str] = []
    try:
        fm = parse_frontmatter(path)
    except (ValueError, yaml.YAMLError) as exc:
        return [f"frontmatter parse error: {exc}"]

    # Required-fields check
    for field in REQUIRED_FIELDS:
        if field not in fm:
            failures.append(f"missing required field: {field}")

    # paper_number validity
    pn = fm.get("paper_number")
    if pn is None:
        # Already reported by missing-field check; skip downstream weight check.
        pass
    elif not isinstance(pn, int) or pn < 0:
        failures.append(f"paper_number must be a non-negative integer, got {pn!r}")

    # weight invariant: weight == paper_number + 1
    weight = fm.get("weight")
    if isinstance(pn, int) and pn >= 0:
        if not isinstance(weight, int):
            failures.append(f"weight must be an integer, got {weight!r}")
        else:
            expected = pn + 1
            if weight != expected:
                failures.append(
                    f"weight invariant violated: paper_number={pn}, "
                    f"weight={weight}, expected {expected} "
                    f"(convention: weight = paper_number + 1)"
                )

    # series membership
    if "series" in fm and not series_contains_papers(fm["series"]):
        failures.append(f"series must contain 'papers', got {fm['series']!r}")

    return failures


def gather_paths(args: list[str]) -> list[Path]:
    if not args:
        print("Usage: validate-papers.py [--all | --check | <path1> <path2> ...]", file=sys.stderr)
        sys.exit(2)
    if args[0] in ("--all", "--check"):
        if len(args) > 1:
            print(f"ERROR: {args[0]} takes no additional arguments", file=sys.stderr)
            sys.exit(2)
        paths = sorted(REPO_ROOT.glob(PAPERS_GLOB))
        if not paths:
            print(f"ERROR: no papers found under {PAPERS_GLOB}", file=sys.stderr)
            sys.exit(1)
        return paths
    return [Path(a) for a in args]


def main(argv: list[str]) -> int:
    paths = gather_paths(argv[1:])

    all_failures: dict[Path, list[str]] = {}
    for p in paths:
        if not p.exists():
            all_failures[p] = ["file not found"]
            continue
        failures = validate_paper(p)
        if failures:
            all_failures[p] = failures

    if all_failures:
        print("PAPER FRONTMATTER VALIDATION FAILED", file=sys.stderr)
        for path, fails in all_failures.items():
            try:
                rel = path.relative_to(REPO_ROOT)
            except ValueError:
                rel = path
            print(f"  {rel}:", file=sys.stderr)
            for f in fails:
                print(f"    ✗ {f}", file=sys.stderr)
        return 1

    print(f"PAPER FRONTMATTER OK: {len(paths)} paper(s) validated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
