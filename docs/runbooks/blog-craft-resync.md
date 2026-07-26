# blog-craft ↔ frank — the re-sync contract

Frank's blog is a **blog-craft-materialized** blog: the shortcodes, scripts, and
scaffolding under `blog/` are produced from the blog-craft templates
(`derio-net/blog-craft`, `templates/hugo-hextra/…`). Frank tracks a specific
blog-craft revision, pinned in `.blog-craft.yaml`:

```yaml
blog_craft_version: "v0.10.0"   # blog-craft RELEASE frank is synced to
```

Keep this accurate: `update.py` recovers the 3-way-merge base by **re-rendering
at the recorded release**, so a stale or wrong value silently degrades every
`merged` path to a baseless conflict. It is a release tag, not a main SHA (older
revisions of this note showed a SHA). Bump it *after* an apply, not before.

Two axes move independently — the config **schema** (`version:`, migrated by
`tools/migrate_config.py`) and the blog-craft **release** (`blog_craft_version`).
`migrate_config.py --check` reports the first; the release gap is the usual one.

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
python tools/update.py --config "$(pwd)/.blog-craft.yaml" --blog .
```

**Pass `--config` as an ABSOLUTE path.** `update.py` hands the value straight to
`bootstrap-render.sh` in a subprocess that runs from a different cwd, so a
relative path dies in a `CalledProcessError` traceback whose real cause —
`load answers: open .blog-craft.yaml: no such file or directory` — is swallowed
in the captured output and never printed. `--blog` points at the **config root**
(the repo root, which is where `.blog-craft.yaml` lives), *not* at `blog/`;
`site_dir: blog` in the config already maps the Hugo paths under `blog/`.

`update.py` only touches paths blog-craft **materializes** (`layouts/`, `hugo.toml`,
CI, …); frank's authored content (`content/**`, `data/**`, images,
`.blog-craft.yaml`) is `content`-class and left alone. `data/layer_palette.yaml`
is content-class too — regenerate it explicitly (above), it is not auto-updated.

## A reverted `framework` path is usually an UPSTREAM bug — fix it there

Before adding anything to the table below, apply this test:

> Does this path encode a fact about **frank's repo**, or a gap in
> **blog-craft**?

`framework` means "blog-craft owns this — overwrite unconditionally". There is
no merge and no conflict detection, so a local patch to such a file is invisible
upstream and silently reverted on **every** update, drifting further each
release while every other blog-craft blog keeps the bug. The exclusion table is
for the first case only. **The second case gets an issue/PR against
`derio-net/blog-craft`, then a clean re-run of `/update`** — never a local patch
plus a table row.

Worked example (2026-07-26, blog-craft #53 / #54). Updating v0.10.0 → v0.13.1
returned three `framework` paths as *reverts*; all three were upstream gaps, not
frank customizations, and all three were fixed upstream in v0.14.0:

| Path | The upstream gap |
|------|------------------|
| `blog/layouts/docs/single.html` | Rendered the post cover as a raw `<img>` while `list.html` (the cover *thumbnail*), `render-image.html`, `screenshot.html` and `site-banner.html` all used `opt-image.html` — so the largest image on the page skipped WebP, `maxWidth` capping and `srcset`. This is frank PR #710's fix; a blanket apply would have reverted it. |
| `blog/scripts/generate-images.py` | `post_process()`'s `resize` step could not write to a `target` (`crop_resize` and `ico` already could), so a one-master-to-many-derivatives pass — the favicon set — was inexpressible. |
| `.reference-pool/README.md` | Documented the v4 reference precedence chain that v5 removed in 0.10.0, contradicting blog-craft's own `docs/CONFIG.md`. |

After v0.14.0 these render identically to frank's copies and drop out of the
update plan. Frank's *persona-specific* reference notes — the eye-design
invariant, the startled-expression trap, the head-only favicon sheet — moved to
**`.reference-pool/PERSONA.md`**, which blog-craft never materializes (its
manifest names `.reference-pool/README.md` explicitly, not a `**` glob) and
`update.py` never deletes.

## Frank-owned paths — DO NOT let an update overwrite these

blog-craft's manifest classifies these `framework`/`merged` (overwrite/merge),
but frank genuinely owns them — each encodes a fact about frank's repo that has
no upstream meaning. Exclude them from any `update.py --apply`:

| Path | Why frank owns it |
|------|-------------------|
| `blog/layouts/shortcodes/papers-roadmap.html` | Frank-customized (papers roster + Published/deferred status). blog-craft ships a generic one via the papers content-type; frank's is bespoke and **not** generalized upstream. |
| `.github/workflows/blog-ci.yml` | Frank has its own blog CI + GitHub Pages deploy; blog-craft's generic workflow does not apply. |
| `blog/README.md` | Frank's blog has no standalone README (frank's README is repo-root). |

`blog/hugo.toml` is `merged`, not excluded, but a v0.14.0 update proposes only a
re-ordering of the `[params.seriesIndex]` / `[params.imageOptimize]` blocks —
semantically identical TOML that would drop frank's explanatory comments for no
gain. Skip it unless a later release changes it substantively.

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
  (now carries `name` per entry; the `inference`/`docs` aliases are retired).
  Every consumer of the retired aliases was migrated to the canonical code, same
  colours by construction: `roadmap.yaml` (`inference`→`infer`, `docs`→`repo`)
  AND `blog/data/papers.yaml` (paper 0 `layer: docs`→`repo` — consumed by
  `papers-roadmap.html`, which reads the data file, not post frontmatter).
- Added `[params.seriesIndex] style = "cards"` to `blog/hugo.toml`.
- Net visual change: the layer-name card tag is `font-weight: 600` (was `500`);
  every colour and all other markup is byte-identical.
