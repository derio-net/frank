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

7. **Cover image** — add prompt to `blog/prompt_for_images.yaml` under
   `# --- Papers Series Covers ---`. Template:
   `"Frank examining [domain object] with a decision-maker expression
   (curious / skeptical / weighing), wearing his thin black tie and
   round reading glasses."`
   Generate: `scripts/generate-all-images.py --only <key>`

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
