#!/usr/bin/env python3
"""Sync Frank Papers dossiers into Hugo data files.

Reads docs/papers-dossiers/<slug>/dossier.md and writes
blog/data/papers/<slug>.yaml. The data file is the single
source the Hugo §8 partial reads at build time.

CLI:
    sync-dossier-to-data.py <slug>           regenerate one
    sync-dossier-to-data.py --all            regenerate all
    sync-dossier-to-data.py --check          CI drift gate

The --output flag (single-slug mode only) overrides the
default blog/data/papers/<slug>.yaml destination — used by
the test suite to write to a tmp dir.
"""
from __future__ import annotations
import argparse
import difflib
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.lib.dossier_parser import parse_dossier, get_primary_sources

DOSSIERS_DIR = REPO_ROOT / "docs" / "papers-dossiers"
DATA_DIR = REPO_ROOT / "blog" / "data" / "papers"


def render(sources: list[dict]) -> str:
    """Serialize sources to a stable YAML string."""
    payload = {"primary_sources": sources}
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=10**9)


def sync_one(slug: str, output: Path | None = None) -> Path:
    dossier = DOSSIERS_DIR / slug / "dossier.md"
    if not dossier.exists():
        raise SystemExit(f"dossier not found: {dossier}")
    sections = parse_dossier(dossier)
    sources = get_primary_sources(sections)
    dest = output if output else DATA_DIR / f"{slug}.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(sources))
    return dest


def check_drift() -> tuple[int, str]:
    """Return (exit_code, diff_text)."""
    diffs: list[str] = []
    for dossier in sorted(DOSSIERS_DIR.glob("*/dossier.md")):
        slug = dossier.parent.name
        sections = parse_dossier(dossier)
        sources = get_primary_sources(sections)
        expected = render(sources)
        actual_path = DATA_DIR / f"{slug}.yaml"
        actual = actual_path.read_text() if actual_path.exists() else ""
        if expected != actual:
            diffs.extend(difflib.unified_diff(
                actual.splitlines(keepends=True),
                expected.splitlines(keepends=True),
                fromfile=f"{actual_path} (on disk)",
                tofile=f"{actual_path} (expected)",
            ))
    if diffs:
        return 1, "".join(diffs)
    return 0, ""


def sync_all() -> list[Path]:
    results = []
    for dossier in sorted(DOSSIERS_DIR.glob("*/dossier.md")):
        slug = dossier.parent.name
        results.append(sync_one(slug))
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="Sync dossiers → blog/data/papers/*.yaml")
    p.add_argument("slug", nargs="?", help="Single dossier slug to sync")
    p.add_argument("--all", action="store_true", help="Sync every dossier")
    p.add_argument("--check", action="store_true", help="Fail on drift (CI mode)")
    p.add_argument("--output", type=Path, help="(single-slug only) write to this path")
    args = p.parse_args()

    if args.check:
        rc, diff = check_drift()
        if rc != 0:
            sys.stderr.write(diff)
            sys.stderr.write("\nFAIL: run `scripts/sync-dossier-to-data.py --all` and commit.\n")
        return rc

    if args.all:
        written = sync_all()
        for path in written:
            try:
                shown = path.relative_to(REPO_ROOT)
            except ValueError:
                shown = path
            print(f"wrote {shown}")
        return 0

    if args.slug and not args.all and not args.check:
        dest = sync_one(args.slug, args.output)
        try:
            shown = dest.relative_to(REPO_ROOT)
        except ValueError:
            shown = dest
        print(f"wrote {shown}")
        return 0
    p.error("must pass <slug>, --all, or --check")


if __name__ == "__main__":
    sys.exit(main())
