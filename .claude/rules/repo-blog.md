## Blog Post Pattern

Posts use Hugo page bundles with PaperMod theme:

```
blog/content/building/NN-slug/   # "Building Frank" posts
blog/content/operating/NN-slug/  # "Operating on Frank" posts
  index.md       # Post content
  cover.png      # Cover image
  *.png          # Inline images
```

Frontmatter:
```yaml
---
title: "Post Title"
date: 2026-MM-DD
draft: false
tags: ["tag1", "tag2"]
summary: "One-sentence summary for cards"
weight: <NN>    # Sort order matches post number
cover:
  image: cover.png
  alt: "Descriptive alt text"
  relative: true
---
```

Cover image generation prompts go in `blog/prompt_for_images.yaml` — one entry per post, following the existing YAML format (key, output, description, prompt, optional post_process). Insert prompts in their correct section (building prompts before `# --- Operating Series Covers`, operating prompts at end of operating section). Do NOT embed the prompt in the frontmatter `alt` field; `alt` should be a short human-readable description. Generate images with: `.venv/bin/python scripts/generate-all-images.py -r blog/static/images/reference.png --only <key>` (run `uv sync` first if the venv is stale)

## Blog Commands

```bash
cd blog && hugo server --buildDrafts   # or use preview_start "hugo-dev"
hugo --minify                          # Production build
```
