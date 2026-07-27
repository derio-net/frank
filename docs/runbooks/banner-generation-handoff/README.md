# Banner image generation — handoff

Everything needed to generate Frank's four series banners, including the prompts
already written and the failure modes already measured. Written 2026-07-25, at the
point of moving generation off the Gemini API to another model.

## 0. Resolution requirement — read before generating

**The banner renders full-bleed at `100vw`.** Its required pixel width is therefore
`viewport_css_px × devicePixelRatio`, with no layout cap to hide behind. That number
is large, and it is the single spec the next generation run has to hit:

| viewport (CSS px) | DPR | device px needed |
|---|---|---|
| 1084 | 2 | 2168 |
| 1512 (14" MBP) | 2 | 3024 |
| 1728 (16" MBP) | 2 | 3456 |
| 2560 (external) | 2 | 5120 |

**Target a native sheet ≥ 3400px wide; ~5000px covers a 2560px external display.**

### Where the current set stands (2026-07-26)

The four shipped banners are `2169×241` (landing `2106×234`). That is *not* a
downscale — `prompt_for_images.yaml` records `aspect_ratio: '3:1'`, `image_size:
native`, and a native 3:1 sheet of `2169×723` cropped to 9:1 is exactly `2169×241`.
It is the generator's full output.

So they are crisp only up to about a **1084px viewport at DPR 2**, and soften from
there: 1.39× upscale at 1512px, 1.59× at 1728px, 2.36× at 2560px. Accepted
deliberately on 2026-07-26 rather than reverting the text-free redesign; recorded
here so the next run fixes it at the source.

For contrast, the pre-2026-07-25 Gemini set was **5088×832 native** (ar 6.12). The
move to Codex is what cost the resolution, not any processing step in this runbook.

### The upscale trap in step 5

Step 5 below normalises the sheet with
`sips --resampleHeightWidth 1280 3840`. **`sips` will happily UPSCALE.** Run that on
a 2169-wide sheet and you get `3834×426` crops that are dimensionally correct and
carry no additional detail — files that look fixed in a directory listing and
identical in a browser.

**Verify the native sheet width BEFORE cropping:**

```bash
sips -g pixelWidth -g pixelHeight <key>-openai-3stripe-source.png
# < 3400 wide → regenerate. Do NOT normalise up and ship it.
```

### Two code-side ceilings to lift in the same change

Both are no-ops today because the assets are smaller than the caps, and both will
silently clip a better asset the moment one lands:

1. `blog/hugo.toml` → `[params.imageOptimize] bannerMaxWidth = 2560`. A 5088-wide
   source is resized down to 2560 on the way in. Raise it to match the new asset.
2. `blog/layouts/partials/opt-image.html` builds srcset rungs `480 / 960 / <primary>`.
   With a much larger primary, a phone needing ~1170px jumps straight to the full
   file; add an intermediate rung (~1920) when the assets grow.

The srcset itself is no longer a limit: frank#710 fixed the clamp that dropped the
top candidate, so the primary's full width is now reachable by the browser. The
asset's native width is the only remaining ceiling.

## Current OpenAI/Codex workflow

Use this workflow for new banner ideation output in this repo. The Gemini notes
below remain useful history, but the current path is:

1. Use the built-in Codex `image_gen` tool, not the old Gemini wrapper.
2. Generate one 3:1 source image arranged as three equal horizontal stripes.
3. Each stripe is a complete standalone version of the same idea, with slight
   pose, lighting, and composition variations.
4. Copy the generated source into the matching `.regen-archive/idea-*/` folder
   using this naming pattern:
   `<key>-openai-3stripe-source.png`
5. Normalize the source to exactly `3840x1280`:
   `<key>-openai-3stripe-3840x1280.png`
   — but check the native width first (§0): `sips` upscales silently, and
   normalising a 2169-wide sheet yields 3834px crops with no added detail.
6. Crop three exact `9:1` banners from that normalized source:
   - `<key>-openai-3stripe-top-9x1.png`
   - `<key>-openai-3stripe-middle-9x1.png`
   - `<key>-openai-3stripe-bottom-9x1.png`

The model path available through Codex does not expose reliable native 6:1,
8:1, or 9:1 canvas control. `gpt-image-2` via API supports flexible dimensions
only up to a `3:1` long-edge ratio. The three-stripe source-sheet trick works
around that limit: a single 3:1 generation becomes three usable 9:1 banners.

Recommended local post-processing:

```bash
sips --resampleHeightWidth 1280 3840 <key>-openai-3stripe-source.png \
  --out <key>-openai-3stripe-3840x1280.png

sips --cropToHeightWidth 426 3834 --cropOffset 0 3 \
  <key>-openai-3stripe-3840x1280.png \
  --out <key>-openai-3stripe-top-9x1.png

sips --cropToHeightWidth 426 3834 --cropOffset 427 3 \
  <key>-openai-3stripe-3840x1280.png \
  --out <key>-openai-3stripe-middle-9x1.png

sips --cropToHeightWidth 426 3834 --cropOffset 854 3 \
  <key>-openai-3stripe-3840x1280.png \
  --out <key>-openai-3stripe-bottom-9x1.png
```

The crop is `3834x426`, exactly `9:1`. The source sheet stays `3840x1280`.

**Ready-to-paste prompts:** `prompts/*.txt` — 24 files, each a fully composed
prompt with its reference images named in the header. That is the fastest path:
open one, attach the listed reference image(s) in order, generate.

---

## 1. Why we're moving

The four banners want an **ultra-wide strip** (~6:1 to 8:1). Measured support:

| model | 16:9 | 21:9 | 4:1 | 8:1 |
|---|---|---|---|---|
| gemini-3-pro-image-preview | 1376×768 | 1584×672 | rejected | rejected |
| gemini-3-pro-image | 1376×768 | 1584×672 | rejected | rejected |
| gemini-3.1-flash-image | 1376×768 | 1584×672 | 2064×512 | 2928×352 |
| gemini-3.1-flash-lite-image | 1376×768 | 1584×672 | 2064×512 | 2928×352 |
| gemini-2.5-flash-image | 1344×768 | 1536×672 | rejected | rejected |

(dimensions at `image_size: 1K`; 2K and 4K scale ×2 and ×4)

Ultra-wide is **flash-only**. The pro models — the ones that produced every good
image — refuse 4:1 and 8:1 outright. The flash models accept the format but are
plainly undertrained in it; see the measured defects in §5.

**Careful with the API's own error message.** A rejected ratio returns a 400
listing `'1:1', '1:4', '1:8', '2:3', '3:2', '3:4', '4:1', '4:3', '4:5', '5:4',
'8:1', '9:16', '16:9', '21:9'`. That is the *service*-wide list, not the model's.
Ask for `8:1` on a pro model and you get a second, different 400: *"Aspect ratio
8:1 is not supported for this model."* Believe the second one.

**If you ever come back to Gemini:** the unexplored path is pro-preview at
`21:9` / `4K` → 6336×2688, cropped to a central band → 6336×792 at 8:1. That is
wider *and* taller than anything flash produced natively, drawn by the good model.
It needs the prose reworked to compose *for the band* (subject in the central
third, discardable headroom above and below) — the opposite of the current
"fill the frame top to bottom" instruction.

---

## 2. What a prompt is made of

Prompts are **layered**, not monolithic. A per-entry `scene` is the only
banner-specific text; everything else is shared prose assembled at generation time.

- **Shared layers** live in `.blog-craft.yaml` under `image.layers`:
  `base_character` (Frank's canonical appearance), `base_atmosphere` (the dark
  server-room look), `reference_guidance` (a map of chunks explaining the
  attached images), `clothing` (per-series outfit tables), `mood` (expression
  presets).
- **Per-entry text** lives in `blog/prompt_for_images.yaml` (the real banners) or
  `ideation-scenes.yaml` (the 20 exploratory scenes, copied here because the
  original lives in gitignored scratch and has been wiped twice).
- **Assembly order** is named in `.blog-craft.yaml` under
  `image.composition_orders`; an entry picks one via
  `composition.order: composition_orders[<name>]`, defaulting to `hero`.

Because of this, **never copy a `scene:` string and call it a prompt** — it is
roughly 20% of what the model actually receives. Use `--print-prompt` (§3) or the
files in `prompts/`.

### Reference-image contract — the part that bites

`composition.reference_images.primary` is sent **first**; everything in
`composition.reference_images.clothing` (a list) follows **in declared order**.
The guidance chunks make positional claims about those images, so the order used
must match the order the prose describes:

| chunk | asserts |
|---|---|
| `character` | "The FIRST reference image is the canonical character-design sheet" |
| `banner_lettering` | "The SECOND reference image is a crop of the exact title lettering" |
| `banner_transform` | "The FIRST reference image is this banner's existing finished artwork" — to be widened, not redrawn |
| `single_hero` | "There is exactly ONE Frank in the final image" |
| `drawing_instructions` | "Redraw Frank from scratch; vary his pose" |

Pick the order whose claims are **true** for the images you actually attach.
Three orders exist:

- `hero` (default) — one reference, a character sheet. Fresh illustration.
- `banner` — two references: character sheet, then lettering crop.
- `banner_transform` — widen existing artwork. Deliberately omits
  `base_character` and `drawing_instructions`, because "redraw Frank from
  scratch, vary his pose" is the exact opposite of preserving artwork.

Mismatching these is a silent failure: the model is told image 2 is a font when
it's a banner, and quietly does something wrong.

---

## 3. Driving the generator

Wrapper: `blog/scripts/generate-images.py`. Use the repo venv — the system
python lacks `google-genai` and `PIL`.

```bash
# see the full composed prompt without spending anything
.venv/bin/python blog/scripts/generate-images.py --print-prompt <key>

# see which reference images would actually be sent, and how many
.venv/bin/python blog/scripts/generate-images.py --dry-run --only <key>

# generate N variants (archives all, writes the LAST to the entry's output:)
.venv/bin/python blog/scripts/generate-images.py --only <key> --count 6

# list every key
.venv/bin/python blog/scripts/generate-images.py --list
```

`--config <file>` selects the config, and **the repo root is taken from that
file's directory** — a config in `/tmp` breaks every relative path. Overrides
therefore have to sit at the repo root.

Output of `--count N`: N images into `.regen-archive/<key>/<key>-<sha>.png`, each
with a `.txt` twin recording the exact prompt, reference and model; a labelled
`contact-sheet.png`; and a copy of the **last** variant at the entry's `output:`
path. Adopting a different one is just `cp`. The archive is FIFO-capped at 30
(`image.curation.archive_cap`).

**Secrets:** `GEMINI_API_KEY` is read live from
`~/.config/fr/secrets/frank/dev.env`. Never inline it.

```bash
set -a; . "$HOME/.config/fr/secrets/frank/dev.env"; set +a
```

**Two 429s that look alike but aren't.** `exceeded its monthly spending cap` is a
policy stop on a billed project — raise it at <https://ai.studio/spend> and it
works. `limit: 0 … FreeTier` is a tier capability stop: image generation is not
sold on the free tier, and no amount of retrying will help. Read the
`QuotaFailure.violations` block, not the first line.

---

## 4. Scripts written during this work

All in the session scratchpad; copy out anything worth keeping.

| script | purpose |
|---|---|
| `gen-banners.sh <count> [model]` | All four banners, with a **preflight**: one cheap call to check the declared aspect ratio is accepted before spending `count × 4` generations. Writes a repo-root model-override config and removes it on exit. |
| `gen-banners-resume.sh <count> <model> <key>...` | Same, but one generator invocation **per key with retries**. Use this. See the failure mode below. |
| `gen-ideation.sh` / `gen-selected.sh` | Batch-run the exploratory scenes. |
| `build_banner_refs.py` | Rebuild the style anchors + the "Building Frank" lettering crop into `.reference-pool/banners/reference/`. |
| `build_ideation.py` / `revise_ideation.py` | Author and revise the 20 exploratory scenes. |

**Why per-key with retries matters:** `generate-images.py` has no retry layer by
design. A single transient `httpx.ReadError` aborts the whole `--only` list, and
because keys run in file order, everything *after* the failure silently gets zero
variants — while the wrapper still exits 0. One run produced 6 variants for the
first banner, 3 for the second and nothing for the last two, reported as success.
**Count archived files per key; do not trust the exit code.**

---

## 5. Measured failure modes

Carry these to whatever model comes next — they are what to check for.

**Pale bottom band.** On flash at 8:1, a white/fog strip across the bottom of the
frame. Present in **13 of 20** images at **13.5%–25% of image height**. Perfectly
correlated with scenes having a visible ground plane; scenes with no floor in
frame were clean. Adding an explicit anti-fog, fill-to-the-bottom-edge clause
lifted the clean rate from 31% to 58% — a suppression, not a cure, and one scene
(`the-balance`) regressed from 0% to 20–26% *because* of the clause.

Detect it mechanically rather than by eye — it is easy to miss in a contact sheet:

```python
from PIL import Image
def pale_bottom_pct(path):
    """% of image height occupied by a pale band at the bottom. >5 is a defect."""
    im = Image.open(path).convert("L"); w, h = im.size
    px = im.resize((64, h)).load(); n = 0
    for y in range(h - 1, -1, -1):
        if sum(px[x, y] for x in range(64)) / 64 > 150: n += 1
        else: break
    return 100 * n / h
```

**Duplicated Frank.** On 8:1 the model clones the subject to fill horizontal
space. The `single_hero` prose was present in all 20 and did not prevent it: five
scenes drew 2–4 Franks. The pattern is compositional — every scene that held to
one figure had a strong **non-Frank horizontal element** spanning the frame (a
crane boom, a schematic table, a row of machines, a scale beam, a monitor wall).
Scenes without one cloned him. Give a wide banner something other than Frank to
span the width.

**Garbled lettering.** Flash mangled roughly half of all rendered titles
("Operatthigroien Frank", "Buding Frank"). Two mitigations, both measured:
attaching a **crop of correct lettering** as a reference lifted the yield from
~50% to ~83%; dropping text entirely removes the failure mode. `banner-landing`
was the only banner clean 6-of-6 all session — it is the one whose prompt ends
*"ABSOLUTELY NO TEXT anywhere in the image."*

**Character drift.** Roughly 1-in-6 even on the pro model — one cover came back
with Frank drawn as a plain human, no green skin or temple bolts. Always review
faces before adopting.

---

## 6. Reference images

`.reference-pool/<series>/reference/` holds character-design sheets — full-body
turnaround, expression row, outfit callouts. Pick the sheet whose outfit matches
the entry's `clothing:` modifier; the sheet is the authority on face, eye style
(solid black with a small white pupil — never white sclera) and costume.

`.reference-pool/banners/reference/` was added during this work and is **not** a
character directory:

- `banner-{landing,operating,building,papers}-style.png` — the shipped 6.12:1
  banners, as layout/palette authority
- `banner-title-lettering.png` — a crop of "Building Frank" with its glow and
  circuit-trace underline, as typeface authority

---

## 7. State at handoff

**Adopted and final:**
- `blog/content/docs/building/36-metrics-api/cover.png` ← `building-36-metrics-api-5b154e5deea6`
- `blog/content/docs/operating/29-metrics-api/cover.png` ← `ops-29-metrics-api-5696265cf52e`

**Uncommitted repo changes:**
- `.blog-craft.yaml` — added `banner` + `banner_transform` composition orders,
  `banner_lettering` + `banner_transform` guidance chunks, `operating[lab_coat]`
- `blog/prompt_for_images.yaml` — four banner entries reworked; `banner-building`
  added (it had artwork on disk but no entry); banners at `aspect_ratio: '8:1'`
- `blog/assets/images/banner-*.png` — **currently hold generated variants, not
  the originals.** `git checkout -- blog/assets/images/` restores the shipped
  6.12:1 versions. The `.reference-pool/banners/` copies are from the originals
  and are unaffected.
- untracked: `.reference-pool/banners/`, the two covers, this directory
- `.blog-craft.ideation.yaml` at the repo root is scratch — safe to delete

**Unresolved:** the banners still need final art. Thirteen exploratory scenes were
shortlisted (see `ideation-scenes.yaml` and `prompts/idea-*.txt`); of those,
`operating-1-the-chair`, `papers-2-the-board` and `building-2-the-forge` never
produced a clean variant on flash, and `papers-3-the-balance` was only clean in
its first generation.

**If banners stay text-free**, the series titles must come from the Hugo template
or each section's `_index.md` — the site currently gets "Building Frank" /
"Operating on Frank" / "The Frank Papers" from the banner images themselves.
