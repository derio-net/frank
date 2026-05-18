---
title: "Building The Frank Papers — Research Infrastructure for a Third Series"
date: 2026-05-18
draft: false
tags: ["papers", "blog", "hugo", "hextra", "mermaid", "dossier", "research", "shortcodes"]
summary: "A third blog series — research-grade landscape reviews framed as decisions, gated behind a committed dossier before any paper can be drafted."
weight: 31
---

The cluster has two voices already. The [Building series]({{< relref "/docs/building/00-overview" >}}) answers *how* — step by step, with the manifests and the gotchas. The [Operating series]({{< relref "/docs/operating/00-overview" >}}) answers *how to run* — day-to-day commands, the wrong things to type, what to check first when the page goes red. Neither answers *why this and not the other twelve options*. That's the gap the third series fills.

**The Frank Papers** are research-grade landscape reviews. Each paper maps the vendor space for one capability, grades the options against criteria a staff engineer or CTO actually brings to the table, then returns to Frank's choice as a worked case study — honest about where that choice wouldn't generalize. Every paper carries a ≤150-word TL;DR up front, so an engineering manager reading over a shoulder gets the conclusion without scrolling.

This post is about the infrastructure that makes a paper *legal to ship*. Phase 0 produces no published content — it produces the toolchain. The first paper comes after.

## Why a Third Series at All

Building and Operating both center Frank. The cluster is the subject. The narrative arc is "I tried this, here is what broke, here is what I changed."

That voice is the wrong voice for a decision-maker. Someone who is weighing Authentik against Keycloak against Auth0 doesn't want the homelab build journal — they want the landscape, the trade-offs that hold across orgs, and a worked example with named scar tissue. Frank's experience is one data point in that example, but the paper itself argues from a wider perch.

So the Papers series sits at a different altitude:

- **Building** — first person, narrative, exhaustive. Length: ~3000 words. Voice: workshop journal.
- **Operating** — imperative, reference, terse. Length: ~1500 words. Voice: SRE handbook.
- **Papers** — third person (mostly), analytical, with a worked-example coda. Length: ~5000 words plus a TL;DR. Voice: a research note you'd pay €5k for, minus the consultancy hand-waving.

The cluster doesn't need to argue for itself in Building or Operating — the posts *show* the cluster. Papers is where it argues. Against cloud defaults where the argument holds. Against homelab romanticism where that applies. Always with the dossier behind it.

## The Dossier Gate

The single load-bearing piece of Phase 0 is a pre-commit hook that refuses to let a Papers `index.md` be staged unless a committed research dossier passes validation.

```bash
$ git commit -m "draft Paper 04 — GPU operators"
DOSSIER GATE: no dossier found for staged paper '04-gpu-operators'
  Expected: docs/papers-dossiers/04-gpu-operators/dossier.md
  Run: scripts/scaffold-paper.sh <NN> <slug> to create it
```

The dossier is a structured Markdown file with six required sections, parsed as YAML blocks under `##` headers:

```markdown
## Vendors in scope
- name: NVIDIA GPU Operator
  positioning: incumbent
  primary_url: https://github.com/NVIDIA/gpu-operator
- name: Intel Device Plugin / DRA
  positioning: open-alternative
  primary_url: https://github.com/intel/intel-device-plugins-for-kubernetes
- name: AMD GPU Operator
  positioning: third-party
  primary_url: https://github.com/ROCm/k8s-device-plugin

## Primary sources
- title: "NVIDIA GPU Operator architecture overview"
  type: vendor-docs
  url: https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/overview.html
  quoted_passages: ["..."]
  relevance: "Foundational architecture for the incumbent."
# ... ≥5 sources total

## Frank artefacts
# ≥3 — kind: grafana-screenshot | asciinema | yaml | commit | incident

## Diagrams planned
## Named gaps
## Counter-arguments considered
```

`scripts/validate-dossier.py` parses those YAML blocks and enforces:

- **≥3 vendors in scope** — no one-vendor "review."
- **≥5 primary sources**, each with `type` in `{vendor-docs, paper, postmortem, talk, benchmark}` and a reachable URL (`HEAD` check at validation time).
- **≥3 Frank artefacts** linking the analysis back to operational evidence on this cluster.
- **≥1 named gap** in the analysis — the question you couldn't answer with the available evidence.
- **≥1 counter-argument** the paper deliberately engaged with.

That last one is the whole reason the gate exists. It is too easy to write a paper that argues itself into Frank's choice without ever taking the strongest opposing view seriously. The gate forces the file to *exist* before the index.md can be committed, and the structure forces the author (human or agent) to name the opposing view at dossier time, before the prose starts pulling its punches.

The validator is invoked from `.githooks/pre-commit`:

```bash
PAPER_FILES=$(git diff --cached --name-only --diff-filter=ACM \
  | grep -E '^blog/content/docs/papers/[0-9]+-[^/]+/index\.md$' || true)

for PAPER_INDEX in $PAPER_FILES; do
  PAPER_DIR=$(echo "$PAPER_INDEX" | sed 's|blog/content/docs/papers/||; s|/index\.md||')
  DOSSIER_PATH="docs/papers-dossiers/${PAPER_DIR}/dossier.md"
  [ -f "$DOSSIER_PATH" ] || { echo "DOSSIER GATE: missing $DOSSIER_PATH"; exit 1; }
  "$REPO_ROOT/scripts/validate-dossier.py" "$DOSSIER_PATH"
done
```

Two intentional consequences:

1. The dossier ships **with** the paper, in the repo, on the same SHA. Anyone reading Paper 04 a year from now can `git show HEAD:docs/papers-dossiers/04-gpu-operators/dossier.md` and see the sources, gaps, and counter-arguments the author was working from.
2. An agent dispatched to research a paper has the gate to push against — there's no path to "I'll just write the prose now and fill the dossier later." The prose can't pass `git commit` without it.

The dossier itself can be written by an agent. The validator runs in a hot loop until it passes. By the time a human reviews the paper, the structural rigor is already there.

## The Scaffold Script

`scripts/scaffold-paper.sh` creates the two halves at once:

```bash
$ scripts/scaffold-paper.sh 04 gpu-operators
Created blog/content/docs/papers/04-gpu-operators/index.md
Created docs/papers-dossiers/04-gpu-operators/dossier.md
```

Both files start with the section skeleton already in place. The Hugo `index.md` lands with the full §1–§6 outline (stack position → vendor landscape → architecture comparison → operational evidence → decision rubric → return-to-Frank's-choice), Mermaid placeholders ready, and the frontmatter pre-populated with `series: papers`, the right `paper_number`, and empty `related_building` / `related_operating` slots.

The dossier lands with the six section headers and a stub entry in each. The first thing the author (or agent) does is fill in the actual vendors, sources, artefacts. Then `python scripts/validate-dossier.py docs/papers-dossiers/04-gpu-operators/dossier.md` until it returns clean. Then drafting can begin.

## Hugo Foundation — Three Taxonomies, One Nav Entry

The Hextra theme's section system is per-directory; `blog/content/docs/papers/` is the bundle root. Two things happen at config time so the section feels native:

```toml
# blog/hugo.toml
[taxonomies]
  tag = "tags"
  series = "series"
  capabilities = "capabilities"
  references = "references"

[[menu.main]]
  identifier = "papers"
  name = "Papers"
  pageRef = "/docs/papers"
  weight = 3
```

`series`, `capabilities`, and `references` are net-new. The `series` taxonomy is what `papers-backlink.html` queries at render time to find Papers that link back to the current Building/Operating page (more on that below). `capabilities` gives readers a "show me all Papers tagged auth" navigation. `references` collects bibliography entries across the corpus.

The Papers nav entry sits between Operating and the GitHub link, weight 3, no submenu. Section landing lives at `/docs/papers/_index.md` with a title, a one-sentence positioning statement, and (when paginated) a list of papers by `paper_number`. Right now it says "First paper coming soon." in production. That's the truthful state.

The site-root `_index.md` was rewritten from a custom `frank-series-cards` shortcode block to native Hextra `{{< cards >}}` / `{{< card >}}` shortcodes — three cards instead of two, with the Papers card pointing at `/docs/papers/`. This was a quiet rebase of the spec, written when the landing was still on a bespoke shortcode. The blog had been refactored to Hextra-native cards in the interim, so Phase 0 followed the new pattern instead of preserving the old one.

## Visual System — Mermaid Frank Theme and the `.paper-post` Scope

Papers are diagram-dense. Mermaid Hextra ships with their default palette, which is fine for Building posts and wrong for Papers (which need a consistent visual signature across the corpus). So Phase 0 ships `blog/assets/js/mermaid-frank.js` — a small init script that registers a Mermaid theme keyed to Frank's color palette:

```javascript
mermaid.initialize({
  startOnLoad: true,
  theme: 'base',
  themeVariables: {
    primaryColor: '#1f2937',
    primaryTextColor: '#f3f4f6',
    primaryBorderColor: '#0d9488',
    lineColor: '#fb923c',
    secondaryColor: '#0d9488',
    tertiaryColor: '#1e293b',
    // ... plus contrast pairs for dark mode
  }
});
```

That theme only applies on pages with the `paper-post` body class. The class is gated in `single.html`:

```go-html-template
{{ $isPaper := eq .Params.series "papers" }}
<body class="{{ if $isPaper }}paper-post{{ end }}">
```

Same gate carries the matching CSS scope. `.paper-post` rules in `blog/assets/css/custom.css` give Papers slightly tighter type, denser tables, a different blockquote treatment for `{{< papers/pullquote >}}`, and the visual styling for `{{< papers/scar >}}` callouts. Building and Operating posts don't inherit any of it — `body.paper-post` only matches Papers pages.

The point is *consistency across the corpus, isolation from the rest of the site*. The day a reader lands on Paper 04 from a search result, every other Paper they click feels familiar. The day they navigate to a Building post from a Paper, the visual language returns to the build-journal voice without bleed-through.

## Five Shortcodes Under `papers/`

Five new Hugo shortcodes live in `blog/layouts/shortcodes/papers/`:

| Shortcode | Where it appears in a Paper |
|---|---|
| `pullquote` | §3 architecture comparison — pull the load-bearing sentence out of a vendor doc |
| `scar` | §4 operational evidence — call out a named incident on Frank |
| `capability-matrix` | §2 vendor landscape — feature-by-feature grid |
| `landscape` | §2 vendor landscape — Mermaid `quadrantChart` wrapper |
| `dossier-link` | section header — render the chip linking to the dossier for that paper |

`landscape` is the most fun. It wraps a Mermaid `quadrantChart` with positioning that's hard to remember from scratch:

```go-html-template
{{ $axes := .Get "axes" | default "complexity:flexibility" }}
{{ $vendors := .Get "vendors" }}
<div class="mermaid">
quadrantChart
    title {{ .Get "title" }}
    x-axis "{{ index (split $axes ":") 0 }}"
    y-axis "{{ index (split $axes ":") 1 }}"
    quadrant-1 "{{ .Get "q1" }}"
    quadrant-2 "{{ .Get "q2" }}"
    quadrant-3 "{{ .Get "q3" }}"
    quadrant-4 "{{ .Get "q4" }}"
{{ $vendors }}
</div>
```

The author writes one line in the paper:

```
{{</* papers/landscape
  title="Auth landscape — late 2025"
  axes="complexity:openness"
  q1="self-host friendly"
  q2="cloud-first incumbents"
  q3="walled gardens"
  q4="DIY territory"
  vendors="Authentik: [0.35, 0.85]\nKeycloak: [0.7, 0.8]\nAuth0: [0.85, 0.15]"
*/>}}
```

…and gets a quadrant chart in the Frank palette. Same idea for `capability-matrix` (renders as a styled table), `pullquote`, and `scar`. The diagram-types-by-section table in `agents/rules/repo-papers.md` codifies which type goes where, so a paper isn't a quadrant-chart-and-mermaid-flowchart soup.

`dossier-link` deserves a note. The Paper's single source of truth for "where is my dossier" is the path convention: `docs/papers-dossiers/NN-slug/dossier.md`. The shortcode renders a chip to that path. Phase 0 also wires `single.html` to *automatically* inject a footer dossier chip on every Papers page, so inline use of the shortcode is optional. There's a documented gotcha: don't do both in the same paper, or the chip renders twice.

## Cross-Series Linking — Zero Retrofit Writes

The bidirectional discovery surface across all three series is the part that took the most thinking and the least code.

The constraint: 29 Building posts and 24 Operating posts already exist. Retrofitting "→ See Paper NN" links onto each of them would be a write-multiplier nightmare every time a new Paper changed which Building post it relates to. So the linking is single-sourced from the **Paper's** frontmatter:

```yaml
---
title: "Local Inference — Choosing an Inference Stack for Self-Hosted LLMs"
series: papers
paper_number: 10
related_building: "docs/building/10-local-inference"
related_operating: "docs/operating/07-inference"
---
```

Two partials read those keys:

**`papers-forwardlinks.html`** runs on Papers pages, takes the `related_building` and `related_operating` paths from the current page's frontmatter, fetches those pages, and renders forward chips:

```html
🔧 Hands-on:
  <a href="/docs/building/10-local-inference/">Building — Local Inference …</a>
  <a href="/docs/operating/07-inference/">Operating — Operating on Local Inference</a>
```

**`papers-backlink.html`** runs on *non-Papers* pages (Building, Operating). It iterates `where .Site.Pages "Params.series" "papers"`, asks each Paper whether its `related_building` or `related_operating` matches the current page's path, and renders a chip on a match:

```html
🔬 Decision-level view:
  <a href="/docs/papers/10-local-inference/">Paper 10 — Local Inference …</a>
```

Both partials are wired into `single.html`. The existing Building and Operating `index.md` files are untouched and remain untouched forever. Adding a new Paper that links to two existing posts is a one-line frontmatter add; Hugo's next build picks up the backlink at render time and the chip appears on both targets simultaneously.

The whole linking surface is N edits per Paper, not N×M edits across the corpus. The 29 Building posts will sprout backlinks as Papers ship, with no retrofit writes touching them.

## Banner Images — Three Tries to Land the Cover

The series needed a visual signature. Phase 6 generates two assets: `tile-papers.png` (a 1424×752 16:9 image used as the landing-page card thumbnail) and `banner-papers.png` (a thin 1200×200 strip carrying the "The Frank Papers" title in the same retro-tech lettering as `banner-building.png` and `banner-operating.png`, shown above every Papers page by the `site-banner.html` partial).

The character brief sits in `agents/skills/papers/SKILL.md`:

> *Frank examining [domain object] with a decision-maker expression, wearing his thin black tie and round reading glasses.*

That's the consistent visual signature. Every per-paper cover gets a tie + glasses Frank in a setting that signals the paper's topic.

The series banner went through three iterations:

1. **First pass** — Frank in a green shirt at a whiteboard. The shirt blended with his skin, so the silhouette read flat.
2. **`a3729d7`** — regenerate, drop a duplicate Frank in the background, fix the thin-banner composition. Closer, but Frank was still green-on-green.
3. **`10cb465`** — explicit "Frank in **white dress shirt**, not green." That's the version in production now.

The prompt text in `blog/prompt_for_images.yaml` is verbose deliberately — the character-fidelity block ("no nose," "visible Frankenstein stitches," "RJ45-connector neck bolts," "messy black hair flat-top") is the same character sheet used on every cover, copy-pasted into each prompt entry so Gemini doesn't drift. The reference image at `blog/static/images/reference.png` is passed in too, with the explicit instruction to treat it as a strict character sheet for face shape and stitches.

The assets get generated by:

```bash
.venv/bin/python scripts/generate-all-images.py \
  -r blog/static/images/reference.png \
  --only banner-papers
```

(`tile-papers.png` was repurposed from the earlier wide whiteboard render and is checked into git directly; only the thin title-bearing banner is regenerated by the script.)

## Agent Docs — The Series Is Agent-Executable on Purpose

The Papers workflow runs end-to-end through agents. That's not an accident — it's the reason the dossier gate is machine-enforced. A human author can run the whole pipeline themselves, but the design point was: dispatch the research to a subagent, let it iterate against `validate-dossier.py` until the dossier passes, hand back the drafted paper, human reviews.

Two new files make that possible:

- **`agents/rules/repo-papers.md`** — the canonical reference. Lifecycle (scaffold → dossier → author dossier → draft → media → review → publish), frontmatter schema, dossier format, the cross-linking shape, the diagram-types-by-section table, the don't-double-render-dossier-chip warning, the scaffold/validate commands.
- **`agents/skills/papers/SKILL.md`** — invoked as `/papers` in Claude Code, enforces the dossier gate, the scaffold command, and the section skeleton. The skill description starts with the trigger: *"Write or continue a Frank Paper — enforces the dossier gate, scaffold commands, and section skeleton."*

`AGENTS.md` was updated to load both files in the standard rules + skills sweep. `scripts/validate-agent-config.sh` (already part of the pre-commit hook for any change to `AGENTS.md` or files under `agents/`) confirms both referenced files exist on every commit that touches the agent surface, so neither can be silently broken.

## What Got Reverted Along the Way

The honest part. Phases 0 and "Paper 00" (the prologue) were being worked on in parallel, on the assumption that Paper 00 could land before the infrastructure was complete. It couldn't. Paper 00's draft work landed three commits that took dependencies on phase-0 surface that hadn't been merged yet:

- `94c33be` — Paper 00 dossier construction (Phase 1 of frank-papers-paper-00)
- `1ee6a0a` — Paper 00 gate validation (Phase 2)
- `6a99957` — Paper 00 cover prompt + Mermaid validation (Phase 4)

By the time those landed, `validate-dossier.py` and the cover-image generation tooling on `main` didn't yet exist. The pre-commit hook on Paper 00's index.md tried to run a validator that wasn't installed, and the cover prompt referenced a YAML section that wasn't there.

`3cd2f78` reverts phases 1–3 of Paper 00 cleanly. `validate-dossier.py` then re-landed in Phase 8 of frank-papers-phase-0, in its proper home. Paper 00 will get re-drafted against the now-complete phase-0 foundation.

The lesson is small and old: a paper can't depend on infrastructure that isn't yet on `main`. Even when both branches are open at the same time, the merge order has to follow the dependency arrow, not the writing-energy arrow.

## The Compatibility Rebases

Two quiet rebases between the spec (2026-04-15) and Phase 0 (2026-05-16):

- The blog was refactored in the interim. Rules now live in `agents/rules/` (not `.claude/rules/`); skills now live in `agents/skills/` (not `.claude/skills/`). The spec's references to those paths were translated as Phase 0 went in.
- The landing-page cards were rewritten to native Hextra `{{< cards >}}` / `{{< card >}}` shortcodes. The spec had assumed a custom `frank-series-cards` block. Phase 0 followed the new convention, three cards under the same `{{< cards >}}` parent.

Neither rebase changed the *what* — three series, dossier gate, cross-series linking, Mermaid Frank theme. They changed where the files landed and which shortcode wrapper the cards used. Both are noted at the top of `_prose.md` so future re-readers of the plan see the deltas immediately.

## What's Next

The toolchain ships. The dossier gate works. The visual system, shortcodes, and cross-series linking are wired. The Papers landing page in production says *First paper coming soon.* — which is the truthful state. Paper 00, the prologue, is the first to come back through the now-complete pipeline.

After 00, the publish order is decision-weight, not table-of-contents order. The first capability paper is whatever question the cluster is currently best-positioned to answer with operational evidence — probably auth, probably storage, probably local inference. The dossiers will tell.

The cluster will, as ever, have opinions. Now it has the format for them.

## References

- [Spec — The Frank Papers]({{< ref "" >}}) — `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
- [Plan — Phase 0 Tooling]({{< ref "" >}}) — `docs/superpowers/plans/2026-05-16--repo--frank-papers-phase-0/`
- [Hextra theme](https://imfing.github.io/hextra/) — taxonomies, cards, custom CSS scoping
- [Mermaid theming guide](https://mermaid.js.org/config/theming.html) — `themeVariables` schema
- [Operating The Frank Papers]({{< relref "/docs/operating/25-frank-papers" >}}) — companion operating post (research-and-publish workflow)
