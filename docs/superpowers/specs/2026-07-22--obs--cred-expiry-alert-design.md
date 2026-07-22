# Spec — alert-agent Claude-credential expiry alert

**Status:** Draft
**Layer:** obs (fix/extension of the deployed `apps/alert-agent` — NOT a new layer)
**Date:** 2026-07-22
**Author:** Frank (fr-goal, autonomous)

## Problem

alert-agent's Claude OAuth **refresh token silently expired 2026-07-18** and the
C&C Telegram bot went dead for **3 days with no alert**: the pod stayed
`3/3 Running`, ArgoCD stayed green, and the failure (`Login expired · Please run
/login`) lived inside a tmux pane — invisible to every existing probe. The token
is a hard ~30-day clock (freshly renewed 2026-07-22 → `refreshTokenExpiresAt`
2026-08-19). We need to be warned *before* it expires, and to notice if the
warner itself dies.

## Constraints (from live scoping — do NOT relitigate)

- **Credential**: `/home/agent/.claude/.credentials.json` on PVC `alert-agent-home`
  (RWO, `apps/alert-agent/manifests/pvc.yaml:4-10`), mounted at `/home/agent`
  **only on the `agent` container** (`deployment.yaml:65`). Field
  `refreshTokenExpiresAt` (epoch-ms int); confirmed live 2026-07-22
  (`=2026-08-19`, `expiresAt=0`). Path per `agent-shells.md:567-568`.
- **RWO + no-RBAC posture** (`automountServiceAccountToken: false`,
  `deployment.yaml:22-25`) → a standalone CronJob can neither co-mount the PVC
  nor `kubectl exec`. A separate canary pod is **out**.
- The `agent` container already has everything the check needs: the PVC mount,
  the Telegram secret via `envFrom` (`FRANK_C2_TELEGRAM_BOT_TOKEN`/`CHAT_ID`,
  `deployment.yaml:62`), `tg_bridge.tg_send` on `PYTHONPATH` (`/opt/pylib`,
  `deployment.yaml:67`), and **supercronic** running `.crontab`
  (`apps/alert-agent/manifests/files/.crontab`).
- **Frank VictoriaLogs message field is `_msg`, NOT `log`.** Verified live:
  `kubernetes.namespace_name:alert-agent AND _msg:"surge-gate" | stats count()`
  → 12; the same query with `log:"…"` → 0. The Hop crowdsec rule uses `log:`
  because Hop's fluent-bit maps differently; **the Frank rule MUST use `_msg:`**.
  supercronic re-emits each cron job's stdout as its own VL line, so a `print()`
  heartbeat is queryable.

## Decisions (operator-owned, confirmed)

| Decision | Choice |
|---|---|
| Warning thresholds | **Escalating**: daily warning at `days_left ≤ 7`; wording sharpens at `≤ 3`, `≤ 1`, and `≤ 0` (expired) |
| Check cadence | **Once daily**, `0 9 * * *`, in the `agent` container's `.crontab` |
| Signal split | **Script sends the "expiring soon" Telegram warning itself**; it always emits a heartbeat line, and a **Grafana dead-man rule** pages if the heartbeat stops (checker died / pod down / container wedged) |
| Post-merge verification | **Frank triggers both signals live** and shows the operator |

## Design

### The check — `apps/alert-agent/handlers/handlers/cred_expiry.py`

A pure, unit-tested core plus a thin runner (mirrors `orchestration.run_surge`):

- **`evaluate_expiry(creds_text: str | None, now_ms: int) -> Verdict`** — pure.
  Parses the JSON, reads `refreshTokenExpiresAt` (epoch-ms), computes
  `days_left = floor((exp_ms - now_ms) / 86_400_000)`. Returns a `Verdict`:
  `{days_left: int | None, tier: str, should_warn: bool, message: str,
  heartbeat: str}`. Tiers by `days_left`: `>7 ok`, `≤7 notice`, `≤3 soon`,
  `≤1 urgent`, `≤0 expired`. `should_warn = tier != "ok"`. A missing file
  (`creds_text is None`), unparseable JSON, or absent/non-int
  `refreshTokenExpiresAt` → `tier="error"`, `days_left=None`,
  `should_warn=True` (a broken cred file is itself alarming — never a silent
  skip). `message` is **plain text with no `<`/`>`/`&`** (Telegram contact is
  plain-text; a bare `<>&` would be fine here but we keep the invariant).
  `heartbeat` is a stable single line:
  `cred-expiry-check days_left=<N|unknown> tier=<tier> refresh_expires=<iso|unknown> ts=<iso>`.
- **`run_cred_check()`** — the runner: read the cred file
  (`CRED_PATH` env, default `/home/agent/.claude/.credentials.json`; `None` on
  `FileNotFoundError`), `now_ms` from the clock, `v = evaluate_expiry(...)`,
  **always `print(v.heartbeat)`** (→ supercronic → VictoriaLogs), and
  `if v.should_warn: tg_send(v.message)` (plain text, no `parse_mode`). Defensive
  like `_deterministic_snapshot`: a `tg_send` transport error is caught + logged
  to stderr so a send failure never suppresses the heartbeat.

### Wiring

- **Bin wrapper** `apps/alert-agent/handlers/cred-expiry-check` (mirrors
  `handlers/surge-gate`): `from handlers.cred_expiry import run_cred_check;
  run_cred_check()`.
- **`.crontab`**: append `0 9 * * * /opt/alert-agent-bin/cred-expiry-check`.
- **`kustomization.yaml`**: add `cred_expiry.py` to the `alert-agent-handlers`
  configMapGenerator and `cred-expiry-check=handlers/cred-expiry-check` to
  `alert-agent-bin`. Both hash-suffixed → the edit rolls the pod (no image
  rebuild). The `.crontab` edit already rolls via its own generator.

### Grafana dead-man rule — `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

Mirror `crowdsec-canary-heartbeat-stale` (`:1743-1781`) exactly, with the Frank
field fix:

- `uid: alert-agent-cred-expiry-heartbeat-stale`
- VictoriaLogs datasource `affdoo4s9258gc`, query
  **`kubernetes.namespace_name:alert-agent AND _msg:"cred-expiry-check" | stats count() as value`**
  (`_msg`, per the constraint above).
- `relativeTimeRange.from: 108000` (30h) — the check is daily, so the window
  must exceed 24h + run/eval jitter; a missed daily run → 0 in 30h → fires.
- reduce `last` (dropNN) → threshold `lt 1`; `noDataState: OK`
  (VictoriaLogs outage = blindness, not death); `execErrState: Error`;
  `for: 2h` (a slightly-late daily run must not flap).
- `labels.telegram_direct: "true"` → routes DIRECTLY to Telegram contact
  `efi04e0201jb4f`, bypassing the LLM agent — the same reason the crowdsec
  dead-man does: the warner is down, so the agent cannot be trusted to triage its
  own outage. **Confirmed folder-independent**: `telegram_direct="true"` is a
  top-of-policy route with `continue:false` (`notification-policy-cm.yaml:57-60`),
  evaluated *before* the `grafana_folder="blog-edge"` route (`:65-68`), so it
  fires from any folder. Place the rule in the **`feature-health` folder**, new
  group `alert-agent-cred-expiry`, beside the analogous `tls-cert-expiry-1h`
  watchdog (`alert-rules-cm.yaml:1529`) — but with `telegram_direct` (pages), not
  the quieter `canary_watchdog` label the cert watchdog uses (silence is the
  enemy here).
- File-provisioned → read at boot: **restart the grafana pod after the CM change**
  (documented in the plan + Test Plan).

The dual signal is deliberate: the script's own `tg_send` is the *expiring-soon*
warning (self-contained, no dependency on VL field extraction); the Grafana rule
is the *checker-died* backstop. They fail independently.

## Test plan (unit — TDD)

`apps/alert-agent/handlers/tests/test_cred_expiry.py`:

1. `days_left` arithmetic: a token N days out → `days_left == N` (floor);
   boundary table: 8→ok, 7→notice, 3→soon, 1→urgent, 0→expired, −5→expired.
2. `should_warn` true iff `tier != "ok"`; false at 8 days.
3. wording escalates (distinct substrings at notice/soon/urgent/expired);
   message contains no `<`/`>`/`&`.
4. broken input: `None` (missing file), `"{ not json"`, `{}` (no field),
   `{"refreshTokenExpiresAt": "nope"}` → `tier="error"`, `should_warn=True`,
   `days_left is None`, safe message.
5. `heartbeat` format stable and single-line, carries `days_left=` and `tier=`.
6. `run_cred_check` wiring (monkeypatch the file read + `tg_send`): heartbeat is
   ALWAYS printed; `tg_send` called iff `should_warn`; a `tg_send` exception is
   swallowed and the heartbeat still prints.

## Post-deploy / docs

- ConfigMap-mounted → no image rebuild; ArgoCD rolls the pod on the new hash.
- **gotcha**: one-liner in `agents/rules/frank-gotchas.md` (Observability digest
  section) + prose in `docs/runbooks/frank-gotchas/obs-digest.md` — the incident,
  the dual-signal design, and the **`_msg` vs `log` VictoriaLogs-field trap**
  (Frank uses `_msg`; Hop uses `log`).
- **blog**: retroactively extend the persistent-agent / observability posts
  (`building/18-persistent-agent`, `operating/05-observability` — the alert-agent
  is documented there) with a short note on the expiry alert + the ~monthly
  re-login cadence it enforces. Fix/extension — extend the existing post, not a
  new one; confirm the exact section at implementation.
- **runbook**: no new manual op (the `obs-alert-agent-claude-login` op already
  covers re-login; this alert just makes it timely). No `/sync-runbook`.

## Acceptance

- `cred-expiry-warns-before-expiry` — when the refresh token is ≤7 days from
  expiry, the daily check sends a Telegram warning whose urgency escalates at
  ≤3/≤1/expired.
- `cred-expiry-heartbeat-deadman` — a Grafana rule pages Telegram directly if the
  daily heartbeat line stops appearing in VictoriaLogs (checker died / pod down).
- `cred-expiry-robust-on-bad-cred` — a missing / unparseable / field-less
  credential file yields a warning + an `error`-tier heartbeat, never a silent
  skip.
- `cred-expiry-live-observed` — post-merge, both signals are triggered and
  observed live (operator-shown). *(Live-only.)*

## Test Plan (post-merge — operator-driven trigger, Frank-observed)

After merge + pod roll + grafana restart:
1. `kubectl -n alert-agent rollout status deploy/alert-agent`; confirm
   `/opt/alert-agent-bin/cred-expiry-check` present in the `agent` container.
2. **Heartbeat**: run the check normally in-container; confirm the
   `cred-expiry-check days_left=… tier=ok` line prints AND appears in
   VictoriaLogs (`kubernetes.namespace_name:alert-agent AND _msg:"cred-expiry-check"`).
3. **Warning**: run the check with a forced near-expiry (`CRED_PATH` pointing at
   a temp cred with `refreshTokenExpiresAt` 2 days out) → confirm a real Telegram
   warning is delivered.
4. **Dead-man**: confirm the Grafana rule `alert-agent-cred-expiry-heartbeat-stale`
   loaded (Alerting UI) and its VictoriaLogs query returns ≥1; optionally confirm
   it goes `Pending` under a simulated stale window.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-07-22--obs--cred-expiry-alert | `derio-net/frank` | `2026-07-22--obs--cred-expiry-alert` | — |
