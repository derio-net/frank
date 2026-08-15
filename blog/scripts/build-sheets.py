#!/usr/bin/env python3
"""Lay the configured stickers onto print-ready sheets (blog-craft, features.stickers).

A port of frank's private `blog/_private/frank-stickers/build-sheets.py`, with its
four hardcoded constants replaced by config. Each sticker entry's `sheet` (1-based)
and `pos` (1-based cell, left->right then top->bottom) drive placement; the image
comes from the entry's `output:` (frank's `<images_dir>/sticker-<key>.png` when an
entry declares none). Output: `<sheets_dir>/<sheets_prefix>-<SIZE>-sheet<N>.png`,
with the paper's DPI written into the PNG.

Config (`.blog-craft.yaml`):

    features:
      stickers:
        prompts_file: blog/_private/stickers/stickers-prompts.yaml
        images_dir:   blog/_private/stickers/images
        sheets_dir:   blog/_private/stickers/sheets
        sheets_prefix: frank-stickers          # default: <slug(project.name)>-stickers
        sheet: { size: a4, dpi: 300, grid: [3, 3], gutter: 60 }

WHY the page pixels are DERIVED and not configured. frank hardcoded
`A4_W, A4_H = 2480, 3508`; there is no config key for them, and adding one would
let `size: a4` and an inconsistent pixel size disagree — a wrong-sized page that
prints wrong. So the page comes from `size` + `dpi` against a millimetre table:
`round(210 / 25.4 * 300) == 2480` and `round(297 / 25.4 * 300) == 3508`, which are
*exactly* frank's constants (and exactly the IHDR of his committed sheets). The
derivation is not a linear scale — at 600 dpi the A4 width is 4961, not 4960 — so
the rounding is part of the contract.

`sheet.size` is deliberately NOT validated by `tools/validate_config.py`: the
paper vocabulary belongs here, so the table can grow without a validator change.
That makes THIS script the only guard, and an unknown size must be a hard error —
never a silent fallback to A4.

WHY the DPI is written into the file: `page.save(dest, dpi=(dpi, dpi))` is what
makes "print at 100%" map the page 1:1 onto the paper, which is what keeps the
dark-green keyline a literal cut path rather than decoration. PNG stores this as
integer pixels-per-metre, so 300 dpi is 11811 px/m.

`grid` is honoured, not decorative: frank hardcoded `3` in five places, so
`[cols, rows]` is a rewrite of the gutter algebra (`(cols+1)`/`(cols-1)` were
specialised to `4 *`/`2 *`) plus a change to `pos`'s valid range. For `[3, 3]` the
generalised form reproduces frank's numbers exactly; `tests/unit/test_build_sheets.py`
pins that equality and a non-3x3 case.

Usage:  python build-sheets.py [--config <.blog-craft.yaml>]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

MM_PER_INCH = 25.4
# Paper vocabulary, in MILLIMETRES. Additive: a new size is one row here.
SIZES = {
    "a4": (210.0, 297.0),
    "letter": (215.9, 279.4),
}
DEFAULT_SIZE = "a4"
DEFAULT_DPI = 300
DEFAULT_GUTTER = 60
DEFAULT_GRID = (3, 3)


def find_config(start: Path) -> Path:
    d = start.resolve()
    for cand in [d, *d.parents]:
        f = cand / ".blog-craft.yaml"
        if f.is_file():
            return f
    raise SystemExit("no .blog-craft.yaml found from " + str(start))


def slug(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(name).lower())).strip("-")


def page_pixels(size: str, dpi: int) -> tuple[int, int]:
    """`round(mm / 25.4 * dpi)` per axis. SystemExit on an unknown size."""
    try:
        mm_w, mm_h = SIZES[size]
    except KeyError:
        raise SystemExit(
            f"unknown features.stickers.sheet.size: {size!r} — known sizes: "
            f"{', '.join(sorted(SIZES))}. Add the paper's millimetre dimensions to "
            f"SIZES in build-sheets.py rather than guessing a page."
        ) from None
    return round(mm_w / MM_PER_INCH * dpi), round(mm_h / MM_PER_INCH * dpi)


def geometry(w: int, h: int, gutter: int, cols: int, rows: int) -> tuple[int, int, int]:
    """`(cell, off_x, off_y)` for a CENTRED cols x rows grid of square cells.

    The generalisation of frank's hardcoded 3x3: his `(W - 4*G)//3` is
    `(W - (cols+1)*G)//cols` and his `3*cell + 2*G` is `cols*cell + (cols-1)*G`.
    """
    cell = min((w - (cols + 1) * gutter) // cols, (h - (rows + 1) * gutter) // rows)
    if cell < 1:
        raise SystemExit(
            f"features.stickers.sheet: a {cols}x{rows} grid with gutter {gutter} does "
            f"not fit on a {w}x{h} page (cell would be {cell}px)"
        )
    grid_w, grid_h = cols * cell + (cols - 1) * gutter, rows * cell + (rows - 1) * gutter
    return cell, (w - grid_w) // 2, (h - grid_h) // 2


def build_sheet(cells: dict, dest: Path, w: int, h: int, dpi: int, gutter: int,
                cols: int, rows: int) -> None:
    """`cells: pos -> (key, image path)`."""
    from PIL import Image
    cell, off_x, off_y = geometry(w, h, gutter, cols, rows)
    page = Image.new("RGB", (w, h), (255, 255, 255))
    for pos in range(1, cols * rows + 1):
        placed = cells.get(pos)
        if not placed:
            continue
        key, src = placed
        # LOUD, never a blank cell: a hole in a printed sheet costs paper and ink.
        if not src.exists():
            raise SystemExit(f"missing image: {src} (sticker {key}, sheet cell {pos})")
        r, c = divmod(pos - 1, cols)
        im = Image.open(src).convert("RGB").resize((cell, cell))
        page.paste(im, (off_x + c * (cell + gutter), off_y + r * (cell + gutter)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.save(dest, dpi=(dpi, dpi))
    print(f"Saved {dest.name}  ({w}x{h} @ {dpi}dpi, cell {cell}px)")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Build print-ready sticker sheets.")
    ap.add_argument("--config", help="path to .blog-craft.yaml (default: search upward)")
    a = ap.parse_args(argv)

    cfg_path = Path(a.config) if a.config else find_config(Path.cwd())
    root = cfg_path.parent
    cfg = yaml.safe_load(cfg_path.read_text()) or {}
    stk = ((cfg.get("features") or {}).get("stickers")) or {}
    if not isinstance(stk, dict) or not stk:
        raise SystemExit(f"features.stickers is not configured in {cfg_path} — "
                         f"nothing to lay out")
    # NOTE: `enabled` is deliberately not re-checked here. The gate lives at
    # materialization (tools/bootstrap-render.sh only ships this script when
    # features.stickers.enabled is true); re-gating a purely local composition of
    # already-generated images would only strand an operator who flipped the flag
    # off after curating a set.
    for req in ("prompts_file", "images_dir", "sheets_dir"):
        if not str(stk.get(req) or "").strip():
            raise SystemExit(f"features.stickers.{req} must be set in {cfg_path}")

    prompts = root / stk["prompts_file"]
    if not prompts.is_file():
        raise SystemExit(f"sticker prompts file not found: {prompts} "
                         f"(features.stickers.prompts_file)")
    entries = (yaml.safe_load(prompts.read_text()) or {}).get("images") or []

    sheet_cfg = stk.get("sheet") or {}
    size = str(sheet_cfg.get("size", DEFAULT_SIZE))
    dpi = int(sheet_cfg.get("dpi", DEFAULT_DPI))
    gutter = int(sheet_cfg.get("gutter", DEFAULT_GUTTER))
    grid = sheet_cfg.get("grid") or list(DEFAULT_GRID)
    if not (isinstance(grid, (list, tuple)) and len(grid) == 2):
        raise SystemExit(f"features.stickers.sheet.grid must be [cols, rows] (got {grid!r})")
    cols, rows = int(grid[0]), int(grid[1])
    if cols < 1 or rows < 1:
        # Same judgement as `_contact_sheet(cols=0)`: a computed grid dimension of
        # zero is a caller/config bug, and a plausible-looking sheet would hide it.
        raise SystemExit(f"features.stickers.sheet.grid must be positive "
                         f"[cols, rows] (got {grid!r})")

    w, h = page_pixels(size, dpi)
    geometry(w, h, gutter, cols, rows)   # fail before creating anything
    images_dir = root / stk["images_dir"]
    prefix = str(stk.get("sheets_prefix") or "").strip() or \
        f"{slug((cfg.get('project') or {}).get('name') or 'blog')}-stickers"

    sheets: dict = defaultdict(dict)
    for e in entries:
        # frank's own skip rule: a sticker with no sheet/pos is not on a sheet.
        if not (e.get("sheet") and e.get("pos")):
            continue
        key = e.get("key")
        pos = int(e["pos"])
        if not 1 <= pos <= cols * rows:
            raise SystemExit(
                f"{key}: pos {pos} is outside 1..{cols * rows} for "
                f"features.stickers.sheet.grid [{cols}, {rows}]"
            )
        src = (root / e["output"]) if e.get("output") else images_dir / f"sticker-{key}.png"
        n = int(e["sheet"])
        # LOUD, never last-wins. frank's `sheets[s["sheet"]][s["pos"]] = key`
        # silently kept the LAST claimant, so the other sticker was simply absent
        # from a page the operator PRINTS and CUTS — paper, ink and manual cutting
        # spent before anyone notices. `pos` out of range is already an error; this
        # is the same class of mistake and gets the same treatment. It is a
        # behaviour change against frank's code, and an unobservable one for his
        # data: his 18 stickers occupy 18 distinct (sheet, pos) pairs (measured,
        # pinned by test_franks_real_eighteen_still_build_both_sheets).
        if pos in sheets[n]:
            other = sheets[n][pos][0]
            raise SystemExit(
                f"duplicate placement: sheet {n}, cell {pos} is claimed by both "
                f"{other!r} and {key!r} — one of them would silently vanish from a "
                f"printed sheet. Give each sticker its own (sheet, pos) in "
                f"{prompts}."
            )
        sheets[n][pos] = (key, src)

    if not sheets:
        print(f"no stickers declare sheet/pos in {prompts} — nothing to build")
        return 0

    sheets_dir = root / stk["sheets_dir"]
    for n in sorted(sheets):
        dest = sheets_dir / f"{prefix}-{size.upper()}-sheet{n}.png"
        build_sheet(sheets[n], dest, w, h, dpi, gutter, cols, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
