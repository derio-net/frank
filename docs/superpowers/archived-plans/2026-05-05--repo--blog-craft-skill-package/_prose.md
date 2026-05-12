# Blog Craft Skill Package Implementation Plan

## Phase 1: Repo bootstrap + plugin manifest

### Task 1: Verify current Claude Code plugin manifest spec

- P1.T1.S1: Query context7 for current plugin manifest schema. *(skipped — context7 returned "Invalid API key"; fell through to Step 2's on-disk verification, which the plan already names as the authoritative source.)*

- P1.T1.S2: Cross-check against an existing plugin in the user's installation.

### Task 2: Create the repo on disk and on GitHub

- P1.T2.S3: Create the directory and initialize git. *(commit identity adjusted from spec default `stoicepicurian@gmail.com` to `clawdia.ai.assistant@gmail.com` per "clawdia is the visible operator/committer in derio-net".)*

- P1.T2.S4: Create README, LICENSE, .gitignore.

- P1.T2.S5: Create the GitHub remote. *(needed `env -u GITHUB_TOKEN gh auth switch -u YiannisDermitzakis` first — the active service token `clawdia-ai-assistant` lacks `read:org`. Switched back wired into Phase 6 cleanup.)*

- P1.T2.S6: Create internal `docs/ARCHITECTURE.md`.

### Task 3: Plugin manifest

- P1.T3.S7: Write `.claude-plugin/plugin.json`. *(`author` written as object `{name: ...}` not string per actual schema; no `skills` enumeration since the loader auto-discovers.)*

- P1.T3.S8: Create empty skill directories with stub SKILL.md.

- P1.T3.S9: Commit Phase 1. *(committed `2c06db2`; 8 files, 170 insertions; not pushed yet.)*

## Phase 2: Hugo + Hextra template (static surface)

### Task 1: Verify Hextra version and recommended layout

- P2.T1.S1: Query context7 for current Hextra setup. *(skipped via MCP — same Invalid API key error; ctx7 CLI worked once verified Hextra v0.10.0+ recommended pattern. Frank's go.mod was authoritative.)*

- P2.T1.S2: Copy reference files from Frank for diffing.

### Task 2: Verbatim files (no templating)

- P2.T2.S3: Copy `screenshot.html` and `asciinema.html` shortcodes verbatim.

- P2.T2.S4: Stage `roadmap.html` (gated). *(rewrote as a generic minimal skeleton instead of porting Frank's 21KB cluster-roadmap; pointer to Frank's full version left in a comment for users who want richer CSS.)*

### Task 3: Templated files

- P2.T3.S5: `templates/hugo-hextra/hugo.toml.tmpl`. *(also added `[security.http]` block — Hugo 0.158+ default blocks Hextra's flexsearch CDN URL containing `@`.)*

- P2.T3.S6: `templates/hugo-hextra/go.mod.tmpl`. *(Hextra pinned to v0.12.1 + Go 1.24.2 to match Frank's working blog/go.mod; spec said v0.10.0 / 1.22 — out of date.)*

- P2.T3.S7: `templates/hugo-hextra/content/docs/_index.md.tmpl`.

- P2.T3.S8: `templates/hugo-hextra/layouts/partials/extend_head.html.tmpl`. *(actual Hextra path is `layouts/partials/custom/head-end.html` — file kept verbatim, not templated, because the file's body uses literal `{{ }}` Hugo template syntax.)*

- P2.T3.S9: `templates/hugo-hextra/scripts/generate-images.py.tmpl`. *(also added `BLOG_CRAFT_TEST_MODE=1` switch — writes 1px PNG instead of calling Gemini; needed for Phase 4 smoke tests per the plan's Notes section.)*

- P2.T3.S10: `templates/hugo-hextra/prompt_for_images.yaml.tmpl`.

- P2.T3.S11: `templates/hugo-hextra/MEDIA-GUIDE.md.tmpl`. *(landed as `MEDIA-GUIDE.md` (no `.tmpl`) — the file contains literal `{{< shortcode >}}` examples that Go templating would corrupt; no per-blog substitutions were needed anyway.)*

- P2.T3.S12: `templates/hugo-hextra/.blog-craft.yaml.tmpl`.

- P2.T3.S13: `templates/hugo-hextra/.gitignore.tmpl` + **`README.md.tmpl`.** *(`.gitignore` landed without `.tmpl` — no per-blog substitutions needed. README simplified to drop Hugo-specific template fns that don't exist in Go text/template; replaced with `.project.base_path` derived in the renderer.)*

### Task 4: Render test

- P2.T4.S14: Write a fixture and render harness. *(also added `templates/per-series-always/` and `templates/per-series-overview/` subdirs + `--per-series` mode in the renderer for series-scoped templates that the spec hadn't anticipated. Renderer is `tools/render-template/main.go` (~150 lines, Go stdlib + yaml.v3); harness is `tests/render-template.sh`.)*

- P2.T4.S15: Run the harness; check `hugo server` against the output. *(`HTTP 200` on `localhost:1314/test/` after the security override fix; title and description correctly substituted.)*

- P2.T4.S16: Commit Phase 2. *(committed `33dfda2`; 21 files, 927 insertions; not pushed yet.)*

## Phase 3: bootstrap-blog skill

### Task 1: Define the smoke test contract

- P3.T1.S1: Write `tests/smoke-bootstrap.sh`. *(also extracted `tools/bootstrap-render.sh` so the SKILL.md stays prose-focused; smoke test drives the helper end-to-end. Extended `tools/render-template/main.go` with `--check` and `--get-bool` modes to validate YAML without a Python-yaml dep — system python3 lacks PyYAML.)*

### Task 2: Write the SKILL.md

- P3.T2.S2: SKILL.md frontmatter.

- P3.T2.S3: Body — Steps 0 through 6 (data collection).

- P3.T2.S4: Body — Step 7 (render).

- P3.T2.S5: Body — Steps 8–9 (initial image + verify). *(Step 8 tightened during self-review — replaced shell pseudocode with real instructions, deferred prompt composition to the same base_style+persona+constants+brief+guidance pattern blog-post uses, added explicit user-approval gate.)*

### Task 3: Run the smoke test

- P3.T3.S6: Drive the skill against the smoke fixture. *(5/5 assertions pass — file existence, YAML parse, hugo 200 on /test/, re-run refusal.)*

- P3.T3.S7: Commit Phase 3. *(committed `0dfa3f8` and self-review fix `991a4c4`; 5 files total; not pushed yet.)*

## Phase 4: blog-post skill

### Task 1: Define the smoke test contract

- P4.T1.S1: Write `tests/smoke-blog-post.sh`. *(uses a cached venv at `/tmp/blog-craft-test-venv` for PyYAML — system python3 lacks it; `BLOG_CRAFT_TEST_MODE=1` writes a 1px PNG via hardcoded bytes in generate-images.py, so Pillow isn't a test dep.)*

### Task 2: Write the SKILL.md

- P4.T2.S2: SKILL.md frontmatter.

- P4.T2.S3: Body — config discovery + validation.

- P4.T2.S4: Body — page bundle creation. *(extracted to `tools/blog-post-create.sh`; helper does page bundle + prompts entry + image-gen + overview update — SKILL.md stays prose-focused for the conversational layer.)*

- P4.T2.S5: Body — image prompt composition.

- P4.T2.S6: Body — series overview update. *(idempotent via `tools/insert-before-marker.py` + auto-managed markers in the overview template; insertion order is `<post-number>. [<title>](relref)` under `## Series Index`, then `| <number> | <title> | (TODO) |` under `## Topic / Evolution Map`.)*

- P4.T2.S7: Body — smoke check. *(now Step 9 in the SKILL.md — split prior Step 6 into Step 6 (api-key check) + Step 7 (helper run) during self-review, renumbered downstream. Prints preview command, no auto-launch.)*

### Task 3: Run the smoke test

- P4.T3.S8: Drive the skill against the bootstrapped fixture. *(10/10 assertions pass — page bundle, frontmatter title/weight/draft, prompts entry key+body, cover PNG validity, overview index + map updates.)*

- P4.T3.S9: Commit Phase 4. *(commits `7c041e1` + self-review `eececad`; 7 files total.)*

## Phase 5: media skill

### Task 1: Define the smoke test contract

- P5.T1.S1: Write `tests/smoke-media.sh`. *(also tests the missing-asset-skip branch and idempotency on re-run; rendered-HTML path correction (`public/docs/...`, no base-path prefix) caught after first run.)*

### Task 2: Write the SKILL.md

- P5.T2.S2: SKILL.md frontmatter.

- P5.T2.S3: Body — port Frank's workflow. *(extracted the textual replacement to `tools/media-fill.py` (~75 lines, pure stdlib). SKILL.md keeps the conversational/capture/optimize layers; helper does the line-pair rewrite. Drops Frank's `source .env` / `source .env_hop` branching per spec.)*

- P5.T2.S4: Body — Standards section. *(self-review fix: corrected the captions-required claim — helper only requires `src=`, caption is recommended but not enforced.)*

- P5.T2.S5: Body — Reference section. *(paths anchored to `<blog_root>/...`, not Frank's `blog/...`.)*

### Task 3: Run the smoke test

- P5.T3.S6: Drive the skill against the bootstrapped fixture. *(7/7 assertions pass — present-asset filled correctly, missing-asset preserved, hugo build succeeds, rendered HTML contains `<figure class="screenshot">`, second run is no-op.)*

- P5.T3.S7: Commit Phase 5. *(commits `021fbb9` (helper + smoke), `e53c551` (belated SKILL.md — Write tool needed prior Read), `cda3035` (self-review caption fix); 4 files total.)*

## Phase 6: End-to-end integration + plugin install

### Task 1: Local plugin install

- P6.T1.S1: Install the plugin from the local path. *(install path turned out to be a two-step `marketplace add` then `install <plugin>@<marketplace>`, not the bare `/plugin install <path>` shown here. Required adding `.claude-plugin/marketplace.json` to blog-craft (see commit `f2c90ac`) and patching `~/.claude/plugins/known_marketplaces.json` to add a missing `lastUpdated` field. Three skills now appear in this session as `blog-craft:bootstrap-blog`, `blog-craft:blog-post`, `blog-craft:media`.)*

### Task 2: Drive the full pipeline by hand

- P6.T2.S2: Bootstrap a fresh blog. *(driven two ways: (a) for the conversational layer — operator drove `/bootstrap-blog` to scaffold the **stoa-blog** in a separate terminal, which surfaced the bugs that became PR #1 (banner placement, 2-col tile grid, Hextra subpath URL handling, operator-generated banners for Gemini's panoramic-aspect-ratio limit); (b) for static-surface validation — drove `tools/bootstrap-render.sh` against `tests/fixtures/answers-frank-like.yaml` → `/tmp/blog-craft-pr1-test/` with `BLOG_CRAFT_TEST_MODE=1`. Hugo build clean; homepage renders 2-col grid linking to `docs/tutorials/` and `docs/recipes/`; no 404s.)*

- P6.T2.S3: Create a post. *(driven two ways: (a) operator drove `/blog-post` against the real stoa-blog with a live Gemini call — that real-use exposed the asymmetry between asking the user for body/summary vs composing them from context, which became PR #1's commit-2 (`feat(blog-post): compose body and summary from context`) refactor; (b) drove `tools/blog-post-create.sh` directly against `/tmp/blog-craft-pr1-test/tutorials/01-hello-frank/` with `BLOG_CRAFT_TEST_MODE=1` for the static-surface verification — page bundle written with correct frontmatter (title, weight=2, draft:false, summary), prompts entry appended (`key: tutorials-01`), 1px stub PNG generated at `static/images/tutorials-01-cover.png`, both Series Index and Topic/Evolution Map rows added to `00-overview/index.md`.)*

- P6.T2.S4: Add a media placeholder and fill it. *(executed against `/tmp/blog-craft-pr1-test/content/docs/tutorials/01-hello-frank/` — added the canonical `<!-- MEDIA: ... -->` + `<!-- {{</* shortcode */>}} -->` pair, dropped a 1px PNG named `screenshot.png` in the bundle, ran `tools/media-fill.py`. Marker pair correctly replaced with live `{{< screenshot src="screenshot.png" caption="Test screenshot" >}}`. Hugo build clean; rendered HTML at `public/docs/tutorials/01-hello-frank/index.html` contains `<figure class="screenshot"><img src="/test/docs/tutorials/01-hello-frank/screenshot.png" loading="lazy" /><figcaption>Test screenshot</figcaption></figure>` with subpath-correct URL. Re-running media-fill confirmed idempotent: `no <!-- MEDIA: --> placeholders found`. Side note caught during the test: the `/blog-post` skill's prose says "see MEDIA-GUIDE.md for marker syntax" — agents must read that before composing markers, since the second placeholder line uses Hugo's `{{</* */>}}` commented-shortcode form, NOT the bare `{{< >}}` form.)*

### Task 3: Verify acceptance criteria

- P6.T3.S5: Walk the spec's six acceptance criteria. *(all 6 ✅. **AC1** plugin installs cleanly via two-step `/plugin marketplace add` → `/plugin install` (annotation in Step 1). **AC2** `bootstrap-blog` produces a working Hugo + Hextra site — `public/index.html` 31KB, lists both configured series with subpath-correct URLs. **AC3** `.blog-craft.yaml` is written with full schema; re-running `bootstrap-render.sh` against the same target exits 2 with `Refusing to overwrite. Remove the file manually if you really want to re-bootstrap.` **AC4** `blog-post` creates page bundle + cover image (`BLOG_CRAFT_TEST_MODE=1` mocks the live Gemini HTTP call; real-Gemini path is exercised, only the API request short-circuits — confidence in real-Gemini behavior carries from operator-driven stoa-blog runs that did call the API) + updates overview. **AC5** `media` finds + (operator-)optimizes + inserts a screenshot placeholder end-to-end (optimization is operator-driven per `MEDIA-GUIDE.md`'s pngquant/optipng instructions — the helper itself doesn't auto-compress). **AC6** end-to-end smoke against freshly-bootstrapped `/tmp/blog-craft-pr1-test/` — full pipeline (bootstrap → first post → first media-fill) clean. Plus PR #1's 6-item test plan: 6/6 PASS. Plus all 3 smoke suites: 22/22 PASS (5+10+7).)*

### Task 4: Push and tag

- P6.T4.S6: Push to GitHub. *(done across two PRs. **PR #1** (`feat: site banner above navbar; 2-col homepage tiles; body+summary composition`, https://github.com/derio-net/blog-craft/pull/1) merged 2026-05-12 — site banner partial, 2-col Hextra card grid, asymmetric `image=` vs `link=` subpath handling, operator-generated banners (Gemini doesn't do panoramic), body/summary auto-composition refactor. **PR #2** (`feat: hugo-serve.sh wrapper + smoke-blog-post.sh helper-signature fix`, https://github.com/derio-net/blog-craft/pull/2) merged 2026-05-12 — wrapper around `hugo server` for predictable Hugo Module builds, smoke-blog-post adapted to PR #1's helper signature, consistency sweep across 6 docs/scripts. Both PRs went through code-review; PR #2's review-fix commit addressed three Important issues plus three Minor polish items. Default branch flipped from feature → main on first push (PR #1 description noted this).)*

- P6.T4.S7: Tag v0.1.0. *(tagged **v0.2.0** instead. Rationale: PR #1 + PR #2 added meaningful surface (banner, 2-col tiles, body/summary composition, hugo-serve wrapper) on top of the original Phase-5 plugin install, so the first versioned release reflects that. Tag created locally (annotated) and pushed to origin: `v0.2.0` → `d49984f`. Tag message captures the cumulative surface and the 22/22 smoke result.)*

- P6.T4.S8: Update plan status. *(this edit — top-of-file Status: Not Started → Complete. Convention follows `plan-config.yaml`'s `repo` layer: "Complete" rather than "Deployed" since blog-craft has no cluster footprint.)*

- P6.T4.S9: Clean up test artifacts. *(removed `/tmp/test-bootstrap-fixture/`, `/tmp/blog-craft-pr1-test/`, `/tmp/blog-craft-test-venv/`, plus the `/tmp/pr1-*` and `/tmp/test-blog-post-*` fixture files used for the helper drives, plus `/tmp/hugo-serve.log` and `/tmp/hugo-smoke-bootstrap.log`.)*
