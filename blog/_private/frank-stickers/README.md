# Frank stickers

Die-cut sticker set of Frank — flat white background, wide white bleed, dark-green
(`#1b4332`) keyline cut-guide. Made to print, cut out, and process into physical stickers.

**Not part of the published blog.** This lives under `blog/_private/`, which Hugo does
not process or copy into `public/` — it's kept in-repo as a reusable asset only.

## Layout

```
stickers.yaml        prompt set (shared style + 18 selected stickers, with sheet/pos)
generate-stickers.py regenerate any sticker from the yaml (Gemini image model)
build-sheets.py      compose the 2 print-ready A4 sheets from images/ + yaml sheet/pos
images/              the 18 individual stickers (sticker-<key>.png)
sheets/              frank-stickers-A4-sheet{1,2}.png — 300 DPI A4, 3x3 each
```

## Regenerate

```bash
source .env_common                              # GEMINI_API_KEY
./generate-stickers.py --list                   # show the 18 keys
./generate-stickers.py --only 22-coffee-b       # regenerate one into ./regen/
./generate-stickers.py --only 22-coffee-b --dry-run   # inspect prompt + refs, no API call
```

Pick a winner from `regen/` (a `contact-sheet.png` is written for batches ≥2), copy it
over the matching `images/sticker-<key>.png`, then rebuild the sheets:

```bash
python build-sheets.py
```

## Notes

- **Prompt composition** (per sticker): `base_character + sticker_atmosphere +
  reference_guidance + face_pins + clothing + "Frank's expression: <mood>." + scene +
  border_spec`.
- **References** (order matters — the first is the face authority): `references.canon_face`
  (the canonical character sheet — keeps the no-nose / no-eyebrows / solid-black-eyes face),
  then `references.style_anchors` (stickers 09 & 20 — head shape, dark hair + green edge-glow),
  then the per-sticker clothing subject from `references.subjects_dir`.
- **Printing:** print at 100% / "actual size" (not "fit to page") so A4 maps 1:1 and the
  green keyline stays the exact cut path.
- Reference assets (`canon_face`, clothing subjects) live in the repo's `.reference-pool/`;
  all yaml reference paths resolve against the repo root.
