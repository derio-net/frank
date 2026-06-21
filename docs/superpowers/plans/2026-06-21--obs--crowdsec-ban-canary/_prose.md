# CrowdSec Ban-Pipeline Canary (Hop) — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-06-21--obs--crowdsec-ban-pipeline-canary-design.md`
**Layer:** obs · **Repo:** derio-net/frank · **Branch:** `feat/crowdsec-ban-pipeline-canary`

## Why

The Hop CrowdSec ban pipeline failed **silently** three times in three days (#583 persistence,
docker runtime, #594 rotation-blindness) — agent `Running`, ArgoCD green, yet zero bans. Every
health signal we monitor stayed green while the actual capability died. This canary watches the
pipeline's *real* work and pages when it silently stops.

## Approach

A **passive frozen-watch** canary, settled with the operator:

- **Mechanism:** persisted cross-run delta on CrowdSec's own counters (single ~5 s scrape per run,
  compared to the previous run's stored sample). Three checks, each mapped to a historical failure:
  acquisition-live (`cs_filesource_hits_total` delta > 0), parsing-live
  (`cs_node_hits_ok_total{name="crowdsecurity/caddy-logs"}` delta > 0 while filesource advances),
  agent-alive (`:6060/metrics` scrapable). Metric names pinned live against v1.7.8.
- **Home & signal:** an in-cluster Hop `CronJob` (`*/5`) pages Telegram **directly** (dedicated
  `crowdsec-canary-telegram` secret) on the **2nd** consecutive failed run; every run emits a
  `verdict=` heartbeat to stdout → fluent-bit → Frank VictoriaLogs.
- **Dead-man's switch:** a Frank Grafana VictoriaLogs alert fires if the heartbeat goes stale
  (≥ 20 m) — the independent observer that catches the canary itself dying.

**Key design choices** (full rationale in the spec): a **sibling `crowdsec-canary` Application**
(the crowdsec app is Helm-only; ergonomics, not resources); **persisted-delta single-scrape** for
~2 % duty cycle on hop-1 (operator resource concern) + natural gate=2; **stock digest-pinned
`python:3-alpine`**, script from a ConfigMap, **no custom image/CI**; **Telegram creds optional**
so the CronJob is healthy *before* the back-loaded secret phase (heartbeat-only until then). The
acquisition check leans on Frank's ~360/hr blackbox edge probe as a guaranteed traffic floor
(load-bearing cross-ref).

## Phases

1. **Canary eval logic + unit tests (TDD)** — `canary.py` (parse / extract / evaluate / state /
   telegram / main) with pytest fixtures for all three historical failure signatures + healthy +
   bootstrap + gate + telegram-format. Tests first (RED → GREEN).
2. **Hop manifests** — state PV/PVC (hostPath, hetzner-volume, hop-1), CronJob + script ConfigMap
   (kustomize configMapGenerator from the one `canary.py`), sibling ArgoCD Application, and a
   static-validation guard test.
3. **Frank dead-man's-switch alert** — a VictoriaLogs heartbeat-staleness rule in
   `alert-rules-cm.yaml` (queryType stats, SSE A→B→C, Telegram contact, HTML-400-safe).
4. **Docs** — hop-gotchas one-liner, the reciprocal blackbox-floor cross-ref, an operating note.
5. **[manual] secret + acceptance test** — create `crowdsec-canary-telegram` (manual-op,
   `/sync-runbook`) and the operator-driven post-merge break-injection Test Plan (agent-down → FAIL
   page; suspend cronjob → dead-man's switch; steady-state no false pages; capture message_ids).
   Back-loaded: no agentic phase depends on it.

## Verification

Per "not Deployed until the workflow runs": phases 1–3 carry guard tests; phase 5's break-injection
proves the page end-to-end. ArgoCD-green is not proof — the Telegram `message_id`s are.
