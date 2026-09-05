# Frank

Building, operating, and deciding: an AI-hybrid Kubernetes homelab with Talos Linux, Cilium, Longhorn, ArgoCD, and GPU compute

This blog was scaffolded with [blog-craft](https://github.com/derio-net/blog-craft) and uses [Hugo](https://gohugo.io/) + [Hextra](https://imfing.github.io/hextra/).

## Local development

```bash
hugo mod get -u                                 # first time only
bash scripts/hugo-serve.sh --buildDrafts        # serves at http://localhost:1313/frank/
```

The `scripts/hugo-serve.sh` wrapper is a small PATH shim around `hugo server`. **Use it instead of invoking `hugo server` directly.** Hextra is a Hugo Module and its `go.mod` declares `go 1.24.2`; older Go binaries (notably macOS's `/usr/local/go` pinned at 1.19) reject that directive with `invalid go version '1.24.2': must match format 1.23`. The wrapper iterates common modern-Go locations (Intel brew, Apple Silicon brew, linuxbrew, asdf) and prepends the first one that has `go` — without polluting your shell. If your Go lives somewhere unusual, the wrapper's header shows the one-line `GO_LOCATIONS` edit.

## Python dependencies (image generation)

The image-generation pipeline (`scripts/generate-images.py`) needs Python deps. Set up a venv once:

```bash
python3 -m venv .venv
.venv/bin/pip install pyyaml pillow google-genai
source .venv/bin/activate       # or use .venv/bin/python explicitly
```

If you only run image-gen with `BLOG_CRAFT_TEST_MODE=1` (e.g. in tests), only `pyyaml` is required.

## Writing a new post

```
/blog-post series=<key> number=<NN> slug=<kebab-case> title="..."
```

`<key>` must match a `series[].key` in `.blog-craft.yaml`. Available series: `building`, `operating`, `papers`.

The skill creates the page bundle, prompts you for a one-paragraph cover-image brief, composes a Gemini prompt from your central metaphor, generates the cover, and updates the relevant series overview.

## Capturing media

While drafting a post, embed `<!-- MEDIA: ... -->` placeholders for each screenshot, recording, or photo you'll need. See [`MEDIA-GUIDE.md`](MEDIA-GUIDE.md) for the placeholder syntax.

When you're ready to fill them:

```
/media post=<series-key>/<NN>-<slug>
```

Or omit the `post=` arg to list all posts with remaining placeholders.

## Generating cover images

The image-generation pipeline is in `scripts/generate-images.py`, with prompts in `prompt_for_images.yaml`. To regenerate one image:

```bash
export GEMINI_API_KEY=...
python scripts/generate-images.py --only <key>
```

The reference image is resolved automatically from `.blog-craft.yaml` (`image.reference_image` or the `image.reference_pool`); pass `--reference <path>` to override. Use `--list` to see all image keys, `--dry-run` to preview without calling the API, and `--print-prompt <key>` to see the composed prompt.

## Deploy

blog-craft does not ship a deploy pipeline. Pick whatever fits — GitHub Pages, Netlify, Cloudflare Pages, or container-into-cluster (Frank's pattern). Build with `python3 scripts/build-site.py` and deploy the complete `public/` directory. This includes configured agent exports; plain `hugo` alone does not create Markdown endpoints.

## Reader experience and blog-craft ownership

The reader feature is enabled in the repository's `.blog-craft.yaml`. Curated
starting points and topic mappings live in `blog/data/reader.yaml`; the home,
About and topic pages are ordinary operator-owned content. Edit these locally.
Reusable layouts, CSS, image behavior and the Markdown exporter are supplied by
blog-craft. Keep changes to framework-owned templates upstream so `/update` does
not overwrite them. Hugo configuration and CSS are three-way merged; commit
`.blog-craft.sync.yaml` with each successful update.

Build from `blog/` with `python3 scripts/build-site.py`, then run
`python3 scripts/check_blog_reader.py blog/public` from the repository root.
GitHub Pages and the container deploy the same rendered pages and exports. The
canonical URL is `https://blog.derio.net/frank/`, including when mirrored on
GitHub Pages. The committed Hextra module pin remains authoritative.

The new public endpoints are `content-index.json`, `llms.txt`, and a rendered
`index.md` beside each published regular page. RSS is at `index.xml`. The catalog
includes summaries, canonical URLs, source paths, series/layers, editorial dates,
optional evidence fields and a digest of each complete Markdown response. It does
not include private dossiers, drafts or future/expired content. Paper exports do
include their public reference lists. A plain `hugo` preview does not generate
Markdown: use the build helper when checking those links.

Write a concise frontmatter `description` for new articles. Add `last_verified`,
`tested_versions`, `prerequisites` and `commands_change_state` only when supported
by actual checks. `last_updated` is an editorial date, not evidence of runtime
verification. Missing verification is represented explicitly; no existing posts
were assigned invented verification dates. LinkedIn generation remains deferred.

`Caddyfile` enables gzip/Zstandard compression, five-minute content caching and
one-year immutable caching for fingerprinted assets only. Verify actual transfer
sizes and browser performance on the deployed origin after review and release.

### Companion upstream change

This change pins the exact companion blog-craft reader-experience commit. Push
that branch first; the pin must be reachable in `derio-net/blog-craft` before a
fresh updater checkout can resolve it. After the upstream change is merged and
its `v0.22.0` release exists, change the pin to that release, run the updater dry
run and apply, then commit the refreshed sync snapshot. Do not run the update
from an older installed blog-craft plugin against this newer pin.
