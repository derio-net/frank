# Blog Quality Gate — turning on the educational-writing gate

blog-craft ships a structural gate for teaching posts and frank has it vendored
but unwired: `quality.enabled` is unset, so the CI step is never rendered. The
validator exists and gates nothing. This plan turns it on.

## The part that is easy to get wrong

The obvious sequence — run the validator, fix what it names, flip the flag —
would have produced a large amount of damaging work.

At blog-craft v0.18.0 the gate reported **39 findings across 34 posts**, 34 of
them "no actionable section". But most of those posts already had one:
blog-craft's `_ACTIONABLE` pattern anchored its verbs as `\bverify\b` and
`\brecover\b`, and a word boundary cannot match an inflected form. So the check
that asks *"is there a heading a reader under pressure can follow?"* was
rejecting `## Verifying the Bootstrap`, `## Recovery Path` and `## The Smoke
Test`.

Fixed upstream (blog-craft#70, v0.18.1) and resynced (frank#731). The same
measurement afterwards: **15 findings across 11 posts**. Twenty-three of the
thirty-four were never failing. Nothing in that reduction touched a post.

Had the gate been believed, the work would have been renaming `## Recovery Path`
to `## Recover` across two dozen posts — mutilating good writing to satisfy a
regex, and calling it a quality improvement.

**So the standing instruction for this plan: when a gate reports a large
backlog, check the gate before working the backlog.**

## What is actually left

Eleven posts. Ten need a genuine actionable section, two of those also lack any
command/output block, two need a diagram, one has an invalid Diátaxis mode, and
one trips the ai-vocabulary lint on "seamless".

## The constraint that shapes every phase

`_has_actionable_heading` is a regex over heading text. Any H2 containing
`verify`, `runbook`, `steps`, `recover` and friends satisfies it — **including
one with nothing underneath**. A green run therefore proves nothing about
whether a reader can act.

Every section this plan adds must carry real commands that were actually run,
with their real output. Where a post has no operational surface (06-fun-stuff /
OpenRGB is the likely case), `quality_exempt: <reason>` is the honest answer and
is explicitly allowed — a hollow section is worse than a declared exemption,
because the exemption is visible and the hollow section looks like coverage.

Phase 6 adds a mechanical floor: a tripwire requiring a fenced command block
under every actionable heading. It cannot judge whether a section is *good*, but
it makes an empty one fail — and, like the toolchain guard it mirrors, it
carries a self-test proving the detector can actually fire.

## Ordering

The gate runs over the whole corpus, not the changed files. Flipping
`quality.enabled` before the backlog clears turns `main` red on every unrelated
PR. So the flip is Phase 6 and every earlier phase leaves `main` green — each
phase is independently mergeable and independently useless-to-revert.

## Evidence gathering

Ten posts need commands that genuinely work. Use `blog-craft:post-researcher`
per post to gather file:line-cited evidence, run the candidates, and paste real
output. Where an operating companion post already owns the runbook, link it
rather than duplicating it — two copies of a runbook drift, and the drift
surfaces during an incident.
