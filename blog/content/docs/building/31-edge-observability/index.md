---
title: "Building Edge Observability — Watching Frank's Edge Without Watching Frank's Edge Burn"
date: 2026-05-24
draft: false
tags: ["observability", "victoria-logs", "fluent-bit", "goatcounter", "crowdsec", "falco", "grafana", "litellm", "hop", "talos", "caddy", "fastapi", "tdd"]
summary: "Collectors on Hop, backend on Frank, AI alert enrichment that knows when 12× baseline is a scraper and when it's Hacker News."
weight: 32
---

The blog at `blog.derio.net/frank` had no observability. I knew this in the abstract — Hop is a single Hetzner CX23 with four gigs of RAM and no Grafana — but I didn't know it concretely until the day I wanted to ask "how many people read Paper 15 this week?" and the answer was a shrug. Caddy's stdout had the answer. Nothing was reading Caddy's stdout. Nothing was retaining it longer than the container's lifetime. Nothing was alerting if the apex started returning 5xx, nothing was banning the credential-stuffing IPs walking the sitemap, nothing was watching the Pod filesystem for the runc-escape pattern that would land me on a security disclosure page nobody wants to be on.

This post is the build narrative for fixing that. The full vendor-landscape research — six analytics products, four edge-security products, three runtime-security products, the sources, the quoted passages, the named gaps and counter-arguments — sits in the research file at `docs/investigations/2026-05-24--obs--edge-observability-research.md` for anyone who wants to read the unvarnished decision substrate. The series-shaped Papers version of that research got pulled before publish — the layer touches three separate vendor landscapes plus a bespoke piece, which fights the Papers series' single-decision shape; the three narrower future papers it seeds are listed as Deferred on {{< relref "/docs/papers" >}}. This post is the *how*, complete with the three commits I had to revert and the wrong helm value I shipped before getting yelled at by an SSE engine I'd never heard of.

## The shape of the problem

Two clusters. Hop sits on Hetzner running Talos, serves the blog through Caddy on hostPort 80/443, terminates TLS via the Cloudflare DNS challenge. Frank is the homelab — seven nodes, GitOps everything, Grafana and VictoriaMetrics and a bunch of services already humming. Frank has the heavy stack. Hop has 4 GB of RAM and 73% of it already committed before I added a single observability byte.

Three concerns rolled into one layer:

1. **Analytics.** Who's reading what? Where are they coming from? Which papers actually get read versus which sit in the sidebar pretending?
2. **Edge security.** Who's probing `/wp-login.php`? Who's walking the sitemap with `python-requests`? Block them at the edge before they cost me Hetzner egress.
3. **Runtime security.** If a Caddy CVE landed and someone got code-exec inside the Pod, would I find out from a Telegram alert or from a defacement?

The naive answer was "deploy a SIEM on Hop." Wazuh's manager is 1.5 GB. There is no Wazuh manager on Hop. The cluster will have opinions.

## The architecture that survived three reviews

**Collectors-on-Hop, backend-on-Frank.** Hop runs only thin agents that ship over the existing Tailscale subnet route to Frank, where the existing VictoriaLogs / VictoriaMetrics / Grafana / LiteLLM stack picks the work back up. Frank is extended, not duplicated.

```
┌──────────── Hop (CX23, 4 GB) ────────────┐    ┌────────────── Frank ──────────────┐
│ Caddy ── JSON access logs ── stdout      │    │  victoria-logs (extended)         │
│ fluent-bit DaemonSet ────────────────────┼───→│   ClusterIP for Frank-local       │
│                                          │    │   LoadBalancer 192.168.55.225     │
│ CrowdSec agent ── decisions ── caddy-cs- │    │   for cross-cluster ingest        │
│   bouncer (local enforcement at edge)    │    │                                   │
│                                          │    │  Grafana ── 3 new dashboards      │
│ Falco modern_ebpf + falcosidekick        │    │  Alert rules → AI Helper webhook  │
│   ↘ Loki output ─────────────────────────┼───→│                                   │
│   ↘ Telegram (critical, direct)          │    │  goatcounter (new app)            │
│                                          │    │   LoadBalancer 192.168.55.224     │
│ Hugo blog ── JS snippet ─→ counter.derio.net (Caddy reverse-proxies to .224)     │
│                                          │    │                                   │
│                                          │    │  ai-alert-helper (new app)        │
│                                          │    │   /digest /alert /surge-check     │
│                                          │    │   ↘ LiteLLM ↘ Telegram bot        │
└──────────────────────────────────────────┘    └───────────────────────────────────┘
```

Three cross-cluster networking facts the design is built on:

- **The Tailscale subnet router advertises home-LAN CIDRs only** — `192.168.10.0/24`, `192.168.50.0/24`, `192.168.55.0/24` — not the kube service CIDR. I learned this the hard way. The reviewer learned it less hard, by reading the [subnet-router design]({{< relref "/docs/building/24-in-cluster-ingress" >}}) and asking the only question that mattered: "does the kube service CIDR get advertised?" It does not. So **cross-cluster reach has to go via Cilium L2 LoadBalancer IPs** in the 192.168.55.x range. That's a load-bearing constraint, not a detail.
- **Frank has no Alertmanager.** Alerting is entirely Grafana-managed through the existing `apps/grafana-alerting/manifests/{contact-points,notification-policy,alert-rules}-cm.yaml`. Any plan that said "Alertmanager webhook" was wrong. (Mine did. Twice. The reviewer caught it both times.)
- **Grafana lives as a subchart of `victoria-metrics`.** There is no `apps/grafana/values.yaml`. Datasources come from sidecar ConfigMaps with label `grafana_datasource: "1"`. Dashboards mount via `extraConfigmapMounts` on the victoria-metrics chart. Any plan that said "edit `apps/grafana/values.yaml`" was also wrong. (Mine did.)

The reviewer caught all three on the first pass. He extracted the actual Helm charts and proved that `server.extraServices` doesn't exist in `vm/victoria-logs-single 0.11.28` (it's `extraObjects` at the top level), that `falcosidekick.config.victoriaLogs` is fictional (use the Loki output, VictoriaLogs accepts the protocol natively), that GoatCounter's `-real-ip-header` flag doesn't exist (Caddy's reverse-proxy sets `X-Forwarded-For` and GoatCounter consumes it without a flag). Six critical issues. Then he did it again on the rewrite and found five more. The lesson is in the auto-memory now: *for every config-shaped claim, the next step before moving on is a verification command that grounds it in the artifact's real schema.*

## Phase 1 — Log plumbing

Extend the existing VictoriaLogs. Frank already had `apps/victoria-logs/` deployed, 14d retention, 20Gi PVC. Bump retention to 30d and add a sibling Service of type LoadBalancer at `192.168.55.225` via the chart's `extraObjects`:

```yaml
# apps/victoria-logs/values.yaml
server:
  retentionPeriod: 30d
  service:
    type: ClusterIP
    port: 9428
extraObjects:
  - apiVersion: v1
    kind: Service
    metadata:
      name: victoria-logs-lb
      namespace: monitoring
      annotations:
        lbipam.cilium.io/ips: "192.168.55.225"
        lbipam.cilium.io/sharing-key: "victoria-logs-lb"
    spec:
      type: LoadBalancer
      selector:
        app.kubernetes.io/name: victoria-logs-single
        app.kubernetes.io/instance: victoria-logs
      ports:
        - { name: http, port: 9428, targetPort: 9428 }
```

The selector matters — `kubectl get pod -n monitoring -l app.kubernetes.io/instance=victoria-logs --show-labels` confirms the labels match before pushing. After sync: `192.168.55.225:9428/metrics` returns Prometheus-style metrics from both Frank-internal pods and from a curl pod on Hop.

On Hop, mirror Frank's existing fluent-bit pattern. Same chart, same kubernetes filter, same output protocol — only the destination Host changes from the in-cluster FQDN to the LB IP. The 80 Mi memory limit is what fluent-bit actually uses on Hop in practice; the chart's default is higher.

```ini
# clusters/hop/apps/fluent-bit/values.yaml — outputs section
[OUTPUT]
    Name            http
    Match           kube.*
    Host            192.168.55.225
    Port            9428
    URI             /insert/jsonline?_stream_fields=stream,kubernetes.pod_name,kubernetes.namespace_name,kubernetes.container_name&_msg_field=msg&_time_field=time
    Format          json_lines
    Json_Date_Key   time
    Json_Date_Format iso8601
```

The first version shipped with `_msg_field=log` because the spec said `log`. Wrong. fluent-bit's kubernetes filter with `Merge_Log On` merges container JSON into the top-level record. Caddy emits `{"msg": "handled request", ...}` — top-level `msg`, not `log`. The fix was a one-line change to `_msg_field=msg`. The signal was a VictoriaLogs query returning `_msg: "missing _msg field; see ..."` — VictoriaLogs's actual error string, captured verbatim because that's better than guessing.

One Hop-side fact-of-life: the `monitoring` namespace gets created fresh on Hop. Default PodSecurity is `restricted`. Fluent-bit hostPath-mounts `/var/log/containers`, which `restricted` denies. So the namespace manifest gets a `pod-security.kubernetes.io/enforce: privileged` label, the same way `caddy-system` and `headscale-system` already have it. Per the Hop gotchas file, this is the standard move for hostPath workloads on Talos.

Caddy's per-site `log` directive was the other initial confusion. The global `log` directive in the Caddyfile sets the *runtime/error* logger — it gets you the boot-time JSON spew but no access logs. Access logs require a `log` directive *inside* each site block. Per-site, opt-in. The first deploy emitted zero `"msg":"handled request"` lines because of this. The second deploy had `log` inside `blog.derio.net { ... }` and the JSON access lines arrived.

## Phase 2 — Blog analytics

GoatCounter over Umami. The reviewer would tell you Umami has funnels and rich event tracking and a polished dashboard. He'd be right. But GoatCounter is a single Go binary with SQLite, fits in 40 MB, and matches the actual question I'm asking ("which papers get read?") without needing a Postgres companion. Multi-site multi-event analytics is YAGNI for one Hugo blog.

The catch is that GoatCounter eats `GOATCOUNTER_*` env vars as flag overrides. Kubernetes auto-injects `GOATCOUNTER_PORT=tcp://10.x.x.x:8080` when a Service named `goatcounter` exists in the namespace. The pod crashlooped reading `tcp://...` as a port number. `enableServiceLinks: false` on the Pod spec fixes it permanently. It's the kind of bug that shows up in production at 02:00 and the fix is a six-character config change.

The `-domain` flag is a 3-value tuple — `mainDomain,staticDomain,countDomain`. For us:

```yaml
args:
  - serve
  - -db=sqlite+/home/goatcounter/goatcounter-data/goatcounter.sqlite3
  - -listen=:8080
  - -tls=none
  - -automigrate
  - -domain=counter.cluster.derio.net,counter.cluster.derio.net,counter.derio.net
```

Main + static = the mesh-only admin host (counter.cluster.derio.net). Count = the public beacon hostname (counter.derio.net) which Hop's Caddy reverse-proxies to `192.168.55.224:8080`. Reads count as a single record routed by GoatCounter's site `cname` field. Confirmed it via reading `cmd/goatcounter/serve.go` directly through the GitHub API — the GoatCounter docs are sparse on this and trial-and-error would have eaten an hour.

The site itself is bootstrapped via `goatcounter db create site`:

```
kubectl exec -n goatcounter-system deploy/goatcounter -- sh -c \
  "goatcounter db create site \
    -db sqlite+/home/goatcounter/goatcounter-data/goatcounter.sqlite3 \
    -vhost counter.cluster.derio.net \
    -user.email <email> \
    -user.password '<generated>'"
```

The `-user.password` flag is what lets you script this without an interactive TTY — the interactive path errors out under `kubectl exec` because there's no terminal to prompt against. A manual-op block in the runbook records this exactly because it's exactly the kind of thing that gets forgotten three months from now when GoatCounter eats its own database.

The Hugo snippet drops in via `blog/layouts/partials/custom/goatcounter.html`:

```html
{{ if eq hugo.Environment "production" -}}
<script data-goatcounter="https://counter.derio.net/count"
        async src="https://counter.derio.net/count.js"></script>
{{- end }}
```

The guard is real. `hugo.Environment` is `production` for the deploy build and `development` for local `hugo server`. The dev build does NOT include the script tag — verified by building `hugo -e development` and `hugo -e production` into separate output directories and grepping for `counter.derio.net`. Tracking my own dev sessions would have polluted the visitor counts within a week.

Behind the scenes: Authentik forward-auth fronts `counter.cluster.derio.net`. The provider blueprint goes into `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml` (already registered in `apps/authentik/values.yaml → blueprints.configMaps`). The manual step that always trips me up: blueprints cannot mutate the embedded outpost's provider list — that has to happen via the Django ORM, by hand, after the blueprint syncs:

```python
kubectl exec -n authentik deploy/authentik-server -- python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'authentik.root.settings')
django.setup()
from authentik.providers.proxy.models import ProxyProvider
from authentik.outposts.models import Outpost
outpost = Outpost.objects.get(name='authentik Embedded Outpost')
provider = ProxyProvider.objects.get(name='GoatCounter (cluster)')
outpost.providers.add(provider)
print('done')
"
```

This is documented in `agents/rules/frank-argocd.md` and now in the manual-operations runbook under `obs-goatcounter-authentik-outpost`. It is the seventh time I've done it for a new mesh-only service. It is the seventh time it has worked.

## Phase 3 — Edge security with CrowdSec

CrowdSec runs as agent + LAPI. The agent tails Caddy logs, parses them through the `crowdsecurity/caddy` collection, applies HTTP behavioural scenarios (`http-cve`, `http-dos`, `base-http-scenarios`), and writes ban decisions to the local LAPI. The Caddy bouncer module polls LAPI every 10 seconds and returns 403 for any banned IP. Enforcement is local — no Frank dependency on the request path, so a mesh hiccup doesn't open the front door.

Building this required rebuilding the Caddy image to include the bouncer modules:

```dockerfile
FROM caddy:2.11.3-builder AS builder
ENV GOTOOLCHAIN=auto
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare \
    --with github.com/hslatman/caddy-crowdsec-bouncer/http \
    --with github.com/hslatman/caddy-crowdsec-bouncer/layer4

FROM caddy:2.11.3-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

This is the third version. Version one used the project's existing `caddy:2.9-builder` (the existing Caddy image was 2.9). The build failed because `caddy-crowdsec-bouncer v0.12.1` requires `go >= 1.25.7` and the 2.9 builder ships go 1.23. Version two added `ENV GOTOOLCHAIN=auto` to let Go bootstrap a newer toolchain on demand. That fixed the Go problem but exposed a second one: the bouncer also requires `caddy v2.10.2+`. Bumping the entire stack to 2.11.3 was the actual fix — and updating the deployment image tag in the same commit.

The Caddy ConfigMap then gets the `crowdsec` directive in the global block (with `order crowdsec first` so it runs before reverse_proxy) and the `crowdsec` handler inside the blog.derio.net site block:

```caddyfile
{
  email admin@derio.net
  acme_dns cloudflare {env.CF_API_TOKEN}
  log { output stdout, format json, level INFO }
  order crowdsec first
  crowdsec {
    api_url http://crowdsec-service.crowdsec-system.svc:8080
    api_key {env.CROWDSEC_BOUNCER_API_KEY}
    ticker_interval 10s
  }
}

blog.derio.net {
  log
  crowdsec
  handle /frank* { reverse_proxy blog.blog-system.svc:8080 }
  handle { redir https://blog.derio.net/frank{uri} permanent }
}
```

The service name in the bouncer config is `crowdsec-service`, not `crowdsec-lapi` as the spec assumed. The chart names the Service `crowdsec-service` regardless of the deployment name. Caused a "no such host" DNS resolution error for a few minutes; fixed by reading what `kubectl -n crowdsec-system get svc` actually returns. *Look at what the artifact actually does, not what the documentation describes it as.*

The harder issue: Hop has no persistent volume available for CrowdSec. Hop's `hetzner-volume` StorageClass is manual-provisioning (no provisioner — just pre-allocated PVs), and both existing PVs are already bound to Caddy data and Headscale data. So CrowdSec LAPI runs without persistence. Each LAPI restart wipes the bouncer registration. The Caddy bouncer then hits LAPI with a stale API key and gets `access forbidden` — every 10 seconds, in a tight retry loop, until I notice.

The fix is a postStart lifecycle hook on the LAPI container that re-registers the bouncer with a fixed key from a Secret:

```yaml
lapi:
  env:
    - name: CADDY_HOP_BOUNCER_KEY
      valueFrom:
        secretKeyRef: { name: crowdsec-bouncer-keys, key: caddy-hop }
  lifecycle:
    postStart:
      exec:
        command:
          - /bin/sh
          - -c
          - |
            for i in $(seq 1 10); do
              cscli bouncers list >/dev/null 2>&1 && break
              sleep 2
            done
            cscli bouncers add caddy-hop -k "$CADDY_HOP_BOUNCER_KEY" 2>/dev/null \
              || echo "bouncer already registered"
```

The matching Secret in `caddy-system` (`caddy-crowdsec`) holds the same key under `CROWDSEC_BOUNCER_API_KEY`. Both secrets are seeded out-of-band with a `openssl rand -hex 32` value. After every LAPI restart, the postStart hook re-registers with the same key and the Caddy bouncer's pull succeeds within one tick. Smoke test:

```
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- cscli decisions add --ip <my-public-ip> --duration 45s
# wait 12s for bouncer pull
curl -s -o /dev/null -w '%{http_code}\n' https://blog.derio.net/frank/   # 403
# wait 45s for expiry
curl -s -o /dev/null -w '%{http_code}\n' https://blog.derio.net/frank/   # 200
```

403 during the window, 200 after. It works. A real future-Frank concern: if I want this resilient through a Hetzner Volume migration, I need to actually buy another Hetzner Volume. €1/month. I haven't yet. The postStart hook is the workaround that survives most failure modes but not all of them.

## Phase 4 — Falco on a no-userland kernel

Falco DaemonSet, `driver.kind: modern_ebpf`. This is the only viable driver on Talos because Talos has no kernel headers and no userland to load eBPF the legacy way. The `modern_ebpf` driver attaches CO-RE programs via the kernel ABI directly.

The honest admission: on Talos, Falco's default rule set does not reliably catch `kubectl exec`. I tested it. I exec'd into the blog Pod, ran `id`, exited. No "Terminal shell in container" rule fired. The rules that DO fire are things like "Contact K8S API Server From Container" (Notice priority) when a Pod's process talks to kube-apiserver via the in-cluster Service — which happens constantly because that's how everything Kubernetes-native works. Falco's value on Talos is narrower than the marketing promises. It's still net positive — the container CVE class of attacks (cryptominer exec, suspicious file reads, unexpected DNS exfil) does trigger — but the most theatrical demo doesn't work.

The verification that DID work was via Falcosidekick's `/test` endpoint:

```
curl -X POST http://falco-falcosidekick.falco-system:2801/test
# falcosidekick logs:
# [INFO] : Enabled Outputs: [Loki Telegram]
# [INFO] : Loki - POST OK (204)
# [INFO] : Telegram - POST OK (200)
```

Both outputs receive synthetic events. Real Falco events (the "Contact K8S API Server" rule firing constantly from fluent-bit, ArgoCD, Caddy) land in VictoriaLogs via the Loki push protocol. The fact that VictoriaLogs natively accepts Loki's `/loki/api/v1/push` shape — its endpoint is `/insert/loki/api/v1/push` — meant no protocol gateway was needed. There is no `victoriaLogs` output in falcosidekick (the spec invented one; the reviewer caught it). The Loki output works directly:

```yaml
falcosidekick:
  config:
    loki:
      hostport: "http://192.168.55.225:9428"
      endpoint: "/insert/loki/api/v1/push"
      format: "json"
      minimumpriority: "informational"
    telegram:
      minimumpriority: "critical"
  config:
    existingSecret: falco-telegram   # holds TELEGRAM_TOKEN + TELEGRAM_CHATID
```

`config.existingSecret` is the chart key — not `existingSecret` at the top level. The reviewer caught that one too. The deployment's envFrom is *additive*: it mounts both the chart's auto-generated config Secret AND the existingSecret, so the merged env has both the Loki config (auto) and the Telegram creds (mine).

The macro override pattern in Falco is its own story:

```yaml
customRules:
  talos-quiet.yaml: |-
    - macro: user_known_shell_in_container_activities
      condition: (k8s.ns.name = "kube-system")
```

There is no `override:` key in the Falco schema. The first version of the values block invented one. The actual override mechanism is to re-declare the macro with the same name in a later-loaded rules file; the later definition replaces the earlier one. The chart loads `customRules` after the default rules, so this works as long as the names match.

## Phase 5 — The AI helper and the surge that wasn't

This was the most novel piece and the part I most expected to over-engineer. The brief was: a service that produces a daily blog digest and enriches alert-time messages with LLM context. Plus, eventually, surge detection — when traffic spikes, classify it (Hacker News, scraper, attack) before someone has to look.

The first design routed alerts through Alertmanager. Frank has no Alertmanager. The first design also routed surge detection through Grafana alert rules backed by `quantile_over_time` over the same hour-of-day across seven days. LogsQL has no `quantile_over_time`. Both designs were caught by the reviewer. The second design moved surge detection into Python in the helper itself — eight LogsQL `stats count()` queries (current hour + seven historical hours-of-day), median computed in `statistics.median`, ratio compared against tier thresholds. Cheap. ~50 ms per check. Triggered by a CronJob every 15 minutes.

The contract that everything hangs from is in `ai_adapter.py`:

```python
def summarize(facts: dict) -> str:
    """Daily digest — ~200-word narrative from a structured facts dict."""

def investigate(alert: dict, facts: dict) -> str:
    """Alert enrichment — 1-paragraph 'what happened, what's the risk'."""
```

`facts.py` produces the structured dicts; `ai_adapter.py` consumes them. The contract is the swap point: today the implementation calls LiteLLM with `qwen-think-14b` (local on the homelab GPU) and falls back to `claude-haiku-4-5` on timeout. Some future day, when [Sympozium]({{< relref "/docs/building/26-vk-remote-self-host" >}}) gets multi-agent debate working, only this module changes. The fact-sheet shape is the contract that survives.

TDD got serious on this phase. Twelve tests against `respx`-mocked HTTP:

```
tests/test_ai_adapter.py::test_summarize_calls_primary_model PASSED
tests/test_ai_adapter.py::test_call_falls_back_to_secondary_on_5xx PASSED
tests/test_ai_adapter.py::test_investigate_picks_surge_template_for_BlogTrafficSurge_alert PASSED
tests/test_ai_adapter.py::test_investigate_picks_generic_template_for_unknown_alert PASSED
tests/test_facts.py::test_build_for_alert_dispatches_to_security_for_crowdsec PASSED
tests/test_facts.py::test_build_for_alert_dispatches_to_falco_for_falco_event PASSED
tests/test_facts.py::test_build_for_alert_returns_minimal_sheet_for_unknown PASSED
tests/test_surge.py::test_compute_returns_none_when_traffic_normal PASSED
tests/test_surge.py::test_compute_returns_notable_when_3x_baseline PASSED
tests/test_surge.py::test_compute_returns_major_when_10x_baseline PASSED
tests/test_surge.py::test_compute_handles_empty_baseline_without_divide_by_zero PASSED
tests/test_surge.py::test_compute_handles_zero_current_traffic PASSED
============================== 12 passed in 1.13s ==============================
```

The two tests I'm most proud of are the divide-by-zero one (brand-new blog with no historical data shouldn't crash — baseline forces to 1) and the zero-current-traffic one (no requests this hour shouldn't fire a surge alert about a 0× ratio). Both came from imagining the boring cases first. The fallback-on-5xx test came from imagining LiteLLM's worst day — Telegram still needs the alert, even if it's the fallback model. The fallback model exists so the system can survive its primary failing without me waking up to a silent oncall.

The in-cluster end-to-end smoke had two halves:

```
# Daily digest, triggered manually
kubectl create job -n ai-alert-helper-system digest-now --from=cronjob/digest
# 10s later: Telegram message arrives — "Yesterday: 1,593 requests, 0 security events"

# Alert enrichment, triggered with a synthetic Grafana webhook payload
echo '{"alerts":[{"labels":{"alertname":"CrowdSecDecisionBurst","severity":"warning","grafana_folder":"blog-edge"}}]}' \
  | kubectl exec -i alert-fire -- curl -X POST -H "Content-Type: application/json" -d @- http://ai-alert-helper:8080/alert
# 8s later: Telegram message with LLM-generated 2-sentence summary referencing the fact sheet
```

Both produced Telegram messages with LLM narratives generated against real fact sheets. The local qwen model on gpu-1 handled both, well under one second of inference. The fallback path is untested in production because LiteLLM hasn't failed yet — but the unit test is enough confidence to leave the path quiet.

## The DatasourceError storm

The day after deployment, Telegram lit up. Every minute, an URGENT `DatasourceError` alert. The new `blog-edge` rule group was failing on every evaluation cycle:

```
[sse.readDataError] [A] got error: input data must be a wide series but got type long
```

The VictoriaLogs Grafana datasource defaults to `queryType: instant` which hits `/select/logsql/query` and returns a *long* series of log lines. Grafana's SSE `reduce` step expects a *wide* (Prometheus-style instant vector) series and rejects the long format. The fix is one line in the alert rule's model block: `queryType: stats`. That hits `/select/logsql/stats_query` instead, which returns the wide format. Renamed the stats output column from `c` to `value` (idiomatic for wide), dropped a redundant inline `_time:5m` from the Falco query (relativeTimeRange already provides the window), pushed. Both rules now show `state: inactive` with empty `lastError`. The URGENT storm stopped within one evaluation cycle.

This gotcha now lives in `agents/rules/frank-gotchas.md` under Grafana, two lines above the existing "12.x SSE alert rules need 3-step A→B→C" entry. It's a one-line guard against the next person hitting the same wall.

## What I'd do differently

**Inventory `apps/` before designing a new app.** The first version of the spec invented a new VictoriaLogs deployment. VictoriaLogs was already running. Same for fluent-bit — already shipping Frank's container logs to VictoriaLogs. The spec ignored both because I treated "what observability stack should Frank have?" as a greenfield design question. Six critical issues and a complete rewrite later, the lesson is now an auto-memory note: *for every "let's add X" design in this repo, do `ls apps/` first.*

**Verify every chart key against the chart.** The first rewrite invented `server.extraServices`, `falcosidekick.config.victoriaLogs`, GoatCounter's `-real-ip-header` flag. None exist. The reviewer extracted each chart, read the values schema, and proved it. The discipline that finally stuck was: any time I write a config-shaped claim, the next step is `helm pull --untar` (or `gh api` for the project's source) and `grep` for the literal key.

**Get the Hop AppProject right before deploying any new Hop app.** Hop has a single AppProject (`hop-infrastructure`) with a narrow sourceRepos whitelist. New chart repos must be added before any chart-backed Application can sync. This is one line of work that, if forgotten, produces a confusing "project validation failed" message on three separate applications. Phase 1 now extends the whitelist as a prerequisite task before any chart deploys.

## What this enables

Every blog visit now produces a Caddy access log line, a GoatCounter pageview, a Grafana time-series data point. Every IP that walks the sitemap with a python user agent gets banned at the edge within 10 seconds. Every shell-in-a-container event would Telegram me directly. The daily digest arrives at 08:00 UTC with the previous day's traffic shape. The surge check runs every 15 minutes — quietly, until it isn't.

What this is *not* yet: a community blocklist subscription on CrowdSec (deferred — free tier sign-up still pending). A Wazuh-grade SIEM (won't fit on Hop and isn't proportional to the threat surface). A Frank-side Falco for the homelab itself (separate plan, separate resource budget, separate publishing cycle).

The cluster has opinions. The cluster now also has receipts.

## References

- [`docs/investigations/2026-05-24--obs--edge-observability-research.md`](https://github.com/derio-net/frank/blob/main/docs/investigations/2026-05-24--obs--edge-observability-research.md) — Full vendor-landscape research (the Papers-series version was pulled; three narrower future papers are seeded on {{< relref "/docs/papers" >}})
- {{< relref "/docs/operating/26-edge-observability" >}} — Companion operating post: day-to-day commands for the obs layer
- `docs/superpowers/specs/2026-05-23--obs--hop-blog-edge-monitoring-design.md` — Spec
- `docs/superpowers/plans/2026-05-23--obs--hop-blog-edge-monitoring/` — Phased plan with state-tracked checkboxes
- `docs/runbooks/manual-operations.yaml` — Eight new manual-op entries from this layer
- [VictoriaLogs docs](https://docs.victoriametrics.com/victorialogs/) — Loki push protocol compatibility
- [Falco modern_ebpf driver](https://falco.org/docs/setup/kernel/) — Why this is the only viable choice on Talos
- [CrowdSec docs](https://docs.crowdsec.net/) — Behavioral scenarios, bouncer integration
- [GoatCounter](https://github.com/arp242/goatcounter) — Cookieless single-binary analytics
- [caddy-crowdsec-bouncer](https://github.com/hslatman/caddy-crowdsec-bouncer) — Caddy module
