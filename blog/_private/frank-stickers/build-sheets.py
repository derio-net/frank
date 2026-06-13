#!/usr/bin/env python3
"""Lay the selected stickers onto print-ready A4 sheets (3x3 each).

Reads stickers.yaml: each sticker's `sheet` (1-based) and `pos` (1-9, the
3x3 cell, left->right top->bottom) drive placement. Images come from
images/sticker-<key>.png. Output: sheets/frank-stickers-A4-sheet<N>.png
at 300 DPI (2480x3508), white background.

Usage:  python build-sheets.py
"""
from collections import defaultdict
from pathlib import Path

import yaml
from PIL import Image

HERE = Path(__file__).resolve().parent
YAML = HERE / "stickers.yaml"
IMAGES = HERE / "images"
SHEETS = HERE / "sheets"

DPI = 300
A4_W, A4_H = 2480, 3508      # A4 portrait @ 300 DPI
GUTTER = 60


def build_sheet(cells: dict[int, str], dest: Path) -> None:
    """cells: pos(1-9) -> image path stem key."""
    cell = min((A4_W - 4 * GUTTER) // 3, (A4_H - 4 * GUTTER) // 3)
    grid = 3 * cell + 2 * GUTTER
    off_x, off_y = (A4_W - grid) // 2, (A4_H - grid) // 2
    page = Image.new("RGB", (A4_W, A4_H), (255, 255, 255))
    for pos in range(1, 10):
        key = cells.get(pos)
        if not key:
            continue
        src = IMAGES / f"sticker-{key}.png"
        if not src.exists():
            raise SystemExit(f"missing image: {src}")
        r, c = divmod(pos - 1, 3)
        im = Image.open(src).convert("RGB").resize((cell, cell))
        page.paste(im, (off_x + c * (cell + GUTTER), off_y + r * (cell + GUTTER)))
    page.save(dest, dpi=(DPI, DPI))
    print(f"Saved {dest.name}  ({A4_W}x{A4_H} @ {DPI}dpi, cell {cell}px)")


def main():
    cfg = yaml.safe_load(YAML.read_text())
    sheets: dict[int, dict[int, str]] = defaultdict(dict)
    for s in cfg["stickers"]:
        if s.get("sheet") and s.get("pos"):
            sheets[s["sheet"]][s["pos"]] = s["key"]
    SHEETS.mkdir(exist_ok=True)
    for n in sorted(sheets):
        build_sheet(sheets[n], SHEETS / f"frank-stickers-A4-sheet{n}.png")


if __name__ == "__main__":
    main()
