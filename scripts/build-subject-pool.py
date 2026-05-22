#!/usr/bin/env python3
"""Lift Frank-subjects from every cover/banner/archive image and drop them
into .reference-pool/<series>/subjects/ for curation.

Backed by scripts/extract-subject.swift, which uses Apple Vision's
VNGenerateForegroundInstanceMaskRequest (same code path as Preview's
"subject lift"). Each output PNG has a transparent background.

Routing:
  blog/content/docs/papers/<slug>/cover.png      → papers/subjects/<slug>.png
  blog/content/docs/building/<slug>/cover.png    → building/subjects/<slug>.png
  blog/content/docs/operating/<slug>/cover.png   → operating/subjects/<slug>.png
  blog/static/images/{banner,tile}-papers.*      → papers/subjects/<basename>
  blog/static/images/{banner,tile}-building.*    → building/subjects/<basename>
  blog/static/images/{banner,tile}-operating.*   → operating/subjects/<basename>
  blog/static/images/* (other Frank assets)      → generic/subjects/<basename>
  .regen-archive/<key>/<file>.png (opt-in)       → <series>/subjects/archive-<key>-<sha>.png

Usage:
    ./scripts/build-subject-pool.py                # covers + static-image refs
    ./scripts/build-subject-pool.py --include-archive   # also walk .regen-archive/
    ./scripts/build-subject-pool.py --force        # re-lift even if output exists
    ./scripts/build-subject-pool.py --dry-run      # show what would be done
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACTOR = REPO_ROOT / "scripts" / "extract-subject.swift"
POOL = REPO_ROOT / ".reference-pool"

# Mapping rules.  Each rule is (source-glob, target-fn).  target-fn takes the
# matched Path and returns the destination Path under .reference-pool/.
SERIES_FOR_PREFIX = {
    "paper-": "papers",
    "building-": "building",
    "ops-": "operating",
    "operating-": "operating",
}


def _series_from_static_basename(name: str) -> str | None:
    """`banner-papers.png` → 'papers'; `tile-building.png` → 'building'.
    Returns None when the static asset is not series-coded (e.g. banner-landing).
    """
    for suffix in ("papers", "building", "operating"):
        if f"-{suffix}" in name:
            return suffix
    return None


def _walk_covers() -> list[tuple[Path, Path]]:
    """One subject per published cover."""
    pairs: list[tuple[Path, Path]] = []
    for series in ("papers", "building", "operating"):
        for cover in (REPO_ROOT / "blog" / "content" / "docs" / series).glob("*/cover.png"):
            slug = cover.parent.name
            dest = POOL / series / "subjects" / f"{slug}.png"
            pairs.append((cover, dest))
    return pairs


def _walk_static() -> list[tuple[Path, Path]]:
    """Banner / tile / hero / favicon — Frank-bearing site furniture."""
    pairs: list[tuple[Path, Path]] = []
    static = REPO_ROOT / "blog" / "static" / "images"
    for src in static.glob("*.png"):
        # Skip reference.png — it's the canonical character design sheet,
        # not a "subject in scene" we want to lift.
        if src.name == "reference.png":
            continue
        series = _series_from_static_basename(src.name)
        bucket = series if series else "generic"
        dest = POOL / bucket / "subjects" / src.name
        pairs.append((src, dest))
    return pairs


def _walk_archive() -> list[tuple[Path, Path]]:
    """.regen-archive iterations — large pool of historical Franks for
    curation. Series is derived from the per-key folder name's prefix.
    """
    pairs: list[tuple[Path, Path]] = []
    archive = REPO_ROOT / ".regen-archive"
    if not archive.exists():
        return pairs
    for key_dir in sorted(archive.iterdir()):
        if not key_dir.is_dir():
            continue
        series = None
        for prefix, name in SERIES_FOR_PREFIX.items():
            if key_dir.name.startswith(prefix):
                series = name
                break
        if series is None:
            series = "generic"
        for png in sorted(key_dir.glob("*.png")):
            # File names already include the key + sha shortname.
            dest = POOL / series / "subjects" / f"archive-{png.stem}.png"
            pairs.append((png, dest))
    return pairs


def lift(src: Path, dest: Path, force: bool, dry: bool) -> tuple[str, str]:
    """Run the Swift extractor for one image. Returns (status, detail)."""
    rel_src = src.relative_to(REPO_ROOT)
    rel_dest = dest.relative_to(REPO_ROOT)
    if dest.exists() and not force:
        return ("skipped", f"{rel_dest} (exists)")
    if dry:
        return ("would-lift", f"{rel_src} → {rel_dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [str(EXTRACTOR), str(src), str(dest)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return ("error", f"{rel_src}: {exc}")
    if result.returncode == 0:
        return ("ok", f"{rel_src} → {rel_dest}")
    if result.returncode == 1:
        # Vision found no foreground. Subsequent runs WILL retry this file
        # (dest still doesn't exist) — Vision is cheap and idempotent, so
        # retrying is harmless. If you want to permanently skip a known
        # foreground-less source, delete it from the walk roots.
        return ("no-subject", f"{rel_src} (Vision: no foreground instance)")
    return ("error", f"{rel_src}: {result.stderr.strip() or 'extractor failed'}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--include-archive",
        action="store_true",
        help="Also process every PNG under .regen-archive/ (slow, large output volume).",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Re-lift even when the output already exists.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="List what would be lifted; don't write anything.",
    )
    args = p.parse_args()

    if not EXTRACTOR.exists() or not EXTRACTOR.stat().st_mode & 0o111:
        print(f"error: {EXTRACTOR} not found or not executable", file=sys.stderr)
        print("Run: chmod +x scripts/extract-subject.swift", file=sys.stderr)
        sys.exit(2)

    pairs = _walk_covers() + _walk_static()
    if args.include_archive:
        pairs += _walk_archive()

    if not pairs:
        print("Nothing to lift.")
        return

    counts: dict[str, int] = {"ok": 0, "skipped": 0, "no-subject": 0, "error": 0, "would-lift": 0}
    for src, dest in pairs:
        status, detail = lift(src, dest, force=args.force, dry=args.dry_run)
        counts[status] = counts.get(status, 0) + 1
        prefix = {
            "ok": "  +",
            "skipped": "  =",
            "no-subject": "  ?",
            "error": "  !",
            "would-lift": "  ~",
        }.get(status, "   ")
        print(f"{prefix} {detail}")

    print()
    print("=" * 60)
    print(f"  Processed {len(pairs)} sources:")
    for k, v in counts.items():
        if v:
            print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
