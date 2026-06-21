# CrowdSec Ban-Pipeline Canary (Hop)

**Layer:** obs (hop — new workload under `clusters/hop/apps/`, plus one Frank Grafana rule)
**Status:** Draft
**Date:** 2026-06-21
**Repo:** `derio-net/frank`
**Motivated by:** three silent CrowdSec failures in three days — emptyDir persistence (#583),
docker→containerd runtime, inotify→poll log-rotation blindness (#594). Debugging log:
`docs/superpowers/debugging/2026-06-21-crowdsec-log-rotation-blind.md`.

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
  │   1. scrape agent /metrics (+ a 2nd sample after ~120s)     │
  │   2. evaluate 3 checks (read-advancing, parse-advancing,    │
  │      agent↔LAPI-connected)                                  │
  │   3a. on FAIL → POST Telegram directly (falco-telegram)  ───┼──► Telegram  (fast,
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

The canary scrapes the agent's Prometheus endpoint (`:6060/metrics`, enabled by default in
CrowdSec `config.yaml`) twice within one run, ~120 s apart, and evaluates deltas. No persistent
state needed — the deltas are computed in-run.

| Check | Signal | FAIL when | Catches |
|-------|--------|-----------|---------|
| **Acquisition live** | `cs_reader_hits_total{source="file:…caddy…log"}` | delta == 0 over the window | rotation-blindness (#594) |
| **Parsing live** | `cs_parser_hits_total` (or `cs_node_hits_ok_total`) for caddy-logs | parsed delta == 0 **while** reader delta > 0 | wrong runtime (docker) |
| **Agent↔LAPI connected** | agent `/metrics` reachable **and** `cs_lapi_*` request metrics show success | metrics unreachable (agent crashloop) or LAPI calls all erroring | lost persistence (#583) |

**Why the 120 s in-run window is enough (no quiet-period false positive):** Frank's own blackbox
uptime probe hits the public blog edge **~360/hr (~6/min)** via the home egress IP
(`Frank-Blackbox-Probe`, documented in `obs-digest.md`). So Caddy is *never* idle — a healthy
acquisition counter advances by ≳10 over 120 s. A frozen counter is therefore unambiguous, with no
separate "is there traffic?" query.
**Cross-ref hazard:** this assumption is load-bearing. If the blackbox probe is ever retired or
re-pointed, this canary loses its guaranteed traffic floor and the acquisition check could
false-positive in a genuinely idle window. Add a reciprocal comment in the blackbox-exporter config
and in `obs-digest.md`.

**False-positive guard:** require **2 consecutive failed runs** (or in-run re-sampling) before
paging, so a one-off 120 s network blip doesn't page. The heartbeat is still emitted every run.

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
**Duty-cycle note (constrained node):** the 120 s two-sample window means the pod is awake ~40 % of
each interval. That's fine for a tiny curl/jq pod on hop-1, but if it ever matters the documented
fallback is a single-sample + persisted-delta variant (state on a small PV → pod runs ~5 s/run).

New, under `clusters/hop/apps/crowdsec-canary/manifests/`:
- `cronjob-ban-canary.yaml` — `*/5 * * * *`, `concurrencyPolicy: Forbid`, restartPolicy `Never`,
  small resources. Image: a minimal `curl`+`jq` (or `python:slim`) image; **digest-pinned**, baked,
  not `apk add` at runtime (Falco `EXE_UPPER_LAYER` Critical — `hop-gotchas.md`).
- `canary.sh` (or `.py`) in a ConfigMap — the scrape/eval/page logic.
- Reuse the existing `falco-telegram` Secret (already in a Hop namespace — confirm namespace, or
  mirror it into `crowdsec-system` via the existing secret-management path).

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
| Canary cadence | `*/5 * * * *` | every 5 min |
| In-run freeze window | ~120 s, 2 samples | blackbox floor → ≳10 expected reader hits |
| Consecutive fails before page | 2 | blip suppression |
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

## Open questions / risks

- **`falco-telegram` secret namespace.** Confirm where it lives; if not in `crowdsec-system`, decide
  mirror-via-secret-management vs a dedicated canary secret.
- **fluent-bit capture scope.** Confirm `crowdsec-system` container stdout is shipped to
  VictoriaLogs (it should be — CrowdSec logs already are), else the heartbeat never reaches Frank.
- **CrowdSec metric names** (`cs_reader_hits_total`, `cs_parser_hits_total`, `cs_lapi_*`) — pin
  against the live `:6060/metrics` of the running agent during planning; CrowdSec has renamed
  metrics across versions.
- **Image choice** — smallest pinned image that has `curl`+`jq` (or stdlib python) and can reach
  both the agent metrics port and the Telegram API.

## Future work

- **Active synthetic-injection probe** — periodically replay enough scanner-shaped requests to trip
  a real scenario from a throwaway source, assert a fresh decision appears, then delete it. The only
  way to catch a *novel* break that freezes none of the passive counters. Layer it on once the
  passive canary is proven.
- If a cross-cluster metrics path is ever built for other reasons, migrate the dead-man's switch and
  checks onto `probe_success`-style metrics to match the Frank layer-canary pattern.
