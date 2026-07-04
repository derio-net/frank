# frank adoption — page-derived series-index cards + unified layer palette

**Date:** 2026-07-04
**Status:** Complete
**Layer:** repo (blog infra)
**Repo:** derio-net/frank
**Upstream:** derio-net/blog-craft `docs/superpowers/implemented/specs/2026-07-03--series-index--page-derived-series-overviews-design.md` (mechanism, shipped in blog-craft #10)

## Problem

blog-craft #10 shipped a generic `{{< series-index >}}` shortcode that renders a
series' index from its actual pages at Hugo build time — retiring the marker-append
*push* model. frank's blog still uses the push model, and two facts block a drop-in
adoption:

1. **frank vendors its own `blog/layouts/`.** The Hextra theme is a Go module;
   blog-craft is not a Hugo dependency. `blog/layouts/shortcodes/` has
   `papers-roadmap.html`, `roadmap.html`, etc. but no `series-index.html`.
2. **frank's building/operating posts carry no `series:` frontmatter.** Only papers
   does. Building/operating are grouped purely by directory, so the shipped
   shortcode (selects by `Params.series`) would list zero posts.

frank's index lived inside one combined page, `building/00-overview`: Roadmap +
hand-curated Technology→Capability Map + Cluster State + a hand-numbered **building**
index (33 entries, #604 markers, a planned KubeVirt line) + a hand-numbered
**Operating on Frank** index (28 entries). Papers already does the target thing:
`papers/_index.md` carries a short intro + `{{< papers-roadmap >}}`.

## Goals

- Each series (**building**, **operating**) gets a self-maintaining, page-derived
  index on its **section entrypoint** (`docs/<series>/_index.md`), under the intro —
  exactly like papers' `_index.md`.
- The index renders as **papers-roadmap-style cards**, **colour-coded by layer**, so
  all three series (building / operating / papers) share one visual language.
- **One source of truth for layer colours** — `blog/data/layer_palette.yaml` — used
  by all three shortcodes, so a layer is the same colour everywhere.
- Retire the #604 marker-append machinery.

## Non-goals

- **Papers keeps its roster mechanism** (`papers-roadmap.html` over `data/papers.yaml`)
  — it tracks planned/deferred entries with no page, which a page-derived index can't.
  Only its card *styling* is aligned (layer name tag + shared palette).
- **The Technology → Capability Map and Cluster State stay hand-curated** on
  `building/00-overview` — cluster inventories, not per-series indexes.
- **The KubeVirt "(planned)" line is not preserved inline** — page-derived indexes list
  real pages; `{{< roadmap >}}` already shows planned layers on `building/00-overview`.
- No prev/next nav, no URL changes to existing posts, no cover-image regeneration.

## Design

### 1. Placement — index on the section entrypoints

`{{< series-index "building" >}}` goes on `blog/content/docs/building/_index.md`
(under its intro) and `{{< series-index "operating" >}}` on `operating/_index.md` —
mirroring `papers/_index.md`. The positional arg names the series (the entrypoint has
no `series:` param of its own).

- **`building/00-overview` is kept** for the Roadmap + Capability Map + Cluster State,
  but the index is removed from it, and its `series: ["building"]` frontmatter is
  removed so it does **not** appear as a card in its own index.
- **`operating/00-overview` is deleted** — it existed only to hold the index, which now
  lives on the entrypoint.

### 2. `series:` + `layer:` frontmatter on the posts

The card shortcode selects posts by `series` and colours them by `layer`. Add both to
each of the 33 building + 28 operating post frontmatters (list-form `series`, e.g.
`series: ["building"]`; `layer:` = a `docs/layers.yaml` registry code, mapped per post
by topic — ambiguous/multi-layer posts assigned the dominant layer, e.g.
`02-foundation`→`os`, ingress→`net`, agent-shell/VK posts→`agents`, intro & papers
posts→`repo`).

**List form + frontmatter-scoped, mandatory.** A scalar `series:` is a hard Hextra
build error. The two `*-frank-papers` posts quote `series: papers` **in their body**
(documenting papers frontmatter), so the migration MUST parse only the leading
`---`-delimited block — a whole-file grep would false-match the prose and corrupt it.
Idempotent (skip a post whose frontmatter already declares the value).

### 3. Weight normalization (required bugfix)

The index sorts `.ByWeight`. Building already follows the documented `weight = number+1`.
**Operating's weights were a broken mix** (`100+n` / `n+1` / a stray `127`) that
scrambled the `.ByWeight` order of both the index and the operating sidebar (17 and
23–28 sorted *before* 01). Normalize all operating posts to `weight = number+1`. This
repairs the pre-existing scrambled sidebar — a **visible change**, flagged in the PR.

### 4. The `series-index` card shortcode (frank customisation)

`blog/layouts/shortcodes/series-index.html` — page-derived selection like the shipped
shortcode, but rendered as a **vertical timeline of cards** (papers-roadmap layout):
number badge, linked title, `summary` takeaway, and a leading **layer-name tag**
(`.tag-layer`, full name from the registry — "Storage", not "stor"). Series inferred
from the host page's `series` param or a positional override; posts sorted by weight,
host page self-excluded. Card colour (left border + number badge, light & dark) comes
from `site.Data.layer_palette` keyed on the post's `layer`.

*This diverges from blog-craft's shipped plain-table shortcode — frank's is a card
customisation. Standardising the card version upstream is a follow-up blog-craft PR.*

### 5. Unified layer palette — one source of truth

`blog/data/layer_palette.yaml` maps each of the 21 layer codes → `{ light, dark, lt, dt }`
(card colours + badge text colours), generated by `blog/scripts/gen-layer-palette.py`:

- **21 unique colours, never reused** — a colour identifies exactly one layer.
- Built in **OKLCH** with a hue-dependent lightness tracking each hue's chroma peak, so
  yellows/greens read vivid, not muddy olive.
- Hues assigned in a **permuted** order (`PERM_STEP` coprime to 21) so **successive
  layers contrast ~137°** (the opposite of a rainbow), aiding the roadmap timeline.
- `inference`/`docs` aliases mirror the keys `roadmap.yaml`/`papers.yaml` use.

**Propagation:** `roadmap.html` and `papers-roadmap.html` are reworked to read the same
`layer_palette.yaml` (their duplicated hardcoded `--rm-accent` palettes are retired),
and `papers-roadmap.html` shows the layer as a full-name `.tag-layer` (left-most),
matching the series-index cards while keeping its Published/drafting/planned/deferred
status badge and deferred-reason note.

### 6. Re-touch the workflow docs

- `repo-workflows.md` Step 5 (Blog) and `plan-post-deploy-checklist.md` Steps 2 & 3 —
  drop the "update the series index in `building/00-overview`" instructions (the section
  entrypoint auto-lists now); keep "add the roadmap layer to `blog/data/roadmap.yaml`";
  note the Capability Map stays hand-curated and operating has its own overview.

## Testing

`scripts/tests/test_series_index_adoption.py` builds the real production (`--minify`)
site and asserts (run with `pytest`):

- **Parity:** each series' entrypoint (`docs/<series>/index.html`) cards **exactly** its
  section posts (fs-derived ground truth), in numeric order, no overview page listed.
- **Placement:** `building/00-overview` still renders but carries no series-index;
  `operating/00-overview` is gone.
- **Layer colouring:** cards carry `layer-<code>` classes and the full-name `.tag-layer`.
- **Papers alignment:** papers uses the shared `.tag-layer` (no `layer: <code>` terse form).
- **No stale push machinery:** `building/00-overview` has no `auto-appends` markers, no
  embedded operating index, no `{{< series-index >}}`.
- **Palette reproducibility:** `gen-layer-palette.py` output == committed
  `layer_palette.yaml` (drift guard).

Plus a whole-site `hugo --minify` clean build.

## Test Plan

Post-merge, operator-driven (deploys to `blog.derio.net/frank` + `derio-net.github.io/frank`):

1. Wait for the blog deploy workflow.
2. **building** `docs/building/`: the card index lists all 33 posts, order/links match the
   retired hand-list; layer colours render; spot-check links resolve 200.
3. **operating** `docs/operating/`: same for the 28 operating posts.
4. **roadmap + papers**: `building/00-overview` roadmap and `papers/` roadmap render on the
   new palette (a layer is the same colour across all three); papers shows full layer names.
5. **dark mode**: toggle and confirm both palettes read correctly.

## Rollout

Single frank PR. Follow-up: standardise the card `series-index` + `layer_palette.yaml`
convention upstream in blog-craft (a separate PR — it changes stoa's index appearance).

## Implementation Plans

| Plan | Repo | Scope |
|------|------|-------|
| 2026-07-04-frank-series-index-adoption | derio-net/frank | frontmatter (series+layer) + card shortcode + entrypoint placement + palette + roadmap/papers propagation + docs + tests |
