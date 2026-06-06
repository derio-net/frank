# Blog Cover Contact Sheet — Design

**Date:** 2026-06-06
**Status:** Draft
**Layer:** `repo` (blog tooling — `scripts/`, agent skills)

## Problem

The blog-post skill generates cover-image variants in batches (`generate-all-images.py --only <key> --count 8`, archived under `.regen-archive/<key>/`) and tells the agent to "show the user the variants and let them pick." How that showing happens is unspecified, so each session improvises: one session composed an ad-hoc overview montage, the next listed eight filenames and made the operator open them one by one. Behavior that lives in a session instead of in the skill evaporates (observed 2026-06-06 — the operator asked where the overview card went; it had never been codified).

## Solution

Three parts: a tested composition module, automatic wiring in the generator, and a codified pick step in the skills.

### 1. `scripts/lib/contact_sheet.py` — composition module

Pure functions, no API calls, PIL-only (Pillow is already in the generator's `uv run --with pillow` set):

```python
def build_labels(paths: list[Path]) -> list[str]:
    """'1 · 8e62d3' — 1-based index + the sha12 prefix parsed from
    '<key>-<sha12>.png' filenames (first 6 chars of sha12 shown).
    Falls back to the bare stem when a filename doesn't match the
    archive pattern."""

def compose_contact_sheet(
    paths: list[Path],
    labels: list[str] | None = None,   # default: build_labels(paths)
    cols: int = 4,
    tile_width: int = 480,
) -> "PIL.Image.Image":
    """Grid of labeled thumbnails. Rows = ceil(n / cols); trailing
    cells stay background-colored. Thumbnails keep their aspect ratio
    scaled to tile_width; a solid label strip (PIL default bitmap
    font, scaled ~3x for legibility at 480px tiles) sits under each
    tile. Raises ValueError on empty paths."""
```

The module raises on empty input and tolerates mixed image sizes (each thumbnail scales independently to `tile_width`; row height = max thumb height in that row + label strip).

### 2. Generator wiring — auto on `--count > 1`

At the end of a `--count N>1` run for a key, `generate-all-images.py` composes `.regen-archive/<key>/contact-sheet.png` from **that run's** archived variants (the paths returned by `write_archive_entry` during the loop — NOT a glob of the archive dir, which may hold older variants), overwriting any previous sheet. Console output prints the sheet path alongside the existing per-variant lines.

- `--no-contact-sheet` opts out.
- `count == 1` or a key whose run produced < 2 archived variants (failures, `--archive-cap 0`): no sheet, no error.
- The FIFO archive cap globs `{key}-*.png`, so `contact-sheet.png` is naturally exempt from pruning — assert this stays true with a test rather than relying on the coincidence silently.
- `--dry-run` does not compose (nothing is generated).

### 3. Skill updates — the codified pick step

**`agents/skills/blog-post/SKILL.md`** (step 4, cover generation — `.claude/skills` is a tracked symlink to `agents/skills`, so the change propagates): after the batch run, the agent

1. **Reads** `.regen-archive/<key>/contact-sheet.png` itself (the Read tool renders images) to pre-screen,
2. presents an **AskUserQuestion** whose options reference tile indices/short hashes with one-line descriptions of each candidate (top 3–4 picks as options; the operator can also open the sheet file directly — include its path in the question text),
3. copies the chosen variant (`.regen-archive/<key>/<key>-<sha>.png`) to the entry's `output` path.

**`agents/skills/papers/SKILL.md`** (cover step): papers covers run through the same generator and inherit the auto sheet; add a one-line pointer to the same Read-sheet-and-AskUserQuestion pick flow.

Out of scope: the `blog-craft` plugin (separate repo) and `/media` (no batch-pick flow).

## Testing

`scripts/tests/test_contact_sheet.py`, pytest, synthetic in-memory PIL images (no fixtures on disk beyond tmp_path, no API):

- `build_labels`: archive-pattern filenames → `"1 · 8e62d3"` form; non-matching names fall back to stems; ordering preserved.
- Grid geometry: 8 images / 4 cols → 2 rows; 5 images → 2 rows with 3 blank cells; 2 images → 1 row; canvas dimensions match `cols × tile_width` and computed row heights.
- Labels render: the label strip region is non-uniform (text pixels present).
- Mixed input sizes scale without distortion (aspect ratios preserved per tile).
- Empty input raises `ValueError`.
- Cap exemption: a file named `contact-sheet.png` in an archive dir does not match the `{key}-*.png` prune glob (regression guard for the generator's FIFO cap).

Generator wiring is verified by a thin integration test that monkeypatches the generation call and asserts the sheet lands for `count=2` and is absent for `count=1` — if the generator's structure makes that disproportionate, the wiring assertions (this-run paths only, opt-out flag, count gate) move to a code-review checklist item in the plan instead, and the module tests remain the hard gate.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-06-06--repo--blog-cover-contact-sheet | `derio-net/frank` | `docs/superpowers/plans/2026-06-06--repo--blog-cover-contact-sheet/` | — |
