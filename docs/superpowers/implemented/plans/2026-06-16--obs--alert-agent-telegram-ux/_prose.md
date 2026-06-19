# Alert-Agent Telegram UX (frank portion)

Extends the live agentic alert-agent (PR #563). Two bridge threads + one back-loaded
cross-repo join. The agent-session **driver** cold-start fix (Thread A) is a separate
agent-images plan (`2026-06-16-agent-session-coldstart`) that gates only the live smoke test.

## Why these threads

The bridge currently forwards every allowlisted DM verbatim to the agent — no command layer, no
receipt feedback. Two gaps surface in real use:

- **Slash commands need to survive the argless-from-menu trap.** Telegram's command menu sends a
  command the instant it's tapped, so a parameterized command always arrives bare. We dissolve the
  trap instead of handling it: a slash command is a *prompt template* expanded into one English
  instruction for the agent (which already has `frank-facts`), carrying a "use sensible defaults"
  suffix. There is no positional arg to be missing. `/help` is the one command rendered by the
  bridge itself — it must work when the agent is cold.
- **No ack/answer feedback.** ⚡ on receipt (before the blocking turn) + 👍 on a real answer / 🤔 on
  the deterministic fallback, via `setMessageReaction`. Best-effort — a reaction failure never
  blocks the reply.

## Design boundaries

- All changes are pure functions over the existing `_http_post_json` seam, unit-tested the same way
  as the current 5 bridge tests. `poll_loop` (the network loop) stays `# pragma: no cover`; the
  only new code there is the best-effort `set_my_commands()` call.
- Poll loop stays **synchronous** (single getUpdates consumer per bot token). ⚡ fires before the
  blocking `session_send`, so receipt feedback is instant; per-update threading is deferred (YAGNI,
  single operator).
- The bridge code ships via a hash-suffixed `configMapGenerator` (kustomization at the app root), so
  an edit rolls the pod automatically once merged.

## Cross-repo sequencing

agent-images Thread A merges → CI builds a new `multi-agent-shell` tag → Phase 3 bumps
`deployment.yaml` to that SHA on this PR (the join) → operator merges → post-merge Test Plan proves
a cold DM is answered with the ⚡/👍 reactions. Phase 3 is manual/back-loaded: the tag doesn't exist
until agent-images merges, so the agentic run ships Phases 1–2 and leaves Phase 3 for the operator.
