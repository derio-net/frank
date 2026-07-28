# Blog Quality Gate — enabling the educational-writing gate in CI

**Date:** 2026-07-28
**Layer:** `repo` — meta / blog infrastructure
**Status:** Designed — backlog partially cleared upstream; implementation is this spec's plan.
**Prompted by:** the blog-craft v0.18.0 resync (#729), which shipped
`validate_educational.py` but left it ungated.

## What this is

blog-craft ships an educational-writing gate: a structural check that every
`content_type: posts` post declares a `reader_goal`, names a Diátaxis mode,
carries at least one command/output block, and offers a heading a reader under
pressure can follow. It ships a warnings-first AI-tells lint on top.

frank has the validator vendored at `blog/scripts/validate_educational.py` but
`quality.enabled` is unset, so the shipped CI step is never rendered. The gate
exists and does nothing. This spec covers turning it on.

## Why the backlog is smaller than it first looked

The obvious approach — read the validator's output, fix what it names — would
have been wrong, and expensively so.

Measured across all 83 posts at blog-craft v0.18.0, the gate reported **39
findings across 34 posts**, 34 of them "no actionable section". Inspecting the
posts rather than the report showed most of those posts already had exactly such
a section:

```
MISS   Verifying the Bootstrap      MATCH  Verify
MISS   Recovery Path                MATCH  Recover
MISS   The Smoke Test
MISS   Troubleshooting / Diagnosis
```

`_ACTIONABLE` anchored its verbs as `\bverify\b` / `\brecover\b`, and a word
boundary cannot match an inflected form. The check asking *"is there a heading a
reader can act on?"* was rejecting `## Verifying the Bootstrap`.

Fixed upstream (derio-net/blog-craft#70, released v0.18.1) and resynced here
(#731). The same measurement afterwards:

| | findings | posts |
|---|---|---|
| v0.18.0 | 39 | 34 |
| **v0.18.1** | **15** | **11** |

**23 of the 34 "failures" were never failures.** Acting on the v0.18.0 output
would have meant renaming good prose (`## Recovery Path` → `## Recover`) to
satisfy a regex — degrading the writing the gate exists to protect. No post was
edited to achieve that reduction.

The lesson generalises and belongs in the plan: **when a gate reports a large
backlog, check the gate before working the backlog.**

## The remaining backlog

| Finding | Posts |
|---|---|
| no actionable section | building `00-overview`, `01-introduction`, `03-storage`, `05-gitops`, `06-fun-stuff`, `08-backup`, `10-local-inference`, `13-unified-auth`, `36-metrics-api`; operating `29-metrics-api` |
| too little evidence | building `00-overview`, `01-introduction` |
| missing diagram | building `30-frank-papers`, operating `29-metrics-api` |
| invalid `diataxis: explainer` | building `01-introduction` |
| lint FAIL `'seamless'` | operating `22-cicd-platform` |

## Design constraints

### 1. The gate is trivially gameable — green is not the goal

`_has_actionable_heading` is a regex over H2–H6 text. Any heading containing
`reproduce|runbook|steps|verify|recover|rollback|checklist|walkthrough|
procedure|how to|try it yourself|troubleshoot|diagnos|smoke test` satisfies it,
regardless of what follows.

So a passing run proves nothing about whether a reader can act. **Every section
added by this plan must carry at least one fenced command block with real,
verified commands from this repo** — not invented ones, and not a heading with
the right word in it. Where a post genuinely has nothing operational to offer,
the honest move is `quality_exempt: <reason>` in frontmatter, not a hollow
section.

Phase 6 adds a mechanical floor for this: a tripwire asserting every
actionable-matching heading is followed by a fenced command block before the
next H2. That does not make a section *good*, but it makes an empty one fail.

### 2. Ordering — the flip comes last

The gate runs over **all** posts, not just changed ones. Setting
`quality.enabled: true` before the backlog is cleared turns `main` red on every
subsequent PR, unrelated to its contents. Every phase before the last leaves
`main` green.

### 3. Evidence gathering is per-post and belongs in a subagent

Ten posts each need commands that actually work against this cluster or repo.
Use blog-craft's `post-researcher` agent to gather file:line-cited evidence per
post rather than improvising commands into a draft; use `cold-reader` on the
result. Improvised commands in a published runbook are worse than no runbook.

## Verification

- `uv run --frozen python blog/scripts/validate_educational.py --config .blog-craft.yaml blog/content/docs/*/*/index.md`
  exits 0 over the whole corpus, with the gate enabled.
- `uv run --frozen pytest` stays green (currently 354 passed, 1 xfailed).
- `hugo --buildDrafts` clean.
- Each added section's commands are run and their output pasted, not paraphrased.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-07-28-blog-quality-gate | `derio-net/frank` | `2026-07-28-blog-quality-gate` | — |
