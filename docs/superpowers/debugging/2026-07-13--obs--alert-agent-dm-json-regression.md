# Debugging: alert-agent replies as raw JSON + never answers slow DMs

**Date:** 2026-07-13 · **Layer:** obs · **Branch:** fix/alert-agent-dm-json-regression
**Regression of:** #631 (frank-alert-triage skill + alert-agent report fixes)

## Symptom & reproduction

During #631's post-merge Test Plan, the operator DM'd `@agent_zero_cc_bot`:
`/status`, `/digest`, `/surge`, `/edge_traffic`. Result:
1. ~10 min of no reply, then
2. all four came back as **raw structured JSON blobs**, not the intended compact
   plain-text tables.

Repro: DM any command to the bot on the #631-deployed pod; observe raw JSON
(and, for a command that makes the model investigate, a multi-minute wait).

## Evidence

- **Live tmux pane** of the per-chat session (`claude --resume 63abf571…`, elapsed
  12 min): `● Surge-compute shows a Major tier. Let me get attacker IPs… ● Running
  3 shell commands… ✢ Hyperspacing (47s · thinking)` — the turn was probe-sweeping
  (surge-compute → attacker-IP `ipinfo.io` curls), not hung.
- **agent-session server** `/usr/local/bin/agent-session` (image-level, multi-agent-shell):
  - line ~367: appends `"[agent-session] When done, write ONLY the JSON result to
    the file <path> — raw JSON, overwrite it, nothing else."` to every turn.
  - line ~380: `payload = json.load(fh)` — the file's JSON **is** the payload the
    bridge receives.
- **`bridge.render_payload`**: a dict payload without a `text` key →
  `json.dumps(payload)` → the raw JSON is what gets posted.
- **`bridge._run_agent_turn`**: `DM_TIMEOUT_S=600`; `session_send` is not wrapped,
  and on timeout/empty it posts only `"(the agent did not return a reply…)"`.

## Root cause

**Two independent causes, both confirmed:**

1. **JSON leak (regression #631 introduced).** The agent↔session-server contract is
   *file-based JSON*: the agent MUST write a JSON object whose `text` field carries the
   message, and `render_payload` extracts `.text`. #631 wrongly "fixed the JSON reply"
   by *removing* the `{"text": …}` envelope from `SKILL.md` and the `orchestration.py`
   cron prompts (told the agent "plain text, no JSON"). But the session wrapper still
   mandates "write raw JSON result". Conflicted, the agent writes a *rich* JSON object
   with no `text` key → `render_payload` re-serializes it → **raw JSON to Telegram**.
   The `{"text": …}` envelope was never the bug; it is the load-bearing transport. The
   real fix is "the compact table lives *inside* `text`", not "drop the envelope".

2. **Slow turn + no mechanical backstop (pre-existing).** #631's "≤2 probes, answer
   now" is a *soft prompt nudge*; the bridge spawns `claude --resume`, whose restored
   transcript carries deep-dive momentum that overrides the freshly-loaded CLAUDE.md.
   And `_run_agent_turn` has no deterministic fallback (unlike the cron `deliver()`),
   so an over-investigating turn yields only a useless 10-min `"(no reply)"` — or, if
   the HTTP call raises on timeout, a silently-dead worker thread and nothing at all.

## Fix

1. **Restore the `{"text": "<compact plain-text table>"}` contract** in
   `apps/alert-agent/manifests/files/SKILL.md` and the `run_surge`/`run_digest`
   prompts (`orchestration.py`) — the table goes inside `text`. Kept #631's
   de-Hacker-News/evidence-driven phrasing (proven correct live: the surge reply
   attributed "Chrome/120 stale UA… crawler", no Hacker News) and the
   `render_payload` `{"text":…}`-string unwrap (still valid belt-and-braces).
2. **Mechanical DM backstop** in `bridge.py`: `DM_TIMEOUT_S` 600→150; wrap
   `session_send` so a transport error never kills the turn; on timeout/empty/error
   post `_deterministic_snapshot()` — a `python3 -m frank_facts.cli surge-compute`
   verdict (verified live: `tier=Notable current=58 baseline=9 x6.44`) — instead of
   the bare "(no reply)".

**Failing tests pinning it:** `test_orchestration.py` envelope asserts flipped
(`{"text"` MUST be present, `"Hacker News"` MUST NOT); `test_bridge.py`
`test_dm_timeout_posts_deterministic_fallback`, `test_dm_session_exception_does_not_kill_turn`,
`test_dm_success_still_posts_agent_text`. Full suite: bridge 33 · handlers 15 · frank-facts 13.

## Rejected hypotheses

- *"The bridge is dead / not polling"* — ruled out: `python3 telegram-bridge` is pid 1;
  empty logs are Python block-buffering, not a dead process.
- *"The claude session hung / crashed / OOM"* — ruled out: the pane showed it actively
  running tool calls; `claude` pid alive, RSS ~500 MB, 0 container restarts.
- *"Cold-start / auth failure"* — ruled out: `native-claude 2.1.207 already installed`,
  `.credentials.json` present, the turn was executing.
- *"Only the DM path is affected"* — ruled out: the cron digest/surge prompts share the
  same `session_send` file-result contract and were broken identically; fixed both.

## Lesson

In-pod instruction *presence* ≠ correct *output*. #631's unit tests fed
`render_payload` a `{"text":…}` dict directly and never exercised the real
agent↔session-server contract; the deploy was called "verified" from the mounted
instructions, not observed output. Only the live DM caught it — exactly the
"test workflows before declaring Deployed" rule. This fix's acceptance is
gated on a live DM, not a green unit run.
