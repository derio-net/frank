# Debugging: alert-agent STILL leaks raw JSON after #633 — the mechanical fix

**Date:** 2026-07-13 · **Layer:** obs · **Branch:** fix/alert-agent-render-dict-table
**Follows:** #633 (which restored the `{"text":…}` envelope *instruction*) — insufficient.

## Symptom & reproduction

After #633 merged and rolled, a **live session probe** (POST to the in-pod
agent-session server, observing the actual payload — the step #631/#633 skipped)
showed the agent STILL wrote a rich object with **no `text` field**:

```
STATUS: ok | HAS_TEXT_KEY: False
{"gpu_mode": "unknown…", "firing_alerts": "none…", "edge_traffic": "3813 reqs…"}
```

`render_payload` `json.dumps`es that → raw JSON to Telegram. The turn itself was
fast and correct (≤2 probes, no timeout, no Hacker News — #633's latency/de-HN
parts work); only the JSON *presentation* was still broken.

## Root cause (architecture, not another prompt)

Two instruction-layer attempts failed: #631 removed the `{"text":…}` envelope,
#633 restored it. Neither binds, because the **agent-session server appends
`"write ONLY the JSON result to the file — raw JSON"` to every turn**, and that
per-turn wrapper dominates the ambient `CLAUDE.md`. The model writes a
domain-shaped JSON, not `{"text":…}`, no matter what the instructions say.

Confirmed hard-stop signal (systematic-debugging Phase 4 step 5): repeated fixes
at the same layer failing → the layer is wrong. **The bridge must own
presentation** — a mechanism the agent's per-turn wrapper cannot override.

## Fix

`render_payload` renders **any** dict payload as a compact plain-text `key  value`
table (`_dict_to_table`), instead of `json.dumps`:

- `{"text": "<table>"}` → return `text` (preferred; agent-composed table).
- any other dict → aligned `key  value` rows; nested values compacted to a
  single-line JSON so each top-level key stays one row.
- non-dict JSON (list/number) / bare string → unchanged.

**Verified against the REAL leaked payload** (not a synthetic test): the exact
`{"gpu_mode":…, "firing_alerts":…, "edge_traffic":…}` object now renders as a
3-row aligned table, `is_raw_json=False`. SKILL.md updated to say a flat
`label→value` object is fine (the bridge tables it) — deep nesting still
compacts, so keep it flat.

Tests: 4 new `render_payload` table cases; the two old tests that asserted
"leave the textless dict raw" (the bug behaviour) updated. bridge 36 · handlers
15 · frank-facts 13 green.

## Rejected approach

*A third instruction tweak* (e.g. a louder "you MUST use text"). Rejected: the
live probe proved the session wrapper wins; a mechanism is the only reliable
layer. This is the "in-pod instruction presence ≠ correct output" lesson,
enforced by observing the actual payload this time.
