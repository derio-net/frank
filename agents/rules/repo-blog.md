## Blog Post Pattern

Posts use Hugo page bundles with Hextra theme:

```
blog/content/docs/building/NN-slug/   # "Building Frank" posts
blog/content/docs/operating/NN-slug/  # "Operating on Frank" posts
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
---
```

Cover image entries go in `blog/prompt_for_images.yaml` — read the top-of-file comment block for the agent procedure. Required fields per entry: `key`, `series`, `torso_variant` (int index into `torso_variants.<series>`), `mood` (preset key), `references` (1–2 paths from `.reference-pool/<series>/subjects/` — filenames are descriptive, pick the one whose clothing+pose matches the scene intent), `output`, `description`, `prompt` (scene-only). The random pool sampler is disabled by default — explicit `references:` are the canonical path. Insert entries in their correct section (building before `# --- Operating Series Covers`, operating at end of operating section). Do NOT embed the prompt in the frontmatter `alt` field; `alt` should be a short human-readable description. Generate: `source .env_common && uv run --with pyyaml --with google-genai --with pillow scripts/generate-all-images.py --only <key>` (the script auto-picks the reference from `.reference-pool/<series>/reference-<series>.png` based on the entry's `series:` field or key prefix; pass `-r path/to/custom-ref.png` to override)

## Blog Commands

```bash
cd blog && hugo server --buildDrafts   # or use preview_start "hugo-dev"
hugo --minify                          # Production build
```
