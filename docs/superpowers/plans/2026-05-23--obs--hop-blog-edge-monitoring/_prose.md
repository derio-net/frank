# Hop Blog Edge Monitoring — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-23--obs--hop-blog-edge-monitoring-design.md`
**Status:** Deployed — cluster phases 1–5 verified end-to-end on 2026-05-24. Paper + building/operating blog posts deferred to a dedicated creative session.

> **Note for the future Paper-writing session (P6.T1):**
> Per user instruction (2026-05-24): create a Pull Request for the Paper +
> building post + operating post. **Do not commit directly to main.**
> The rest of the obs layer was developed directly on main because
> ArgoCD only syncs from main — that workflow doesn't apply to the
> documentation work, which goes through Hugo CI and benefits from PR
> review before publishing.

Hop (Hetzner CX23) has no observability for the public blog at
`blog.derio.net/frank`. This plan adds, in six phases, a complete
edge-monitoring plane: traffic analytics, edge HTTP security, container runtime
security, and an AI helper that produces a daily digest plus alert-time
enrichment with surge-origin analysis.

The design choice that shapes every phase is **collectors-on-Hop,
backend-on-Frank, reusing Frank's existing log/metric/alert stack**. Hop runs
only thin agents (~240 MB total memory) that ship over the existing
Headscale/Tailscale mesh. Frank's stack is **extended**, not duplicated:
VictoriaLogs gains a `LoadBalancer` Service for cross-cluster ingest;
fluent-bit (Frank's proven log shipper) is mirrored onto Hop with its output
URL pointed at the new LB IP; alerts go into the existing Grafana-managed
alert pipeline; the only genuinely new ArgoCD apps are `goatcounter` and
`ai-alert-helper`.

Three cross-cluster networking facts shape the plan:

- The Tailscale subnet router advertises only home-LAN ranges
  (`192.168.10/50/55.0/24`), not the kube service CIDR. Cross-cluster reach
  goes via Cilium L2 LoadBalancer IPs in `192.168.55.0/24`.
- Frank's VictoriaLogs gets a new LB IP at `192.168.55.225` for Hop's
  fluent-bit to push to. GoatCounter gets `192.168.55.224` for Hop's Caddy to
  reverse-proxy `counter.derio.net` to.
- Grafana datasources are provisioned via sidecar ConfigMaps (label
  `grafana_datasource: "1"`) — no `apps/grafana/values.yaml` file exists,
  Grafana being a subchart of `victoria-metrics`.

Phase 1 is the foundation everything else depends on: extend VictoriaLogs with
the LB Service + 30d retention, switch Caddy to JSON access logs, deploy
fluent-bit on Hop mirroring Frank's proven pattern.

Phases 2, 3, and 4 form a fan-out from phase 1, each delivering one
independently testable subsystem:

- **Phase 2 — Blog analytics.** GoatCounter on Frank at LB IP `192.168.55.224`
  with `X-Forwarded-For` trust for Hop's Tailscale range, Hugo partial
  injecting the tracker script, Hop's Caddy reverse-proxying `counter.derio.net`
  over the mesh. GoatCounter datasource added via new sidecar ConfigMap.
- **Phase 3 — Edge security.** CrowdSec agent on Hop reading Caddy's JSON
  logs, Caddy's `crowdsec-bouncer` module enforcing decisions locally. The
  bouncer intentionally lives at the edge (no Frank dependency on the request
  path).
- **Phase 4 — Host runtime.** Falco DaemonSet on Hop with the `modern_ebpf`
  driver — the only viable driver on Talos's no-userland kernel. Falco rule
  overrides done by **re-declaring** macros (there is no `override:` key in
  the Falco schema). Falcosidekick dual-publishes: routine events to
  VictoriaLogs LB IP for correlation, critical events direct to Telegram
  (delivery-must-not-depend-on-LLM-uptime).

Phases 3 and 4 can run in parallel after phase 1 — they touch different apps
on Hop and only share the Caddy ConfigMap (only phase 3 modifies it).

Phase 5 is the AI layer. The `ai-alert-helper` is a ~250-LOC FastAPI service
with **three entrypoints**:

1. `POST /digest` — daily Kubernetes CronJob at 08:00 UTC.
2. `POST /alert` — Grafana contact point webhook (Frank has no Alertmanager;
   alerting is Grafana-managed via the existing `apps/grafana-alerting/manifests/`
   ConfigMaps).
3. `POST /surge-check` — Kubernetes CronJob every 15 min. Surge detection
   lives in code (`surge.py`) because LogsQL cannot natively compute "median
   count over the same hour-of-day for the past 7 days"; the helper issues 7
   queries (one per recent day) and computes the median in Python.

The helper is built around a fact-sheet contract: `facts.py` produces
structured dicts specialised by alert type, and `ai_adapter.py` (LiteLLM-backed
with retry-fallback) consumes them. The `BlogTrafficSurge` trigger has two
tiers (Notable: 3× hour-of-day baseline; Major: 10× requests AND 5× unique
visitors). The single swap point — `ai_adapter.summarize` and
`ai_adapter.investigate` — is the future Sympozium-integration seam.

Two new entries land in the existing Grafana alerting pipeline (under a new
`blog-edge` folder): `CrowdSecDecisionBurst` (warning) and `FalcoCriticalEvent`
(critical). Both use the 3-step A (data) → B (reduce) → C (threshold) SSE
format required by Grafana 12.x; any 2-step format fails with `sse.parseError`
per `agents/rules/frank-gotchas.md`. Routing: a new `AI Helper Webhook` contact
point + a notification policy route matching `grafana_folder = "blog-edge"`.

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

- `kubectl get application` shows all new/extended ArgoCD apps Healthy/Synced
  on both clusters.
- Grafana Explore returns Caddy access logs from the last 24h via the
  existing VictoriaLogs datasource.
- A blog visit from incognito produces a hit in GoatCounter and a log entry
  in Grafana within 30s.
- A controlled CrowdSec probe pattern (`/wp-login.php` 10×) results in a
  Caddy 403 on the next request from the test IP.
- A controlled `kubectl exec` into a Hop Pod produces a Telegram alert within
  5 seconds via Falcosidekick's direct path.
- A synthetic load test (`hey -z 2m -c 50 https://blog.derio.net/frank/...`)
  triggers a surge classification at the next 15-min cron tick, and the AI
  helper posts a Telegram message that correctly identifies it as a scraper
  (low visitor count, single IP, high request count).
- The 08:00 UTC daily digest arrives on Telegram the morning after phase 5
  ships.
- Hop's memory limits stay below 90% allocatable across all phases.

Resource budget on Hop:

| Component | Memory limit | Phase |
|---|---|---|
| fluent-bit | 80 Mi | 1 |
| crowdsec-agent | 128 Mi | 3 |
| falco + sidekick | 200 Mi | 4 |
| **Sum new** | **408 Mi** | |

Pre-plan: 73% of 3263 Mi limits committed. Post-plan: ~85%. Each Hop-affecting
phase has a `kubectl describe node hop-1` budget check as an exit step. If
phase 4 pushes the node past 88% limits, defer Falco as a separate rework plan
and ship phases 1–3 + 5.

Post-deploy per `docs/superpowers/plan-config.yaml`: standard layer, all six
post-deploy steps apply (external exposure, building post, operating post,
README, runbook, status).
