# Plan — Post-Deploy Orchestrator Skill + Skill-Registration Guard

**Status:** Complete
**Layer:** repo
**Spec:** `docs/superpowers/specs/2026-07-24-post-deploy-orchestrator-and-skill-guard-design.md`
**Issue:** derio-net/frank#581 (re-scoped to fixes #3 + #4)

## Overview

Two residual fixes for the skill-drift issue: an actuation-verb orchestrator
skill (#3) and a CI-enforced cross-agent skill-registration guard (#4). Surfacing
(#1/#2) is already resolved by the `.claude/skills` symlink. Repo-meta layer —
no cluster deploy, no blog/README close-out (this ships the orchestrator; it
does not consume it).

### Task 1: Cross-agent skill-registration guard (fix #4) — TDD

- [x] **Step 1 (RED):** Generalize `scripts/validate-agent-config.sh` — replace
  the hardcoded 5-alias `require_grep` loop with a loop over every
  `agents/skills/*/SKILL.md` asserting: SKILL.md exists, frontmatter `name:` ==
  dir name, and `agents/skills/<name>/SKILL.md` is referenced in AGENTS.md. Run
  it and confirm it FAILS naming `awx-onboard-hosts` + `hop-trace-analysis`
  (proves the guard catches real live drift). *(RED confirmed.)*
- [x] **Step 2 (GREEN):** Add `awx-onboard-hosts` and `hop-trace-analysis` to
  AGENTS.md's "Shared Skills" registry. Re-run the validator → passes.
- [x] **Step 3 (regression):** Synthetic-drift check — a stub skill dir with no
  AGENTS.md entry fails the validator; removing it restores green. Confirms the
  guard is discovery-driven, not a fresh hardcoded list. *(Guard caught it.)*

### Task 2: `post-deploy` orchestrator skill (fix #3)

- [x] **Step 1:** Write `agents/skills/post-deploy/SKILL.md` — frontmatter
  (`name: post-deploy`, `user-invocable: true`), When-to-use/skip matrix, Step 0
  classify, Branch A (standard-layer Post-Deploy Checklist chaining
  `expose-service`/`blog-post`/`update-readme`/`sync-runbook`/plan-status),
  Branch B (Layer Fix/Extension Workflow), verify+finish. Delegates to existing
  skills; points at the two authoritative rules files.
- [x] **Step 2:** Register `post-deploy` in AGENTS.md Shared Skills. The guard
  from Task 1 now requires it. Re-run validator → passes.
- [x] **Step 3:** Confirm `post-deploy` surfaces via the `.claude/skills`
  symlink and its frontmatter is well-formed. *(Confirmed — it appears in Claude
  Code's available-skills list.)*

### Task 3: Verify & close out

- [x] **Step 1:** Run `scripts/validate-agent-config.sh` (full pass),
  `scripts/validate-plans.sh` on this plan.
- [x] **Step 2:** Code review over spec + plan + diff; fix all findings.
- [ ] **Step 3:** Set plan Status to Complete; open PR.

## Deployment Deviations

**Code-review findings fixed (2026-07-24, all confirmed against reality):**

- **F1 (false-pass):** the guard's AGENTS.md check matched a skill path
  *anywhere*, so a skill also named in the aliases prose (`blog-post`,
  `sync-runbook`) could be deleted from the registry list and still pass.
  Anchored the check to a registry list line (`^-[[:space:]]…`).
- **F2 (false-fail):** a double-quoted frontmatter `name:` yielded `"name"`
  with quotes → mismatch. The parse now strips surrounding quotes.
- **F3 (parse scope):** `/^name:/` matched any line, incl. a body line. Bounded
  the parse to the leading `---` frontmatter block.
- **F4 (faithfulness):** Branch B was labelled "the five-step Layer
  Fix/Extension Workflow" though it drops Diagnose/Fix and adds README/runbook
  steps. Relabelled as the fix/extension *close-out* and flagged the additions.
- **F5 (path clarity):** Branch A step 3 now names the operating index file
  explicitly (same `00-overview/index.md` as the building index).
- **F6 (pre-existing doc bug):** originally fixed a wrong `repo-workflows.md`
  blog-index path — **superseded by the rebase**: `main`'s blog-craft migration
  rewrote that whole step (page-derived indexes), so the change was dropped and
  main's version taken as-is.
- **Cleanups:** dropped now-redundant static `require_file` skill entries
  (subsumed by the discovery loop); broadened the reverse-check char class.

**Rebase reconciliation (2026-07-24):** the branch was rebased onto a `main` that
had migrated blog authoring (`blog-post`/`media`/`papers`) into the **blog-craft
plugin**, added the `frank-alert-triage` skill, and made blog series indexes
page-derived. Reconciled: (1) the `post-deploy` skill + spec now target
`/blog-craft:blog-post` / `/blog-craft:media` with no manual index-edit step;
(2) the guard was re-applied on top of main's validator (main kept a hardcoded
3-alias loop); (3) AGENTS.md now registers **all** repo-local skills — main was
itself missing `awx-onboard-hosts`, `hop-trace-analysis`, **and**
`frank-alert-triage` (drift the new guard caught and this PR fixes).
