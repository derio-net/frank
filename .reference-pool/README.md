# Reference-pool — character anchors for image generation

Every v5 prompt entry in `blog/prompt_for_images.yaml` declares **exactly one**
reference image — `composition.reference_images.primary` — a character-design
sheet from `<series>/reference/`. What is declared is sent, nothing else;
verify what a run would send with `scripts/generate-images.py --dry-run`.

A character-design sheet is an animation model sheet: a full-body turnaround
(front / three-quarter / side), a row of expression close-ups, and detail
callouts of the outfit's signature props. One sheet per outfit variant, with a
descriptive filename (e.g. `frank-white-shirt-black-tie-1.png`). Sheets anchor
the face, proportions, eye style (large solid-black eyes with a small white
pupil highlight — never white sclera), line work, AND the costume — so pick
the sheet whose outfit matches the entry's `clothing:` modifier.

## Layout

```
.reference-pool/
  README.md
  <series>/                    # one per series in .blog-craft.yaml
    reference-<series>.png     # legacy master ref (fallback for entries
                               #   that declare no primary; unused by v5 entries)
    reference/                 # character-design sheets — the v5 anchors
  generic/
    reference/                 # incl. frank-favicon.png (head-only icon sheet)
```

## Adding a new sheet (new outfit variant)

1. Get a single-figure render of the new outfit (any generation, transparent
   background preferred; on macOS `scripts/extract-subject.swift <in> <out>`
   isolates a figure from a busy cover via Apple Vision).
2. Generate a sheet from it, anchored on 2–3 existing approved sheets so the
   face/eye style stays on-model. The sheet prompt comes from
   `gen-character-sheet.py`'s `build_prompt()` (`image.character_sheet.layers`
   in `.blog-craft.yaml`); attach the render FIRST (costume authority) and the
   approved sheets after (style authority). Known trap: the *startled/surprised*
   expression pulls Gemini toward white-sclera cartoon eyes — pin the
   expression row to neutral / grin / angry / worried.
3. Review every face on the sheet, then drop it in
   `<series>/reference/<outfit-name>.png` and point prompt entries at it.

## Bootstrapping a blog with no sheets at all

`python scripts/gen-character-sheet.py 12` generates candidate master sheets
from `image.layers` prose alone (no art needed) into `.regen-archive/reference/`
(gitignored); browse with `scripts/build-gallery.py`, promote the keeper.
