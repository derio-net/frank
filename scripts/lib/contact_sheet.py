"""Compose a labeled contact sheet from cover-variant images.

Used by generate-all-images.py after a --count>1 batch so the operator
picks from ONE grid image instead of opening every archived variant.
Pure PIL — no API calls, no repo state.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Archive filenames are <key>-<sha12>.png (write_archive_entry in
# generate-all-images.py); the stem therefore ends in 12 hex chars.
_ARCHIVE_RE = re.compile(r"^(?P<key>.+)-(?P<sha>[0-9a-f]{12})$")

LABEL_STRIP_PX = 36
BG = (24, 24, 28)
STRIP_BG = (12, 12, 14)
FG = (230, 230, 235)


def _label_font():
    try:
        return ImageFont.load_default(size=20)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def build_labels(paths: list[Path]) -> list[str]:
    """'1 · 8e62d3' — 1-based index + sha prefix from archive filenames.

    Falls back to the bare stem when a filename doesn't match the
    archive pattern.
    """
    labels = []
    for i, p in enumerate(paths, 1):
        m = _ARCHIVE_RE.match(p.stem)
        suffix = m.group("sha")[:6] if m else p.stem
        labels.append(f"{i} · {suffix}")
    return labels


def compose_contact_sheet(
    paths: list[Path],
    labels: list[str] | None = None,
    cols: int = 4,
    tile_width: int = 480,
) -> Image.Image:
    """Grid of labeled thumbnails.

    Rows = ceil(n / cols); trailing cells stay background-colored.
    Thumbnails keep their aspect ratio scaled to tile_width; a solid
    label strip sits in the bottom LABEL_STRIP_PX band of each row.
    Raises ValueError on empty paths.
    """
    if not paths:
        raise ValueError("no images to compose")
    if labels is None:
        labels = build_labels(paths)

    thumbs = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        h = round(im.height * tile_width / im.width)
        thumbs.append(im.resize((tile_width, h)))

    rows = math.ceil(len(thumbs) / cols)
    row_heights = [
        max(t.height for t in thumbs[r * cols : (r + 1) * cols]) + LABEL_STRIP_PX
        for r in range(rows)
    ]

    sheet = Image.new("RGB", (cols * tile_width, sum(row_heights)), BG)
    draw = ImageDraw.Draw(sheet)
    font = _label_font()

    y = 0
    for r in range(rows):
        strip_y = y + row_heights[r] - LABEL_STRIP_PX
        for c, t in enumerate(thumbs[r * cols : (r + 1) * cols]):
            x = c * tile_width
            sheet.paste(t, (x, y))
            draw.rectangle(
                [x, strip_y, x + tile_width - 1, strip_y + LABEL_STRIP_PX - 1],
                fill=STRIP_BG,
            )
            draw.text((x + 8, strip_y + 8), labels[r * cols + c], fill=FG, font=font)
        y += row_heights[r]
    return sheet
