# CrowdSec ban-pipeline canary (Hop)

Detects the **silent-failure class** that bit the Hop CrowdSec pipeline three times in three days
(#583 lost persistence, docker-runtime parse break, #594 rotation-blindness) — the agent stayed
`Running` and ArgoCD stayed green while the pipeline silently stopped banning.

A `CronJob` (`*/5`) scrapes the agent `:6060/metrics` once per run, compares to the previous run's
persisted sample (state PV), and fails on any of:

| Check | FAIL when | Catches |
|-------|-----------|---------|
| acquisition | `cs_filesource_hits_total` delta == 0 | rotation-blindness (#594) |
| parsing | caddy-logs `cs_node_hits_ok_total` delta == 0 while reads grow | docker runtime |
| agent_alive | `/metrics` unreachable / empty | #583 crashloop |

It pages Telegram **directly** on the **2nd consecutive** failed run, and emits a
`crowdsec-ban-canary verdict=…` heartbeat every run. A Frank Grafana rule
(`crowdsec-canary-heartbeat-stale`) is the dead-man's switch: it pages if the heartbeat itself
stops. Full design: `docs/superpowers/specs/2026-06-21--obs--crowdsec-ban-pipeline-canary-design.md`.

## Operate

```bash
# (Hop) read the heartbeats — recent runs, newest first
kubectl -n crowdsec-system get jobs,pods -l app=crowdsec-ban-canary
kubectl -n crowdsec-system logs -l app=crowdsec-ban-canary --tail=5      # "verdict=ok ..." lines

# in VictoriaLogs (Frank Grafana → Explore): the same heartbeat the watchdog watches
#   kubernetes.namespace_name:crowdsec-system AND log:"crowdsec-ban-canary verdict"

# suspend (e.g. during planned agent maintenance, to avoid a false page)
kubectl -n crowdsec-system patch cronjob crowdsec-ban-canary -p '{"spec":{"suspend":true}}'
# resume
kubectl -n crowdsec-system patch cronjob crowdsec-ban-canary -p '{"spec":{"suspend":false}}'
```

> Suspending for >20 min trips the Frank dead-man's switch (by design — a suspended canary IS an
> unwatched pipeline). For short maintenance, expect and ignore that page, or silence it in Grafana.

## When it pages

A `FAIL` page names the failed check(s). First triage:

1. `kubectl -n crowdsec-system logs -l app=crowdsec-ban-canary --tail=5` — read the deltas.
2. **acquisition** → the agent is likely blind on log rotation again — check `cscli metrics` for a
   frozen `filesource` (`hop-gotchas.md`: `poll_without_inotify`).
3. **parsing** → reads grow but nothing parses as Caddy — check `container_runtime` /
   `cscli metrics` parser rows (`hop-gotchas.md`: containerd vs docker).
4. **agent_alive** → the agent pod is down/crashlooping — check it registered with LAPI
   (`hop-gotchas.md`: emptyDir persistence #583).

## Telegram secret

Paging needs `crowdsec-canary-telegram` (`TELEGRAM_TOKEN` + `TELEGRAM_CHATID`) in `crowdsec-system`
— a manual-op (see `docs/runbooks/manual-operations.yaml`). Until it exists the canary runs
heartbeat-only (the secret env is `optional`), so the CronJob is healthy without it.
