# Plan: Blog Traffic Surge Detector — False-Positive Fix

**Spec:** `docs/superpowers/specs/2026-05-25--obs--surge-detector-false-positive-design.md`
**Layer:** `obs` (fix/extension of `2026-05-23--obs--hop-blog-edge-monitoring`)

## Why

The `ai-alert-helper` `surge-check` CronJob fired an **URGENT** "Blog traffic
surge" alert while GoatCounter showed no human activity. Both signals were
correct — they measure different things. The 370 edge requests were 97% Frank's
*own* blackbox uptime probe (`Blackbox Exporter/0.25.0`, ~360/hr to
`https://blog.derio.net`), plus a couple of internet scanners. GoatCounter
counts only JS-beacon pageviews from real browsers, so it correctly showed
nothing. The URGENT was a false positive from three compounding issues:

1. **Baseline forced to `1`** (`surge.py:35` `... or 1`) — the 7-day hour-of-day
   median was 0, so `ratio = 370/1 = 370×`.
2. **Frank's own probe counted as blog traffic** — no exclusion in
   `surge._hour_count` / `build_for_digest` / `build_for_surge`.
3. **The documented GoatCounter visitor-side cross-check was never implemented**
   — `/surge-check` sends `urgent=(tier=="Major")` with no human confirmation.

The CronJob re-fires every 15 min, so it is a sustained false-page storm until
the trailing baseline absorbs the probe (~3 days).

## What this plan does

- **Tags Frank's probes** with a self-controlled User-Agent
  (`Frank-Blackbox-Probe/...`) and excludes *that identity* (not the vendor's
  default UA) from the edge definition — see spec for why identity-based beats
  signature-based.
- **Centralizes** the edge query in one `facts.edge_filter()` so the surge
  alert, the surge narrative, and the daily digest can never disagree about
  what "blog traffic" is, canonicalized on `kubernetes.host:hop-1`.
- **Adds an absolute floor** (`SURGE_ABS_FLOOR`, default 50) so a baseline of 1
  cannot manufacture a high ratio from a trickle.
- **Implements the missing GoatCounter cross-check** in `/surge-check`:
  URGENT requires real visitors (`SURGE_VISITOR_FLOOR`, default 10), fails
  **open** (still pages, annotated) when GoatCounter is unreachable, and
  **downgrades** a Major to non-urgent Notable when GoatCounter confirms no
  humans.

## Execution constraints (important)

- **ArgoCD only watches `main`.** Every cluster-affecting change (cron suspend,
  blackbox UA, image deploy, un-suspend) takes effect *only after merge to
  `main`*. Phases 1 and 3 are therefore operator/manual: they include the
  `commit → PR → merge to main → ArgoCD sync → live verify` loop and require
  GHCR push creds for the manual `docker build`. Phase 2 is pure
  code/tests (CI-verifiable, no cluster effect).
- **Deploy ordering is structural.** Phase 3 `depends_on: [1]` so the exclusion
  filter never ships before the probe's new UA is live and verified — flipping
  it early would silently re-introduce the false page (the `Frank-Blackbox-Probe`
  token excludes 0 rows while the probe still sends the stock UA).
- **Silence during the work window.** Phase 1 sets the surge-check CronJob
  `suspend: true` (declarative); Phase 3 reverts it to `false` after the fix is
  verified live.

## Build / deploy recipe (proven, from the parent plan + digest-rework)

The image is built **manually** (the CI workflow's hardcoded `0.1.0` tag is
stale — aligned in Phase 3, proper parametrization deferred):

```bash
docker build -t ghcr.io/derio-net/ai-alert-helper:0.1.5 apps/ai-alert-helper/src/
docker push  ghcr.io/derio-net/ai-alert-helper:0.1.5
# bump api.py + pyproject.toml + deployment.yaml to 0.1.5; merge to main; ArgoCD syncs
```

The GoatCounter API token already carries the `stats` permission (manual-op
`obs-goatcounter-token-stats-permission`, done), so `/api/v0/stats/total`
returns 200 for the cross-check — no new secret needed.

## Phases

1. **Cluster prep — silence + probe identity** (manual): suspend surge-check;
   tag probes with `Frank-Blackbox-Probe`; merge; verify live UA.
2. **ai-alert-helper logic** (agentic, TDD): `edge_filter` + migrate 3 callers;
   absolute floor; GoatCounter reachability + visitor helper; `/surge-check`
   decision matrix + env wiring.
3. **Build, deploy & end-to-end verify + restore detector** (manual): bump +
   build/push 0.1.5; un-suspend; merge; live exclusion-query gate; confirm the
   probe no longer triggers; exercise the GC gate.
4. **Docs & close-out** (agentic): deviation note, gotchas, operating-post
   tuning section, runbook sync, status.
