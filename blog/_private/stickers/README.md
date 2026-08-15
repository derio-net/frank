# Frank stickers

Die-cut sticker set of Frank — flat white background, wide white bleed, dark-green
(`#1b4332`) keyline cut-guide. Made to print, cut out, and process into physical
stickers.

**Not part of the published blog.** This lives under `blog/_private/`, which Hugo
does not process or copy into `public/` — it's kept in-repo as a reusable asset
only.

Since blog-craft v0.21.1 the generator and sheet-builder are **shipped by
blog-craft**, not hand-rolled here. The old private implementation
(`blog/_private/frank-stickers/`) was retired by `/update`; this directory now
holds only content — the prompts, the curated masters and the print sheets.

## Layout

```
stickers-prompts.yaml   the 18 sticker entries (v5 shape, with sheet/pos)
images/                 the 18 curated masters (sticker-<key>.png)
sheets/                 frank-stickers-A4-sheet{1,2}.png — 300 DPI A4, 3x3 each
```

The two scripts live at `blog/scripts/`, and everything is wired through
`features.stickers` in `.blog-craft.yaml` (paths, paper size, DPI, grid, gutter).
Page pixels are **derived** from `size` + `dpi` (`round(mm / 25.4 * dpi)` per
axis), never configured — so a sheet cannot claim A4 and print at another size.

## Regenerate

```bash
source .env_common                                       # GEMINI_API_KEY
blog/scripts/generate-stickers.py --list                 # show the 18 keys
blog/scripts/generate-stickers.py --dry-run              # full prompt + refs, no API call
blog/scripts/generate-stickers.py --only 22-coffee-b     # regenerate one into ./regen/
```

**Non-destructive by default.** The shim always passes `--out` (default `regen`),
so a regeneration never writes over a curated master. Pick a winner from `regen/`
(a `contact-sheet.png` is written for batches of 2+), copy it over the matching
`images/sticker-<key>.png`, then rebuild the sheets:

```bash
blog/scripts/build-sheets.py
```

A relative `--out` resolves against the **config root** (this repo's root), not
the script directory — a deliberate change from the retired private script, whose
`regen/` sat beside it.

## Notes

- **Prompt composition** is the `sticker` order in `.blog-craft.yaml`:
  `sticker_base_character + sticker_atmosphere + sticker_reference_guidance +
  sticker_face_pins + clothing + sticker_mood + scene + sticker_border_spec`.
  `border_spec` trails `scene` deliberately — the die-cut finish is described
  after the scene it frames. `clothing` and `scene` are shared with the cover
  layers; the rest are sticker-scoped so they cannot collide.
- **`sticker_mood`, not `mood`.** It carries a `_template`
  (`Frank's expression: {}.`), and a `_template` attaches to the *layer* — so
  putting it on the cover `mood` table, whose values are already complete
  sentences, would compose "Frank's expression: Frank's expression is curious —
  …" on every cover.
- **References** (order matters — the first is the face authority): the canonical
  character sheet, then the style anchors (stickers 09 & 20 — head shape, dark
  hair + green edge-glow), then the per-sticker clothing subject. The set
  references two of its own masters as style anchors, which is why those paths
  moved with `images/`.
- **Printing:** print at 100% / "actual size" (**not** "fit to page") so A4 maps
  1:1 and the green keyline stays the exact cut path. The DPI is written into the
  PNG (`pHYs`, 300 dpi = 11811 px/m), which is what makes that work.
- Reference assets (canonical face, clothing subjects) live in the repo's
  `.reference-pool/`; yaml reference paths resolve against the repo root.
