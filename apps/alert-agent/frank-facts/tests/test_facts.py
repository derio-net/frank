"""Tests for the stdlib-ported fact builders.

The single HTTP seam is `frank_facts.facts._http_get(url, params, headers) -> str`.
We patch THAT (not the network / not respx) and assert on the dict shapes + that
the right LogsQL/GoatCounter queries are issued. This replaces the old respx mocks.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone

import pytest

from frank_facts import facts


def _stats(count: int) -> str:
    """VictoriaLogs `... | stats count() as c` response (one row)."""
    return json.dumps({"data": {"result": [{"value": [0, str(count)]}]}})


def _stats_by(rows: list[tuple[str, str, int]]) -> str:
    """VictoriaLogs `... | stats by (<label>) count() as c` response."""
    return json.dumps({"data": {"result": [
        {"metric": {label: val}, "value": [0, str(c)]} for (label, val, c) in rows
    ]}})


def test_build_for_alert_crowdsec(monkeypatch):
    monkeypatch.setattr(facts, "_http_get", lambda url, params=None, headers=None, timeout=15: _stats(15))
    sheet = facts.build_for_alert({"alertname": "CrowdSecDecisionBurst"})
    assert sheet["alertname"] == "CrowdSecDecisionBurst"
    assert sheet["decisions_in_window"] == 15


def test_build_for_alert_falco(monkeypatch):
    monkeypatch.setattr(facts, "_http_get", lambda url, params=None, headers=None, timeout=15: _stats(3))
    sheet = facts.build_for_alert({"alertname": "FalcoCriticalEvent"})
    assert sheet["alertname"] == "FalcoCriticalEvent"
    assert sheet["events_in_window"] == 3


def test_build_for_alert_unknown_no_crash():
    sheet = facts.build_for_alert({"alertname": "Unrecognized"})
    assert sheet == {"alertname": "Unrecognized"}


def test_http_error_is_soft(monkeypatch):
    """A failing _http_get must yield 0/[] — fact builders never crash callers."""
    def boom(url, params=None, headers=None, timeout=15):
        raise OSError("victoria down")
    monkeypatch.setattr(facts, "_http_get", boom)
    assert facts._logsql_count("x") == 0
    assert facts._logsql_group("x", "request.host") == []


def test_edge_filter_excludes_probes_and_scopes_host():
    f = facts.edge_filter(host="blog.derio.net")
    assert "kubernetes.host:hop-1" in f
    assert '`request.host`:"blog.derio.net"' in f
    assert facts.PROBE_UA_TOKEN in f  # probe exclusion present
    assert facts.edge_filter().find("request.host") == -1  # no host scope when None


def test_build_for_surge_shape(monkeypatch):
    """Surge sheet carries counts + top paths/UAs/referrers from the seam."""
    monkeypatch.setattr(facts, "GOATCOUNTER_TOKEN", "tok")  # else the GC call short-circuits to {}
    def seam(url, params=None, headers=None, timeout=15):
        q = (params or {}).get("query", "")
        if "/api/v0/stats/toprefs" in url:
            return json.dumps({"stats": [{"name": "news.ycombinator.com", "count": 40}]})
        if "stats by (request.uri)" in q:
            return _stats_by([("request.uri", "/", 50), ("request.uri", "/blog", 20)])
        if "stats by (request.headers.User-Agent)" in q:
            return _stats_by([("request.headers.User-Agent", '["curl/8"]', 30)])
        return _stats(70)  # total_requests
    monkeypatch.setattr(facts, "_http_get", seam)
    w0 = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    w1 = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)
    sheet = facts.build_for_surge(w0, w1)
    assert sheet["total_requests"] == 70
    assert sheet["top_paths"][0] == {"path": "/", "count": 50}
    assert sheet["top_user_agents"][0] == {"ua": "curl/8", "count": 30}  # bracket-array stripped
    assert sheet["top_referrers"][0]["name"] == "news.ycombinator.com"


def test_surge_visitor_pageviews_none_when_unreachable(monkeypatch):
    """GoatCounter unreachable → None (so /surge-check can fail open)."""
    monkeypatch.setattr(facts, "GOATCOUNTER_TOKEN", "tok")
    def boom(url, params=None, headers=None, timeout=15):
        raise OSError("gc down")
    monkeypatch.setattr(facts, "_http_get", boom)
    w0 = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    w1 = datetime(2026, 6, 15, 13, 0, tzinfo=timezone.utc)
    assert facts.surge_visitor_pageviews(w0, w1) is None
