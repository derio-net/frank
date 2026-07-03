# Blog Media Capture Guide

Reference for adding screenshots, CLI animations, photos, and videos to blog posts.

## Shortcode Quick Reference

### Screenshot

```markdown
{{</* screenshot src="grafana-dashboard.png" caption="Grafana node metrics dashboard" */>}}
```

Parameters: `src` (required), `caption`, `alt` (defaults to caption), `width` (e.g. "80%")

### CLI Animation (asciinema)

```markdown
{{</* asciinema src="cilium-status.cast" rows="20" */>}}
```

Parameters: `src` (required), `cols` (120), `rows` (30), `speed` (1), `idle-time-limit` (2), `poster` ("npt:0:3")

### YouTube Video

```markdown
{{</* youtube VIDEO_ID */>}}
```

Hugo built-in shortcode. Just pass the video ID from the URL.

## Capturing Screenshots

1. Set the dashboard/UI to **dark mode** (preferred) or leave as default if dark isn't available
2. Browser window at **~1200px width** for consistency
3. **Crop to the relevant area** -- no browser chrome, no OS taskbar
4. Save as **PNG** in the post's page bundle directory (same dir as `index.md`)
5. Use **kebab-case filenames**: `grafana-node-metrics.png`, not `screenshot-1.png`
6. Compress if over 500KB:
   ```bash
   pngquant --quality=65-80 --strip --output compressed.png original.png
   # or
   optipng -o3 original.png
   ```

## Recording CLI Animations

### Install asciinema

```bash
pip install asciinema
# or
brew install asciinema
```

### Record

```bash
asciinema rec --cols 120 --rows 30 --idle-time-limit 2 output.cast
```

- Keep recordings **short (10-30 seconds)** -- verification-style, not full workflows
- Rehearse the command sequence before recording
- `.cast` files go in the page bundle directory alongside `index.md`

### Trim/Edit

Cast files are JSON -- you can edit them directly or use:
```bash
pip install asciinema-edit
asciinema-edit cut --start 0.5 --end 25.0 input.cast > trimmed.cast
```

## Adding Photos

- Horizontal orientation, well-lit
- Compress to under 1MB (use ImageMagick: `convert photo.jpg -resize 1600x -quality 85 photo.jpg`)
- Save in the page bundle directory
- Use the `screenshot` shortcode (it works for any image, not just screenshots)

## Placeholder Format

Posts contain HTML comment placeholders marking where media should go:

```markdown
<!-- MEDIA: screenshot | Dashboard description | Capture instructions -->
<!-- {{</* screenshot src="suggested-filename.png" caption="Description" */>}} -->
```

To fill a placeholder:
1. Capture the media following the instructions in the comment
2. Save with the suggested filename in the post's page bundle
3. Uncomment the shortcode line (remove `<!-- ` and ` -->`)
4. Delete the `<!-- MEDIA: ... -->` instruction comment
5. Preview with `bash scripts/hugo-serve.sh --buildDrafts` (the wrapper prepends a recent Go to PATH so Hextra's go.mod loads cleanly — see the wrapper header for details)

## Using the `/media` Skill

Run `/media` to get guided assistance with capturing and inserting media. The skill scans for remaining placeholders and walks you through each one.
