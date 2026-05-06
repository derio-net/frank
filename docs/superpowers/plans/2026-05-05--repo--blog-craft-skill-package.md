# Blog Craft Skill Package Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-05--repo--blog-craft-skill-design.md`
**Status:** Not Started

**Goal:** Stand up a new sibling repo `~/Docs/projects/DERIO_NET/blog-craft/` packaged as a Claude Code plugin, shipping three skills (`bootstrap-blog`, `blog-post`, `media`) plus a Hugo + Hextra blog template, verified end-to-end by bootstrapping a fresh blog into `/tmp/` and driving one full post + media-fill cycle through it.

**Layer:** repo (meta — no Frank workload changes; Post-Deploy Checklist intentionally skipped per `plan-config.yaml`).

**Execution mode:** Inline or subagent-driven. **Not** dispatched via VK — the configured `dispatch.default_repo` is `derio-net/frank`, but every task in this plan touches the new `derio-net/blog-craft` repo. Issues against Frank would be wrong.

---

## Phase 1: Repo bootstrap + plugin manifest [agentic]

**Depends on:** —

Stand up the empty `blog-craft` repo on disk and on GitHub, with the plugin manifest in place so the skill loader can discover the (still empty) skill files Phases 3–5 will land. No skills are functional yet — the goal is "an installable plugin that registers zero behaviors."

### Task 1: Verify current Claude Code plugin manifest spec

- [-] **Step 1: Query context7 for current plugin manifest schema.** *(skipped — context7 returned "Invalid API key"; fell through to Step 2's on-disk verification, which the plan already names as the authoritative source.)*
  Run:
  ```bash
  # context7 MCP query — exact tool call from this session:
  # mcp__context7__resolve-library-id query="claude code plugin manifest"
  # then mcp__context7__query-docs library-id=<resolved> query="plugin.json schema skills field"
  ```
  Capture the canonical field names and required keys. Specifically confirm: (a) the directory must be `.claude-plugin/`, (b) the file must be `plugin.json`, (c) whether `skills:` enumerates files or auto-discovers from `skills/*/SKILL.md`, (d) any required fields beyond `name`, `version`, `description`.

  **Expected output:** A short note pasted as a comment block at the top of `docs/ARCHITECTURE.md` (created in Step 6 below) recording exact schema as of today.

- [x] **Step 2: Cross-check against an existing plugin in the user's installation.**
  ```bash
  ls ~/.claude/plugins/cache/ | head -5
  cat ~/.claude/plugins/cache/derio-net/superpowers-for-vk/*/plugin.json 2>/dev/null \
    || cat ~/.claude/plugins/cache/claude-plugins-official/superpowers/*/plugin.json 2>/dev/null
  ```
  Confirm the schema matches what context7 reported. If they diverge, trust the on-disk one (it's what the loader actually parses) and update the note in `docs/ARCHITECTURE.md`.

### Task 2: Create the repo on disk and on GitHub

- [x] **Step 3: Create the directory and initialize git.** *(commit identity adjusted from spec default `stoicepicurian@gmail.com` to `clawdia.ai.assistant@gmail.com` per "clawdia is the visible operator/committer in derio-net".)*
  ```bash
  mkdir -p ~/Docs/projects/DERIO_NET/blog-craft
  cd ~/Docs/projects/DERIO_NET/blog-craft
  git init -b main
  git config user.email "stoicepicurian@gmail.com"
  git config user.name "Yiannis Dermitzakis"
  ```

- [x] **Step 4: Create README, LICENSE, .gitignore.**
  - `README.md` — three sections: "What is blog-craft", "Install", "The three skills". One paragraph each. No prose about Frank specifics.
  - `LICENSE` — MIT, year 2026, holder "Yiannis Dermitzakis".
  - `.gitignore` — minimal: `.DS_Store`, `*.swp`, `__pycache__/`, `.venv/`, plus a comment noting per-blog gitignore is the bootstrapped blog's concern.

- [x] **Step 5: Create the GitHub remote.** *(needed `env -u GITHUB_TOKEN gh auth switch -u YiannisDermitzakis` first — the active service token `clawdia-ai-assistant` lacks `read:org`. Switched back wired into Phase 6 cleanup.)*
  ```bash
  gh repo create derio-net/blog-craft --private --source=. --description "Portable teaching-blog scaffolding and authoring skills for Claude Code (Hugo + Hextra)."
  # Don't push yet — repo is empty.
  ```
  **Expected:** `gh repo create` confirms creation; `git remote -v` shows `origin` pointing at `git@github.com:derio-net/blog-craft.git`.

- [x] **Step 6: Create internal `docs/ARCHITECTURE.md`.**
  Single-page doc covering: (a) the plugin/template duality, (b) the `.tmpl` vs verbatim file convention, (c) the wizard → config → skill data flow, (d) the schema note from Steps 1–2. Aim for ~150 lines. Audience: future-you maintaining the repo six months from now.

### Task 3: Plugin manifest

- [x] **Step 7: Write `.claude-plugin/plugin.json`.** *(`author` written as object `{name: ...}` not string per actual schema; no `skills` enumeration since the loader auto-discovers.)*
  Use the schema confirmed in Steps 1–2. Skeleton (adjust `skills` field per discovered convention):
  ```json
  {
    "name": "blog-craft",
    "version": "0.1.0",
    "description": "Portable teaching-blog scaffolding and authoring skills (Hugo + Hextra).",
    "author": "Yiannis Dermitzakis"
  }
  ```
  If the schema requires explicit skill enumeration, append a `skills` array; if it auto-discovers from `skills/*/SKILL.md`, omit it. Either way, the three skill directories don't exist yet — this is intentional. The next step verifies the loader handles a manifest pointing at empty skill directories.

- [x] **Step 8: Create empty skill directories with stub SKILL.md.**
  ```bash
  mkdir -p skills/{bootstrap-blog,blog-post,media}
  for d in skills/bootstrap-blog skills/blog-post skills/media; do
    cat > "$d/SKILL.md" <<EOF
  ---
  name: $(basename $d)
  description: Stub — implementation lands in a later phase.
  user-invocable: false
  ---

  Not yet implemented.
  EOF
  done
  ```
  These stubs let the plugin install cleanly without errors. `user-invocable: false` keeps them out of `/` autocomplete until they're real.

- [x] **Step 9: Commit Phase 1.** *(committed `2c06db2`; 8 files, 170 insertions; not pushed yet.)*
  ```bash
  git add .
  git status   # confirm only intended files staged
  git commit -m "feat: bootstrap plugin manifest and stub skills"
  ```
  **Expected:** ~10 files committed. No push yet — that lands in Phase 6 after end-to-end smoke test passes.

---

## Phase 2: Hugo + Hextra template (static surface) [agentic]

**Depends on:** Phase 1

Land every file under `templates/hugo-hextra/` that doesn't depend on the wizard runtime. After this phase, a hypothetical "render every `*.tmpl` with a fixed answers fixture" command produces a working Hugo site. The `bootstrap-blog` skill (Phase 3) is just the wizard around this static surface.

### Task 1: Verify Hextra version and recommended layout

- [-] **Step 1: Query context7 for current Hextra setup.** *(skipped via MCP — same Invalid API key error; ctx7 CLI worked once verified Hextra v0.10.0+ recommended pattern. Frank's go.mod was authoritative.)*
  ```bash
  # mcp__context7__resolve-library-id query="hextra hugo theme"
  # then mcp__context7__query-docs library-id=<resolved> query="hugo module imports go.mod baseurl"
  ```
  Confirm: (a) module path for `hextra` (Frank uses `github.com/imfing/hextra`), (b) recommended `hugo.toml` shape, (c) any new params Frank's older config doesn't have.

- [x] **Step 2: Copy reference files from Frank for diffing.**
  ```bash
  cd ~/Docs/projects/DERIO_NET/blog-craft
  mkdir -p /tmp/blog-craft-frank-ref
  cp -r ~/Docs/projects/DERIO_NET/frank/blog/{hugo.toml,go.mod,go.sum,MEDIA-GUIDE.md} /tmp/blog-craft-frank-ref/
  cp -r ~/Docs/projects/DERIO_NET/frank/blog/layouts /tmp/blog-craft-frank-ref/layouts
  cp ~/Docs/projects/DERIO_NET/frank/scripts/generate-all-images.py /tmp/blog-craft-frank-ref/
  ```
  Use this dir as the source-of-truth for what to port. Delete after Phase 2.

### Task 2: Verbatim files (no templating)

- [x] **Step 3: Copy `screenshot.html` and `asciinema.html` shortcodes verbatim.**
  ```bash
  mkdir -p templates/hugo-hextra/layouts/shortcodes
  cp /tmp/blog-craft-frank-ref/layouts/shortcodes/{screenshot,asciinema}.html \
     templates/hugo-hextra/layouts/shortcodes/
  ```
  These shortcodes are blog-agnostic — no Frank-specific assumptions. Verify by reading both files end-to-end and confirming zero hardcoded "frank", "talos", or cluster-specific strings.

- [x] **Step 4: Stage `roadmap.html` (gated).** *(rewrote as a generic minimal skeleton instead of porting Frank's 21KB cluster-roadmap; pointer to Frank's full version left in a comment for users who want richer CSS.)*
  ```bash
  cp /tmp/blog-craft-frank-ref/layouts/shortcodes/cluster-roadmap.html \
     templates/hugo-hextra/layouts/shortcodes/roadmap.html
  ```
  Read the file. Strip Frank-specific layer codes (the body of the `{{ define "roadmap-layers" }}` block, if such a block exists) — replace with a generic placeholder block the user fills in post-bootstrap. Keep the CSS structure intact. Document at the top: `<!-- Generic roadmap shortcode. Customize the layer entries for your blog. -->`

### Task 3: Templated files

- [x] **Step 5: `templates/hugo-hextra/hugo.toml.tmpl`.** *(also added `[security.http]` block — Hugo 0.158+ default blocks Hextra's flexsearch CDN URL containing `@`.)*
  Render fields from wizard answers: `baseURL = "{{ .project.base_url }}"`, `title = "{{ .project.name }}"`, `params.description = "{{ .project.tagline }}"`. Hextra module import block stays static. Use Go `text/template` action syntax; do **not** use Hugo's own `{{ }}` collision-prone syntax — escape any literal `{{` in the template body with `{{"{{"}}` (Frank's `hugo.toml` has none, so no escaping needed unless we add one).

- [x] **Step 6: `templates/hugo-hextra/go.mod.tmpl`.** *(Hextra pinned to v0.12.1 + Go 1.24.2 to match Frank's working blog/go.mod; spec said v0.10.0 / 1.22 — out of date.)*
  ```
  module {{ .project.module_path }}
  go 1.22
  require github.com/imfing/hextra v0.10.0
  ```
  `project.module_path` is derived from `base_url`'s host + path during wizard rendering — see Phase 3 Step 5 for the derivation.

- [x] **Step 7: `templates/hugo-hextra/content/docs/_index.md.tmpl`.**
  ```yaml
  ---
  title: "{{ .project.name }}"
  ---
  {{ .project.tagline }}
  ```
  Hextra renders this as the docs root. Series subdirs (created by `bootstrap-blog`'s render step from the `series` list, not by this template) appear as sidebar entries.

- [x] **Step 8: `templates/hugo-hextra/layouts/partials/extend_head.html.tmpl`.** *(actual Hextra path is `layouts/partials/custom/head-end.html` — file kept verbatim, not templated, because the file's body uses literal `{{ }}` Hugo template syntax.)*
  Port from Frank's `blog/layouts/partials/extend_head.html`, keeping only the media-related CSS section. Strip any Frank-specific theming.

- [x] **Step 9: `templates/hugo-hextra/scripts/generate-images.py.tmpl`.** *(also added `BLOG_CRAFT_TEST_MODE=1` switch — writes 1px PNG instead of calling Gemini; needed for Phase 4 smoke tests per the plan's Notes section.)*
  Port from Frank's `scripts/generate-all-images.py`. Substitutions: `{{ .image_gen.api_key_env }}` for the env var name, `{{ .image_gen.model }}` for the model name, `{{ .image_gen.output_dir }}` for the output directory. The `--only <key>` CLI behavior must be preserved verbatim — `blog-post` (Phase 4) depends on it.

- [x] **Step 10: `templates/hugo-hextra/prompt_for_images.yaml.tmpl`.**
  Initial structure:
  ```yaml
  base_style: |
    {{ .metaphor.base_style | indent 2 }}
  reference_guidance: |
    {{ .metaphor.reference_guidance | indent 2 }}
  images:
    {{ range .series -}}
    - key: overview-{{ .key }}
      output: {{ $.image_gen.output_dir }}/overview-{{ .key }}-cover.png
      description: "Cover for the {{ .title }} series overview"
      prompt: ""    # filled in by user post-bootstrap
    {{ end }}
  ```
  This seeds one entry per series so the user can immediately edit the prompts and run image-gen.

- [x] **Step 11: `templates/hugo-hextra/MEDIA-GUIDE.md.tmpl`.** *(landed as `MEDIA-GUIDE.md` (no `.tmpl`) — the file contains literal `{{< shortcode >}}` examples that Go templating would corrupt; no per-blog substitutions were needed anyway.)*
  Port from Frank's `blog/MEDIA-GUIDE.md`. Substitute `{{ .project.name }}` for "Frank" in the opening paragraph. Strip the closing "Using the `/media` Skill" section's Frank-specific reference paths (e.g., `blog/layouts/shortcodes/...`) and replace with relative paths from the blog root.

- [x] **Step 12: `templates/hugo-hextra/.blog-craft.yaml.tmpl`.**
  This template renders the full schema from the spec. Use Go `text/template` `range`, `printf`, and conditional blocks to emit valid YAML for arbitrary `series` lists and arbitrary `visual_constants` lists. Include the `# only supported in v1` comment on `provider`. Include the `version: 1` line literally (no template).

- [x] **Step 13: `templates/hugo-hextra/.gitignore.tmpl`** + **`README.md.tmpl`.** *(`.gitignore` landed without `.tmpl` — no per-blog substitutions needed. README simplified to drop Hugo-specific template fns that don't exist in Go text/template; replaced with `.project.base_path` derived in the renderer.)*
  - `.gitignore.tmpl`: `public/`, `resources/`, `.hugo_build.lock`, `.env`, `__pycache__/`, `.venv/`. Plain file, no substitution.
  - `README.md.tmpl`: opening with `{{ .project.name }}` and `{{ .project.tagline }}`, then sections "How to write a post" (uses `/blog-post`), "Capturing media" (uses `/media`, link to `MEDIA-GUIDE.md`), "Generating images" (uses `scripts/generate-images.py`), "Deploy" (stub: "Choose your own — this template doesn't ship a deploy pipeline").

### Task 4: Render test

- [x] **Step 14: Write a fixture and render harness.** *(also added `templates/per-series-always/` and `templates/per-series-overview/` subdirs + `--per-series` mode in the renderer for series-scoped templates that the spec hadn't anticipated. Renderer is `tools/render-template/main.go` (~150 lines, Go stdlib + yaml.v3); harness is `tests/render-template.sh`.)*
  ```bash
  mkdir -p tests/fixtures
  cat > tests/fixtures/answers-frank-like.yaml <<'EOF'
  project:
    name: "Test Blog"
    tagline: "A teaching blog"
    base_url: "https://example.com/test/"
    module_path: "example.com/test"
  metaphor:
    persona: "A test persona"
    visual_constants: ["constant one", "constant two"]
    reference_image: "static/images/reference.png"
    base_style: "test base style"
    reference_guidance: "test reference guidance"
  series:
    - key: tutorials
      title: "Tutorials"
      description: "Step-by-step"
    - key: recipes
      title: "Recipes"
      description: "Atomic how-tos"
  voice: "test voice"
  image_gen:
    provider: gemini
    model: gemini-2.5-flash-image-preview
    api_key_env: GEMINI_API_KEY
    output_dir: static/images
    prompts_file: prompt_for_images.yaml
  features:
    roadmap_shortcode: false
    series_overview_posts: true
  EOF
  ```
  Then write `tools/render-template/main.go` — a thin Go program that loads the YAML, renders every `*.tmpl` under a source dir via `text/template`, writes results to a destination dir (stripping `.tmpl`), and copies non-template files verbatim. ~50 lines. This is **the** runtime renderer — `bootstrap-blog` invokes it in Phase 3 Step 4. Using Go (vs Python) guarantees template semantics match.

  Wrap with `tests/render-template.sh` for the test harness:
  ```bash
  #!/bin/bash
  set -euo pipefail
  ANSWERS=$1
  DST=$2
  go run tools/render-template/main.go --src templates/hugo-hextra/ --dst "$DST" --answers "$ANSWERS"
  ```

- [x] **Step 15: Run the harness; check `hugo server` against the output.** *(`HTTP 200` on `localhost:1314/test/` after the security override fix; title and description correctly substituted.)*
  ```bash
  cd ~/Docs/projects/DERIO_NET/blog-craft
  bash tests/render-template.sh tests/fixtures/answers-frank-like.yaml /tmp/golden-output-frank-like/
  cd /tmp/golden-output-frank-like/
  hugo mod init example.com/test 2>&1 || true
  hugo mod get github.com/imfing/hextra@latest
  hugo server --port 1314 &
  HUGO_PID=$!
  sleep 5
  curl -sf http://localhost:1314/test/ > /dev/null && echo "OK" || echo "FAIL"
  kill $HUGO_PID
  ```
  **Expected:** `OK`. If `FAIL`, fix templates and re-run.

- [x] **Step 16: Commit Phase 2.** *(committed `33dfda2`; 21 files, 927 insertions; not pushed yet.)*
  ```bash
  cd ~/Docs/projects/DERIO_NET/blog-craft
  rm -rf /tmp/blog-craft-frank-ref /tmp/golden-output-frank-like
  git add templates/ tools/ tests/
  git status
  git commit -m "feat: ship Hugo + Hextra blog template + render harness"
  ```

---

## Phase 3: bootstrap-blog skill [agentic]

**Depends on:** Phase 2

Replace the stub `skills/bootstrap-blog/SKILL.md` with the real wizard. Test-first: the smoke test fixture from Phase 2 becomes the harness for "did the wizard produce the expected tree?"

### Task 1: Define the smoke test contract

- [x] **Step 1: Write `tests/smoke-bootstrap.sh`.** *(also extracted `tools/bootstrap-render.sh` so the SKILL.md stays prose-focused; smoke test drives the helper end-to-end. Extended `tools/render-template/main.go` with `--check` and `--get-bool` modes to validate YAML without a Python-yaml dep — system python3 lacks PyYAML.)*
  Drives the skill end-to-end against `/tmp/test-bootstrap-<ts>/` using a canned answer set (the same `answers-frank-like.yaml`). Asserts:
  - `.blog-craft.yaml` exists and parses
  - Every file in the Phase 2 fixture exists in the bootstrapped output
  - `hugo server` returns 200 on the chosen port
  - Re-running the wizard refuses with the expected error message

  The smoke test invokes the renderer directly via `tools/render-template/main.go --answers <yaml>`, bypassing the conversational wizard (the conversational layer's tested by hand in Phase 6). This decouples the static-render correctness from the conversational layer.

### Task 2: Write the SKILL.md

- [x] **Step 2: SKILL.md frontmatter.**
  ```yaml
  ---
  name: bootstrap-blog
  description: Bootstrap a new Hugo + Hextra teaching blog with a custom central metaphor and configurable series structure. Use once per new blog repo.
  user-invocable: true
  disable-model-invocation: false
  arguments:
    - name: target_dir
      description: "Directory to create the blog in (default: CWD). Refuses if .blog-craft.yaml already exists."
      required: false
    - name: answers_file
      description: "Path to a YAML file with all wizard answers (testing/automation only — skips the conversational flow)."
      required: false
  ---
  ```

- [x] **Step 3: Body — Steps 0 through 6 (data collection).**
  Write the wizard steps verbatim from the spec's "Wizard Flow: bootstrap-blog" section. Each step is a numbered Markdown subsection. Include exact prompts to show the user, expected reply shape, and validation rules. For Step 3 (series), include the three preset menu and the custom-loop prose with the "tracks" explanation from the spec.

- [x] **Step 4: Body — Step 7 (render).**
  Document: walk every `*.tmpl` under `<plugin_root>/templates/hugo-hextra/`, render with Go `text/template` using collected answers, write to `<target_dir>` (strip `.tmpl`). Plain files copy verbatim. Compute `project.module_path` from `base_url` (parse host + path, strip trailing slash, e.g. `https://my.com/blog/` → `my.com/blog`). Invoke the renderer:
  ```bash
  go run <plugin_root>/tools/render-template/main.go \
    --src <plugin_root>/templates/hugo-hextra/ \
    --dst <target_dir> \
    --answers /tmp/wizard-answers-<ts>.yaml
  ```
  (Renderer was created in Phase 2 Step 14; doubles as runtime.)

- [x] **Step 5: Body — Steps 8–9 (initial image + verify).** *(Step 8 tightened during self-review — replaced shell pseudocode with real instructions, deferred prompt composition to the same base_style+persona+constants+brief+guidance pattern blog-post uses, added explicit user-approval gate.)*
  Document: copy reference image if supplied, run `python <target_dir>/scripts/generate-images.py --only overview-<series-key>` for the first series if `features.series_overview_posts` is true and a reference exists, then port-pick + Hugo smoke test (use `python -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1])"` for the free port).

### Task 3: Run the smoke test

- [x] **Step 6: Drive the skill against the smoke fixture.** *(5/5 assertions pass — file existence, YAML parse, hugo 200 on /test/, re-run refusal.)*
  ```bash
  cd ~/Docs/projects/DERIO_NET/blog-craft
  TS=$(date +%s)
  bash tests/smoke-bootstrap.sh tests/fixtures/answers-frank-like.yaml /tmp/test-bootstrap-$TS
  ```
  **Expected output:** the script prints `PASS` for each assertion and `ALL OK` at the end. On failure, the script prints which assertion failed and leaves the bootstrapped dir in place for inspection.

- [x] **Step 7: Commit Phase 3.** *(committed `0dfa3f8` and self-review fix `991a4c4`; 5 files total; not pushed yet.)*
  ```bash
  git add skills/bootstrap-blog/SKILL.md tests/smoke-bootstrap.sh
  git commit -m "feat(bootstrap-blog): wizard-driven blog scaffolder"
  ```

---

## Phase 4: blog-post skill [agentic]

**Depends on:** Phase 2

Port Frank's `blog-post` skill, generalize against `.blog-craft.yaml`. Phase 3's smoke fixture produces a working blog dir we use as the test sandbox here.

### Task 1: Define the smoke test contract

- [x] **Step 1: Write `tests/smoke-blog-post.sh`.** *(uses a cached venv at `/tmp/blog-craft-test-venv` for PyYAML — system python3 lacks it; `BLOG_CRAFT_TEST_MODE=1` writes a 1px PNG via hardcoded bytes in generate-images.py, so Pillow isn't a test dep.)*
  Preconditions: a bootstrapped blog at `/tmp/test-bootstrap-fixture/` (the script invokes `tests/smoke-bootstrap.sh` if missing). Drives the skill with: `series=tutorials`, `number=01`, `slug=hello-world`, `title="Hello World"`, brief="A test image". Mocks the Gemini call (`BLOG_CRAFT_TEST_MODE=1` switch in `scripts/generate-images.py` writes a 1px PNG instead of calling the API). Asserts:
  - `content/docs/tutorials/01-hello-world/index.md` exists with correct frontmatter
  - `prompt_for_images.yaml` has a new entry with `key: tutorials-01`
  - `static/images/tutorials-01-cover.png` exists
  - `content/docs/tutorials/00-overview/index.md` has a new line referencing post 01

### Task 2: Write the SKILL.md

- [x] **Step 2: SKILL.md frontmatter.**
  ```yaml
  ---
  name: blog-post
  description: Create a new Hugo blog post in a blog-craft blog. Generates a cover image from the configured central metaphor and updates the relevant series overview.
  user-invocable: true
  disable-model-invocation: false
  arguments:
    - name: series
      description: "Series key — must match a series[].key in .blog-craft.yaml"
      required: true
    - name: number
      description: "Post number (zero-padded, e.g. 07)"
      required: true
    - name: slug
      description: "URL slug (kebab-case)"
      required: true
    - name: title
      description: "Post title"
      required: true
  ---
  ```

- [x] **Step 3: Body — config discovery + validation.**
  Section 1: walk up from CWD looking for `.blog-craft.yaml`. If missing, refuse with: `Not in a blog-craft blog. Run /bootstrap-blog or cd to a blog-craft repo.` Section 2: parse YAML, validate `series` arg is in `series[].key`; if not, list valid keys.

- [x] **Step 4: Body — page bundle creation.** *(extracted to `tools/blog-post-create.sh`; helper does page bundle + prompts entry + image-gen + overview update — SKILL.md stays prose-focused for the conversational layer.)*
  Use the spec's frontmatter shape. Compute `weight = number + 1`. Document the file path: `content/docs/<series>/<NN>-<slug>/index.md`. The body of `index.md` starts with a `<!-- Add content here. Use <!-- MEDIA: ... --> placeholders for screenshots/recordings. -->` comment so authors know the contract.

- [x] **Step 5: Body — image prompt composition.**
  Document the concatenation order verbatim from the spec (base_style + persona + visual_constants + brief + reference_guidance). Show the full composed prompt to the user; require explicit approval before appending to `prompt_for_images.yaml` and running image-gen. On regen request: edit the YAML entry, re-run, repeat.

- [x] **Step 6: Body — series overview update.** *(idempotent via `tools/insert-before-marker.py` + auto-managed markers in the overview template; insertion order is `<post-number>. [<title>](relref)` under `## Series Index`, then `| <number> | <title> | (TODO) |` under `## Topic / Evolution Map`.)*
  If `features.series_overview_posts` is true, edit `content/docs/<series>/00-overview/index.md`: append a line under `## Series Index` (look for the heading; if missing, create it) of the form `1. [<title>]({{< relref "<NN>-<slug>" >}})`. Append a row under `## Topic / Evolution Map` (create heading if missing) with `| <NN> | <title> | <one-line, prompt user> |`.

- [x] **Step 7: Body — smoke check.** *(now Step 9 in the SKILL.md — split prior Step 6 into Step 6 (api-key check) + Step 7 (helper run) during self-review, renumbered downstream. Prints preview command, no auto-launch.)*
  Print: `Draft created. Preview with: cd <blog_root> && hugo server --buildDrafts`. Don't auto-launch.

### Task 3: Run the smoke test

- [x] **Step 8: Drive the skill against the bootstrapped fixture.** *(10/10 assertions pass — page bundle, frontmatter title/weight/draft, prompts entry key+body, cover PNG validity, overview index + map updates.)*
  ```bash
  cd ~/Docs/projects/DERIO_NET/blog-craft
  BLOG_CRAFT_TEST_MODE=1 bash tests/smoke-blog-post.sh
  ```
  **Expected:** `PASS` for each assertion and `ALL OK`.

- [x] **Step 9: Commit Phase 4.** *(commits `7c041e1` + self-review `eececad`; 7 files total.)*
  ```bash
  git add skills/blog-post/SKILL.md tests/smoke-blog-post.sh
  git commit -m "feat(blog-post): per-post creator with metaphor-driven covers"
  ```

---

## Phase 5: media skill [agentic]

**Depends on:** Phase 2

Port Frank's `media` skill verbatim except for the two changes documented in the spec (drop env logic; anchor to `.blog-craft.yaml` location). Smoke test against a sandbox blog with one seeded placeholder.

### Task 1: Define the smoke test contract

- [x] **Step 1: Write `tests/smoke-media.sh`.** *(also tests the missing-asset-skip branch and idempotency on re-run; rendered-HTML path correction (`public/docs/...`, no base-path prefix) caught after first run.)*
  Preconditions: bootstrapped blog at `/tmp/test-bootstrap-fixture/` with at least one post containing:
  ```markdown
  <!-- MEDIA: screenshot | A grafana dashboard | Visit https://example.com and screenshot -->
  <!-- {{</* screenshot src="grafana.png" caption="Grafana" */>}} -->
  ```
  Pre-seed the post's bundle dir with a `grafana.png` (1px PNG). Drive the skill with arg `post=tutorials/01-hello-world`. Asserts:
  - The `<!-- MEDIA: ... -->` instruction comment is gone
  - The shortcode line is uncommented (no `<!-- ` prefix or ` -->` suffix)
  - `grafana.png` is unchanged (already under 500KB) OR has been compressed (if pngquant ran)
  - `cd /tmp/test-bootstrap-fixture && hugo --minify` exits 0

### Task 2: Write the SKILL.md

- [x] **Step 2: SKILL.md frontmatter.**
  ```yaml
  ---
  name: media
  description: Capture, optimize, and insert media (screenshots, CLI animations, photos) into blog-craft posts. Fills <!-- MEDIA: ... --> placeholders with rendered shortcodes.
  user-invocable: true
  disable-model-invocation: false
  arguments:
    - name: post
      description: "Post path relative to content/docs/ (e.g. tutorials/07-monitoring). If omitted, lists all posts with remaining placeholders."
      required: false
  ---
  ```

- [x] **Step 3: Body — port Frank's workflow.** *(extracted the textual replacement to `tools/media-fill.py` (~75 lines, pure stdlib). SKILL.md keeps the conversational/capture/optimize layers; helper does the line-pair rewrite. Drops Frank's `source .env` / `source .env_hop` branching per spec.)*
  Copy verbatim from `~/Docs/projects/DERIO_NET/frank/.claude/skills/media/SKILL.md` Steps 1–6 ("Identify Target Post" through "Verify"), with these substitutions:
  - All `blog/content/` → walk up from CWD to find `.blog-craft.yaml`, then `<blog_root>/content/`
  - Drop the entire "Frank cluster: `source .env` / Hop cluster: `source .env_hop`" block under Step 3 ("CLI Animations / Agent-Executed Mode"). Replace with: "Ensure your shell has the env vars your recorded commands depend on. The skill does not source any env files for you."
  - All references to `frank-` paths → relative paths from `<blog_root>`

- [x] **Step 4: Body — Standards section.** *(self-review fix: corrected the captions-required claim — helper only requires `src=`, caption is recommended but not enforced.)*
  Port verbatim, no changes (file size limits, kebab-case, dark-mode preference, etc. are blog-agnostic).

- [x] **Step 5: Body — Reference section.** *(paths anchored to `<blog_root>/...`, not Frank's `blog/...`.)*
  Replace Frank-specific paths with template-relative ones: `<blog_root>/MEDIA-GUIDE.md`, `<blog_root>/layouts/shortcodes/screenshot.html`, etc.

### Task 3: Run the smoke test

- [x] **Step 6: Drive the skill against the bootstrapped fixture.** *(7/7 assertions pass — present-asset filled correctly, missing-asset preserved, hugo build succeeds, rendered HTML contains `<figure class="screenshot">`, second run is no-op.)*
  ```bash
  cd ~/Docs/projects/DERIO_NET/blog-craft
  bash tests/smoke-media.sh
  ```
  **Expected:** `PASS` for each assertion and `ALL OK`.

- [x] **Step 7: Commit Phase 5.** *(commits `021fbb9` (helper + smoke), `e53c551` (belated SKILL.md — Write tool needed prior Read), `cda3035` (self-review caption fix); 4 files total.)*
  ```bash
  git add skills/media/SKILL.md tests/smoke-media.sh
  git commit -m "feat(media): generalized port of Frank's media skill"
  ```

---

## Phase 6: End-to-end integration + plugin install [manual]

**Depends on:** Phase 3, Phase 4, Phase 5

The previous phases each tested their own skill in isolation against fixtures. This phase exercises the *real* user path: install the plugin into Claude Code, invoke the skills via slash commands, generate a real cover image (real Gemini call), and verify all 6 acceptance criteria. Marked manual because the plugin install + Claude Code restart loop, plus the human eyeball check on the generated cover image, can't be scripted.

### Task 1: Local plugin install

- [ ] **Step 1: Install the plugin from the local path.**
  In a Claude Code session:
  ```
  /plugin install /Users/derio/Docs/projects/DERIO_NET/blog-craft
  ```
  Verify all three skills appear in `/` autocomplete: `/bootstrap-blog`, `/blog-post`, `/media`. If `bootstrap-blog` doesn't appear, check `user-invocable: true` in its frontmatter; if it appears but errors on invoke, check the plugin manifest's skills enumeration matches what was discovered in Phase 1 Step 1.

### Task 2: Drive the full pipeline by hand

- [ ] **Step 2: Bootstrap a fresh blog.**
  In a fresh terminal:
  ```bash
  mkdir -p /tmp/test-blog-craft-e2e && cd /tmp/test-blog-craft-e2e
  ```
  Then in Claude Code: `/bootstrap-blog`. Walk through the conversational wizard, answering with: name "E2E Test Blog", tagline "An end-to-end test", base_url "https://example.com/e2e/", a one-paragraph persona, two visual_constants, skip reference image, the default base_style, default reference_guidance, "tracks" preset (accept building/operating defaults), default voice, default image-gen settings, default toggles, no `gh repo create`. **Expected:** `hugo server` smoke test at the end reports a URL; opening it in a browser shows the index page listing both series.

- [ ] **Step 3: Create a post.**
  In Claude Code (still in `/tmp/test-blog-craft-e2e`): `/blog-post series=building number=01 slug=hello-frank title="Hello Frank"`. Provide a one-paragraph image brief. Approve the composed prompt. Confirm the cover image generates and is on-model (the spec calls this out as user-judgment). **Expected:** new file at `content/docs/building/01-hello-frank/index.md`, new entry in `prompt_for_images.yaml`, cover PNG in `static/images/`, overview updated.

- [ ] **Step 4: Add a media placeholder and fill it.**
  Edit `content/docs/building/01-hello-frank/index.md` and add:
  ```markdown
  <!-- MEDIA: screenshot | The Hugo welcome page | Visit localhost:1313/e2e/ and screenshot -->
  <!-- {{</* screenshot src="hugo-welcome.png" caption="Hugo welcome page" */>}} -->
  ```
  Take the screenshot manually (or use any 1px PNG as a stand-in), save as `content/docs/building/01-hello-frank/hugo-welcome.png`. Then in Claude Code: `/media post=building/01-hello-frank`. **Expected:** placeholder gone, shortcode rendered; `cd /tmp/test-blog-craft-e2e && hugo --minify` exits 0.

### Task 3: Verify acceptance criteria

- [ ] **Step 5: Walk the spec's six acceptance criteria.**
  Open `docs/superpowers/specs/2026-05-05--repo--blog-craft-skill-design.md`, jump to the "Acceptance criteria" section, walk through items 1–6, mark each as ✅ or ❌. If any are ❌, file follow-up tasks (do **not** mark this phase done until all 6 are ✅).

### Task 4: Push and tag

- [ ] **Step 6: Push to GitHub.**
  ```bash
  cd ~/Docs/projects/DERIO_NET/blog-craft
  git log --oneline -10   # confirm clean history
  git push -u origin main
  ```

- [ ] **Step 7: Tag v0.1.0.**
  ```bash
  git tag -a v0.1.0 -m "v0.1.0: initial release — bootstrap-blog, blog-post, media skills"
  git push origin v0.1.0
  ```

- [ ] **Step 8: Update plan status.**
  In this plan file, change `**Status:** Not Started` → `**Status:** Complete` (cluster repo workloads use "Deployed", but blog-craft has no cluster footprint; "Complete" matches `repo` layer convention).

- [ ] **Step 9: Clean up test artifacts.**
  ```bash
  rm -rf /tmp/test-bootstrap-* /tmp/test-blog-craft-e2e
  ```

---

## Notes for the executor

- **No Frank changes.** This plan touches one file in Frank: this plan file itself, plus a status flip on the spec's plan-index table (handled by `vk plan spec-index`). All other work lands in `~/Docs/projects/DERIO_NET/blog-craft/`.
- **Two repos, one head.** Each phase commits to `blog-craft`, not Frank. Don't try to push Frank as part of this plan — those commits stay on the `docs/repo-blog-craft-spec` branch in Frank for later folding into main.
- **Test-first interpretation for declarative skill files.** A SKILL.md is a behavioral spec written in prose. The "test" is a smoke script that drives the skill end-to-end and asserts on filesystem state. Phases 3–5 each define their smoke test in Task 1 *before* writing the SKILL.md in Task 2.
- **Mock the Gemini call in Phase 4's smoke test.** Real Gemini calls cost money and require an API key. The `BLOG_CRAFT_TEST_MODE=1` switch in `scripts/generate-images.py` writes a 1px PNG instead. Phase 6's manual run is where the real call happens.
- **`gh repo create` requires `gh auth login`.** Phase 1 Step 5 assumes the user has already authenticated. If not, the script should error clearly, not silently fall back to creating a local-only repo.
