# Spec — alert-agent Telegram report formatting (monospace tables)

**Status:** Draft
**Layer:** obs (fix/extension of the deployed `apps/alert-agent` — NOT a new layer)
**Date:** 2026-07-22
**Author:** Frank (fr-goal, autonomous)

## Problem

The Frank C&C Telegram agent's command reports are unreadable. `_dict_to_table`
in `apps/alert-agent/telegram-bridge/tg_bridge/bridge.py:163-180` renders
structured agent payloads badly. Reproduced live (deployed pod, `/edge_traffic`,
2026-07-21) — the literal text Telegram received:

```
top_attacker_ips   [{"ip":"52.152.150.151","count":266,"org":"Microsoft Corporation","banned":false},{"ip":...
crowdsec_bans      ["time=\"2026-07-21T21:00:36Z\" level=info msg=\"...\""]
```

Three separable defects:

1. **Nested list/dict values are `json.dumps`'d to one line** (`bridge.py:174-177`).
   A list-of-uniform-dicts *is* a table but renders as escaped JSON on one row.
2. **200-char truncation silently destroys data** (`bridge.py:176`). No `+N more`
   marker; the operator saw 3 of 10 attacker IPs, cut mid-JSON.
3. **Plain-text transport misaligns columns** (`bridge.py:4-5,54-56`). `tg_send`
   sends with no `parse_mode`, so even a perfectly padded table drifts in
   Telegram's proportional font (worst on mobile).

## Hard constraints (prior art — do NOT relitigate)

- **The fix is a bridge mechanism, never an agent-prompt change.** The
  agent-session server appends "write ONLY the JSON result to the file — raw
  JSON" to *every* turn, which dominates `CLAUDE.md`/`SKILL.md`. PRs #631/#633/#634
  proved output shape cannot be forced via instructions. `render_payload` /
  `_dict_to_table` own presentation.
- **`{"text": "..."}` preferred-shape passthrough stays unchanged.** A payload
  (dict or JSON-string) with a string `text` field returns that text verbatim —
  narratives are already prose and must not be tabled.
- **HTML parse_mode 400s on a bare `<`, `>`, or `&`** and the message then
  *silently never delivers* (frank-gotcha, `grafana.md` / obs). Any HTML we emit
  must strict-escape every interpolated value.

## Decisions (operator-owned, already made)

| Decision | Choice |
|---|---|
| Render style for structured payloads | **Monospace tables via `parse_mode=HTML` + `<pre>` blocks** |
| Row cap per table | **10 rows, then a `+N more` footer** |
| Message > 4096 chars | **Split into numbered messages `(1/3)`, `(2/3)`, …** |
| Post-merge verification | **I (Frank) drive a live turn in the deployed pod and show the operator the rendered output** |

## Design

### Rendering model — `render_report(payload: dict) -> str`

A new pure function replaces the body of `_dict_to_table`. Input is the agent's
domain dict; output is a single HTML string (may contain multiple `<pre>` blocks
and section headers). Per top-level key:

- **list of dicts (uniform-ish)** → an aligned column table inside one `<pre>`:
  - Columns = **union of keys across rows**, in **first-seen order** (stable;
    a key appearing only in a later row is appended). Missing key → blank cell.
  - Header row = column names (upper-cased), a rule line, then data rows.
  - Cells left-aligned; numeric-looking columns right-aligned for scan-ability.
  - Cap at **10 data rows**; if more, append a `+N more` line inside the `<pre>`.
  - Column width = max cell width in that column (post-cap), so `+N more` rows
    don't widen the table.
- **list of scalars** → one item per line inside a `<pre>` (e.g. `crowdsec_bans`
  log lines). Capped at 10 + `+N more`.
- **empty list** → the row renders `key   (none)` — no empty `<pre>`.
- **nested dict** → an indented `key: value` sub-block inside a `<pre>`
  (one level; deeper nesting compacts to single-line JSON as a leaf).
- **scalar** (str/int/bool/None) → a `key  value` line, grouped with other
  top-level scalars into a single leading `<pre>` "summary" block.

Section header for each non-scalar key: the key humanized (`top_attacker_ips`
→ `Top attacker ips`) on its own line above its `<pre>`. Scalars need no header.

`<pre>` blocks are the only HTML; **all cell/section content is HTML-escaped**
(`html.escape` on `&`, `<`, `>`) before interpolation. The `<pre>...</pre>` tags
themselves are the sole unescaped markup.

### Transport — opt-in HTML, plain-text fallback

- `tg_send(text, chat_id=None, parse_mode=None)` gains an **optional**
  `parse_mode`. Default `None` keeps today's zero-risk plain-text path — so every
  existing narrative/`/help`/fallback caller is unchanged (dodges the HTML-400
  gotcha exactly as before). Only the report renderer opts into `"HTML"`.
- **4096-char splitting** (`_split_for_telegram`): split into ≤4096-char parts on
  **whole-block boundaries** (never mid `<pre>`). Each part independently
  opens/closes its own `<pre>` where needed so no part ships an unclosed tag.
  A single `<pre>` block that alone exceeds 4096 is split on **whole rows**, each
  fragment re-wrapped in `<pre>...</pre>`. Multi-part messages get a `(i/n)`
  prefix line (outside the `<pre>`). One part → no prefix.
- **Per-message 400 fallback:** `tg_send_html(html, plain, chat_id)` posts HTML;
  if `sendMessage` returns HTTP 400 (or a Telegram `ok:false`), it retries **once**
  with `parse_mode=None` and the **plain-text rendering of the same content**
  (the `<pre>`/escaping stripped). A formatting bug can therefore never silence a
  C&C report — the non-negotiable safety property. The plain-text rendering is
  the same table minus HTML (still row-capped, still `+N more`).

### `render_payload` wiring

`render_payload` still returns a **string** (its callers — `deliver`,
`process_update` — post via `tg_send`). It gains an internal signal that the
string is HTML so the caller opts into `parse_mode=HTML`. Concretely:

- Preferred `{"text": str}` → return the string, plain (no HTML) — unchanged.
- Bare string / non-dict JSON → unchanged (plain).
- Text-less dict → `render_report(dict)` (HTML). Callers detect "this came from a
  report" and route through the HTML+split+fallback sender.

Wiring seam: both reply sites — `deliver()` (cron, static `fallback_text`) and
`_run_agent_turn()` (DM, `_deterministic_snapshot()` fallback) — route through a
single new `send_reply(resp, chat_id, fallback)` helper, where `fallback` is a
str **or** a zero-arg callable (generalized so the DM path keeps its lazy
deterministic snapshot). The helper decides HTML-vs-plain, applies splitting, and
owns the 400 fallback. HTML-ness is signalled by the presence of a `<pre>` block
in the rendered string — the only producer of `<pre>` is `render_report`, and all
values are escaped, so no cell can forge one.

**400 seam:** `_http_post_json` raises `urllib.error.HTTPError` on 4xx (it wraps
`urlopen`), which today propagates. `tg_send` routes `sendMessage` through a
`_send_message(params)` wrapper that catches `HTTPError` and returns the parsed
error body (`{"ok": False, "error_code": 400, ...}`) instead of raising — so a
real 400 and a test's canned `{"ok": False, "error_code": 400}` look identical,
and the HTML sender can detect failure and retry plain. `_http_post_json` stays
the one patchable HTTP seam; tests assert on recorded `sendMessage` params
(`parse_mode`, `text`) and simulate a 400 by canning an error response.

## Test plan (unit — TDD, extends `telegram-bridge/tests/test_bridge.py`)

Fixture: the captured live `/edge_traffic` payload
(`top_scanned_paths`, `top_attacker_ips` with a ragged key set — one row has
`country`, others don't — and `crowdsec_bans` as a scalar log-line list).

1. list-of-dicts → aligned table: header row present, one line per row, columns
   union incl. `country`, missing `country` cell blank, NOT raw JSON.
2. ragged keys → `country` column appears once, ordered after first-seen keys.
3. row cap: an 11-row list renders 10 rows + a `+N more` footer, no mid-value cut.
4. scalar list (`crowdsec_bans`) → one line per entry, escaped, capped.
5. HTML-escape: a value containing `<`, `>`, `&` is escaped in output; the only
   literal `<`/`>` are the `<pre>` tags.
6. `{"text": "prose"}` still returns prose plain, no `<pre>`, no `parse_mode`.
7. bare-string / list-JSON payloads unchanged (plain).
8. 4096 split: a payload forcing >4096 chars yields ≥2 `sendMessage` calls, each
   ≤4096, each with balanced `<pre>` tags, `(i/n)` prefixes present.
9. **400 fallback:** canned 400 on the first HTML `sendMessage` → exactly one
   retry with `parse_mode` absent and a plain (no-`<pre>`) body carrying the data.
10. `tg_send` with no `parse_mode` arg still omits `parse_mode` (existing
    `test_outbound_sender_posts_to_configured_chat` must still pass).

## Post-deploy / docs

- ConfigMap-mounted (`kustomization.yaml` → `alert-agent-bridge`), hash-suffixed
  → editing `bridge.py` rolls the pod, **no image rebuild**. `prune: true` already
  on the Application.
- **frank-gotchas update (parse_mode posture changed):** the existing one-liner
  says Telegram is plain-text-only to dodge HTML-400. Amend to: reports now opt
  into `parse_mode=HTML` with strict per-value escaping **and a plain-text 400
  fallback**; narratives stay plain. One-liner in `agents/rules/frank-gotchas.md`
  (grafana/obs section) + full prose in the matching
  `docs/runbooks/frank-gotchas/` topic file.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-07-22--obs--telegram-report-tables | `derio-net/frank` | `2026-07-22--obs--telegram-report-tables` | — |

## Acceptance

- `report-tables-list-of-dicts` — a list-of-uniform-dicts payload renders as an
  aligned monospace column table in Telegram, not escaped one-line JSON.
- `report-tables-no-silent-truncation` — over-cap lists show `+N more`; no value
  is ever cut mid-character/mid-JSON.
- `report-tables-html-escape-safe` — values with `< > &` deliver (never a silent
  HTML-400); proven by unit test + the 400→plain fallback path.
- `report-tables-live-observed` — a live command turn in the deployed pod renders
  a real table (operator-observed, post-merge). *(Live-only; unit tests can't
  prove the deployed ConfigMap rolled.)*

## Test Plan (post-merge, operator-driven trigger / Frank-observed)

After merge + pod roll:
1. `kubectl -n alert-agent rollout status deploy/alert-agent` — new ConfigMap hash live.
2. Drive each report command through the **deployed** bridge and capture the
   rendered `sendMessage` body (exec the `telegram-bridge` container,
   `render_report(session_send(expand_command(cmd)))`): `/edge_traffic`,
   `/security`, `/digest`, `/status`.
3. Confirm: aligned columns, `+N more` where capped, no raw JSON, balanced
   `<pre>`, multi-part `(i/n)` only when >4096.
4. Send one real value containing `&`/`<` (e.g. a UA string) and confirm delivery
   (no silent drop) — exercises the escape path end-to-end.
