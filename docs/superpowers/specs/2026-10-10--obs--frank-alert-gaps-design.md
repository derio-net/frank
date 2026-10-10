# Frank alerting gaps — Telegram parse_mode, cred-expiry cadence, PVC capacity

**Issues:** derio-net/frank#799, derio-net/frank#746, derio-net/frank#722 (batch `frank-alert-gaps`, one PR)
**Layer:** obs
**Branch:** `feat/batch-frank-alert-gaps`

## Context

Three blind spots, all in Grafana alerting:

1. **#799: the repo contradicts itself on Telegram `parse_mode`.** `apps/grafana-alerting/manifests/contact-points-cm.yaml:19` says
   "parse_mode intentionally unset → plain text". The `layer-1-nic-link-flap` comment in
   `alert-rules-cm.yaml` and the `frank-gotchas.md` Grafana entry both say HTML. **The upstream source settles it.**
   `grafana/alerting` `receivers/telegram/v1/config.go:84-86` reads:
   `// if field is missing, then we fall back to the previous default: HTML` / `if settings.ParseMode == "" { settings.ParseMode = DefaultTelegramParseMode }`,
   with `DefaultTelegramParseMode = "HTML"`. `"None"` maps to `""`, and `telegram.go:131` then omits `parse_mode`
   from the Bot API call, so Telegram falls back to plain text. Frank runs `grafana/grafana:12.3.3` (verified on the live pod).
   So claim A is false: the contact point sends HTML. The seven Telegram-routed rules that carry bare `<`/`>`/`&`
   (`exercise-reminder-stale`, `session-manager-stale`, `audit-digest-stale`,
   `layer-1-node-memory-headroom`, `tls-cert-expiring-14d`, `tls-cert-expiring-7d`,
   `headscale-api-key-expiry-warning`) can each be rejected with a 400, and the failure is silent.
2. **#746: the cred-expiry dead-man false-pages on one missed run.** `alert-agent-cred-expiry-heartbeat-stale`
   (`alert-rules-cm.yaml`, group `alert-agent-cred-expiry`) has a 30h window (`from: 108000`) and `for: 2h`, while the heartbeat
   arrives once a day (`0 9 * * *`). One missed run makes a 48h gap, which pages. **Discovery:** the issue assumed
   the crontab was built into the agent-images image. It is not any more. It is `apps/alert-agent/manifests/files/.crontab`, shipped by
   a kustomize `configMapGenerator` (`apps/alert-agent/kustomization.yaml:41-43`) and mounted at
   `/home/agent/.crontab`. Raising the cadence is therefore a frank-only change.
3. **#722: nothing alerts on PVC capacity.** No rule mentions `kubelet_volume_stats_*`. The metrics exist:
   36 series live today (2026-10-10), with a top of `secure-agent-pod/agent-home` 78.2%, `paperclip-system/paperclip-data`
   68.4% and `hermes-agent-shell/hermes-agent-shell-home` 65.5%. They come from the kubelet, not kube-state-metrics.

## Requirements

R1. The Telegram contact point sets `parse_mode` explicitly to `None`, so alerts are delivered as plain text and a bare `<`, `>` or `&` in an annotation cannot cause a Telegram 400.
R2. Every place in the repo that describes the Telegram contact point's parse mode agrees with R1: that an unset value means HTML, and that the contact point is pinned to `None`. That covers the contact-point comment, the `layer-1-nic-link-flap` and `layer-2-etcd-health` rule NOTE comments, the `scripts/tests/test_etcd_scrape.py` docstring and assertion message, the `frank-gotchas.md` Grafana one-liner, `docs/runbooks/frank-gotchas/grafana.md`, and the parse-mode passages of the operating posts `05-observability` and `15-health-monitoring`.
R3. A tripwire test fails if the Telegram receiver's `parse_mode` is removed or set to anything other than `None`.
R4. The alert-agent `cred-expiry-check` runs every 6 hours, at `0 3,9,15,21 * * *`, instead of once a day at 09:00 UTC. The 09:00 UTC slot is kept.
R5. The cred-expiry Telegram warning (text plus `LOGIN_CMD`) is sent at most once per warning-day per tier. A warning-day runs from 09:00 UTC to 09:00 UTC, so routine warnings still arrive at the 09:00 UTC run, as they do today. A tier change within a warning-day warns again. A send counts as successful only when both `tg_send` calls return a dict with `ok: True`. The de-dup key is written only after a successful send, so a failed send warns again on the next run. If the de-dup state cannot be read or written, the check still warns (it fails open toward warning). The heartbeat line prints on every run, whatever the outcome.
R6. The `alert-agent-cred-expiry-heartbeat-stale` window is 13h (`from: 46800` on all three refIds), with `for: 2h` and the group's `interval: 1h` kept. One missed 6-hourly run (a 12h gap) does not fire it. A dead check pages 15 to 16h after its last heartbeat. The summary text states the new window and the 6-hourly cadence.
R7. A rule fires `warning` when any PVC's byte utilisation `100 * used / capacity` is above 85% for 30m, and `critical` when it is above 95% for 5m, per `namespace`/`persistentvolumeclaim`. The annotation names the volume and its percentage. A zero or absent denominator never fires.
R8. A rule fires `warning` when any PVC's inode utilisation is above 90% for 30m, per `namespace`/`persistentvolumeclaim`. A zero inode count never fires.
R9. The PVC rules live in the `feature-health` folder with `github_issue: "frank-ops#4"`, `pvc_capacity: "true"`, `noDataState: OK` and `execErrState: Error`. Their uids are each at most 40 characters.
R10. The PVC rules reach Telegram and Health Bridge, as the operator chose, but re-notify at most every 4h instead of the root policy's 3m. A `pvc_capacity="true"` route, placed before the severity routes, sets `repeat_interval: 4h` and fans out to both receivers through child routes.
R11. Tripwire tests pin the new PVC rules' expressions (including the denominator guard), thresholds, `for` windows, labels, uids and route. They also pin the cred-expiry crontab cadence, the window, and the de-dup behaviour. The window guard parses the cadence from the crontab and asserts `window > 2 × cadence` and `window < 30h`.

## Design

### #799 — explicit `parse_mode: None`

Evidence for the change: a pre-merge live probe through the real bot (spec journal `parse-mode-live-probe`) sent the same bare-`<` text twice. With `parse_mode` unset the result was `400 Bad Request`; with `None` it was `ok`.

- `contact-points-cm.yaml`: add `parse_mode: None` to the `efi04e0201jb4f` receiver `settings` and replace the comment. The new comment says that an **unset** value is HTML (citing upstream `receivers/telegram/v1/config.go:84-86` and the probe), that `None` is plain text, and that #143's original reason still stands: Markdown strips underscores.
- Leave the seven rules' annotations alone. Under `None`, `<>&` are inert, and rewriting them is churn (operator decision).
- Reword the `layer-1-nic-link-flap` and `layer-2-etcd-health` NOTE comments, and the docstring and assertion message at `scripts/tests/test_etcd_scrape.py:1038,1062-1063`. Each should say that the unset default was HTML (so the 2026-06-08 400 was real) and that the contact point has been pinned to `None` since this change. The etcd test's assertion that annotations carry no `<>&` stays, as a style guard.
- `frank-gotchas.md` Grafana one-liner and `docs/runbooks/frank-gotchas/grafana.md`: rewrite them to the same facts, and name the tripwire.
- Operating posts `blog/content/docs/operating/05-observability/index.md` and `15-health-monitoring/index.md`: correct the parse-mode passages, using a normal markdown edit per the fix/extension workflow.
- New tripwire `scripts/tests/test_telegram_parse_mode_explicit.py`. It loads the contact-points ConfigMap, finds every `type: telegram` receiver and asserts `settings.parse_mode == "None"`.
- Leave the alert-agent's own `tg_bridge` sends alone. They use the Bot API directly, not the Grafana contact point.

### #746 — 6-hourly heartbeat, once-a-day warning, 13h window

- `.crontab`: change the schedule to `0 3,9,15,21 * * * /opt/alert-agent-bin/cred-expiry-check`, and fix both comment lines that say "daily" (lines 2 and 5). The pod rolls on its own: the ConfigMap is hash-suffixed and the app runs `prune: true`.
- `handlers/cred_expiry.py`:
  - `STATE_PATH` is a module attribute, default `os.environ.get("CRED_WARN_STATE_PATH", "/home/agent/.cache/cred-expiry-last-warn")`. It is on the `alert-agent-home` PVC. Functions read it **at call time** (as `cred_expiry.STATE_PATH`), so tests can monkeypatch it.
  - Add a pure `_warn_key(tier, now_ms) -> f"{date(now - 9h)}:{tier}"`, which anchors the warning-day at 09:00 UTC.
  - `run_cred_check` prints the heartbeat first, unconditionally. It warns only when `v.should_warn` holds and the stored key differs from `_warn_key`. The key is written (creating the parent directory) only when **both** `tg_send` results are dicts with `ok` true. A read error counts as "no prior key". A write error is logged to stderr and swallowed. Docstrings and the `Verdict` comments stop saying "daily".
- `alert-rules-cm.yaml`, group `alert-agent-cred-expiry`: change `from: 108000` to `from: 46800` on A, B and C, keeping `for: 2h` and `interval: 1h`. Rewrite the summary to cover both "for 13h" and "The 6-hourly check is dead". Update the comment block with the arithmetic: 6h cadence, 13h window, one miss tolerated, fires 15 to 16h after the last heartbeat.
- Guards:
  - `scripts/tests/test_cred_expiry_alert_rule.py`: parse the cadence from `.crontab` and assert `2 × cadence < window < 30h`; `for` stays 2h.
  - `apps/alert-agent/handlers/tests/test_cred_expiry_wiring.py`: pin the 6-hourly line.
  - `test_cred_expiry.py`: add an **autouse fixture** that monkeypatches `cred_expiry.STATE_PATH` to `tmp_path`, and make the `wired` fixture's `tg_send` return `{"ok": True}`. De-dup cases:
    - same warning-day and tier → suppressed
    - next warning-day → warns
    - the 03:00 UTC run belongs to the previous warning-day
    - tier escalation → warns
    - `ok: False` send → key not written → the next run warns
    - unreadable state → warns
    - unwritable state → still warns and still heartbeats

### #722 — PVC capacity and inode rules

The new group `pvc-capacity`, `folder: feature-health`, `interval: 1m`, datasource `P4169E866C3094E38` (VictoriaMetrics, the same as `layer-1-node-memory-headroom`). It uses the house A→B→C shape (query, `reduce last dropNN`, `threshold`):

| uid | expr (A) | threshold | for | severity |
|---|---|---|---|---|
| `pvc-capacity-warning` | `100 * max by (namespace, persistentvolumeclaim) (kubelet_volume_stats_used_bytes) / (max by (namespace, persistentvolumeclaim) (kubelet_volume_stats_capacity_bytes) > 0)` | `gt 85` | 30m | warning |
| `pvc-capacity-critical` | same | `gt 95` | 5m | critical |
| `pvc-inodes-warning` | `100 * max by (namespace, persistentvolumeclaim) (kubelet_volume_stats_inodes_used) / (max by (namespace, persistentvolumeclaim) (kubelet_volume_stats_inodes) > 0)` | `gt 90` | 30m | warning |

- `max by` collapses a duplicate series that can briefly exist while a volume moves between nodes. The `> 0` filter drops a zero denominator, which would otherwise give +Inf and fire forever. Live on 2026-10-10 no series had a zero denominator, and the inode maximum was 34.7%.
- Labels: `severity`, `github_issue: "frank-ops#4"` and `pvc_capacity: "true"`. Annotations: `summary` names `{{ $labels.namespace }}/{{ $labels.persistentvolumeclaim }}` and `{{ $values.B.Value | printf "%.0f" }}`%. `runbook` points to the Longhorn headroom check in `frank-gotchas.md` → Storage (expansion can be silently refused) and to the untracked-resource and prune notes. The annotations avoid `<>&` for style.
- A volume that is not mounted reports no series. That gives NoData, so the rule stays OK. Those volumes cannot fill, so this is expected.
- `notification-policy-cm.yaml`: a new route before the two severity routes, and after the escape-hatch routes:
  ```yaml
  - matchers: [pvc_capacity="true"]
    receiver: "Telegram - Willikins"
    repeat_interval: 4h
    continue: false
    routes:
      - receiver: "Telegram - Willikins"
        continue: true
      - receiver: "Health Bridge Webhook"
  ```
  A slow-burn condition that only operator action clears would otherwise re-page every 3m for days.
- Guards: a new `scripts/tests/test_pvc_capacity_alert.py` (rules and route). The existing folder-wide guards in `test_feature_health_workload_metrics.py` must stay green: severities, explicit no-data and exec-error states, and the 40-char uid limit.

## Verification

Test evidence is CI (`tests: ci`, gated by `.fr/ci.yaml`) plus targeted local tests. Per operator instruction the full suite does not run locally.

- obs-telegram-alerts-deliver-any-text: none — the tripwire (R3) runs in CI. The pre-merge live probe (`parse-mode-live-probe`) proved that unset gives 400 and `None` gives delivery on the real bot. The Test Plan step 2 checks the provisioned receiver after merge.
- obs-cred-expiry-deadman-tolerates-one-miss: live — the window and the de-dup are unit-tested. Proving that a missed slot leaves the rule Normal needs the merged crontab and rule on the cluster.
- obs-pvc-capacity-pages: live — the expressions are checked against VictoriaMetrics before merge. Proving that the provisioned rules evaluate needs Grafana to reload provisioning after merge.

## Test Plan (post-merge — operator-driven)

1. Confirm that `grafana-alerting` and `alert-agent` applied the merge SHA. Compare `status.operationState.operation.sync.revision` with the merge commit; do not rely on `Synced` (see the frank-gotchas ArgoCD stale-revision entry). Then run `kubectl -n monitoring rollout restart deploy/victoria-metrics-grafana`, because provisioning is read at boot.
2. Check the provisioned contact point: `GET /api/v1/provisioning/contact-points` from the grafana pod shows `parse_mode` `None` on `efi04e0201jb4f`.
3. Grafana alert list: `pvc-capacity-warning`, `pvc-capacity-critical` and `pvc-inodes-warning` are Normal, and each query returns all mounted PVCs.
4. Miss one cred-expiry slot. Scale `deploy/alert-agent` to 0 from about :55 to about :05 around a slot (this is a C&C bot outage). Confirm in VictoriaLogs that the slot has no `cred-expiry-check` line, then confirm that the dead-man rule stays Normal until the next slot's heartbeat lands.

## Out of scope

- Pruning on agent-shell home volumes (#722's "worth considering", item 1).
- Fill-rate (`predict_linear`) forecasting. The operator declined it in favour of inode coverage.
