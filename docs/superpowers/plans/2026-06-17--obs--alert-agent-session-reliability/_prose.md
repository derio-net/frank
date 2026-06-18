# alert-agent session reliability — frank portion

Bridge UX + the deployment side of the continuum fix, gated by the agent-images persistence plan.

- **A (Phase 1):** the `setMyCommands` 400 — `/edge-traffic`'s hyphen is an invalid Telegram command
  id and rejects the whole menu. Rename to `/edge_traffic` and filter `set_my_commands` to valid ids
  so one bad name can never nuke the menu again.
- **D (Phase 2):** thread agent turns off the single getUpdates consumer with a per-session lock, so a
  slow/stuck turn no longer head-of-line-blocks static `/help`. One consumer per bot token preserved.
- **Phase 3 [manual, back-loaded]:** set `AGENT_TMUX_RESTORE=off` on the alert-agent + n8n-01 agent
  containers and bump both `multi-agent-shell` image SHAs to the new tag (which also unstrands n8n
  from 9635df9a). The tag only exists after the agent-images plan merges, so this is operator-driven.

Post-merge proof is a double cold-restart: the first proves liveness (no continuum dead-shell reuse) +
menu + reactions + unblocked /help; the second proves `--session-id` persistence (memory across
restarts).
