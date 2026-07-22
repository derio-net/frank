# alert-agent credential-expiry alert

**Status:** Deployed
**Layer:** obs (fix/extension of the deployed `apps/alert-agent`)
**Spec:** `docs/superpowers/specs/2026-07-22--obs--cred-expiry-alert-design.md`

## Why

alert-agent's Claude OAuth refresh token silently expired 2026-07-18; the C&C
Telegram bot went dead 3 days with no alert (pod `3/3 Running`, ArgoCD green —
the failure lived in a tmux pane). The token is a hard ~30-day clock. This adds a
proactive warning + a dead-man's switch so the next expiry never goes unnoticed.

## Approach

The `agent` container already has everything the check needs — the credential PVC
mounted, the Telegram secret, `tg_bridge.tg_send` on PYTHONPATH, and supercronic
running `.crontab` — and a standalone canary pod is impossible (RWO PVC + no-RBAC
posture). So the check is a **daily cron entry in that container**:

- **Phase 1** — `handlers/cred_expiry.py`: a pure, unit-tested
  `evaluate_expiry(creds_text, now_ms)` (days_left → tier → escalating plain-text
  message + stable heartbeat line) plus a thin `run_cred_check()` runner that
  ALWAYS prints the heartbeat and sends a Telegram warning when `days_left ≤ 7`
  (escalating at ≤3/≤1/expired). Broken/missing cred → an `error`-tier warning,
  never a silent skip.
- **Phase 2** — wiring: `cred-expiry-check` bin wrapper, `0 9 * * *` crontab
  entry, `kustomization.yaml` configMapGenerator additions (hash-suffixed → rolls
  the pod, no image rebuild).
- **Phase 3** — a Grafana file-provisioned **dead-man rule**
  (`alert-agent-cred-expiry-heartbeat-stale`, `feature-health` folder) that pages
  Telegram directly (`telegram_direct: "true"`) if the daily heartbeat stops in
  VictoriaLogs. **Uses `_msg:` not `log:`** — Frank's VL message field
  (verified live; the Hop crowdsec rule's `log:` returns 0 on Frank). A guard test
  pins the field + noDataState + window so the trap can't regress.
- **Phase 4** — gotcha one-liner + obs-digest prose + a retroactive note in the
  persistent-agent/observability blog posts.
- **Phase 5** `[manual]` — post-deploy: roll, restart grafana (file-provisioned
  rules read at boot), then trigger and observe all three signals live.

The two signals fail independently: the script's own `tg_send` is the
expiring-soon warning; the Grafana rule is the checker-died backstop.

## Testing

`uv run --with pytest python3 -m pytest tests/ -q` from
`apps/alert-agent/handlers/` (TDD, pure-core first). Plus a stdlib+yaml guard test
for the Grafana rule (`scripts/tests/test_cred_expiry_alert_rule.py`) pinning the
`_msg` field, `noDataState: OK`, `telegram_direct`, and the >24h window.

## Gotchas honoured

- Grafana Telegram contact is plain-text → keep `<>&` out of the warning.
- File-provisioned rules read at boot → restart the grafana pod after the CM edit.
- Dead-man `noDataState: OK` → a VictoriaLogs outage is blindness, not death.
- Frank VL message field is `_msg`, NOT `log` (Hop differs).
