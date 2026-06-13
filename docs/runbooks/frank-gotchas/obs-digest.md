# Frank Gotchas — Observability Digest

Long-form companion to the **Observability digest** section in
`agents/rules/frank-gotchas.md`. Covers the `ai-alert-helper` daily digest's
log-field and time-window traps. The hot file has the one-liners; this file has
the prose, the field maps, and the live evidence.

## Falco events use Loki-push field names, not the fluent-bit ones

There are two log-shipping paths into Frank's VictoriaLogs, and they label
their fields differently:

| Path | Source | Namespace field | Notable fields |
|---|---|---|---|
| fluent-bit collector | Caddy, CrowdSec | `kubernetes.namespace_name` | `kubernetes.host`, `request.host` |
| falcosidekick → Loki-push | Falco | `k8s_ns_name` | `source`, `priority`, `rule` |

Falco events arrive via falcosidekick's Loki output, which emits the Falco-native
labels `source` / `priority` / `rule` / `k8s_ns_name` — **not**
`kubernetes.namespace_name`. A Falco query written with the fluent-bit field
name matches nothing.

```logsql
# WRONG — Falco events don't carry kubernetes.namespace_name.
_time:1d kubernetes.namespace_name:falco

# RIGHT — Falco syscall events, all priorities.
_time:1d source:syscall | stats by (priority) count()
```

Query Falco with `source:syscall` and break down by `priority` / `rule`. The
digest's `_digest_security_facts` builds three facts off this path:
`falco_by_priority` (all priorities), `falco_top_rules`, and
`falco_critical_rules` (rule names filtered to `priority:Critical`, so the LLM
can name *which* rule was the benign Critical rather than guessing).

Live evidence (2026-05-25), the `priority` breakdown shape over a day:

```
priority   count
Critical   1     # headscale-backup sqlite3 .backup → "Drop and execute new binary in container" @ 03:00 UTC
Warning    2     # "Read sensitive file untrusted"
```

The original digest counted only `priority:Critical`, so the two Warnings never
surfaced and the single Critical was reported ~29h late (see split window
below).

## The digest's split window: traffic vs. security

The daily "📊 Yesterday on the Frank blog" digest runs at 08:00 UTC and uses
**two different time windows**, by design:

- **Traffic + pageviews** = the prior calendar day `[since, until)`. This
  matches GoatCounter's daily buckets and the literal "Yesterday" in the title.
- **Security (Falco / CrowdSec)** = `[since, security_until)` where
  `security_until` is the digest's *run time* (≈08:00 today), not midnight.

The asymmetry exists so an overnight Critical surfaces same-morning. A benign
Critical that fires at 03:00 UTC (the headscale-backup CronJob's `sqlite3
.backup` tripping "Drop and execute new binary in container") would, under a
strict prior-calendar-day window, wait until the *next* morning's digest — ~29h
late. With the security window extended through run time, it lands in today's
message. So an "overnight" Critical appearing in a morning digest is expected
behaviour, not a clock bug.

In `api.py` the windows are:

```python
since = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
until = since + timedelta(days=1)                 # traffic = prior calendar day
sheet = facts.build_for_digest(since, until, now) # security runs to now
```

## Auditing the fact sheet

`POST /digest?dry_run=true` returns the full fact sheet as JSON without invoking
the LLM or posting to Telegram — the canonical way to confirm what the digest
actually sees before blaming the prompt:

```bash
kubectl exec -n ai-alert-helper-system deploy/ai-alert-helper -- \
  curl -sf -X POST "http://localhost:8080/digest?dry_run=true" | jq .
# "narrative": null confirms the LLM was skipped.
```

If `edge_requests_by_vhost` shows traffic but `blog_pageviews` is `0`, the
problem is the GoatCounter reader (token `stats` permission, exclusive-`end`
date range, or SSO redirect on the public URL — see the rework plan's
deployment deviations), not the prompt.

## The surge detector: probe identity, the floor, and the visitor gate

On 2026-05-25 `/surge-check` fired an **URGENT** "Blog traffic surge" while
GoatCounter showed nothing. Both signals were right — they measure different
things. The detector counts **Hop-edge Caddy requests** (`facts.edge_filter`);
GoatCounter counts **JS-beacon pageviews** from real browsers. Bots, scanners,
and uptime probes hit the edge but never run the beacon, so an edge surge with
a flat GoatCounter is the bot-vs-human signal, not a contradiction.

The false page had three compounding causes, each now fixed:

1. **Baseline forced to 1.** `surge.compute` baseline is
   `median(7 hour-of-day samples) or 1`. On a quiet blog the median is 0 →
   forced to 1, so "10× baseline" degenerates into "≥10 requests/hour".
   **Fix:** `SURGE_ABS_FLOOR` (default 50, ai-alert-helper Deployment env) —
   no tier when `current < floor` (the comparison is `<`, so exactly 50 fires).

2. **Frank's own probe counted as blog traffic.** The blackbox-exporter
   (`apps/blackbox-exporter`) probes `https://blog.derio.net` ~360×/hour; it
   leaves the cluster and returns via the home egress IP, so Caddy logs it as
   external blog traffic. **Fix:** the probe carries a self-controlled
   `User-Agent: Frank-Blackbox-Probe/1.0` (configmap `http_2xx` /
   `http_2xx_no_redirect` `headers:`), and `facts.edge_filter` excludes
   `facts.PROBE_UA_TOKEN` (`-`request.headers.User-Agent`:"Frank-Blackbox-Probe"`).
   We exclude Frank's **own probe identity**, not the vendor default UA —
   excluding `Blackbox Exporter` would whitelist any third-party blackbox /
   spoofer and is semantically wrong. The two strings are coupled across repos;
   a Python pinning test + cross-ref comments guard the drift.

3. **The documented GoatCounter cross-check was never implemented.** A `Major`
   edge tier must be confirmed by real visitors before paging. **Fix:**
   `/surge-check` calls `facts.surge_visitor_pageviews(start, end)`:
   - visitors ≥ `SURGE_VISITOR_FLOOR` (default 10) → **URGENT**;
   - GoatCounter unreachable (`None`) → **URGENT, fail-open**, message annotated
     `(visitor data unavailable)` — never suppress a possibly-real surge;
   - visitors < floor → **downgrade Major → non-urgent Notable**
     ("edge surge, no visitor confirmation — likely automated").
   `surge_visitor_pageviews` uses `_goatcounter_raw` (returns `None` on error,
   distinct from a real `0`); `_goatcounter` stays a `{}`-coercing wrapper so
   the daily digest can't crash on an unreachable GoatCounter.

### Re-tag transition residue (expected, transient)

For ~1–2h after the probe is re-tagged, the rolling `[HH:00, HH+1:00]` window
still contains old-UA (`Blackbox Exporter/0.25.0`) hits, which the new filter
does **not** exclude (it only excludes the new token). During that window
`current` is inflated and the edge tier can compute `Major`; the visitor gate
then downgrades it to a non-urgent Notable (no page). Once the residue ages
out, `current` drops below the floor → `triggered: false`. Verify what a check
*would* do without sending anything by replaying `surge.compute`'s 8 queries
through the VictoriaLogs `stats_query` API.

### Building the image (no manual docker)

`gh workflow run build-ai-alert-helper.yml --ref <branch>` builds the branch's
code with the branch's workflow and pushes the version-pinned tag to GHCR —
the same convention as caddy/openrgb. Bump the hardcoded tag in
`.github/workflows/build-ai-alert-helper.yml` with the version (`api.py`,
`pyproject.toml`, `deployment.yaml`). Deferred follow-up: derive the tag from
`pyproject.toml` so it can't go stale.

## Notification de-dup + grounded narrative (rework-1, 0.1.6)

The parent fix correctly distinguished bots from humans, but in operation the
blog edge still saw frequent crawler bursts (Baiduspider, wpbot, scrapers) of
50–270 req/hr — ~10 of 24 hours on 2026-05-26 cleared `SURGE_ABS_FLOOR`. Each is
an edge-Major that the visitor gate downgrades to a non-urgent Notable, but
because `/surge-check` is stateless and runs every 15 min against the same
completed hour, it re-sent the same Notable ~4× per hot hour (~20/night). And
the narrative blamed "Hacker News" every time — the prompt pre-seeded it and the
fact sheet carried no referrers/paths/UAs to argue otherwise.

**De-dup.** `/surge-check` keeps an **in-memory** `_last_notify = {tier, at}` and
gates with `_should_notify = rising or cooled`: `rising` = the final tier
outranks the last-sent tier (escalation); `cooled` = `SURGE_COOLDOWN_HOURS`
(default 6) elapsed since the last send. A sustained or flapping bot surge sends
once per cooldown; a genuine escalation to a confirmed-human URGENT always passes
immediately. The gate runs **before** `build_for_surge` + the LLM call, so
suppressed ticks are cheap. State is process-global and safe (single replica,
one uvicorn worker, cron `concurrencyPolicy: Forbid` → no concurrent
`/surge-check`); a pod restart re-arms (at most one extra message); not persisted
(no PVC — a cooldown doesn't warrant one).

Observe it on the **helper Deployment** logs — the cron's `curl -sf` discards the
response body, so the suppressed JSON only shows where the helper logs it:

```bash
kubectl -n ai-alert-helper-system logs deploy/ai-alert-helper | grep -E "surge (sent|suppressed)"
```

**Grounded narrative.** `build_for_surge` now ships `top_referrers` (GoatCounter
toprefs, hour-window), `top_paths` and `top_user_agents` (Caddy, probe-excluded;
VictoriaLogs returns the UA as a bracketed `["…"]` string, stripped by
`_bare_ua`). `prompts/investigate-surge.txt` classifies only from those: Hacker
News *only* if a `news.ycombinator.com` referrer is present, scraper if the UAs
are bots with ~0 visitors, "Cause: undetermined" otherwise. No more phantom HN.

## The Telegram analyst (0.2.0)

`/digest`-era ai-alert-helper was one-way. 0.2.0 adds a `getUpdates` long-poll
poller + a tool-calling loop (`analyst.py`, `tools.py`, `commands.py`,
`poller.py`). Operational traps:

- **One `getUpdates` consumer per bot token** (Telegram 409s a second poller).
  The Deployment is `replicas: 1` + `strategy: Recreate` for this; never give
  it a RollingUpdate or a second replica.
- **Chat gate:** non-allowlisted chats are dropped + logged WARNING. A "deaf
  bot" for a foreign account is the gate working.
- **`POST /ask?dry_run=true` `{"question": …}`** runs the full tool loop
  without Telegram — the canonical smoke test (returns `answer` + `tool_trace`).
- **Slash commands bypass the LLM entirely** — they keep working when gpu-1
  is saturated (the 2026-06-04 starvation scenario).
- **The playbook is the ConfigMap:** `apps/ai-alert-helper/skill/SKILL.md`,
  hash-suffixed via kustomize `configMapGenerator` → edits roll the pod. The
  agent-runtime block between the HTML markers is what the pod loads; the
  rest is for humans. Same file doubles as the `hop-trace-analysis` Claude
  Code skill (registry pointer in `agents/skills/`).
- **Context window is server-side:** LiteLLM drops per-request `num_ctx` for
  `ollama_chat` (litellm#12930) — `OLLAMA_CONTEXT_LENGTH=16384` on the ollama
  Deployment is the only effective control; `ANALYST_NUM_CTX` is the client
  trim budget and must stay equal. Measured 2026-06-05: mistral-small-24b at
  16384 = 18 GB total, 16%/84% CPU/GPU (vs 16 GB, 11%/89% at 4096) — fits.
- **CrowdSec reality check:** 30d of retention contains zero local decision
  lines; only community-blocklist syncs. `crowdsec_activity` parses the sync
  format and passes anything else through raw — if `other_lines` is non-empty,
  read it verbatim; that phrasing has never been seen before.
- **Follow-up (next image bump):** analyst INFO logs (the per-question audit
  trail) aren't emitted — the app never configures the logging level, so
  Python's WARNING default swallows them. Configure logging in `api.py`.

## Health Bridge — blindness ≠ death (2026-06-08 power-outage incident)

> Health Bridge (Grafana-alerting → Derio Ops board + frank-ops bug issues) is
> a separate service from the ai-alert-helper digest above; this section lives
> here because both are observability plumbing. Building/operating posts:
> `building/23-health-bridge`, `operating/16-health-bridge`.

**Symptom.** After a whole-cluster power outage, the Derio Ops board stayed red
and `[Bug] DatasourceError is dead — …` issues (`frank-ops#44–48`, every
summary `[no value]`) stayed open long after the alerts stopped firing. Giving
it time did NOT help — the bridge had nothing left to receive.

**Root cause (two defects).**
1. *Blindness treated as death.* When the datasource was unreachable, Grafana
   fired its built-in `DatasourceError` alert, which inherits the `github_issue`
   label of every rule whose query errored (~10 layers). The bridge mapped a
   critical-severity `DatasourceError` → `dead`, set those trackers
   dead/degraded, and created a bug per layer. None described a real fault.
2. *No resolve ever arrives.* Grafana came back as a **fresh pod**
   (`restarts=0`, started *after* the firing). A new Grafana process has no
   in-flight `DatasourceError` instance to clear, so the matching `resolved`
   webhook is never sent. Compounded by the pre-v0.4.0 close path keying on
   *alertname*: even the real per-rule resolves that did arrive
   (e.g. `Layer 18 …`) could not match a `[Bug] DatasourceError is dead` title.

**Fix (health-bridge v0.4.0).**
- `isBlindAlert()` — firing `DatasourceError`/`NoData` caps at `degraded`, no
  bug created.
- `FindOpenBugsByFeature()` — the heal path closes open bugs by the
  `**Feature Issue:** <org>/<repo>#<n>` body ref alone, alertname-agnostic.
  `FindOpenBugs` (title-prefix + ref) stays for the create-dedup path.

**Recovery for an already-stranded board / bugs** (e.g. a future fresh-pod
outage, or pre-v0.4.0 residue). First confirm the affected services are
actually healthy (don't mask a real outage), then replay the missing resolve —
the bridge's own idempotent path flips tiles to `healthy` and closes the
matching bugs with heal comments:

```bash
cd <frank-repo> && source .env            # KUBECONFIG is relative — cd first
SECRET=$(kubectl get secret -n monitoring health-bridge-secrets \
  -o jsonpath='{.data.WEBHOOK_SECRET}' | openssl base64 -d -A)
ISSUES="18 1 12 13 15 24 3 5 6 8"          # stuck frank-ops# trackers (from logs/board)
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ); alerts=""
for n in $ISSUES; do
  alerts="${alerts}{\"status\":\"resolved\",\"labels\":{\"alertname\":\"DatasourceError\",\"github_issue\":\"frank-ops#${n}\",\"severity\":\"critical\"},\"annotations\":{\"summary\":\"Outage recovery\"},\"startsAt\":\"${NOW}\",\"endsAt\":\"${NOW}\"},"
done
payload="{\"status\":\"resolved\",\"alerts\":[${alerts%,}]}"
kubectl port-forward -n monitoring svc/health-bridge 18080:8080 >/tmp/hb-pf.log 2>&1 &
PF=$!; trap 'kill $PF 2>/dev/null' EXIT; sleep 3
curl -sS -X POST http://127.0.0.1:18080/webhook \
  -H "Authorization: Bearer ${SECRET}" -H "Content-Type: application/json" -d "${payload}"
```

`alertname: DatasourceError` makes the create-era bugs match by title; the
v0.4.0 feature-ref close handles any other titles. Idempotent. Verify:
`kubectl logs -n monitoring -l app=health-bridge --tail=40 | grep -E 'Closed bug|→ healthy'`.
