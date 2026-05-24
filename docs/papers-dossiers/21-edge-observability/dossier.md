---
paper: 21-edge-observability
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: GoatCounter
  positioning: "Single-binary cookieless web analytics in Go, SQLite by default, ~40 MB resident. Privacy-shaped: no cookies, hashed-per-day session IDs, GDPR-safe by design. Optimised for one-blog deployments — the configuration surface is small enough to fit in a Helm-less raw manifest set. Frank's choice for the public ingest path."
  primary_url: "https://www.goatcounter.com/"
- name: Umami
  positioning: "Self-hosted analytics with a richer event model than GoatCounter — multi-site, custom events, funnels — backed by Postgres or MySQL. The honest counter-argument to GoatCounter for any deployment that might eventually need product-style funnels rather than just pageviews."
  primary_url: "https://umami.is/"
- name: Plausible
  positioning: "The other privacy-first analytics product Frank considered. Erlang/Elixir runtime, Clickhouse storage, multi-site by default. Self-host friendly, but the dependency stack (Postgres + Clickhouse + the BEAM VM) is heavier than GoatCounter's single Go binary; not a fit for Hop's 3.8 GiB budget."
  primary_url: "https://plausible.io/"
- name: CrowdSec
  positioning: "Open-source behavioural intrusion-prevention agent. Parses application logs in real time, applies community-curated scenarios (HTTP probing, brute-force, CVE-specific patterns), and pushes decisions to a 'bouncer' that enforces locally (Caddy module, nginx module, ipset, etc.). Decision-pull model means the bouncer doesn't consult a central server on every request — enforcement is local, observation aggregates upstream."
  primary_url: "https://www.crowdsec.net/"
- name: Falco
  positioning: "CNCF graduated runtime-security project. Reads kernel syscall events via eBPF, matches them against rules (shell-in-container, sensitive-file-read, unexpected-outbound), and emits alerts. The `modern_ebpf` driver — CO-RE programs attached via the kernel ABI — is the only viable Falco path on Talos because Talos has no kernel headers and no userland to load the legacy probe."
  primary_url: "https://falco.org/"
- name: Wazuh
  positioning: "The full-XDR alternative considered and rejected. Wazuh manager + agent + Elasticsearch backend gives you HIDS, FIM, log analysis, vulnerability scans and compliance reporting in one product — at a ~1.5 GB manager resource floor that doesn't fit Hop's budget and a rule-tuning surface disproportionate to a single-node edge. The right answer for an enterprise XDR; the wrong answer for one VPS in front of a blog."
  primary_url: "https://wazuh.com/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "GoatCounter — README (arp242/goatcounter on GitHub)"
  type: vendor-docs
  url: "https://github.com/arp242/goatcounter"
  quoted_passages:
    - "GoatCounter is an open source web analytics platform available as a hosted service (free for non-commercial use) or self-hosted app."
    - "Privacy-aware; doesn't track users with unique identifiers and doesn't need a GDPR notice."
    - "Lightweight and fast; should run fine on a 486 from 1992."
  relevance: "Vendor's authoritative description of GoatCounter's privacy-by-design model: cookieless, IP+UA hashed with a daily-rotating salt so no cross-day re-identification is possible. This is the load-bearing claim behind Frank's §3 choice of GoatCounter over Umami/Plausible and the §6 decision-tree branch 'do you need user-session analytics, or just pageviews?'."

- title: "CrowdSec — Documentation (CrowdSec docs landing)"
  type: vendor-docs
  url: "https://docs.crowdsec.net/"
  quoted_passages:
    - "CrowdSec is a free, modern & collaborative behavior detection engine, coupled with a global IP reputation network."
    - "The engine parses logs from various sources, and applies scenarios to detect malicious behavior."
    - "Decisions are then enforced by bouncers, which are software components that can act on the decisions taken by the engine."
  relevance: "Vendor's canonical statement of the CrowdSec agent + scenarios + decisions + bouncers split. Grounds the §3 'how each option handles the hard part' diagram showing the Caddy bouncer pulling decisions from the local LAPI on Hop while the agent's events also stream upstream to Frank for dashboarding. Source for the §5 'enforcement local, observation centralised' architecture claim."

- title: "Falco — Documentation (falco.org)"
  type: vendor-docs
  url: "https://falco.org/docs/"
  quoted_passages:
    - "Falco is a cloud native runtime security tool for Linux operating systems."
    - "Falco uses system calls to secure and monitor a system."
    - "The modern eBPF driver leverages CO-RE (Compile Once - Run Everywhere) to be portable across kernel versions without requiring kernel headers."
  relevance: "Vendor's documentation that modern_ebpf is built for immutable-OS environments — which is exactly Frank's situation on Talos (no kernel headers, no userland). Justifies the §3 architecture choice and the §5 honest admission that the legacy kmod and bpf-via-clang drivers were never available paths on Talos."

- title: "VictoriaLogs — Documentation"
  type: vendor-docs
  url: "https://docs.victoriametrics.com/victorialogs/"
  quoted_passages:
    - "VictoriaLogs is a fast, easy to use and cost-efficient log management system."
    - "VictoriaLogs is API-compatible with Loki and Elasticsearch ingestion endpoints."
    - "It accepts logs at /insert/loki/api/v1/push endpoint."
  relevance: "Vendor's own documentation of the load-bearing protocol-compatibility claim that lets Frank reuse VictoriaLogs as the backend for Falcosidekick — which only ships a Loki output, not a native VictoriaLogs output. Frank avoided a Loki migration purely because VictoriaLogs accepts the Loki push protocol on /insert/loki/api/v1/push. Source for the §3 'how Falco gets its events into Frank's existing TSDB-shaped log store' decision."

- title: "Caddy — log directive (Caddyfile reference)"
  type: vendor-docs
  url: "https://caddyserver.com/docs/caddyfile/directives/log"
  quoted_passages:
    - "Enables and configures HTTP request logging (also known as access logs)."
    - "The default log encoder is the JSON encoder."
    - "Multiple log directives may be used."
  relevance: "Vendor's reference for Caddy's structured JSON access log — the foundational data source the entire edge observability stack reads from. CrowdSec parses these logs; fluent-bit ships them to VictoriaLogs; the GoatCounter pipeline correlates against them. Without Caddy's JSON output being a first-class log directive, §3's 'one chokepoint, one log format, three consumers' architecture would require a custom log parser per consumer."

- title: "Falcosidekick — README (falcosecurity/falcosidekick on GitHub)"
  type: vendor-docs
  url: "https://github.com/falcosecurity/falcosidekick"
  quoted_passages:
    - "A simple daemon for enhancing available outputs for Falco."
    - "It takes Falco's events and forwards them to different outputs in a fan-out way."
    - "Each output can be filtered by minimum priority."
  relevance: "Vendor's statement of the dual-output pattern Frank uses: Falcosidekick forwards routine events to the Loki output (which VictoriaLogs accepts natively) AND ships critical events directly to Telegram, bypassing the AI helper so delivery survives an LLM outage. Source for the §3 'critical alerts bypass AI enrichment' decision and the §6 'when does the LLM go in the alert path?' branch."

- title: "Falco — modern_bpf driver source (falcosecurity/libs)"
  type: talk
  url: "https://github.com/falcosecurity/libs/tree/master/driver/modern_bpf"
  quoted_passages:
    - "The modern eBPF probe is a CO-RE program directly attached to the kernel."
    - "It doesn't require any kernel-specific build."
    - "It is the recommended driver for kernel versions that support BTF."
  relevance: "The actual source tree of the modern_bpf driver — the project's own README and code maps directly onto Frank's Talos constraint. No kernel-specific build, no userland-loaded module, just a CO-RE program. Underwrites the §3 architecture comparison between Falco's three drivers and the §5 'this is the only Falco that works on Talos' claim — not a marketing convenience, a real engineering requirement."

- title: "Plausible — Plausible vs Google Analytics (plausible.io/vs)"
  type: vendor-docs
  url: "https://plausible.io/vs-google-analytics"
  quoted_passages:
    - "Plausible Analytics doesn't use cookies, doesn't track users across the web, and doesn't collect personal data."
    - "Lightweight script: less than 1 KB, hosted on your own subdomain."
    - "Self-hostable in containers."
  relevance: "Vendor-side framing of the privacy-first analytics value proposition that book-ends the GoatCounter choice. Underwrites the §2 capability matrix row 'cookieless + GDPR-safe by design' as a shared property of the GoatCounter / Umami / Plausible cohort, not a Frank-specific preference."

- title: "Wazuh — Getting started (wazuh.com)"
  type: vendor-docs
  url: "https://documentation.wazuh.com/current/getting-started/index.html"
  quoted_passages:
    - "The Wazuh platform provides XDR and SIEM capabilities."
    - "It consists of agents, deployed on the monitored endpoints, and a central component that analyzes data from the agents."
    - "The Wazuh indexer is based on a forked version of OpenSearch."
  relevance: "Vendor's own architecture statement for the heavyweight XDR alternative Frank considered. The manager-plus-indexer-plus-agent topology — and the implied OpenSearch/Elasticsearch footprint behind it — is the load-bearing reason Wazuh is out of scope for a 3.8 GiB Hop node. Source for the §2 matrix row 'resource floor' and the §6 decision-tree branch."

- title: "Falco — graduation announcement (falco.org blog)"
  type: postmortem
  url: "https://falco.org/blog/falco-graduation/"
  quoted_passages:
    - "Falco is now a CNCF graduated project."
    - "Graduation signifies project maturity and broad adoption."
    - "Falco has been adopted by hundreds of organizations to protect their cloud-native workloads."
  relevance: "The project's own graduation post — the closest thing to a public postmortem-equivalent for the maturity-of-the-vendor question. Underwrites the §2 quadrant placement of Falco as 'single-purpose tool, mature' rather than a tooling experiment, and §7's claim that runtime security is no longer a 'try this in dev' capability."

- title: "VictoriaLogs — product page (resource-footprint claims)"
  type: benchmark
  url: "https://victoriametrics.com/products/victorialogs/"
  quoted_passages:
    - "VictoriaLogs uses up to 30x less RAM than Elasticsearch and Loki for the same workload."
    - "Loki and Elasticsearch-compatible ingestion endpoints."
    - "Designed for high-cardinality logs at any volume."
  relevance: "Vendor-biased but published resource-footprint claim anchoring the §3 architectural-equivalence argument — VictoriaLogs is the cheaper Loki for the same write protocol. Source for the §4 'what scale changes' framing of log-store resource footprint and the §6 'Loki or VictoriaLogs?' decision-tree branch ('whichever one your existing observability stack already runs')."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "clusters/hop/apps/caddy/manifests/configmap.yaml"
  date: 2026-05-24
  demonstrates: "The Caddy ConfigMap on Hop is the single chokepoint that makes the whole 'one log source, three consumers' architecture work. It declares global JSON access logging, the crowdsec order/bouncer block that wires Caddy 2.11.3 to the local LAPI at crowdsec-lapi.crowdsec-system.svc:8080, the counter.derio.net reverse-proxy hop to GoatCounter at 192.168.55.224:8080 over the Tailscale mesh, and the blog.derio.net route protected by the crowdsec directive. Every log line every dashboard ever queries originates here."

- kind: yaml
  path_or_url: "apps/ai-alert-helper/"
  date: 2026-05-24
  demonstrates: "The ai-alert-helper ArgoCD app: a ~250-LOC FastAPI service with three endpoints (/digest, /alert, /surge-check) backed by ai_adapter.py — the load-bearing swap point that lets Sympozium replace LiteLLM as a single-module change. The two Kubernetes CronJobs (digest-daily at 08:00 UTC, surge-check every 15 min) are deliberately separated from the FastAPI Deployment so a slow LLM call cannot take the next surge check down with it. ConfigMaps hold the prompts; ExternalSecret pulls the LiteLLM virtual key, Telegram bot token, and GoatCounter API token from Infisical."

- kind: yaml
  path_or_url: "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
  date: 2026-05-24
  demonstrates: "The blog-edge rule group appended to Frank's existing Grafana-managed alerting ConfigMap. Both rules — CrowdSecDecisionBurst and FalcoCriticalEvent — use the 3-step A (LogsQL query against VictoriaLogs) → B (reduce, last, dropNN) → C (threshold) shape mandated by the Grafana 12.x SSE engine. Each query carries queryType: stats so VictoriaLogs hits the /select/logsql/stats_query endpoint and returns the wide-series shape SSE expects — the gotcha that landed in frank-gotchas.md after we watched the alerts go DatasourceError for ten minutes on first deploy."

- kind: commit
  path_or_url: "git: aedb96a docs(obs): gotcha — VictoriaLogs alert rules need queryType:stats"
  date: 2026-05-24
  demonstrates: "The gotcha registry entry committed alongside the actual rule fix at a6651c4. Without model.queryType: stats, the rule hits /select/logsql/query which returns a long-series shape that SSE rejects with `input data must be a wide series but got type long`. The shape of this scar is the shape of every Frank scar: default config produced no signal, the failure mode was DatasourceError loops at 10-second cadence, the fix was one annotation, the lesson is documented so the next deploy doesn't pay the tax again."

- kind: commit
  path_or_url: "git: 6f9f868 fix(obs): re-register caddy-hop bouncer on every LAPI restart"
  date: 2026-05-24
  demonstrates: "The bouncer key re-registration postStart-hook scar. Because Hop runs the CrowdSec LAPI in-cluster with no persistent volume, every LAPI restart wipes the registered bouncers from the embedded SQLite DB. The fix is a postStart hook that re-runs `cscli bouncers add caddy-hop --key $CADDY_BOUNCER_KEY` after each LAPI start. Cost ~half a day of 'why does the bouncer return 401 after every LAPI rolling update' before the postStart pattern was committed. Documented as a soak risk in the dossier because the postStart hook can race against the bouncer's first pull."

- kind: incident
  path_or_url: "docs/runbooks/manual-operations.yaml#obs-goatcounter-bootstrap-first-site"
  date: 2026-05-24
  demonstrates: "The first manual-operation block that ships with this layer: GoatCounter has no first-party Helm chart and no declarative site-bootstrap API; the first site (blog.derio.net) is created via `goatcounter create site` inside the running Pod, with the resulting site ID captured manually for the Hugo partial. Three more manual blocks live in the same runbook entry — the Authentik outpost-provider assignment for the admin IngressRoute, the GoatCounter API-token mint for the Grafana Infinity datasource, and the public DNS A-record for counter.derio.net. These are the load-bearing exceptions to the declarative-everything principle for this layer."

- kind: grafana-screenshot
  path_or_url: "blog/content/docs/papers/21-edge-observability/blog-overview-dashboard-TODO.png"
  date: TBD
  demonstrates: "The 'Blog overview' Grafana dashboard rendered against live data ~24 hours after deployment. Panels (planned): daily unique visitors from GoatCounter Infinity datasource, top 10 pages from VictoriaLogs count_over_time by URI, top referrers, country breakdown, human-vs-bot pie keyed on User-Agent classification, CrowdSec decision count, Falco event severity count. To be captured before publish — the dashboard ConfigMap is in place but the panels need a day of real traffic to look like anything other than zeroes."

## Diagrams planned
- landscape:
    x_axis: "Observe-only ↔ Observe + Enforce"
    y_axis: "Single-purpose tool ↔ Full-XDR platform"
    vendors_plotted: ["GoatCounter", "Umami", "Plausible", "CrowdSec", "Falco", "Wazuh"]
- architecture_comparison:
    vendors: ["GoatCounter (browser JS → counter.derio.net → Caddy reverse-proxy → Frank GoatCounter Pod over mesh)", "CrowdSec (Caddy logs → CrowdSec agent on Hop → LAPI → caddy-crowdsec-bouncer poll → enforcement at request edge; agent events also stream to Frank's VictoriaLogs)", "Falco (modern_ebpf kernel probe → Falco userspace → Falcosidekick → Telegram direct OR Loki-protocol push to Frank's VictoriaLogs)"]
    note: "Exactly 3 architecture flowcharts in §3 — one per observability concern (analytics / edge-security / runtime-security). Umami, Plausible, and Wazuh get one-paragraph mentions inside the matching shape."
- decision_tree:
    leaves: 4
    description: "Question: when you put a public service on a single VPS in front of a homelab, what observability stack do you put in front of it? Branches on (1) is the service genuinely public or only mesh-reachable, (2) is the VPS budget tight enough that 1.5 GB of XDR is out of scope, (3) do you want the LLM in the alert path or just delivery-guaranteed pages. Terminates in: managed analytics + tunnel (Cloudflare / Vercel — for the team that has already paid for that edge); GoatCounter + CrowdSec + Falco on the VPS itself (Frank's pick — observe-and-enforce on the same node); Wazuh-shaped full-XDR (for the team that has the manager-node budget); Grafana Cloud + Tailscale Funnel (mesh-only, no public edge to defend)."

## Named gaps (≥1)
- "No community blocklist subscription is enabled yet. Frank ships with CrowdSec's local scenarios only — http-probing, http-cve, http-dos — and a small set of custom Caddy parsers. Subscribing to the free community blocklist tier would meaningfully expand the decision corpus (~hundreds of thousands of IPs known-bad across the CrowdSec network) at no resource cost, but the subscription is an account-bound operation and was deferred to a follow-up. Until it lands, the CrowdSecDecisionBurst alert only fires on attackers Frank has personally trained the parsers against — a noticeable blind spot for an edge-security claim."
- "Falco on Talos doesn't catch `kubectl exec` reliably with the stock ruleset. We observed routine syscall events firing (process execs, file opens, the expected baseline noise from a busy Caddy Pod) but never the 'Terminal shell in container' rule that should fire on an exec'd shell. The leading hypothesis is that the modern_ebpf probe attaches at a kernel-event level that misses container-runtime-mediated execs on Talos's specific kernel build, but we have not confirmed by reading the relevant Falco rule's matching predicate. This is a real coverage gap — if an attacker pivots into a Pod via the kubelet API rather than via the Pod's own services, Falco silently passes."
- "Bouncer key re-registration depends on the postStart hook landing before the bouncer's first decision pull. The hook runs after `cscli` is on PATH inside the LAPI container, but the bouncer Pod's poll loop starts immediately when its own container does — there is a tens-of-seconds race window during which the bouncer hits the LAPI with a stale (deleted-on-restart) key and gets 401. We've seen this in soak testing but not yet in production; the failure mode is 'all traffic gets allowed for ~30s' rather than 'all traffic gets blocked', which is the right direction but still wrong."
- "Surge detection has up-to-15-minute latency by design. The `surge-check` CronJob runs every 15 minutes and computes a 1-hour window vs hour-of-day baseline. That cadence is acceptable for the typical surge pattern (HN/Reddit spikes ramp over tens of minutes) but means a sudden coordinated scrape that completes inside one 15-minute window will be detected only after the scraper has finished. A faster cadence (5 minutes) would help; a much faster one (1 minute) would make the baseline computation pointless because the per-minute variance is too high."

## Counter-arguments considered (≥1)
- "Counter: just use Cloudflare or Vercel analytics — they're free, they're battle-tested, and they don't cost you a single megabyte of Hop's RAM budget. The honest answer: yes, for an observability-only deployment that question is overwhelmingly correct. Frank picked the self-hosted path for two reasons, neither of which is 'self-hosting is morally better'. First, Hop costs €5/month already because it runs the Headscale coordination plane; adding 270 MB of observability collectors to a node Frank is paying for anyway is a marginal cost of zero. Second, the GoatCounter + CrowdSec + Falco stack catches *runtime* signals (Pod-internal compromise, behavioural HTTP attacks, per-day surge ratios against a Frank-controlled baseline) that Cloudflare's analytics layer can't see by design — Cloudflare sits in front of the TLS terminator, not behind it. For a team whose only public surface is a static blog and whose threat model is 'I might get HN'd', Cloudflare's free tier is the correct answer; Frank's situation is different and the answer changes."
- "Counter: Wazuh is the right XDR product for this — it gives you HIDS, FIM, log analysis, vulnerability scans, and compliance reporting in one cohesive stack with eight years of mature rules behind it. Why ship three separate agents (CrowdSec, Falco, fluent-bit) when one Wazuh agent does all of it? The honest answer: the Wazuh manager's ~1.5 GB resource floor doesn't fit Hop's 3.8 GiB budget, and even if it did the rule-tuning surface is disproportionate to one node's blast radius. Wazuh is the right answer at 10+ endpoints with a security team to operate it; at one VPS in front of a blog, the three-tool composition is lighter, each tool's failure is independent, and the rule-tuning surface stays proportional to what's actually exposed."
- "Counter: Loki is the more idiomatic log-store for a Falco + fluent-bit stack — every example in the Falco docs and every CNCF demo uses Loki, not VictoriaLogs. Why bend VictoriaLogs into the role? The honest answer: Frank already runs VictoriaLogs as part of the existing metrics + logs stack (chart vm/victoria-logs-single, 14d retention bumped to 30d), the Grafana datasource is already provisioned, and VictoriaLogs accepts the Loki push protocol natively at /insert/loki/api/v1/push. Adding Loki as a second log store to serve Falco specifically would mean two log stores to operate, two retention policies to tune, two PVCs to grow. The protocol-compatibility surface (Loki push protocol, vendor-confirmed) makes the second store unnecessary."
- "Counter: AI alert enrichment is over-engineering for a blog. A Grafana alert that fires 'CrowdSecDecisionBurst' with an attached query is enough information for a human at 3 AM to triage. Wrapping it in an LLM call is theatre. The honest answer to this is the strongest of the four: the AI helper's *load-bearing* contribution is not the narrative output, it's the structured fact-sheet contract — top referrers, top pages, geo distribution, human-vs-bot ratio, status distribution, CrowdSec decision count — computed and handed to *some* downstream consumer. The LLM is a swap-out detail; the fact-sheet is the durable architecture. If LiteLLM goes away tomorrow, Frank replaces ai_adapter.summarize with a Jinja template producing the same prose, the alert text gets uglier, and nothing else changes."
