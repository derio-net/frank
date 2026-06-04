"""Tests for tools.py — the curated tool registry: schemas, windows, caps,
dispatch, and the guarded LogsQL escape hatch."""
from __future__ import annotations
from datetime import timedelta

import httpx
import pytest
import respx

from ai_alert_helper import facts, tools


# --- registry shape ---

def test_registry_exposes_exactly_the_curated_tools():
    assert set(tools.TOOLS) == {
        "edge_traffic", "attacker_profile", "falco_events",
        "crowdsec_decisions", "scan_patterns", "logsql_query",
    }
    for name, t in tools.TOOLS.items():
        # logsql_query is invoked as /logsql (alias); all others as /<name>
        prefix = "/logsql" if name == "logsql_query" else f"/{name}"
        assert t["usage"].startswith(prefix), name
        assert t["description"], name


def test_openai_schemas_are_wellformed():
    schemas = tools.openai_schemas()
    assert len(schemas) == len(tools.TOOLS)
    for s in schemas:
        assert s["type"] == "function"
        fn = s["function"]
        assert fn["name"] in tools.TOOLS
        assert fn["description"]
        params = fn["parameters"]
        assert params["type"] == "object"
        for req in params.get("required", []):
            assert req in params["properties"]


# --- window parsing ---

def test_parse_window_accepts_m_h_d():
    assert tools.parse_window("30m") == timedelta(minutes=30)
    assert tools.parse_window("6h") == timedelta(hours=6)
    assert tools.parse_window("2d") == timedelta(days=2)


def test_parse_window_rejects_nonsense():
    for bad in ("6 fortnights", "", "h6", "0h", "999d", "-1h"):
        with pytest.raises(tools.ToolError):
            tools.parse_window(bad)


# --- caps live in dispatch, outside the tools ---

@respx.mock
def test_dispatch_caps_rows():
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": [
            {"metric": {"request.host": f"h{i}.example"}, "value": [0, str(1000 - i)]}
            for i in range(120)
        ]}}))
    out = tools.dispatch("edge_traffic", {"window": "1h", "group_by": "host"})
    assert len(out["rows"]) <= tools.MAX_ROWS
    assert out.get("truncated") is True


@respx.mock
def test_dispatch_caps_bytes():
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": [
            {"metric": {"request.uri": "/" + "x" * 300 + str(i)}, "value": [0, "9"]}
            for i in range(40)
        ]}}))
    out = tools.dispatch("edge_traffic", {"window": "1h", "group_by": "path"})
    import json as _json
    assert len(_json.dumps(out)) <= tools.MAX_BYTES + 200  # marker overhead allowance
    assert out.get("truncated") is True


def test_dispatch_unknown_tool_is_tool_error_with_usage_hint():
    with pytest.raises(tools.ToolError) as e:
        tools.dispatch("rm_rf", {})
    assert "unknown tool" in str(e.value).lower()


def test_dispatch_missing_required_arg_names_it():
    with pytest.raises(tools.ToolError) as e:
        tools.dispatch("attacker_profile", {"window": "24h"})   # ip missing
    assert "ip" in str(e.value)
    assert tools.TOOLS["attacker_profile"]["usage"] in str(e.value)


def test_dispatch_rejects_bad_group_by():
    with pytest.raises(tools.ToolError) as e:
        tools.dispatch("edge_traffic", {"window": "1h", "group_by": "password"})
    assert "group_by" in str(e.value)


# --- escape hatch guards ---

def test_logsql_requires_time_filter():
    with pytest.raises(tools.ToolError) as e:
        tools.dispatch("logsql_query", {"query": 'request.host:"blog.derio.net" | stats count()'})
    assert "_time" in str(e.value)


@respx.mock
def test_logsql_stats_query_routes_to_stats_endpoint():
    route = respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": [
            {"metric": {"status": "404"}, "value": [0, "37"]}]}}))
    out = tools.dispatch("logsql_query", {
        "query": 'request.host:"blog.derio.net" _time:1h | stats by (status) count() as c'})
    assert route.called
    assert out["rows"][0]["status"] == "404"


@respx.mock
def test_logsql_row_query_routes_to_query_endpoint_with_clamped_limit():
    route = respx.get(facts.VICTORIALOGS_URL + "/select/logsql/query").mock(
        return_value=httpx.Response(200, text='{"_msg": "handled request", "status": "200"}'))
    tools.dispatch("logsql_query", {"query": "_time:5m kubernetes.host:hop-1", "limit": 99999})
    q = route.calls.last.request.url.params["query"]
    assert "limit" in q
    import re as _re
    m = _re.search(r"limit (\d+)", q)
    assert int(m.group(1)) <= tools.LOGSQL_MAX_LIMIT


@respx.mock
def test_attacker_profile_queries_are_ip_scoped():
    route = respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": []}}))
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/query").mock(
        return_value=httpx.Response(200, text=""))
    tools.dispatch("attacker_profile", {"ip": "203.0.113.7", "window": "24h"})
    assert route.called
    for c in route.calls:
        assert '`request.client_ip`:"203.0.113.7"' in c.request.url.params["query"]
