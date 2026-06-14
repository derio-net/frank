# Vendored agent_session fixtures

Source of truth: the `agent_session` contract fixtures in
`agentic-stoa/content-factory` (private). These copies pin the **shape** the
Frank-side `agent-session` driver must emit — `{session_id, agent, status,
turn, payload}` for receive, `{session_id, agent, message, expect?,
timeout_s?}` for send.

Values are generic placeholders (no business context — technical only); only
the field set + types are load-bearing.
