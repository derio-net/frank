# The Frank Papers — Paper 00: Prologue

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Complete (2026-05-18 — Paper 00 published)

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete — scripts,
shortcodes, dossier gate, and `agents/skills/papers/SKILL.md` must be in place.

Paper 00 is the series prologue: *"Why Run Your Own Cluster in 2026?"* It is the
exception in the series — capped at 1500 words (vs 2400–4200 for capability
papers), no capability matrix, and no heavy vendor comparison. Its job is to
argue for the series thesis and demonstrate the voice before readers choose
whether to follow.

The paper maps three approaches (cloud, managed homelab-as-code, DIY homelab)
rather than individual vendors. The "landscape" here is philosophies, not
products. Frank's answer is explicit: Frank is a learning platform, not a
production alternative. That honesty is the hook.

## Phase 1: Dossier construction

Research the why-homelab-in-2026 landscape independently. Source material:
cost analyses of cloud vs self-hosted, academic or practitioner papers on
homelab culture, primary sources on AI inference costs at small scale, and
counter-arguments from cloud advocates. Frank artefacts from the cluster itself
(git log, cost calculations, layer-1 through layer-12 highlights).

Parallel subagents are appropriate: one per "vendor philosophy" (cloud, managed,
DIY). Merger reviews the full dossier for coverage gaps.

## Phase 2: Gate validation

Run `validate-dossier.py` and fix any gaps. Human gate: author reviews the
named gaps and counter-arguments for quality. The key counter-argument to nail:
"cloud gives instant scale and reliability — why doesn't that win for learning?"

## Phase 3: Scaffold + draft

Run scaffold if not already done. Fill all sections in order. Paper 00 has a
simplified structure (no §3 per-vendor architecture, no §4 scale benchmarks):
- TL;DR (≤150 words) — write last
- §1 The question (150–300 words) — why does anyone ask this?
- §2 Three approaches and their real costs (400–600 words)
- §3 Frank's answer, and what happened (300–500 words) — scar callout required
- §4 When Frank's answer doesn't generalize (200–400 words) + decision flowchart
- §5 What this series is (150–250 words) — the only self-referential section

## Phase 4: Media fill

Per-paper cover image: Frank at a whiteboard with "2026?" written on it,
reading glasses and tie, skeptical expression. One Mermaid flowchart for §2
(three-branch comparison of approaches). One decision flowchart for §4.

## Phase 5: Review + publish

Voice pass, TL;DR, dossier-link check. Set draft: false. This paper's publish
triggers Phase 1 of the broader series — log the publish date.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update the Papers section _index.md
stub, update the Building/Operating series overviews, update README, set plan
status to Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
