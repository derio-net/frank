"""Fact-sheet builders.

Each function returns a structured dict that the AI adapter consumes.
The shape is the swap contract: when the adapter swaps from LiteLLM to
Sympozium, only ai_adapter.py changes — the fact sheet shape stays put.
"""
from __future__ import annotations
import os
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


def _goatcounter(path: str, params: dict) -> dict:
    """GET a GoatCounter /api/v0 endpoint with Bearer auth. {} on error."""
    if not GOATCOUNTER_TOKEN:
        return {}
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
        return {}


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
            {"name": r.get("name", ""), "count": int(r.get("count", 0))}
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
    }


def build_for_digest(since: datetime, until: datetime, security_until: datetime) -> dict:
    """Daily digest fact sheet.

    Traffic/pageviews cover the calendar day [since, until). Security
    (Falco/CrowdSec) covers [since, security_until) so an overnight
    Critical event surfaces same-day rather than ~24h late.
    """
    tw = f"_time:[{since.isoformat()},{until.isoformat()}]"
    # All Hop-edge Caddy requests — scoped to the Hop node, grouped, no host substring filter.
    edge = f'{tw} kubernetes.host:hop-1 AND _msg:"handled request"'
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


def build_for_surge(window_start: datetime, window_end: datetime) -> dict:
    """Surge fact sheet — top_referrers/top_pages/etc. for the surge window."""
    window = f"_time:[{window_start.isoformat()},{window_end.isoformat()}]"
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "total_requests": _logsql_count(
            f'{window} kubernetes.namespace_name:caddy-system AND _msg:"handled request" | stats count() as c'
        ),
        # The richer top-N breakdowns (top_referrers, top_pages, geo) would be
        # built here in production; first ship lands with the essential
        # ratio + count fact sheet so surge.py can call investigate().
    }


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
