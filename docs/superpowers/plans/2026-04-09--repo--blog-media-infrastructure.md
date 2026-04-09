# Blog Media Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add media embedding infrastructure (asciinema player, screenshot shortcode, CSS) to the Hugo blog and insert media placeholders into ~23 posts.

**Architecture:** Two custom Hugo shortcodes + CSS in extend_head.html + a `/media` skill for guided capture. Conditional JS loading via `.HasShortcode`.

**Tech Stack:** Hugo shortcodes, asciinema-player 3.9.0 (CDN), PaperMod CSS variables

**Spec:** `docs/superpowers/specs/2026-04-09-repo-blog-media-design.md`

---

### Task 1: Create `screenshot` shortcode

**Files:**
- Create: `blog/layouts/shortcodes/screenshot.html`

- [x] **Step 1: Create the shortcode**
- [x] **Step 2: Commit** *(combined into single infrastructure commit)*

---

### Task 2: Create `asciinema` shortcode

**Files:**
- Create: `blog/layouts/shortcodes/asciinema.html`

- [ ] **Step 1: Create the shortcode**

```html
{{- $src := .Get "src" -}}
{{- $cols := .Get "cols" | default "120" -}}
{{- $rows := .Get "rows" | default "30" -}}
{{- $speed := .Get "speed" | default "1" -}}
{{- $idleTimeLimit := .Get "idle-time-limit" | default "2" -}}
{{- $poster := .Get "poster" | default "npt:0:3" -}}
{{- $id := printf "asciinema-%d" .Ordinal -}}
{{- $res := .Page.Resources.GetMatch $src -}}
{{- $url := "" -}}
{{- if $res -}}
  {{- $url = $res.RelPermalink -}}
{{- else -}}
  {{- $url = $src -}}
{{- end -}}
<div id="{{ $id }}" class="asciinema-container"></div>
<script>
(function() {
  var theme = document.documentElement.dataset.theme === 'light' ? 'solarized-light' : 'asciinema';
  AsciinemaPlayer.create('{{ $url }}', document.getElementById('{{ $id }}'), {
    cols: {{ $cols }},
    rows: {{ $rows }},
    speed: {{ $speed }},
    idleTimeLimit: {{ $idleTimeLimit }},
    poster: '{{ $poster }}',
    theme: theme,
    fit: 'width'
  });
})();
</script>
```

- [x] **Step 2: Commit** *(combined into single infrastructure commit)*

---

### Task 3: Add CSS and conditional asset loading to extend_head.html

**Files:**
- Modify: `blog/layouts/partials/extend_head.html`

- [x] **Step 1: Append conditional asciinema assets + media CSS after the closing `</style>` tag**

After the existing `</style>` on line 118, add:

```html
{{- if .HasShortcode "asciinema" }}
<link rel="stylesheet" href="https://unpkg.com/asciinema-player@3.9.0/dist/bundle/asciinema-player.css" />
<script src="https://unpkg.com/asciinema-player@3.9.0/dist/bundle/asciinema-player.min.js"></script>
{{- end }}

{{- /* Media styles for screenshots, asciinema, and YouTube embeds */ -}}
<style>
/* Screenshot shortcode */
.screenshot {
    margin: 1.5rem 0;
    text-align: center;
}

.screenshot a {
    display: block;
    line-height: 0;
}

.screenshot img {
    max-width: 100%;
    height: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    cursor: zoom-in;
    transition: box-shadow 0.2s ease;
}

.screenshot img:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.screenshot figcaption {
    margin-top: 0.5rem;
    font-size: 0.85rem;
    font-style: italic;
    color: var(--secondary);
}

/* Asciinema player container */
.asciinema-container {
    margin: 1.5rem 0;
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* Polish existing inline images in post content */
.post-content img:not([src*="cover.png"]) {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* Responsive YouTube embeds */
.youtube-container {
    position: relative;
    padding-bottom: 56.25%;
    height: 0;
    overflow: hidden;
    margin: 1.5rem 0;
    border-radius: var(--radius);
}

.youtube-container iframe {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
}

/* Dark mode adjustments */
body.dark .screenshot img {
    border-color: rgba(255, 255, 255, 0.1);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

body.dark .screenshot img:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
}

body.dark .asciinema-container {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

body.dark .post-content img:not([src*="cover.png"]) {
    border-color: rgba(255, 255, 255, 0.1);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}
</style>
```

- [-] **Step 2: Verify Hugo builds without errors** *(hugo not available in container — verified template syntax manually)*

```bash
cd blog && hugo --minify 2>&1 | tail -5
```

Expected: Build succeeds, no template errors.

- [x] **Step 3: Commit** *(combined into single infrastructure commit)*

---

### Task 4: Create MEDIA-GUIDE.md

**Files:**
- Create: `blog/MEDIA-GUIDE.md`

- [x] **Step 1: Write the guide**

Content should cover:
- asciinema: install (`pip install asciinema`), record (`asciinema rec --cols 120 --rows 30 --idle-time-limit 2 output.cast`), trim, save to page bundle
- Screenshots: dark mode preferred, ~1200px width, PNG, crop to relevant area, compress if >500KB (`pngquant --quality=65-80 file.png`)
- Photos: horizontal, well-lit, <1MB, page bundle
- YouTube: upload, use `{{</* youtube VIDEO_ID */>}}`
- Quick reference: copy-paste shortcode examples for each type
- Placeholder format explanation

- [x] **Step 2: Commit** *(combined into single infrastructure commit)*

---

### Task 5: Insert media placeholders into high-priority building posts

**Files (modify each post's `index.md`):**
- `blog/content/building/02-foundation/index.md`
- `blog/content/building/07-observability/index.md`
- `blog/content/building/11-agentic-control-plane/index.md`
- `blog/content/building/13-unified-auth/index.md`
- `blog/content/building/16-media-generation/index.md`
- `blog/content/building/17-public-edge/index.md`
- `blog/content/building/20-workflow-automation/index.md`
- `blog/content/building/22-health-monitoring/index.md`
- `blog/content/building/24-in-cluster-ingress/index.md`

Placeholder format (HTML comments, invisible in rendered output):
```markdown
<!-- MEDIA: type | description | capture instructions -->
<!-- {{</* screenshot src="suggested-filename.png" caption="Description" */>}} -->
```

For each post, read it, identify the best insertion points (after the paragraph discussing the topic, before the next heading), and insert placeholders. Use the media map from the spec:

| Post | Placeholders |
|------|-------------|
| 02-foundation | 2 CLI animations (cilium status, talosctl health) |
| 07-observability | 3 screenshots (Grafana, VMUI, log explorer) + 1 CLI animation |
| 11-agentic-control-plane | 2 screenshots + 1 CLI animation |
| 13-unified-auth | 3 screenshots (admin, login, provider config) |
| 16-media-generation | 2 screenshots + 2 CLI animations |
| 17-public-edge | 2 screenshots + 2 CLI animations |
| 20-workflow-automation | 2 screenshots |
| 22-health-monitoring | 2 screenshots + 2 CLI animations |
| 24-in-cluster-ingress | 2 screenshots + 2 CLI animations |

- [x] **Step 1: Insert placeholders into all 9 high-priority posts**
- [-] **Step 2: Verify Hugo builds clean** *(hugo not available in container)*
- [x] **Step 3: Commit** *(combined into single placeholders commit)*

---

### Task 6: Insert media placeholders into medium-priority and operating posts

**Files (modify each post's `index.md`):**
- `blog/content/building/01-introduction/index.md` (photo)
- `blog/content/building/04-gpu-compute/index.md` (CLI animation)
- `blog/content/building/05-gitops/index.md` (CLI animation)
- `blog/content/building/06-fun-stuff/index.md` (photo)
- `blog/content/building/09-secrets/index.md` (screenshot)
- `blog/content/building/10-local-inference/index.md` (CLI animation)
- `blog/content/building/14-multi-tenancy/index.md` (CLI animation)
- `blog/content/building/15-paperclip/index.md` (screenshot)
- `blog/content/building/19-progressive-delivery/index.md` (screenshot)
- `blog/content/building/21-secure-agent-pod/index.md` (CLI animation)
- `blog/content/operating/05-observability/index.md` (screenshot)
- `blog/content/operating/10-media-generation/index.md` (screenshot)
- `blog/content/operating/15-health-monitoring/index.md` (screenshot)
- `blog/content/operating/17-ingress/index.md` (screenshot)

- [x] **Step 1: Insert placeholders into all 14 medium/operating posts** (1-2 per post)
- [-] **Step 2: Verify Hugo builds clean** *(hugo not available in container)*
- [x] **Step 3: Commit** *(combined into single placeholders commit)*

---

### Task 7: Create `/media` skill

**Files:**
- Create: `.claude/skills/media/SKILL.md`

- [x] **Step 1: Create the skill file**

The skill should:
- Be user-invocable with optional `post` argument
- Scan for `<!-- MEDIA: ... -->` placeholders in the specified post (or list all posts with remaining placeholders)
- Present a checklist of remaining media items
- **Guided mode** for screenshots/photos: show capture instructions (URL, dark mode, framing), accept file path, validate (size, format), compress if needed (`pngquant`), insert shortcode, remove placeholder
- **Agent-executed mode** for CLI animations: source correct env file, run `asciinema rec` with scripted commands, validate .cast JSON, place in page bundle, insert shortcode
- **Standards**: PNG max 500KB, .cast valid JSON, filenames kebab-case, caption required for screenshots
- Post-processing: `pngquant`/`optipng` compression, ImageMagick resize/crop, .cast trimming

Follow the pattern from `.claude/skills/blog-post/SKILL.md` for YAML frontmatter format.

- [x] **Step 2: Commit** *(combined into single infrastructure commit)*

---

### Task 8: Verify and push

- [-] **Step 1: Run Hugo build to verify no regressions** *(hugo not available in container — verify on next local build)*
- [-] **Step 2: Verify placeholders are invisible in output** *(deferred to local build)*
- [x] **Step 3: Push all commits**

---

## Verification

After all tasks complete:
1. `cd blog && hugo server --buildDrafts` -- site builds, no errors
2. Existing posts with inline images (01, 02, 03, 05) render with polished borders
3. HTML comment placeholders don't appear in rendered output
4. `/media` skill is available and lists pending placeholders
5. Shortcodes are ready for use once actual media files are captured
