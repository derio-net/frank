# frank adoption — page-derived series-index overviews

**Date:** 2026-07-04
**Status:** draft
**Layer:** repo (blog infra)
**Repo:** derio-net/frank
**Upstream:** derio-net/blog-craft `docs/superpowers/implemented/specs/2026-07-03--series-index--page-derived-series-overviews-design.md` (mechanism, shipped in blog-craft #10)

## Problem

blog-craft #10 shipped a generic `{{< series-index >}}` shortcode that renders a
series' index table from its actual pages at Hugo build time (weight-sorted,
host page self-excluded, `#` from the slug prefix, takeaway from `summary`). It
retires the marker-append *push* model.

frank's blog still uses the push model, and two facts block a drop-in adoption:

1. **frank vendors its own `blog/layouts/`.** The Hextra theme is a Go module;
   blog-craft is not a Hugo dependency. `blog/layouts/shortcodes/` has
   `papers-roadmap.html`, `roadmap.html`, etc. but **no `series-index.html`** —
   the shortcode must be copied in.
2. **frank's building/operating posts carry no `series:` frontmatter.** Only
   papers does (`series: ["papers"]`). Building/operating are grouped purely by
   directory. The shipped shortcode selects by `Params.series`, so on frank it
   would list zero posts.

frank's index today lives inside one combined page, `blog/content/docs/building/00-overview/index.md`:
Roadmap + a hand-curated Technology→Capability Map + a Cluster State table + a
hand-numbered **building** index (33 entries, #604 markers, one planned KubeVirt
line) + a hand-numbered **Operating on Frank** index (28 entries). The push model
drifts and forces operating's index to live inside building's page. Papers already
does the target thing: `blog/content/docs/papers/_index.md` carries a short intro +
`{{< papers-roadmap >}}`, so its roster is self-maintaining — **papers needs no
change**.

## Goals

- frank's **building** and **operating** series each get their own
  auto-updating `{{< series-index >}}` landing page — always in sync, no markers.
- Operating gains its own overview page (today its index is buried in building's).
- Retire the #604 marker-append comments from `building/00-overview`.
- Keep the mechanism frozen: adopt the **shipped** blog-craft shortcode as-is
  (operator decision — single frank PR, no blog-craft change), by giving frank's
  posts the `series:` frontmatter the shortcode selects on.

## Non-goals

- **The blog-craft shortcode is unchanged.** Adoption adds `series:` frontmatter
  to frank's posts and copies the shipped `series-index.html` verbatim; it does
  not modify the mechanism.
- **Papers is unchanged.** `papers/_index.md` already renders `{{< papers-roadmap >}}`.
- **The Technology → Capability Map and Cluster State tables stay hand-curated**
  on `building/00-overview` — they are cluster inventories, not per-series indexes,
  and do not map 1:1 to posts.
- **The KubeVirt "(planned)" line is not preserved inline.** Page-derived indexes
  list only real pages; planned layers are already shown by `{{< roadmap >}}`
  (from `blog/data/roadmap.yaml`) higher on the same page. No information is lost.
- No prev/next nav, no URL changes to existing posts, no cover-image regeneration.

## Design

### 1. Add `series:` frontmatter to building/operating posts

frank has 33 building post bundles (`blog/content/docs/building/NN-slug/`,
excluding `00-overview`) and 28 operating post bundles. Add a list-form `series:`
to each post's frontmatter:

- Every `blog/content/docs/building/*/index.md` → `series: ["building"]`
- Every `blog/content/docs/operating/*/index.md` → `series: ["operating"]`
- `building/00-overview/index.md` and the new `operating/00-overview/index.md`
  also get their series (so the shortcode infers it and self-excludes).

**List form only.** Hextra's opengraph partial ranges over `series`, so a scalar
`series:` is a hard build error. `building/30-frank-papers/index.md` currently has
no frontmatter `series:` → it gets `series: ["building"]` like every other building
post (it is a building post that happens to be *about* the papers series).

**Frontmatter-scoped insertion — mandatory.** The two `*-frank-papers` posts
(`building/30-frank-papers`, `operating/25-frank-papers`) contain a literal
`series: papers` line *in their body* (example frontmatter they quote while
documenting the papers series — at line 229 and line 173 respectively). The
migration MUST parse the leading `---`-delimited frontmatter block and edit only
that; a whole-file `grep '^series:'` would false-match the body example and both
mis-detect "already has series" and risk editing prose. Insertion is idempotent
(skip a file whose *frontmatter* already declares the right `series:`). These
body-example lines are left untouched.

### 2. Vendor the shortcode

Copy blog-craft's shipped `templates/hugo-hextra/layouts/shortcodes/series-index.html`
(current `origin/main`) verbatim to `blog/layouts/shortcodes/series-index.html`.
Frank's Hugo build then resolves `{{< series-index >}}`.

### 3. Rewrite `building/00-overview`

- Add `series: ["building"]` to the frontmatter.
- Keep: intro prose, `## Roadmap` + `{{< roadmap >}}`, `## Technology → Capability Map`,
  `## Cluster State`.
- Replace the hand-numbered `## Series Index` list (and the KubeVirt planned line)
  with `## Series Index` + `{{< series-index >}}`.
- **Delete** the entire `## Operating on Frank — Series Index` section (moves to
  the operating overview, §4).
- **Drop both #604 markers**: `<!-- /blog-post auto-appends entries here as posts are created. -->`
  and `<!-- /blog-post auto-appends rows here. -->`.

### 4. Create `operating/00-overview`

New bundle `blog/content/docs/operating/00-overview/index.md`:

```yaml
---
title: "Operating on Frank: Overview"
date: 2026-07-04
draft: false
series: ["operating"]
tags: ["overview"]
summary: "Index of the Operating on Frank series — day-to-day commands, health checks, and debugging guides for every component on the cluster."
weight: 1
---
```

Body: a short "About this series" intro (reuse the existing one-liner —
"Companion series with day-to-day commands, health checks, and debugging
guides.") under `## Series Index`, then `{{< series-index >}}`.

**No cover image.** `building/00-overview` has a `cover.png`, but generating a
matching one for the operating overview needs the interactive `/blog-craft:media`
flow + `GEMINI_API_KEY` — out of scope for an autonomous, agentic-pure run, and
not required for the index to work. Operating ships cover-less; a card image can
be added later via `/blog-craft:media` if the operator wants thumbnail parity.
Flagged, not silently dropped.

### 5. Re-touch `agents/rules/repo-workflows.md`

- **Step 5 (Blog):** the overview auto-lists a new post via `{{< series-index >}}`
  — remove any "append to Series Index / update the overview index" wording; keep
  "add the roadmap layer to `blog/data/roadmap.yaml`". Note operating now has its
  own overview.
- **Fix/Extension step 4:** drop the marker-append / manual-overview reference.

(These two spots were last touched by #604, which introduced the markers this
change retires.)

## Testing

TDD, red → green, at a real `hugo` build. New test at frank's test location
`scripts/tests/test_series_index_adoption.py` (alongside the other
`scripts/tests/test_*.py`; run with `pytest`):

1. **Red first:** before the change, assert `{{< series-index >}}` on
   `building/00-overview` renders a table listing all 33 building posts — fails
   (shortcode absent / no series frontmatter).
2. **Parity (the core assertion):** after the change, build the blog and assert
   the rendered `building/00-overview` series-index table lists **exactly** the 33
   building post bundles, weight-sorted, each linked, and that this set **matches
   the retired hand-list** (same 33 `NN-slug` targets). Same for `operating/00-overview`
   (28 rows). This is the in-repo half of the "full parity diff".
3. **Self-exclusion:** the overview page itself is not a row.
4. **No stale markers:** `building/00-overview` no longer contains
   `auto-appends` comments, and no longer contains the `Operating on Frank — Series Index`
   section.

Plus a plain `hugo --minify` clean build over the whole site (drafts off).

## Test Plan

Post-merge, operator-driven (deploys to `blog.derio.net/frank` + `derio-net.github.io/frank`):

1. Wait for the blog deploy workflow to publish the merge.
2. **Full parity diff — building:** open `blog.derio.net/frank/docs/building/`
   overview; confirm the auto-generated index lists all 33 posts, and every row's
   title/link/order matches the retired hand-list (captured in this spec's §Design
   and the parity test's ground truth). Click-check a sample of links resolve 200.
3. **Full parity diff — operating:** same for the new operating overview (28 rows).
4. **Visual:** eyeball both overviews for no regression vs the old rendering
   (table renders, Roadmap + Capability Map + Cluster State intact on building).
5. Confirm papers overview is unchanged.

## Rollout

Single frank PR. No user-facing content change beyond the index becoming
self-maintaining and operating gaining its own landing page. No blog-craft change
(shortcode adopted as shipped).

## Implementation Plans

| Plan | Repo | Scope |
|------|------|-------|
| _TBD_ | derio-net/frank | frontmatter migration + shortcode vendor + overview split + #604 marker drop + workflow re-touch + parity test |
| 2026-07-04-frank-series-index-adoption | `derio-net/frank` | `2026-07-04-frank-series-index-adoption` | — |
