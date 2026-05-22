# Paper Bibliography Rendering — Dossier → §8

**Spec:** `docs/superpowers/specs/2026-05-22--repo--paper-bibliography-rendering-design.md`
**Status:** Planning — drafted on top of approved spec `be8e87e`.

Every Frank Paper carries a research dossier under
`docs/papers-dossiers/<slug>/dossier.md` with primary sources, **quoted
passages** per source, and a **relevance** sentence per source explaining
where in the paper the source is used. The Frank Papers series spec
promised §8 References would auto-render from that research trail; in
practice no template was ever built and every paper today carries the
literal placeholder `*Auto-rendered from frontmatter by Hugo taxonomy.*`.

This plan closes the gap in six linear phases. The dossier becomes the
single source of truth: a sync script extracts `primary_sources` from each
dossier into `blog/data/papers/<slug>.yaml` (Phase 1); the data files are
generated for all 17 existing dossiers (Phase 2); two Hugo partials render
the per-paper §8 and a cross-series `/docs/papers/references/` index, both
reading the same data files (Phase 3); the literal `## References`
placeholder is stripped from every paper body (Phase 4); the redundant
`references:` frontmatter block is hard-deleted alongside the
`/references/` content page and parent-spec updates (Phase 5); and a
`--check` mode is wired into CI to catch drift even on edits that bypass
the local pre-commit hook (Phase 6).

The §8 partial is **auto-injected by `single.html`** alongside the existing
`papers-forwardlinks` and `papers/dossier-link` partials — no shortcode
call appears in paper markdown. The cross-series index page uses
`series: references` (deliberately not `papers-index`) because Hugo's `in`
operator does substring matching on strings, and `in "papers-index"
"papers"` returns true — which would silently fire the per-paper §8
partial onto the index page itself. This is documented inline in the spec
and is the single biggest correctness trap in the implementation.

Phase 1 is the only phase writing executable code (the sync script + its
tests). It follows strict TDD: failing test against a real dossier
fixture, then implementation, then green. The parser is extracted (or
imported) from `scripts/validate-dossier.py` so the dossier validator and
the data-file sync share one source of truth for the `## Primary sources`
YAML-block shape. Phases 2–6 are Hugo templating, one-shot migration
scripts, and config-file edits — the "test" there is `hugo server` +
visual verification on three representative papers (Paper 09 for all five
type values, Paper 04 for the `paper` type, Paper 14 for a `postmortem`
source).

Success criteria:

- §8 on every paper page renders title + URL + type chip + quoted passages
  + per-paper relevance, with no paper-author intervention.
- `/docs/papers/references/` lists every cited URL deduped, grouped by
  type, with per-citing-paper relevance preserved.
- The `*Auto-rendered from frontmatter by Hugo taxonomy.*` placeholder no
  longer appears anywhere in `blog/content/`.
- `scripts/sync-dossier-to-data.py --check` exits 0 in CI and 1 with a
  unified diff if any dossier and its data file diverge.
- `references:` frontmatter is gone from every paper bundle and from
  `scripts/scaffold-paper.sh`.

Layered dependencies (1→2→3→4→5→6, no parallelism — phases 4 and 5 both
edit every paper's `index.md` so sequential ordering avoids merge noise).

Post-deploy: per `docs/superpowers/plan-config.yaml` `skip_when:
meta/repo layer`, this plan skips blog posts, README sync, and
runbook sync. Final action is setting the plan status to **Complete**.
