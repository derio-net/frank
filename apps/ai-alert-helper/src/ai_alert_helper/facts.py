"""Fact-sheet builders.

Each function returns a structured dict that the AI adapter consumes.
The shape is the swap contract: when the adapter swaps from LiteLLM to
Sympozium, only ai_adapter.py changes — the fact sheet shape stays put.
"""
from __future__ import annotations
import json
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

VICTORIALOGS_URL = os.environ.get(
    "VICTORIALOGS_URL",
    "http://victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local:9428",
)
# Default to the in-cluster Service: the public counter.cluster.derio.net
# ingress is behind Authentik forward-auth, which 302-redirects API token
# requests to the SSO login. Deployments override this via env anyway.
GOATCOUNTER_URL = os.environ.get(
    "GOATCOUNTER_URL", "http://goatcounter.goatcounter-system.svc.cluster.local:8080"
)
GOATCOUNTER_TOKEN = os.environ.get("OBS_GOATCOUNTER_API_TOKEN", "")

# Self-controlled User-Agent that Frank's blackbox uptime probes carry. The edge
# definition excludes Frank's *own probe identity* (not the vendor default UA).
# MUST match the User-Agent set in
# apps/blackbox-exporter/manifests/configmap.yaml.
PROBE_UA_TOKEN = "Frank-Blackbox-Probe"


def edge_filter(host: str | None = None, *, exclude_probes: bool = True) -> str:
    """Canonical Hop-edge Caddy access-log filter — single source of truth so the
    surge alert, the surge narrative, and the digest agree on what "blog traffic"
    is. Backtick-quote the dotted/hyphenated field names (verified live against
    VictoriaLogs; phrase-matches the array-valued User-Agent field)."""
    f = 'kubernetes.host:hop-1 AND _msg:"handled request"'
    if host:
        f += f' AND `request.host`:"{host}"'
    if exclude_probes:
        f += f' AND -`request.headers.User-Agent`:"{PROBE_UA_TOKEN}"'
    return f


def _logsql_count(query: str) -> int:
    """Issue a `... | stats count() as c` query and return the integer count."""
    try:
        resp = httpx.get(
            f"{VICTORIALOGS_URL}/select/logsql/stats_query",
            params={"query": query},
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json().get("data", {}).get("result", [])
        if not result:
            return 0
        return int(result[0]["value"][1])
    except Exception:  # noqa: BLE001 — fact builders must not crash callers
        return 0


def _logsql_group(query: str, label: str, top: int | None = None) -> list[dict]:
    """Run a `... | stats by (<label>) count() as c` query.

    Returns `[{label: <value>, "count": <int>}, ...]`, sorted desc.
    Empty list on any error — fact builders must not crash callers.
    """
    try:
        resp = httpx.get(
            f"{VICTORIALOGS_URL}/select/logsql/stats_query",
            params={"query": query},
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json().get("data", {}).get("result", [])
    except Exception:  # noqa: BLE001
        return []
    rows = [
        {label: r["metric"].get(label, ""), "count": int(r["value"][1])}
        for r in result
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:top] if top else rows


def _goatcounter_raw(path: str, params: dict) -> dict | None:
    """GET a GoatCounter /api/v0 endpoint with Bearer auth.

    Returns the parsed dict on success, or `None` when GoatCounter is
    unreachable / errors — so callers that must distinguish "down" from
    "genuinely zero" (the surge cross-check) can. Callers that only need a
    dict use `_goatcounter`, which coerces `None` to `{}`.
    """
    if not GOATCOUNTER_TOKEN:
        return None
    try:
        resp = httpx.get(
            f"{GOATCOUNTER_URL}{path}",
            headers={"Authorization": f"Bearer {GOATCOUNTER_TOKEN}"},
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        return None


def _goatcounter(path: str, params: dict) -> dict:
    """GET a GoatCounter /api/v0 endpoint with Bearer auth. {} on error/empty.

    Back-compat wrapper for the digest builders, which `.get()` the result.
    """
    return _goatcounter_raw(path, params) or {}


def surge_visitor_pageviews(window_start: datetime, window_end: datetime) -> int | None:
    """Human pageviews (GoatCounter, JS-beacon) in the surge window.

    `None` when GoatCounter is unreachable (so /surge-check can fail open).
    GoatCounter start/end are date-time, "rounded to the hour" (per /api.json).
    """
    data = _goatcounter_raw(
        "/api/v0/stats/total",
        {
            "start": window_start.replace(minute=0, second=0, microsecond=0).isoformat(),
            "end": window_end.replace(minute=0, second=0, microsecond=0).isoformat(),
        },
    )
    return None if data is None else int(data.get("total", 0))


def _digest_blog_facts(since: datetime, until: datetime) -> dict:
    """Blog reader metrics from GoatCounter for the calendar day [since, until)."""
    # GoatCounter's API treats the range as [start, end) — end is EXCLUSIVE.
    # start==end (e.g. both "2026-05-24") yields an empty range and 0 views;
    # to capture the full calendar day [since, until) we pass end = until's
    # date (the next day at midnight).
    window = {"start": since.date().isoformat(), "end": until.date().isoformat()}
    total = _goatcounter("/api/v0/stats/total", window)
    hits = _goatcounter("/api/v0/stats/hits", {**window, "limit": 10})
    # Top referrers live at /stats/toprefs (one of the {page} stats), NOT
    # /stats/refs — that path is per-page referrers (/stats/hits/{path_id})
    # and 400s when hit directly. The response wraps rows in "stats".
    refs = _goatcounter("/api/v0/stats/toprefs", {**window, "limit": 10})
    return {
        "blog_pageviews": int(total.get("total", 0)),
        "blog_top_pages": [
            {"path": h.get("path", ""), "count": int(h.get("count", 0))}
            for h in hits.get("hits", [])
        ],
        "blog_top_referrers": [
            # GoatCounter reports direct/no-referrer traffic with an empty
            # name; label it "direct" so the digest doesn't render a blank.
            {"name": r.get("name") or "direct", "count": int(r.get("count", 0))}
            for r in refs.get("stats", [])
        ],
    }


def _digest_security_facts(since: datetime, security_until: datetime) -> dict:
    """Falco (all priorities) + CrowdSec over the security window [since, security_until)."""
    sw = f"_time:[{since.isoformat()},{security_until.isoformat()}]"
    by_priority = _logsql_group(
        f"{sw} source:syscall | stats by (priority) count() as c", "priority"
    )
    top_rules = _logsql_group(
        f"{sw} source:syscall | stats by (rule) count() as c", "rule", top=5
    )
    # Critical-priority rules broken out separately: falco_by_priority and
    # falco_top_rules don't link priority↔rule, so the LLM can't reliably name
    # WHICH rule was the benign Critical. This gives it the rule names directly.
    critical_rules = _logsql_group(
        f"{sw} source:syscall AND priority:Critical | stats by (rule) count() as c",
        "rule",
        top=5,
    )
    return {
        "falco_by_priority": [
            {"priority": r["priority"], "count": r["count"]} for r in by_priority
        ],
        "falco_top_rules": [
            {"rule": r["rule"], "count": r["count"]} for r in top_rules
        ],
        "falco_critical_rules": [
            {"rule": r["rule"], "count": r["count"]} for r in critical_rules
        ],
        "crowdsec_decisions": _logsql_count(
            f"{sw} kubernetes.namespace_name:crowdsec-system "
            f"AND log:Adding AND log:decisions | stats count() as c"
        ),
        # Phase 1 trace-analyst enrichment — names attackers instead of counting them.
        "scan_pattern_counts": scan_pattern_counts(since, security_until),
        "top_attacker_ips": top_attacker_ips(since, security_until, top=5),
        "crowdsec_activity": crowdsec_activity(since, security_until),
    }


def build_for_digest(since: datetime, until: datetime, security_until: datetime) -> dict:
    """Daily digest fact sheet.

    Traffic/pageviews cover the calendar day [since, until). Security
    (Falco/CrowdSec) covers [since, security_until) so an overnight
    Critical event surfaces same-day rather than ~24h late.
    """
    tw = f"_time:[{since.isoformat()},{until.isoformat()}]"
    # All Hop-edge Caddy requests — canonical filter, probe-excluded, grouped.
    edge = f'{tw} {edge_filter()}'
    by_vhost = _logsql_group(f"{edge} | stats by (request.host) count() as c", "request.host", top=10)
    by_status = _logsql_group(f"{edge} | stats by (status) count() as c", "status")
    status_class: dict[str, int] = {}
    for row in by_status:
        cls = (str(row["status"])[:1] or "?") + "xx"
        status_class[cls] = status_class.get(cls, 0) + row["count"]
    sheet = {
        "traffic_window": {"since": since.isoformat(), "until": until.isoformat()},
        "security_window": {"since": since.isoformat(), "until": security_until.isoformat()},
        "edge_requests_total": _logsql_count(f"{edge} | stats count() as c"),
        "edge_requests_by_vhost": [{"host": r["request.host"], "count": r["count"]} for r in by_vhost],
        "edge_requests_by_status_class": status_class,
    }
    sheet.update(_digest_blog_facts(since, until))      # GoatCounter
    sheet.update(_digest_security_facts(since, security_until))  # Falco/CrowdSec
    return sheet


def _bare_ua(v: str) -> str:
    """Strip VictoriaLogs' bracketed-array wrapper on the UA group value: `["<ua>"]` -> `<ua>`."""
    v = v.strip()
    if v.startswith('["') and v.endswith('"]'):
        return v[2:-2]
    return v


def build_for_surge(window_start: datetime, window_end: datetime) -> dict:
    """Surge fact sheet — counts + top referrers/paths/user-agents for the window.

    These are the facts the investigate prompt classifies from: HN only if a
    Hacker News referrer is present, scraper if the UAs are bots, etc. Without
    them the model has nothing to cite and speculates.
    """
    window = f"_time:[{window_start.isoformat()},{window_end.isoformat()}]"
    ef = edge_filter(host="blog.derio.net")
    # GoatCounter toprefs takes hour-rounded date-time start/end (same as /total).
    gcw = {
        "start": window_start.replace(minute=0, second=0, microsecond=0).isoformat(),
        "end": window_end.replace(minute=0, second=0, microsecond=0).isoformat(),
    }
    refs = _goatcounter("/api/v0/stats/toprefs", {**gcw, "limit": 5})
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "total_requests": _logsql_count(f'{window} {ef} | stats count() as c'),
        "top_paths": [
            {"path": r["request.uri"], "count": r["count"]}
            for r in _logsql_group(f'{window} {ef} | stats by (request.uri) count() as c', "request.uri", top=5)
        ],
        "top_user_agents": [
            {"ua": _bare_ua(r["request.headers.User-Agent"]), "count": r["count"]}
            for r in _logsql_group(f'{window} {ef} | stats by (request.headers.User-Agent) count() as c', "request.headers.User-Agent", top=5)
        ],
        "top_referrers": [
            {"name": r.get("name") or "direct", "count": int(r.get("count", 0))}
            for r in refs.get("stats", [])
        ],
    }


# Classic scan-probe paths. Grouped, not exhaustive — the analyst's escape
# hatch covers the long tail. Keep in sync with the playbook in
# apps/ai-alert-helper/skill/SKILL.md.
SCAN_PROBE_PATHS = [
    "/wp-login.php", "/xmlrpc.php", "/.env", "/.git/config", "/wp-admin",
    "/phpmyadmin", "/admin", "/.aws/credentials", "/config.json", "/backup",
]


def _window(since: datetime, until: datetime) -> str:
    return f"_time:[{since.isoformat()},{until.isoformat()}]"


def _error_edge(since: datetime, until: datetime) -> str:
    """Edge filter scoped to client errors — the attacker/scan aggregations all
    share this so they can't drift apart."""
    return f'{_window(since, until)} {edge_filter()} AND status:~"4.."'


def scan_pattern_counts(since: datetime, until: datetime) -> list[dict]:
    """Hit counts for the classic probe paths, probe-excluded, desc-sorted."""
    uri_filter = " OR ".join(f'`request.uri`:"{p}"' for p in SCAN_PROBE_PATHS)
    q = f"{_window(since, until)} {edge_filter()} AND ({uri_filter}) | stats by (request.uri) count() as c"
    rows = _logsql_group(q, "request.uri")
    return [{"path": r["request.uri"], "count": r["count"]} for r in rows]


def top_attacker_ips(since: datetime, until: datetime, top: int = 10) -> list[dict]:
    """IPs behind the 4xx noise. Field `request.client_ip` verified live
    2026-06-04 (Caddy emits both client_ip and remote_ip; client_ip respects
    trusted_proxies)."""
    q = f"{_error_edge(since, until)} | stats by (request.client_ip) count() as c"
    rows = _logsql_group(q, "request.client_ip", top=top)
    return [{"ip": r["request.client_ip"], "count": r["count"]} for r in rows]


def top_scanned_paths(since: datetime, until: datetime, top: int = 10) -> list[dict]:
    """Most-probed paths across all 4xx traffic (not just the classics)."""
    q = f"{_error_edge(since, until)} | stats by (request.uri) count() as c"
    rows = _logsql_group(q, "request.uri", top=top)
    return [{"path": r["request.uri"], "count": r["count"]} for r in rows]


# Observed lapi sync line (the ONLY decision-ish phrasing in 30d of retention,
# verified 2026-06-04): msg="crowdsecurity/community-blocklist : added 900
# entries, deleted 0 entries (alert:1)"
_BLOCKLIST_RE = re.compile(
    r'time="(?P<time>[^"]+)".*community-blocklist : added (?P<added>\d+) entries, '
    r"deleted (?P<deleted>\d+) entries"
)


def crowdsec_activity(since: datetime, until: datetime, limit: int = 200) -> dict:
    """CrowdSec activity from the VictoriaLogs trail (Hop's LAPI is unreachable
    from Frank). Blocklist syncs are parsed (observed format); any OTHER
    alert/decision-ish line is passed through raw — local scenario triggers have
    never been observed in retention, so an unrecognized line is the story, and
    a parser guessed against an unobserved format would hide it."""
    q = (
        f"{_window(since, until)} kubernetes.namespace_name:crowdsec-system "
        f'AND (log:alert OR log:decision OR log:ban) | limit {limit}'
    )
    try:
        resp = httpx.get(
            f"{VICTORIALOGS_URL}/select/logsql/query",
            params={"query": q},
            timeout=15,
        )
        resp.raise_for_status()
        lines = [json.loads(l) for l in resp.text.splitlines() if l.strip()]
    except Exception:  # noqa: BLE001 — fail-soft like every fact builder
        return {"blocklist_syncs": [], "other_lines": []}
    syncs, other = [], []
    for entry in lines:
        log = entry.get("log", "")
        m = _BLOCKLIST_RE.search(log)
        if m:
            syncs.append(
                {"time": m.group("time"), "added": int(m.group("added")),
                 "deleted": int(m.group("deleted"))}
            )
        else:
            other.append(log[:300])
    return {"blocklist_syncs": syncs, "other_lines": other[:20]}


def build_for_alert(alert: dict) -> dict:
    """Dispatch to alert-type-specialised fact sheet based on alertname."""
    name = alert.get("alertname", "")
    sheet: dict = {"alertname": name}
    if "CrowdSec" in name:
        sheet["decisions_in_window"] = _logsql_count(
            '_time:5m kubernetes.namespace_name:crowdsec-system AND log:Adding AND log:decisions | stats count() as c'
        )
    elif "Falco" in name:
        sheet["events_in_window"] = _logsql_count(
            '_time:5m source:syscall AND priority:Critical | stats count() as c'
        )
    return sheet
