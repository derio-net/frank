# The Frank Papers — Third Blog Series

**Layer:** repo
**Date:** 2026-04-15
**Status:** Approved (pending user review of this spec)

## Summary

Launch a third blog series on the Frank blog called **The Frank Papers** — long-form, research-driven posts that frame each capability on the cluster as a *decision*. Each paper maps the vendor landscape in its capability domain, grades the options against criteria a technical decision-maker would actually use, and returns to Frank's choice as one worked example — including honest notes on where that choice would not generalize. The primary reader is a staff engineer, architect, or CTO; every paper carries a ≤150-word TL;DR for managers reading over their shoulder.

The series is 21 papers total: a prologue (Paper 00) plus 20 capability papers mapped to the layer registry. Two papers (workflow automation, feature-level health) are deferred to Phase 2 because the underlying Frank work is too nascent to write responsibly about. Papers publish in decision-weight order, not in TOC order — readers find the series through the paper on the topic they were already searching for.

Every paper gates on a committed **research dossier** (vendors in scope, primary sources, Frank artefacts, named gaps, counter-arguments considered) before drafting may begin. The dossier gate is machine-enforced via a pre-commit script and designed to be agent-executable so research can be parallelized across subagents without losing rigor.

Visually, the series reuses the existing Hextra page-bundle pattern but gets its own banner (Frank at a whiteboard, with thin round reading glasses and a thin black necktie — a consistent visual signature across every Papers cover), a Frank-themed Mermaid palette for diagrams, and four new Hugo shortcodes (`pullquote`, `scar`, `capability-matrix`, `landscape`, `dossier-link`). A bidirectional cross-series linking partial creates "→ Paper NN" chips on Building/Operating posts and "→ Building NN / Operating NN" chips on Papers, all single-sourced from Paper frontmatter — no retrofit writes to existing posts.

## Motivation

The existing Building Frank and Operating Frank series answer *how* (step-by-step construction) and *how to run* (day-to-day operations). Neither answers *why these choices and not others* — the question a decision-maker, budget holder, or QA lead brings to the cluster. That gap is what this series fills.

Three audiences benefit without the series having to compromise voice:

- **Technical decision-makers** (staff engineers, architects, CTOs) get a research-grade landscape review grounded in operational experience. The kind of post you'd pay a consultancy €5k for, with a case study instead of consultancy hand-waving.
- **Engineering managers / budget holders** get the TL;DR up front — 150 words that fit into a one-pager for their own stakeholders.
- **QA / reliability leads** get the failure-mode and observability discussion that falls out naturally of the "what scale changes" and "scar tissue" sections.

The series is also the right place to articulate Frank's thesis explicitly. Building/Operating show the cluster as fact; Papers argue *for* the cluster — against cloud defaults where that holds up, against homelab romanticism where that applies.

## Goals and Non-Goals

### Goals

- Ship Paper 00 (prologue) and 18 Phase 1 capability papers (papers 01–17 and 20), in decision-weight order.
- Enforce a research dossier gate before any paper's drafting may begin.
- Produce a visually distinct but pattern-consistent series on the existing Hextra site.
- Create bidirectional cross-series discoverability with zero retrofit writes to existing posts.
- Make the entire workflow (dossier → draft → media → publish) agent-executable via vk-plan scaffolding, so the series can run mostly via agentic dispatch with the author as reviewer.

### Non-Goals

- No fixed publish cadence. Publication is demand-driven on dossier readiness.
- No retrofit of Building or Operating posts for cross-linking (done via render-time query).
- No production of deep-dive papers in Phase 1. Deep-dives emerge from Phase 1 overview papers where a single section outgrows its budget.
- Not a consultancy-style vendor comparison without a case study. If Frank hasn't lived with the capability, the paper is deferred (as #18 and #19 are).

## Series structure

### Audience, POV, voice

- **Primary reader:** technical decision-maker.
- **Voice:** landscape-framed-by-Frank. Open with the capability question, map the vendor space, grade against a decision-maker rubric, return to Frank's pick as the case study, close with explicit generalization limits.
- **TL;DR:** every paper opens with a ≤150-word plain-prose summary written last, after the body has stabilized.

### Full paper list

TOC order below (bottom-of-stack upward). Publish order is separate and described further down.

| # | Title | Covers | Phase |
|---|-------|--------|-------|
| 00 | *Why Run Your Own Cluster in 2026?* (prologue, ≤1500 words) | framing | 1 |
| 01 | Heterogeneous Hardware as a Design Choice | hw | 1 |
| 02 | Immutable OS & Declarative Machines | os | 1 |
| 03 | eBPF Networking Without a Service Mesh | net | 1 |
| 04 | Distributed Storage on Bare Metal | stor | 1 |
| 05 | GPU Scheduling for Mixed Workloads | gpu | 1 |
| 06 | GitOps at Small Scale | gitops | 1 |
| 07 | The Observability Stack, Honestly | obs | 1 |
| 08 | Backup & DR Without a Vendor Contract | backup | 1 |
| 09 | Secrets Management Without the Bootstrap Chicken-and-Egg | secrets | 1 |
| 10 | Self-Hosted Inference & the LLM Gateway Pattern | infer | 1 |
| 11 | Identity for a Heterogeneous Stack | auth | 1 |
| 12 | Multi-Tenancy with vCluster | tenant | 1 |
| 13 | Self-Hosted CI/CD on a Homelab | Gitea + Tekton + Zot | 1 |
| 14 | Progressive Delivery & the Service-Mesh Tax | Argo Rollouts | 1 |
| 15 | Ingress, Forward-Auth, and the Service Catalog | Traefik + Homepage | 1 |
| 16 | Self-Hosted Media Generation | ComfyUI + GPU switcher | 1 |
| 17 | Agentic Orchestration & Safe Agent Workstations | Sympozium + secure-agent-pod + VK Remote | 1 |
| 18 | Workflow Automation Beyond CI/CD | n8n | 2 (deferred — need lived experience) |
| 19 | Feature-Level Health & the Alert-to-Issue Bridge | Blackbox + Pushgateway + Health Bridge | 2 (deferred — need lived experience) |
| 20 | Edge Clusters & Public Exposure | Hop + Headscale + Caddy | 1 |

### Publication order (Phase 1)

Publish in decision-weight order, leading with the highest-interest vendor fights to buy attention for the foundational papers.

**00 → 10 → 04 → 11 → 14 → 06 → 07 → 02 → 03 → 09 → 05 → 08 → 17 → 13 → 15 → 16 → 12 → 01 → 20**

### Cadence

No fixed cadence. Each paper advances through `dossier-ready → drafting → review → published` states at its own pace. The author commits to the dossier gate; ship velocity is emergent.

## Per-paper anatomy

### Skeleton (fixed order, fixed budgets)

| § | Section | Target words | Required media |
|---|---------|--------------|----------------|
| — | **TL;DR** | ≤150 | — |
| 1 | The capability | 200–350 | 1 stack-position diagram (Mermaid) |
| 2 | The landscape | 400–600 | 1 vendor landscape diagram + 1 capability matrix |
| 3 | How each option handles the hard part | 800–1400 | 1 architecture diagram per vendor (shared visual language) |
| 4 | What scale changes | 300–600 | 1–2 scale/benchmark charts OR ≥2 primary-source citations if no benchmark |
| 5 | Frank's choice, and what happened | 300–600 | ≥1 evidence artefact + ≥1 scar-tissue callout |
| 6 | When Frank's answer doesn't generalize | 200–400 | 1 decision flowchart (≤4 leaves) |
| 7 | Roadmap & where this space is going | 200–400 | Optional timeline + roadmap citations |
| 8 | References & further reading | — | Auto-rendered from frontmatter |

**Total budget per paper:** 2400–4200 words. Paper 00 caps at 1500.

### Frontmatter schema

```yaml
---
title: "Self-Hosted Inference & the LLM Gateway Pattern"
date: 2026-MM-DD
draft: false
weight: 10                            # drives sidebar order in /docs/papers/
series: papers                        # new taxonomy value
layer: infer                          # existing layer code for cross-linking
paper_number: 10
publish_order: 2
status: published                     # drafting | dossier-ready | review | published
tldr: |
  Three-paragraph exec summary, <= 150 words.
tags: ["inference", "llm", "gpu"]
capabilities: ["infer", "gpu"]        # A-style capability tag
related_building: "docs/building/10-local-inference"
related_operating: "docs/operating/07-inference"
references:
  - title: "Ollama design notes"
    type: vendor-docs                 # vendor-docs | paper | postmortem | talk | benchmark
    url: "https://ollama.com/blog/..."
  - title: "vLLM paper — Kwon et al. 2023"
    type: paper
    url: "https://arxiv.org/abs/2309.06180"
---
```

## Research workflow and dossier gate

### Dossier location and schema

Dossiers live in a new tree in the repo but outside Hugo content:

```
docs/papers-dossiers/
  00-why-homelab-in-2026/
    dossier.md
  10-self-hosted-inference/
    dossier.md
  ...
```

Dossier file format:

```yaml
---
paper: 10-self-hosted-inference
status: draft | ready | published
---

## Vendors in scope (≥3, typically 4–6)
- name: Ollama
  positioning: "one-line claim from their own marketing"
  primary_url: "https://..."

## Primary sources (≥5, ≥3 distinct `type` values)
- title: "..."
  type: vendor-docs | paper | postmortem | talk | benchmark
  url: "..."
  quoted_passages: [">..."]
  relevance: "one sentence"

## Frank artefacts (≥3, ≥2 distinct `kind` values)
- kind: grafana-screenshot | asciinema | yaml | commit | incident
  path_or_url: "..."
  date: 2026-MM-DD
  demonstrates: "one sentence"

## Diagrams planned
- landscape:
    x_axis: "centralized ↔ distributed"
    y_axis: "OSS ↔ commercial"
    vendors_plotted: [...]
- architecture_comparison:
    vendors: [...]
- decision_tree:
    leaves: 4

## Named gaps (≥1)
- "No published head-to-head benchmark for [X] vs [Y] at <=2 concurrent users"

## Counter-arguments considered (≥1)
- "The general answer is 'just use an API' — why doesn't that win?"
```

### Gate rules (enforced before drafting)

A paper's draft may not begin until `scripts/validate-dossier.py` passes for its dossier:

- `vendors_in_scope` ≥ 3
- `primary_sources` ≥ 5, spanning ≥ 3 distinct `type` values
- All `primary_sources[].url` return HTTP 200 at validation time
- `frank_artefacts` ≥ 3, spanning ≥ 2 distinct `kind` values
- `named_gaps` ≥ 1
- `counter_arguments_considered` ≥ 1

The gate is wired into `.githooks/pre-commit` for any commit that adds a `content/docs/papers/NN-*/index.md` file. A paper draft cannot land without its matching dossier being valid.

### Agentic execution model

The workflow is designed to be parallelizable and agent-friendly. A typical paper moves through a vk-plan with these phases:

- **P1 — Dossier construction.** One subagent per vendor builds a mini-dossier fragment (positioning, primary sources, architecture notes). A merger subagent consolidates. A reviewer subagent audits gap rules and counter-arguments.
- **P2 — Gate.** `validate-dossier.py` runs and fails loud on any missing requirement.
- **P3 — Draft.** A skeleton-filler subagent produces a first-pass draft from the validated dossier, populating every section and marking every media slot either filled or `TODO:<type>`.
- **P4 — Media fill.** Diagrams, screenshots, asciinema, charts, and per-paper cover image generated and inserted.
- **P5 — Review and publish.** Author review, polishing, TL;DR write-up (last), publish-time taxonomy validation.

Author's role: reviewer at P2 (gap-naming is a judgment call), P5 (final voice pass). Everything else is agent-executable with human checkpoints.

## Media system

### Diagrams — Mermaid, Frank-themed

A central theme file at `blog/assets/js/mermaid-frank.js` defines brand colors matched to the existing Frank palette (dark navy background, electric blue accents, Frank-green highlights, stitched dashed lines for failure paths). Loaded via `layouts/partials/custom/head-end.html` gated on `.HasShortcode "mermaid"` or on `series: papers` in frontmatter.

Section-to-diagram-type mapping:

| Section | Mermaid type | Use |
|---------|--------------|-----|
| §1 stack position | `flowchart LR` with subgraphs | Where the capability sits in the stack |
| §2 vendor landscape | `quadrantChart` (Mermaid 10.6+) | 2×2 positioning of vendors |
| §2 capability matrix | Markdown table with semantic classes | High-density per-vendor comparison |
| §3 architecture comparison | `flowchart TD` per vendor, shared shapes | Internal structure of each option |
| §6 decision tree | `flowchart TD`, ≤4 leaves | "Should you pick this" rubric |

Escape hatch for diagrams too dense for Mermaid: export SVG, commit to page bundle, link inline. Goal: keep 90%+ of diagrams in Mermaid for Git-diff-ability.

### Custom Hugo shortcodes

New shortcodes to build under `blog/layouts/shortcodes/papers/`:

- **`{{< papers/pullquote source="..." url="..." >}}quoted text{{< /papers/pullquote >}}`** — styled block quote with citation chip.
- **`{{< papers/scar date="2026-MM-DD" >}}markdown...{{< /papers/scar >}}`** — scar-tissue callout box with date stamp. 1–3× per paper.
- **`{{< papers/capability-matrix data="vendors" >}}`** — reads a YAML data file in the page bundle (`data/vendors.yaml`) and renders a styled comparison table with yes/partial/no glyphs.
- **`{{< papers/landscape axes="x:OSS↔commercial,y:centralized↔distributed" >}}...{{< /papers/landscape >}}`** — thin wrapper around Mermaid `quadrantChart` enforcing consistent styling.
- **`{{< papers/dossier-link paper="10-self-hosted-inference" >}}`** — renders a small link at the bottom of every paper pointing at the committed dossier file on GitHub. Builds trust by making the research trail visible.

### References taxonomy

Enable a new Hugo taxonomy `references` populated from Paper frontmatter. Renders as:

- The auto-generated §8 bibliography of each Paper.
- A cross-series index at `/references/` listing every cited source with back-links to the Papers that cite it.

### Cover imagery

Three new Gemini prompts added to `blog/prompt_for_images.yaml`. All three carry the shared visual signature: **Frank wears thin round reading glasses resting low on the nose and a thin black necktie.**

- **`banner-papers`** (1200×630, Papers card on landing page): Frank at a wall-sized whiteboard drawing a decision tree that branches across the wall. Floor scattered with server parts being *considered*, not assembled. Warm overhead work-lamp light. Distinct from the triumphant Building cover — here Frank is thinking, not winning.

- **`banner-papers-thin`** (wide thin strip for `/docs/papers/` section-page hero): wide low silhouette of Frank seated at a desk covered in books, terminals, and schematics, annotating a diagram with a marker. Profile view. No text.

- **Per-paper covers** (one per paper): prompt template `"Frank examining [domain object] with a decision-maker expression (curious / skeptical / weighing), wearing his thin black tie and round reading glasses."` Per-paper prompts drafted at dossier-complete time, generated at draft time.

## Site integration

### URL and content tree

```
blog/content/docs/papers/
  _index.md                      # section landing — hero + map of published papers
  00-why-homelab-in-2026/
    index.md
    cover.png
  01-heterogeneous-hardware/
    index.md
    cover.png
    data/
      vendors.yaml               # capability-matrix source
  ...

docs/papers-dossiers/            # research artefacts, not Hugo content
  00-why-homelab-in-2026/
    dossier.md
  ...
```

URL pattern: `/docs/papers/10-self-hosted-inference/` — numbered, slugged, mirrors Building/Operating. Paper numbers follow TOC order (not publish order) so browsers of `/docs/papers/` see a logical sequence.

### Navigation

**Top nav** (`hugo.toml`): add a third content entry:

```toml
[[menu.main]]
  name = "Papers"
  pageRef = "/docs/papers"
  weight = 3                     # Search becomes 4, GitHub 5
```

**Sidebar**: auto-generated by Hextra from numbered page bundles, same as Building/Operating. `_index.md` sets `sidebar.open: true`.

**Landing page** (`content/_index.md`): add a third `frank-series-cards` block below the Operating card — "The Frank Papers" with `banner-papers.png` cover, linked to `/docs/papers/`.

### Cross-series discoverability — bidirectional, zero retrofit

The Paper's frontmatter is the single source of truth:

```yaml
related_building: "docs/building/10-local-inference"
related_operating: "docs/operating/07-inference"
```

A new Hugo partial `layouts/partials/papers-backlink.html` runs on every Building/Operating post's `single.html`. At render time it:

1. Queries `where .Site.Pages "Params.series" "papers"`.
2. Filters to Papers whose `related_building` or `related_operating` matches the current page's path.
3. Renders a "→ The decision-level view: Paper NN — [title]" chip if a match exists, nothing otherwise.

A companion partial `layouts/partials/papers-forwardlinks.html` runs on Papers pages and renders "→ Hands-on: Building NN / Operating NN" chips from `related_building` / `related_operating`.

This design means:

- Zero writes to existing Building/Operating posts.
- When a Paper is renamed, unpublished, or has its `related_*` changed, all backlinks update on the next Hugo build automatically.
- Reverse links only appear when the Paper exists and references the post — no stale chips on unpublished papers.

### Hextra wiring

- **Mermaid theme** loaded via `custom/head-end.html`, scoped to Papers pages.
- **Shortcode CSS** appended to `blog/assets/css/custom.css`, scoped under `.paper-post` to avoid polluting Building/Operating.
- **`.paper-post` body class** applied by a `layouts/docs/single.html` override gated on `series: papers` in frontmatter, enabling scoping.

### RSS sub-feed

`/docs/papers/index.xml` — readers can subscribe to Papers only. Hugo generates it automatically for the section.

### Capability cross-index

A new taxonomy page `/capabilities/<code>/` (e.g., `/capabilities/infer/`) lists the Building post, Operating post, and Paper for a given capability side-by-side. Auto-generated from the `capabilities:` frontmatter field. One-stop view of "everything we've written about storage/auth/inference/etc."

## Phase 0 — Tooling and scaffolding

Before Paper 00 may begin its dossier, the following must be in place. This is one vk-plan's worth of work.

1. Add `series`, `capabilities`, `references` taxonomies to `hugo.toml`.
2. Create `content/docs/papers/_index.md` with the section banner + "first paper coming" stub.
3. Generate `banner-papers.png` and `banner-papers-thin.png` (Gemini prompts added to `prompt_for_images.yaml`).
4. Add third card to `content/_index.md` (landing page) with "Launching soon" copy.
5. Build five shortcodes under `blog/layouts/shortcodes/papers/`: `pullquote`, `scar`, `capability-matrix`, `landscape`, `dossier-link`.
6. Build Mermaid Frank theme at `blog/assets/js/mermaid-frank.js` and wire into `custom/head-end.html`.
7. Build `scripts/validate-dossier.py` and wire into `.githooks/pre-commit`.
8. Build `scripts/scaffold-paper.sh NN slug` — creates both the Hugo page bundle and the dossier from templates.
9. Add `papers-backlink.html` and `papers-forwardlinks.html` partials to `single.html`.
10. Document the workflow in `.claude/rules/repo-papers.md` (mirrors `repo-blog.md`).
11. Add a `/papers` skill (`.claude/skills/papers/`) mirroring `blog-post` but scoped to Papers, enforcing the dossier gate and scaffolding.

Phase 0 done → Paper 00 dossier → Paper 00 draft → publish → Phase 1 opens.

## Success criteria

- Paper 00 ships after Phase 0, establishing the series thesis and the visual/editorial pattern for every subsequent paper.
- Bidirectional cross-series links visible on every Building/Operating post that has a matching Paper, rendered at build time from Paper frontmatter with no retrofit writes.
- Every published Paper's dossier is committed under `docs/papers-dossiers/`, linked from the paper via the `dossier-link` shortcode, and passes `scripts/validate-dossier.py`.
- The full pipeline (dossier construction → gate → draft → media fill → publish) runs end-to-end via agent dispatch on at least one Paper early in Phase 1, proving the "mostly agentic" execution model.
- Phase 2 papers (#18, #19) ship only after the underlying Frank capability has accumulated ≥3 months of lived operational experience — earlier would violate the "no brochures" principle.

(No time-based targets. Cadence is emergent.)

## Open questions for future decisions

- **Deep-dive upgrade criteria.** A Phase 2 deep-dive post gets written when a Phase 1 overview's §3 grows beyond its 1400-word budget during drafting. Explicit threshold to be documented in `repo-papers.md`.
- **Cross-posting.** Whether to syndicate Papers to Substack / Medium / LinkedIn long-form. Defer until after 3–5 Papers published — syndication strategy benefits from having a sample.
- **Reader feedback loop.** Comments, email replies, or issue-tracker-style "errata" per paper. Start without, add only if readers ask.

## Related documents

- Layer registry: `docs/layers.yaml`
- Existing blog architecture rules: `.claude/rules/repo-blog.md`
- Existing post skill: `.claude/skills/blog-post/`
- Hextra migration spec: `docs/superpowers/specs/2026-04-13--repo--blog-hextra-migration-design.md`

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| The Frank Papers — Phase 0: Tooling & Scaffolding | derio-net/frank | `docs/superpowers/plans/2026-05-16--repo--frank-papers-phase-0/` | — |
| The Frank Papers — Paper 00: Prologue | derio-net/frank | `docs/superpowers/plans/2026-05-16--repo--frank-papers-paper-00/` | Phase 0 complete |
| 2026-05-18--repo--frank-papers-paper-10 | `derio-net/frank` | `docs/superpowers/plans/2026-05-18--repo--frank-papers-paper-10/` | — |
| The Frank Papers — Paper 04: Distributed Storage on Bare Metal | derio-net/frank | `docs/superpowers/plans/2026-05-18--repo--frank-papers-paper-04/` | Phase 0 complete; Paper 00 published |
