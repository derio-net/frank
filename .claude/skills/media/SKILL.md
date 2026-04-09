---
name: media
description: Guide media capture, optimize assets, and insert shortcodes into blog posts. Can auto-record CLI animations via asciinema.
user-invocable: true
disable-model-invocation: false
arguments:
  - name: post
    description: "Post path relative to blog/content/ (e.g. building/07-observability). If omitted, lists all posts with remaining placeholders."
    required: false
---

# Media Capture and Insertion

Guide the capture, optimization, and insertion of media (screenshots, CLI animations, photos, videos) into Frank blog posts.

## Overview

Blog posts contain `<!-- MEDIA: ... -->` placeholder comments marking where media should be inserted. This skill helps fill those placeholders by:
- Listing remaining media items across all posts or for a specific post
- Guiding manual captures (screenshots, photos) with specific instructions
- Auto-recording CLI animations via asciinema when asked
- Validating and optimizing assets before insertion
- Inserting the shortcode and cleaning up the placeholder

## Workflow

### Step 1: Identify Target Post

If `$ARGUMENTS.post` is provided, read that post. Otherwise, scan all posts under `blog/content/` for `<!-- MEDIA:` comments and present a summary:

```bash
grep -rn "<!-- MEDIA:" blog/content/ --include="*.md"
```

Show the user a checklist of remaining media items grouped by post.

### Step 2: For Each Placeholder

Read the placeholder comment to understand:
- **Type**: `screenshot`, `asciinema`, `photo`, or `youtube`
- **Description**: What to capture
- **Instructions**: How to capture it (URL, command, etc.)

### Step 3: Capture (Mode Depends on Type)

#### Screenshots, Photos, Videos (Guided Mode)

1. Show the user specific capture instructions from the placeholder
2. Remind them: dark mode preferred, ~1200px width, PNG format, crop to relevant area
3. Ask for the file path once captured
4. Proceed to validation

#### CLI Animations (Agent-Executed Mode)

When the user asks you to record a CLI animation:

1. Determine the correct environment:
   - Frank cluster: `source .env`
   - Hop cluster: `source .env_hop`
2. Check that `asciinema` is installed: `which asciinema`
3. Record with scripted commands (use `asciinema rec` with `--command` for non-interactive recording):
   ```bash
   asciinema rec --cols 120 --rows 30 --idle-time-limit 2 \
     --command "<commands separated by semicolons>" \
     <output-path>.cast
   ```
4. Validate the resulting `.cast` file

### Step 4: Validate and Optimize

**For PNG screenshots/photos:**
- Check file size: warn if over 500KB
- If `pngquant` is available, auto-compress: `pngquant --quality=65-80 --strip --force --output <file> <file>`
- If `optipng` is available as fallback: `optipng -o3 <file>`
- If neither tool is available, warn the user about file size
- Verify the file is valid PNG: `file <path>`

**For .cast files:**
- Validate JSON structure: `python3 -c "import json; json.load(open('<file>'))""`
- Check header has `version: 2`
- Warn if recording exceeds 60 seconds

**For all files:**
- Verify filename is kebab-case
- Verify file is in the correct page bundle directory

### Step 5: Insert

1. Read the post's `index.md`
2. Find the `<!-- MEDIA: ... -->` placeholder for this item
3. Remove the `<!-- MEDIA: ... -->` instruction comment
4. Uncomment the shortcode line (remove `<!-- ` prefix and ` -->` suffix)
5. Update the `src` parameter to match the actual filename
6. Ensure `caption` is present for screenshots (reject if missing)

### Step 6: Verify

```bash
cd blog && hugo --minify 2>&1 | tail -5
```

Remind the user to preview with `hugo server --buildDrafts`.

## Standards

- **PNG screenshots**: max 500KB after compression
- **`.cast` files**: valid asciinema v2 JSON, under 60 seconds preferred
- **Filenames**: kebab-case, descriptive (e.g., `grafana-node-metrics.png`)
- **Captions**: required for all screenshots (reject insertion without one)
- **Dark mode**: preferred for screenshots, light acceptable
- **Dimensions**: recordings at 120x30 default unless content needs more

## Reference

- Shortcode docs: `blog/MEDIA-GUIDE.md`
- Shortcode source: `blog/layouts/shortcodes/screenshot.html`, `blog/layouts/shortcodes/asciinema.html`
- CSS: `blog/layouts/partials/extend_head.html` (media styles section)
- Placeholder format: `<!-- MEDIA: type | description | capture instructions -->`
