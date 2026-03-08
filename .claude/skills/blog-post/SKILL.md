---
name: blog-post
description: Create a new Hugo blog post for the Frank cluster documentation series
user-invocable: true
disable-model-invocation: true
arguments:
  - name: number
    description: "Post number (e.g. 07)"
    required: true
  - name: slug
    description: "URL slug (kebab-case, e.g. monitoring)"
    required: true
  - name: title
    description: "Post title (e.g. 'Monitoring with Prometheus and Grafana')"
    required: true
---

# Create Blog Post

Create a new Hugo blog post for the Frank cluster documentation series.

## Arguments

- `$ARGUMENTS.number` — post number (e.g. `07`)
- `$ARGUMENTS.slug` — URL slug (e.g. `monitoring`)
- `$ARGUMENTS.title` — post title

## Steps

### 1. Create Page Bundle

Create directory and index file:

```
blog/content/posts/$ARGUMENTS.number-$ARGUMENTS.slug/index.md
```

### 2. Frontmatter

Use this exact pattern (reference existing posts for consistency):

```yaml
---
title: "$ARGUMENTS.title"
date: <today's date YYYY-MM-DD>
draft: false
tags: [<relevant tags>]
summary: "<one-sentence summary for post cards>"
weight: <$ARGUMENTS.number + 1>
cover:
  image: cover.png
  alt: "<descriptive alt text>"
  relative: true
---
```

**Weight rule**: weight = post number + 1 (post 00 has weight 1, post 07 has weight 8).

### 3. Content Structure

Follow the established voice and structure from existing posts. The blog is written for intermediate practitioners — technical but approachable, with real commands and real outputs.

Typical structure:
- Opening paragraph (motivation, what and why)
- Hardware/requirements context (if relevant)
- Implementation walkthrough with real commands and manifests
- Verification steps (kubectl commands, screenshots)
- Gotchas and lessons learned
- References section at the bottom

### 4. Images

- **Cover image prompt**: Generate a Gemini image prompt for the cover image following the style and examples in `blog/prompts_for_images.md`. The base style is:
  > `Cartoon illustration, vibrant colors, thick outlines, chibi proportions. Dark background with electric blue lightning accents. Tech-horror aesthetic, playful not scary.`
  The subject is always the Frank monster (a Frankenstein monster made of server/computer hardware) in a scene related to the post topic. Present the prompt to the user for approval, then append it to `blog/prompts_for_images.md` under a new heading for this post.
- **Cover image file**: The user will generate the image externally (Gemini) and place it as `cover.png` in the page bundle directory.
- Inline images: co-locate in the page bundle directory (NOT in `/static/images/`)
- Use relative paths: `![Alt text](image.png)`

### 5. Update Overview Post

`blog/content/posts/00-overview/index.md` is a **living document** — update it after every new post:

1. **Series Index** — append the new post as a numbered list item with a Hugo relref link.
2. **Technology → Capability Map** — add a row for any new technology introduced in this post (tool name in bold, capabilities in the second column).
3. **`blog/layouts/shortcodes/cluster-roadmap.html`** — add a new `roadmap-layer` div for the new phase/capability. Use the existing colour classes (`layer-hw`, `layer-net`, etc.) or add a new `layer-*` class with its own `--rm-accent-N` colour variable (add to both light and dark mode sections). Use `layer-upcoming` for phases that are planned but not yet deployed (dashed border, muted opacity).

### 6. Blog Preview

After creating the post, start the Hugo dev server to preview:
- Use `preview_start "hugo-dev"` (configured in `.claude/launch.json`)
- Or: `cd blog && hugo server --buildDrafts`
- Verify the post renders at http://localhost:1313/

### 7. Conventions

- Tags should be lowercase, descriptive (check existing posts for reuse)
- Summary should be one sentence, compelling, under 150 chars
- Don't include the title as H1 in content (PaperMod renders it from frontmatter)
- Code blocks should use language identifiers (```yaml, ```bash, etc.)
- Reference the specific cluster nodes by name when relevant (mini-1, gpu-1, etc.)
- End with a References section linking to relevant docs
