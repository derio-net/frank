# Reference-pool — character anchors for image generation

Reference images are attached to the image-generation call to keep the blog's
persona consistent across covers, tiles, and banners.

Every **v5** prompt entry declares **exactly one** reference image —
`composition.reference_images.primary` — a character-design sheet from
`<series>/reference/`, plus optional `clothing:` anchors. What is declared is
sent, nothing else: the v4 precedence chain (`image.reference_image`, the
per-series master, the pool) does **not** run for a v5 entry. Verify what a run
would actually send with:

```
scripts/generate-images.py --dry-run
```

Order is load-bearing — the primary is sent FIRST, and
`image.layers.reference_guidance` tells the model that first image is canonical
for the face.

> **Legacy v4 entries** (top-level `prompt` + selector fields, no `composition:`
> block) still resolve through the old chain: `--reference` override →
> `image.reference_image` → `<series>/reference-<series>.png` → entry
> `references:`. One engine serves both, so a blog can migrate entry by entry.
> `tools/migrate_prompts.py` converts v4 entries to v5, freezing whatever the
> chain would have resolved.

## What a character-design sheet is

An animation model sheet: a full-body turnaround (front / three-quarter /
side), a row of expression close-ups, and detail callouts of the outfit's
signature props. One sheet per outfit variant, with a descriptive filename
(e.g. `white-shirt-black-tie-1.png`).

A sheet anchors the face, proportions, eye style, line work **and** the
costume — so point an entry at the sheet whose outfit matches its `clothing:`
modifier, not just any on-model sheet.

## Layout

```
.reference-pool/
  README.md
  <series>/                    # one per series in .blog-craft.yaml
    reference/                 # character-design sheets — the v5 anchors
    reference-<series>.png     # legacy v4 master ref; unused by v5 entries
  generic/
    reference/                 # sheets for entries with no series
                               #   (e.g. a head-only sheet for the favicon)
```

## Adding a new sheet (new outfit variant)

1. Get a single-figure render of the new outfit (any generation; transparent
   background preferred).
2. Generate a sheet from it, anchored on 2–3 already-approved sheets so the
   face and eye style stay on-model. The sheet prompt is built by
   `gen-character-sheet.py`'s `build_prompt()` from
   `image.character_sheet.layers`. Attach the new render FIRST (costume
   authority) and the approved sheets after (style authority).
3. Review every face on the sheet before promoting it, then drop it in
   `<series>/reference/<outfit-name>.png` and point prompt entries at it.

**Known trap:** a *startled / surprised* expression pulls the model toward
generic cartoon eyes, which will not match a stylized persona. Pin the
expression row to steady expressions (neutral / grin / angry / worried).

## Bootstrapping a blog with no sheets at all

`image.layers` prose alone is enough to generate candidates — no hand-drawn art
required:

```
python scripts/gen-character-sheet.py 12   # -> .regen-archive/reference/ (gitignored)
python scripts/build-gallery.py            # browse, then promote the keeper
```

Promote the keeper into `<series>/reference/` (or `generic/reference/`) and
point entries at it.
