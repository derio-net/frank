# Spec: blog-craft — portable teaching-blog skill package

**Date:** 2026-05-05
**Layer:** repo (meta — spawns a new sibling repo)
**Status:** Draft
**Brainstorming source:** this conversation, 2026-05-05

## Summary

Extract Frank's blog tooling (the `/blog-post` and `/media` slash commands, plus the implicit blog-bootstrapping knowledge currently encoded only in Frank's history) into a standalone Claude Code plugin repo at `~/Docs/projects/DERIO_NET/blog-craft/`. The plugin ships three skills — `bootstrap-blog`, `blog-post`, `media` — and a Hugo + Hextra blog template that the bootstrap skill renders into any chosen working directory. Each bootstrapped blog gets a per-install `.blog-craft.yaml` capturing the project's central metaphor, series structure, voice, and image-gen settings; the post and media skills consume that config so the same plugin serves any number of blogs with different identities.

## Goals

- One installable artifact (Claude Code plugin) that gives a user three reusable skills for authoring teaching-style blogs.
- Bootstrap a fresh Hugo + Hextra blog with one command, capturing identity decisions in a wizard.
- Author posts and fill media placeholders the same way Frank does today, but against any blog's identity, not Frank's specifically.
- Keep the per-install config explicit, human-readable, and the only source of "what this blog is about."
- Stay Hugo-only, Hextra-only, no deploy pipeline — KISS for v1.

## Non-Goals

- **No multi-SSG support.** Hugo only. Astro/Eleventy/etc. would be a v2 if real demand appears.
- **No theme wizard.** Hextra only. Users can swap themes themselves post-bootstrap.
- **No deploy pipeline.** Bootstrap stops at "`hugo server` shows the home page." Deploy choices (Cloudflare Pages, Netlify, container into a cluster, etc.) are out of scope.
- **No multi-character lore bible.** The metaphor wizard captures one persona + visual constants; that's it.
- **No companion-post auto-prompting.** Frank's bicameral building↔operating prompt drops out because series are now arbitrary-N (see Series Structure below).
- **No automatic media-placeholder insertion in `blog-post`.** Authors add `<!-- MEDIA: ... -->` while drafting; `media` fills them. Same contract as Frank.

## Architecture

### Distribution shape

The repo is **simultaneously a Claude Code plugin and a blog template source**:

- As a plugin: install once via `/plugin install <repo>`, all three skills become available everywhere.
- As a template source: the `bootstrap-blog` skill renders `templates/hugo-hextra/` into the current working directory (or a directory the user names) to produce a fresh blog repo.

A directory is "a blog-craft blog" iff it contains `.blog-craft.yaml` at its root. Both `blog-post` and `media` refuse to run without it (with a hint to invoke `bootstrap-blog`).

### Repo layout

```
~/Docs/projects/DERIO_NET/blog-craft/
├── .claude-plugin/
│   └── plugin.json                          # plugin manifest
├── skills/
│   ├── bootstrap-blog/SKILL.md              # invoke once per new blog
│   ├── blog-post/SKILL.md                   # invoke per post
│   └── media/SKILL.md                       # invoke per draft to fill placeholders
├── templates/
│   └── hugo-hextra/                         # rendered into target dir by bootstrap
│       ├── hugo.toml.tmpl
│       ├── go.mod.tmpl
│       ├── content/
│       │   └── docs/
│       │       └── _index.md.tmpl
│       ├── layouts/
│       │   ├── partials/
│       │   │   └── extend_head.html.tmpl    # media CSS
│       │   └── shortcodes/
│       │       ├── screenshot.html          # generic, identical for every blog
│       │       ├── asciinema.html           # generic
│       │       └── roadmap.html             # only copied if features.roadmap_shortcode = true
│       ├── static/
│       │   └── images/.gitkeep
│       ├── scripts/
│       │   └── generate-images.py.tmpl      # Gemini image-gen runner
│       ├── prompt_for_images.yaml.tmpl      # initial entry: cover for series-overview posts
│       ├── MEDIA-GUIDE.md.tmpl              # always copied
│       ├── .blog-craft.yaml.tmpl            # populated from wizard answers
│       ├── .gitignore.tmpl
│       └── README.md.tmpl
├── README.md
├── LICENSE
└── docs/
    └── ARCHITECTURE.md                      # internal: how the templates render, why these seams
```

### The three skills

| Skill              | Lifecycle           | Inputs                                       | Outputs                                                              |
| ------------------ | ------------------- | -------------------------------------------- | -------------------------------------------------------------------- |
| `bootstrap-blog`   | Once per new blog   | wizard answers, optional reference image     | rendered blog repo in CWD; first reference image; verified `hugo server` |
| `blog-post`        | Per post            | series, number, slug, title; per-post brief  | new page bundle; cover image generated; series overview updated       |
| `media`            | Per draft           | optional `post` arg                          | placeholders filled with rendered shortcodes; assets validated/optimized |

### Discovery contract

`.blog-craft.yaml` at repo root is the single discovery marker. Both `blog-post` and `media` walk up from CWD looking for it (so users can run from `blog/` or repo root). If absent, refuse with: "Not in a blog-craft blog. Run `/bootstrap-blog` first or `cd` to a blog-craft repo."

## Per-install Config: `.blog-craft.yaml`

Captured by the wizard; consumed by all three skills.

```yaml
version: 1

project:
  name: "Frank, the Talos Cluster"
  tagline: "Tutorial series on building and operating an AI-hybrid Kubernetes homelab"
  base_url: "https://derio-net.github.io/frank/"

metaphor:
  persona: |
    Frank is a chibi Frankenstein monster made of server hardware...
  visual_constants:
    - "Green skin, messy black hair, black eyes (not glowing)"
    - "RJ45 neck bolts"
    - "Blue glow comes from environment, NOT eyes"
  reference_image: "static/images/reference.png"
  base_style: |
    Chibi anime style, soft lighting, painterly...
  reference_guidance: |
    Match the proportions, palette, and outline weight of the reference exactly...

series:
  - key: building
    title: "Building Frank"
    description: "How each layer of the cluster came together"
  - key: operating
    title: "Operating on Frank"
    description: "Day-to-day commands, health checks, troubleshooting"

voice: |
  Technical but approachable. Intermediate practitioners. Real commands and outputs.
  Gotchas inline. References at the bottom.

image_gen:
  provider: gemini                            # only supported in v1
  model: gemini-2.5-flash-image-preview       # default; user can override during bootstrap
  api_key_env: GEMINI_API_KEY
  output_dir: static/images
  prompts_file: prompt_for_images.yaml

features:
  roadmap_shortcode: false                    # if true, ships layouts/shortcodes/roadmap.html
  series_overview_posts: true                 # if true, seeds 00-overview/index.md per series
```

### Schema rules

- `version` is a single integer. Bumped only on breaking changes; `bootstrap-blog` writes 1.
- `series` is a non-empty list. Each `key` must be kebab-case and unique within the file.
- `metaphor.reference_image` is optional; if missing, image-gen still works (Gemini just runs without a reference) but quality consistency is the user's problem.
- `voice` is free-text. Default value pre-fills with the "teaching" paragraph above.
- `image_gen.provider` must equal `gemini` in v1 (`bootstrap-blog` rejects anything else).

## Wizard Flow: `bootstrap-blog`

Conversational, step-by-step, ~10 minutes including image generation:

0. **Target directory.** Prompt: "Where should the blog be created? (default: current working directory `<CWD>`)". User can accept or type a path. If the chosen directory already contains `.blog-craft.yaml`, refuse with a hint to remove it first.
1. **Project basics.** Prompt for `name`, `tagline`, `base_url` (one at a time).
2. **Central metaphor.** Walk through (each free-text, with concrete Frank examples shown for inspiration):
   - `persona`
   - `visual_constants` — collect bullets one-by-one until user types `done`
   - **Reference image** — prompt for a *source path* on disk. If supplied, the wizard later copies it to `<target_dir>/static/images/reference.png` and writes that destination into `metaphor.reference_image`. User can type `skip` to omit; `metaphor.reference_image` is then unset.
   - `base_style`
   - `reference_guidance`
3. **Series.** Offer three presets, then loop if the user picks custom:
   - `(1) single` — writes one series `posts` (title `Posts`, description empty). Best for blogs that don't need parallel narrative structures.
   - `(2) tracks` — writes two parallel series that move through the same subject matter at different altitudes. The classic split is **a story track** (chronological narrative — "how we built X, in order") and **a reference track** (atemporal companion — "how to operate X, day-to-day"). Each post in the story track tends to have a sibling in the reference track. The two tracks reinforce each other: the story explains *why* something exists; the reference tells you *how to use it*. Suggested defaults the user can edit: `building` + `operating` (Frank's pattern). Other natural pairings: `tutorials` + `recipes`, `concepts` + `playbooks`, `journey` + `cookbook`.
   - `(3) custom` — loop: prompt for `key` (kebab-case), `title`, `description`, then "Add another? (y/N)". Continue until user says no. Validate keys are unique and kebab-case at end of loop. Use this when you have N>2 dimensions, e.g. one track per product the blog covers.
4. **Voice/tone.** Show the default "teaching" paragraph; user accepts or replaces.
5. **Image-gen settings.** Confirm `provider: gemini`, `model` (default offered), `api_key_env` (default `GEMINI_API_KEY`).
6. **Optional toggles.** Roadmap shortcode (default no), `00-overview` per series (default yes), `git init` (default yes), `gh repo create` (default ask).
7. **Render.** Walk every `*.tmpl` under `templates/hugo-hextra/`, render with wizard answers, write to target directory (strip `.tmpl` on write). Plain files (e.g. `screenshot.html`, `asciinema.html`) copy verbatim. If a reference-image source path was supplied in step 2, copy it to `<target_dir>/static/images/reference.png` now.
8. **Initial image (optional).** If `features.series_overview_posts` is true *and* a reference image was supplied: offer to generate a cover image for the first series-overview post via `scripts/generate-images.py --only overview-<series-key>`. Skip silently if either condition is false.
9. **Verify.** Pick a free TCP port (don't assume 1313). Run `hugo server --buildDrafts --port <port>` in background, wait until `localhost:<port>` returns 200 (timeout 30s), then kill. Print the URL the user can open.

## Skill Behavior: `blog-post`

**Args** (same as Frank's): `series`, `number`, `slug`, `title`.

1. Walk up from CWD to find `.blog-craft.yaml`. Refuse with hint if missing.
2. Validate `series` is in `series[].key`; on mismatch, list valid keys.
3. Create page bundle at `content/docs/<series>/<NN>-<slug>/index.md`. Frontmatter:
   ```yaml
   ---
   title: "<title>"
   date: <today YYYY-MM-DD>
   draft: false
   tags: []
   summary: ""
   weight: <NN+1>
   ---
   ```
4. Prompt user for a one-paragraph **per-post brief** describing the cover image scene.
5. **Compose Gemini prompt** by concatenating: `metaphor.base_style` + `metaphor.persona` + `metaphor.visual_constants` (joined as bullets) + per-post brief + `metaphor.reference_guidance`. Show the full composed prompt; require user approval.
6. Append a new entry to `<image_gen.prompts_file>` under `images:`:
   ```yaml
   - key: <series>-<NN>
     output: <output_dir>/<series>-<NN>-cover.png
     description: <one-line, from title>
     prompt: <composed prompt>
   ```
7. Run `python scripts/generate-images.py --only <series>-<NN>` (uses `image_gen.api_key_env`). Show the result. Offer regen.
8. **Update series overview.** If `features.series_overview_posts` is true, edit `content/docs/<series>/00-overview/index.md`:
   - Append a numbered Hugo `relref` line under "Series Index"
   - Append a row under "Topic / Evolution Map" (post number → title → one-line takeaway)
9. **Smoke check.** Print `hugo server --buildDrafts` URL the user can open to preview the new draft.

The skill **does not** insert media placeholders — that's the author's job while drafting.

## Skill Behavior: `media`

Identical to Frank's, with two changes:

- **Drops Frank-specific environment logic.** No `source .env` vs `source .env_hop` branching for asciinema recording — generic blogs have no equivalent. The skill assumes `asciinema` is on the user's PATH; if not, instruct them to install it.
- **Anchors paths to `.blog-craft.yaml` location.** Frank's skill assumes `blog/content/...`; this version walks up from CWD to find `.blog-craft.yaml`, treats that directory as the blog root.

Otherwise: same args, same workflow, same placeholder format (`<!-- MEDIA: type | description | capture instructions -->`), same validation/optimization (pngquant → optipng fallback → warn), same Hugo build verification.

## Plugin Manifest: `.claude-plugin/plugin.json`

```json
{
  "name": "blog-craft",
  "version": "0.1.0",
  "description": "Portable teaching-blog scaffolding and authoring skills (Hugo + Hextra).",
  "author": "Yiannis Dermitzakis",
  "skills": [
    "skills/bootstrap-blog/SKILL.md",
    "skills/blog-post/SKILL.md",
    "skills/media/SKILL.md"
  ]
}
```

(Exact field shape will be reconciled against current Claude Code plugin spec during implementation.)

## Templates

### Rendering rules

- Files ending in `.tmpl` are rendered with [Go `text/template`](https://pkg.go.dev/text/template) using values from the wizard answers (then `.tmpl` is stripped on write).
- Files without `.tmpl` are copied verbatim (the generic shortcodes, `MEDIA-GUIDE.md`'s static sections, etc.).
- Rendering uses `text/template` not `html/template` — the wizard answers are trusted (operator-supplied), and we want literal output for things like `{{</* shortcode */>}}` examples in `MEDIA-GUIDE.md`.

### Template file inventory

| Template file                                       | Purpose                                                              |
| --------------------------------------------------- | -------------------------------------------------------------------- |
| `hugo.toml.tmpl`                                    | `baseURL`, `title`, `params.description` from wizard                 |
| `go.mod.tmpl`                                       | Module path = `<base_url path>` (Hextra Hugo modules)                |
| `content/docs/_index.md.tmpl`                       | Landing index, lists series                                          |
| `layouts/partials/extend_head.html.tmpl`            | Media CSS injected into `<head>`                                     |
| `layouts/shortcodes/screenshot.html`                | Verbatim from Frank                                                  |
| `layouts/shortcodes/asciinema.html`                 | Verbatim from Frank                                                  |
| `layouts/shortcodes/roadmap.html`                   | Only written if `features.roadmap_shortcode = true`                  |
| `scripts/generate-images.py.tmpl`                   | Reads `prompt_for_images.yaml`, calls Gemini API, writes PNGs        |
| `prompt_for_images.yaml.tmpl`                       | Initial entry per series-overview post; rest grows via `blog-post`   |
| `MEDIA-GUIDE.md.tmpl`                               | Mostly verbatim; substitutes blog name in opening paragraph          |
| `.blog-craft.yaml.tmpl`                             | The full schema above, populated from wizard                         |
| `.gitignore.tmpl`                                   | `public/`, `resources/`, `.hugo_build.lock`, `.env`, etc.            |
| `README.md.tmpl`                                    | Boilerplate with project name, "how to write a post", deploy stub    |

## Repository: bootstrap of blog-craft itself

The blog-craft repo is created out-of-band by the user (and the implementation plan):

```bash
mkdir -p ~/Docs/projects/DERIO_NET/blog-craft
cd ~/Docs/projects/DERIO_NET/blog-craft
git init
gh repo create derio-net/blog-craft --private --source=. --push
```

Then implementation lands the file tree above, commits, pushes, and (manually) installs as a plugin via `/plugin install /Users/derio/Docs/projects/DERIO_NET/blog-craft` for end-to-end testing. Smoke test: `bootstrap-blog` into `/tmp/test-blog-craft/`, then create one post via `blog-post`, then fill one media placeholder via `media`. All three skills must pass.

## Out-of-band Frank impact

The Frank repo's existing `.claude/skills/blog-post/`, `.claude/skills/media/` continue to work as today; nothing in Frank changes as part of this work. **A future migration** (separate plan) would have Frank install blog-craft as a plugin, write `.blog-craft.yaml` for Frank's blog, and remove the in-tree skills. Out of scope here.

## Risks & open questions

- **Plugin manifest format may have evolved.** The exact JSON shape for `plugin.json` (and whether skills auto-discover from `skills/*/SKILL.md` without enumeration) needs verification against the current Claude Code plugin docs at implementation time. Captured as the first implementation task.
- **Gemini model name drift.** `gemini-2.5-flash-image-preview` may be deprecated; bootstrap should query the available models or at least prompt the user to override the default.
- **Reference-image quality is user-dependent.** A good reference image is the single biggest determinant of generated cover quality. The wizard makes that explicit ("seriously — invest 30 minutes here") but cannot enforce quality.
- **`hugo server` smoke test in step 9 of bootstrap can flake** on slower machines or when port 1313 is in use. Implementation should pick a free port, not assume 1313.

## Acceptance criteria

1. Plugin installs cleanly via `/plugin install`.
2. `bootstrap-blog` in an empty directory produces a working Hugo + Hextra site that serves on `hugo server` and renders an index page listing the configured series.
3. `.blog-craft.yaml` is written with all wizard answers; re-running `bootstrap-blog` in a directory that already contains a `.blog-craft.yaml` refuses outright (instructs the user to remove the file manually if they truly want to re-bootstrap).
4. `blog-post` creates a page bundle, generates a cover image (given a valid `GEMINI_API_KEY`), and updates the relevant series overview.
5. `media` finds, optimizes, and inserts at least one screenshot placeholder end-to-end.
6. End-to-end smoke test passes against a freshly bootstrapped `/tmp/test-blog-craft/` directory.

## References

- Frank's existing `/blog-post`: `.claude/skills/blog-post/SKILL.md`
- Frank's existing `/media`: `.claude/skills/media/SKILL.md`
- Frank's `MEDIA-GUIDE.md`: `blog/MEDIA-GUIDE.md`
- Frank's image generation: `scripts/generate-all-images.py` and `blog/prompt_for_images.yaml`
- Hextra theme: <https://imfing.github.io/hextra/>
- Earlier Frank meta-blog specs (sibling `repo` layer):
  - `2026-03-06--repo--blog-series-design.md`
  - `2026-03-13--repo--operating-blog-series-design.md`
