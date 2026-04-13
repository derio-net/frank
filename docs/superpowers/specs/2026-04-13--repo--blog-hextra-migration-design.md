# Blog Theme Migration: PaperMod to Hextra

**Layer:** repo
**Date:** 2026-04-13
**Status:** Approved

## Summary

Migrate the Frank blog from the PaperMod Hugo theme to Hextra — a modern, documentation-oriented theme with built-in sidebar navigation, full-text search, and dark mode. The migration addresses three pain points: difficulty navigating between posts in a series (no sidebar), lack of built-in search, and an aging visual aesthetic. Additionally, a client-side read-tracking feature will mark visited posts in the sidebar.

## Motivation

The blog has grown to 48 posts across two structured series (Building Frank, Operating on Frank). PaperMod is a blog theme — it renders posts as chronological card feeds with no persistent sidebar navigation. Readers cannot easily browse between related posts or find content without scrolling through lists. The content is narrative documentation — blog-shaped but documentation-structured (numbered series, ToC, code blocks, diagrams). A documentation-first theme with blog capabilities is a better fit than a blog theme with documentation bolted on.

### Why Hextra

- Sidebar navigation with collapsible sections (solves the "where am I" problem)
- Built-in FlexSearch for full-text client-side search
- Modern Tailwind CSS aesthetic with dark/light mode
- First-class support for both docs and blog content types
- Active maintenance, ~1.7k GitHub stars, Hugo module installation
- Clean Nextra-inspired design without JavaScript framework overhead

## Architecture

### Approach: In-Place Swap via Hugo Module

Replace the PaperMod git submodule with Hextra as a Hugo module in the existing `blog/` directory. No parallel directory, no intermediate state.

- Remove `blog/themes/PaperMod/` git submodule
- Initialize Hugo modules: `hugo mod init` creates `blog/go.mod` + `blog/go.sum`
- Import Hextra via `hugo.toml` module config
- Rewrite `hugo.toml` for Hextra's configuration format
- Restructure content directory to match Hextra's docs layout
- Port custom shortcodes and add custom features

### Content Structure

Current:
```
blog/content/
  building/
    _index.md
    01-introduction/index.md  (+ cover.png, images)
    02-foundation/index.md
    ...26 posts
  operating/
    _index.md
    01-cluster-nodes/index.md
    ...20 posts
```

Target:
```
blog/content/
  _index.md                    # Hextra landing page (hero + feature cards)
  docs/
    building/
      _index.md                # Section index, sidebar root for Building
      01-introduction/
        index.md               # Post content
        cover.png              # Page bundle images preserved
        ...
      02-foundation/
        index.md
        ...
    operating/
      _index.md                # Section index, sidebar root for Operating
      01-cluster-nodes/
        index.md
        ...
```

Both series live under `content/docs/` to get Hextra's sidebar navigation. Page bundles (directory with `index.md` + images) are preserved as-is. Sidebar ordering uses the `weight` frontmatter already present on every post.

The root `content/_index.md` uses Hextra's landing page layout with a hero section ("Frank, the Talos Cluster") and two feature cards linking to Building and Operating.

### Configuration

`hugo.toml` is rewritten from PaperMod format to Hextra format:

| Setting | PaperMod (current) | Hextra (target) |
|---------|-------------------|-----------------|
| Theme source | `theme = "PaperMod"` (submodule) | `module.imports` (Hugo module) |
| Dark mode | `defaultTheme = "auto"` | `theme.default = "system"` |
| Search | JSON output + custom JS | FlexSearch (built-in, enabled by default) |
| ToC | `ShowToc = true` | Built-in, enabled by default on docs pages |
| Code copy | `ShowCodeCopyButtons = true` | Built-in |
| Breadcrumbs | `ShowBreadCrumbs = true` | Built-in on docs pages |
| Syntax style | `markup.highlight.style = "monokai"` | Same (Hugo-level config, theme-independent) |
| Navigation | Top menu (Building, Operating, Tags, RSS) | Navbar + sidebar auto-generated from docs tree |

### Frontmatter Migration

Mechanical transformation across 48 posts:

- **Remove:** `cover` block (image, alt, relative) — handled by layout override
- **Keep:** `title`, `date`, `draft`, `tags`, `summary`, `weight`
- **Optional (post-migration):** Add `sidebar: { label: "..." }` for cleaner sidebar titles

The `summary` field stays for RSS/meta description. The `cover` block is removed because Hextra doesn't use it — instead, a layout override detects `cover.png` in the page bundle via Hugo's `Resources.GetMatch`.

### Custom Features to Port

**Shortcodes (port as-is):**

All three shortcodes are self-contained Hugo templates that don't depend on PaperMod internals. They move to `blog/layouts/shortcodes/` (same location, already outside the theme directory).

| Shortcode | Function | Migration Effort |
|-----------|----------|-----------------|
| `asciinema.html` | Terminal recording player, CDN-loaded, theme auto-detect | Minimal — update theme detection from PaperMod's body class to Hextra's `html[class~="dark"]` attribute |
| `screenshot.html` | Figure with border, box-shadow, click-to-zoom | None — pure HTML/CSS, theme-independent |
| `cluster-roadmap.html` | Interactive SVG roadmap visualization | Minimal — move inline styles to `assets/css/custom.css` |

**Cover images (layout override):**

Override `layouts/docs/single.html` to render `cover.png` from the page bundle as a hero image at the top of each post. Uses Hugo's `Resources.GetMatch "cover.*"` to detect the image. Posts without a cover render normally.

**Series accent bar (CSS-only):**

A subtle colored top-border on docs pages, differentiated by section:
- Building series: one accent color
- Operating series: different accent color

Implemented via `assets/css/custom.css` using CSS selectors on the URL path. Lighter touch than PaperMod's sticky banners — the sidebar already provides series context.

### Read-Tracking Feature

Pure client-side implementation using localStorage:

**Components:**
- `assets/js/read-tracker.js` — loaded via `layouts/partials/custom/head.html`
- Styles in `assets/css/custom.css`
- Reset link in `layouts/partials/custom/footer.html`

**Behavior:**
1. On every docs page load, store the current URL path in `localStorage` key `frank-read-posts` (JSON array)
2. On sidebar render (after DOM ready), query all sidebar anchor elements
3. Compare each `href` against the stored array
4. Append `<span class="read-marker">✓</span>` to visited links
5. Style the checkmark as small, muted-color text via CSS

**Reset:** A "Clear read history" link in the footer clears the localStorage key and reloads the page.

**Scope:** No cookies, no server-side state, no GDPR concerns. localStorage-only, single-browser, personal use.

### CI/CD & Deployment

**Dockerfile (`blog/Dockerfile`):**
- Base image `gohugoio/hugo:v0.157.0` (extended, includes Go for modules)
- Add `hugo mod get` step before `hugo --minify` to fetch Hextra at build time
- Rest of the multi-stage build (Caddy serving) unchanged

**GitHub Actions (`deploy-blog.yml`):**
- Verify the Hugo action includes Go for module downloads
- No workflow structural changes expected

**Netlify (`netlify.toml`):**
- Hugo modules work natively on Netlify when `go.mod` is present
- Verify Hugo version compatibility

**baseURL:** Unchanged — `https://derio-net.github.io/frank/` for Pages, overridden in Dockerfile for self-hosted.

## Files Changed

### Removed
- `blog/themes/PaperMod/` (git submodule)
- `blog/layouts/index.html` (home page series cards — replaced by Hextra landing)
- `blog/layouts/partials/header.html` (PaperMod sticky banner override)
- `blog/layouts/partials/home_info.html` (PaperMod home info override)
- `blog/layouts/partials/extend_head.html` (PaperMod CSS extensions)
- `blog/layouts/_default/list.html` (PaperMod list override)
- `blog/layouts/partials/post_nav_links.html` (PaperMod nav override)

### Added
- `blog/go.mod`, `blog/go.sum` (Hugo module files)
- `blog/content/_index.md` (Hextra landing page)
- `blog/content/docs/` (new parent directory for both series)
- `blog/layouts/docs/single.html` (cover image override)
- `blog/layouts/partials/custom/head.html` (load read-tracker JS)
- `blog/layouts/partials/custom/footer.html` (read history reset link)
- `blog/assets/js/read-tracker.js` (localStorage read tracking)
- `blog/assets/css/custom.css` (accent bars, read markers, shortcode styles)

### Modified
- `blog/hugo.toml` (full rewrite for Hextra config)
- `blog/Dockerfile` (add `hugo mod get` step)
- `blog/netlify.toml` (verify Hugo version)
- `blog/.gitmodules` (remove PaperMod entry)
- `blog/layouts/shortcodes/asciinema.html` (update theme detection class)
- `blog/layouts/shortcodes/screenshot.html` (verify compatibility)
- `blog/layouts/shortcodes/cluster-roadmap.html` (move styles to custom.css)
- 48 post `index.md` files (frontmatter migration — remove cover block)
- 2 section `_index.md` files (move under docs/, update for Hextra)

## Out of Scope

- Cross-device read sync (future enhancement if needed)
- Blog section for announcements (can be added later if wanted)
- Sidebar label cleanup (cosmetic, post-migration polish)
- Media placeholder population (separate ongoing effort per existing plan)
- Content changes to post bodies (only frontmatter changes)
