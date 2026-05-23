# Hop Blog Edge Monitoring — Traffic Analytics, Edge Security & AI-Enriched Alerts

**Layer:** obs
**Date:** 2026-05-23
**Status:** Approved — ready for plan

## Summary

Hop (Hetzner CX23, 2 vCPU / 3.8 GiB) currently has no observability for the public blog at `blog.derio.net/frank`. There are no analytics, no log retention beyond container stdout, no edge security beyond Caddy defaults, and no node-level intrusion monitoring. This spec adds all three concerns on a single telemetry plane.

The design is **collectors-on-Hop, backend-on-Frank**: Hop runs only thin agents (~230 MB total) that ship to Frank over the existing Headscale/Tailscale mesh, where Grafana, VictoriaMetrics, Alertmanager, and the LiteLLM gateway already live. The new Frank-side components are VictoriaLogs (log store), GoatCounter (cookieless analytics), and `ai-alert-helper` (FastAPI service that produces a daily LLM digest and enriches every alert with a human-readable "what happened, what's the risk" narrative).

A `BlogTrafficSurge` alert with two severity tiers (Notable: 3× baseline, Major: 10× baseline + 5× unique visitors) fires whenever blog traffic deviates from the hour-of-day baseline. The AI helper investigates surges with a specialized fact sheet (top referrers, top pages, geo, human-vs-bot ratio, status distribution, time shape) and tells you in one paragraph whether it looks like a Hacker News spike, a scraper, or something hostile. CrowdSec handles HTTP-layer blocking at the Caddy edge; Falco's modern_ebpf driver watches Pod syscalls for runtime threats and bypasses the AI helper for critical events (delivery-must-not-depend-on-LLM-uptime).

The AI helper is built around a fact-sheet contract so its body can be swapped from LiteLLM to Sympozium later as a one-module change.

## Motivation

The blog is the public face of the Frank project — every paper, every building post, every operating post lives there. We have zero visibility today into:

1. **Who reads what.** No analytics. We don't know how many unique readers visited, where they came from, which papers actually get read, which search engines index us.
2. **What attacks the public edge.** Caddy runs with default rate-limits (none). A scraper or vulnerability scanner pounding the blog would be invisible until the node OOM'd or Hetzner billed for egress. No record of *who* is probing, *what* they're probing for, or *whether* they got anywhere.
3. **What happens inside Hop's Pods at runtime.** If a Caddy CVE landed and someone got code-execution in the Caddy Pod, we'd find out from external symptoms (defacement, egress alert) rather than from a syscall-level event. Talos's immutable base mitigates some of this, but not container-internal compromise.
4. **Whether something is unusual.** No baseline traffic shape, no anomaly detection. A 12× traffic spike from a successful Hacker News submission looks exactly like a 12× spike from a coordinated scrape attempt, and we'd notice neither.

The architectural opportunity is that **Caddy is the single chokepoint** for everything inbound — blog, Headscale, GitHub webhook. One log source feeds analytics, security, and AI. And **Frank already has the heavy stack** (Grafana, VictoriaMetrics, Alertmanager, LiteLLM, Telegram bot) plus the mesh transport to Hop. The work reduces to: pick the lightest possible collectors for Hop, choose a log store that matches Frank's existing VM ecosystem, and wire an AI enrichment layer that's cheap to call and easy to swap.

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
┌──────────────── Hop (Hetzner CX23, 2 vCPU / 3.8 GiB) ───────────────┐      ┌──────────────────────── Frank ─────────────────────────┐
│                                                                      │      │                                                          │
│  Caddy (existing, JSON logs enabled)                                 │      │  victoria-logs ◄────────── vlagent (Hop)                 │
│   │                                                                  │      │     │                                                    │
│   ├─→ shared volume ─→ crowdsec-agent ── decisions ──→ caddy-bouncer │      │     ├─→ Grafana (existing) ── 3 new dashboards          │
│   │                                                   (block/captcha)│      │     │      • Blog overview                              │
│   │                                                                  │      │     │      • Security events                            │
│   ├─→ Hugo blog ── JS snippet ──→ counter.derio.net ─────────────────┼──────┼──→ goatcounter (UI: counter.cluster.derio.net mesh-only)│
│   │                              (Caddy reverse-proxy via mesh)      │      │     ▲                                                    │
│   │                                                                  │      │     └── Grafana datasource                              │
│   └─→ falco DaemonSet (modern_ebpf) + falcosidekick                  │      │                                                          │
│                            │                                         │      │  alertmanager (existing) ──→ ai-alert-helper           │
│                            ├──── critical ─────────────────────────────────────────────────────────────→ Telegram (URGENT)            │
│                            │    (bypasses AI; delivery guarantee)    │      │     │                              ▲                    │
│                            └──── routine ──→ victoria-logs           │      │     │   ┌──────────────────────────┘                    │
│                                                                      │      │     ▼   │                                               │
│  vlagent DaemonSet (tails Caddy + CrowdSec + Falco logs)             │      │   ai-alert-helper (FastAPI, ~60 MB)                    │
│   │                                                                  │      │     • daily digest CronJob (08:00 UTC)                 │
│   └────── ships over Tailscale mesh ─────────────────────────────────┼──────┤     • alertmanager webhook receiver                    │
│                                                                      │      │     • ai_adapter.py ←─ swap point for Sympozium        │
└──────────────────────────────────────────────────────────────────────┘      │     • LiteLLM client (existing gateway)                │
                                                                              │     • Telegram client (existing @agent_zero_cc_bot)    │
                                                                              └────────────────────────────────────────────────────────┘
```

### Why these choices

**VictoriaLogs over Loki.** Frank already runs VictoriaMetrics. Same vendor, same operational model, no JVM, ~100 MB resident. Grafana datasource is mature. Avoids running Loki's heavier Promtail sidecar pattern on Hop — the matching agent `vlagent` is ~30 MB.

**GoatCounter over Umami.** Single Go binary, SQLite default, ~40 MB. MIT-licensed. Cookieless. Shaped for one Hugo blog. Umami's richer event model (multi-site, custom events) isn't load-bearing — YAGNI.

**CrowdSec over fail2ban.** Modern behavioural scenarios (not just regex matches), community blocklists, Caddy bouncer plugin is native. Decision-pull model means the bouncer doesn't have to consult Frank on every request.

**Falco modern_ebpf over kmod or ebpf-legacy on Talos.** Talos has no kernel headers and no userland to load eBPF the legacy way. modern_ebpf attaches CO-RE programs via the kernel ABI directly — works on Talos out of the box. Container/Pod syscall coverage is the relevant scope; host-FS rules don't apply to an immutable OS.

**Two-tier surge detection.** A single threshold is either too noisy (catches weekly rhythm) or too quiet (misses moderately interesting events). `Notable` (3× baseline) is informational; `Major` (10× + 5× visitors) is "look at this now." Same rule structure, different severity labels, same enrichment path.

**Bouncer local, observation centralised.** Enforcement on the request path stays on Hop (no Frank-dependency for blocking); analysis and alerting aggregate on Frank. This is the right split for an edge-collector architecture — survivable degradation if the mesh flaps.

**Critical alerts bypass the AI helper.** Falcosidekick dual-publishes critical events: VictoriaLogs (for context) AND Telegram (direct). The AI enrichment is *nice-to-have* on top of a *must-deliver* signal. If LiteLLM is slow or down during an active incident, the page still arrives.

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
    api_url http://crowdsec.crowdsec-system.svc:8080
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

### vlagent DaemonSet (new)

`clusters/hop/apps/observability/manifests/vlagent.yaml`. Tails Caddy stdout via the kubelet's `/var/log/pods` path (read-only hostPath mount); also tails CrowdSec and Falco log streams via Kubernetes API watch. Pushes to `victoria-logs.observability.svc.cluster.local:9428` on Frank via mesh IP.

Resource budget: requests `cpu: 10m / memory: 32Mi`, limits `memory: 64Mi`. ~30 MB resident in practice.

### crowdsec-agent DaemonSet (new)

`clusters/hop/apps/crowdsec/`. Helm chart: `crowdsecurity/crowdsec`. Configuration:

- Parsers + scenarios from `crowdsecurity/base-http-scenarios`, `crowdsecurity/http-cve`, `crowdsecurity/http-dos`
- Acquisition: Caddy access logs (shared volume with Caddy or via kubelet log path)
- LAPI exposed via ClusterIP service `crowdsec.crowdsec-system.svc:8080` so the Caddy bouncer can pull decisions locally
- Community blocklist subscription enabled (free tier; rotates via CrowdSec hub)
- Resource budget: requests `cpu: 50m / memory: 80Mi`, limits `memory: 128Mi`

Decisions are also written to a log stream that vlagent forwards to VictoriaLogs for the Grafana "Security events" dashboard.

### falco DaemonSet (new)

`clusters/hop/apps/falco/`. Helm chart: `falcosecurity/falco`. Configuration:

- Driver: `modern_ebpf` (the only viable choice on Talos — no kernel headers required, attaches CO-RE programs to the kernel ABI)
- Rules: stock `falco_rules.yaml` + targeted overrides in `falco_rules.local.yaml` to silence Talos-noisy rules (e.g., "shell-in-container" is irrelevant for `kubectl exec` debugging sessions; we'll allow exec from `kube-system` while keeping it as a critical signal for other namespaces)
- Output: falcosidekick sidecar with two outputs configured: VictoriaLogs for routine events, Telegram direct for critical-severity
- Resource budget: requests `cpu: 50m / memory: 100Mi`, limits `memory: 200Mi` (Falco itself + sidecar ~120 MB combined in practice)

### Resource budget on Hop

| Component | Memory request | Memory limit | Resident (est.) |
|---|---|---|---|
| vlagent | 32 Mi | 64 Mi | ~30 MB |
| crowdsec-agent | 80 Mi | 128 Mi | ~80 MB |
| falco + sidekick | 100 Mi | 200 Mi | ~120 MB |
| **Total new on Hop** | **212 Mi** | **392 Mi** | **~230 MB** |

Hop currently sits at 61% requested / 73% limits of 3263 Mi allocatable. After this plan: ~68% requested / ~85% limits. Memory limits hit the high-water mark — every phase that touches Hop must verify with `kubectl describe node hop-1` and adjust if a Pod is OOMKilled.

## Components — Frank side

### victoria-logs (new ArgoCD app)

`apps/victoria-logs/`. Helm chart: `vm/victoria-logs-single` (or the operator-managed CR if we standardise on `vm-operator`). Configuration:

- Single-instance, PVC-backed (Longhorn). Retention: 30 days for `severity=info` (access logs), 90 days for `severity>=warn` (security events). Storage estimate: ~5 GB for 30 days of Hop's traffic at current levels.
- Grafana datasource provisioned via `apps/grafana/values.yaml` additional-datasources block.
- Exposed within the cluster as `victoria-logs.observability.svc.cluster.local:9428`. Mesh-reachable so vlagent on Hop can push directly.
- Resource budget: requests `cpu: 100m / memory: 200Mi`, limits `memory: 512Mi`.

### goatcounter (new ArgoCD app)

`apps/goatcounter/`. The chart is community-maintained but trivial (single binary, SQLite). Configuration:

- Single replica, SQLite PVC (Longhorn, 1 GB)
- One configured site: `blog.derio.net/frank`
- Cilium L2 LoadBalancer Service at **`192.168.55.224`** (next free slot after the GitHub webhook receiver at `.223`). Register the new IP in `agents/rules/frank-infrastructure.md` as part of phase 2.
- IngressRoute via Traefik: `counter.cluster.derio.net` (mesh-only, Authentik forward-auth) for the admin/dashboard UI
- The public **ingest** endpoint is reached via Hop's Caddy at `counter.derio.net`, which reverse-proxies over the Tailscale mesh to `192.168.55.224:8080`. This keeps GoatCounter itself never directly internet-exposed.
- API token configured for the Grafana datasource to query GoatCounter from the "Blog overview" dashboard
- Resource budget: requests `cpu: 20m / memory: 40Mi`, limits `memory: 128Mi`

### Grafana dashboards (3 new)

Provisioned as ConfigMaps under `apps/grafana-alerting/manifests/dashboards-blog-edge/`:

1. **Blog overview** — daily/hourly unique visitors (GoatCounter), top pages (last 24h, 7d), top referrers, country breakdown, human-vs-bot pie, search-engine inbound counts.
2. **Security events** — CrowdSec decisions over time, top banned IPs, top matched scenarios, geographic clustering, Falco event count by severity, top Falco rule matches.
3. **Crawler & SE traffic** — known crawler User-Agent breakdown (GoogleBot, Bingbot, GPTBot, ClaudeBot, etc.), request rate per crawler, top pages crawled, robots.txt hit rate.

### Alertmanager rules (new)

Added to `apps/grafana-alerting/manifests/rules-blog-edge.yaml`:

- **BlogTrafficSurgeNotable** — `1h request rate > 3× quantile_over_time(0.5, $hour-of-day, 7d)` — severity: warning
- **BlogTrafficSurgeMajor** — `1h request rate > 10× baseline AND 1h unique visitors > 5× baseline` — severity: critical
- **CrowdSecDecisionBurst** — `rate(crowdsec_decisions_total[5m]) > 0.5` — severity: warning
- **FalcoCriticalEvent** — any event with `priority >= "critical"` in the last 5m — severity: critical (also routes directly via falcosidekick → Telegram, but Alertmanager owns the canonical record)

All alerts route through Alertmanager → `ai-alert-helper` webhook → Telegram.

### ai-alert-helper (new ArgoCD app)

`apps/ai-alert-helper/`. A ~200-LOC FastAPI service. Resource budget: requests `cpu: 20m / memory: 40Mi`, limits `memory: 128Mi`.

**File layout:**
```
apps/ai-alert-helper/manifests/
  deployment.yaml
  service.yaml
  configmap-app.yaml      # prompts, schedule, model names
  cronjob-digest.yaml     # Tekton TaskRun at 08:00 UTC
  secret-reference.yaml   # ExternalSecret → LITELLM_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

**Module structure:**
```
ai_alert_helper/
  __init__.py
  api.py              # FastAPI app: POST /alert, POST /digest
  facts.py            # fact-sheet builders (queries VictoriaLogs + GoatCounter)
  ai_adapter.py       # the swap point: summarize() / investigate()
  telegram.py         # delivery
  prompts/
    digest.txt
    investigate-generic.txt
    investigate-surge.txt
```

`ai_adapter.py` v1 uses the existing LiteLLM gateway (`http://litellm-gateway.litellm.svc:4000`). Default model: `qwen-think-14b` (local, free, ample for this task — fallback `claude-haiku-4-5` via LiteLLM virtual key if local is slow).

**The swap contract (do not change without a follow-up plan):**
```python
def summarize(facts: dict) -> str:
    """Daily digest. ~200 word narrative from a structured facts dict."""

def investigate(alert: dict, facts: dict) -> str:
    """Alert enrichment. 1-paragraph 'what happened, what's the risk' from
    an Alertmanager payload + a fact sheet specialised to the alert type."""
```

Sympozium-backed v2 replaces only these two function bodies. The facts.py builder, telegram.py delivery, and FastAPI handlers stay identical.

## Data flow

### Human visit
1. Reader's browser → Caddy on Hop → blog Pod
2. Caddy emits a JSON access log line `{ts, host, uri, status, ua, referer, remote_ip, duration}`
3. vlagent ships the line to VictoriaLogs on Frank
4. Browser executes Hugo's GoatCounter JS snippet → POSTs `/count` to `counter.derio.net`
5. Hop's Caddy reverse-proxies the POST over the mesh to GoatCounter on Frank
6. GoatCounter records the pageview (cookieless, daily-rotating hashed session ID)
7. Grafana's "Blog overview" dashboard reads from both sources — humans (GoatCounter) and everything (VictoriaLogs)

### Crawler visit
1. Same as human path 1–3
2. JS never executes; only the Caddy log records the request
3. Grafana's "Crawler & SE traffic" dashboard classifies known bots by User-Agent from VictoriaLogs queries

### Attack/scan
1. Attacker hits `/wp-login.php`, `/.env`, etc.
2. Caddy logs each request as normal
3. CrowdSec agent (sharing the log path) matches `crowdsecurity/http-probing` or similar scenario → emits a **decision** (ban IP for 4h)
4. CrowdSec writes the decision to its LAPI (ClusterIP-local on Hop)
5. caddy-crowdsec-bouncer module polls the LAPI every 10s → next request from that IP returns 403 at Caddy
6. CrowdSec also writes the decision to a log stream → vlagent → VictoriaLogs
7. If decision rate exceeds threshold, `CrowdSecDecisionBurst` fires → Alertmanager → ai-alert-helper → Telegram

### Container compromise
1. Attacker (via app CVE) gets RCE inside the Caddy or blog Pod
2. Their shell exec's `/bin/sh`
3. Falco's eBPF probe sees the `execve` in that container's cgroup → matches `Run shell untrusted` rule
4. Falcosidekick sidecar dual-publishes:
   - Telegram direct (immediate, URGENT)
   - VictoriaLogs (for the dashboard and for AI helper to correlate against Caddy logs)
5. `FalcoCriticalEvent` Alertmanager rule also fires → ai-alert-helper enriches with surrounding context → second Telegram message (the "story" version)

### Traffic surge
1. Background: Caddy logs continuously stream to VictoriaLogs
2. Background: Alertmanager evaluates `BlogTrafficSurge*` rules every minute
3. Surge condition met → Alertmanager fires → ai-alert-helper `/alert` webhook
4. ai-alert-helper builds the **surge fact sheet** (see next section)
5. ai_adapter.investigate(alert, surge_facts) → narrative
6. Telegram message with verdict ("HN spike, benign" / "scraper, CrowdSec mitigating" / "investigate")

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

Tekton CronJob in `apps/ai-alert-helper/manifests/cronjob-digest.yaml`, schedule `0 8 * * *` (08:00 UTC). Steps:

1. Query GoatCounter API: yesterday's uniques, top pages, top referrers, country breakdown
2. Query VictoriaLogs: yesterday's request count, status distribution, top User-Agents (humans vs bots), CrowdSec decision count, Falco event count
3. Build a structured fact sheet (JSON)
4. `ai_adapter.summarize(facts)` → ~200-word narrative
5. Post to Telegram via `@agent_zero_cc_bot`

Token cost: prompt template + ~2 KB facts → ~3 KB total → effectively free at `qwen-think-14b` local rates.

### Alert enrichment (entrypoint 2)

POST `/alert` from Alertmanager. Steps:

1. Parse the Alertmanager webhook payload (rule name, labels, time window)
2. `facts.py.build_for(alert)` returns the alert-type-specialised fact sheet
3. `ai_adapter.investigate(alert, facts)` → 1-paragraph verdict
4. Post to Telegram, threaded under the original alert if Alertmanager's notification ID is available

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
| Daily digest | CronJob → `summarize` → Telegram | Standard, 08:00 UTC |
| CrowdSec decision burst | Alertmanager → `investigate` → Telegram | Standard |
| Falco routine event | vlagent → VictoriaLogs only | None (dashboard) |
| Falco critical event | falcosidekick direct → Telegram + Alertmanager → `investigate` → Telegram | URGENT (direct first) + Standard (enriched follow-up) |
| BlogTrafficSurge Notable | Alertmanager → `investigate` (surge facts) → Telegram | Standard |
| BlogTrafficSurge Major | Alertmanager → `investigate` (surge facts) → Telegram | URGENT |

## Implementation phases

### Phase 1 — Log plumbing
- `apps/victoria-logs/` ArgoCD app on Frank, PVC-backed, datasource wired into Grafana
- Caddy ConfigMap switched to JSON access logs
- `clusters/hop/apps/observability/` ArgoCD app, vlagent DaemonSet shipping to Frank over mesh
- Smoke: search recent Caddy logs in Grafana Explore
- **Exit criteria:** logs visible in Grafana with `service=caddy` filter; Hop memory usage within budget

### Phase 2 — Blog analytics
- `apps/goatcounter/` ArgoCD app on Frank, SQLite PVC, IngressRoute for admin UI (mesh-only)
- Hugo partial `blog/layouts/partials/goatcounter.html` injected globally; tested with `hugo --buildDrafts`
- Caddy ConfigMap on Hop gains `counter.derio.net` route proxying via mesh
- DNS record `counter.derio.net` → Hop's public IP
- "Blog overview" Grafana dashboard ConfigMap
- Smoke: visit blog incognito → see hit in GoatCounter + Grafana within 30s
- **Exit criteria:** dashboard shows >0 visitors after self-test; Hop memory unchanged

### Phase 3 — Edge security
- `clusters/hop/apps/caddy/Dockerfile` rebuilt with `caddy-crowdsec-bouncer` module
- `clusters/hop/apps/crowdsec/` ArgoCD app with community blocklists + http scenarios
- Caddy ConfigMap gains `crowdsec` global directive + bouncer config
- "Security events" Grafana dashboard ConfigMap
- Alertmanager rule `CrowdSecDecisionBurst`
- Smoke: `curl -A "() { :; }; /bin/cat /etc/passwd" https://blog.derio.net/frank/` 5× from a controlled IP → next request 403
- **Exit criteria:** decision count > 0 in Grafana; controlled IP blocked

### Phase 4 — Host runtime monitoring
- `clusters/hop/apps/falco/` ArgoCD app with modern_ebpf driver + falcosidekick sidekick
- Local rule overrides in `falco_rules.local.yaml` (silence kube-system exec noise, raise priority on workload namespaces)
- Falcosidekick configured: VictoriaLogs output for all events, Telegram output for critical only
- Alertmanager rule `FalcoCriticalEvent`
- Smoke: `kubectl exec -n blog-system deploy/blog -- sh` (from authorised admin) → Falco event in Telegram within 5s
- **Exit criteria:** Falco event count > 0 in Grafana; controlled exec test triggers Telegram; Hop memory within budget

### Phase 5 — AI helper & surge detection
- `apps/ai-alert-helper/` ArgoCD app: FastAPI service, ExternalSecret for LiteLLM + Telegram secrets
- Tekton CronJob `digest-daily` at 08:00 UTC
- Alertmanager rules `BlogTrafficSurgeNotable` + `BlogTrafficSurgeMajor` with hour-of-day baseline queries
- `ai_adapter.py` LiteLLM-backed implementation
- Prompts committed in `prompts/`
- Smoke: synthetic surge (`hey -n 5000 -c 50 https://blog.derio.net/frank/`) → BlogTrafficSurgeMajor fires within 2m → AI helper enriches → Telegram message received
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
| vlagent | 32 Mi | 64 Mi | log shipper |
| crowdsec-agent | 80 Mi | 128 Mi | + community blocklists |
| falco + sidekick | 100 Mi | 200 Mi | modern_ebpf |
| **Total** | **212 Mi** | **392 Mi** | |

Hop pre-plan: 61% req / 73% lim on 3263 Mi. Post-plan target: ~68% / ~85%. Tightest cluster on Frank fleet; expect to revisit if a Pod is OOMKilled.

### Frank (new)

| Component | mem req | mem lim | Storage |
|---|---|---|---|
| victoria-logs | 200 Mi | 512 Mi | ~5 GB / 30 days |
| goatcounter | 40 Mi | 128 Mi | ~1 GB (SQLite, growth-bounded) |
| ai-alert-helper | 40 Mi | 128 Mi | none |

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
