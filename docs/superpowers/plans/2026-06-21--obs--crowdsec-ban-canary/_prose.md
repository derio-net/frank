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

## Phase 5 — manual operation (operator, post-merge)

The canary deploys and runs heartbeat-only **without** this secret (the env is `optional`); creating
it only unlocks the direct Telegram page. Back-loaded — no agentic phase depends on it.

```yaml
# manual-operation
id: obs-crowdsec-canary-telegram-secret
layer: obs
app: crowdsec-canary
plan: 2026-06-21--obs--crowdsec-ban-canary
when: After the crowdsec-canary Application syncs; before relying on FAIL pages.
why_manual: Secret material (Telegram bot token + chat id) — cannot be declarative in git.
commands: |
  # Target the Hop cluster (NOT Frank) before running these.
  # Same bot/chat as falco-telegram (which lives in falco-system; secrets are
  # namespace-scoped, so the canary needs its own copy in crowdsec-system).
  # Source the values from the existing falco secret rather than retyping:
  TOKEN=$(kubectl -n falco-system get secret falco-telegram -o jsonpath='{.data.TELEGRAM_TOKEN}' | base64 -d)
  CHATID=$(kubectl -n falco-system get secret falco-telegram -o jsonpath='{.data.TELEGRAM_CHATID}' | base64 -d)
  kubectl -n crowdsec-system create secret generic crowdsec-canary-telegram \
    --from-literal=TELEGRAM_TOKEN="$TOKEN" --from-literal=TELEGRAM_CHATID="$CHATID"
verify: |
  # (Hop context) next canary run should NOT log "telegram skipped (no creds)"
  kubectl -n crowdsec-system logs -l app=crowdsec-ban-canary --tail=20 | grep -i "no creds" && echo "STILL MISSING" || echo "creds present"
status: pending
```

### Post-merge Test Plan (operator-driven — ArgoCD-green is not proof)

1. **agent-alive break** → make the agent `/metrics` unreachable (e.g. patch the agent DaemonSet
   nodeSelector to an impossible label so the pod is removed); wait ~2 canary runs (gate=2);
   CONFIRM a Telegram FAIL page; capture `message_id`; restore the DaemonSet.
2. **dead-man's switch** → `kubectl -n crowdsec-system patch cronjob crowdsec-ban-canary -p
   '{"spec":{"suspend":true}}'`; wait ~20–25 m; CONFIRM the Frank `crowdsec-canary-heartbeat-stale`
   alert pages Telegram; capture `message_id`; unsuspend.
3. **steady-state** → confirm `verdict=ok` heartbeats each run in VictoriaLogs and NO false pages
   over ~30 m. Record the `message_id`s + the VictoriaLogs query; only then mark the layer Deployed.
