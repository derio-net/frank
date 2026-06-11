# Enrich the agent-images bump PR body with upstream context

## Why

`agent-images-bump.yml` opens an automated PR every time agent-images
advances, but its body is two opaque SHA lines. A reviewer can't tell what
changed or why without diffing two SHAs in another repo. This plan makes the
body self-explanatory: it names the upstream agent-images PR(s) the bump
pulls in (number, title, author, link), a one-line summary of each, and a
compare link — while keeping the existing `vk-remote: <sha>` line.

Full design, operator decisions (Q1–Q4), and edge-case table:
`docs/superpowers/specs/2026-06-11-agent-images-bump-context-design.md`.

## Approach

A single stdlib-only Python script, `scripts/render_bump_body.py`, split into
a pure `render(bump) -> str` (all inclusion/formatting logic, fully
unit-tested) and a thin `collect()` gh-api layer, with `main()` wiring them
and falling back to the legacy two-line body on any failure so enrichment
never blocks a bump. The workflow captures the OLD agent-images SHA before
its sed overwrites the pin, then calls the script for `--body`.

TDD: Phase 1 writes the renderer test-first (it carries the docs-only filter
and all formatting). Phase 2 adds the gh-api collection + non-blocking
fallback, with a live integration check to de-risk the API path pre-merge.
Phase 3 is pure workflow glue. Phase 4 is the back-loaded post-deploy
checklist.

## Key decisions

- **Docs-only filter = the upstream trigger contract.** agent-images
  `build.yaml` only rebuilds (and only dispatches the bump) when a push
  touches files outside `docs/**`. So "PRs that triggered (or would trigger)
  a bump" (operator Q1) = range PRs with at least one non-`docs/` path. The
  filter lives in `render()` and is unit-tested.
- **Public repo, default token.** agent-images is public, so the workflow's
  existing `secrets.GITHUB_TOKEN` reads its compare/commits/pulls cross-repo
  — no new permissions, no App token.
- **Best-effort, never blocking.** Any gh failure (or missing/equal OLD)
  degrades to the current two-line body; the PR still opens.
- **vk-remote untouched** (Q3): stays the `vk-remote: <sha>` line.

## Scope / skips

- "chore gh issue" in the request means the **PR** — the workflow creates no
  issue. This enriches the PR body only.
- Commit message, branch naming, trigger logic: unchanged.
- Post-Deploy checklist: internal CI plumbing — no homepage tile,
  IngressRoute, blog posts, or README change; no manual-operation blocks so
  no /sync-runbook. Only a one-line gotcha is added.
- The live workflow run is the post-merge, operator-driven Test Plan (a
  workflow is only "Deployed" once triggered + observed end-to-end).
