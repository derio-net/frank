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

> **Never use `weight: 0`.** Hugo treats `weight: 0` as "unset" and sorts the page
> LAST in the Hextra sidebar (the recurring "00 is at the bottom" bug). The **00**
> overview post must use `weight: 1`. Papers use `weight = paper_number + 1` (see
> `repo-papers.md`). A hookify guard (`.claude/hookify.warn-hextra-weight-zero.local.md`)
> warns on `weight: 0` in any `blog/content/**.md` write.

Cover image **entries** go in `blog/prompt_for_images.yaml` (per-entry scene only): `key`, `series`, `torso_variant` (int index into the `torso` layer's `<series>` list), `mood` (preset key), `references` (1–2 paths from `.reference-pool/<series>/subjects/` — pick the one whose clothing+pose matches the scene), `output`, `description`, `prompt` (scene-only). The **shared prose** (`base_character`, `base_atmosphere`, `reference_guidance`, the `torso` variants, and the `mood` presets) lives in `.blog-craft.yaml` under `image.layers` — NOT in `prompt_for_images.yaml`. Do NOT embed the prompt in the frontmatter `alt` field; `alt` should be a short human-readable description. Generate with the `/blog-craft:media` skill, which composes `image.layers` + the entry via `image.composition_order` and calls the provider.

## Blog Commands

```bash
cd blog && hugo server --buildDrafts   # or use preview_start "hugo-dev"
hugo --minify                          # Production build
```
