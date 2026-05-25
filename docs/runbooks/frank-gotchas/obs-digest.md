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
