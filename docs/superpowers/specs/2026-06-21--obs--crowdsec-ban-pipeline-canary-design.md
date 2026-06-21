# CrowdSec Ban-Pipeline Canary (Hop)

**Layer:** obs (hop — new workload under `clusters/hop/apps/`, plus one Frank Grafana rule)
**Status:** Draft
**Date:** 2026-06-21
**Repo:** `derio-net/frank`
**Motivated by:** three silent CrowdSec failures in three days — emptyDir persistence (#583),
docker→containerd runtime, inotify→poll log-rotation blindness (#594). Debugging log:
`docs/superpowers/debugging/2026-06-21-crowdsec-log-rotation-blind.md`.

## Implementation Plans

| Plan | Target repo | Slug | Status |
|------|-------------|------|--------|
| 2026-06-21--obs--crowdsec-ban-canary | `derio-net/frank` | `2026-06-21--obs--crowdsec-ban-canary` | — |

## Problem

The Hop CrowdSec ban pipeline has failed **silently** three times in three days. Each time the
agent stayed `Running 1/1`, ArgoCD stayed `Synced/Healthy`, and yet **zero IPs were banned** —
scanners walked the blog edge unblocked until a human happened to notice. The failures were:

| # | Failure | What broke | Observable signature |
|---|---------|-----------|----------------------|
| #583 | emptyDir persistence | LAPI restart wiped the agent's machine row → agent crashloops `ent: machine not found` | agent not validated / no agent metrics |
| — | `container_runtime: docker` on containerd | `docker-logs` parser yields empty message → caddy-logs parses nothing | lines **read** climbing, lines **parsed** = 0 |
| #594 | inotify can't follow symlinked log rotation | tailer hangs in "Waiting for …to appear" | lines **read** frozen while Caddy traffic flows |

The common thread: **every health signal we monitor (pod readiness, ArgoCD sync) stayed green while
the actual capability — banning — was dead.** All three are detectable from the *same* passive
signature: **parse/decision activity frozen while Caddy traffic keeps flowing**, or **the agent not
connected to LAPI**. A canary watching those signatures would have caught all three.

## Goals

- **Page Telegram** when the ban pipeline stops actually working, within minutes, *before* a human
  notices the bans stopped.
- Catch the **three known failure modes** (acquisition frozen, parse frozen, agent↔LAPI broken)
  from passive signals — no synthetic attack traffic.
- Be **self-watching**: a crashed/suspended canary must itself be detected (else it silently
  reproduces the exact failure class it exists to prevent).
- Reuse existing infrastructure; add no cross-cluster metrics pipeline.

## Non-goals (this iteration)

- **Active synthetic injection** (send a real scanner request, assert a decision, clean it up).
  Gold-standard end-to-end proof and the only way to catch a *novel* failure that freezes nothing,
  but it needs scenario-threshold replay, risks self-banning the prober, and requires decision
  cleanup. Deferred as a future extension (§ Future work) — all three *known* failures are passively
  observable, so passive detection is the YAGNI-correct MVP.
- Building a cross-cluster Prometheus/VictoriaMetrics scrape from Hop. Hop has no metrics-scrape
  infra; standing one up is out of scope.

## Operator decisions (settled)

1. **Mechanism: passive frozen-watch** (MVP). Watch CrowdSec's own counters for the frozen / not-
   connected signatures rather than injecting traffic.
2. **Home & signal: in-cluster Hop CronJob → Telegram direct**, reusing the existing `falco-telegram`
   secret (`TELEGRAM_TOKEN` + `TELEGRAM_CHATID`). The check runs where it has direct access to the
   agent + LAPI; the failure page does not depend on the cross-cluster log path.
3. **Dead-man's switch: yes**, via heartbeat freshness. Resolves the "who watches the canary"
   tension: a self-contained Hop CronJob cannot detect its own death, so each run emits a heartbeat
   that an **independent** observer on Frank watches for staleness.

## Architecture

```
                          Hop cluster (crowdsec-system)
  ┌─────────────────────────────────────────────────────────────┐
  │  CronJob crowdsec-ban-canary  (*/5 * * * *)                  │
  │   1. scrape agent /metrics ONCE; delta vs prev-run sample   │
  │   2. evaluate 3 checks (read-advancing, parse-advancing,    │
  │      agent-alive); persist sample + fail-counter            │
  │   3a. 2nd consecutive FAIL → POST Telegram (canary secret)──┼──► Telegram  (fast,
  │   3b. always → print structured heartbeat line to stdout    │      log-path-independent)
  └───────────────┬─────────────────────────────────────────────┘
                  │ stdout (verdict=ok|fail …)
                  ▼ fluent-bit  →  Loki-push
        Frank VictoriaLogs (192.168.55.225)
                  ▲
                  │ LogsQL query
  ┌───────────────┴─────────────────────────────────────────────┐
  │  Frank Grafana alert: dead-man's switch                      │
  │   no `crowdsec-ban-canary` heartbeat in 20m  → Telegram      │
  │   (optional) a `verdict=fail` line seen      → Telegram      │
  └─────────────────────────────────────────────────────────────┘
```

Two independent failure detectors, defense-in-depth:
- **Pipeline broken** → Hop canary pages Telegram **directly** (works even if VictoriaLogs/fluent-bit
  is down).
- **Canary dead/suspended** → Frank Grafana fires on heartbeat staleness (an independent observer;
  rides the already-flowing log path, no new metrics pipeline).

### The three checks (passive)

**Sampling: persisted cross-run delta (single scrape per run).** Each run scrapes the agent's
Prometheus endpoint (`:6060/metrics`, enabled by default) **once**, then compares against the
**previous run's** sample stored on a tiny state volume — the delta is over the ~5 min between runs.
Chosen over an in-run two-sample window specifically for hop-1's resource budget: the pod runs ~5 s
and exits (~2 % duty cycle) instead of staying awake ~120 s (~40 %). It also implements the
**consecutive-fail gate naturally**: the state file carries a fail-counter (reset on OK, increment on
FAIL); the canary pages only when it reaches **2**. First run after a state reset has no previous
sample → it bootstraps (stores the sample, verdict `ok`, no page).

**Metric names pinned against the live agent (`v1.7.8`, 2026-06-21) — the agent does NOT expose
`cs_reader_hits_total`/`cs_parser_hits_total` rates or any `cs_lapi_*`; use the families below:**

| Check | Signal | FAIL when | Catches |
|-------|--------|-----------|---------|
| **Acquisition live** | `cs_filesource_hits_total{source="…caddy…log"}` (lines read from the file) | delta == 0 over the ~5-min cross-run interval | rotation-blindness (#594) |
| **Parsing live** | `cs_node_hits_ok_total{name="crowdsecurity/caddy-logs"}` (the parsed-as-Caddy count) | delta == 0 **while** `cs_filesource_hits_total` delta > 0 | wrong runtime (docker → all unparsed: caddy-logs `ok` frozen, `cs_node_hits_ko_total` climbs) |
| **Agent alive** | agent `:6060/metrics` returns HTTP 200 with `cs_` series | scrape fails / empty | lost persistence (#583): a not-registered agent crashloops → no metrics |

The agent has no `cs_lapi_*`, so "agent↔LAPI connected" collapses to "is `/metrics` scrapable at all" —
a #583 crashloop (machine-not-found) produces no metrics endpoint, which the alive-check catches.

**Why a frozen counter is unambiguous (no quiet-period false positive):** Frank's own blackbox
uptime probe hits the public blog edge **~360/hr (~6/min)** via the home egress IP
(`Frank-Blackbox-Probe`, documented in `obs-digest.md`). So Caddy is *never* idle — a healthy
acquisition counter advances by ≳30 over the ~5-min interval. A frozen counter is therefore
unambiguous, with no separate "is there traffic?" query.
**Cross-ref hazard:** this assumption is load-bearing. If the blackbox probe is ever retired or
re-pointed, this canary loses its guaranteed traffic floor and the acquisition check could
false-positive in a genuinely idle window. Add a reciprocal comment in the blackbox-exporter config
and in `obs-digest.md`.

**False-positive guard:** page only after **2 consecutive failed runs** (the persisted fail-counter,
~10 min), so a one-off scrape blip doesn't page. The heartbeat is still emitted every run regardless.

### Signalling

- **Heartbeat (every run):** structured stdout line, e.g.
  `crowdsec-ban-canary verdict=ok reader_delta=14 parser_delta=14 lapi=ok ts=<iso>`.
  The CronJob runs in `crowdsec-system`, already in fluent-bit's capture scope → lands in
  VictoriaLogs. (Verify the namespace is captured; widen the fluent-bit input if not.)
- **Direct page (on FAIL):** `curl` POST to the Telegram Bot API using `falco-telegram`’s
  `TELEGRAM_TOKEN` / `TELEGRAM_CHATID`. Message names the failed check(s) and the last deltas.
  **HTML parse-mode trap:** keep `<`/`>`/`&` out of the message body (the documented Telegram-400
  silent-drop — `frank-gotchas.md`); send plain text.

## Components & files

**App structure (settled): a sibling `crowdsec-canary` Application**, not folded into the crowdsec
app. Rationale: the canary pod is a `CronJob` — its resource cost (one small short-lived pod every
5 min) is identical whether it's a separate Application or folded in, so this is an ergonomics
decision, not a resource one. The crowdsec Application is a **pure Helm-chart source** (chart +
values ref, no raw-manifests path), so raw CronJob manifests have no natural home inside it without
bolting on a second ArgoCD source. A small sibling Application (`clusters/hop/apps/root/templates/
crowdsec-canary.yaml` → `path: clusters/hop/apps/crowdsec-canary/manifests`) is the conventional fit
and lets the canary be suspended/synced/tested independently of the pipeline it watches.
**Duty-cycle note (constrained node):** the persisted-delta design keeps the pod awake ~5 s/run
(~2 % duty cycle), chosen for hop-1's budget over the ~40 % of an in-run 120 s window.

New, under `clusters/hop/apps/crowdsec-canary/manifests/`:
- `cronjob-ban-canary.yaml` — `*/5 * * * *`, `concurrencyPolicy: Forbid`, restartPolicy `Never`,
  small resources. Image: a **stock, digest-pinned `python:3-alpine`** — no custom build. Python
  stdlib does the HTTP scrape, Prometheus-text parse, and Telegram POST, so there's no Dockerfile /
  CI / bump-image machinery. Falco `EXE_UPPER_LAYER` only fires on *runtime* installs; a stock
  baked image with the script mounted from a ConfigMap is fine (no `apk add`). Mounts the state PV
  (below) at e.g. `/state`.
- `canary.py` in a ConfigMap (mounted, run by the stock python image) — scrape → parse →
  compare-to-prev-sample → eval → persist {sample, fail-counter} → page-on-2nd-fail / heartbeat.
  **Telegram creds are optional**: if the secret is absent, the canary still scrapes, evaluates, and
  emits the heartbeat — it just skips the direct page (so the CronJob is healthy *before* the manual
  secret phase; the secret only unlocks paging). Env via `secretKeyRef … optional: true`.
- A small **state PV** for the persisted sample + fail-counter — a static `hostPath`
  (`DirectoryOrCreate`, subdir of the already-attached Hetzner Volume `/var/mnt/hop-data/…`, pinned
  to `hop-1`), mirroring the crowdsec LAPI persistence pattern (`clusters/hop/apps/storage/manifests/`),
  bound to a `crowdsec-canary-state-pvc` via `claimRef`, `storageClassName: hetzner-volume`
  (MANDATORY — no default SC). State loss → the canary bootstraps (no false page).
- A **dedicated `crowdsec-canary-telegram` Secret in `crowdsec-system`** (`TELEGRAM_TOKEN` +
  `TELEGRAM_CHATID`). `falco-telegram` lives in `falco-system` and Secrets are namespace-scoped, so
  the canary can't reference it cross-namespace. Created out-of-band (Hop = plain `kubectl create
  secret`, per repo-principles) as a **back-loaded manual-op** — same Telegram bot/chat as falco.

New, under `apps/grafana-alerting/manifests/` (Frank):
- A VictoriaLogs-backed alert rule in `alert-rules-cm.yaml`: dead-man's switch on the heartbeat
  (`crowdsec-ban-canary` absent ≥ 20 m). Follow the VictoriaLogs alert conventions in
  `grafana.md` (`model.queryType: stats`, the wide-series requirement).

Guard tests (`scripts/tests/`, the local pytest pattern alongside the existing
`test_crowdsec_*.py`):
- assert the CronJob schedule, `concurrencyPolicy: Forbid`, pinned image (no `:latest`), and the
  Telegram-secret reference exist;
- assert the eval script's three checks are present (a unit test feeding it canned `/metrics`
  fixtures for each of the three historical signatures → expect FAIL, and a healthy fixture →
  expect OK).

## Tunable parameters (defaults; adjustable at plan/review)

| Param | Default | Note |
|-------|---------|------|
| Canary cadence | `*/5 * * * *` | every 5 min; also the cross-run delta interval |
| Delta interval | ~5 min (= cadence) | blackbox floor → ≳30 expected filesource hits |
| Consecutive fails before page | 2 (persisted counter) | blip suppression; ~10 min to page |
| Dead-man's-switch staleness | 20 min | ~4 missed runs |

## Failure-mode coverage

| Historical failure | Detected by | How |
|--------------------|-------------|-----|
| #594 rotation-blindness | Acquisition-live check | reader delta == 0 vs blackbox floor |
| docker runtime | Parsing-live check | parsed delta == 0 while reader delta > 0 |
| #583 lost persistence | Agent↔LAPI check | agent metrics unreachable / LAPI errors |
| canary itself dies | Frank dead-man's switch | heartbeat stale ≥ 20 m |
| *novel* freeze-nothing break | **NOT covered** | needs active injection (future work) |

## Acceptance / end-to-end verification (required before "Deployed")

Per the "a layer is not Deployed until its workflow runs end-to-end" rule, the plan must **trigger a
real break** and observe a page — ArgoCD-green is not proof:
1. **Agent-down**: scale the agent DaemonSet to 0 (or cordon its scheduling) → expect the
   Agent↔LAPI check to FAIL and a Telegram page within ~2 cadences; restore.
2. **Parse-frozen** (optional, safe): temporarily set `container_runtime: docker` on a throwaway
   branch in a vCluster/test, or feed the unit-test fixture — expect the Parsing-live FAIL.
3. **Dead-man's switch**: suspend the CronJob → expect the Frank Grafana staleness alert ~20 m
   later; resume.
Capture the Telegram `message_id`s as evidence.

## Open questions / risks — RESOLVED (2026-06-21, live)

- ✅ **`falco-telegram` secret namespace** — it's in `falco-system`. Secrets are namespace-scoped →
  a **dedicated `crowdsec-canary-telegram` Secret in `crowdsec-system`** (back-loaded manual-op).
- ✅ **fluent-bit capture scope** — fluent-bit tails `/var/log/containers/*.log` across ALL
  namespaces (`kube.*`) and pushes to VictoriaLogs with `kubernetes.namespace_name`/`pod_name`
  fields, `_msg_field=msg`. The canary's stdout (in `crowdsec-system`) reaches Frank. The Frank
  dead-man's-switch LogsQL keys on `kubernetes.namespace_name:crowdsec-system` +
  `kubernetes.pod_name:crowdsec-ban-canary*` + the `verdict=` heartbeat marker.
- ✅ **CrowdSec metric names** — pinned live: `cs_filesource_hits_total` (read),
  `cs_node_hits_ok_total{name="crowdsecurity/caddy-logs"}` (parsed), `cs_node_hits_ko_total`
  (unparsed). No `cs_reader_hits_total`/`cs_parser_hits_total` rate, no agent-side `cs_lapi_*`.
- ✅ **Image** — stock digest-pinned `python:3-alpine`, script from ConfigMap, no custom build.

Remaining risk: pin the **exact `python:3-alpine` digest** at implementation time, and re-confirm
`cs_filesource_hits_total` is present on whatever agent version is live at deploy (re-scrape
`:6060/metrics`).

## Future work

- **Active synthetic-injection probe** — periodically replay enough scanner-shaped requests to trip
  a real scenario from a throwaway source, assert a fresh decision appears, then delete it. The only
  way to catch a *novel* break that freezes none of the passive counters. Layer it on once the
  passive canary is proven.
- If a cross-cluster metrics path is ever built for other reasons, migrate the dead-man's switch and
  checks onto `probe_success`-style metrics to match the Frank layer-canary pattern.
