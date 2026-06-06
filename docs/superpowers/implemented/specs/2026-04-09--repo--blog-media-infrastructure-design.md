# Blog Media Infrastructure Design

**Layer:** `repo`
**Date:** 2026-04-09

## Problem

The Frank blog has 41 posts across building/operating series but is text-heavy -- only 5 inline images exist across 4 posts. All other posts are prose + code blocks. The blog needs visual enrichment: CLI session animations, screenshots of dashboards, hardware photos, and video embeds to improve credibility, comprehension, and engagement.

## Goals (Prioritized)

1. **Proof & credibility** -- screenshots and CLI recordings showing things actually running
2. **Comprehension aids** -- visuals at section breaks that make concepts click
3. **Engagement & polish** -- hardware photos, video, visual variety

**Target density:** 4-6 media items per post, placed at major section breaks.

## Design

### Hugo Shortcodes

**`asciinema` shortcode** -- `blog/layouts/shortcodes/asciinema.html`

Embeds an asciinema-player for `.cast` files stored in page bundles.

Parameters:
- `src` (required) -- `.cast` filename in the page bundle
- `cols` (default: 120) -- terminal columns
- `rows` (default: 30) -- terminal rows
- `speed` (default: 1) -- playback speed multiplier
- `idle-time-limit` (default: 2) -- max seconds of idle time
- `poster` (default: "npt:0:3") -- preview frame

Implementation:
- Resolves `.cast` file via `.Page.Resources.GetMatch`
- Renders `<div>` with unique ID (using `.Ordinal`)
- Inits player via `AsciinemaPlayer.create()` in inline `<script>`
- Auto-detects PaperMod dark/light theme from `document.documentElement.dataset.theme`: dark → `asciinema` theme (dark background), light → `solarized-light` theme

Usage:
```markdown
{{</* asciinema src="cilium-status.cast" rows="20" */>}}
```

**`screenshot` shortcode** -- `blog/layouts/shortcodes/screenshot.html`

Enhanced figure for screenshots with border, caption, and click-to-zoom.

Parameters:
- `src` (required) -- image filename in the page bundle
- `caption` (optional) -- text below image
- `alt` (optional, defaults to caption) -- alt text
- `width` (optional) -- CSS width override (e.g., "80%")

Implementation:
- Resolves image via `.Page.Resources.GetMatch`
- Renders `<figure class="screenshot">` containing `<a href="full-size" target="_blank"><img></a>`
- Optional `<figcaption>` when caption provided

Usage:
```markdown
{{</* screenshot src="grafana-dashboard.png" caption="Node metrics in Grafana" */>}}
```

**YouTube** -- Hugo built-in `{{</* youtube VIDEO_ID */>}}`, no custom shortcode needed.

### Conditional Asset Loading

In `blog/layouts/partials/extend_head.html`, load asciinema-player CSS/JS only on pages that use the shortcode:

```html
{{- if .HasShortcode "asciinema" }}
<link rel="stylesheet" href="https://unpkg.com/asciinema-player@3.9.0/dist/bundle/asciinema-player.css" />
<script src="https://unpkg.com/asciinema-player@3.9.0/dist/bundle/asciinema-player.min.js"></script>
{{- end }}
```

### CSS Styling

All media CSS appended to `blog/layouts/partials/extend_head.html` after existing banner/card styles.

**Screenshot figure:**
- Border with `border-radius: var(--radius)` (PaperMod variable)
- Subtle `box-shadow` for depth
- Centered, `max-width: 100%`, optional width override
- `cursor: zoom-in` on hover
- Figcaption: centered, `color: var(--secondary)`, smaller italic text
- Dark mode: lighter border via `body.dark` selector, adjusted shadow

**Asciinema container:**
- Matching border-radius and box-shadow
- Margin consistent with code blocks
- Max-width capped to content width

**Existing inline images:**
- `.post-content img` gets subtle border + border-radius so existing images in posts 01/02/03/05 look polished without markdown changes

**YouTube responsive wrapper:**
- 16:9 aspect ratio via `padding-bottom: 56.25%`
- Full content width

All styles use PaperMod CSS variables (`--border`, `--radius`, `--secondary`, `--entry`) for automatic theme adaptation.

### Media Placeholders

HTML comment blocks inserted into posts marking what to capture:

```markdown
<!-- MEDIA: screenshot | Grafana node metrics dashboard | Navigate to 192.168.55.203, Node Overview, dark mode -->
<!-- {{</* screenshot src="grafana-node-metrics.png" caption="Grafana node metrics dashboard" */>}} -->
```

When media is captured, the placeholder comment is removed and the shortcode is uncommented.

### Post Coverage

**High-priority (4-6 media each, ~34 total):**

| Post | Screenshots | CLI Animations | Count |
|------|------------|----------------|-------|
| 02-foundation | Omni cluster overview | `cilium status`, `talosctl health` | 4 |
| 07-observability | Grafana dashboard, VMUI, log explorer | `kubectl top nodes` | 4 |
| 11-agentic-control-plane | Sympozium dashboard, agent detail | AgentRun lifecycle watch | 4 |
| 13-unified-auth | Authentik admin, login page, provider config | -- | 3 |
| 16-media-generation | GPU Switcher UI, ComfyUI editor | GPU switch toggle | 4 |
| 17-public-edge | Headplane dashboard, blog on Hop | `talosctl health` on Hop | 4 |
| 20-workflow-automation | n8n editor, execution history | -- | 3 |
| 22-health-monitoring | Feature Health dashboard, Telegram alert | heartbeat check | 4 |
| 24-in-cluster-ingress | Homepage dashboard, Traefik dashboard | cert-manager status | 4 |

**Medium-priority (1-3 media each, ~13 total):**

| Post | Media |
|------|-------|
| 01-introduction | Hardware setup photo |
| 04-gpu-compute | `nvidia-smi` CLI animation |
| 05-gitops | `argocd app sync` CLI animation |
| 06-fun-stuff | LED hardware photo |
| 09-secrets | Infisical dashboard screenshot |
| 10-local-inference | LiteLLM streaming CLI animation |
| 14-multi-tenancy | vCluster create CLI animation |
| 15-paperclip | Paperclip UI screenshot |
| 19-progressive-delivery | Rollouts dashboard screenshot |
| 21-secure-agent-pod | SSH session CLI animation |

**Operating posts (1-2 media each, ~6 total):**
- operating/05-observability, 10-media-generation, 15-health-monitoring, 17-ingress

**Grand total: ~53 media placeholders across ~23 posts.**

### `/media` Skill

A standalone skill (`.claude/skills/media.md`) for capturing, optimizing, and inserting media into blog posts.

**Two modes:**

**Guided mode (screenshots, photos, videos):**
1. Select post to enrich (or detect from context)
2. Scan `<!-- MEDIA: ... -->` placeholders, present as checklist
3. For each placeholder, show capture instructions (target service URL, dark mode reminder, framing guidance)
4. User provides file path to captured asset
5. Validate & optimize (see standards below)
6. Insert: uncomment shortcode, update `src`, remove placeholder comment
7. Remind user to check with `hugo server`

**Agent-executed mode (CLI animations):**
The agent records asciinema sessions itself when asked:
1. Source the correct env file (`.env` for Frank, `.env_hop` for Hop)
2. Run `asciinema rec` with scripted commands (non-interactive)
3. Consistent terminal dimensions (120x30 default), clean output, no typos
4. Validate resulting `.cast` file
5. Trim trailing blank frames if needed
6. Place in page bundle and insert shortcode

**Post-processing (agent-executed):**
- PNG compression via `pngquant` / `optipng` (if available)
- Image resize via `convert` (ImageMagick) if oversized
- Crop via `convert` with specified dimensions
- `.cast` validation (valid JSON, asciinema v2 header) and trimming

**Standards enforced:**
- PNG screenshots: max 500KB after compression (auto-compress, warn if tool unavailable)
- `.cast` files: valid asciinema v2 JSON
- All screenshots must have `caption` param (reject if missing)
- Filenames: kebab-case, descriptive (e.g., `grafana-node-metrics.png`, not `screenshot-1.png`)
- Dark mode preferred for screenshots, light acceptable

**Testing:** After creating the skill, test on one post (e.g., 24-in-cluster-ingress) with a sample screenshot and a small `.cast` file to verify the full pipeline.

### Media Capture Guide

`blog/MEDIA-GUIDE.md` -- reference document for manual captures:

- **asciinema**: install, record, trim, save to page bundle
- **Screenshots**: dark mode preferred, ~1200px width, PNG, crop to relevant area, compress if >500KB
- **Photos**: horizontal, well-lit, <1MB
- **YouTube**: upload, grab ID, use built-in shortcode
- **Quick reference**: copy-paste shortcode examples

## Files

**New:**
- `blog/layouts/shortcodes/asciinema.html`
- `blog/layouts/shortcodes/screenshot.html`
- `blog/MEDIA-GUIDE.md`
- `.claude/skills/media.md`

**Modified:**
- `blog/layouts/partials/extend_head.html` -- conditional asset loading + media CSS
- ~23 blog posts -- media placeholder comments inserted

## Verification

- `cd blog && hugo server --buildDrafts` -- shortcodes render, CSS looks correct in both themes
- Test asciinema player loads and plays with a small `.cast` file
- Test screenshot shortcode renders with border, caption, click-to-zoom
- YouTube embed is responsive
- No regressions on existing pages (covers, banners, cluster-roadmap)
- HTML comment placeholders don't render visibly
- `/media` skill successfully guides through one placeholder and inserts media

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| Blog Media Infrastructure Implementation Plan |  | `docs/superpowers/archived-plans/2026-04-09--repo--blog-media-infrastructure/` | — |
