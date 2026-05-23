# Hop Blog Edge Monitoring — Traffic Analytics, Edge Security & AI-Enriched Alerts

**Layer:** obs
**Date:** 2026-05-23
**Status:** Approved — ready for plan

## Summary

Hop (Hetzner CX23, 2 vCPU / 3.8 GiB) currently has no observability for the public blog at `blog.derio.net/frank`. There are no analytics, no log shipping off the node, no edge security beyond Caddy defaults, and no Pod-level intrusion monitoring. This spec adds all three concerns on a single telemetry plane that **reuses Frank's existing log/metric/alert stack** — VictoriaLogs, VictoriaMetrics, Grafana, fluent-bit, and the Grafana-managed alerting pipeline — rather than introducing a parallel one.

The design is **collectors-on-Hop, backend-on-Frank**: Hop runs only thin agents (~270 MB total) that ship to Frank over the existing Tailscale subnet routes (LAN ranges only — `192.168.55.0/24` reaches Frank's Cilium L2 LoadBalancer IPs; the kube service CIDR is *not* routable cross-cluster). Frank's stack is extended in three ways: (1) VictoriaLogs gains a `LoadBalancer` Service so Hop's fluent-bit can push to it; (2) two new ArgoCD apps are added — `goatcounter` (cookieless analytics backend) and `ai-alert-helper` (FastAPI service); (3) the Grafana alerting ConfigMaps gain a new `blog-edge` rule group, a new webhook contact point, and a routing entry for it.

A `BlogTrafficSurge` flow with two severity tiers (Notable: 3× baseline, Major: 10× baseline + 5× unique visitors) detects anomalies. Because LogsQL cannot natively compute "median count over the same hour-of-day for the past 7 days", surge detection lives in the AI helper itself: a Kubernetes CronJob hits `/surge-check` every 15 minutes; the helper queries VictoriaLogs for both the current window and the historical baseline, computes the ratio in Python, and on a hit builds the surge fact sheet, calls the LLM, and posts to Telegram. Routine threshold alerts (CrowdSecDecisionBurst, FalcoCriticalEvent) ride Grafana's native alerting → contact point → webhook → ai-alert-helper enrichment → Telegram path. CrowdSec handles HTTP-layer blocking at the Caddy edge; Falco's `modern_ebpf` driver watches Pod syscalls and uses Falcosidekick's direct-Telegram output for critical events (delivery-must-not-depend-on-LLM-uptime).

The AI helper is built around a fact-sheet contract so its body can be swapped from LiteLLM to Sympozium later as a one-module change.

## Motivation

The blog is the public face of the Frank project — every paper, every building post, every operating post lives there. We have zero visibility today into:

1. **Who reads what.** No analytics. We don't know how many unique readers visited, where they came from, which papers actually get read, which search engines index us.
2. **What attacks the public edge.** Caddy runs with default rate-limits (none). A scraper or vulnerability scanner pounding the blog would be invisible until the node OOM'd or Hetzner billed for egress. No record of *who* is probing, *what* they're probing for, or *whether* they got anywhere.
3. **What happens inside Hop's Pods at runtime.** If a Caddy CVE landed and someone got code-execution in the Caddy Pod, we'd find out from external symptoms (defacement, egress alert) rather than from a syscall-level event. Talos's immutable base mitigates some of this, but not container-internal compromise.
4. **Whether something is unusual.** No baseline traffic shape, no anomaly detection. A 12× traffic spike from a successful Hacker News submission looks exactly like a 12× spike from a coordinated scrape attempt, and we'd notice neither.

The architectural opportunity is that **Caddy is the single chokepoint** for everything inbound — blog, Headscale, GitHub webhook. One log source feeds analytics, security, and AI. And **Frank already has the heavy stack** (Grafana, VictoriaMetrics, VictoriaLogs, fluent-bit, LiteLLM, Telegram bot) plus the mesh transport to Hop. The work reduces to: pick the lightest possible collectors for Hop, choose a log store that matches Frank's existing VM ecosystem, and wire an AI enrichment layer that's cheap to call and easy to swap. (Note: Frank has no Alertmanager — alerting is Grafana-managed via the existing `apps/grafana-alerting/manifests/` ConfigMaps.)

## Goals

- **Blog analytics that distinguish humans from bots.** Per-day unique visitors, top pages, top referrers, country breakdown, search-engine inbound traffic. Cookieless and GDPR-safe by design.
- **Caddy access logs persisted, queryable, and graphed.** 30-day retention for access logs in VictoriaLogs on Frank. Grafana Explore must answer arbitrary log questions (e.g., "all 5xx in the last hour from non-mesh IPs").
- **HTTP-layer threats blocked at the edge.** CrowdSec parses Caddy logs in real time, applies community + custom scenarios, pushes decisions to the Caddy bouncer module. Enforcement happens at Hop — observation aggregates on Frank.
- **Pod runtime threats detected and surfaced.** Falco DaemonSet on Hop (modern_ebpf driver) catches container-internal compromise patterns (shell-in-container, sensitive-file-read, unexpected outbound). Critical-severity events go straight to Telegram; everything else aggregates on Frank for correlation.
- **Anomalous traffic auto-detected with origin analysis.** `BlogTrafficSurge` alert with two tiers; AI helper produces a same-message verdict ("HN spike, benign" vs "scraper, CrowdSec mitigating" vs "investigate"). Alert delivery is independent of LLM uptime.
- **Daily LLM digest of "what happened on the blog yesterday."** One Telegram message at 08:00 UTC summarising traffic, top pages, top sources, security events. Cheap (≤1 LLM call/day for the digest path).
- **Designed for Sympozium swap-in.** A single Python module `ai_adapter.py` exposes two functions (`summarize`, `investigate`) — the contract is the fact-sheet shape. Replacing LiteLLM with Sympozium is one-file work, not a re-architecture.
- **Stays within Hop's resource budget.** Total memory added on Hop ≤ 250 MB. Each phase that touches Hop has a `kubectl describe node hop-1` budget check as exit criterion.

## Non-Goals

- **Not a full SIEM/XDR.** Wazuh and similar were considered and rejected (~1.5 GB manager overhead, rule-tuning burden disproportionate to one-node attack surface). If Hop grows to multiple edge nodes, revisit.
- **Not user-session analytics.** GoatCounter is intentionally limited to pageview + referrer + UA + country. No funnels, no scroll depth, no A/B testing. If we later need that, Umami is the next step — out of scope here.
- **Not multi-blog tracker hosting.** GoatCounter is scoped to `blog.derio.net` only. Adding a second site is trivial later but not implemented in this plan.
- **Not auto-remediation by AI.** AI enriches alerts; humans (or CrowdSec's own rule engine) take action. The "agent that proposes AND applies mitigations" tier was explicitly deferred — phase 5 ships read-only AI.
- **Not the Sympozium swap.** Phase 5 ships LiteLLM-backed `ai_adapter`. The Sympozium-backed adapter is a separate future plan whose existence is acknowledged here only so the seam is documented.
- **Not host file-integrity monitoring.** Talos is immutable; host FIM is largely pointless. Falco's value on Talos is **container** runtime monitoring via eBPF, not host filesystem watching.
- **Not Hop autonomy if Frank is down.** This was a deliberate topology choice. CrowdSec's bouncer enforces locally so request-path security survives Frank outage, but analytics, log retention, AI digests, and surge alerts go dark while Frank is unreachable. If Hop-autonomy becomes a requirement, this design needs to be re-opened.

## Architecture

```
┌──────────────── Hop (Hetzner CX23, 2 vCPU / 3.8 GiB) ─────────────┐      ┌──────────────────────── Frank ─────────────────────────┐
│                                                                    │      │                                                          │
│  Caddy (existing, JSON logs enabled)                               │      │  victoria-logs (existing app — extend with LB IP)        │
│   │                                                                │      │   FQDN:  victoria-logs-victoria-logs-single-server       │
│   ├─→ /var/log/containers ── fluent-bit (Hop, new)                 │      │           .monitoring.svc.cluster.local:9428             │
│   │                                │                               │      │   LB IP: 192.168.55.225:9428  (new, for Hop reach)       │
│   │                                └── HTTP POST /insert/jsonline ─┼──────┼─→ 192.168.55.225:9428                                   │
│   │                                                                │      │      │                                                   │
│   ├─→ shared log path ─→ crowdsec-agent (Hop)                      │      │      ├─→ Grafana (subchart of victoria-metrics)         │
│   │                       ├── parses, scenarios → decisions        │      │      │     • 3 new dashboards (sidecar ConfigMaps)      │
│   │                       └── LAPI on Hop ClusterIP                │      │      │     • GoatCounter datasource (Infinity)           │
│   │                                ▲                               │      │      │       (sidecar ConfigMap, label                  │
│   │  caddy-crowdsec-bouncer ──poll─┘ (local — no Frank dep)        │      │      │       grafana_datasource: "1")                   │
│   │                                                                │      │      │                                                   │
│   ├─→ Hugo blog ── JS snippet ──→ counter.derio.net ───────────────┼──────┼──→ goatcounter (new app, LB 192.168.55.224:8080)        │
│   │                              (Caddy reverse-proxy via mesh)    │      │      ▲   IngressRoute counter.cluster.derio.net          │
│   │                                                                │      │      │   (mesh-only via Traefik + Authentik)            │
│   └─→ falco DaemonSet (modern_ebpf, new) + falcosidekick           │      │                                                          │
│        │                                                           │      │  grafana-alerting (existing ConfigMaps — extend)         │
│        ├── critical ─────────────────────────────────────────────────────────→ Telegram direct (URGENT, delivery-guaranteed)        │
│        │    (falcosidekick Telegram output)                        │      │      │                                                   │
│        │                                                           │      │      ├── alert-rules-cm.yaml: append blog-edge group     │
│        └── routine ──HTTP→ 192.168.55.225 (VictoriaLogs LB IP)     │      │      │      • CrowdSecDecisionBurst (3-step A→B→C)       │
│                                                                    │      │      │      • FalcoCriticalEvent (3-step A→B→C)         │
│   ┌────── fluent-bit pushes Caddy/CrowdSec/Falco logs ────────────────────┤      ├── contact-points-cm.yaml: append "AI Helper       │
│   └────── over Tailscale subnet route to 192.168.55.0/24 ─────────────────┤      │     Webhook"                                      │
│                                                                    │      │      └── notification-policy-cm.yaml: route warning|     │
└────────────────────────────────────────────────────────────────────┘      │            critical+grafana_folder="blog-edge" → AI      │
                                                                            │            Helper Webhook                                │
                                                                            │             │                                            │
                                                                            │             ▼                                            │
                                                                            │   ai-alert-helper (new app, FastAPI, ~60 MB)             │
                                                                            │     • POST /alert  ← Grafana webhook                     │
                                                                            │     • POST /digest ← daily CronJob 08:00 UTC             │
                                                                            │     • POST /surge-check ← surge CronJob every 15m        │
                                                                            │     • ai_adapter.py ← swap point for Sympozium           │
                                                                            │     • LiteLLM client (existing gateway)                  │
                                                                            │     • Telegram client (existing @agent_zero_cc_bot)      │
                                                                            └──────────────────────────────────────────────────────────┘
```

### Why these choices

**Reuse existing VictoriaLogs.** The cluster already runs `victoria-logs-single` in namespace `monitoring` (chart `vm/victoria-logs-single`, release `victoria-logs`, 14d retention, 20 Gi Longhorn PVC). The plan extends it with a new `LoadBalancer` Service so Hop can push directly; retention is bumped from 14d → 30d to match the spec's access-log retention goal. The Grafana VictoriaLogs datasource is already provisioned (`apps/victoria-metrics/manifests/grafana-victorialogs-ds.yaml`).

**Reuse fluent-bit (Frank's proven pattern) on Hop.** Frank already runs `fluent-bit` as a DaemonSet (`apps/fluent-bit/`) that tails `/var/log/containers/*.log` and writes to VictoriaLogs via the HTTP `/insert/jsonline` endpoint. We deploy a second fluent-bit instance under `clusters/hop/apps/fluent-bit/` with the same proven config, targeting Frank's new VictoriaLogs LoadBalancer IP. Fluent-bit's `prometheus_exporter` filter is *not* used here — surge detection is in-helper, not in PromQL — see "AI loop design".

**Why an LB IP for VictoriaLogs (and not a cross-cluster ClusterIP).** Hop's Tailscale subnet router advertises only the home-LAN ranges (`192.168.10/50/55.0/24`, per `docs/superpowers/specs/2026-03-21--edge--subnet-router-autoapproval-design.md`). The kube service CIDR (`10.43.0.0/16`) is *not* advertised and Hop's CoreDNS doesn't know Frank's `.svc.cluster.local` zone. Adding a Cilium L2 `LoadBalancer` Service at `192.168.55.225` is the minimal change that makes VictoriaLogs reachable from Hop — and "192.168.55.225 from Hop" is the same path Caddy already uses to reach GoatCounter at `192.168.55.224`.

**Grafana datasources via sidecar ConfigMaps.** Grafana is a subchart of `victoria-metrics` (no `apps/grafana/values.yaml` exists). The provisioning pattern: a ConfigMap in namespace `monitoring` with label `grafana_datasource: "1"`, picked up by the Grafana provisioning sidecar. The VictoriaLogs datasource follows this pattern today; the new GoatCounter (Infinity plugin) datasource will too.

**Grafana-managed alerting (no Alertmanager).** Frank's VictoriaMetrics chart has Alertmanager and VMAlert disabled. All alerting is Grafana-managed: rules in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`, contact points in `contact-points-cm.yaml`, routing in `notification-policy-cm.yaml`. The plan extends each: adds a `blog-edge` rule group, an "AI Helper Webhook" contact point, and a routing entry. Rules use the 3-step A (data) → B (reduce) → C (threshold) format per Grafana 12.x SSE requirements (any 2-step format fails with `sse.parseError` — gotcha at `agents/rules/frank-gotchas.md`).

**Surge detection in the AI helper, not in Grafana alert rules.** Computing "median count over the same hour-of-day for the past 7 days" is awkward in both LogsQL (no `quantile_over_time`) and PromQL (subqueries are slow at low scrape rates with sparse data). The cleanest path: a 15-minute Kubernetes CronJob calls the AI helper's `/surge-check` endpoint; the helper queries VictoriaLogs for both the current 1h window and the historical baseline, computes the ratio in Python, and triggers the surge enrichment path on a hit. Latency: up to 15 min for surge detection, ~30s for the AI message. Acceptable for a blog-traffic anomaly.

**GoatCounter over Umami.** Single Go binary, SQLite default, ~40 MB. MIT-licensed. Cookieless. Shaped for one Hugo blog. Umami's richer event model (multi-site, custom events) isn't load-bearing here — YAGNI. The two products' switching costs are roughly symmetric (pageview history migrates via CSV either direction; custom-event history is lost), so we pick the smaller bet.

**CrowdSec over fail2ban.** Modern behavioural scenarios (not just regex matches), community blocklists, Caddy bouncer plugin is native. Decision-pull model means the bouncer doesn't have to consult Frank on every request — enforcement stays local to Hop.

**Falco modern_ebpf on Talos.** Talos has no kernel headers and no userland to load eBPF the legacy way. `modern_ebpf` attaches CO-RE programs via the kernel ABI directly — works on Talos out of the box. Container/Pod syscall coverage is the relevant scope; host-FS rules don't apply to an immutable OS.

**Two-tier surge detection.** A single threshold is either too noisy (catches weekly rhythm) or too quiet (misses moderately interesting events). `Notable` (3× baseline) is informational; `Major` (10× + 5× visitors) is "look at this now." Both tiers ride the same Python path inside the helper.

**Bouncer local, observation centralised.** Enforcement on the request path stays on Hop (no Frank-dependency for blocking); analysis and alerting aggregate on Frank. This is the right split for an edge-collector architecture — survivable degradation if the mesh flaps.

**Critical alerts bypass the AI helper.** Falcosidekick has a direct Telegram output for `priority >= critical`; that fires before the AI enrichment path runs. The Grafana `FalcoCriticalEvent` rule fires in parallel and produces an enriched follow-up. If LiteLLM is slow or down during an active incident, the direct page still arrives.

## Components — Hop side

### Caddy (existing, modified)

`apps/caddy/manifests/configmap.yaml` (already exists in `clusters/hop/`) — add JSON access logging globally:

```caddyfile
{
  email admin@derio.net
  acme_dns cloudflare {env.CF_API_TOKEN}
  log access {
    output stdout
    format json
    level INFO
  }
  order crowdsec first
  crowdsec {
    api_url http://crowdsec-lapi.crowdsec-system.svc:8080
    api_key {env.CROWDSEC_BOUNCER_KEY}
    ticker_interval 10s
  }
}

# Public blog route gains the bouncer + structured log fields
blog.derio.net {
  handle /frank* {
    crowdsec
    reverse_proxy blog.blog-system.svc:8080
  }
  handle {
    redir https://blog.derio.net/frank{uri} permanent
  }
}

# NEW: tracker ingest endpoint (reverse-proxied via mesh to GoatCounter on Frank)
# GoatCounter is exposed on Frank as a Cilium L2 LoadBalancer at 192.168.55.224,
# reachable from Hop via the Tailscale DaemonSet's subnet route to 192.168.55.0/24.
counter.derio.net {
  reverse_proxy 192.168.55.224:8080
}
```

Image change: `ghcr.io/derio-net/caddy-cloudflare:2.9` → a new build that includes the `caddy-crowdsec-bouncer` module. Built via the existing `clusters/hop/apps/caddy/Dockerfile`.

### fluent-bit DaemonSet (new on Hop — mirrors Frank's existing app)

`clusters/hop/apps/fluent-bit/`. Same Helm chart and config shape as Frank's existing `apps/fluent-bit/` (chart `fluent/fluent-bit`, release `fluent-bit`). Tails `/var/log/containers/*.log` (captures Caddy + CrowdSec + Falco logs from every Pod), applies the kubernetes filter for Pod metadata, and ships via HTTP to Frank's VictoriaLogs at `http://192.168.55.225:9428/insert/jsonline` (Cilium L2 LoadBalancer IP added in phase 1).

Resource budget: requests `cpu: 10m / memory: 40Mi`, limits `memory: 80Mi`. ~40 MB resident in practice — slightly more than the vlagent alternative would have been, but the trade is access to fluent-bit's proven Kubernetes-aware enrichment pipeline.

### crowdsec-agent DaemonSet (new)

`clusters/hop/apps/crowdsec/`. Helm chart: `crowdsecurity/crowdsec`. Configuration:

- Parsers + scenarios from `crowdsecurity/base-http-scenarios`, `crowdsecurity/http-cve`, `crowdsecurity/http-dos`
- Acquisition: Caddy access logs (shared volume with Caddy or via kubelet log path)
- LAPI exposed via ClusterIP service `crowdsec-lapi.crowdsec-system.svc:8080` so the Caddy bouncer can pull decisions locally
- Community blocklist subscription enabled (free tier; rotates via CrowdSec hub)
- Resource budget: requests `cpu: 50m / memory: 80Mi`, limits `memory: 128Mi`

Decisions are also written to a log stream that fluent-bit forwards to VictoriaLogs for the Grafana "Security events" dashboard.

### falco DaemonSet (new)

`clusters/hop/apps/falco/`. Helm chart: `falcosecurity/falco`. Configuration:

- Driver: `modern_ebpf` (the only viable choice on Talos — no kernel headers required, attaches CO-RE programs to the kernel ABI)
- Rules: stock `falco_rules.yaml` + targeted overrides in `falco_rules.local.yaml` to silence Talos-noisy rules. Macro/rule overrides are done by **re-declaring the macro/rule with the same name in a later-loaded rules file** (e.g., redefining `user_known_shell_in_container_activities` to include `(k8s.ns.name = "kube-system")`). There is no `override:` key in the Falco schema; the previously-loaded definition is replaced.
- Output: falcosidekick sidecar with two outputs configured: VictoriaLogs (via the new LB IP `192.168.55.225`) for routine events, Telegram direct for `priority >= critical`
- Resource budget: requests `cpu: 50m / memory: 100Mi`, limits `memory: 200Mi` (Falco itself + sidecar ~120 MB combined in practice)

### Resource budget on Hop

| Component | Memory request | Memory limit | Resident (est.) |
|---|---|---|---|
| fluent-bit | 40 Mi | 80 Mi | ~40 MB |
| crowdsec-agent | 80 Mi | 128 Mi | ~80 MB |
| falco + sidekick | 100 Mi | 200 Mi | ~120 MB |
| **Total new on Hop** | **220 Mi** | **408 Mi** | **~240 MB** |

Hop currently sits at 61% requests / 73% limits of 3263 Mi allocatable. After this plan: ~68% requests / ~85% limits. Memory limits hit the high-water mark — every phase that touches Hop must verify with `kubectl describe node hop-1` and adjust if a Pod is OOMKilled. **Fallback:** if phase 4's Falco deployment pushes the node past 88% limits, defer Falco as a separate rework plan and ship phases 1–3 + 5 (the surge-check path and the CrowdSecDecisionBurst alert remain useful; only `FalcoCriticalEvent` is lost).

## Components — Frank side

### victoria-logs (existing ArgoCD app — extended)

`apps/victoria-logs/`. Chart `vm/victoria-logs-single`, release `victoria-logs`, namespace `monitoring`. Currently 14d retention, 20 Gi Longhorn PVC, `ClusterIP` Service. Extended in phase 1:

- **Add a second Service of type `LoadBalancer`** at Cilium L2 IP `192.168.55.225` so Hop's fluent-bit can push directly. We add a sibling Service (not change the existing `ClusterIP`), so Frank-internal clients (fluent-bit on Frank, Grafana datasource) continue to use the existing FQDN.
- **Bump `retentionPeriod` from 14d to 30d** to match this spec's access-log retention goal. PVC may need to grow if disk pressure shows up — defer to ops.
- Existing Grafana datasource (`apps/victoria-metrics/manifests/grafana-victorialogs-ds.yaml`) continues to point at the in-cluster FQDN; no datasource change needed.
- The new LB IP must be registered in `agents/rules/frank-infrastructure.md`.

### goatcounter (new ArgoCD app)

`apps/goatcounter/`. GoatCounter has no first-party Helm chart; deploy via raw manifests (single Deployment + Service + PVC + ConfigMap). Namespace `goatcounter-system`. Configuration:

- Single replica, SQLite PVC (Longhorn, 1 GB), `strategy: Recreate` (RWO PVC)
- One configured site: `blog.derio.net/frank`
- Cilium L2 LoadBalancer Service at **`192.168.55.224`** (next free slot after the GitHub webhook receiver at `.223`). Register in `agents/rules/frank-infrastructure.md` as part of phase 2.
- IngressRoute via Traefik: `counter.cluster.derio.net` (mesh-only, Authentik forward-auth) for the admin/dashboard UI
- The public **ingest** endpoint is reached via Hop's Caddy at `counter.derio.net`, which reverse-proxies over the Tailscale mesh to `192.168.55.224:8080`. **Trusted-proxy config:** GoatCounter must be configured with `-real-ip-header=X-Forwarded-For` and a trust whitelist of Hop's mesh IP, otherwise every hit appears to originate from Hop's reverse-proxy address and country/bot breakdowns are destroyed.
- API token configured for the Grafana datasource to query GoatCounter from the "Blog overview" dashboard
- Resource budget: requests `cpu: 20m / memory: 40Mi`, limits `memory: 128Mi`

### Grafana dashboards (3 new) and the GoatCounter datasource

Grafana is a subchart of `victoria-metrics`. Dashboards and datasources are provisioned via sidecar ConfigMaps (labels `grafana_dashboard: "1"` / `grafana_datasource: "1"`) — same pattern as the existing `apps/victoria-metrics/manifests/grafana-victorialogs-ds.yaml`.

**New ConfigMap:** `apps/victoria-metrics/manifests/grafana-goatcounter-ds.yaml` — Infinity datasource pointing at `https://counter.cluster.derio.net` with the GoatCounter API token mounted from Infisical via the existing `grafana-secrets` ExternalSecret.

**New dashboard ConfigMaps** under `apps/grafana-alerting/manifests/dashboards-blog-edge/`:

1. **Blog overview** — daily/hourly unique visitors (GoatCounter), top pages (last 24h, 7d), top referrers, country breakdown, human-vs-bot pie, search-engine inbound counts.
2. **Security events** — CrowdSec decisions over time, top banned IPs, top matched scenarios, geographic clustering, Falco event count by severity, top Falco rule matches.
3. **Crawler & SE traffic** — known crawler User-Agent breakdown (GoogleBot, Bingbot, GPTBot, ClaudeBot, etc.), request rate per crawler, top pages crawled, robots.txt hit rate.

### Grafana alert rules and routing (extension of existing ConfigMaps)

Frank's alerting is entirely Grafana-managed (Alertmanager and VMAlert are disabled in `apps/victoria-metrics/values.yaml`). The plan extends three existing ConfigMaps in `apps/grafana-alerting/manifests/`:

**`alert-rules-cm.yaml`** — append a `blog-edge` rule group with the following rules. Every rule uses the 3-step `A` (data, datasource UID) → `B` (reduce, `__expr__`) → `C` (threshold, `__expr__`) format. Anything less than 3 steps fails Grafana 12.x's SSE engine with `sse.parseError`. Folder: `blog-edge`.

- **CrowdSecDecisionBurst** — A: `count_over_time({stream="crowdsec",msg=~".*ban.*"}[5m])` on VictoriaLogs; B: `reduce(A, last, dropNN)`; C: `B > 10`; `for: 1m`; severity: warning.
- **FalcoCriticalEvent** — A: `count_over_time({stream="falco",priority="Critical"}[5m])` on VictoriaLogs; B: `reduce(A, last, dropNN)`; C: `B > 0`; `for: 0s`; severity: critical.

Surge alerts (`BlogTrafficSurgeNotable`, `BlogTrafficSurgeMajor`) are **not Grafana rules** — surge detection lives in the AI helper via the `/surge-check` CronJob, because the baseline computation is awkward in LogsQL and noisy in PromQL with sparse log-derived metrics.

**`contact-points-cm.yaml`** — append:

```yaml
- orgId: 1
  name: "AI Helper Webhook"
  receivers:
    - uid: ai-alert-helper-webhook
      type: webhook
      settings:
        url: "http://ai-alert-helper.ai-alert-helper-system.svc.cluster.local:8080/alert"
        httpMethod: POST
```

**`notification-policy-cm.yaml`** — append a route under the existing root policy:

```yaml
- receiver: "AI Helper Webhook"
  matchers:
    - grafana_folder = "blog-edge"
  continue: false
```

The `continue: false` means `blog-edge` alerts go to the AI helper and *not* the existing Telegram contact point. The AI helper does its own Telegram delivery via the existing bot — this avoids duplicate messages while preserving the option for the helper to suppress noisy alerts later.

### ai-alert-helper (new ArgoCD app)

`apps/ai-alert-helper/`. A ~250-LOC FastAPI service. Namespace `ai-alert-helper-system`. Resource budget: requests `cpu: 20m / memory: 40Mi`, limits `memory: 128Mi`.

**File layout:**
```
apps/ai-alert-helper/manifests/
  deployment.yaml
  service.yaml
  configmap-app.yaml      # prompts, schedule, model names
  cronjob-digest.yaml     # Kubernetes CronJob at 08:00 UTC daily
  cronjob-surge-check.yaml  # Kubernetes CronJob every 15m
  externalsecret.yaml     # ExternalSecret → LITELLM_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OBS_GOATCOUNTER_API_TOKEN
```

**Module structure:**
```
ai_alert_helper/
  __init__.py
  api.py              # FastAPI: POST /alert, POST /digest, POST /surge-check, GET /healthz
  facts.py            # fact-sheet builders (queries VictoriaLogs + GoatCounter)
  surge.py            # baseline computation + threshold logic for /surge-check
  ai_adapter.py       # the swap point: summarize() / investigate()
  telegram.py         # delivery
  prompts/
    digest.txt
    investigate-generic.txt
    investigate-surge.txt
```

`ai_adapter.py` v1 uses the existing LiteLLM gateway. Default model: `qwen-think-14b` (local, free, ample for this task). The `_call()` function has a single retry-with-fallback to `claude-haiku-4-5` (via LiteLLM virtual key) on timeout or 5xx, so a slow local model doesn't drop alerts.

**The swap contract (do not change without a follow-up plan):**
```python
def summarize(facts: dict) -> str:
    """Daily digest. ~200 word narrative from a structured facts dict."""

def investigate(alert: dict, facts: dict) -> str:
    """Alert enrichment. 1-paragraph 'what happened, what's the risk' from
    a Grafana webhook payload + a fact sheet specialised to the alert type."""
```

Sympozium-backed v2 replaces only these two function bodies. The facts.py builder, surge.py logic, telegram.py delivery, and FastAPI handlers stay identical.

## Data flow

### Human visit
1. Reader's browser → Caddy on Hop → blog Pod
2. Caddy emits a JSON access log line `{ts, host, uri, status, ua, referer, remote_ip, duration}` to stdout (captured by `/var/log/containers/`)
3. fluent-bit on Hop tails the log file, applies the kubernetes filter for Pod metadata, and POSTs to `http://192.168.55.225:9428/insert/jsonline` (Frank's VictoriaLogs LB IP)
4. Browser executes Hugo's GoatCounter JS snippet → POSTs `/count` to `counter.derio.net`
5. Hop's Caddy reverse-proxies the POST over the mesh to `192.168.55.224:8080` (Frank's GoatCounter LB IP)
6. GoatCounter records the pageview (cookieless, daily-rotating hashed session ID), respecting `X-Forwarded-For` to record the real reader IP
7. Grafana's "Blog overview" dashboard reads from both sources — humans (GoatCounter) and everything (VictoriaLogs)

### Crawler visit
1. Same as human path 1–3
2. JS never executes; only the Caddy log records the request
3. Grafana's "Crawler & SE traffic" dashboard classifies known bots by User-Agent from VictoriaLogs queries

### Attack/scan
1. Attacker hits `/wp-login.php`, `/.env`, etc.
2. Caddy logs each request as normal
3. CrowdSec agent (reading the same Caddy log path on Hop) matches `crowdsecurity/http-probing` or similar scenario → emits a **decision** (ban IP for 4h)
4. CrowdSec writes the decision to its LAPI (Hop-local ClusterIP)
5. caddy-crowdsec-bouncer module polls the LAPI every 10s → next request from that IP returns 403 at Caddy
6. CrowdSec's decision log line goes to stdout → fluent-bit → Frank's VictoriaLogs
7. Grafana's `CrowdSecDecisionBurst` rule evaluates the LogsQL count over the last 5m. On threshold breach, the alert routes through the new `blog-edge` folder → notification policy → **AI Helper Webhook** contact point → `POST /alert` on `ai-alert-helper` → fact sheet + LLM + Telegram

### Container compromise
1. Attacker (via app CVE) gets RCE inside the Caddy or blog Pod
2. Their shell exec's `/bin/sh`
3. Falco's eBPF probe sees the `execve` in that container's cgroup → matches `Terminal shell in container` rule
4. Falcosidekick sidecar dual-publishes:
   - Telegram direct (immediate, URGENT) — bypasses the AI helper to guarantee delivery
   - VictoriaLogs (for the dashboard and for AI helper to correlate against Caddy logs)
5. Grafana's `FalcoCriticalEvent` rule also fires within 1 min → AI Helper Webhook → enriched follow-up Telegram message (the "story" version)

### Traffic surge
1. Background: Caddy logs continuously stream into VictoriaLogs
2. Every 15 min: Kubernetes CronJob `surge-check` calls `POST /surge-check` on the AI helper
3. The helper's `surge.py` queries VictoriaLogs for (a) request count in the last 1h and (b) hour-of-day baseline (median of the same hour across the last 7 days)
4. If `ratio_1h := current/baseline > 3` (Notable) or `> 10` (Major), AND for Major the unique-visitor ratio from GoatCounter > 5, the helper proceeds to build the **surge fact sheet** (see next section)
5. `ai_adapter.investigate({alertname: BlogTrafficSurgeNotable|Major}, surge_facts)` → narrative
6. Telegram message with verdict ("HN spike, benign" / "scraper, CrowdSec mitigating" / "investigate"); the message is tagged URGENT for Major

## Surge detection — fact sheet

When `BlogTrafficSurge*` fires, `facts.py` builds:

```python
surge_facts = {
    "window":                  {"start": ..., "end": ..., "peak_rps_minute": ...},
    "total_requests_window":   N,
    "unique_visitors_window":  N,                          # GoatCounter
    "baseline_for_window":     N,                          # hour-of-day median, 7d
    "human_vs_bot": {
        "humans":          0.96,
        "known_crawlers":  0.03,
        "unknown_ua":      0.01,
    },
    "top_referrers":           [{host, count, share}],     # top 10
    "top_pages":               [{path, count, share}],     # top 10
    "geo_breakdown":           [{country, count, share}],  # top 10
    "ua_skew":                 [{ua_family, count}],       # top 10 — flags scrapers
    "status_distribution":     {"2xx": 0.97, "3xx": 0.02, "4xx": 0.01, "5xx": 0.0},
    "shape":                   "spike" | "sustained" | "stepped",
    "crowdsec_decisions":      N,                          # decisions issued during window
}
```

The **human-vs-bot ratio plus visitor-to-request ratio is the discriminator** the LLM keys off:
- High visitor count, high request count, dominant external referrer → viral hit
- Low visitor count, high request count, single UA, single IP range → scraper
- Low visitor count, high request count, varied UAs, varied IPs, high 4xx → distributed scan

These ratios are *pre-computed facts* handed to the LLM, not patterns the LLM is expected to derive from raw logs. This is critical for cost (prompt cache hits) and reliability (no hallucinated counts).

### Example messages

> 🔥 **Blog traffic surge — 12× baseline (Major)**
> Last 60 min: 1,840 requests / 410 unique visitors (baseline 35).
> **Likely cause:** 73% from `news.ycombinator.com` referrer, concentrated on `/frank/papers/15-ingress-and-service-catalog/`. Classic HN spike — sharp ramp at 19:14 UTC, plateauing now.
> **Risk read:** Benign. 96% humans, 0 CrowdSec decisions in window, 4xx rate 1.2%.
> **What to look at:** Blog overview dashboard, Paper 15.

> 🔥 **Blog traffic surge — 8× baseline (Notable)**
> Last 60 min: 1,200 requests / 18 unique visitors. Visitor:request ratio 1:66 — not human.
> **Likely cause:** Single /16 from Bulgaria, walking the sitemap. UA `python-requests/2.31`. 47 CrowdSec decisions issued.
> **Risk read:** Scraper. CrowdSec mitigating.
> **What to look at:** Confirm bouncer dropping; consider tightening parsers if surge persists.

## AI loop design

### Daily digest (entrypoint 1)

Kubernetes CronJob in `apps/ai-alert-helper/manifests/cronjob-digest.yaml`, schedule `0 8 * * *` (08:00 UTC). The CronJob's container runs `curl -sf -X POST http://ai-alert-helper:8080/digest`. The helper then:

1. Queries GoatCounter API: yesterday's uniques, top pages, top referrers, country breakdown
2. Queries VictoriaLogs: yesterday's request count, status distribution, top User-Agents (humans vs bots), CrowdSec decision count, Falco event count
3. Builds a structured fact sheet (JSON)
4. `ai_adapter.summarize(facts)` → ~200-word narrative
5. Posts to Telegram via `@agent_zero_cc_bot`

Token cost: prompt template + ~2 KB facts → ~3 KB total → effectively free at `qwen-think-14b` local rates.

### Alert enrichment (entrypoint 2)

POST `/alert` from Grafana's "AI Helper Webhook" contact point. Steps:

1. Parse the Grafana webhook payload (rule name from `alerts[].labels.alertname`, time window from `alerts[].startsAt`/`endsAt`)
2. `facts.py.build_for_alert(alert)` returns the alert-type-specialised fact sheet (dispatches on alert name to `build_for_security` / `build_for_falco`)
3. `ai_adapter.investigate(alert, facts)` → 1-paragraph verdict
4. Post to Telegram (no native threading — Grafana webhook payload doesn't expose a parent message ID)

### Surge check (entrypoint 3)

POST `/surge-check` from a Kubernetes CronJob every 15 min. The endpoint:

1. `surge.compute()` queries VictoriaLogs for (a) count of `blog.derio.net` requests in the last 1h and (b) median of `count_over_time(...) at hour-of-day` over the last 7 days. Both queries use the existing LogsQL `stats by (host) count() as count` shape — no PromQL, no new scrape configs.
2. If ratio < 3 → return `{triggered: false}` and exit.
3. If ratio ≥ 3 → `facts.build_for_surge(window_start, window_end)` builds the rich fact sheet (top referrers, top pages, geo, human-vs-bot, status distribution, shape).
4. Determine tier: `Major` if `ratio ≥ 10` AND `unique_visitor_ratio ≥ 5`; else `Notable`.
5. `ai_adapter.investigate({alertname: "BlogTrafficSurge" + tier}, surge_facts)` → narrative.
6. Post to Telegram (URGENT label for Major; standard for Notable).

### Prompt structure

All prompts (`prompts/*.txt`) follow the same shape:

```
<system>
You are Frank's blog observatory. You receive structured facts and produce
short, direct narratives. Never invent numbers. Cite specific paths, IPs, or
referrers when they appear in facts. If facts are missing, say so — do not
extrapolate.
</system>

<task>
[per-prompt task description]
</task>

<facts>
{JSON dump}
</facts>

<output_format>
[expected format — prose paragraph, Telegram-markdown-safe]
</output_format>
```

This keeps the **system prompt constant** across all calls (good for prompt caching), with only the `<task>` and `<facts>` varying. Token cost stays flat per call.

## Notification routing summary

| Event | Path | Channel |
|---|---|---|
| Daily digest | CronJob → `POST /digest` → `summarize` → Telegram | Standard, 08:00 UTC |
| CrowdSec decision burst | Grafana rule → AI Helper Webhook → `investigate` → Telegram | Standard |
| Falco routine event | fluent-bit → VictoriaLogs only | None (dashboard) |
| Falco critical event | falcosidekick direct → Telegram + Grafana rule → AI Helper Webhook → `investigate` → Telegram | URGENT (direct first) + Standard (enriched follow-up) |
| BlogTrafficSurge Notable | surge-check CronJob → `surge.compute` → `investigate` (surge facts) → Telegram | Standard |
| BlogTrafficSurge Major | surge-check CronJob → `surge.compute` → `investigate` (surge facts) → Telegram | URGENT |

## Implementation phases

### Phase 1 — Log plumbing
- Edit existing `apps/victoria-logs/values.yaml`: bump retention 14d → 30d; add a sibling `LoadBalancer` Service at `192.168.55.225` (the existing `ClusterIP` Service is preserved for Frank-internal clients).
- Register the new LB IP in `agents/rules/frank-infrastructure.md`.
- Switch Hop's Caddy ConfigMap to JSON access logs.
- New `clusters/hop/apps/fluent-bit/` ArgoCD app mirroring Frank's `apps/fluent-bit/` config, output targets `http://192.168.55.225:9428/insert/jsonline`.
- Smoke: search recent Caddy logs in Grafana Explore via the existing VictoriaLogs datasource.
- **Exit criteria:** logs visible in Grafana for `host=blog.derio.net` filter; Hop memory usage within budget.

### Phase 2 — Blog analytics
- New `apps/goatcounter/` ArgoCD app on Frank (raw manifests — no first-party Helm chart), SQLite PVC, LoadBalancer at `192.168.55.224`, `-real-ip-header=X-Forwarded-For` trusted-proxy config.
- New IngressRoute `counter.cluster.derio.net` (mesh-only, Authentik forward-auth) for admin UI. Authentik proxy provider added; manual outpost-provider assignment via Django ORM (per `agents/rules/frank-argocd.md`).
- Hop's Caddy gains `counter.derio.net` route reverse-proxying to `192.168.55.224:8080`.
- DNS record `counter.derio.net` → Hop's public IP.
- Hugo partial `blog/layouts/partials/goatcounter.html` injected via global head extension.
- New sidecar ConfigMap `apps/victoria-metrics/manifests/grafana-goatcounter-ds.yaml` provisions the Infinity datasource.
- "Blog overview" Grafana dashboard ConfigMap.
- **Exit criteria:** dashboard shows >0 visitors after self-test; Hop memory unchanged.

### Phase 3 — Edge security
- `clusters/hop/apps/caddy/Dockerfile` rebuilt with `caddy-crowdsec-bouncer` module; new image tag rolled.
- Caddy Deployment kept on `strategy: Recreate` (existing); hostPort + RollingUpdate would deadlock.
- New `clusters/hop/apps/crowdsec/` ArgoCD app with community blocklists + http scenarios.
- Caddy ConfigMap gains `crowdsec` global directive + bouncer config; bouncer API key sourced from Infisical via ExternalSecret.
- "Security events" Grafana dashboard ConfigMap.
- New `blog-edge` rule group appended to `apps/grafana-alerting/manifests/alert-rules-cm.yaml` with the `CrowdSecDecisionBurst` rule (3-step A→B→C).
- New "AI Helper Webhook" contact point appended to `contact-points-cm.yaml`; new route appended to `notification-policy-cm.yaml`.
- Smoke: `for i in $(seq 1 12); do curl -s -o /dev/null https://blog.derio.net/wp-login.php; done` from a controlled IP → next request returns 403.
- **Exit criteria:** decision count > 0 in Grafana; controlled IP blocked.

### Phase 4 — Host runtime monitoring
- New `clusters/hop/apps/falco/` ArgoCD app with `driver.kind: modern_ebpf` + falcosidekick sidecar.
- Local rule overrides via re-declaration (not `override:`) of macros to silence Talos-noisy patterns.
- Falcosidekick configured: VictoriaLogs output → `http://192.168.55.225:9428/...` for all events; Telegram output for `priority >= critical` only.
- `FalcoCriticalEvent` rule appended to the `blog-edge` rule group (3-step A→B→C).
- Smoke: `kubectl exec -n blog-system deploy/blog -- sh -c 'id; exit'` (from authorised admin) → Falco event in Telegram within 5s.
- **Exit criteria:** Falco event count > 0 in Grafana; controlled exec test triggers Telegram; Hop memory within budget.

### Phase 5 — AI helper & surge detection
- New `apps/ai-alert-helper/` ArgoCD app: FastAPI service, ExternalSecret for LiteLLM + Telegram + GoatCounter secrets
- Kubernetes CronJob `digest-daily` at 08:00 UTC (HTTP POST to `/digest`)
- Kubernetes CronJob `surge-check` every 15m (HTTP POST to `/surge-check`)
- `ai_adapter.py` LiteLLM-backed implementation with retry-fallback model
- Prompts committed in `prompts/` (digest, investigate-generic, investigate-surge)
- Smoke: synthetic load (`hey -z 2m -c 50 https://blog.derio.net/frank/papers/00-why-homelab-in-2026/`) → within 15 min, surge-check fires the scraper-archetype branch → AI helper builds surge fact sheet → Telegram URGENT message received
- Smoke: receive next morning's 08:00 UTC digest
- **Exit criteria:** synthetic surge fully traced end-to-end; daily digest received; no LLM error rate

### Phase 6 — Post-deploy
- New Paper: "Edge Observability — Watching Frank's Edge Without Watching Frank's Edge Burn" (working title), slotted in the papers series sequence
- New building post on the obs layer
- New operating post (commands: query Grafana, force a CrowdSec decision, tune a Falco rule, suppress an alert)
- `/update-readme` to add the new layer to Technology Stack, Repository Structure, Service Access, Current Status
- `/sync-runbook` for any `# manual-operation` blocks (Falco rule tuning ritual, CrowdSec community blocklist enrollment, GoatCounter initial site creation)
- Plan status set to `Deployed`
- **Exit criteria:** standard layer checklist complete; blog posts published; README sections updated

## Resource budget

### Hop (new)

| Component | mem req | mem lim | Notes |
|---|---|---|---|
| fluent-bit | 40 Mi | 80 Mi | log shipper (mirrors Frank pattern) |
| crowdsec-agent | 80 Mi | 128 Mi | + community blocklists |
| falco + sidekick | 100 Mi | 200 Mi | modern_ebpf |
| **Total** | **220 Mi** | **408 Mi** | |

Hop pre-plan: 61% req / 73% lim on 3263 Mi. Post-plan target: ~68% / ~85%. If phase 4's Falco deployment pushes the node past 88% lim, defer Falco as a separate rework plan and ship phases 1–3 + 5.

### Frank (new and modified)

| Component | mem req | mem lim | Storage |
|---|---|---|---|
| victoria-logs (existing) | unchanged | unchanged | grow PVC if 30d retention exceeds 20 Gi |
| goatcounter (new) | 40 Mi | 128 Mi | ~1 GB (SQLite, growth-bounded) |
| ai-alert-helper (new) | 40 Mi | 128 Mi | none |

Frank has multi-GB headroom across worker nodes — this is rounding error.

## Future work (out of scope for this plan)

- **Sympozium swap.** Replace `ai_adapter.py`'s LiteLLM calls with a Sympozium multi-agent debate. Same `summarize` / `investigate` signatures, same fact-sheet shape. Plan would be filed under the `orch` layer.
- **Auto-remediation.** Agent that proposes AND applies CrowdSec rules from novel patterns. Risk-heavy; defer until we have weeks of clean telemetry to baseline what novel even means.
- **Multi-site analytics.** If a second public site joins Hop, switch GoatCounter to multi-site config (one-line change) or migrate to Umami if richer events become necessary.
- **Loki migration.** Only if a future use case actually needs Loki-specific features (e.g., LogQL JOINs against Prometheus). VictoriaLogs covers all current requirements.
- **Frank-side Falco.** Extending host/Pod runtime monitoring to Frank's workers is a separate plan with its own resource picture (Frank has plenty of headroom but the rule-tuning surface is larger).

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-05-23--obs--hop-blog-edge-monitoring | `derio-net/frank` | `docs/superpowers/plans/2026-05-23--obs--hop-blog-edge-monitoring/` | — |

## Open questions

- **Paper title and number.** "Edge Observability" is the working title; the canonical slot number depends on which papers have shipped by the time we author this one. Decide at paper-writing time, not plan time.
- **GoatCounter retention.** Default is forever. Recommend setting a 1-year cap to keep the SQLite file small; revisit if we want longer historical views.
- **Falco rule-tuning cadence.** First two weeks will be noisy. Plan to do a tuning pass after week 1 and week 2 to suppress workload-specific false positives. Document in operating post.
