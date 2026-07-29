# Improvements surfaced by the first run of the blind-agent pipeline

This plan was the **first** execution of the isolated-agent treatment: an
orchestrator-dispatched `blog-craft:post-researcher` before writing, and an
orchestrator-dispatched `blog-craft:cold-reader` after, with
`super-fr:fr-phase-executor` doing only the mechanical work between them.

It worked — see the findings table at the bottom — but the run surfaced a long
list of defects in the tooling around it. Collected here rather than filed
piecemeal mid-run, to be submitted once the plan completes.

Status key: **[filed]** already upstream · **[open]** to file · **[local]** fix in this repo

---

## super-fr

1. **[filed — #428]** A plan step can instruct `fr-phase-executor` to dispatch a
   subagent it has no tool for, and the step gets ticked anyway. Its grant is
   `Read, Edit, Write, Bash, Grep, Glob` — no `Agent`. Silent hollow compliance.
2. **[filed — #428]** The executor should refuse the tick on a step it could not
   perform as written. Ours reported the deviation *and ticked*, so the plan
   recorded completion for work nobody did.
3. **[filed — #428]** `fr journal check --require-reviews` — fr-goal §7 mandates a
   code review per milestone and nothing enforces it. See the dedicated issue on
   this; it is the largest of the four.
4. **[filed — #428]** fr-plan guidance: steps should name **outcomes**, not
   mechanisms. A step naming a tool rots silently when the actor changes.
5. **[open]** **`fr plan edit --state` cannot untick.** It accepts only `x` or
   `-`, so a wrong tick is unfixable without hand-editing YAML. This directly
   weakens (2): an executor told to refuse a tick has no way to *undo* one it
   already made. We had to hand-edit `03.yaml` to reverse the contaminated
   research ticks.
6. **[open]** **Adding steps to a phase without matching `state.steps` entries
   fails with a raw pydantic error** naming neither the file nor the missing key
   (`… input_type=dict]  For further information visit https://errors.pydantic.dev/…`).
   Either auto-create missing state entries or name the offending step id.
7. **[open]** **The plan schema has no notion of *which actor* owns a step.**
   Orchestrator-only steps (dispatch a subagent) and executor steps are
   indistinguishable, so we encoded it in prose (`**ORCHESTRATOR STEP — not the
   phase executor's.**`) and hoped. A `actor: orchestrator|executor` field would
   let `fr pickup` filter and `self-review` validate (1) mechanically.
8. **[open]** **The isolation guard rejects a command that leads with a variable
   assignment**, even when the `cd` target is the prescribed worktree
   (`WT=… && cd "$WT" && …` denied; literal `cd … && …` allowed). This worked on
   the previous plugin build and broke on 3.19.0. Every executor brief in this
   run had to carry a warning about it.
9. **[open]** **Journal entries cannot be edited** — `fr journal` is add / render
   / check only. Flipping a finding `open → fixed` (which `check` gates on)
   requires hand-editing the markdown and its HTML comment marker.

## blog-craft

10. **[open]** **`quality_exempt` removes a post from the *lint* layer too**, not
    just the structural gate — unlike `diagram_exempt`, which waives one check.
    An exempt post becomes invisible to em-dash, what-transfers and AI-vocabulary
    checks with no signal. Either scope it or document it loudly.
11. **[open]** **`_ACTIONABLE` is a heading regex, so a section passes with
    nothing under it.** We are shipping a frank-local tripwire (every actionable
    heading must be followed by a fenced command block, with a self-test proving
    the detector can fire) — it belongs upstream.
12. **[open]** **Nothing validates repo-relative links.** `06-fun-stuff` shipped a
    dead link to the OpenRGB investigation (`docs/superpowers/plans/…`; the file
    is under `docs/superpowers/implemented/investigations/…`). Cheap check.
13. **[open]** **Nothing validates cited commit hashes.** Across two Missteps
    tables, **7 of 8 were wrong** — real commits attached to the wrong rows.
    `ce2fcd9e` was cited three times across two posts and was wrong every time.
    A Missteps table is an explicit invitation to verify; ours did not survive
    being taken up on it. `git cat-file -e <sha>` plus a subject-vs-claim check
    would catch the class.
14. **[open]** **The `what-transfers` WARN fires on 31 posts and has been scrolling
    past unread.** A warning nobody triages is a check that does not exist.
    Consider a per-post baseline so new posts cannot add to the count, or a
    warning budget that fails when it grows.
15. **[open]** **`post-researcher` / `cold-reader` are dispatched from the *skill*
    layer** (`/blog-post`, `/post-rewrite`), which runs in the main loop where
    `Agent` exists. Any pipeline that writes posts by another route silently
    loses both — which is exactly what happened here. Document the contract, or
    expose a callable entry point that does not depend on the caller being a skill.

## frank (local)

16. **[local]** `blog/data/layer_palette.yaml` has 21 entries; `docs/layers.yaml`
    has 22 codes — no `virt` colour. Latent until a post is tagged `layer: virt`.
17. **[local]** `blog/data/roadmap.yaml` has the wrong `key` on five entries
    (Multi-tenancy→`net`, AI Agent Orchestrator→`agents`, Media Generation→`gpu`,
    Progressive Delivery→`gitops`, Infrastructure Automation→`cicd`). Five cards
    render in another layer's colour. Nothing fails a build. Found independently
    by two agents.
18. **[local]** `2026-03-20--repo--multi-cluster-restructure` is ticked complete
    with a backfilled note, but `clusters/frank/` was never created — only
    `clusters/hop/`. The live repo contradicts its own completion record.
19. **[local]** `README.md` and `agents/rules/frank-infrastructure.md` still
    describe the Zone A Raspberry Pi 5 that **died 2026-06-20**.
20. **[local]** `patches/README.md` is stale (longhorn 1.11.0, "RTX 5070 PCIe not
    detected").
21. **[local]** `docs/papers-dossiers/05-gpu-scheduling/dossier.md:78` cites
    `patches/phase04-gpu/gpu-operator-values.yaml` as a live artefact; it is
    vestigial.
22. **[local]** Four superseded Helm values files remain tracked under `patches/`
    (cilium, longhorn ×2, gpu-operator) — Layer 2 config in the Layer 1 tree.
    Decide: archive, or document the exception.
23. **[local, needs a human]** `06-fun-stuff` says the fans are rainbow; the
    investigation's "Current State" says the LEDs are black, replaying a
    pre-BIOS-update colour from NV memory. One is stale. Nobody in the session
    can see the physical machine.

## super-fr — sanction this list as process

30. **[open] Make an improvements list a first-class artifact, alongside the
    journal.** The journal holds findings *about the work*
    (`fr journal add --kind finding|discovery`). This file holds findings *about
    the machinery doing the work* — tooling defects, pipeline gaps, process
    corrections — and there is nowhere for it to live. It exists here only
    because the operator asked mid-run; a session that ends without that prompt
    loses the lot.
    Same argument as journaling: durable run-state that outlives the context
    window, written when the insight is fresh rather than reconstructed at PR
    time. Shape could be `fr journal add --kind improvement --target <repo>`
    (rendered into a separate section, and into the PR body the way findings
    and decisions already are), or a sanctioned `_improvements.md` per plan
    folder. The `--target` matters: these route to *other* repos, so they need
    to survive the plan being archived.

## Process (the pipeline itself)

24. **Negative claims from a read-only researcher are unreliable.** Two of four
    briefs asserted "X does not exist in the repo" and one was false
    (`longhorn-static` *does* exist, Longhorn-generated). Positive citations
    (`file:line`, here is the value) held up everywhere. A Grep-only agent can
    prove presence, never absence. **Rule: verify every negative by running it.**
25. **Silent-failure commands are the dangerous class.** Of three broken commands
    found in one operating post, the one that *errored* was harmless — you know
    instantly. The two that returned empty (`{"mirror": null}` from an
    unauthenticated call against a private repo; a 401 swallowed by `curl -sf`)
    read as "healthy" in a health check. Prefer commands that fail loudly, and
    test each one against the "what if I lack permission?" case.
26. **Orchestrator distillation re-introduces contamination.** I compressed the
    four blind briefs into the executor prompt, filtering through my own framing.
    Passing the briefs as *files* would preserve fidelity and blindness.
27. **Two executors cannot run in parallel on one worktree** — same git index.
    This serialises the pipeline; the cold-reads parallelise, the writing cannot.
28. **The cold-reader should ideally run before the orchestrator reads the draft**,
    so the orchestrator's framing cannot leak into the revision brief.
29. **A verify section can be fully evidenced and still not be a decision
    procedure.** Test: for each command, *what would I do differently depending on
    its output?* "Nothing" means it is documentation, not verification.
30. **The cold-reader is not mode-aware, and the orchestrator must be.** It reads
    `reader-arc.md`, which is prose and applies teaching-post expectations to
    every draft. The *validator* is mode-gated — its what-transfers check says
    `(expected for tutorial/explanation posts)` and never fires on `reference`.
    On `00-overview` (`diataxis: reference`) the cold-reader reported a missing
    what-transfers section as an arc failure; the orchestrator relayed it
    unfiltered; the executor added three ~90-word prose bullets to a page whose
    register is tables. **Regression, caught by the operator, not by the
    pipeline.**
    Two fixes: state the post's diataxis mode in every cold-reader brief and ask
    for mode-appropriate expectations; and treat the critique as *evidence*, not
    as a work order — the orchestrator is the only actor that knows the genre.
    Upstream: `reader-arc.md`'s ending requirement should mirror the lint's mode
    gating, or say plainly that it does not apply to `reference`.
31. **Briefs must carry the invariant rules, not just the per-post findings.**
    In the same pass, `01-introduction`'s brief said "remove Missteps rows about
    the post's drafting history — the methodology counts a wrong turn in building
    the system, not in writing the post," and `00-overview`'s brief said only
    "reframe rows as forks." Same executor, opposite outcomes: `00` gained a row
    narrating its own correction, plus session narration inside a table cell
    ("failed the build again while this row was being drafted"). Anything true
    for every post belongs in a standing preamble, not re-derived per brief.
32. **Watch for register drift when acting on a critique.** `00-overview`'s
    Missteps cells went from terse to 60–100-word paragraphs — a table in name
    only — because each critique point was answered with prose. Fixing a finding
    should not change what kind of document the page is.

---

## What the pipeline actually caught (first run, 7 posts)

Findings invisible to every existing gate, lint, and CI check:

| Class | Count | Example |
|---|---|---|
| Broken published commands | 3 | `kubectl logs -c step-*` (no glob); two more failing **silently** |
| Wrong commit citations | 7 of 8 | `ce2fcd9e` cited 3× across 2 posts, wrong each time |
| Retired components documented as live | 4 | `ai-alert-helper`, OpenRouter free tier, 2 Ollama models |
| Unsupported claims | 2 | VK Remote "Authentik SSO ingress"; a one-directional grep offered as proof of a two-directional invariant |
| Nonexistent paths | 1 | `clusters/frank/` |
| Wrong hardware | 1 | RTX 5070 → 5070 Ti (prose + diagram, 2 posts) |
| Wrong layer number | 1 | "Layer 8" → 9, corroborated 4 ways |
| Stale infrastructure | 2 | dead Zone A Pi; `CI_AUTHORITY` documented as `github`, live `gitea` |
| Structural (recap endings) | 4 of 4 | every post ended in a recap; best lesson buried mid-document |

Every one of these passed the educational gate, the AI-tells lint, the glossary
gate, the mermaid check and `hugo --minify`.
