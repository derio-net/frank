# Hermes Context-Window Survival — Rework 1: the brain transplant

**Parent:** `docs/superpowers/implemented/plans/2026-06-06--orch--hermes-context-survival/`
**Spec:** `docs/superpowers/specs/2026-06-06--orch--hermes-context-survival-design.md` (Addendum section)
**Status:** In progress

The parent plan's Test Plan replay did its job: the *infrastructure* all
verified (0 truncations, 64k @100% GPU, fetch-text live), and the replay
surfaced two findings the design hadn't anticipated:

1. **Hermes hard-requires ≥64k context** — its preamble alone is ~15k tokens;
   with truthful budgets it refuses every 16k model. `gemma-12b-64k` became
   the only local model hermes accepts…
2. **…and gemma4-12B can't drive hermes's agentic loop** — invalid tool-call
   names, a 90-iteration degenerate loop on `hostname` (confabulated answer
   with the real one in hand), tool-skipping confabulation with thinking on.

Candidate measurements (2026-06-06): qwen3:14b **clamps to 40,960** (derived
num_ctx silently caps at the trained ceiling — below the floor);
mistral-small3.2:24b honors 65536 but balloons to **33 GB / 15 t/s** (dense
KV); **qwen3.6:35b-a3b honors 65536 at 24 GB, 39/61 hybrid, 61 t/s
generation, 1,792 t/s long-prefill** (14k tokens in 7.8 s — hermes preamble
≈8 s cold, then prefix-cached). MoE 3B-active makes hybrid cheap; it's also
the strongest tool-calling family in the lineup.

- **Phase 1 (agentic):** declarative `qwen3.6:35b-a3b-64k` + alias pair
  `qwen36-a3b-64k`/`-nothin`; codify the parent's live deviations (SOUL
  wording, loop guard) and the new gotchas (floor, clamp, gate failure) in
  runbook + spec addendum.
- **Phase 2 (manual):** post-merge verify, hermes budget entries for the new
  pair, then the **agentic gate test** — the exact probes gemma4 failed
  (fetch+summarize with recall, trivial-command loop check). Default flips to
  `qwen36-a3b-64k` only on a pass; a fail documents the BYOK-frontier posture
  honestly. gemma-12b-64k-nothin stays as the fast chat/vision option either
  way.
