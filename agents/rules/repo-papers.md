## The Frank Papers — Series Rules

Papers live at `blog/content/docs/papers/NN-slug/` (Hugo page bundles).
Research dossiers live at `docs/papers-dossiers/NN-slug/dossier.md`.

### Paper lifecycle

1. **Scaffold** — `scripts/scaffold-paper.sh <NN> <slug>`
   Creates the Hugo bundle skeleton and a dossier template.
2. **Fill dossier** — edit `docs/papers-dossiers/NN-slug/dossier.md`
   until `scripts/validate-dossier.py` passes (≥3 vendors, ≥5 sources,
   ≥3 artefacts, ≥1 gap, ≥1 counter-argument).
3. **Author dossier** (human gate) — user reviews named gaps and
   counter-arguments; marks dossier `status: ready`.
4. **Draft** — fill every `§` section of the Hugo `index.md`.
5. **Media** — Mermaid diagrams + cover image (use `/media` skill).
   Cover prompt: `"Frank examining [domain object] with a
   decision-maker expression, wearing his thin black tie and round
   reading glasses."` Add prompt to `blog/prompt_for_images.yaml`
   under `# --- Papers Series Covers ---` section; generate with
   `scripts/generate-all-images.py --only <key>`.
6. **Review** — voice pass, TL;DR ≤150 words, dossier-link renders.
7. **Publish** — set `draft: false`, set `status: published`.

### Frontmatter schema

Required fields: `title`, `date`, `draft`, `weight`, `series: papers`,
`layer`, `paper_number`, `publish_order`, `status`, `tldr`, `tags`,
`capabilities`, `related_building`, `related_operating`.

### Cross-linking (bidirectional, zero retrofit)

The Paper's frontmatter is the single source of truth:
- `related_building: "docs/building/10-local-inference"` — path
  relative to `blog/content/`
- `related_operating: "docs/operating/07-inference"` — same

`papers-backlink.html` renders a chip on Building/Operating posts at
Hugo build time, querying pages with `series: papers`. No edits to
existing posts needed.

### Dossier format

Sections (YAML blocks under `##` headers):
- `## Vendors in scope` — list with `name`, `positioning`, `primary_url`
- `## Primary sources` — list with `title`, `type`, `url`, `quoted_passages`, `relevance`
- `## Frank artefacts` — list with `kind`, `path_or_url`, `date`, `demonstrates`
- `## Diagrams planned`
- `## Named gaps`
- `## Counter-arguments considered`

Valid source `type` values: `vendor-docs`, `paper`, `postmortem`, `talk`,
`benchmark`.
Valid artefact `kind` values: `grafana-screenshot`, `asciinema`, `yaml`,
`commit`, `incident`.

### Dossier vs. shortcode: avoid double-render

`papers-forwardlinks.html` and a footer dossier chip are automatically
injected by `single.html`. Do NOT also use `{{< papers/dossier-link >}}`
inline in a Paper that relies on the automatic injection — it will render
twice. Use the shortcode inline OR rely on automatic injection, not both.

### Diagram types by section

| Section | Mermaid type |
|---------|-------------|
| §1 stack position | `flowchart LR` |
| §2 vendor landscape | `quadrantChart` via `{{< papers/landscape >}}` |
| §2 capability matrix | `{{< papers/capability-matrix >}}` |
| §3 architecture comparison | `flowchart TD` per vendor |
| §6 decision tree | `flowchart TD` ≤4 leaves |

### Commands

```bash
scripts/scaffold-paper.sh <NN> <slug>         # scaffold bundle + dossier
python scripts/validate-dossier.py <dossier>  # gate check (exit 0 = pass)
cd blog && hugo server --buildDrafts           # preview
hugo --minify                                  # production build
```
