"""Tests for scripts/lib/contact_sheet.py — pure PIL, no API."""
from pathlib import Path

import pytest
from PIL import Image

from scripts.lib.contact_sheet import (
    build_labels,
    compose_contact_sheet,
    should_compose,
    write_contact_sheet,
)


def test_build_labels_archive_pattern():
    paths = [
        Path("building-33-hermes-shell-4fa9ea19ba2f.png"),
        Path("building-33-hermes-shell-8e62d3bffe90.png"),
    ]
    assert build_labels(paths) == ["1 · 4fa9ea", "2 · 8e62d3"]


def test_build_labels_fallback_to_stem():
    assert build_labels([Path("cover.png")]) == ["1 · cover"]


def test_build_labels_preserves_order():
    paths = [Path(f"k-{i:012x}.png") for i in (0xB, 0xA, 0xC)]
    labels = build_labels(paths)
    assert [label.split(" · ")[0] for label in labels] == ["1", "2", "3"]


def _mk(tmp_path, n, size=(160, 90), name="k-{i:012x}.png"):
    paths = []
    for i in range(n):
        p = tmp_path / name.format(i=i)
        Image.new("RGB", size, (10 * i % 255, 60, 90)).save(p)
        paths.append(p)
    return paths


def test_empty_input_raises(tmp_path):
    with pytest.raises(ValueError):
        compose_contact_sheet([])


def test_grid_8_images_4_cols(tmp_path):
    sheet = compose_contact_sheet(_mk(tmp_path, 8), cols=4, tile_width=160)
    # 8 thumbs at 160x90 → 2 rows of (90 + LABEL_STRIP_PX)
    from scripts.lib.contact_sheet import LABEL_STRIP_PX

    assert sheet.width == 4 * 160
    assert sheet.height == 2 * (90 + LABEL_STRIP_PX)


def test_grid_5_images_has_blank_cells(tmp_path):
    sheet = compose_contact_sheet(_mk(tmp_path, 5), cols=4, tile_width=160)
    from scripts.lib.contact_sheet import BG, LABEL_STRIP_PX

    assert sheet.height == 2 * (90 + LABEL_STRIP_PX)
    # cell (row 2, col 4) stays background
    assert sheet.getpixel((3 * 160 + 80, 90 + LABEL_STRIP_PX + 45)) == BG


def test_mixed_sizes_keep_aspect(tmp_path):
    wide = _mk(tmp_path, 1, size=(320, 90), name="w-{i:012x}.png")
    tall = _mk(tmp_path, 1, size=(90, 320), name="t-{i:012x}.png")
    sheet = compose_contact_sheet(wide + tall, cols=2, tile_width=160)
    # tall image scaled to width 160 → height 569 dominates the row
    from scripts.lib.contact_sheet import LABEL_STRIP_PX

    assert sheet.height == round(320 * 160 / 90) + LABEL_STRIP_PX


def test_label_strip_has_text_pixels(tmp_path):
    sheet = compose_contact_sheet(_mk(tmp_path, 1), cols=1, tile_width=160)
    from scripts.lib.contact_sheet import LABEL_STRIP_PX, STRIP_BG

    strip = sheet.crop((0, 90, 160, 90 + LABEL_STRIP_PX))
    colors = {c for _, c in strip.getcolors(maxcolors=4096)}
    assert colors != {STRIP_BG}  # text rendered → not a uniform strip


def test_contact_sheet_filename_exempt_from_prune_glob(tmp_path):
    """generate-all-images.py prunes .regen-archive/<key>/ with glob
    '<key>-*.png'. The composed sheet must never be eligible. Guards
    the coincidence the generator wiring relies on.

    MIRROR, not a direct call: the glob string here must match the one
    in write_archive_entry's FIFO-cap block (generate-all-images.py —
    see the cross-ref comment there). Change them together."""
    key = "building-33-hermes-shell"
    d = tmp_path / key
    d.mkdir()
    (d / f"{key}-aaaaaaaaaaaa.png").touch()
    (d / "contact-sheet.png").touch()
    assert sorted(p.name for p in d.glob(f"{key}-*.png")) == [
        f"{key}-aaaaaaaaaaaa.png"
    ]


@pytest.mark.parametrize(
    "count,opt_out,dry_run,n,expected",
    [
        (8, False, False, 8, True),
        (1, False, False, 1, False),  # count gate
        (8, True, False, 8, False),  # --no-contact-sheet
        (8, False, True, 0, False),  # --dry-run
        (8, False, False, 1, False),  # < 2 archived (failures)
    ],
)
def test_should_compose(count, opt_out, dry_run, n, expected):
    assert should_compose(count, opt_out, dry_run, n) is expected


def test_write_contact_sheet(tmp_path):
    paths = _mk(tmp_path, 3)
    dest = tmp_path / "contact-sheet.png"
    out = write_contact_sheet(paths, dest)
    assert out == dest and dest.exists()
    assert Image.open(dest).width == 4 * 480  # default cols/tile_width
