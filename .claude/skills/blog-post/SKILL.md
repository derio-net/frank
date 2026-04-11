---
name: blog-post
description: Create a new Hugo blog post for the Frank cluster documentation series
user-invocable: true
disable-model-invocation: false
arguments:
  - name: series
    description: "Series name: 'building' or 'operating'"
    required: true
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

- `$ARGUMENTS.series` — the series name (`building` or `operating`)
- `$ARGUMENTS.number` — post number (e.g. `07`)
- `$ARGUMENTS.slug` — URL slug (e.g. `monitoring`)
- `$ARGUMENTS.title` — post title

## Steps

### 1. Create Page Bundle

Create directory and index file:

```
blog/content/$ARGUMENTS.series/$ARGUMENTS.number-$ARGUMENTS.slug/index.md
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

- **Cover image prompt**: Generate a Gemini image prompt for the cover image following the style and format in `blog/prompt_for_images.yaml`. Read the file's `base_style` and `reference_guidance` fields, plus existing entries for tone/length reference. The character is Frank — a chibi Frankenstein monster made of server hardware (green skin, messy black hair, black eyes, RJ45 neck bolts). Blue glow comes from environment/props/sparks, NOT his eyes. Present the prompt to the user for approval, then append a new YAML entry to `blog/prompt_for_images.yaml` under the `images:` list with fields: `key`, `output`, `description`, `prompt`.
- **Cover image generation**: After the prompt is approved, generate the cover image:
  ```bash
  source .env && .venv/bin/python scripts/generate-all-images.py \
    -r blog/static/images/reference.png \
    --only <key>
  ```
  Use the `key` from the YAML entry you just added (e.g. `post-07` for building, `operating-03` for operating). Show the generated image to the user for review. If they want a regeneration, run the command again.
- Inline images: co-locate in the page bundle directory (NOT in `/static/images/`)
- Use relative paths: `![Alt text](image.png)`

### 5. Update Overview Posts

Each series has its own **00-overview** post — a living document updated after every new post.

**For `building` series posts** — update `blog/content/building/00-overview/index.md`:

1. **Series Index** — append the new post as a numbered list item with a Hugo relref link (under the "Series Index" heading).
2. **Technology → Capability Map** — add a row for any new technology introduced in this post (tool name in bold, capabilities in the second column).
3. **`blog/layouts/shortcodes/cluster-roadmap.html`** — add a new `roadmap-layer` div for the new layer/capability. Use the existing colour classes (`layer-hw`, `layer-net`, etc.) or add a new `layer-*` class with its own `--rm-accent-N` colour variable (add to both light and dark mode sections). Use `layer-upcoming` for layers that are planned but not yet deployed (dashed border, muted opacity). Layer codes are defined in `docs/layers.yaml`.

**For `operating` series posts** — update `blog/content/operating/00-overview/index.md`:

1. **Series Index** — append the new post as a numbered list item with a Hugo relref link.
2. No roadmap or capability map — the operating series is a companion reference, not a build narrative.

**For both**: also update the cross-reference index in `blog/content/building/00-overview/index.md` under "Operating on Frank — Series Index" when adding a new operating post.

### 6. Companion Operating Post

**When `series` is `building`:** After completing the building post, check whether the layer introduces operational concerns (day-to-day commands, health checks, promotion flows, troubleshooting). Most deployed layers do. If so, **prompt the user** to also create the companion operating post:

> "This layer has operational commands (e.g., promoting rollouts, checking status). Should I also create the operating post? Suggested: `/blog-post series:operating number:NN slug:<slug> title:'Operating on <Layer>'`"

Do NOT silently skip this step. The operating series is a companion reference — every building post that deploys a workload should have one.

**When `series` is `operating`:** No companion prompt needed.

### 7. Blog Preview

After creating the post, start the Hugo dev server to preview:
- Use `preview_start "hugo-dev"` (configured in `.claude/launch.json`)
- Or: `cd blog && hugo server --buildDrafts`
- Verify the post renders at http://localhost:1313/

### 8. Conventions

- Tags should be lowercase, descriptive (check existing posts for reuse)
- Summary should be one sentence, compelling, under 150 chars
- Don't include the title as H1 in content (PaperMod renders it from frontmatter)
- Code blocks should use language identifiers (```yaml, ```bash, etc.)
- Reference the specific cluster nodes by name when relevant (mini-1, gpu-1, etc.)
- End with a References section linking to relevant docs
