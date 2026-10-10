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
R2. Every place in the repo that describes the Telegram contact point's parse mode agrees with R1. That covers the contact-point comment, the `layer-1-nic-link-flap` rule comment, the `frank-gotchas.md` Grafana one-liner and `docs/runbooks/frank-gotchas/grafana.md`.
R3. A tripwire test fails if the Telegram receiver's `parse_mode` is removed or set to anything other than `None`.
R4. The alert-agent `cred-expiry-check` runs every 6 hours (`0 */6 * * *`) instead of daily.
R5. The cred-expiry Telegram warning (text plus `LOGIN_CMD`) is sent at most once per UTC day per tier. A tier change within a day warns again. If the de-dup state cannot be read or written, the check still warns (it fails open toward warning). The heartbeat line prints on every run, whatever the outcome.
R6. The `alert-agent-cred-expiry-heartbeat-stale` window is 13h (`from: 46800` on all three refIds), with `for: 2h` kept. One missed 6-hourly run (a 12h gap) does not fire it, and a dead check pages within about 15h. The summary text states the new window.
R7. A rule fires `warning` when any PVC's byte utilisation `100 * used / capacity` is above 85% for 30m, and `critical` when it is above 95% for 5m, per `namespace`/`persistentvolumeclaim`. The annotation names the volume and its percentage.
R8. A rule fires `warning` when any PVC's inode utilisation is above 90% for 30m, per `namespace`/`persistentvolumeclaim`.
R9. The PVC rules live in the `feature-health` folder with `github_issue: "frank-ops#4"`, `noDataState: OK` and `execErrState: Error`, and route through the existing severity routes (Telegram, then Health Bridge). They need no new notification-policy route. Their uids are each at most 40 characters.
R10. Tripwire tests pin the new PVC rules' expressions, thresholds, `for` windows, labels and uids. They also pin the cred-expiry crontab cadence, the new window and the de-dup behaviour.

## Design

### #799 — explicit `parse_mode: None`

- `contact-points-cm.yaml`: add `parse_mode: None` to the `efi04e0201jb4f` receiver `settings`. Replace the comment.
  The new comment says that an **unset** value is HTML (citing the upstream `config.go` lines), that `None` is plain text, and
  that #143's original reason still stands: Markdown strips underscores.
- Leave the seven rules' annotations alone. Under `None`, `<>&` are inert, and rewriting them is churn (operator decision).
- Rewrite the `layer-1-nic-link-flap` NOTE comment. It should record that the 2026-06-08 400 was real, because the unset default was HTML, and that
  `parse_mode: None` (this change) removes the constraint.
- `frank-gotchas.md` Grafana one-liner, and the matching section of `docs/runbooks/frank-gotchas/grafana.md`: rewrite
  them to say the contact point is pinned to `None`, that an unset `parse_mode` means HTML (not plain), and that the tripwire guards it.
- New tripwire `scripts/tests/test_telegram_parse_mode_explicit.py`. It loads the contact-points ConfigMap, finds every
  `type: telegram` receiver and asserts `settings.parse_mode == "None"`.
- Leave the alert-agent's own `tg_bridge` sends alone. They use the Bot API directly, not the Grafana contact point.

### #746 — 6-hourly heartbeat, once-a-day warning, 13h window

- `.crontab`: change the schedule to `0 */6 * * * /opt/alert-agent-bin/cred-expiry-check` and update the comment. The pod rolls on its own
  (hash-suffixed ConfigMap).
- `handlers/cred_expiry.py`: add `STATE_PATH` (env-overridable, default
  `/home/agent/.cache/cred-expiry-last-warn`, on the `alert-agent-home` PVC). The new pure helper
  `_warn_key(tier, now_ms) -> f"{utc_date}:{tier}"` builds the de-dup key. `run_cred_check` warns only when `v.should_warn` holds and the stored key
  differs. After a successful send it writes the key, creating the parent directory. A read error counts as "no prior key" and the check warns.
  A write error is logged to stderr and swallowed. The heartbeat still prints first, unconditionally. Docstrings stop saying "daily".
- `alert-rules-cm.yaml`: change the window on all three refIds from `from: 108000` to `from: 46800`. Keep `for: 2h`, change the summary from "for 30h" to
  "for 13h", and update the comment block above the group to explain the cadence/window arithmetic: 6h cadence, 13h window,
  one miss tolerated.
- Existing guards to update: `scripts/tests/test_cred_expiry_alert_rule.py` (window must be at least 2× the cadence and
  less than 30h; `for` stays 2h), `apps/alert-agent/handlers/tests/test_cred_expiry_wiring.py` (6-hourly line) and
  `test_cred_expiry.py` (de-dup cases: same day and tier suppressed; new day warns; tier escalation warns;
  unreadable state warns; unwritable state still warns and still heartbeats).

### #722 — PVC capacity and inode rules

The new group `pvc-capacity`, `folder: feature-health`, `interval: 1m`, datasource `P4169E866C3094E38` (VictoriaMetrics, the same as
`layer-1-node-memory-headroom`). It uses the house A→B→C shape (query, `reduce last dropNN`, `threshold`):

| uid | expr (A) | threshold | for | severity |
|---|---|---|---|---|
| `pvc-capacity-warning` | `100 * max by (namespace, persistentvolumeclaim) (kubelet_volume_stats_used_bytes) / max by (namespace, persistentvolumeclaim) (kubelet_volume_stats_capacity_bytes)` | `gt 85` | 30m | warning |
| `pvc-capacity-critical` | same | `gt 95` | 5m | critical |
| `pvc-inodes-warning` | `100 * max by (namespace, persistentvolumeclaim) (kubelet_volume_stats_inodes_used) / max by (namespace, persistentvolumeclaim) (kubelet_volume_stats_inodes)` | `gt 90` | 30m | warning |

- `max by` collapses a duplicate series that can briefly exist while a volume moves between nodes.
- Labels: `severity` and `github_issue: "frank-ops#4"`. Annotations: `summary` names
  `{{ $labels.namespace }}/{{ $labels.persistentvolumeclaim }}` and `{{ $values.B.Value | printf "%.0f" }}`%. `runbook`
  points to the Longhorn headroom check in `frank-gotchas.md` → Storage (expansion can be silently refused) and to the
  untracked-resource and prune notes. The annotations avoid `<>&` for style, even though R1 makes them inert.
- A volume that is not mounted reports no series. That gives NoData, so the rule stays OK. Those volumes cannot fill, so this is expected.
- Guard: `scripts/tests/test_pvc_capacity_alert.py`. The existing folder-wide guards in
  `test_feature_health_workload_metrics.py` must stay green, including the 40-char uid limit and the explicit no-data and exec-error states.

## Verification

- obs-telegram-alerts-deliver-any-text: none — the tripwire test (R3) runs in CI. Before merge, a live Grafana `receivers/test` probe sends one message with a bare `<` through the real bot, once with `parse_mode` unset (expect a Telegram 400) and once with `None` (expect delivery). It is run from the grafana pod and its outcome is recorded in the spec journal.
- obs-cred-expiry-deadman-tolerates-one-miss: live — the 13h window and the de-dup are unit-tested. Proving that a skipped run leaves the rule Normal needs the merged crontab and rule on the cluster.
- obs-pvc-capacity-pages: live — the expressions are checked against VictoriaMetrics before merge. Proving that the provisioned rules evaluate (Normal, 36 series) needs Grafana to reload provisioning after merge.

## Test Plan (post-merge — operator-driven)

1. Confirm `grafana-alerting` and `alert-agent` applied the merge SHA: compare `status.operationState.operation.sync.revision` with the merge commit, not `Synced` (frank-gotchas ArgoCD stale-revision entry). Then run `kubectl -n monitoring rollout restart deploy/victoria-metrics-grafana`, because provisioning is read at boot.
2. Grafana alert list: `pvc-capacity-warning`, `pvc-capacity-critical` and `pvc-inodes-warning` are Normal and each query returns all mounted PVCs.
3. Skip one cred-expiry slot: delete the alert-agent pod about 5 minutes before a `:00` 6-hourly run. Over the next 13h the dead-man rule stays Normal, and the next run's heartbeat appears.

## Out of scope

- Pruning on agent-shell home volumes (#722's "worth considering", item 1).
- Fill-rate (`predict_linear`) forecasting. The operator declined it in favour of inode coverage.
