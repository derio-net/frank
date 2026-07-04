# Frank image-optimization adoption — design

**Layer:** repo (blog infra / tooling meta)
**Date:** 2026-07-04
**Status:** draft
**Follows:** blog-craft #14 (image-optimization WebP pipeline mechanism)
**Mechanism spec:** `derio-net/blog-craft:docs/superpowers/implemented/specs/2026-07-04--image-optimization--webp-pipeline-design.md`

## Problem

Frank's live blog serves **90.9 MB of raw PNG** (152 files, 100% PNG; 82 covers =
60.5 MB, banners up to 7 MB each), with no optimization — `hugo --minify` doesn't
touch images. On a slow connection this dominates page load. blog-craft #14
(merged, SHA `5dc31f8`) now ships the opt-in WebP pipeline; this adopts it in
frank so the live blog actually gets faster (~90 MB → ~10–20 MB, WebP wins
77–99% measured).

## What is grounded (measured)

Frank's image templates are the **pre-change blog-craft baseline** — `list.html`,
`screenshot.html`, `site-banner.html` differ from blog-craft@`5dc31f8` **only**
by the opt-image changes. So they can be replaced wholesale with the merged
versions. Frank additionally has its own `docs/single.html` (papers-injection
version blog-craft doesn't ship) where **post covers** — the 60 MB bulk — render;
that one is edited in place.

## Design

1. **Config** — add to `.blog-craft.yaml`:
   ```yaml
   image:
     optimize: { enabled: true, format: webp, quality: 82, max_width: 1600, banner_max_width: 2560 }
   ```
   Bump `blog_craft_version: "a7f2f7f"` → `"5dc31f8"` (blog-craft #14 merge SHA).
2. **Adopt the merged templates** (copy from blog-craft@`5dc31f8`, which differ
   from frank's only by opt-image):
   - `layouts/partials/opt-image.html` (NEW — the optimizer)
   - `layouts/_markup/render-image.html` (NEW — markdown `![]()` hook)
   - `layouts/shortcodes/screenshot.html`
   - `layouts/docs/list.html` (section-landing cover)
   - `layouts/partials/site-banner.html` (assets-first + static fallback)
3. **Edit frank's own `docs/single.html`** — route the post-cover `<img>` through
   `opt-image` (same change as list.html); this reaches the 60 MB of post covers.
4. **hugo.toml** — add `[params.imageOptimize]` (enabled=true, webp, 82, 1600, 2560).
5. **Relocate banners** — `git mv blog/static/images/banner-*.png` →
   `blog/assets/images/` (4 files: landing 7.1M, operating 7.0M, building 1.7M,
   papers 1.1M) so Hugo can process them; the PNG masters move but are otherwise
   untouched.
6. **Verify** — `hugo --minify` clean; WebP derivatives generated; the rendered
   per-page image payload drops sharply; PNG masters otherwise unchanged.

## Tests

`scripts/tests/test_image_optimization_adoption.py`:
- Config declares `image.optimize.enabled: true` + `blog_craft_version: 5dc31f8`.
- `opt-image.html` + `_markup/render-image.html` exist and are byte-identical to
  the blog-craft@`5dc31f8` fixtures (drop-divergence: frank tracks the mechanism).
- A real `hugo --minify` build emits `.webp` (+ `srcset`) for a cover/inline
  image, and the 4 banners live in `assets/images/` (not `static/images/`).

## Test Plan (post-merge, operator-driven)

Frank deploys a live blog (`blog.derio.net/frank` + GitHub Pages). After deploy:
1. Load a representative **post** and a **section page**; in DevTools Network,
   confirm the per-page image transfer dropped sharply (PNG → WebP).
2. Confirm images still render **crisply — no visible quality loss** — in light +
   dark; spot-check a cover, an inline screenshot, and a banner.
3. Confirm the committed PNG **masters are otherwise untouched** (only relocated).

## Implementation Plans

| Plan | Target repo | Status | Notes |
|------|-------------|--------|-------|
| 2026-07-04-image-optimization-adoption | `derio-net/frank` | `2026-07-04-image-optimization-adoption` | — |

## Non-goals

Shrinking the PNG masters (kept as source; Hugo processes at build). AVIF
(WebP-only). Any blog-craft change (mechanism is merged).
