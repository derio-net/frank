# Hop Blog Edge Monitoring — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-23--obs--hop-blog-edge-monitoring-design.md`
**Status:** Planning — drafted on top of approved spec.

Hop (Hetzner CX23) has no observability for the public blog at
`blog.derio.net/frank`. This plan adds, in six phases, a complete edge-monitoring
plane: traffic analytics, edge HTTP security, container runtime security, and
an AI helper that produces a daily digest plus alert-time enrichment with
surge-origin analysis.

The design choice that shapes every phase is **collectors-on-Hop,
backend-on-Frank**: Hop runs only thin agents (~230 MB total memory) that ship
over the existing Headscale/Tailscale mesh to Frank, where Grafana,
VictoriaMetrics, Alertmanager, and the LiteLLM gateway already live. New
Frank-side components are VictoriaLogs (log store), GoatCounter (cookieless
analytics), and `ai-alert-helper` (FastAPI service). Hop's role stays
proportional to its budget — agents, not databases.

Phase 1 is the foundation everything else depends on: VictoriaLogs alive on
Frank, Caddy emitting JSON access logs, vlagent shipping over the mesh. Without
this plane no other phase has data to work with.

Phases 2, 3, and 4 form a fan-out from phase 1, each delivering one
independently testable subsystem:

- **Phase 2 — Blog analytics.** GoatCounter on Frank at LB IP `192.168.55.224`,
  Hugo partial injecting the tracker script, Hop's Caddy reverse-proxying
  `counter.derio.net` over the mesh. First user-visible feature.
- **Phase 3 — Edge security.** CrowdSec agent on Hop reading Caddy's JSON logs,
  Caddy's `crowdsec-bouncer` module enforcing decisions locally. The bouncer
  intentionally lives at the edge (no Frank dependency on the request path).
- **Phase 4 — Host runtime.** Falco DaemonSet on Hop with the `modern_ebpf`
  driver — the only viable driver on Talos's no-userland kernel.
  Falcosidekick dual-publishes: routine events to VictoriaLogs for
  correlation, critical events direct to Telegram (delivery-must-not-depend-
  on-LLM-uptime).

Phases 3 and 4 can run in parallel after phase 1 — they touch different apps
on Hop and only share the Caddy ConfigMap (and only phase 3 modifies it).

Phase 5 is the AI layer. The `ai-alert-helper` is a ~200-LOC FastAPI service
with two entrypoints (daily digest CronJob, Alertmanager webhook receiver)
built around a fact-sheet contract: `facts.py` produces structured dicts
specialised by alert type, and `ai_adapter.py` (LiteLLM-backed) consumes
them. The `BlogTrafficSurge` rule fires in two tiers (Notable: 3× hour-of-day
baseline; Major: 10× requests AND 5× unique visitors) and the AI helper
investigates with a specialised surge fact sheet (top referrers, top pages,
geo, human-vs-bot ratio, status distribution, time shape). The single swap
point — `ai_adapter.summarize` and `ai_adapter.investigate` — is the future
Sympozium-integration seam.

Phase 6 is the standard layer publish: new Paper "Edge Observability" (with
dossier), new building post, new operating post, README sync, runbook sync,
plan status to Deployed.

Layered dependencies:

```
   ┌─→ 02 (analytics) ──┐
01 ┼─→ 03 (CrowdSec)  ──┼─→ 05 (AI helper) ──→ 06 (publish)
   └─→ 04 (Falco)     ──┘
```

Success criteria:

- `kubectl get` shows all new ArgoCD apps Healthy/Synced on both clusters.
- Grafana Explore returns Caddy access logs from the last 24h.
- A blog visit from incognito produces a hit in GoatCounter and a log entry
  in Grafana within 30s.
- A controlled CrowdSec probe pattern (`/wp-login.php` 10×) results in a
  Caddy 403 on the next request from the test IP.
- A controlled `kubectl exec` into a Hop Pod produces a Telegram alert within
  5 seconds via Falcosidekick's direct path.
- A synthetic traffic surge (`hey -n 5000 -c 50 https://blog.derio.net/frank/`)
  fires `BlogTrafficSurgeMajor` within 2 minutes, and the AI helper posts a
  Telegram message that correctly identifies it as a synthetic load (low
  visitor count, single IP class, high request count).
- The 08:00 UTC daily digest arrives on Telegram the morning after phase 5
  ships.
- Hop's memory limits stay below 90% allocatable across all phases.

Resource budget on Hop:

| Component | Memory limit | Phase |
|---|---|---|
| vlagent | 64 Mi | 1 |
| crowdsec-agent | 128 Mi | 3 |
| falco + sidekick | 200 Mi | 4 |
| **Sum new** | **392 Mi** | |

Pre-plan: 73% of 3263 Mi limits committed. Post-plan: ~85%. Each Hop-affecting
phase has a `kubectl describe node hop-1` budget check as an exit step.

Post-deploy per `docs/superpowers/plan-config.yaml`: standard layer, all six
post-deploy steps apply (external exposure, building post, operating post,
README, runbook, status).
