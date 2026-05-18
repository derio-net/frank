---
title: "Operating The Frank Papers — Research, Dossiers, and Publishing"
date: 2026-05-18
draft: false
tags: ["operations", "papers", "blog", "hugo", "dossier", "mermaid", "research"]
summary: "Day-to-day commands for the Papers workflow — scaffolding a paper, getting the dossier past the gate, the five `papers/` shortcodes, cross-series linking, cover-image generation, and the publish flow."
weight: 26
---

This is the operational companion to [Building The Frank Papers]({{< relref "/docs/building/30-frank-papers" >}}). That post explains *why* there's a third series and what the dossier gate is for. This one is the cookbook: scaffold a paper, get the dossier to pass, write the prose, generate the cover, ship.

## What "Ready to Write" Looks Like

A Paper is *ready to write* when all of the following are true:

- `blog/content/docs/papers/NN-slug/index.md` exists and has the §1–§6 skeleton with `series: papers` frontmatter.
- `docs/papers-dossiers/NN-slug/dossier.md` exists.
- `python scripts/validate-dossier.py docs/papers-dossiers/NN-slug/dossier.md` exits 0.
- The dossier's `status:` field is `ready` (set by the human author after reviewing the named gaps and counter-arguments).

Until all four are true, drafting prose is premature. The pre-commit hook will block the commit; the section-skeleton template will not have the Frank-specific context it needs; and the cover-image prompt key won't exist in `blog/prompt_for_images.yaml`.

## Scaffolding a New Paper

One command creates both halves:

```bash
scripts/scaffold-paper.sh <NN> <slug>
```

`NN` is the two-digit paper number; `slug` is kebab-case and matches the layer code wherever possible (e.g. `04-gpu-operators`, `13-auth`, `10-local-inference`).

```bash
$ scripts/scaffold-paper.sh 04 gpu-operators
Created blog/content/docs/papers/04-gpu-operators/index.md
Created docs/papers-dossiers/04-gpu-operators/dossier.md
```

The Hugo bundle lands with:

- Frontmatter pre-populated (`title:`, `paper_number: 4`, `series: papers`, `status: draft`, empty `tldr`, empty `tags`, empty `capabilities`, empty `references`).
- §1 Stack position, §2 Vendor landscape, §3 Architecture comparison, §4 Operational evidence, §5 Decision rubric, §6 Return to Frank's choice — each with a placeholder paragraph.
- Mermaid diagram placeholders in the sections that need them (§1 `flowchart LR`, §2 the `landscape` shortcode, §3 per-vendor `flowchart TD`, §6 the decision tree).
- A `{{< papers/dossier-link >}}` placeholder — **commented out by default**, because `single.html` injects one automatically (see *Don't render the dossier chip twice* below).

The dossier lands with the six required section headers and stub entries:

```markdown
## Vendors in scope
- name: TODO
  positioning: incumbent
  primary_url: https://example.com

## Primary sources
- title: TODO
  type: vendor-docs
  url: https://example.com
  quoted_passages: ["..."]
  relevance: TODO

## Frank artefacts
- kind: yaml
  path_or_url: TODO
  date: TODO
  demonstrates: TODO

## Diagrams planned
- TODO

## Named gaps
- TODO

## Counter-arguments considered
- TODO
```

## The Dossier Loop

Once `scaffold-paper.sh` returns, the workflow is: fill the dossier, validate, fix, validate, fix, validate, until clean.

```bash
python scripts/validate-dossier.py docs/papers-dossiers/04-gpu-operators/dossier.md
```

The validator parses sections as YAML blocks under `##` headers and checks the gate rules. **Exit 0 = pass.** On failure it prints each problem on its own line and exits 1.

Common failures and how to read them:

- **`Vendors in scope: only 2 entries; need ≥3`** — add a third vendor. If you genuinely can't name three, the topic is too narrow for a *landscape* paper and probably belongs in a Building deviation instead.
- **`Primary sources: only 4 entries; need ≥5`** — add a fifth. Allowed `type:` values: `vendor-docs`, `paper`, `postmortem`, `talk`, `benchmark`. A second link from the same vendor counts; a blog post by a vendor counts as `vendor-docs`, not `paper`.
- **`Source X has invalid type 'documentation' (must be one of …)`** — fix the `type:` to one of the allowed values.
- **`URL https://… returned non-2xx (or timed out)`** — the validator does a `HEAD` then `GET` fallback against every source URL. Either the URL is wrong, or the source is temporarily unreachable, or the host rejects the validator's User-Agent. Common offenders: gated postmortem PDFs, vendor docs behind a CDN that doesn't like `HEAD`. Verify the URL by hand; if it's intermittent, rerun.
- **`Frank artefacts: only 2 entries; need ≥3`** — add a third operational reference. Allowed `kind:` values: `grafana-screenshot`, `asciinema`, `yaml`, `commit`, `incident`. A line in `frank-gotchas.md` counts as an `incident`. A commit SHA counts as `commit`. A YAML manifest path counts as `yaml`.
- **`Named gaps: 0 entries; need ≥1`** — name a question the analysis couldn't answer with the available evidence. "We don't have data for the vendor's behaviour at >10k QPS" is a fine gap. "There may be edge cases" is not.
- **`Counter-arguments considered: 0 entries; need ≥1`** — name the strongest opposing view the paper deliberately engaged with. Required to ship.

Iterate until the validator is clean. Then mark the dossier ready:

```yaml
# At the top of dossier.md
status: ready
```

(`status: ready` is checked by the prose-drafting skill, not the gate itself — it's the human author's gesture that the structural work is done and prose can begin.)

## The `/papers` Skill

The repo skill `/papers` enforces the workflow:

```
/papers
```

Invoking it triggers the dossier-gate check, scaffolds if needed, and walks the section skeleton. It will refuse to draft prose until the validator passes. The skill lives at `agents/skills/papers/SKILL.md` and is loaded via `AGENTS.md`.

When dispatched to a subagent (e.g. `vk pickup` for a phase that says "draft Paper 04"), the agent gets the same gate. There is no path that lets a subagent bypass the gate by clever invocation — the pre-commit hook runs on every commit and rejects unstaged dossiers regardless of who staged the index.md.

## The Five Shortcodes

All under `blog/layouts/shortcodes/papers/`. Use them in `index.md` like:

```
{{</* papers/pullquote source="NVIDIA gpu-operator architecture overview" */>}}
Foundational architecture for the incumbent — every other vendor
either re-implements its components or stitches around its absence.
{{</* /papers/pullquote */>}}
```

Quick reference:

| Shortcode | Section it belongs in | What it renders |
|---|---|---|
| `papers/pullquote` | §3 architecture | Indented blockquote with attribution + a tied-back source link |
| `papers/scar` | §4 operational evidence | Callout box (orange left-border) for a named incident on Frank |
| `papers/capability-matrix` | §2 vendor landscape | Feature-by-feature grid table styled for `.paper-post` |
| `papers/landscape` | §2 vendor landscape | Mermaid `quadrantChart` wrapper — pass `title`, `axes`, four `q1..q4` labels, and `vendors` |
| `papers/dossier-link` | (auto-injected; see below) | A chip linking to `/docs/papers-dossiers/NN-slug/dossier.md` |

Example `landscape` usage:

```
{{</* papers/landscape
  title="Auth landscape — late 2025"
  axes="complexity:openness"
  q1="self-host friendly"
  q2="cloud-first incumbents"
  q3="walled gardens"
  q4="DIY territory"
  vendors="Authentik: [0.35, 0.85]\nKeycloak: [0.7, 0.8]\nAuth0: [0.85, 0.15]"
*/>}}
```

The diagram types by section live in `agents/rules/repo-papers.md`. Use the right one — don't mix `flowchart TD` and `quadrantChart` in §2, and don't draw a quadrant chart in §3 (that's for per-vendor architecture comparisons, which want `flowchart TD`).

## Don't Render the Dossier Chip Twice

`single.html` automatically injects a footer chip pointing to the paper's dossier on every Papers page. **If you also use `{{< papers/dossier-link >}}` inline in the body, the chip renders twice.**

Two patterns, pick one:

- **Default (recommended):** rely on the auto-injected footer chip. Leave the inline shortcode commented out in `index.md`.
- **Inline:** use `{{< papers/dossier-link >}}` near §1 to make the dossier discoverable above the fold. If you do this, **remove the auto-injection** for this paper by setting `dossier_link_auto: false` in frontmatter (it overrides the default `single.html` behaviour for this page only).

This is captured in `agents/rules/repo-papers.md` and is the most common authoring footgun.

## Cross-Series Linking

The bidirectional discovery surface is single-sourced from the Paper's frontmatter:

```yaml
---
title: "GPU Operators — Choosing an Operator for Self-Hosted GPU Workloads"
series: papers
paper_number: 4
related_building: "docs/building/04-gpu-compute"
related_operating: "docs/operating/04-gpu-compute"
---
```

What this gives you:

- **On Paper 04** — `papers-forwardlinks.html` reads the two `related_*` paths from frontmatter and renders forward chips at the top of the article: *🔧 Hands-on: Building — GPU Compute / Operating on GPU Compute.*
- **On Building 04 and Operating 04** — `papers-backlink.html` iterates `where .Site.Pages "Params.series" "papers"`, matches their `related_*` paths against the current page's path, and renders a chip: *🔬 Decision-level view: Paper 04 — GPU Operators.*

The chips appear automatically the moment the Paper is built. You do not edit Building 04 or Operating 04 to make them appear.

If a chip doesn't render after you publish:

1. Double-check the `related_building` and `related_operating` paths in the Paper's frontmatter. They are relative to `blog/content/` — `docs/building/04-gpu-compute`, no leading slash, no `.md`.
2. Confirm Hugo built without errors: `cd blog && hugo --buildDrafts 2>&1 | grep ^ERROR`.
3. Confirm the target Building/Operating page exists at exactly that path. A typo in the slug silently produces no backlink.

## Cover Image Generation

Every Paper gets a per-paper cover image generated by Gemini, following the established pipeline:

1. **Write the prompt.** Append a new entry to `blog/prompt_for_images.yaml` under the `# --- Papers Series Covers ---` section:

    ```yaml
    - key: paper-04-gpu-operators
      output: blog/content/docs/papers/04-gpu-operators/cover.png
      description: "Paper 04 — GPU Operators (Frank weighing operator architectures)"
      prompt: >-
        Frank the server-hardware Frankenstein monster examining a row of
        candidate GPU operators … wearing his thin black necktie and round
        reading glasses [Papers signature]. EXACTLY ONE FIGURE.
        ABSOLUTELY NO TEXT.
    ```

    The Papers visual signature is **thin black necktie + round reading glasses** — the consistent reader cue that they're on a Papers cover, not a Building or Operating one.

2. **Generate.**

    ```bash
    source .env_common
    .venv/bin/python scripts/generate-all-images.py \
      -r blog/static/images/reference.png \
      --only paper-04-gpu-operators
    ```

    The `-r blog/static/images/reference.png` argument is critical — it pins Frank's face shape, the no-nose constraint, and the visible Frankenstein stitches. Without it, Gemini drifts (no-nose becomes a nose, the green skin loses contrast, the character sheet softens).

3. **Review the output.** Open `cover.png`. If Frank is wrong (e.g. shirt blends with skin, duplicate Frank, mangled text on a sign), regenerate. The Gemini model returns variation per call, so the same command often fixes a near-miss.

4. **On 503 from Gemini:** the model is shared and occasionally returns `503 UNAVAILABLE`. Retry with a 20–60 second backoff. Multi-image batches with `--only key-a,key-b` are useful when generating multiple Papers covers in sequence.

The series assets — `banner-papers.png` (thin title strip shown above every Papers page) and `tile-papers.png` (16:9 landing-page card thumbnail) — live at `blog/static/images/`. They're regenerated only when the series visual signature changes, not per paper.

## Building and Previewing

Standard Hugo workflow with `--buildDrafts` to include in-progress papers:

```bash
cd blog && hugo server --buildDrafts --port 1313
```

Open `http://localhost:1313/docs/papers/`. The section landing lists all Papers (including drafts). Each Paper renders with the Mermaid Frank theme, the `.paper-post` CSS scope, the auto-injected dossier chip, and the forward-link chips (if `related_building` / `related_operating` are set).

To verify cross-linking:

- Visit the matching Building post (`/docs/building/04-gpu-compute/`). The 🔬 Decision-level view chip should appear at the top.
- Visit the matching Operating post. Same chip.

If neither appears, see *Cross-Series Linking* above.

For the final pre-publish check:

```bash
cd blog && hugo --buildDrafts 2>&1 | tee /tmp/hugo-build.log | tail -10
grep -cE "^ERROR" /tmp/hugo-build.log
```

Expected: zero errors. The most common Phase 0 break was a malformed shortcode call — `{{< papers/landscape title="…" axes="…" >}}` with mismatched quotes inside the `vendors` argument. Fix the quote escaping; rerun.

## Publishing

When the prose is ready, drafting is done, and the cover image is in:

1. Set `draft: false` and `status: published` in frontmatter.
2. Commit the bundle (`blog/content/docs/papers/NN-slug/index.md`, `cover.png`, any inline images) **and** the dossier (`docs/papers-dossiers/NN-slug/dossier.md`) **and** the prompt entry (`blog/prompt_for_images.yaml`) in a single commit.
3. Push to `main`. The Hop cluster Caddy + CI pipeline picks it up; production is live ~2 minutes later.
4. Verify: `curl -s https://blog.derio.net/frank/docs/papers/NN-slug/ | grep -i "<paper title>"`.

The dossier ships with the paper, on the same SHA. Anyone reading the paper a year from now can `git show HEAD:docs/papers-dossiers/NN-slug/dossier.md` and see the sources, gaps, and counter-arguments the author was working from. That's the gate's whole point — the receipts are versioned with the prose.

## Promoting and Reordering

Papers publish in **decision-weight order**, not paper-number order. `paper_number` is fixed at scaffold time (it maps to the layer code) but `publish_order` and `weight` in frontmatter control where the Paper appears in the section listing.

To move Paper 13 above Paper 04 in the listing:

```yaml
# Paper 13 frontmatter
weight: 5  # lower than Paper 04's weight
publish_order: 2  # explicit reading order
```

Hextra orders section listings by `weight` ascending. The paper-number stays 13 in URLs and frontmatter — only the listing rank changes.

## Renaming or Archiving a Paper

If a Paper is renamed after publish:

```bash
# Hugo bundle
git mv blog/content/docs/papers/04-gpu-operators blog/content/docs/papers/04-gpu-stack
# Dossier
git mv docs/papers-dossiers/04-gpu-operators docs/papers-dossiers/04-gpu-stack
# Update the prompt key in blog/prompt_for_images.yaml
sed -i.bak 's/paper-04-gpu-operators/paper-04-gpu-stack/g' blog/prompt_for_images.yaml
rm blog/prompt_for_images.yaml.bak
# Add a Hugo alias for inbound links
echo 'aliases: ["/docs/papers/04-gpu-operators/"]' >> blog/content/docs/papers/04-gpu-stack/index.md
# Commit; the dossier path lives at the new slug
```

The `aliases` array makes Hugo emit a `<meta http-equiv="refresh">` from the old URL — search engines and shared links keep working.

Archiving (e.g. a Paper that's been superseded) is the same shape but with `draft: true` and a final commit explaining why. Don't delete the bundle — the dossier is part of the historical record.

## Common Failures Cheat Sheet

| Symptom | Cause | Fix |
|---|---|---|
| `git commit` blocked: `DOSSIER GATE: no dossier found` | Paper `index.md` staged with no matching dossier file | `scripts/scaffold-paper.sh <NN> <slug>` to create the dossier; fill and validate |
| `git commit` blocked: validator failure | One of the gate rules failed | Read the validator output; fix that specific section |
| Dossier chip renders twice on a Paper | Inline shortcode + auto-injection both fire | Pick one (see *Don't render the dossier chip twice*) |
| Cross-link chip doesn't appear | `related_building` / `related_operating` path typo or pointing at a non-existent page | Fix path in Paper frontmatter; rebuild |
| Mermaid diagram doesn't theme correctly | Page missing `body.paper-post` class | Confirm `series: papers` in frontmatter — the class is gated on that |
| Cover image is green-on-green Frank | Prompt forgot to specify shirt colour | Add explicit "white dress shirt, not green" to the prompt; regenerate |
| Banner shows duplicate Frank | Gemini drift on prompts that don't say "EXACTLY ONE FIGURE" | Add the constraint; regenerate |
| `hugo --buildDrafts` errors on shortcode parse | Quote escaping in `papers/landscape` `vendors` argument | Use `\n` for line breaks; escape inner quotes carefully |

## References

- [Building The Frank Papers — Research Infrastructure for a Third Series]({{< relref "/docs/building/30-frank-papers" >}}) — the companion building post
- `agents/rules/repo-papers.md` — canonical reference (frontmatter schema, dossier format, diagram types by section)
- `agents/skills/papers/SKILL.md` — `/papers` skill (enforces the workflow)
- `scripts/scaffold-paper.sh` — scaffold a paper + dossier pair
- `scripts/validate-dossier.py` — dossier gate validator
- `.githooks/pre-commit` — the gate that fires on staged Papers files
