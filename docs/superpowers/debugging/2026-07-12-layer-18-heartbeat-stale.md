# Layer 18 Heartbeat Stale Alert After Cluster Restart

## Symptom & Reproduction

Grafana sent resolved notifications for `Layer 18 Persistent Agent Heartbeat Stale`
with two alert instances:

- `job="session_manager"`
- `job="vk_issue_bridge"`

Both instances carried `github_issue="frank-ops#18"` and came from the
`layer-18-persistent-agent-degraded` rule.

## Evidence

- Isolation was recreated with the `cluster-admin` profile after the first `dev`
  profile lacked `kubectl`.
- `kubectl get --raw=/readyz` succeeded with context `omni-frank-fr-isolation`
  after recreating the container so the refreshed admin credentials were loaded.
- `secure-agent-pod` was running and ready after the cluster restart:
  `secure-agent-pod-f6876b66d-9dkbf 2/2 Running`, age about 17h at investigation time.
- `pushgateway` was also running, age about 17h.
- The secure-agent-pod's crontab schedules:
  - `/opt/scripts/session-manager.sh` every 5 minutes.
  - `/home/claude/.local/bin/fr-bridge` every 2 minutes.
- Current Pushgateway samples were fresh at investigation time:
  - `willikins_heartbeat_last_success_timestamp{job="session_manager"}` was about
    3 minutes old.
  - `willikins_heartbeat_last_success_timestamp{job="vk_issue_bridge"}` was about
    1 minute old.
- Grafana evaluated the Layer 18 rule as inactive and healthy:
  - `state=inactive`
  - `health=ok`
  - resolved instance for `session_manager`: `Normal`, active at `2026-07-12T09:25:50Z`
  - resolved instance for `vk_issue_bridge`: `Normal`, active at `2026-07-12T09:27:50Z`
- `session-manager.log` showed the first post-restart session manager run at
  `2026-07-12 09:25:00`.
- `fr-bridge.log` showed post-restart bridge ticks beginning at `2026-07-12 09:26:00`
  and continuing every 2 minutes.

## Root Cause

The Layer 18 heartbeat alerts fired because the cluster restart stopped the
secure-agent-pod long enough for the persisted Pushgateway heartbeat timestamps
to age past the 10-minute Layer 18 threshold. After the pod restarted,
supercronic ran both jobs on their normal schedules, pushed fresh heartbeat
timestamps, and Grafana resolved the two alert instances.

This was a restart-gap alert, not a failure of `session_manager`, `fr-bridge`,
Pushgateway, or Grafana alert provisioning.

## Fix

No code fix. The rule behaved as designed: a Layer 18 cron heartbeat was stale
while the cron host was unavailable, then resolved when the cron host resumed.

No alert threshold or `noDataState` change was made. Widening the threshold would
hide genuine persistent-agent failures, and this incident already self-resolved
with clear per-job evidence.

## Rejected Hypotheses

- `kubectl` missing from isolation: true only for the initial `dev` profile. The
  correct `cluster-admin` profile includes `kubectl`.
- Missing admin credentials in isolation: rejected after container recreation;
  the refreshed profile loaded working kube credentials.
- Supercronic down: rejected; process list showed `supercronic /home/claude/.crontab`
  running.
- `vk_issue_bridge` runtime failure: rejected; `fr-bridge.log` showed regular
  successful ticks and current Pushgateway heartbeat samples.
- `session_manager` runtime failure: rejected; `session-manager.log` showed the
  post-restart run and current Pushgateway heartbeat samples.
