# frank series-index adoption — plan

Adopt blog-craft's shipped `{{< series-index >}}` shortcode (blog-craft #10) into
frank's blog so the **building** and **operating** series each get a self-maintaining,
page-derived landing index — retiring the marker-append push model and giving
operating its own overview page. Single frank PR (operator's choice: migrate
frank's posts to the shortcode's `series:` contract rather than change the mechanism).

See the spec: `docs/superpowers/specs/2026-07-04--repo--frank-series-index-adoption-design.md`.

## Deviation (design evolved during review/preview)

The plan phases below describe the initial approach: a plain-**table** index placed on
the `00-overview` pages. During live preview the design was refined (operator-directed)
into the shipped shape, captured in the updated spec:

- **Index moved to the section entrypoints** (`docs/<series>/_index.md`), not the
  `00-overview` pages — mirroring papers. `operating/00-overview` is **deleted**;
  `building/00-overview` is **kept** (roadmap/capability/state) with the index removed.
- **Card layout, not a table** — `series-index.html` renders papers-roadmap-style cards
  **colour-coded by layer**; posts gained a `layer:` frontmatter alongside `series:`.
- **Unified layer palette** — `blog/data/layer_palette.yaml` (+ `gen-layer-palette.py`),
  adopted by `series-index`, `roadmap`, and `papers-roadmap` (papers now shows the layer
  as a full-name tag). The parity test asserts the card structure + palette reproducibility.

The phase steps are retained as the historical record; the spec is the accurate design.

## Shape

Three agentic phases, TDD red → green → verify:

1. **Failing parity test (red).** A `pytest` at `scripts/tests/test_series_index_adoption.py`
   builds the real Hugo site and asserts each overview's `series-index` table lists
   exactly its section's posts (ground truth derived from the filesystem, not hardcoded),
   weight-ordered, self-excluded, with the push machinery gone. Red today.

2. **Green.** Vendor the shortcode into `blog/layouts/shortcodes/` (frank vendors its own
   layouts — it isn't a Hugo dependency of blog-craft); add list-form `series:` frontmatter
   to the 33 building + 28 operating posts (frontmatter-scoped — the two `*-frank-papers`
   posts quote `series: papers` in their *body*, which must not be touched); rewrite
   `building/00-overview` to `{{< series-index >}}` (dropping the hand-list, the operating
   section, and both #604 markers, keeping Roadmap + Capability Map + Cluster State); create
   `operating/00-overview`. Test goes green.

3. **Docs + full build.** Re-touch `agents/rules/repo-workflows.md` (steps that referenced the
   retired append), and a whole-site `hugo --minify` clean build asserting both overviews
   render a non-empty index.

## Why this shape

- **Papers is untouched** — its roster already renders via `{{< papers-roadmap >}}` on
  `papers/_index.md`.
- **The Capability Map + Cluster State stay hand-curated** — cluster inventories, not
  per-series indexes.
- **KubeVirt "(planned)" is not lost** — `{{< roadmap >}}` (from `data/roadmap.yaml`) already
  shows planned layers on the same page.
- **Deploy is post-merge** (CI → blog.derio.net/frank + github pages) and operator-driven —
  the full-parity-diff Test Plan lives in the spec, not as a plan phase. No manual phase.
