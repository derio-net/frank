---
name: papers
description: Write or continue a Frank Paper — enforces the dossier gate, scaffold commands, and section skeleton.
user-invocable: true
disable-model-invocation: false
arguments:
  - name: number
    description: "Paper number (e.g. 02)"
    required: true
  - name: slug
    description: "URL slug (kebab-case, e.g. local-inference)"
    required: true
---

# papers — Write a Frank Paper

Use this skill when writing or continuing a Frank Paper. Enforces the
dossier gate and correct section skeleton.

## When to use

- Scaffolding a new paper (`scripts/scaffold-paper.sh`)
- Filling a research dossier
- Drafting paper sections
- Generating per-paper cover image
- Publishing (setting draft: false)

## Procedure

1. **Check paper number and slug** — confirm they match the TOC in the spec
   (`docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`).

2. **Scaffold if not yet created:**
   ```bash
   scripts/scaffold-paper.sh <NN> <slug>
   ```

3. **Fill dossier** (`docs/papers-dossiers/NN-slug/dossier.md`):
   - ≥3 vendors in scope
   - ≥5 primary sources, ≥3 distinct type values
   - All URLs reachable
   - ≥3 Frank artefacts, ≥2 distinct kind values
   - ≥1 named gap
   - ≥1 counter-argument

4. **Gate:** `python scripts/validate-dossier.py docs/papers-dossiers/NN-slug/dossier.md`
   Must exit 0 before drafting begins.

5. **Human gate:** Author reviews named gaps + counter-arguments.
   Mark dossier `status: ready` when satisfied.

6. **Draft** — fill every `§` section in `blog/content/docs/papers/NN-slug/index.md`.
   Section budgets:
   - TL;DR: ≤150 words (write last)
   - §1: 200–350 words + 1 `flowchart LR`
   - §2: 400–600 words + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}`
   - §3: 800–1400 words + 1 `flowchart TD` per vendor
   - §4: 300–600 words + charts or ≥2 citations
   - §5: 300–600 words + ≥1 `{{< papers/scar >}}`
   - §6: 200–400 words + `flowchart TD` ≤4 leaves
   - §7: 200–400 words

7. **Cover image** — read the top-of-file comment block in
   `blog/prompt_for_images.yaml` for the full agent procedure. Add an
   entry under `# --- Papers Series Covers ---` with required fields:

   - `key: paper-NN-cover`
   - `torso_variant: <0|1|2>` — index into `torso_variants.papers`
     (`0` = white shirt + tie default, `1` = lab coat over shirt+tie,
     `2` = denim/leather overalls over shirt+tie). Match it to what
     the paper's domain calls for.
   - `mood: <preset key>` — `weighing`, `skeptical`, `cautious`,
     `approving`, `satisfied`, `focused`, etc. Decision-maker moods
     fit Papers best.
   - `references:` — **pick explicitly** from
     `.reference-pool/papers/subjects/`. Filenames are descriptive
     (e.g. `frank-white-shirt-black-tie-2.png`,
     `frank-white-shirt-sleeves-up-black-tie-1.png`). Choose 1 (rarely
     2) whose clothing AND pose match what the scene should look like.
   - `output:`, `description:`, `prompt:` — scene only, following the
     header guidance.

   Setting `series: papers` is fine — there's no auto-attached banner
   anymore, so it no longer brings any risk. Torso also derives from
   the key prefix, so either works.

   Generate (the script auto-picks the papers-series master reference
   from `.reference-pool/papers/reference-papers.png`; add `references:`
   to the yaml entry to stack additional anchors from
   `.reference-pool/papers/subjects/`):
   ```bash
   source .env_common && uv run --with pyyaml --with google-genai --with pillow \
     scripts/generate-all-images.py --only <key>
   ```

   Generating a batch instead (`--count N>1`) leaves a labeled grid at
   `.regen-archive/<key>/contact-sheet.png` — follow the blog-post skill's
   pick flow (Read the sheet, AskUserQuestion with tile indices, copy the
   chosen variant to the entry's `output` path).

8. **Review** — verify TL;DR ≤150 words, voice pass, dossier-link renders.

9. **Publish** — set `draft: false`, `status: published`.
   ```bash
   cd blog && hugo --minify
   git add blog/content/docs/papers/NN-slug/ docs/papers-dossiers/NN-slug/
   git commit -m "docs(repo): publish Paper NN — <title>"
   ```

## Rules

- TL;DR is written last, after the body has stabilized.
- Scar callouts (`{{< papers/scar >}}`) are used 1–3× per paper.
- `{{< papers/dossier-link >}}` inline OR automatic injection — not both.
- `related_building` and `related_operating` use paths relative to
  `blog/content/` (e.g., `docs/building/10-local-inference`).
