---
title: "Building The Frank Papers — Research Infrastructure for a Third Series"
series: ["building"]
layer: repo
date: 2026-05-18
draft: false
tags: ["papers", "blog", "hugo", "hextra", "mermaid", "dossier", "research", "shortcodes"]
summary: "A third blog series — research-grade landscape reviews framed as decisions, gated behind a committed dossier before any paper can be drafted."
weight: 31
reader_goal: "Set up a multi-series Hugo paper infrastructure with dossier gate, cross-series linking, custom shortcodes, and agent-executable workflows"
diataxis: tutorial
last_updated: 2026-07-16
---

The cluster has two voices already. The Building series answers *how*. The Operating series answers *how to run*. Neither answers *why this and not the other twelve options*.

**The Frank Papers** are research-grade landscape reviews. Each paper maps the vendor space for one capability, grades the options, then returns to Frank's choice as a worked case study — honest about where that choice would not generalize. Every paper carries a ≤150-word TL;DR.

This post is about the infrastructure that makes a paper legal to ship. Phase 0 produces no published content — it produces the toolchain.

## Why a Third Series

Building and Operating both center Frank. The narrative arc is "I tried this, here is what broke."

That voice is wrong for a decision-maker weighing Authentik against Keycloak. They want the landscape and trade-offs that hold across orgs. Frank's experience is one data point.

- **Building** — first person, narrative. ~3000 words.
- **Operating** — imperative, reference. ~1500 words.
- **Papers** — third person, analytical, with a worked-example coda. ~5000 words plus TL;DR.

## The Dossier Gate

The load-bearing piece of Phase 0 is a pre-commit hook that refuses to let a Papers `index.md` be staged unless a committed research dossier passes validation:

```bash
$ git commit -m "draft Paper 04 — GPU operators"
DOSSIER GATE: no dossier found for staged paper '04-gpu-operators'
  Expected: docs/papers-dossiers/04-gpu-operators/dossier.md
```

The dossier is a structured Markdown file with six required sections:

```markdown
## Vendors in scope
- name: NVIDIA GPU Operator
  positioning: incumbent
- name: Intel Device Plugin / DRA
  positioning: open-alternative

## Primary sources
# ≥5 sources, each with type in {vendor-docs, paper, postmortem, talk, benchmark}

## Frank artefacts
# ≥3 — kind: grafana-screenshot | asciinema | yaml | commit | incident

## Diagrams planned
## Named gaps
## Counter-arguments considered
```

`scripts/validate-dossier.py` enforces:
- **≥3 vendors in scope** — no one-vendor review.
- **≥5 primary sources** with reachable URLs.
- **≥3 Frank artefacts** linking to operational evidence.
- **≥1 named gap** — the question you could not answer.
- **≥1 counter-argument** the paper deliberately engaged with.

That last one is why the gate exists. It forces the file to *exist* before the index.md can be committed, and the structure forces naming the opposing view at dossier time.

The validator runs from `.githooks/pre-commit` — any staged paper triggers validation. Two consequences: the dossier ships with the paper on the same SHA, and an agent dispatched to research has the gate to push against.

## The Scaffold Script

```bash
$ scripts/scaffold-paper.sh 04 gpu-operators
Created blog/content/docs/papers/04-gpu-operators/index.md
Created docs/papers-dossiers/04-gpu-operators/dossier.md
```

Both files land with section skeletons. The Hugo `index.md` has `§1–§6` outline, Mermaid placeholders, frontmatter with `series: papers`. The dossier has the six section headers with stub entries.

## Hugo Foundation

Three taxonomies, one nav entry:

```toml
[taxonomies]
  series = "series"
  capabilities = "capabilities"
  references = "references"

[[menu.main]]
  identifier = "papers"
  name = "Papers"
  pageRef = "/docs/papers"
  weight = 3
```

`series` is what the backlink partial queries. `capabilities` gives "show me all Papers tagged auth" navigation. `references` collects bibliography entries.

## Visual System

A Mermaid theme keyed to Frank's palette, applied only on `.paper-post` pages:

```javascript
mermaid.initialize({
  theme: 'base',
  themeVariables: {
    primaryColor: '#1f2937',
    primaryTextColor: '#f3f4f6',
    primaryBorderColor: '#0d9488',
    lineColor: '#fb923c',
  }
});
```

Gated in `single.html` — `body.paper-post` matches only Papers pages, so Building and Operating posts inherit nothing.

## Five Shortcodes

| Shortcode | Where |
|-----------|-------|
| `pullquote` | §3 architecture comparison |
| `scar` | §4 operational evidence |
| `capability-matrix` | §2 vendor landscape — feature grid |
| `landscape` | §2 vendor landscape — Mermaid quadrantChart |
| `dossier-link` | section header — dossier chip |

`landscape` wraps a Mermaid `quadrantChart`:

```go-html-template
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

## Cross-Series Linking — Zero Retrofit Writes

29 Building posts and 24 Operating posts already exist. Retrofitting links onto each would be a write-multiplier nightmare. The linking is single-sourced from the **Paper's** frontmatter:

```yaml
related_building: "docs/building/10-local-inference"
related_operating: "docs/operating/07-inference"
```

Two partials read these keys:

- **`papers-forwardlinks.html`** — on Papers pages, renders chips to related Building/Operating posts.
- **`papers-backlink.html`** — on non-Papers pages, iterates all Papers, matches by path, renders a chip.

Wired into `single.html`. Existing `index.md` files are untouched forever. Adding a new Paper is a one-line frontmatter add; Hugo picks up the backlink at render time.

## Banner Images

Series banner needed three iterations: first pass Frank in green shirt (blended with skin), second pass fixed composition but still green-on-green, third pass explicit "Frank in white dress shirt" — that is the production version.

Per-series reference images live under `.reference-pool/papers/` (refactored from a single shared reference in PR #380).

## Agent Docs

The Papers workflow runs end-to-end through agents. Two files make that possible:

- **`agents/rules/repo-papers.md`** — lifecycles, frontmatter schema, dossier format, diagram-types-by-section table.
- **`agents/skills/papers/SKILL.md`** — invoked as `/papers` in Claude Code, enforces dossier gate and scaffold commands.

## What Got Reverted

Paper 00 (prologue) landed three commits depending on phase-0 surface that had not merged yet — `validate-dossier.py` and cover-image tooling did not exist on `main`. `3cd2f78` reverts cleanly. Lesson: a paper cannot depend on infrastructure not yet on `main`.

## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---------------|-----------------|-----------------|--------|
| **Paper 00 landed before Phase 0** — pre-commit hook tried to run validator that did not exist | Two branches open simultaneously; merge order followed writing energy, not dependency arrow | Reverted Paper 00 phases 1-3; re-landed after Phase 0 completed | `3cd2f78` |
| **Banner image Frank blended with background** — green shirt on green background, silhouette unreadable | Prompt did not specify shirt color; Gemini defaulted to green | Explicit "white dress shirt" in prompt text | `10cb465` |
| **Dossier link rendered twice** — both inline shortcode and automatic footer injection fired | `single.html` auto-injects dossier chip; shortcode in body adds a second | Documented gotcha: use either the shortcode or the auto-injection, not both | — |
| **Spec referenced old file paths** — `.claude/rules/` and `.claude/skills/` moved to `agents/` | Blog refactored between spec (April) and Phase 0 (May) | Translated paths during implementation | — |

## Recovery Path

| Symptom | Cause | Fix |
|---------|-------|-----|
| Pre-commit hook blocks commit with "dossier not found" | Paper index.md staged without corresponding dossier | Run `scripts/scaffold-paper.sh <NN> <slug>` and fill in dossier sections |
| Dossier validation fails with "≥3 vendors required" | Only 1-2 vendors in scope | Add more vendor entries to dossier Vendors in scope section |
| Mermaid diagram renders with default palette | Page does not have `.paper-post` body class | Verify `single.html` gates `body` class on `eq .Params.series "papers"` |
| Backlink chips not appearing on Building posts | Paper's `related_building` path does not match post path | Verify path in Paper frontmatter matches the actual file path |

## References

- [Hextra theme](https://imfing.github.io/hextra/) — taxonomies, cards, custom CSS scoping
- [Mermaid theming guide](https://mermaid.js.org/config/theming.html)

**Next: [Edge Observability — Watching Frank's Edge Without Watching Frank's Edge Burn](/docs/building/31-edge-observability)**
