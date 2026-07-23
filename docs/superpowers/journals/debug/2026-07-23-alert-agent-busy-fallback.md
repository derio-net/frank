# Journal: 2026-07-23-alert-agent-busy-fallback

<!-- fr:journal kind=repro scope=debug id=7df9a6538c60 created=2026-07-23T22:27:08 -->
### 7df9a6538c60 · repro · C&C bot answers every DM with 'agent busy — deterministic snapshot'

Live on alert-agent-54cf5cb9-cxqb4 (mini-3, 3/3 Running, image c7a80f6).

Observed chain:
- telegram-bridge log: `WARN telegram-bridge: session_send failed: timed out` (20:13:21Z)
- agent log: `agent-session: session alert-agent-tg-2034763022 not ready after 30.0s; proceeding`
- `ps -eo pid,args` in the agent container: agent-session server is up, but there is NO tmux server and NO claude process at all.
- `tmux ls` -> `no server running on /tmp/tmux-1000/default`

So every DM: agent-session creates the tmux session, the claude pane dies instantly, tmux exits with its last pane, the readiness poll burns 30s, the turn times out, and bridge.py:_deterministic_snapshot() posts the frank-facts fallback (bridge.py:568).

<!-- fr:journal kind=ruled-out scope=debug id=8e2f444c9c70 created=2026-07-23T22:27:26 -->
### 8e2f444c9c70 · ruled-out · NOT the ~30-day refresh-token expiry the cred-expiry guard watches

The obvious hypothesis (token aged out, as on 2026-07-18) is REFUTED by the credential itself:

    refreshTokenExpiresAt = 1787107246868 = 2026-08-19T02:40:46Z  (26 days out)

The clock is fine. The guard is correctly silent about the clock. Something else killed the credential.

<!-- fr:journal kind=root-cause scope=debug id=e99c0f484b27 created=2026-07-23T22:27:27 -->
### e99c0f484b27 · root-cause · Tokens are BLANK while the expiry clock still reads healthy — the guard checks the clock, not the token

`/home/agent/.claude/.credentials.json` (281 bytes, mtime Jul 22 08:00) parses to:

    accessToken      type=str  len=0    <- empty string
    refreshToken     type=str  len=0    <- empty string
    expiresAt        0
    refreshTokenExpiresAt  2026-08-19   <- still 26 days out

claude therefore cannot authenticate at all. Proven directly in the container:

    $ claude -p 'reply with the single word OK'
    Failed to authenticate: OAuth session expired and could not be refreshed

That is why the pane dies instantly and every turn times out.

The guard is blind to this. Run live against the real broken file:

    TIER= ok  WARN= False
    cred-expiry-check days_left=26 tier=ok refresh_expires=2026-08-19T02:40:46+00:00

ROOT CAUSE: `handlers/cred_expiry.py::evaluate_expiry` validates ONLY the
`refreshTokenExpiresAt` clock field. It never asserts that a usable token is
actually present. A credential whose tokens have been blanked (claude clears them
when a refresh fails with invalid_grant, leaving the metadata intact) reads as
perfectly healthy, so neither the Telegram warning nor the Grafana dead-man rule
fires — the heartbeat keeps printing tier=ok.

Aggravating: the unit fixture `_creds()` in tests/test_cred_expiry.py:16-18
literally builds `"refreshToken": ""` and asserts tier=ok — the exact live-broken
shape is encoded in the suite as the definition of healthy.

<!-- fr:journal kind=finding scope=debug id=a9d954c1c94a created=2026-07-23T22:31:49 state=fixed -->
### a9d954c1c94a · finding [fixed] · cred-expiry check now asserts a token EXISTS, not just that its clock is future-dated

Source: apps/alert-agent/handlers/handlers/cred_expiry.py
- new `_refresh_token_usable(oauth)` — refreshToken must be a non-empty string
- `evaluate_expiry` returns error tier (reason=blank-token) BEFORE any clock arithmetic when the nested `claudeAiOauth` blob is present and its token is blank/missing/non-string
- new `_error_verdict(now_ms, reason)` — single constructor, de-duplicates the 3rd copy of the error-Verdict literal; heartbeat gains a stable `reason=<slug>` token (the Grafana dead-man rule matches only the literal 'cred-expiry-check', so this is additive)
- the blank-token Telegram message deliberately does NOT mention days remaining — quoting a healthy clock is exactly what made the failure invisible
- the top-level defensive shape stays clock-only: we have never seen it live and cannot name its token field

Tests: apps/alert-agent/handlers/tests/test_cred_expiry.py
- FIXTURE BUG FIXED: `_creds()` hard-coded `"refreshToken": ""` — the live-broken shape — and asserted tier=ok. It now defaults to a non-empty token, with the blank shape opt-in.
- 10 new failing-first tests: blank/whitespace/missing token, non-string tokens, message wording, heartbeat shape, healthy-still-ok, flat-shape-unchanged.
- RED 10 failed/34 passed -> GREEN 62 passed (full handlers suite).

LIVE PROOF against the real broken credential in alert-agent-54cf5cb9-cxqb4:
  shipped code: TIER= ok    WARN= False   days_left=26 tier=ok
  fixed code:   TIER= error WARN= True    tier=error reason=blank-token

NOT fixed here (follow-up): the image's login MOTD prints '✓ claude (~/.claude/.credentials.json, age 1d)' from file PRESENCE alone — same blindness, but it lives in the agent-images repo.

<!-- fr:journal kind=finding scope=debug id=f1abaf42efe9 created=2026-07-23T22:43:00 state=fixed -->
### f1abaf42efe9 · finding [fixed] · Live verification complete — fix proven on BOTH real credential states

Operator re-logged in (manual op obs-alert-agent-claude-login); clock reset to 2026-08-21 (28 days).

Service restored — a real agent turn completes:

    agent-session send -> {"status": "ok", "turn": 1, "payload": {"text": "ok"}, "started": true}

Full truth table against LIVE credentials (not fixtures):

    state                     shipped code        fixed code
    blank tokens (broken)     tier=ok  WARN=False tier=error WARN=True reason=blank-token
    fresh login (healthy)     tier=ok  WARN=False tier=ok    WARN=False

So the fix flags the real failure and does NOT false-positive on the real healthy
credential. Heartbeat re-seeded to VictoriaLogs via the /proc/1/fd/1 redirect; the
dead-man rule's window is fed.
