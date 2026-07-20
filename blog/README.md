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

blog-craft does not ship a deploy pipeline. Pick whatever fits — GitHub Pages, Netlify, Cloudflare Pages, or container-into-cluster (Frank's pattern). The static site is whatever `hugo --minify` produces in `public/`.
