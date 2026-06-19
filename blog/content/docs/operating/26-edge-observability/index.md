---
title: "Operating Edge Observability — Day-to-Day Commands for the Obs Layer"
date: 2026-05-24
draft: false
tags: ["operations", "observability", "victoria-logs", "goatcounter", "crowdsec", "falco", "grafana", "ai-alert-helper", "hop"]
summary: "Querying the blog log stream, banning a scraper before lunch, tuning Falco out of the kube-system noise, and triggering a digest by hand."
weight: 27
---

The companion to {{< relref "/docs/building/31-edge-observability" >}}. Where the building post explains *why* the wiring is the way it is, this one is the cheat-sheet for the day Hop pages me at 03:14 and Grafana says `DatasourceError`. The commands that ship the layer's mental model into muscle memory.

This post assumes you have the layer deployed and both `.env` (Frank) and `.env_hop` (Hop) set up. If you don't — read the [building post first]({{< relref "/docs/building/31-edge-observability" >}}). The two `source .env*` files are not interchangeable; sourcing `.env` after `.env_hop` overrides `KUBECONFIG` back to Frank and silently sends Hop commands to the wrong cluster. The single most common mistake on Hop work.

## Querying the blog log stream

VictoriaLogs lives in `monitoring` on Frank. Grafana Explore is the human-facing query path; LogsQL is the syntax. The fluent-bit pipeline on Hop ships Caddy + CrowdSec + Falco logs all to the same VictoriaLogs instance via `192.168.55.225:9428/insert/jsonline`, so the **field shapes are different across sources** and that's the first thing to learn.

The dotted `kubernetes.namespace_name` shape — not the underscore form `kubernetes_namespace_name` — is what the fluent-bit kubernetes filter emits with `Merge_Log On`. Queries using the legacy underscore form return zero hits. Burned an evening on that one.

```
# All blog requests in the last 5 minutes (Caddy access logs)
_time:5m kubernetes.namespace_name:caddy-system AND _msg:"handled request"

# All 5xx responses from blog.derio.net in the last hour
_time:1h kubernetes.namespace_name:caddy-system AND _msg:"handled request" AND status:>=500

# Top-N requested paths in the last 24h
_time:24h kubernetes.namespace_name:caddy-system AND _msg:"handled request" | stats by (request.uri) count() as hits | sort by (hits desc) | limit 10

# Bot-vs-human ratio by UA family in the last 6h
_time:6h kubernetes.namespace_name:caddy-system AND _msg:"handled request" | stats by (request.headers.User-Agent) count() as hits | sort by (hits desc) | limit 20

# CrowdSec ban events
_time:1h kubernetes.namespace_name:crowdsec-system AND log:Adding AND log:decisions

# Falco events by priority
_time:1h source:syscall | stats by (priority, rule) count() as c | sort by (c desc)
```

Two endpoint shapes to know:

- `/select/logsql/query` — long series of log lines. What Grafana Explore calls. Used for inspection.
- `/select/logsql/stats_query` — Prometheus-style instant vector. What alert rules need (set `queryType: stats` on the rule). Returns scalars suitable for SSE reduce.

Programmatic access from inside the cluster:

```
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata: { name: vlogs-q, namespace: monitoring }
spec:
  restartPolicy: Never
  securityContext: { runAsNonRoot: true, runAsUser: 100, seccompProfile: { type: RuntimeDefault } }
  containers:
    - name: curl
      image: curlimages/curl
      command: ["sleep", "60"]
      securityContext: { allowPrivilegeEscalation: false, capabilities: { drop: ["ALL"] } }
EOF

kubectl exec -n monitoring vlogs-q -- curl -sG \
  'http://victoria-logs-victoria-logs-single-server.monitoring.svc:9428/select/logsql/query' \
  --data-urlencode 'query=_time:5m kubernetes.namespace_name:caddy-system' \
  --data-urlencode 'limit=5'

kubectl delete pod -n monitoring vlogs-q --force --grace-period=0
```

## GoatCounter — the analytics dashboard

Mesh-only admin at `https://counter.cluster.derio.net`. Behind Traefik's `authentik-forwardauth` middleware, so Authentik admits you first, then GoatCounter shows its own login. The bootstrap user was created from CLI:

```
# Create or reset a site/user from CLI (manual op `obs-goatcounter-bootstrap-first-site`)
kubectl exec -n goatcounter-system deploy/goatcounter -- sh -c \
  "goatcounter db create site \
    -db sqlite+/home/goatcounter/goatcounter-data/goatcounter.sqlite3 \
    -vhost counter.cluster.derio.net \
    -user.email <email> \
    -user.password '<strong-password>'"

# Show the site row
kubectl exec -n goatcounter-system deploy/goatcounter -- \
  goatcounter db show site \
  -db sqlite+/home/goatcounter/goatcounter-data/goatcounter.sqlite3 \
  -find counter.cluster.derio.net
```

The API token Grafana uses for the Infinity datasource is read-only (`count,export,site_read` perms). To rotate it:

```
# Create a fresh token (revoking the old one is via UI Settings → API tokens)
kubectl exec -n goatcounter-system deploy/goatcounter -- sh -c \
  "goatcounter db create apitoken \
    -db sqlite+/home/goatcounter/goatcounter-data/goatcounter.sqlite3 \
    -name grafana-readonly-$(date +%Y%m%d) \
    -user 1 -perm count,export,site_read"

# List tokens to grab the new value
kubectl exec -n goatcounter-system deploy/goatcounter -- \
  goatcounter db show apitoken \
  -db sqlite+/home/goatcounter/goatcounter-data/goatcounter.sqlite3 \
  -find $TOKEN_ID

# Update the Secret Grafana reads from
kubectl create secret generic grafana-goatcounter-token -n monitoring \
  --from-literal=OBS_GOATCOUNTER_API_TOKEN=<NEW> \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart -n monitoring deploy/victoria-metrics-grafana
```

The public ingest at `counter.derio.net` is served by Hop's Caddy reverse-proxying to `192.168.55.224:8080` over Tailscale. A quick liveness probe from anywhere:

```
# count.js must be HTTP 200 and ~8 KB
curl -s -o /dev/null -w 'count.js: %{http_code} size=%{size_download}\n' \
  https://counter.derio.net/count.js
```

If that returns anything other than 200 + ~8 KB, the failure modes (in order of probability):

1. Hop's Caddy can't reach Frank's GoatCounter LB IP. Check `kubectl exec` (on Hop) into a curl pod and `curl -sf http://192.168.55.224:8080/`.
2. Tailscale subnet route to `192.168.55.0/24` is down. `kubectl -n headscale-system exec ds/tailscale -- tailscale status` and look for the raspi subnet routers (`raspi-vlan10-d`, `raspi-vlan10-e`).
3. GoatCounter Pod is unhealthy. `kubectl -n goatcounter-system get pod` — if CrashLoopBackOff, check the logs; likely the `enableServiceLinks: false` regression (see the gotcha below).

## CrowdSec — banning, unbanning, and tuning

Three things you'll do on a normal week: list current decisions, ban an IP, unban an IP. All via `cscli` inside the LAPI pod.

```
# List current bans
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- cscli decisions list

# Ban an IP for 4 hours
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- \
  cscli decisions add --ip 198.51.100.42 --duration 4h --reason "suspicious traffic — see logs"

# Ban a /24 (e.g. a scraper farm)
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- \
  cscli decisions add --range 91.92.0.0/16 --duration 24h --reason "sitemap walker farm"

# Unban an IP
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- \
  cscli decisions delete --ip 198.51.100.42

# List currently-registered bouncers
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- cscli bouncers list

# Reload the agent's scenarios after a config change
kubectl exec -n crowdsec-system deploy/crowdsec-agent -- cscli hub list -o human
```

The bouncer ticker is 10 seconds — a freshly-issued ban is enforced within ~10s on the next `caddy` pull, and unbans propagate at the same cadence.

The community blocklist subscription is deferred (free-tier sign-up at `app.crowdsec.net` is pending), so the agent today applies only local scenarios from the bundled collections (`crowdsecurity/caddy`, `crowdsecurity/base-http-scenarios`, `crowdsecurity/http-cve`, `crowdsecurity/http-dos`). To enroll later:

```
# Manual op `obs-crowdsec-community-blocklists`
# 1. Sign up at app.crowdsec.net, create a Security Engine, copy the enrollment token
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- cscli console enroll <TOKEN>
# 2. Accept the engine in the crowdsec.net UI
# 3. Subscribe to community blocklist
```

### The bouncer key re-registration trap

Hop has no PVC for CrowdSec LAPI. Decision data and bouncer registrations are emptyDir — every LAPI restart wipes them. The `postStart` lifecycle hook re-registers `caddy-hop` with the fixed key from the `crowdsec-bouncer-keys` Secret:

```yaml
lapi:
  env:
    - name: CADDY_HOP_BOUNCER_KEY
      valueFrom:
        secretKeyRef: { name: crowdsec-bouncer-keys, key: caddy-hop }
  lifecycle:
    postStart:
      exec:
        command: [/bin/sh, -c, ...]   # cscli bouncers add caddy-hop -k "$CADDY_HOP_BOUNCER_KEY"
```

If the bouncer ever shows up missing from `cscli bouncers list` after a restart, the postStart hook silently failed (LAPI not ready yet). The fix is a manual re-register with the same key:

```
KEY=$(kubectl -n crowdsec-system get secret crowdsec-bouncer-keys -o jsonpath='{.data.caddy-hop}' | base64 -d)
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- cscli bouncers add caddy-hop -k "$KEY"
```

If `bouncers add` errors with "already exists" — good, that's actually success (it's idempotent at the cscli level). What you don't want is silence followed by Caddy bouncer logs spamming `access forbidden` every 10 seconds. That's the sign the key got de-synced between the two secrets; rotate both:

```
BK=$(openssl rand -hex 32)
kubectl create secret generic crowdsec-bouncer-keys -n crowdsec-system \
  --from-literal=caddy-hop="$BK" --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic caddy-crowdsec -n caddy-system \
  --from-literal=CROWDSEC_BOUNCER_API_KEY="$BK" --dry-run=client -o yaml | kubectl apply -f -
# Then re-register and restart Caddy
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- cscli bouncers delete caddy-hop
kubectl exec -n crowdsec-system deploy/crowdsec-lapi -- cscli bouncers add caddy-hop -k "$BK"
kubectl rollout restart -n caddy-system deploy/caddy
```

This is documented in the manual-operations runbook as `obs-crowdsec-bouncer-api-key`.

### Update (June 2026) — LAPI state is now persistent

The emptyDir story above had a worse failure mode than a de-synced bouncer key. The CrowdSec *agent* registers itself as a machine in the LAPI's SQLite DB; that DB was emptyDir too, so every LAPI restart wiped the agent's machine row and the agent crashlooped with `ent: machine not found` — parsing zero logs and banning nothing, while the dashboard stayed green. A live scan-trace (scanners throwing hundreds of webshell/`.env` probes, none banned) surfaced it.

The LAPI `data` and `config` folders now live on two static `hostPath` PVs (`clusters/hop/apps/storage/manifests/pv-crowdsec-{data,config}.yaml`, subdirectories of the already-mounted Hetzner Volume — no new volume). Consequences for operations:

- The bouncer registration and the community-blocklist enrollment **survive restarts**. The `obs-crowdsec-bouncer-api-key` and `obs-crowdsec-community-blocklists` manual ops are now **one-time setup**, not after-every-restart chores. The `postStart` hook stays as a belt-and-suspenders seed for a first-deploy (empty) DB.
- **Once the agent's machine row is in the persistent DB, every later LAPI restart keeps it** — the agent stays validated, no crashloop. The catch is the *cutover itself* (see below).

**Cutover gotcha — roll the agent once.** The agent is a *DaemonSet* that registers its machine **only in an initContainer** (`cscli lapi register`). On the emptyDir→persistent switch the new LAPI DB is fresh-empty, and the running agent keeps its old creds. A crashlooping container does **not** re-run its initContainer, and nothing changed the agent's pod template, so kubelet won't recreate it — the agent is stuck `ent: machine not found` until you roll it by hand. One-time, at cutover (and any time the agent's emptyDir creds ever diverge from the DB):

```
kubectl -n crowdsec-system rollout restart daemonset/crowdsec-agent   # re-runs the register initContainer
```

**Single-node assumption.** These PVs use `hostPath` with `DirectoryOrCreate` and the inherited `nodeAffinity: hostname Exists` (a tautology — matches any node). On Hop's one node that's fine, but if Hop ever gains a second node and the LAPI pod schedules there, `DirectoryOrCreate` silently makes a *fresh empty* dir and you lose the DB again — silently. Pin the LAPI pod (and these PVs) to `hop-1` before adding a node.

Verify the pipeline is actually alive (do this, don't trust the tile):

```
# PVs bound to the chart's claims
kubectl get pv crowdsec-data crowdsec-config          # both Bound → crowdsec-system/crowdsec-{db,config}-pvc

# (first deploy only) re-register the agent against the fresh persistent LAPI
kubectl -n crowdsec-system rollout restart daemonset/crowdsec-agent

# Agent validated, not crashlooping
kubectl -n crowdsec-system get pods                   # crowdsec-agent Running, restarts not climbing
kubectl -n crowdsec-system exec deploy/crowdsec-lapi -- cscli machines list   # agent present + validated (✔)

# Persistence survives a restart — WITHOUT re-registering the agent this time
kubectl -n crowdsec-system rollout restart deploy/crowdsec-lapi
# …wait Ready, then re-check machines list → still validated, no "machine not found" in agent logs

# End-to-end: a real scan must produce a real ban (the only proof that counts)
#   from a disposable/VPN egress (NOT your own IP):
#   for p in .env .git/config .env.production; do curl -s -o /dev/null https://blog.derio.net/$p; done  (×~15)
kubectl -n crowdsec-system exec deploy/crowdsec-lapi -- cscli decisions list   # a ban for the scan source IP
```

> **Static-PV recovery note.** Reclaim policy is `Retain`, so if either PVC is ever deleted (e.g. a chart uninstall) the PV goes `Released`, not `Available`, and won't rebind to a freshly-recreated same-name PVC until you clear the stale binding:
> `kubectl patch pv crowdsec-data -p '{"spec":{"claimRef":{"uid":null}}}'` (data is preserved on disk).

### Update (June 2026, part 2) — the agent has to actually *parse* the logs

Fixing the crashloop got the agent running, but the first real ban test found it still banned nothing. The agent reads the Caddy logs but parses **zero** of them — because Talos runs containerd (CRI log format) while the chart defaulted `container_runtime: docker`. The `docker-logs` parser expects Docker json-file format and extracts an empty message from a CRI line, so `caddy-logs` never engages. The tell is in `cscli metrics`:

```
# On the agent — the smoking gun:
kubectl -n crowdsec-system exec daemonset/crowdsec-agent -c crowdsec-agent -- cscli metrics
#   Acquisition Metrics: Lines read > 0  but  Lines parsed = 0   (everything "unparsed")
#   Parser Metrics:      only crowdsecurity/docker-logs — NO crowdsecurity/caddy-logs hits
```

The fix is the chart's own knob — `container_runtime: containerd` in `clusters/hop/apps/crowdsec/values.yaml`. That routes logs through `cri-logs` (which strips the `<ts> stdout F` envelope), and the acquisition's `program: caddy` label still reaches `caddy-logs`. Verify the whole chain on one real line without sending any traffic:

```
kubectl -n crowdsec-system exec daemonset/crowdsec-agent -c crowdsec-agent -- sh -c \
  'grep -m1 http.log.access /var/log/containers/caddy-*_caddy-system_*.log > /tmp/one.log; \
   cscli explain -f /tmp/one.log --type containerd --labels program:caddy'
#   expect: cri-logs 🟢 → caddy-logs 🟢 → enrichers 🟢 → parser success → scenarios fire
```

After it's parsing, `Lines parsed` climbs and a sensitive-files scan produces a real `cscli decisions list` ban. (`cscli explain --type cri` is a red herring — the parser's filter is `type == 'containerd'`, not `cri`.)

## Falco — tuning out the noise

Most of Falco's default rule set on Talos is quiet. The exception is `Contact K8S API Server From Container` (priority `Notice`), which fires constantly because every Kubernetes-native workload talks to the API server. Below `Critical` priority, falcosidekick ships events to Loki (silently) but skips Telegram — exactly what we want.

To inspect the Falco firehose:

```
# Top firing rules in the last hour
kubectl logs -n falco-system ds/falco -c falco --since=1h | \
  grep '"rule"' | python3 -c "
import sys, json, collections
c = collections.Counter()
for line in sys.stdin:
    try: c[json.loads(line)['rule']] += 1
    except: pass
for r, n in c.most_common(20): print(f'{n:6}  {r}')
"

# Falcosidekick connection state (Loki + Telegram both enabled)
kubectl logs -n falco-system deploy/falco-falcosidekick --tail 20 | \
  grep -iE "enabled outputs|loki|telegram"
```

The /test endpoint is the canonical way to verify both outputs are still healthy without waiting for a real event:

```
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata: { name: fk-test, namespace: falco-system }
spec:
  restartPolicy: Never
  securityContext: { runAsNonRoot: true, runAsUser: 100, seccompProfile: { type: RuntimeDefault } }
  containers:
    - name: curl
      image: curlimages/curl
      command: ["sleep", "30"]
      securityContext: { allowPrivilegeEscalation: false, capabilities: { drop: ["ALL"] } }
EOF
sleep 3
kubectl exec -n falco-system fk-test -- curl -sf -X POST http://falco-falcosidekick.falco-system:2801/test
kubectl logs -n falco-system deploy/falco-falcosidekick --tail 10 | grep -iE "test|POST OK"
kubectl delete pod -n falco-system fk-test --force --grace-period=0
```

Expect `Loki - POST OK (204)` and `Telegram - POST OK (200)` within seconds. A Telegram message should arrive almost simultaneously.

### Tuning a noisy rule

Falco's macro override pattern is non-obvious and worth practicing once on a safe rule before you need it on a critical one. There is **no `override:` key** in the Falco schema — re-declaration is how overrides work. The chart's `customRules.<filename>` blocks are loaded after the default rules, so a macro with the same name in your custom file replaces the default.

```yaml
# clusters/hop/apps/falco/values.yaml
customRules:
  talos-quiet.yaml: |-
    - macro: user_known_shell_in_container_activities
      condition: (k8s.ns.name = "kube-system")
```

After editing, ArgoCD-sync the chart (Hop's auto-sync picks it up within a minute), then restart the DaemonSet so the new rules ConfigMap mounts:

```
kubectl -n argocd patch application falco --type=merge \
  -p '{"operation":{"sync":{"revision":"HEAD","syncOptions":["ServerSideApply=true","RespectIgnoreDifferences=true"]}}}'

source .env_hop
kubectl rollout restart -n falco-system ds/falco
kubectl rollout status -n falco-system ds/falco --timeout 120s
```

If Falco crashloops after the rule change, the most common cause is invalid YAML in the inline rule body (escaping inside the `|-` block scalar). `kubectl logs -n falco-system ds/falco -c falco --tail 50` shows the parse error.

## The ai-alert-helper

Four entrypoints since 0.2.0: `/digest` (daily 08:00 UTC), `/alert` (Grafana webhook), `/surge-check` (15-min cron), and `/ask` (the analyst — also reachable as a two-way Telegram chat, below). Triggering the cron-backed ones by hand is a one-liner:

### The Telegram analyst (0.2.0)

Reply to `@agent_zero_cc_bot` in the alert chat. Two modes:

- **Slash commands — deterministic, no LLM, no GPU dependency.** `/help` lists everything; the Telegram `/` menu autocompletes. The workhorses:
  ```
  /scan_patterns 6h                      # probe-path hit counts (wp-login, .env, …)
  /edge_traffic 1h group_by=host         # who's hitting which vhost
  /attacker_profile 203.0.113.7 24h      # everything one IP did
  /falco_events 12h priority=Critical
  /crowdsec_decisions 24h
  /logsql <any LogsQL with a _time: filter>
  ```
  Append ` explain` to any of them for an LLM narration of the result.
- **Plain questions — the LLM loop.** "who scanned the blog today and what were they after?" → `mistral-small-24b` calls the same tools (≤6 rounds, 120s cap) and answers in-thread, citing only tool-returned evidence. `/reset` clears the conversation; history expires after 30 idle minutes.

Operational notes: the poller long-polls `getUpdates`, so the Deployment must stay **single-replica with `strategy: Recreate`** (Telegram allows one consumer per bot token). Messages from any chat but the operator's are dropped and logged at WARNING — check `kubectl logs deploy/ai-alert-helper | grep dropped` if the bot seems deaf; that's the gate working. Pre-merge-style verification without Telegram:

```
kubectl exec -n ai-alert-helper-system deploy/ai-alert-helper -- python -c "
import urllib.request, json
r=urllib.request.urlopen(urllib.request.Request('http://localhost:8080/ask?dry_run=true',
  data=json.dumps({'question':'are we being scanned?'}).encode(),
  headers={'Content-Type':'application/json'}, method='POST'), timeout=150)
print(json.loads(r.read())['answer'])"
```

The analyst's knowledge lives in `apps/ai-alert-helper/skill/SKILL.md` (also a Claude Code skill — one playbook, two readers). Editing it rolls the pod automatically via the hash-suffixed ConfigMap. The model's context window is set server-side (`OLLAMA_CONTEXT_LENGTH` on the Ollama Deployment) because LiteLLM drops per-request `num_ctx` for `ollama_chat` — if answers start missing earlier evidence, check Ollama logs for `truncating input prompt` before blaming the model.

```
# Trigger today's digest right now
kubectl create job -n ai-alert-helper-system digest-now --from=cronjob/digest
kubectl logs -n ai-alert-helper-system job/digest-now -f
# Telegram message arrives within ~10s
kubectl delete job -n ai-alert-helper-system digest-now

# Trigger a surge check (will be no-op if traffic is normal)
kubectl create job -n ai-alert-helper-system surge-now --from=cronjob/surge-check
kubectl logs -n ai-alert-helper-system job/surge-now -f
# Output: {"triggered":false,"window_end":"...","current":N,"baseline":M,"ratio":X,"tier":null}
kubectl delete job -n ai-alert-helper-system surge-now

# Post a synthetic Grafana alert payload to /alert (verifies the LLM enrichment path)
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata: { name: alert-test, namespace: ai-alert-helper-system }
spec:
  restartPolicy: Never
  securityContext: { runAsNonRoot: true, runAsUser: 100, seccompProfile: { type: RuntimeDefault } }
  containers:
    - name: curl
      image: curlimages/curl
      command: ["sleep", "60"]
      securityContext: { allowPrivilegeEscalation: false, capabilities: { drop: ["ALL"] } }
EOF
sleep 3
kubectl exec -n ai-alert-helper-system alert-test -- sh -c "cat > /tmp/p.json <<'JSON'
{\"alerts\":[{\"status\":\"firing\",\"labels\":{\"alertname\":\"CrowdSecDecisionBurst\",\"severity\":\"warning\",\"grafana_folder\":\"blog-edge\"}}]}
JSON
curl -sf -X POST -H 'Content-Type: application/json' -d @/tmp/p.json http://ai-alert-helper:8080/alert"
kubectl delete pod -n ai-alert-helper-system alert-test --force --grace-period=0
```

### Reading the digest

The morning digest is three distinct things stacked into one message, and they answer three different questions:

- **Blog readers** — `blog_pageviews`, `blog_top_pages`, `blog_top_referrers`, sourced from GoatCounter. This is "who actually read the blog yesterday." A direct (no-referrer) hit shows up labelled `direct`, not blank.
- **Edge traffic** — `edge_requests_total` plus the per-vhost and per-status-class breakdown, sourced from Caddy access logs scoped to `kubernetes.host:hop-1`. This is "everything Hop's reverse proxy handled" — Headscale, Headplane, ACME, bots, probes, *and* the blog. Edge total dwarfs blog pageviews (15k+/day vs. low hundreds); the per-vhost line is what tells you how much of that was actually `blog.derio.net`.
- **Security** — `falco_by_priority` (all priorities, not just Critical), `falco_top_rules`, `falco_critical_rules` (rule names for the Criticals specifically), and `crowdsec_decisions`.

The one window asymmetry worth internalising: **traffic and pageviews cover the prior calendar day, but the security window runs from yesterday 00:00 through the moment the digest runs.** That's deliberate — a benign Critical that fires at 03:00 UTC (e.g. the headscale-backup `sqlite3 .backup`) would otherwise wait ~29h to appear. With the split window it lands in *this* morning's digest, the same day you'd want to glance at it. So an "overnight" Critical event appearing in today's message is by design, not a clock bug.

### Auditing the fact sheet without sending Telegram

`POST /digest?dry_run=true` builds the exact fact sheet the digest would summarise and returns it as JSON **without** calling the LLM or posting to Telegram. This is the canonical way to check what the digest is actually seeing — if a number looks wrong in the morning message, dump the facts first and decide whether the bug is in the data or the prompt:

```
# Exec into the running helper and hit its own port — no extra pod needed
kubectl exec -n ai-alert-helper-system deploy/ai-alert-helper -- \
  curl -sf -X POST "http://localhost:8080/digest?dry_run=true" | jq .
# → {"facts": {"edge_requests_total": ..., "edge_requests_by_vhost": [...],
#               "blog_pageviews": ..., "blog_top_pages": [...],
#               "falco_by_priority": [...], "falco_critical_rules": [...], ...},
#     "narrative": null}
```

The `"narrative": null` confirms the LLM was skipped. Cross-check `edge_requests_by_vhost` against `blog_pageviews` here — if edge traffic is high but blog pageviews are zero, the problem is GoatCounter (token permissions, range, SSO redirect), not the prompt.

### Rotating LLM models

The helper picks `LLM_MODEL_PRIMARY` first (default `qwen-think-14b`, local on gpu-1) and falls back to `LLM_MODEL_FALLBACK` (default `claude-haiku-4-5`) on timeout or 5xx. Either can be overridden via env. To swap to a different local model:

```
kubectl set env -n ai-alert-helper-system deploy/ai-alert-helper LLM_MODEL_PRIMARY=qwen-coder-14b
kubectl rollout status -n ai-alert-helper-system deploy/ai-alert-helper
```

If the fallback model is exercised in production you'll see it in the helper's logs:

```
kubectl logs -n ai-alert-helper-system deploy/ai-alert-helper --tail 100 | \
  grep -iE "fallback|timeout|503|retry"
```

### Tuning the surge detector

`/surge-check` runs every 15 min, compares the last complete hour of **blog edge requests** against an hour-of-day baseline (median of the same hour over the prior 7 days), and pages if traffic spiked *and* real visitors showed up. Three env knobs on the Deployment tune it:

```
# Minimum requests/hour for ANY tier — stops a baseline of 1 (quiet hour →
# median 0 → forced to 1) from turning a trickle into a "surge". Exactly
# SURGE_ABS_FLOOR fires (the comparison is current < floor → no tier).
kubectl set env -n ai-alert-helper-system deploy/ai-alert-helper SURGE_ABS_FLOOR=50
# Minimum GoatCounter pageviews in the window to confirm a Major as URGENT.
kubectl set env -n ai-alert-helper-system deploy/ai-alert-helper SURGE_VISITOR_FLOOR=10
# Min hours before re-notifying the SAME tier — de-dups repeat bot-surge Notables.
kubectl set env -n ai-alert-helper-system deploy/ai-alert-helper SURGE_COOLDOWN_HOURS=6
```

**Reading a surge message:**

- **`(Major)` + urgent** — edge spiked *and* GoatCounter confirms ≥`SURGE_VISITOR_FLOOR` real pageviews. A genuine human surge (HN/Reddit). Act on it.
- **`(Major) (visitor data unavailable)` + urgent** — edge spiked but GoatCounter was unreachable; it pages anyway (fail-open) rather than miss a real surge. Check GoatCounter.
- **`(Notable)` + non-urgent** — edge spiked but GoatCounter shows no humans, so a Major was downgraded: bots/scrapers/scanners, not readers. Informational; cross-check with CrowdSec/Falco if sustained.

**De-duplication.** `/surge-check` is stateless and runs every 15 min against the same completed hour, so without help it would re-send the same Notable ~4×/hot-hour. It now keeps **in-memory** notification state and only sends on a *rising edge* (a tier first appearing, or escalating Notable→Major); it stays silent while the same-or-lower tier persists, and won't re-notify the same tier again until `SURGE_COOLDOWN_HOURS` (default 6) elapses. Escalation to a confirmed-human URGENT always passes immediately. A pod restart re-arms the state (at most one extra message). To watch it, grep the **helper** Deployment logs (the cron's `curl` discards the body): `kubectl -n ai-alert-helper-system logs deploy/ai-alert-helper | grep -E "surge (sent|suppressed)"`.

**Grounded narrative.** The verdict is now built from `top_referrers` (GoatCounter), `top_paths` and `top_user_agents` (Caddy, probe-excluded) for the window — so it cites real evidence. It names Hacker News *only* if a `news.ycombinator.com` referrer is present, calls a bot-UA-with-no-visitors spike a scraper, and says "Cause: undetermined" when there's nothing to go on. (Previously the prompt pre-seeded "Hacker News" and the fact sheet was empty, so every surge was blamed on HN with zero evidence.)

Frank's own blackbox uptime probe (~360 req/hr to `blog.derio.net`) is tagged `Frank-Blackbox-Probe` and excluded from the count — it must never read as a surge. If you ever change that User-Agent in `apps/blackbox-exporter/manifests/configmap.yaml`, update `facts.PROBE_UA_TOKEN` to match (a unit test pins it).

**Dry-running a check.** `/surge-check` has no `dry_run` (any computed tier sends Telegram), so to see what it *would* do without sending, replay `surge.compute`'s queries through VictoriaLogs:

```bash
source .env
VL=http://192.168.55.225:9428
# current hour's probe-excluded blog edge count (compare to your baseline mentally)
curl -s "$VL/select/logsql/stats_query" --data-urlencode \
  'query=_time:1h kubernetes.host:hop-1 AND _msg:"handled request" AND `request.host`:"blog.derio.net" AND -`request.headers.User-Agent`:"Frank-Blackbox-Probe" | stats count() as c'
```

> **2026-05-25 worked example.** A `370× baseline (Major)` URGENT fired with GoatCounter flat. The "370" was Frank's own blackbox probe against a baseline forced to 1; no humans. The fix (probe identity + absolute floor + the visitor cross-check above) turns that exact case into *no message*. Note: just after re-tagging the probe, the old-UA hits linger in the 1h window for ~1–2h and can transiently trip a non-urgent Notable until they age out.

### The agentic rewrite (June 2026) — namespace `alert-agent`

The FastAPI analyst above was retired and rebuilt as an autonomous `claude` session on the `multi-agent-shell` image (namespace `alert-agent`). Same bot `@agent_zero_cc_bot`, same `frank-facts` tools (now a stdlib CLI), but the brain is a persistent cloud-claude driven over a pod-local HTTP endpoint — no LiteLLM, no GPU dependency. The slash commands and free-text Q&A above still apply; what's new is the agent *runtime*. Same single-consumer constraint as before — `replicas: 1`, `strategy: Recreate` (one `getUpdates` consumer, one persistent tmux session per chat).

**Re-authenticate claude when DMs start returning the fallback.** The agent is a Max-OAuth `claude`; the token lives on the `alert-agent-home` PV at `~/.claude/.credentials.json` and auto-refreshes, but it can expire or get rotated out (one account, several `claude_code` sessions). Re-login interactively, then clear the stale sessions so the driver recreates them on the fresh creds:

```bash
kubectl -n alert-agent exec -it deploy/alert-agent -c agent -- claude   # /login, open the URL, paste the code, exit
kubectl -n alert-agent exec deploy/alert-agent -c agent -- tmux kill-server
# the next DM lazy-creates an authenticated session
```

**Debug a non-answering DM by reading the session pane** — the agent is a real claude REPL, and the pane shows exactly what it's doing (working, stuck, at a login screen, or fumbling for `kubectl`):

```bash
P=$(kubectl -n alert-agent get pod -l app.kubernetes.io/name=alert-agent -o jsonpath='{.items[0].metadata.name}')
kubectl -n alert-agent exec $P -c agent -- bash -lc 'tmux ls'                       # alert-agent-ops + alert-agent-tg-<chat>
kubectl -n alert-agent exec $P -c agent -- bash -lc 'tmux capture-pane -t alert-agent-tg-<chat> -p | tail -30'
kubectl -n alert-agent exec $P -c agent -- bash -lc 'which -a claude'               # MUST resolve ~/.local/bin/claude (native)
```

Read the pane: a turn churning past ~2 min but still answering is just *slow* — raise `DM_TIMEOUT_S` (default 600s) on the `agent` container. A `claude.com/cai/oauth` login screen means re-auth (above). A *bash* pane, or `which claude` resolving `/usr/bin/claude` instead of `~/.local/bin/claude`, means an image regression (continuum restore, or the `$AGENT_HOME` PATH / native-install) — full prose in `docs/runbooks/frank-gotchas/agent-shells.md`.

**Drive a turn without Telegram** (pre-Telegram smoke test — the agent is HTTP-only, no kube creds):

```bash
kubectl -n alert-agent exec $P -c agent -- sh -c \
  'curl -s localhost:8765/session/send -H "Content-Type: application/json" \
   -d "{\"session_id\":\"smoke\",\"agent\":\"claude\",\"message\":\"what is the cluster status?\",\"timeout_s\":600}"'
# → {"status":"ok","turn":1,"payload":{"text":"…"}}  — a fresh session answers in ~30s
```

The agent's instructions (tools + the HTTP-only/no-kubectl boundary) mount as `~/AGENTS.md` + `~/CLAUDE.md`; the image fans the canonical `AGENTS.md` out to every harness's context filename. If you change the mounted instructions file, it MUST be one a harness loads — claude reads `CLAUDE.md` **only**, never `SKILL.md` — or free-text DMs go blind. `AGENT_TMUX_RESTORE=off` keeps tmux-continuum from resurrecting dead sessions on the agent pod.

## Alerts — what's there, how to suppress, how to investigate

The two rules in the `blog-edge` folder:

| Rule | Severity | Threshold | Routes to |
|------|----------|-----------|-----------|
| `CrowdSec decision burst` | warning | >10 bans in last 5m | AI Helper Webhook → Telegram |
| `Falco critical event` | critical | any priority:Critical in last 5m | AI Helper Webhook → Telegram |

The notification policy routes `grafana_folder="blog-edge"` exclusively to the AI helper (no double-notification through the default Telegram contact point). To check current rule states programmatically:

```
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata: { name: gf-rules, namespace: monitoring }
spec:
  restartPolicy: Never
  securityContext: { runAsNonRoot: true, runAsUser: 100, seccompProfile: { type: RuntimeDefault } }
  containers:
    - name: curl
      image: curlimages/curl
      command: ["sleep", "60"]
      env:
        - { name: GF_USER, valueFrom: { secretKeyRef: { name: victoria-metrics-grafana, key: admin-user } } }
        - { name: GF_PASS, valueFrom: { secretKeyRef: { name: victoria-metrics-grafana, key: admin-password } } }
      securityContext: { allowPrivilegeEscalation: false, capabilities: { drop: ["ALL"] } }
EOF
sleep 3
kubectl exec -n monitoring gf-rules -- sh -c \
  'curl -sf -u "$GF_USER:$GF_PASS" http://victoria-metrics-grafana.monitoring.svc:80/api/prometheus/grafana/api/v1/rules' | \
  python3 -c "import json,sys; d=json.load(sys.stdin); [[print(r['name'],'->',r['state'],r.get('lastError','')[:80]) for r in g['rules']] for g in (gg for f in d['data']['groups'] for gg in [f] if f['name'].startswith('blog'))]"
kubectl delete pod -n monitoring gf-rules --force --grace-period=0
```

If you see `lastError` populated with `[sse.readDataError]`, the rule's data step is missing `queryType: stats` — the gotcha that bit me on day one and now lives in `agents/rules/frank-gotchas.md`.

To silence an alert temporarily (UI is faster than CLI for ad-hoc), Grafana → Alerting → Silences → New. CLI version:

```
# Grafana provisioning UI ratholes too easily; from the CLI:
kubectl exec -n monitoring gf-rules -- sh -c \
  'curl -sf -u "$GF_USER:$GF_PASS" -X POST -H "Content-Type: application/json" \
    -d "{\"matchers\":[{\"isEqual\":true,\"isRegex\":false,\"name\":\"alertname\",\"value\":\"CrowdSec decision burst\"}],\"endsAt\":\"$(date -u -v+1H +%Y-%m-%dT%H:%M:%SZ)\",\"comment\":\"investigating noise\",\"createdBy\":\"ops\"}" \
    http://victoria-metrics-grafana.monitoring.svc:80/api/alertmanager/grafana/api/v2/silences'
```

The silence has a 1-hour endsAt above; if you need longer, change `+1H`.

## Backup and restore

GoatCounter's SQLite DB lives on a Longhorn PVC. The backup story is the standard Longhorn one — `apps/longhorn-extras/manifests/recurring-jobs.yaml` already snapshots all PVCs. To restore from a snapshot:

```
# List snapshots for the goatcounter PVC
source .env
kubectl -n goatcounter-system get volumesnapshot

# Restore — create a new PVC from a snapshot
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: goatcounter-data-restored
  namespace: goatcounter-system
spec:
  storageClassName: longhorn
  dataSource:
    name: <snapshot-name>
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
  accessModes: [ ReadWriteOnce ]
  resources:
    requests:
      storage: 1Gi
EOF

# Then edit deployment.yaml to swap claimName from goatcounter-data → goatcounter-data-restored
# and let ArgoCD sync the change (or kubectl patch the Deployment for ad-hoc testing).
```

CrowdSec on Hop is intentionally without a PVC — restoration means nothing more than the `postStart` re-registering the bouncer from the static key Secret. There's no historical decision data to lose, by design.

## Gotchas, in increasing order of mean time to surprise

The five things most likely to bite me again, ordered by probability:

1. **Sourcing `.env` while working on Hop.** `.env` overrides `KUBECONFIG` back to Frank; commands silently target the wrong cluster. Always `source .env_hop` for Hop work, and check `kubectl get nodes` is showing the single hop-1 row before doing anything destructive.
2. **The bouncer key going out of sync.** The two-secret pattern (`crowdsec-bouncer-keys` on Hop, `caddy-crowdsec` on the same cluster but in `caddy-system`) needs both to hold the same hex string. If only one rotates, Caddy spams `access forbidden` and there is no Telegram alert about it — only the bouncer logs. The fix is the rotate-both procedure above.
3. **DatasourceError on new VictoriaLogs alert rules.** Default `queryType` is `instant`, which returns long-series. Grafana SSE rejects it. Set `queryType: stats` and rename the stats output column to `value`.
4. **GoatCounter env-var name collisions.** Kubernetes auto-injects `GOATCOUNTER_PORT=tcp://10.x:8080` when a Service named `goatcounter` exists in the namespace. GoatCounter reads `GOATCOUNTER_*` env vars as flag overrides and crashloops parsing `tcp://...` as a port. `enableServiceLinks: false` on the Pod spec fixes it.
5. **The 15-min surge cron is best-effort.** `surge.compute()` aligns its window to the top of the previous hour. A burst that arrives at HH:50 won't show in the window until HH+1:00+ — up to 25 min from start of burst to detection in the worst case. For tighter windows, either crank the schedule to `*/5 * * * *` or rewrite the surge.py logic to use a sliding window. We haven't.

## What this doesn't cover

- **The Paper authoring workflow.** That's covered by [Operating The Frank Papers]({{< relref "/docs/operating/25-frank-papers" >}}).
- **Cluster-wide Grafana operations.** The companion [Operating Observability]({{< relref "/docs/operating/05-observability" >}}) covers VictoriaMetrics, the Telegram bot, and the wider feature-health dashboards.
- **Hop infrastructure operations.** [Operating Hop]({{< relref "/docs/operating/11-public-edge" >}}) covers the cluster-level operations — Tailscale mesh state, Caddy TLS renewal, Headscale node management.

This post stays narrowly on the obs layer's own surface. The rest is somebody else's runbook.

## References

- {{< relref "/docs/building/31-edge-observability" >}} — Build narrative
- [`docs/investigations/2026-05-24--obs--edge-observability-research.md`](https://github.com/derio-net/frank/blob/main/docs/investigations/2026-05-24--obs--edge-observability-research.md) — Vendor-landscape research substrate (the series-shaped Paper was pulled; three narrower future papers seeded on {{< relref "/docs/papers" >}})
- `docs/runbooks/manual-operations.yaml` — 8 obs entries (search for `obs-`)
- `agents/rules/frank-gotchas.md` — Grafana section, with the `queryType: stats` gotcha
- [LogsQL syntax](https://docs.victoriametrics.com/victorialogs/logsql/) — Query language reference
- [CrowdSec docs](https://docs.crowdsec.net/) — `cscli` reference + scenarios
- [Falco rules reference](https://falco.org/docs/reference/rules/) — Macro re-declaration override pattern
