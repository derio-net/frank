# blog-craft ↔ frank — the re-sync contract

Frank's blog is a **blog-craft-materialized** blog: the shortcodes, scripts, and
scaffolding under `blog/` are produced from the blog-craft templates
(`derio-net/blog-craft`, `templates/hugo-hextra/…`). Frank tracks a specific
blog-craft revision, pinned in `.blog-craft.yaml`:

```yaml
blog_craft_version: "v0.16.0"   # blog-craft RELEASE frank is synced to
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

## MANDATORY after every update: delete `blog/.github/`

blog-craft materializes `.github/**` under `site_dir`, so an update **always
re-adds** `blog/.github/workflows/blog-ci.yml` (an absent managed path is an
`add`, unconditionally). GitHub only ever reads workflows from the **repo root**,
so that copy runs nothing — it sat there inert from #667 until 2026-07-27, and
its papers/mermaid/image gates never fired once. frank's live workflow is
`.github/workflows/blog-ci.yml`; delete the re-added copy every time:

```bash
rm -rf blog/.github
```

`scripts/tests/test_blog_ci_at_repo_root.py` fails the PR if you forget, so this
cannot ship silently again. Tracked upstream as **blog-craft#61** — drop this
step once `.github/**` joins `map_dest`'s config-rooted allowlist.

## `.blog-craft.sync.yaml` — commit it, and read the backfill warning once

Since v0.16.1 the updater records the config it last synced, and renders the
3-way base from THAT instead of your current one. Without it, enabling a
`features.*` flag silently dropped that feature's contribution to every `merged`
path — the base already contained it, so the merge read frank's file as a
deliberate deletion (blog-craft#60; it cost frank the `Validate glossary` CI
step, which had to be restored by hand). **Commit the file.**

The very first update after upgrading still runs on the old, approximate base —
the fix is not retroactive — and then records the snapshot. That one run prints
the `merged` paths its fallback base resolved to `NOOP`, because recording a
snapshot freezes whatever the tree holds, including anything an earlier run had
already dropped. **Check them once; after that they are ordinary NOOPs with no
warning left on them.** Frank's run named `blog/hugo.toml` and
`blog/assets/css/custom.css`; both were verified benign on 2026-07-27 — hugo.toml
differs only in key order (0 lines absent), and custom.css's 174 absent lines are
blog-craft's `.content .mermaid` theme, which frank deliberately rewrote using
`& .mermaid` nesting (76 rules; **0 non-mermaid selectors absent**).

`NOOP` vs `MERGE` is worth internalising: a `NOOP` on a path you expected to
change means the base is wrong, not that there was nothing to do.

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
update plan — confirmed on 2026-07-27: `single.html` was absent from the plan
entirely, and `generate-images.py` / `.reference-pool/README.md` came back as
pure convergence.

Second worked example (2026-07-27, blog-craft #58). Updating v0.10.0 → v0.15.0
surfaced **one** genuine revert, and the same test sent it upstream rather than
into the table below:

| Path | The upstream gap |
|------|------------------|
| `blog/layouts/partials/custom/head-end.html` | Dropped the `mermaid-init.js` load. Hextra initialises mermaid from an **inline `<script>`** that frank's `script-src 'self'` discards; `mermaid.js` self-starts so diagrams still *appear*, but freeze in the light theme and stop following the dark/light toggle across every post that uses one. Frank shipped the external replacement in #710. Fixed upstream in **v0.16.0** as the opt-in `features.mermaid_csp_init`. |

Two things about that one are worth keeping:

- **It is the third instance of the class blog-craft #56 fixed twice** (the
  read-tracker clear-link and the asciinema player). #56 missed it because its
  guard, `test_templates_csp_safe.py`, builds a page with *no diagram* — so the
  theme never loads its mermaid partial and the "no inline script" assertion
  passed vacuously. A guard is only as wide as its fixture.
- **It had to be opt-in upstream, unlike #56's fixes.** Those replaced inline
  scripts blog-craft *itself* emitted, so nothing was left to collide with. This
  one supersedes a script in the **pinned theme**, which blog-craft cannot
  remove — a blog with no CSP still runs it, so an unconditional asset would
  mean two initialisers racing. Hence frank must keep
  `features.mermaid_csp_init: true` set for as long as the CSP is on.

Frank's *persona-specific* reference notes — the eye-design
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

`blog/hugo.toml` is `merged`, not excluded. It **no longer needs skipping**: at
v0.16.0 the 3-way merge resolves byte-identical to frank's current file, so it
drops out of the applied diff on its own. (Through v0.14.0 it proposed a
re-ordering of the `[params.seriesIndex]` / `[params.imageOptimize]` blocks —
semantically identical TOML that would have dropped frank's explanatory comments
for no gain. That advice is obsolete; re-check rather than assume if a future
release touches the file.)

## Deferred framework adds — none outstanding

The 2026-07-04 series-index re-sync (spec
`docs/superpowers/specs/2026-07-04--repo--frank-series-index-resync-design.md`)
deliberately **deferred** three blog-craft scaffold adds to keep that PR's diff
surgical: `blog/.gitignore`, `blog/.hookify.warn-hextra-weight-zero.md`,
`blog/static/images/.gitkeep`. All three are present as of 2026-07-27 and no
longer appear in the plan. Nothing is deferred right now.

## What the 2026-07-27 re-sync actually applied (v0.10.0 → v0.16.0)

Sixteen paths, no conflicts. Everything except the mermaid fix above was
convergence — several of the `framework` replaces were **comments-only** diffs
(`opt-image.html`, `asciinema.html`, `footer.html`) or semantically identical
(`generate-images.py`: one statement reordered).

- **CSP hardening from blog-craft 0.15.0/0.16.0.** asciinema-player is now
  vendored under `blog/assets/vendor/` (Apache-2.0, with `PROVENANCE.md`) and
  served same-origin instead of from unpkg; the asciinema shortcode passes config
  as `data-*`; `mermaid-init.js` becomes blog-craft-owned via
  `features.mermaid_csp_init`.
- **`read-history-clear.js` deleted.** blog-craft absorbed the clear-link handler
  into `read-tracker.js` (same `STORAGE_KEY`, same reasoning frank used), so
  frank's separate asset was orphaned — nothing loaded it after `head-end.html`
  was replaced.
- **De-duplicated `.clear-read-history`** in `custom.css`: blog-craft's rule
  arrived with *byte-identical declarations* to frank's, so frank's later copy
  was removed. No visual change.
- **`opt-image.html` converged** — blog-craft #55 upstreamed frank #710's srcset
  fix and cites `derio-net/frank#710` in the template comment.
- **`blog/hugo.toml` unchanged**; `blog/scripts/glossary_scan.py` +
  `validate_glossary.py` added (they ship unconditionally and only *run* when
  `features.glossary.enabled`, which frank does not set).
- Net rendered change: none expected beyond the asciinema/mermaid wiring — frank
  was already running #710's fixes locally.

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
