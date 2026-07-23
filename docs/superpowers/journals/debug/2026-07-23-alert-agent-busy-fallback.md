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

<!-- fr:journal kind=root-cause scope=debug id=39a1d37d72a1 created=2026-07-23T22:48:09 -->
### 39a1d37d72a1 · root-cause · SECOND root cause: --resume points at a transcript in a project dir claude will never look in

Re-login restored the credential but /digest STILL fell back. Different failure, same symptom.

Evidence — my ad-hoc 'smoke' session runs fine (claude alive, turn ok) while the Telegram session does not exist at all. They take different launch paths (agent-session::launch_command):

  transcript exists -> claude --resume <uuid>
  no transcript     -> claude --session-id <uuid>

And the two transcripts live in DIFFERENT project dirs:

  tg    -> ~/.claude/projects/-run-s6-legacy-services-agent-session-server/63abf571-....jsonl
  smoke -> ~/.claude/projects/-home-agent/1c8c4dfa-....jsonl

The tg transcript was written BEFORE the '-e PWD=HOME' fix, when claude inherited the s6
scandir as its cwd — so it sits under the scandir-encoded project dir. claude now launches
with cwd=/home/agent and resolves --resume WITHIN that project only.

Faithful probe (same tmux invocation as _create_session):
  tmux new-session -d -c /home/agent -e PWD=/home/agent -s probe-resume 'claude --resume 63abf571-... --permission-mode auto'
  -> session DEAD within 10s

Direct:
  $ cd /home/agent && claude --resume 63abf571-b929-52a5-ba8b-5353059493e6 --permission-mode auto
  No conversation found with session ID: 63abf571-b929-52a5-ba8b-5353059493e6
  EXIT=1

ROOT CAUSE: `_session_jsonl_exists` globs `~/.claude/projects/*/<uuid>.jsonl` — ACROSS ALL
project dirs — but claude's --resume is scoped to the ONE project dir derived from the launch
cwd. The predicate is broader than the behaviour it predicts, so a transcript stranded in a
stale project dir makes launch_command choose --resume, claude exits 1, the pane dies, tmux
tears the session down, wait_ready burns 30s, the turn times out, and the bridge posts the
deterministic snapshot. Permanently — nothing self-heals, every DM takes the same path.

This is a LATENT trap for any session whose transcript predates the PWD fix. The tg session
is exactly that, which is why re-login changed nothing.

Code lives in agent-images (/usr/local/bin/agent-session, baked into multi-agent-shell), NOT
frank — frank's apps/n8n-01/manifests/agent-session-driver.yaml is an older copy without this
resume logic.

<!-- fr:journal kind=finding scope=debug id=ae64fee29bef created=2026-07-23T22:54:09 state=fixed -->
### ae64fee29bef · finding [fixed] · Service restored by relocating the stranded transcript; durable fix belongs in agent-images

Remedy applied live (reversible, history preserved): copied the stranded transcript from the scandir project dir into the one the launch cwd derives —

  ~/.claude/projects/-run-s6-legacy-services-agent-session-server/63abf571-....jsonl
    -> ~/.claude/projects/-home-agent/63abf571-....jsonl

Verified end-to-end on the real production session id, twice (across an unrelated pod roll):

  agent-session send session_id=alert-agent-tg-2034763022
    -> {"status": "ok", "turn": 46, "payload": {"text": "ok"}}   (pre-roll)
    -> {"status": "ok", "turn": 47, "payload": {"text": "ok"}}   (post-roll)

turn=46 proves the 45-turn history came back — the relocation preserved the conversation
rather than discarding it. The pane rendered the real July 21 alert chatter.

Also established: `claude --session-id <uuid>` SUCCEEDS even when a transcript with that
uuid exists in a DIFFERENT project dir (probed live -> REPL ALIVE). So claude's
'Session ID already in use' guard is project-scoped too, which means the durable fix is
safe: scoping the predicate cannot strand a caller in a session-id collision.

DURABLE FIX (not in this PR — different repo): in agent-images
/usr/local/bin/agent-session, `_session_jsonl_exists` must glob the project dir derived
from the LAUNCH CWD, not `projects/*`. The predicate must use claude's own scoping rule,
since it exists solely to predict claude's behaviour.

Trigger note: today's image sweep to c7a80f6 is what ACTIVATED this. The '-e PWD=HOME' fix
corrected where NEW transcripts go but performed no migration of existing ones, so a
long-lived session's transcript became unreachable the moment the fix shipped.
