# The Frank Papers — Phase 0: Tooling & Scaffolding

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Complete (2026-05-18)

This plan delivers all infrastructure needed before the first Paper may begin its
dossier. Phase 0 is self-contained and produces no published content — it produces
the toolchain that makes content possible.

**Compatibility note vs. spec (2026-04-15):** The blog was refactored after the
spec was written. Two path changes apply throughout:
- Rules live in `agents/rules/` (not `.claude/rules/`).
- Skills live in `agents/skills/` (not `.claude/skills/`).
- Landing page uses Hextra `{{< cards >}}` / `{{< card >}}` shortcodes (not a
  custom `frank-series-cards` block).

## Phase 1: Hugo foundation

Add taxonomies, Papers nav entry, section `_index.md`, and the landing-page card.
No visual work yet — just the Hugo wiring that everything else builds on.
Can run alongside Phase 5 and Phase 7.

## Phase 2: Visual system

Mermaid Frank theme, `.paper-post` CSS scoping, and the `single.html` body-class
gate. Depends on Phase 1 (needs the `series: papers` taxonomy to be registered).

## Phase 3: Hugo shortcodes

Five shortcodes under `blog/layouts/shortcodes/papers/`: `pullquote`, `scar`,
`capability-matrix`, `landscape`, `dossier-link`. Depends on Phase 1.
Can run in parallel with Phases 2 and 4.

## Phase 4: Cross-series partials

`papers-backlink.html` and `papers-forwardlinks.html`, wired into `single.html`.
Zero retrofit writes to existing posts — backlinks are render-time query.
Depends on Phase 1. Can run in parallel with Phases 2 and 3.

## Phase 5: Research tooling

`scripts/validate-dossier.py`, `scripts/scaffold-paper.sh`, and the pre-commit
hook gate. Fully independent — run in parallel with Phase 1.

## Phase 6: Banner images

Two new Gemini prompts for the series-level images (`banner-papers` 1200×630 and
`banner-papers-thin` wide strip). Depends on Phase 1 (needs the landing page card
to know what image to reference).

## Phase 7: Agent docs

`agents/rules/repo-papers.md` and `agents/skills/papers/SKILL.md` plus AGENTS.md
updates. Fully independent — run in parallel with Phase 1.

## Phase 8: Validation & completion

Hugo build clean, pre-commit hook test, vk plan spec-index, final commit.
Depends on all prior phases.

## Phase 9: Post-deploy checklist

Standard checklist for a repo/meta layer.

## Phase summary

| # | Phase | Depends on | Tag |
|---|-------|-----------|-----|
| 1 | Hugo foundation | — | agentic |
| 2 | Visual system | 1 | agentic |
| 3 | Hugo shortcodes | 1 | agentic |
| 4 | Cross-series partials | 1 | agentic |
| 5 | Research tooling | — | agentic |
| 6 | Banner images | 1 | agentic |
| 7 | Agent docs | — | agentic |
| 8 | Validation & completion | 2,3,4,5,6,7 | agentic |
| 9 | Post-deploy checklist | 8 | manual |
