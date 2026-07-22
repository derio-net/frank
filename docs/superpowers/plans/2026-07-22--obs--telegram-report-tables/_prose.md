# alert-agent Telegram report tables

**Status:** Deployed
**Layer:** obs (fix/extension of the deployed `apps/alert-agent`)
**Spec:** `docs/superpowers/specs/2026-07-22--obs--telegram-report-tables-design.md`

## Why

The Frank C&C Telegram agent's command reports are unreadable: nested
list/dict values are `json.dumps`'d to a single escaped line, over-long values
are silently truncated at 200 chars (the operator saw 3 of 10 attacker IPs cut
mid-JSON), and plain-text transport misaligns any table in Telegram's
proportional font. Reproduced live on 2026-07-21 via `/edge_traffic`.

## Approach

The fix is a **bridge mechanism**, never an agent-prompt change — the
agent-session server appends "write ONLY raw JSON" to every turn and dominates
`CLAUDE.md` (PRs #631/#633/#634 proved this). All work is in one stdlib-only
module, `apps/alert-agent/telegram-bridge/tg_bridge/bridge.py`, plus its unit
tests. It ships via a hash-suffixed ConfigMap (`alert-agent-bridge`) — editing
`bridge.py` rolls the pod, **no image rebuild**.

- **Phase 1** — `render_report`: list-of-uniform-dicts → aligned monospace
  column table (union of keys, first-seen order, missing = blank), 10-row cap +
  `+N more`, scalar lists one-per-line, nested dicts indented, scalars in a
  leading summary block, humanized section headers, and STRICT `html.escape` of
  every interpolated value (only `<pre>` tags are literal markup). Replaces
  `_dict_to_table`.
- **Phase 2** — transport: `tg_send` gains an OPTIONAL `parse_mode` (default
  `None` = today's zero-risk plain path, unchanged for narratives); a
  `_send_message` wrapper turns a 4xx into a returned error dict; a
  `_split_for_telegram` splits >4096-char reports into `(i/n)` parts on whole
  block/row boundaries with balanced `<pre>`; a `send_reply` helper owns
  HTML-vs-plain routing and a **one-shot 400→plain fallback** so a formatting
  bug can never silence the C&C channel. Rewires `deliver` and `_run_agent_turn`.
- **Phase 3** — docs: amend the frank-gotchas one-liner + topic prose for the
  changed parse_mode posture.
- **Phase 4** `[manual]` — post-deploy: confirm the pod rolled and drive a live
  report turn in the deployed pod (Frank-observed), including a value with
  `&`/`<` to exercise the escape path end-to-end.

## Testing

`uv run --with pytest python3 -m pytest tests/test_bridge.py -q` from the
`telegram-bridge/` dir (36 tests pass at baseline). TDD throughout; the live
`/edge_traffic` payload — with its ragged `country` key and a `crowdsec_bans`
scalar log-line list — is the primary fixture.

## Prior art / gotchas honoured

- Telegram HTML `parse_mode` 400s on a bare `<`/`>`/`&` and then *silently*
  never delivers — hence per-value `html.escape` plus the 400→plain fallback.
- Output shape cannot be forced via agent instructions (per-turn raw-JSON
  wrapper dominates) — the renderer is the only reliable seam.
- Verify by driving a live session turn and OBSERVING the rendered payload in
  the deployed pod, not by grepping mounted files.
