# Spec — Post-Deploy Orchestrator Skill + Cross-Agent Skill-Registration Guard

**Date:** 2026-07-24
**Layer:** repo
**Issue:** derio-net/frank#581 (re-scoped)
**Status:** Reviewed

## A. Context & decisions

frank#581 is the "skill drift" issue: the AGENTS.md-standard migration (#236)
flattened repo-local skills (`agents/skills/`) from first-class invocable skills
into prose named in `CLAUDE.md`. The audit
(`docs/investigations/2026-07-24--repo--open-issue-audit.md`, PR #691) re-scoped
the issue to its two **residual** fixes — surfacing (#1/#2) is already resolved
(`.claude/skills` is a symlink to `../agents/skills`, so all 12 skills surface in
Claude Code's available-skills list):

- **Fix #3 — actuation entry point.** A single orchestrator skill/verb so
  "I deployed something" maps to one discoverable skill that chains
  `/blog-craft:blog-post → update-readme → sync-runbook` and walks the
  Post-Deploy Checklist, instead of a bullet the agent must remember to traverse
  to.
- **Fix #4 — cross-agent registration guard.** A CI-enforced check that every
  `agents/skills/<name>` is registered for every supported harness, so drift
  cannot silently recur.

### Decisions (autonomous — repo-meta task, low-cost/reversible; recorded here)

1. **Skill name = `post-deploy`.** Matches the issue/task framing
   ("post-deploy / fix-extension orchestrator skill"). It also drives the
   fix/extension close-out, described in the `## When to use` block. Renaming
   later is a one-file change.
2. **Guard lives in `scripts/validate-agent-config.sh`** (the existing
   CI-wired + pre-commit-wired agent-config validator), not a new
   `scripts/tests/` pytest. Rationale: only the bash validator is actually run
   by CI (`.github/workflows/agent-config.yml`) and the pre-commit hook; the
   gotcha "no CI runs `scripts/tests/`" means a pytest guard would be a *local*
   check only. The strongest anti-drift guarantee is in the CI-enforced script.
3. **"Registered for every supported harness"** in this repo's architecture =
   (a) the `.claude/skills → ../agents/skills` symlink is intact (Claude Code
   surfacing), **and** (b) every skill is declared in `AGENTS.md` "Shared Skills"
   (the single canonical file codex/opencode/antigravity/gemini/pi read). There
   are no separate per-harness skill directories to check — AGENTS.md is the
   shared source of truth. The guard therefore verifies the symlink + the
   AGENTS.md declaration + each skill's own frontmatter `name`.
4. **Fix the live drift now.** On `main` (post blog-craft migration) three skill
   dirs — `awx-onboard-hosts`, `hop-trace-analysis`, and `frank-alert-triage` —
   exist but are **absent** from AGENTS.md's Shared Skills list, unseen by main's
   hardcoded 3-alias guard. That is exactly the drift the generalized guard must
   catch: it fails on them (RED), then registering all three in AGENTS.md turns
   it GREEN (natural TDD).
5. **No blog/README close-out for this work** (repo/meta layer per
   `plan-post-deploy-checklist.md` skip rules). This *is* the meta-task; it ships
   the orchestrator, it doesn't consume it.

## B. Deliverable 1 — `post-deploy` orchestrator skill

New: `agents/skills/post-deploy/SKILL.md` (auto-reachable via the
`.claude/skills` symlink; declared in AGENTS.md by the guard).

Frontmatter:
```yaml
name: post-deploy
description: >
  Close out a deployed change with one verb — walk the Post-Deploy Checklist
  (new layer) or the Layer Fix/Extension Workflow (fix/extension), chaining
  /blog-craft:blog-post -> update-readme -> sync-runbook and updating the plan
  status. Use right after deploying a new layer or a fix/extension.
user-invocable: true
disable-model-invocation: false
```

Body:

1. **When to use / when to skip** — mirror the skip matrix in
   `agents/rules/plan-post-deploy-checklist.md` (internal-only services skip
   Step 1; meta/repo skip blog+README; investigation/audit skip all).
2. **Step 0 — classify the change:** standard new layer · fix/extension to an
   existing layer · meta/repo · investigation. The classification selects the
   branch and which sub-skills run.
3. **Branch A — standard new layer:** the six-step Post-Deploy Checklist from
   `plan-post-deploy-checklist.md`, each step invoking the matching skill
   (Step 1 → `expose-service` if user-facing; Steps 2–3 → `/blog-craft:blog-post`
   with page-derived series indexes, no manual index edit;
   Step 4 → `update-readme`; Step 5 → `sync-runbook` if manual-operation blocks;
   Step 6 → set plan `**Status:**`). Driven with a TodoWrite item per step.
4. **Branch B — fix/extension:** the Layer Fix/Extension close-out from
   `agents/rules/repo-workflows.md` — retroactively edit the *existing* layer's
   building/operating posts directly (a plain markdown edit, not a
   `/blog-craft:blog-post` run; new media markers → `/blog-craft:media`),
   add a `frank-gotchas.md`/`hop-gotchas.md` one-liner + per-topic prose when the
   fix reveals a non-obvious pattern, append a plan Deviation, run
   `update-readme`/`sync-runbook` only if user-visible/manual-op changes.

> **Note (rebase reconciliation):** while this work was in flight, `main` moved
> blog authoring (`blog-post`/`media`/`papers`) out of `agents/skills/` into the
> **blog-craft plugin** and made series indexes page-derived. This spec and the
> `post-deploy` skill are written against that post-migration reality; the guard
> (Deliverable 2) validates only the remaining repo-local `agents/skills/` — blog
> authoring is out of its scope by construction.
5. **Verify & finish** — confirm each sub-skill's artifact landed; set the plan
   `**Status:**`.

The skill **delegates** to the existing skills (does not duplicate their
content) and points at the two authoritative rules files as the source of truth.

## C. Deliverable 2 — cross-agent skill-registration guard

Extend `scripts/validate-agent-config.sh`. Replace the hardcoded 5-alias
`require_grep` loop with a discovery-driven loop over every
`agents/skills/*/SKILL.md`:

For each skill directory `agents/skills/<name>/`:
- `SKILL.md` must exist (a skill dir without one is a broken registration).
- Its frontmatter `name:` must equal `<name>` (the dir is a real invocable
  skill, and its declared name matches — so Claude surfaces it under the
  expected verb).
- `agents/skills/<name>/SKILL.md` must be referenced in `AGENTS.md` (declared in
  the Shared Skills registry that non-Claude harnesses read).

The existing `.claude/skills → ../agents/skills` symlink assertion already
guarantees Claude-side reachability for **all** skills at once, so per-skill
symlink checks are unnecessary; the loop's job is the AGENTS.md declaration +
frontmatter integrity that the symlink can't prove.

Then fix the live drift: add `awx-onboard-hosts`, `hop-trace-analysis`, and the
new `post-deploy` to AGENTS.md's "Shared Skills" list (and the `/alias` prose).

The guard is enforced by the already-wired `agent-config.yml` CI workflow and
`.githooks/pre-commit` (both trigger on `agents/**` and
`scripts/validate-agent-config.sh` changes) — no new CI plumbing needed.

## D. Test Plan

Repo-meta task, no cluster deploy — verification is local/CI, not post-merge
operational. Acceptance:

- `scripts/validate-agent-config.sh` **fails** with only the generalized loop
  added and AGENTS.md un-fixed, naming `awx-onboard-hosts` + `hop-trace-analysis`
  (RED proves the guard catches real drift).
- After AGENTS.md is fixed and `post-deploy` is added, the validator **passes**.
- A synthetic drift (temporarily `mkdir agents/skills/zzz-probe` with a stub
  SKILL.md, no AGENTS.md entry) makes the validator fail; removing it restores
  green (proves the guard is discovery-driven, not a new hardcoded list).
- `post-deploy` surfaces in Claude Code's available-skills list (symlink) and is
  declared in AGENTS.md (other harnesses).
