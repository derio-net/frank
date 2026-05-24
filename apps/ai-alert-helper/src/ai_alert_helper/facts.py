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
GOATCOUNTER_URL = os.environ.get("GOATCOUNTER_URL", "https://counter.cluster.derio.net")
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


def build_for_digest(since: datetime, until: datetime) -> dict:
    """Daily digest fact sheet covering one ~24h window."""
    window = f"_time:[{since.isoformat()},{until.isoformat()}]"
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "total_requests": _logsql_count(
            f'{window} kubernetes.namespace_name:caddy-system AND _msg:"handled request" | stats count() as c'
        ),
        "crowdsec_decisions": _logsql_count(
            f'{window} kubernetes.namespace_name:crowdsec-system AND log:Adding AND log:decisions | stats count() as c'
        ),
        "falco_critical": _logsql_count(
            f'{window} source:syscall AND priority:Critical | stats count() as c'
        ),
        # GoatCounter pageview totals are pulled by api.py /digest using the
        # GoatCounter API token; we keep that lookup out of facts.py to avoid
        # making this module depend on the token at import time.
    }


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
