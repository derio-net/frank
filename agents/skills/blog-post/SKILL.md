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
blog/content/docs/$ARGUMENTS.series/$ARGUMENTS.number-$ARGUMENTS.slug/index.md
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

- **Cover image entry**: Read the top-of-file comment in `blog/prompt_for_images.yaml` — it describes the modular composition (`base_character`, `base_atmosphere`, `reference_guidance`, `torso_variants`, `moods`, `prompt`) and the exact agent procedure. Write a new image entry under `images:` with these required fields:
  - `key` — e.g. `building-07-observability`, `ops-03-gitops` (the prefix routes the series)
  - `series` — `building` / `operating` / `papers`. Drives the default `torso` bucket.
  - `torso_variant` — integer index into `torso_variants.<series>` matching the scene's body/clothing intent
  - `mood` — preset key from `moods:` (e.g. `weighing`, `focused`, `smirking`) matching the scene's emotion
  - `references` — **picked explicitly** from `.reference-pool/<series>/subjects/`. Filenames are descriptive (`frank-white-shirt-black-tie-overalls.png`, `frank-open-torso-3.png`, etc.). List the directory once to see what's available, then pick **1 subject PNG** (occasionally 2) whose clothing AND pose most closely match the intended scene. Optionally add 1 whole-image style anchor from `.reference-pool/<series>/*.png` (root level). Do NOT rely on random pool sampling — the script's `--pool-generic` / `--pool-series` defaults are 0.
  - `output` — path to where the cover lands (e.g. `blog/content/docs/building/07-observability/cover.png`)
  - `description` — one-line caption (used for `--list` and humans skimming)
  - `prompt` — **scene only**: form factor / device / clothing-variant specialization + action + composition + lighting cue. Do NOT repeat traits already in `base_character` / `base_atmosphere` / `torso_variants[X]`. Do NOT keyword-spam.

- **Cover image generation**: After the entry is approved, **always generate a
  batch of options** — Frank's look varies run-to-run, so give the user a choice
  rather than a single take:
  ```bash
  source .env_common && uv run --with pyyaml --with google-genai --with pillow \
    scripts/generate-all-images.py --only <key> --count 8
  ```
  `--count N` produces N variants, each archived under `.regen-archive/<key>/`
  (with a sidecar `.txt` recording the recipe); `cover.png` is left as the last
  one. The script auto-picks the master reference from
  `.reference-pool/<series>/reference-<series>.png` based on the entry's
  `series:` field (or key prefix). Add 1–2 paths to `references:` on the yaml
  entry to stack additional anchors from `.reference-pool/<series>/subjects/`.
  Override the master ref for a one-off run with `-r path.png`.

  **Pick via the contact sheet.** A `--count N>1` batch automatically leaves
  `.regen-archive/<key>/contact-sheet.png` — a labeled grid where each tile
  reads `<index> · <hash>` (1-based tile index + the archive-filename hash
  prefix, so tile "3 · 8e62d3" is `<key>-8e62d3….png`). The pick flow:

  1. **Read the contact sheet** with the Read tool to pre-screen the variants
     yourself.
  2. Present an **AskUserQuestion** with the top 3–4 candidates as options —
     each label carries the tile index + short hash, each description says
     what visually distinguishes that variant. Include the sheet's path in
     the question text so the user can open it directly.
  3. Copy the chosen `.regen-archive/<key>/<key>-<sha>.png` to the entry's
     `output` path as the final `cover.png`.

  Want more options? Re-run with `--count N` (the sheet is recomposed from
  the new batch; archives FIFO-capped at `--archive-cap`, default 30, per
  key). `--no-contact-sheet` skips composition.
- Inline images: co-locate in the page bundle directory (NOT in `/static/images/`)
- Use relative paths: `![Alt text](image.png)`

### 5. Update Overview Posts

Each series has its own **00-overview** post — a living document updated after every new post.

**For `building` series posts** — update `blog/content/docs/building/00-overview/index.md`:

1. **Series Index** — append the new post as a numbered list item with a Hugo relref link (under the "Series Index" heading).
2. **Technology → Capability Map** — add a row for any new technology introduced in this post (tool name in bold, capabilities in the second column).
3. **`blog/layouts/shortcodes/cluster-roadmap.html`** — add a new `roadmap-layer` div for the new layer/capability. Use the existing colour classes (`layer-hw`, `layer-net`, etc.) or add a new `layer-*` class with its own `--rm-accent-N` colour variable (add to both light and dark mode sections). Use `layer-upcoming` for layers that are planned but not yet deployed (dashed border, muted opacity). Layer codes are defined in `docs/layers.yaml`.

**For `operating` series posts** — update `blog/content/docs/operating/00-overview/index.md`:

1. **Series Index** — append the new post as a numbered list item with a Hugo relref link.
2. No roadmap or capability map — the operating series is a companion reference, not a build narrative.

**For both**: also update the cross-reference index in `blog/content/docs/building/00-overview/index.md` under "Operating on Frank — Series Index" when adding a new operating post.

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
- Don't include the title as H1 in content (Hextra renders it from frontmatter)
- Code blocks should use language identifiers (```yaml, ```bash, etc.)
- Reference the specific cluster nodes by name when relevant (mini-1, gpu-1, etc.)
- End with a References section linking to relevant docs
