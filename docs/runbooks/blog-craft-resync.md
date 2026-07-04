# blog-craft ↔ frank — the re-sync contract

Frank's blog is a **blog-craft-materialized** blog: the shortcodes, scripts, and
scaffolding under `blog/` are produced from the blog-craft templates
(`derio-net/blog-craft`, `templates/hugo-hextra/…`). Frank tracks a specific
blog-craft revision, pinned in `.blog-craft.yaml`:

```yaml
blog_craft_version: "a7f2f7f"   # blog-craft main SHA frank is synced to
```

This note records how frank pulls blog-craft updates, and — importantly — which
paths frank **owns** despite blog-craft classifying them otherwise. A blanket
`update.py --apply` would clobber them; the re-sync applies a curated subset.

## Regenerating the layer palette

`blog/data/layer_palette.yaml` is generated (not hand-edited) from the layer
registry in `.blog-craft.yaml` (`series_index.layers`) by the registry-driven
generator vendored at `blog/scripts/gen-layer-palette.py`:

```bash
python blog/scripts/gen-layer-palette.py --config .blog-craft.yaml > blog/data/layer_palette.yaml
```

Edit the registry (add/reorder a layer) → regenerate → commit. Order is
load-bearing: the generator assigns each layer a hue by its registry **index**
(permuted for maximum successive contrast), so reordering changes every colour.
Guarded by `scripts/tests/test_series_index_resync.py` (parity against the
committed palette + registry↔palette name consistency).

## Running an update from blog-craft

From a blog-craft checkout, dry-run the plan against frank's blog:

```bash
python tools/update.py --config <frank>/.blog-craft.yaml --blog <frank>/blog
```

`update.py` only touches paths blog-craft **materializes** (`layouts/`, `hugo.toml`,
CI, …); frank's authored content (`content/**`, `data/**`, images,
`.blog-craft.yaml`) is `content`-class and left alone. `data/layer_palette.yaml`
is content-class too — regenerate it explicitly (above), it is not auto-updated.

## Frank-owned paths — DO NOT let an update overwrite these

blog-craft's manifest classifies these `framework`/`merged` (overwrite/merge),
but frank owns them. Exclude them from any `update.py --apply`:

| Path | Why frank owns it |
|------|-------------------|
| `blog/layouts/shortcodes/papers-roadmap.html` | Frank-customized (papers roster + Published/deferred status). blog-craft ships a generic one via the papers content-type; frank's is bespoke and **not** generalized upstream. |
| `.github/workflows/blog-ci.yml` | Frank has its own blog CI + GitHub Pages deploy; blog-craft's generic workflow does not apply. |
| `blog/README.md` | Frank's blog has no standalone README (frank's README is repo-root). |

## Deferred (harmless) framework adds

The 2026-07-04 series-index re-sync (spec
`docs/superpowers/specs/2026-07-04--repo--frank-series-index-resync-design.md`)
deliberately **deferred** these blog-craft scaffold adds to keep that PR's diff
surgical. A later full update may adopt them:

- `blog/.gitignore`
- `blog/.hookify.warn-hextra-weight-zero.md`
- `blog/static/images/.gitkeep`

## What the 2026-07-04 re-sync actually applied

- Replaced `blog/layouts/shortcodes/series-index.html` + `roadmap.html` with
  blog-craft@`a7f2f7f`'s standardized (registry-driven) versions.
- Vendored the registry-driven `gen-layer-palette.py`; regenerated the palette
  (now carries `name` per entry; the `inference`/`docs` aliases are retired —
  `roadmap.yaml` now uses the canonical `infer`/`repo` codes, same colours).
- Added `[params.seriesIndex] style = "cards"` to `blog/hugo.toml`.
- Net visual change: the layer-name card tag is `font-weight: 600` (was `500`);
  every colour and all other markup is byte-identical.
