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
