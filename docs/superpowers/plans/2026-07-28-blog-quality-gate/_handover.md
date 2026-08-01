# Handover — 2026-07-28-blog-quality-gate

**Delete this file before the PR leaves draft.** It is session-transient, unlike
`_improvements.md` which is a deliverable.

Written 2026-07-30 at an agent change-over, mid-plan. Refreshed 2026-08-01
for a second agent change-over.

## 0. 2026-08-01 second takeover — THE REVISION PASS IS DONE

Two sessions ran on 2026-08-01. The first made no implementation changes (it
opened draft PR #733 for review, then handed over). **This is the second**, and
it changed real state. Everything below §2 predates it — read this section
first, because §2's "revision pass deliberately held" is **no longer true**.

### The operator closed the three open questions

- **Review is complete.** The hold on the revision pass is lifted; it has run.
- **`What Transfers` is teaching-posts-only** — and `01-introduction` must not
  carry one either, *even though* it is `diataxis: explanation`, which the lint
  gates on. The rule is the post's **role** (series entry point), not its mode.
- **The Missteps convention stays; blog-about-blog rows are banned.** The
  invariant, now explicit: a misstep is a wrong turn in building the *system*,
  never in writing the post.

### What this session did

1. **Merged `origin/main`** (12 commits, clean, no conflicts). This was not
   housekeeping — see item 37 in `_improvements.md`. Main carried **blog-craft
   v0.18.1 → v0.19.0**, which touches `.blog-craft.yaml`, `.blog-craft.sync.yaml`
   and adds 18 lines to `.github/workflows/blog-ci.yml`. Phase 6 re-renders that
   workflow via `update.py` **at the `blog_craft_version` tag**, so running it
   pre-merge would have silently dropped main's new mermaid-layout step.
2. **Revision pass** (`5670672f`) on the two entry-point posts — `What
   Transfers` removed from both, the self-correction Missteps row and the
   drafting narration dropped, terse table register restored, verify sections
   de-editorialised but every command and decision procedure kept. The other
   five reviewed posts were scanned: **all their Missteps rows are genuine
   system missteps**, no changes needed.
3. **Closed journal finding `4eeefd7d47f9`** (`104c5bb3`) — and found the same
   bug live in `operating/02-storage-backups:133`, a backup-*verification*
   runbook outside this plan's set. Fixed there too.
4. **`_improvements.md` items 33–37** added.

### Verified state at handover

| | |
|---|---|
| HEAD | `104c5bb3`, pushed, 0 unpushed |
| Behind `origin/main` | **0** |
| PR | #733 OPEN, draft, MERGEABLE |
| Gate | **6 findings / 5 posts / 0 LINT FAIL** — unchanged; neither revised post appears |
| `fr journal check` | **exits 0** (was 1) |
| Suite | **369 passed, 1 xfailed** (was 354; main added tests) |
| `hugo --gc` | exit 0 |
| Phases | 1, 2, 3 complete. **4, 5, 6 not started.** |

### Two consequences to carry forward

- **A new, unwaivable LINT WARN exists on `01-introduction`** (`no
  what-transfers closing section`). It is the accepted cost of the operator's
  rule: `transfers_exempt` does not exist, and `quality_exempt` would drop the
  post from the lint layer entirely — the blind spot Phase 6's tripwire is
  being built to prevent. Item 34. Do not "fix" it by re-adding the section.
- **Do not chase `00-overview`'s em-dash WARN** (15.1 → 20.8). The density rose
  because 350 words were *removed*; the numerator is ~60 table rows each using
  one em-dash as a separator. The lint counts table rows as prose. Item 33.

---

## 1. Where things are

> **The counts in this table are pre-merge and stale — §0 has the current ones.**
> Still accurate here: the worktree path, the plan/spec paths, the prerequisite
> PRs, and the phase state.

| | |
|---|---|
| Worktree | `/Users/derio/.cache/fr/worktrees/frank/feat__blog-quality-gate` |
| Branch | `feat/blog-quality-gate` — 11 commits ahead of `main`, **0 unpushed** |
| PR | **frank#733**, OPEN, **draft** |
| Plan | `docs/superpowers/plans/2026-07-28-blog-quality-gate` |
| Spec | `docs/superpowers/specs/2026-07-28--repo--blog-quality-gate-design.md` (merged in #732) |
| Phases | **1, 2, 3 complete.** 4, 5, 6 not started. |
| Gate | **6 findings / 5 posts / 0 LINT FAIL** |
| Suite | `uv run --frozen pytest` → 354 passed, 1 xfailed (pre-existing) |

Prerequisite PRs already merged: **#729** (blog-craft v0.18.0), **#730** (uv/pytest
toolchain), **blog-craft#70 → v0.18.1** (the `_ACTIONABLE` matcher fix), **#731**
(resync), **#732** (spec + plan).

### ~~⚠️ `fr journal check` currently EXITS 1~~ — CLOSED 2026-08-01 (`104c5bb3`)

Kept for the recipe, since `fr journal` still has no `edit`. One open finding
was: `4eeefd7d47f9` — the `-l longhornvolume=` selector handed down
for `08-backup` was wrong (real label: `backup-volume`), and returns
`No resources found` rather than erroring. It **is** fixed in the post; the
journal entry was never flipped to `state=fixed`. fr-goal §8 gates delivery on a
clean journal check, so **this must be closed before the PR leaves draft.**

Note: `fr journal` has no `edit` — flip `state=open` → `state=fixed` in the HTML
comment marker by hand in
`docs/superpowers/journals/plans/2026-07-28-blog-quality-gate.md`.

---

## 2. The operator's live feedback — READ FIRST, IT CHANGES THE NEXT PASS

> **SUPERSEDED by §0 — the review is complete and this pass has run.**

The operator was **mid-review of the seven completed posts** and has flagged a
**regression** in `00-overview`, in their words:

> the self-involved style of speaking. Talking to itself, recording a snapshot,
> not enduring knowledge. This is not thinking of the reader, it's
> self-congratulating prose: "look, I'm correcting the previous session's
> inconsistencies". The crisp table of contents polluted with self-talk. And the
> table under "What transfers" is replaced by a list.

They intend to continue through the other posts. **A revision pass is owed and
is deliberately being held** until their review completes, so it lands once with
all feedback rather than churning per-post. Do not start it early.

Diagnosed cause (all orchestrator error, not agent error) — full write-up in
`_improvements.md` items 30–32:

1. `00-overview` is `diataxis: reference`. The validator's what-transfers check
   is mode-gated (`"(expected for tutorial/explanation posts)"`) and never fires
   on it. The blind cold-reader flagged it anyway — it reads `reader-arc.md`,
   which is prose and **not** mode-gated — and the orchestrator relayed that as a
   work order without checking the exemption. An index page got a tutorial's
   ending.
2. The two briefs in the same pass contradicted each other: `01-introduction`'s
   said "remove Missteps rows about the post's own drafting history";
   `00-overview`'s said only "reframe rows as forks". Same executor, opposite
   results.
3. Register drift: `00`'s Missteps cells went from terse to 60–100-word
   paragraphs — a table in name only.

**The standing lesson:** a critique is *evidence*, not a work order. The blind
reader is deliberately ignorant of genre, which is what makes it valuable on a
teaching post and wrong on an index. The orchestrator is the only actor that
knows the genre and must filter accordingly.

Two open questions the operator may answer, which change the shape of the fix:

- Should `What Transfers` exist on non-teaching posts at all? If "teaching only",
  `00`'s is a straight revert, not a rewrite.
- Is the **Missteps convention itself** the vector? Four columns inviting "what
  happened / why it was wrong / how we fixed it" structurally invites session
  narration. `01` had two blog-about-blog rows before this pass; `00` gained one
  during it.

---

## 3. The pipeline — how work is actually done here

This plan is the **first run** of a three-stage treatment. Each stage is run by
an agent blind to the others. Reproduce it exactly; it is the point of the plan.

```
ORCHESTRATOR (you — the only actor with the Agent tool)
  │
  ├─► blog-craft:post-researcher   (read-only)  ── BEFORE writing
  │     mechanical brief: repo path, post path, research question.
  │     NOTHING about expected findings, target counts, or how the section
  │     should read. Ask "does the repo contradict this post?"
  │
  ├─► super-fr:fr-phase-executor   (writes)     ── the mechanical work only
  │     hand the evidence brief down inside the dispatch prompt
  │
  └─► blog-craft:cold-reader       (read-only)  ── AFTER writing
        brief = draft path + methodology refs ONLY.
        ALSO STATE THE POST'S diataxis MODE (this is the fix for §2.1 above)
```

**Critical:** `fr-phase-executor`'s tool grant is `Read, Edit, Write, Bash, Grep,
Glob` — **no `Agent`**. It cannot dispatch anything. A plan step telling it to is
silently approximated and ticked (this happened in Phases 1–2 and is why the
retrofit `P3.T3` exists). Filed as **super-fr#428**.

Steps in the plan that are the orchestrator's are marked
`**ORCHESTRATOR STEP — not the phase executor's.**` in their prose. The schema has
no notion of actor; that is improvement item 7.

### Dispatch gotcha

`blog-craft:post-researcher` and `blog-craft:cold-reader` were added to the
read-only allowlist in `~/.claude/hooks/agent-worktree-required.sh` (and
documented in `~/.claude/rules/agent-worktree-default.md`). **Do not pass
`isolation: "worktree"` to them** — it cuts a fresh worktree from `main`, so they
would read a different tree than the one being edited. Same reason
`fr-phase-executor` is exempt.

---

## 4. Environment traps — every executor brief must carry these

1. **Lead every Bash call with a literal `cd /Users/derio/.cache/fr/worktrees/frank/feat__blog-quality-gate && …`.**
   Never a variable assignment (`WT=… && cd "$WT"`) — the fr pipeline guard
   rejects it since super-fr 3.19.0. cwd resets between calls.
2. **`uv run --frozen <cmd>` for all Python.** Bare `pytest`/`python3` lack pyyaml.
3. **`rtk proxy <cmd>` whenever an exit status is the evidence.** rtk summarises
   and can render a hard failure as a benign message — it once reported a missing
   pytest as `Pytest: No tests collected`.
4. **Live cluster needs an absolute kubeconfig** — the worktree has no `.env` or
   `.talos/` (gitignored, so `git worktree add` never brought them):
   `KUBECONFIG=/Users/derio/Docs/projects/DERIO_NET/frank/.talos/Frank_Kubeconfig.yaml`
5. **The guard scans the whole command string** — keep base-clone paths out of
   `fr journal add` bodies (write to a scratch file, pass `--body "$(cat …)"`).
6. **Two executors cannot run in parallel** on this worktree — same git index.
   Cold-reads and researchers parallelise fine (read-only).

---

## 5. What remains

### Phase 4 — `10-local-inference`, `13-unified-auth`, `36-metrics-api`
All fail only `no actionable section`. Full three-stage treatment.

### Phase 5 — `operating/29-metrics-api`, `building/30-frank-papers`
`29` needs an actionable section **and** a diagram; `30` needs only a diagram.
**`05.yaml` explicitly asks whether `30-frank-papers` should have a diagram at
all, or whether its `diataxis` mode is simply wrong** — a decorative diagram to
satisfy a how-to/tutorial check would be the same mistake one level down.

### Phase 6 — flip + guard
- `quality.enabled: true` in `.blog-craft.yaml`, then re-render CI via
  blog-craft's `update.py` (the workflow step is gated on that flag).
- Anti-gaming tripwire. **Three design constraints this run produced:**
  1. Scan headings **independently of `quality_exempt`** — that flag removes a
     post from the *lint* layer too (unlike `diagram_exempt`), so an exempt post
     would otherwise be a blind spot in the guard built to prevent blind spots.
  2. Carry a self-test proving the detector can fire (mirror
     `scripts/tests/test_python_toolchain_single_source.py`).
  3. Consider folding in a **repo-relative dead-link check** — `06-fun-stuff`
     shipped one and nothing in blog CI catches the class.
- Gotcha one-liner in `agents/rules/frank-gotchas.md`.

### Owed regardless
- **The revision pass** carrying the operator's full review feedback (§2).
- **Close journal finding `4eeefd7d47f9`** (§1).
- **`superpowers:requesting-code-review` at each phase boundary.** fr-goal §7
  mandates it; it was **skipped after Phases 1, 2 and 3** and substituted with the
  orchestrator's own inline verification, which is self-review. Filed as
  **super-fr#430**. Do not repeat this.
- **Submit `_improvements.md`** once the plan completes — 32 items across
  super-fr, blog-craft, frank, and the pipeline itself.

---

## 6. Judgement calls already made (don't silently reopen)

- **`06-fun-stuff` is `quality_exempt`, not fixed.** OpenRGB's LEDs are firmware
  write-locked; no alert, no runbook entry, no test, and
  `agents/rules/plan-post-deploy-checklist.md:28` names novelty layers as the
  class that doesn't warrant an operating post. Evidencing greps are pasted in
  the post; the reasoning is in the body so readers see it. The cold-reader
  judged the exemption **earned**.
- **Post-level facts are in scope; repo-level fixes are not.** Factual errors in
  posts this plan edits get fixed. The two data-file bugs, the plan ticked
  complete against a nonexistent `clusters/frank/`, and the infra docs describing
  dead hardware are **listed in `_improvements.md`, deliberately not fixed here**.
- **`06-fun-stuff` has an unresolved contradiction left open on purpose**: the
  post says the fans are rainbow, the investigation says the LEDs are black. No
  agent can see the physical machine. Needs the operator.

---

## 7. Hard-won facts worth not rediscovering

- **The gate is a heading regex.** Any H2 containing
  `verify|verifying|recover|recovery|reproduce|runbook|steps|procedure|how to|rollback|checklist|walkthrough|troubleshoot|diagnos|smoke test`
  passes it **regardless of what follows, including nothing**. Green proves
  nothing.
- **Two independent counters.** Gate findings are indented `x` lines under a post
  heading; lint hits are top-level `LINT FAIL:`/`LINT WARN:` lines. **Never add
  them together** — Phase 1's step got its target wrong exactly that way.
- **31 `what-transfers` lint WARNs across the corpus**, unchanged. Phases 4–5
  touch nine; ~20 are on posts this plan never opens. It's a WARN, so it has been
  scrolling past unread since v0.18.0 — which is how it reached 31.
- **Negative claims from a read-only researcher are unreliable.** Two of four
  briefs asserted "X does not exist in the repo"; one was false (`longhorn-static`
  *does* exist, Longhorn-generated). Positive citations (`file:line`) held
  everywhere. A Grep-only agent can prove presence, never absence. **Verify every
  negative by running it.**
- **Silent-failure commands are the dangerous class.** Of three broken commands
  found in `operating/22`, the one that *errored* was harmless. The two that
  returned empty — an unauthenticated call against a private repo, and a 401
  swallowed by `curl -sf` — read as "healthy" in a health check.
- **A verify section can be fully evidenced and still not be a decision
  procedure.** Test each command: *what would I do differently depending on its
  output?* "Nothing" means it is documentation, not verification.
- **`fr plan edit --state` accepts only `x` or `-` — it cannot untick.** Reversing
  a wrong tick means hand-editing YAML.
- **Adding steps to a phase without matching `state.steps` entries** fails with a
  raw pydantic error naming neither the file nor the key.

---

## 8. Upstream issues filed this run

- **super-fr#428** — a plan step can tell `fr-phase-executor` to dispatch a
  subagent it has no tool for; the step gets ticked anyway. Sibling of #420
  (PR #422 open); a PreToolUse hook cannot catch this one because no tool call is
  ever made.
- **super-fr#430** — fr-goal §7 (milestone code review) is the only step with no
  artifact, so skipping it is free and invisible.
