# Frank series-index re-sync onto blog-craft — plan

Drop frank's hand-written #605 copies of the series-index shortcode, roadmap
shortcode, and palette generator; consume blog-craft's now-standardized,
registry-driven versions (blog-craft `main` @ `a7f2f7f`, PR #12). Put frank on
blog-craft's tracked `update.py` flow, curated to the series-index surface, with
**zero visual change** to the live blog.

Spec: `docs/superpowers/specs/2026-07-04--repo--frank-series-index-resync-design.md`.

## Grounded in measurement

Everything here was measured before planning, not assumed:

- **Colour identity proven** — blog-craft's registry generator over frank's 21
  codes emits byte-identical `light/dark/lt/dt`; only diffs are additive (`name`)
  and the 2 dropped alias entries.
- **Update surface measured** — the `update.py` dry-run yields exactly two
  intended framework replaces (`series-index.html`, `roadmap.html`), a `hugo.toml`
  merge (the `seriesIndex` param), and a set of paths frank must EXCLUDE
  (`papers-roadmap.html` per operator, `blog-ci.yml`/`README.md` as
  frank-inappropriate) or DEFER (harmless scaffold adds). No CSS/scripts drift.
- **Version pin fixed** — frank's `blog_craft_version: 0.3.0` is a phantom (only
  `v0.2.0` is tagged); re-pin to the real synced SHA `a7f2f7f`.

## Shape — two agentic TDD phases

1. **Palette foundation.** Golden-snapshot the #605 palette as the parity
   baseline, then declare the 21-layer registry in `.blog-craft.yaml`
   (`series_index.layers`, `style: cards`), pin `blog_craft_version: a7f2f7f`,
   vendor blog-craft's registry-driven generator into `blog/scripts/`, and
   regenerate `blog/data/layer_palette.yaml`. Guards: colour parity vs the
   golden (21 codes identical), registry↔palette name consistency,
   generator-identity vs blog-craft.
2. **Shortcode re-sync.** RED drop-divergence test (frank's `series-index.html`
   + `roadmap.html` must equal blog-craft's), GREEN verbatim-copy them in, wire
   `[params.seriesIndex]` into `hugo.toml`, retire the 2 `roadmap.yaml` aliases
   (`inference→infer`, `docs→repo`) with a no-orphan-key guard, update the #605
   test to the name-from-palette shape, and verify zero visual change (clean
   `hugo --minify` + a render diff whose only delta is the accepted `tag-layer`
   font-weight 500→600). Record frank's update-exclusions note.

## Why this shape

- **Phase 1 before Phase 2** — the standardized shortcode reads layer NAMES from
  the palette data, so the registry + regenerated palette must exist before the
  shortcode is swapped in, or cards render nameless.
- **No manual phases** — every step is a config/file edit, regen, or test. The
  only human touchpoint is the post-merge Test Plan (in the spec).
- **`papers-roadmap.html` untouched** — operator decision; it already reads the
  palette, so it inherits the regenerated colours automatically.
- **Curated, not blanket `update.py --apply`** — a blanket apply would overwrite
  frank's customized papers-roadmap and add frank-inappropriate CI/README; the
  measured plan is applied as a series-index-scoped subset, with the exclusions
  documented for the next update.

## Out of scope

No blog post, README, or homepage tile (repo/meta re-sync, zero visual change).
No blog-craft change (blog-craft is done). No papers-roadmap generalization
(separate future effort). No un-curated full-tree update (deferred).
