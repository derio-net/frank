"""Tests for facts builders.

Mock VictoriaLogs + GoatCounter responses; check that the right
dict shape comes out.
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone

import respx
import httpx
from ai_alert_helper import facts


@respx.mock
def test_build_for_alert_dispatches_to_security_for_crowdsec():
    """CrowdSecDecisionBurst alert → security fact sheet."""
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": [{"value": [0, "15"]}]}}),
    )

    sheet = facts.build_for_alert({"alertname": "CrowdSecDecisionBurst"})

    assert sheet["alertname"] == "CrowdSecDecisionBurst"
    assert "decisions_in_window" in sheet
    assert sheet["decisions_in_window"] == 15


@respx.mock
def test_build_for_alert_dispatches_to_falco_for_falco_event():
    """FalcoCriticalEvent alert → falco fact sheet."""
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": [{"value": [0, "3"]}]}}),
    )

    sheet = facts.build_for_alert({"alertname": "FalcoCriticalEvent"})

    assert sheet["alertname"] == "FalcoCriticalEvent"
    assert "events_in_window" in sheet


@respx.mock
def test_build_for_alert_returns_minimal_sheet_for_unknown():
    """Unknown alert name → minimal sheet (no crash)."""
    sheet = facts.build_for_alert({"alertname": "Unrecognized"})
    assert sheet["alertname"] == "Unrecognized"


@respx.mock
def test_build_for_digest_edge_requests_scoped_to_hop_and_grouped():
    """#1: edge requests use kubernetes.host:hop-1, group by request.host + status, no _msg host filter."""
    route = respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": [
            {"metric": {"request.host": "blog.derio.net"}, "value": [0, "120"]},
            {"metric": {"request.host": "heads.hop.derio.net"}, "value": [0, "900"]},
        ]}}),
    )
    since = datetime(2026, 5, 24, tzinfo=timezone.utc)
    until = since + timedelta(days=1)
    sheet = facts.build_for_digest(since, until, until)  # security_until == until for this test
    # vhost breakdown present, sorted desc, capped
    assert sheet["edge_requests_by_vhost"][0]["host"] == "heads.hop.derio.net"
    # at least one query scoped to Hop and grouped by request.host
    assert any("kubernetes.host:hop-1" in q and "by (request.host)" in q
               for q in [c.request.url.params.get("query", "") for c in route.calls])
    # never the broken substring filter
    assert all('_msg:"blog.derio.net"' not in c.request.url.params.get("query", "")
               for c in route.calls)


@respx.mock
def test_build_for_digest_pulls_goatcounter_pageviews_and_top_n():
    """#2: digest queries GoatCounter total/hits/toprefs with Bearer auth + day window.

    Referrers come from /api/v0/stats/toprefs (wrapped in "stats"), NOT the
    non-existent /api/v0/stats/refs — asserting the real endpoint + shape is
    the whole point of the rework.
    """
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": []}}))
    total = respx.get(facts.GOATCOUNTER_URL + "/api/v0/stats/total").mock(
        return_value=httpx.Response(200, json={"total": 42}))
    hits = respx.get(facts.GOATCOUNTER_URL + "/api/v0/stats/hits").mock(
        return_value=httpx.Response(200, json={"hits": [{"path": "/frank/x", "count": 30}]}))
    toprefs = respx.get(facts.GOATCOUNTER_URL + "/api/v0/stats/toprefs").mock(
        return_value=httpx.Response(200, json={"stats": [
            {"name": "news.ycombinator.com", "count": 12},
            {"name": "", "count": 7}]}))
    since = datetime(2026, 5, 24, tzinfo=timezone.utc)
    until = since + timedelta(days=1)
    sheet = facts.build_for_digest(since, until, until)
    assert sheet["blog_pageviews"] == 42
    assert sheet["blog_top_pages"][0]["path"] == "/frank/x"
    assert sheet["blog_top_referrers"][0]["name"] == "news.ycombinator.com"
    # GoatCounter's empty (direct) referrer name is relabelled, not left blank
    assert sheet["blog_top_referrers"][1]["name"] == "direct"
    # the toprefs endpoint (not /stats/refs) was actually called
    assert toprefs.called
    # Bearer auth header present on GoatCounter calls
    assert total.calls.last.request.headers["Authorization"].startswith("Bearer ")
    # day-scoped window: GoatCounter range is [start, end) with end EXCLUSIVE,
    # so the full calendar day needs end = next day, not start == end.
    assert hits.calls.last.request.url.params["start"] == "2026-05-24"
    assert hits.calls.last.request.url.params["end"] == "2026-05-25"


@respx.mock
def test_build_for_digest_falco_all_priorities_and_split_window():
    """#3: falco grouped by priority (not Critical-only); security window runs to security_until."""
    captured = []
    def _cap(request):
        q = dict(request.url.params)["query"]
        captured.append(q)
        # Critical-only rules breakdown (check before the generic by-rule branch)
        if "priority:Critical" in q and "by (rule)" in q:
            return httpx.Response(200, json={"data": {"result": [
                {"metric": {"rule": "Drop and execute new binary in container"}, "value": [0, "2"]}]}})
        # priority breakdown response
        if "by (priority)" in q:
            return httpx.Response(200, json={"data": {"result": [
                {"metric": {"priority": "Warning"}, "value": [0, "2"]},
                {"metric": {"priority": "Notice"}, "value": [0, "1652"]}]}})
        return httpx.Response(200, json={"data": {"result": []}})
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(side_effect=_cap)
    respx.get(re.compile(facts.GOATCOUNTER_URL + "/api/v0/.*")).mock(
        return_value=httpx.Response(200, json={"total": 0, "hits": [], "stats": []}))
    since = datetime(2026, 5, 24, tzinfo=timezone.utc)
    until = since + timedelta(days=1)
    security_until = datetime(2026, 5, 25, 8, 0, tzinfo=timezone.utc)
    sheet = facts.build_for_digest(since, until, security_until)
    prios = {row["priority"]: row["count"] for row in sheet["falco_by_priority"]}
    assert prios == {"Warning": 2, "Notice": 1652}
    # Critical-priority rules broken out so the LLM can name them, not guess
    assert sheet["falco_critical_rules"][0]["rule"] == "Drop and execute new binary in container"
    assert any("priority:Critical" in q and "by (rule)" in q for q in captured)
    # security query window ends at security_until, NOT until
    assert any("2026-05-25T08:00:00" in q and "source:syscall" in q for q in captured)


# --- edge_filter (Phase 2: centralized probe-aware edge definition) ---

def test_edge_filter_excludes_probe_by_default():
    f = facts.edge_filter(host="blog.derio.net")
    assert "kubernetes.host:hop-1" in f
    assert '`request.host`:"blog.derio.net"' in f
    assert '-`request.headers.User-Agent`:"Frank-Blackbox-Probe"' in f


def test_edge_filter_no_host_still_excludes_probe():
    f = facts.edge_filter()
    assert "request.host" not in f          # all vhosts
    assert "Frank-Blackbox-Probe" in f       # still probe-excluded


def test_edge_filter_can_include_probes():
    assert "Frank-Blackbox-Probe" not in facts.edge_filter(exclude_probes=False)


def test_probe_ua_token_is_pinned():
    # Drift guard vs apps/blackbox-exporter/manifests/configmap.yaml
    assert facts.PROBE_UA_TOKEN == "Frank-Blackbox-Probe"


# --- GoatCounter reachability + visitor cross-check ---

@respx.mock
def test_goatcounter_raw_none_on_error():
    respx.get(re.compile(facts.GOATCOUNTER_URL + "/api/v0/.*")).mock(
        side_effect=httpx.ConnectError("down"))
    assert facts._goatcounter_raw("/api/v0/stats/total", {}) is None


@respx.mock
def test_visitor_pageviews_none_when_unreachable():
    respx.get(re.compile(facts.GOATCOUNTER_URL + "/api/v0/stats/total.*")).mock(
        side_effect=httpx.ConnectError("down"))
    s = datetime(2026, 5, 25, 16, tzinfo=timezone.utc); e = s + timedelta(hours=1)
    assert facts.surge_visitor_pageviews(s, e) is None


@respx.mock
def test_visitor_pageviews_counts_and_uses_hour_window():
    route = respx.get(re.compile(facts.GOATCOUNTER_URL + "/api/v0/stats/total.*")).mock(
        return_value=httpx.Response(200, json={"total": 7}))
    s = datetime(2026, 5, 25, 16, 37, tzinfo=timezone.utc); e = s + timedelta(hours=1)
    assert facts.surge_visitor_pageviews(s, e) == 7
    q = dict(httpx.QueryParams(route.calls.last.request.url.query.decode()))
    assert q["start"].startswith("2026-05-25T16:00")   # rounded to the hour
    assert q["end"].startswith("2026-05-25T17:00")


@respx.mock
def test_build_for_digest_survives_unreachable_goatcounter():
    """C1 regression: an unreachable GoatCounter must not crash the daily digest."""
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": []}}))
    respx.get(re.compile(facts.GOATCOUNTER_URL + ".*")).mock(side_effect=httpx.ConnectError("down"))
    since = datetime(2026, 5, 24, tzinfo=timezone.utc); until = since + timedelta(days=1)
    sheet = facts.build_for_digest(since, until, until)   # must NOT raise
    assert sheet["blog_pageviews"] == 0
