# Frank series-index re-sync onto blog-craft — design

**Layer:** repo (blog infra / tooling meta)
**Date:** 2026-07-04
**Status:** Deployed
**Follows:** frank #605 (series-index adoption), blog-craft #12 (standardization)

## Problem

Frank #605 shipped a card-based series index by **hand-writing** frank-local
copies of three shortcodes plus a palette generator:

- `blog/layouts/shortcodes/series-index.html` — card layout with a **hardcoded
  21-entry `$nameOf` dict** inline in the template.
- `blog/scripts/gen-layer-palette.py` — OKLCH generator with a **hardcoded
  `ORDER` list** of 21 codes + 2 aliases.
- `blog/data/layer_palette.yaml` — the generated palette (no `name` field).
- `blog/layouts/shortcodes/roadmap.html` — reworked onto the palette.

Blog-craft #12 then **generalized** these into registry-driven, standardized
templates on `main` (SHA `a7f2f7f`):

- `templates/hugo-hextra/layouts/shortcodes/series-index.html` — branches on
  `site.Params.seriesIndex.style` (`cards` default | `table` | `none`); cards
  colour-coded from `site.Data.layer_palette.layers`, **layer name read from the
  palette data** (not a hardcoded dict).
- `tools/gen-layer-palette.py` — **registry-driven**: reads
  `series_index.layers` (`{code, name}`) from a blog's `.blog-craft.yaml` and
  **writes `name` into each palette entry**. Identical OKLCH engine.
- `templates/hugo-hextra/layouts/shortcodes/roadmap.html` — palette-driven,
  neutral-fallback.

Frank now carries a **divergent copy** of code that lives, generalized, in
blog-craft. This re-sync drops frank's copies and puts frank on blog-craft's
tracked update flow, with **zero visual change** to the live blog.

## Operator decisions (batched Q&A, 2026-07-04)

1. **Sync mechanism → full `update.py` re-sync** (not a one-time vendor). Frank
   adopts blog-craft's tracked 3-way-merge update flow; this PR is its first run,
   curated to the series-index surface (see §"Curated update", below).
2. **`papers-roadmap.html` → leave frank-local as-is.** It is frank-specific
   (papers roster + Published/deferred status) and already reads
   `layer_palette.yaml`, so it inherits the regenerated palette automatically.
3. **Post-merge Test Plan → full 3-series × light/dark eyeball** of the live
   blog (see §"Test Plan").

The operator was told, and accepted, the **one cosmetic delta**: blog-craft's
standardized `series-index.html` styles the layer-name tag at `font-weight: 600`
where frank's #605 copy used `500`. Every colour and all other markup is
byte-identical.

## What is proven vs assumed

Measured before design (not assumed):

- **Colour identity — PROVEN.** Blog-craft's registry generator, run over
  frank's 21 codes in frank's `ORDER`, emits **byte-identical**
  `light/dark/lt/dt` for all 21 codes. `_perm_step(21) == 8 == frank's hardcoded
  `PERM_STEP`. The only palette-data diffs are additive (`name` field) and the
  2 alias entries the registry generator does not emit.
- **Update surface — MEASURED.** `update.py` dry-run against frank's blog
  (frank config + `series_index` block, staging from blog-craft@`a7f2f7f`)
  produces exactly:

  ```
  ADD      .github/workflows/blog-ci.yml            [merged]     ← EXCLUDE (frank has own CI)
  ADD      .gitignore                               [framework]  ← DEFER (unrelated scaffold)
  ADD      .hookify.warn-hextra-weight-zero.md      [framework]  ← DEFER (unrelated scaffold)
  ADD      README.md                                [merged]     ← EXCLUDE (frank blog has none)
  CONFLICT hugo.toml                                [merged]     ← MERGE by hand (add seriesIndex param)
  REPLACE  layouts/shortcodes/papers-roadmap.html   [framework]  ← EXCLUDE (operator: leave as-is)
  REPLACE  layouts/shortcodes/roadmap.html          [framework]  ← APPLY (reconcile)
  REPLACE  layouts/shortcodes/series-index.html     [framework]  ← APPLY (the point)
  ADD      static/images/.gitkeep                   [framework]  ← DEFER (unrelated scaffold)
  ```

  No `assets/css/**` and no `scripts/**` appear → **frank's CSS and scripts
  already match blog-craft** (zero CSS drift). Layouts are copied **verbatim**
  by bootstrap (not go-templated), so a "REPLACE" of a shortcode is a direct
  byte-copy of blog-craft's template.

- **Version-pin snag — CONFIRMED.** Frank records `blog_craft_version: 0.3.0`,
  but blog-craft's only tag is `v0.2.0` — `0.3.0` is a phantom. `update.py`'s
  3-way base recovery (`git archive 0.3.0`) would fail. Base is only needed for
  `merged` paths; the series-index files are `framework` (base-independent).

## Design

### 1. Config — declare the registry + pin the real version

Edit `.blog-craft.yaml` (content-class; edited directly):

- Add a `series_index` block:
  ```yaml
  series_index:
    style: cards
    layers:
      - { code: hw,      name: "Hardware & Nodes" }
      # … all 21 codes, IN FRANK'S `ORDER` (order is load-bearing — the
      #    generator assigns hues by registry index; reordering changes colours) …
      - { code: repo,    name: "Repository & Tooling" }
  ```
  The 21 `name` values are copied **verbatim** from frank's current `$nameOf`
  dict so rendered tag text is identical.
- Set `blog_craft_version: "a7f2f7f"` (blog-craft's current `main` SHA — a real
  ref `git archive` accepts; supersedes the phantom `0.3.0`). *(Optional future
  nicety, out of scope here: tag blog-craft `v0.3.0` at this SHA for a cleaner
  semver pin.)*

### 2. Curated update — apply the series-index subset

Use `update.py`'s plan (the tracked flow), applying only the intended subset and
recording frank-side exclusions:

- **APPLY** `layouts/shortcodes/series-index.html` (framework replace = verbatim
  copy of blog-craft@`a7f2f7f`).
- **APPLY** `layouts/shortcodes/roadmap.html` (framework replace). Verify it
  renders frank's `roadmap.yaml` identically before accepting (see §Verification).
- **MERGE** `hugo.toml`: add `[params.seriesIndex]\n  style = "cards"`, keeping
  every existing frank setting. (The shortcode defaults to `cards` even absent
  this param; it is added for explicitness/controllability.)
- **EXCLUDE** `layouts/shortcodes/papers-roadmap.html` (operator: leave as-is),
  `.github/workflows/blog-ci.yml` (frank has its own CI), `README.md` (frank's
  blog has no README).
- **DEFER** the harmless framework adds (`.gitignore`,
  `.hookify.warn-hextra-weight-zero.md`, `static/images/.gitkeep`) — not
  series-index; keep this PR's diff surgical. A future full `update.py` run may
  adopt them.

Record the frank exclusions/deferrals (with reasons) in a short
`docs/runbooks/frank-gotchas/`-adjacent note so the next `update.py` run is
predictable. This documents frank's tracked-update relationship going forward.

### 3. Generator — vendor the registry-driven tool

Blog-craft's generator is a **build tool** (`tools/gen-layer-palette.py`), not a
materialized template, so `update.py` does not deliver it. Vendor it into frank:

- Replace `blog/scripts/gen-layer-palette.py` **content** with blog-craft@`a7f2f7f`'s
  `tools/gen-layer-palette.py` (registry-driven; reads `--config .blog-craft.yaml`).
- New regeneration command:
  `python blog/scripts/gen-layer-palette.py --config .blog-craft.yaml > blog/data/layer_palette.yaml`.

### 4. Palette — regenerate (content-class; explicit step)

`data/**` is content-class → `update.py` never touches `layer_palette.yaml`.
Regenerate it with the vendored generator from the new registry. Result: 21
entries **with `name`**, **no alias entries**. Colours proven identical to the
committed palette.

### 5. Aliases — retire them frank-side (zero visual change)

The registry generator emits no `inference`/`docs` aliases. Their consumers are
**three** entries (measured; an initial pass missed the papers one — caught in
code review): `blog/data/roadmap.yaml` `key: inference` (line 129) and `key: docs`
(line 302), plus `blog/data/papers.yaml` entry 0 `layer: docs` (line 24). The
papers one is easy to miss because `papers-roadmap.html` renders from the **data
file**, not post frontmatter (the paper's own `index.md` correctly uses `repo`).
Because `infer`≡`inference` and `repo`≡`docs` are identical colours by
construction:

- Swap `roadmap.yaml` `key: inference` → `key: infer` (line 129).
- Swap `roadmap.yaml` `key: docs` → `key: repo` (line 302).
- Swap `papers.yaml` entry 0 `layer: docs` → `layer: repo` (line 24) — else that
  one papers-roster card strands on the dropped alias and renders **neutral**.

The `no-orphan-layer-key` test therefore scans `roadmap.yaml`, `papers.yaml`,
AND post frontmatter. `papers-roadmap.html` keeps its own name dict (frank-local,
untouched) — its palette **colour** lookups resolve to the canonical codes in the
regenerated palette. This aligns frank with blog-craft's alias-free registry
model rather than forcing blog-craft to grow an alias feature.

### 6. Tests (frank-side, TDD)

Update/extend `scripts/tests/test_series_index_adoption.py` (#605) and add:

- **Palette colour parity:** regenerating from `.blog-craft.yaml`'s registry
  yields, for all 21 codes, `light/dark/lt/dt` byte-identical to the committed
  `layer_palette.yaml`. (Zero-visual-change on colour, as a guard.)
- **Drop-divergence invariant:** frank's `series-index.html` and `roadmap.html`
  are byte-identical to blog-craft@`a7f2f7f`'s shipped templates. (Proves frank
  no longer carries a divergent copy; a future drift re-fails this.)
- **No orphan layer key:** every `layer:`/`key:` value consumed by
  roadmap.yaml / posts resolves to a palette entry (alias-audit guard).
- **Registry ↔ palette consistency:** every `series_index.layers` code appears
  in the committed palette with a matching `name`.

### 7. Verification (in-repo, pre-merge)

- `cd blog && hugo --minify` clean.
- **Render diff:** build the site before and after; diff rendered
  `docs/building/`, `docs/operating/` section pages and the papers roster. The
  **only** expected delta is the `tag-layer` `font-weight` 500→600. Any other
  delta is a finding to resolve (esp. from the roadmap.html replace — if it is
  not render-identical, either accept a reviewed change or exclude roadmap too).
- Full `scripts/tests/` for the touched tests pass.

## Test Plan (post-merge, operator-driven)

Frank deploys a live blog (`blog.derio.net/frank` + GitHub Pages). After merge +
deploy:

1. Load the **building** section page and the **operating** section page; confirm
   the card series index renders with correct per-layer colours matching #605,
   in **both light and dark** modes; layer-name tags present and correct; no
   neutral/greyed cards.
2. Load the **papers** roster; confirm per-layer card colours unchanged (papers
   roadmap left as-is, inheriting the regenerated palette).
3. Spot-check 2–3 known layer colours (e.g. `stor` = `#d38f00` light) against
   the #605 baseline.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|-------------|--------|-------|
| 2026-07-04-series-index-resync | `derio-net/frank` | `2026-07-04-series-index-resync` | — |

## Non-goals

- Generalizing `papers-roadmap.html` into blog-craft (separate future effort).
- A full, un-curated `update.py --apply` of every blog-craft template change
  (deferred; would pull frank-inappropriate scaffolding — see §2).
- Any blog-craft change (blog-craft is done; this is frank-only).
- Tagging blog-craft `v0.3.0` (optional future nicety; SHA pin suffices).

## Risks & mitigations

- **roadmap.html replace not render-identical** → caught by the pre-merge render
  diff; resolve by accepting a reviewed change or excluding roadmap.
- **A paper uses `layer: inference`/`docs`** → this MATERIALIZED
  (`papers.yaml:24`, missed by the initial scan, caught in code review). Fixed by
  swapping to `repo`; the no-orphan-key test was extended to scan `papers.yaml` so
  the guard would have failed pre-fix. Zero-visual-change re-verified: the papers
  card body diff is a single class rename (`layer-docs`→`layer-repo`, same colour).
- **Future `update.py` run surprises** → the recorded exclusion/deferral note +
  correct version pin make the next run predictable.
