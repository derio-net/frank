# Reference-pool — character anchors for image generation

Reference images are attached to every Gemini call to keep the blog's persona
consistent across covers, tiles, and banners. They stack — compose, don't replace.

1. **Master reference** — `image.reference_image` in `.blog-craft.yaml`
   (default `static/images/reference.png`). The canonical character design sheet.
   Overrides everything for a whole run via
   `scripts/generate-images.py --reference path/to.png`.
2. **Master per-series reference** — auto-picked from
   `<series>/reference-<series>.png` when a prompt entry has `series: <series>`.
   Gives a series its own flavour of the character while staying on-model.
3. **Explicit `references:` on a prompt entry** — hand-picked anchors, usually
   from `<series>/subjects/`. Appended AFTER the master sheet (order is
   load-bearing: the first image is canonical for the face); verify what a run
   would send with `scripts/generate-images.py --dry-run`.

## Building `subjects/` renders

A subject render is a transparent-background, single-figure PNG with a
descriptive filename (e.g. `hero-white-shirt-black-tie-1.png`), promoted by
hand from good generations. On macOS, `scripts/extract-subject.swift` isolates
the foreground figure from a busy cover via Apple Vision:

```
swift scripts/extract-subject.swift <in.png> <out.png>
```

(macOS-only — it needs the Vision framework. Elsewhere any background-removal
tool works; the contract is just "transparent background, exactly one figure".
If a clean subject render already exists, prefer cropping it to its alpha bbox
over re-segmenting a complex scene — auto-segmentation under-performs on busy
compositions.)

## Layout

```
.reference-pool/
  README.md
  generic/
    reference-generic.png      # fallback master ref (entries with no series)
    subjects/                  # hand-curated single-character renders
  <series>/                    # one per series in .blog-craft.yaml (create as needed)
    reference-<series>.png     # master ref for that series
    subjects/                  # series-flavoured character renders
```

## Choosing the master reference (the character design sheet)

The persona + `image.layers.visual_constants` in `.blog-craft.yaml` are enough to
*generate* candidate design sheets — no hand-drawn art required:

1. Generate candidates (source your `.env` for the API key first):
   `python scripts/gen-character-sheet.py 12`
   → writes 12 model sheets + `contact-sheet.png` to `.regen-archive/reference/`
   (the `.regen-archive/` dir is **gitignored**; only keepers are tracked).
2. Browse them full-screen and compare:
   `python scripts/build-gallery.py` → open `.regen-archive/reference/gallery.html`.
3. Promote the best one:
   `cp .regen-archive/reference/reference-<sha>.png static/images/reference.png`
   (optionally also into `generic/reference-generic.png`).
4. Regenerate covers/tiles with the reference in place:
   `python scripts/generate-images.py`

The chosen sheet is what `image.layers.reference_guidance` calls "the canonical
character-design sheet" — every cover's character is drawn to match it.
