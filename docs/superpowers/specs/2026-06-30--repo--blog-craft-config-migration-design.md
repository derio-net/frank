# Design: Extract Frank's Blog System into blog-craft (config-driven creator & updater)

**Status:** Draft
**Date:** 2026-06-30
**Layer:** repo (meta / blog infrastructure)
**Spec owner repo:** frank (this repo)
**Implementation repos:** `../blog-craft` (P1–P6), `frank` (P7)
**Brainstorm:** fr-brainstorming, isolated in `feat/blog-craft-config-migration`

---

## 1. Problem & Goal

Frank's blog tooling (skills, rules, image system, papers/dossier framework,
validators, CI) lives **inline** in this repo (`agents/skills/{blog-post,media,papers}`,
`blog/`, `scripts/*.py`, `.reference-pool/`). A sibling framework, **blog-craft**
(`../blog-craft`, a Claude Code plugin at v0.1.0), already exists and has been
applied to **stoa-blog** (`../../STOA/stoa-blog`) via a `.blog-craft.yaml` config.

**Goal:** make *blog-craft + a per-repo `.blog-craft.yaml`* the single creator **and
updater** of both blogs, such that applying it reproduces each blog's full
structure and functionality. frank is the hard target (papers, layered image
system, roadmap, read-tracker, CI); stoa is the easy target (already a clean
consumer) and serves as a regression guard.

### Acceptance bar (operator decision)

**Structural / tooling parity** — applying blog-craft + a repo's config to an
**empty** repo reproduces the full scaffold (theme, shortcodes, layouts, CSS,
image system, validators, CI). Existing authored posts/cover images are **not**
regenerated; they are operator-owned content. The acceptance test is a
**structural diff** of the generated scaffold vs the repo's current non-content
files (see §7).

### Operator decisions locked during brainstorm

1. Fidelity bar = **tooling/structure parity** (content excluded).
2. Migration posture = **parity first, migrate frank after** (P1–P6 never touch
   frank's working blog; P7 is the deliberate cutover).
3. Papers = **first-class opt-in content-type** in blog-craft (frank on, stoa off).
4. Decomposition = **umbrella spec → sequenced sub-plans** (this doc + fr-plan).
5. Image composition = **Approach A: config-declared composition order** (§4).
6. Roadmap = **data-driven** (`data/roadmap.yaml`), not a baked template.
7. Schema = **v2 bump** with a one-time mechanical stoa config migration.
8. CSS = **split** into shipped structural base + config-injected palette.
9. 3-way-merge base = **recovered by re-render** at the recorded version (no
   stored per-repo baseline).

### Non-goals

- Byte-for-byte reproduction of authored content or generated PNGs.
- A deploy pipeline beyond a validation-core CI template + a config-selected
  deploy tail (blog-craft does not own deploy).
- Abstracting over SSGs (Hugo + Hextra only) or image providers (Gemini only) —
  fields are reserved but not implemented.

---

## 2. Three-repo landscape (current state)

| | frank `blog/` | stoa-blog | blog-craft v0.1.0 |
|---|---|---|---|
| Skills | inline `agents/skills/{blog-post,media,papers}` | consumes blog-craft | ships `bootstrap-blog, blog-post, media, media-screenshots` |
| Config | none (inline) | `.blog-craft.yaml` v1 | `.blog-craft.yaml` v1 schema |
| Series | building, operating, **papers** | forum, content-factory, hum | config-driven |
| Image gen | `generate-all-images.py` (layered: base_character+atmosphere+ref_guidance+torso+mood+scene; `.reference-pool/`; contact sheets; `.regen-archive/`) | single `reference.png`, per-image full prompts | `generate-images.py` (single-prompt; subset of frank's) |
| Papers | dossier gate + 4 validators + ~8 shortcodes + cross-linking | none | none |
| Theme extras | roadmap (~24KB), read-tracker.js, goatcounter, paper CSS | banners, tiles, overview posts | banners, overview posts, basic shortcodes |
| CI | `deploy-blog.yml` (validators + hugo + mermaid + Pages + container) | none | none (smoke tests only) |

frank's `generate-all-images.py` is a strict **superset** of stoa's
`generate-images.py`. The gap from blog-craft → frank-parity is: layered image
composition, the papers content-type, roadmap/read-tracker/CSS params, the
validation/CI surface, and an **update** path (blog-craft has only one-time
bootstrap today).

---

## 3. Architecture overview

blog-craft stays a Claude Code plugin that **materializes** a Hugo+Hextra blog
into a target repo from `.blog-craft.yaml`, then **maintains** it. Four config
concerns map to four implementation areas:

- **project** → site identity/URLs (largely unchanged from v1).
- **image** → the Approach-A composition engine (§4).
- **series + content_types** → structure + the opt-in papers module (§5).
- **features / ci** → layouts, CSS, validators, pipeline (§6).

A single **path-ownership manifest** (shipped with blog-craft) classifies every
materialized path as `framework` (reproduce + overwrite), `content` (ignore +
never touch), or `merged` (reproduce-with-config + 3-way merge). It powers both
the reproduction test (§7) and the updater (§8).

---

## 4. Config contract `.blog-craft.yaml` v2

`version: 2`. stoa's v1 config is migrated once (mechanical; guarded by the
stoa golden test). Only two consumers exist, both operator-controlled, so dual
schema support is not carried.

```yaml
version: 2
blog_craft_version: "<release applied>"   # set by bootstrap/update; drives §8 deltas
project: { name, tagline, base_url, base_path, module_path }

image:
  provider: gemini
  model: gemini-3-pro-image-preview
  api_key_env: GEMINI_API_KEY
  output_dir: static/images
  prompts_file: prompt_for_images.yaml
  reference_pool: .reference-pool          # per-series masters + subjects/ anchors
  curation: { count_default: 1, archive_cap: 30, contact_sheet: true }
  composition_order: [base_character, base_atmosphere, reference_guidance, torso, mood, scene]
  layers:                                  # each layer: scalar | list | indexed-table
    base_character: |  ...                 # scalar → verbatim
    base_atmosphere: | ...                 # scalar
    reference_guidance: | ...              # scalar
    visual_constants:  [ ... ]             # list   → "- " bulleted lines (stoa)
    torso:                                 # indexed-table keyed by (entry.series, entry.torso_variant)
      building: [ "...", "...", ... ]
      operating: [ "...", ... ]
      papers:   [ "...", ... ]
      generic:  [ "..." ]
    mood:                                  # indexed-table keyed by entry.mood (name)
      focused: "..."
      weighing: "..."
    # 'scene' is reserved → resolves to the per-image entry's `prompt` field

series:
  - { key: building,  title: "Building Frank",    description: "...", content_type: posts }
  - { key: operating, title: "Operating on Frank", description: "...", content_type: posts }
  - { key: papers,    title: "The Frank Papers",   description: "...", content_type: papers }

content_types:
  papers:                                  # absent / enabled:false for stoa
    enabled: true
    dossier_dir: docs/papers-dossiers
    data_dir: blog/data/papers
    gate: { min_vendors: 3, min_sources: 5, min_source_types: 3,
            min_artefacts: 3, min_artefact_kinds: 2, min_gaps: 1, min_counterargs: 1 }
    source_types:   [vendor-docs, paper, postmortem, talk, benchmark]
    artefact_kinds: [grafana-screenshot, asciinema, yaml, commit, incident]
    shortcodes:     [landscape, capability-matrix, scar, pullquote, dossier-link, references-index]
    crosslink_fields: [related_building, related_operating]
    weight_offset: 1

features:
  series_overview_posts: true
  read_tracker: true
  banners:   { operator_generated: true }                 # 6:1 panoramic, Gemini-API limit
  roadmap:   { enabled: true, data: data/roadmap.yaml }   # data-driven; frank specifics live in data
  analytics: { provider: goatcounter, code_env: GOATCOUNTER_CODE }
  css:       { mermaid_palette: { node: "#1f3a5f", stroke: "#4dabf7", edge: "#51cf66", label: "#eaf2ff" } }

voice: | ...

ci:
  validators: [frontmatter, dossier, mermaid, hugo_build]  # auto-pruned by content_types present
  deploy: { kind: container_pages }                        # container_pages | pages | none
```

### 4.1 Layer-resolution rule (the contract the generator obeys)

For each name in `image.composition_order`, look it up in `image.layers` and emit:

- **scalar (string):** verbatim.
- **list:** each element as a `- ` bulleted line.
- **indexed-table (map):** select with the per-image entry's matching field —
  `torso` ← `entry.torso_variant` indexing within `entry.series`; `mood` ←
  `entry.mood` (by name). A missing/empty selector skips the layer.
- **`scene` (reserved):** resolves to the per-image entry's `prompt` field.

The generator hardcodes **no** vocabulary or order. frank and stoa ship different
`composition_order` + `layers`; both are pure data. This is the only mechanism
that reproduces *both* blogs' exact composed prompts (frank emits
ref_guidance early, stoa emits it last — a fixed order could not honor both).

---

## 5. Series, content types, and the papers module

- A `series` entry binds to a `content_type` (`posts` default, `papers` opt-in).
- **`content_types.papers`** (config-gated) ships the entire papers subsystem,
  materialized only when at least one series uses it:
  - **Templates** (`templates/content-type-papers/`): paper page-bundle skeleton
    (TL;DR + §1–§7 stubs with budget comments) and the dossier template
    (`scaffold-paper` reads `content_types.papers`).
  - **Validators** (`tools/`): `validate-dossier.py` (thresholds from `gate`),
    `validate-papers.py` (frontmatter + `weight = paper_number + weight_offset`),
    `sync-dossier-to-data.py` (dossier → `data_dir`). No hardcoded thresholds.
  - **Shortcodes/partials:** `landscape`, `capability-matrix`, `scar`,
    `pullquote`, `dossier-link`, `references-index`, plus cross-link partials
    (`papers-forwardlinks`, `papers-backlink`, `papers-prev-next`) and the
    `single.html` injection.
  - **Cross-linking:** bidirectional via `crosslink_fields`; paper frontmatter is
    the single source of truth, resolved at Hugo build (zero retrofit).
  - **Skill:** blog-craft gains a `papers` skill (port of frank's), dormant
    unless the content-type is enabled.
- stoa omits `content_types.papers` → none of the above materializes.

---

## 6. Theme, layout, CSS parameterization

- **Banners** (`site-banner.html`): per-series path-detection partial ships;
  banner image bytes are operator-generated content (6:1, Gemini-web limitation).
- **`custom.css`:** split into a **shipped structural base** (`.post-cover`,
  `.screenshot`, `.asciinema-container`, `.site-track-banner`,
  `.blog-series-cards`, the `.paper-post` family) and a **config-injected
  palette** (`features.css.mermaid_palette` + color tokens).
- **`read-tracker.js`:** ships, gated by `features.read_tracker`.
- **Roadmap:** scaffold shortcode ships; frank's ~24KB of specifics live in
  `data/roadmap.yaml` (a `content` path); the shortcode renders from data.
  Papers-roadmap likewise.
- **Analytics** (`goatcounter.html`): ships, gated by `features.analytics`,
  code from env.
- **Hookify weight-zero guard:** ships as a blog-craft asset so every blog
  inherits the Hextra sidebar-trap protection (`weight = number + offset`).

---

## 7. Testing & the reproduction harness (non-negotiable)

Three tiers, cheapest first:

1. **Unit/contract:** layer-resolution rule (scalar/list/indexed-table), the new
   schema validator (replaces v1's "rely on YAML parse errors"), each papers gate
   threshold, each schema-migration transform.
2. **Per-feature smoke:** extend `smoke-bootstrap` / `smoke-blog-post` /
   `smoke-media`; **add** `smoke-papers` (scaffold → fill dossier → gate pass/fail
   → validators → shortcode renders → Hugo builds) and `smoke-image-compose`
   (prompt-string equality, below).
3. **Integration reproduction (the thesis test):** rests on the §3 path-ownership
   manifest.
   - **Frank golden test:** apply blog-craft + frank's `.blog-craft.yaml` into a
     scratch dir → diff every `framework`/`merged` path vs frank's current `blog/`
     tree → **zero structural drift**. `content` paths excluded by manifest.
   - **Stoa golden test:** same vs stoa's tree (guards frank-driven regressions).
   - **Image equality:** for sampled `prompt_for_images.yaml` entries,
     `generate --print-prompt` is **byte-identical** to the legacy generator's
     output (deterministic; no Gemini call). This is how Approach A is proven.

---

## 8. Versioning & forward-migration (the "updater")

Two version axes recorded per repo: `version:` (config schema) and
`blog_craft_version:` (last-applied blog-craft release).

### 8.1 Schema migration ladder

Ordered, pure, idempotent transforms `migrations/00N-to-00M.py`
(config-in → config-out), each with a golden fixture (`vN sample → expected
vN+1`). `version:` selects which run. Non-destructive: writes new config; prior
recoverable via git (+ a `.bak`).

### 8.2 Template/asset update flow (`/blog-craft:update` / `bootstrap-render.sh --update`)

1. Render templates against current config into a **staging tree** (never in place).
2. Classify each path via the manifest: `framework` → replace; `content` →
   leave; `merged` → 3-way merge.
3. **3-way merge base is recovered, not stored:** re-render templates at the
   recorded `blog_craft_version` (reachable via blog-craft's own git tag) against
   current config = `base`; `local` = file on disk; `incoming` = staging.
   `diff3`; conflicts surfaced, never auto-resolved.
4. Emit a **dry-run diff** for operator review; apply on approval; bump
   `blog_craft_version`.

### 8.3 Testability

The update smoke test bootstraps a blog at blog-craft `vN`, evolves a fixture to
`vN+1` (a changed shortcode + a schema field), runs `update --dry-run`, asserts
the diff equals a golden, applies, then asserts Hugo still builds **and** the
reproduction test passes. The schema ladder gets per-step fixture tests. "Go
from v2 to v3" is thus exercised end-to-end before any real blog is touched.

---

## 9. CI

blog-craft ships a CI workflow template materializing the **validation core**
(frontmatter + dossier + mermaid + `hugo --minify`, pruned by which
`content_types` are present) plus a smoke + reproduction job in blog-craft's own
CI. The **deploy tail** (frank's container→GHCR→manifest-bump) is selected by
`ci.deploy.kind` from a shipped template or left operator-appended; stoa = `none`.

---

## 10. Phase sequencing (for fr-plan)

| Phase | Repo | Deliverable | Gate |
|---|---|---|---|
| **P1 — Config v2 + manifest** | blog-craft | v2 schema, real schema validator, path-ownership manifest, stoa v1→v2 config migration | validator unit tests; stoa smoke green |
| **P2 — Image engine (Approach A)** | blog-craft | canonical generator as generic concatenator, composition_order/layers, reference-pool, curation | `smoke-image-compose` prompt-equality vs legacy |
| **P3 — Papers content-type** | blog-craft | templates, validators, shortcodes, cross-linking, dossier flow, `papers` skill — opt-in | `smoke-papers`; stoa unaffected |
| **P4 — Theme/layout/CSS params** | blog-craft | banners, CSS split, read-tracker, roadmap-as-data, analytics, weight-zero guard | per-feature smoke + Hugo build |
| **P5 — Validation/CI + reproduction harness** | blog-craft | extended smoke suite, frank+stoa golden tests, CI template, blog-craft CI | **both golden tests green = parity proven** |
| **P6 — Updater** | blog-craft | schema migration ladder, 3-way-merge update flow, dry-run diff, update smoke | update smoke (vN→vN+1) green |
| **P7 — Migrate frank** | frank | author frank's `.blog-craft.yaml`, materialize from blog-craft, retire inline skills + diverged script | frank golden test green against migrated repo; stoa still green |

P1–P6 never touch frank's working blog. P7 is the lowest-risk cutover, guarded
by the harness built in P5.

---

## 11. Risks & open items

- **blog-craft fr-enablement:** P1–P6 execute in `../blog-craft`. It needs a
  devcontainer profile for fr-isolation, or its plans dispatch under whatever
  isolation blog-craft supports. Resolve before autonomous execution.
- **Generator port is the one non-mechanical change** (hardcoded order → config
  order). De-risked by `smoke-image-compose` prompt-equality.
- **Manifest completeness:** an unclassified path defaults to `content` (safe:
  never overwritten, never asserted) — but a `framework` path missing from the
  manifest silently drops from the parity test. Add a "no unclassified
  materialized path" assertion.
- **Roadmap-as-data fidelity:** frank's roadmap shortcode must render the data
  file to visually-equivalent output; covered by Hugo-build smoke, not pixel diff.
- **stoa config migration** must be byte-reviewed; the stoa golden test is the
  backstop.

---

## 12. Acceptance criteria (definition of done)

1. `blog-craft + frank/.blog-craft.yaml` → scratch dir → **zero structural
   drift** vs frank `blog/` (manifest `framework`+`merged` paths).
2. `blog-craft + stoa/.blog-craft.yaml` → scratch dir → **zero structural drift**
   vs stoa-blog.
3. `smoke-image-compose` proves prompt-string equality for frank and stoa.
4. `smoke-papers` green with papers on; stoa scaffold proves papers absent when off.
5. Update smoke proves a non-destructive, reviewed v2→v3 path.
6. frank migrated (P7): inline blog skills + `generate-all-images.py` retired;
   frank's blog is produced/maintained by blog-craft + config; stoa still green.

---

## Implementation Plans

blog-craft phases (P1–P6) are planned + tracked in the blog-craft repo
(`derio-net/blog-craft`, PRs #4/#5/#6). Only frank's P7 cutover is planned here.

| Plan | Repo | File | Depends on |
|------|----------------|--------|-------|
| 2026-06-30-frank-blog-craft-p7 | `derio-net/frank` | `2026-06-30-frank-blog-craft-p7` | — |
