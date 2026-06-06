# Blog Cover Contact Sheet — Implementation Plan

> **For VK agents:** use vk-execute to implement assigned phases.
> **For local execution:** subagent-driven-development or executing-plans.

**Spec:** `docs/superpowers/specs/2026-06-06--repo--blog-cover-contact-sheet-design.md`
**Layer:** `repo` (blog tooling)
**Status:** Not Started

**Goal:** Make the cover-variant pick flow a first-class, tested artifact
instead of per-session improvisation: a `scripts/lib/contact_sheet.py` module
(TDD), automatic `.regen-archive/<key>/contact-sheet.png` composition on every
`--count > 1` batch, and a codified Read-sheet + AskUserQuestion pick step in
the blog-post and papers skills.

## Shape

```
Phase 1 (agentic)  contact_sheet module — labels, grid, cap-glob guard   depends_on: []
Phase 2 (agentic)  generator wiring — gate helper + 3-line main() hook   depends_on: [1]
Phase 3 (agentic)  skill docs (blog-post + papers) + final verification  depends_on: [2]
```

All agentic — pure repo change, no cluster, no secrets, no manual phase.

## Design decisions (from the batched Q&A, 2026-06-06)

1. **Auto on `--count > 1`** — zero extra step; `--no-contact-sheet` opts out.
2. **Tile labels `"{index} · {sha6}"`** — index for conversation, hash for file identity.
3. **Pick contract:** agent Reads the sheet, then AskUserQuestion with tile
   indices; operator can open the sheet directly.
4. **Scope:** blog-post + papers skills (blog-craft plugin is a separate repo —
   out of scope).

## Key constraints (verified against the codebase)

- Compose from **this run's** `write_archive_entry` return values (it returns
  the archived `Path`), never a directory glob — the archive holds older
  variants.
- The FIFO cap prunes via `glob(f"{key}-*.png")`; `contact-sheet.png` can't
  match. Phase 1 pins that with a regression test rather than trusting the
  coincidence.
- `.regen-archive/` is gitignored — the sheet is an ephemeral pick artifact.
- Wiring stays minimal in `main()` by pushing the gate into a pure
  `should_compose()` (unit-tested); no monkeypatched main() integration test.
- Pillow font API: `ImageFont.load_default(size=...)` needs Pillow ≥ 10.1 —
  try/except TypeError fallback keeps older environments working.

## Post-deploy checklist

Repo/meta plan: no blog posts, no README change, no runbook sync (no
`# manual-operation` blocks). Set **Status:** `Complete` when all phases done.
