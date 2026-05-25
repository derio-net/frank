"""Tests for surge.compute() — hour-of-day baseline + tier classification.

LogsQL has no `quantile_over_time`, so we issue 8 individual stats_query
calls (1 for the current hour + 7 for the same hour-of-day across the past
7 days), then compute the median in Python.
"""
from __future__ import annotations
from datetime import datetime, timezone

import respx
import httpx
import pytest
from ai_alert_helper import surge, facts


def _stats_response(count: int) -> dict:
    """Shape VictoriaLogs returns for `... | stats count() as c`."""
    return {"data": {"result": [{"value": [0, str(count)]}]}}


@respx.mock
def test_compute_returns_none_when_traffic_normal():
    """If current ≈ baseline, tier is None."""
    # Current hour returns 30; baseline samples return 25,30,35,28,32,30,29 → median 30
    counts = [30, 25, 30, 35, 28, 32, 30, 29]
    for c in counts:
        respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
            return_value=httpx.Response(200, json=_stats_response(c)),
        )
    # respx replays in order; but easier: route by sequence — we use side_effect
    route = respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query")
    route.side_effect = [
        httpx.Response(200, json=_stats_response(c)) for c in counts
    ]

    result = surge.compute()

    assert result["tier"] is None
    assert result["current"] == 30
    assert result["baseline"] == 30
    assert result["ratio"] == 1.0


@respx.mock
def test_compute_returns_notable_when_3x_baseline():
    """3x baseline → Notable."""
    counts = [120, 30, 35, 40, 38, 42, 36, 39]  # current=120, median baseline≈38
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        side_effect=[httpx.Response(200, json=_stats_response(c)) for c in counts],
    )

    result = surge.compute()

    assert result["tier"] == "Notable"
    assert result["ratio"] >= 3
    assert result["ratio"] < 10


@respx.mock
def test_compute_returns_major_when_10x_baseline():
    """10x baseline → Major (caller will then validate visitor side)."""
    counts = [500, 30, 35, 40, 38, 42, 36, 39]
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        side_effect=[httpx.Response(200, json=_stats_response(c)) for c in counts],
    )

    result = surge.compute()

    assert result["tier"] == "Major"
    assert result["ratio"] >= 10


@respx.mock
def test_compute_handles_empty_baseline_without_divide_by_zero():
    """Brand-new blog with no historical data shouldn't crash."""
    counts = [50, 0, 0, 0, 0, 0, 0, 0]
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        side_effect=[httpx.Response(200, json=_stats_response(c)) for c in counts],
    )

    result = surge.compute()

    # baseline forces to 1, so ratio = 50
    assert result["baseline"] == 1
    assert result["tier"] == "Major"


@respx.mock
def test_compute_handles_zero_current_traffic():
    """Zero requests in current hour → ratio 0, no surge."""
    counts = [0, 30, 35, 40, 38, 42, 36, 39]
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        side_effect=[httpx.Response(200, json=_stats_response(c)) for c in counts],
    )

    result = surge.compute()

    assert result["current"] == 0
    assert result["ratio"] == 0.0
    assert result["tier"] is None


@respx.mock
def test_hour_count_filters_on_request_host_field_and_excludes_probe():
    route = respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": [{"value": [0, "5"]}]}}))
    surge._hour_count(datetime(2026, 5, 25, 12, tzinfo=timezone.utc))
    q = route.calls.last.request.url.params["query"]
    assert '`request.host`:"blog.derio.net"' in q          # backtick-quoted field
    assert '_msg:"blog.derio.net"' not in q                 # never the broken substring filter
    assert '-`request.headers.User-Agent`:"Frank-Blackbox-Probe"' in q  # probe excluded


@respx.mock
def test_floor_suppresses_tier_below_abs_floor():
    """current below SURGE_ABS_FLOOR (default 50) → no tier even at a huge ratio."""
    counts = [49, 1, 0, 0, 0, 0, 0, 0]    # ratio 49 but below the floor
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        side_effect=[httpx.Response(200, json=_stats_response(c)) for c in counts])
    assert surge.compute()["tier"] is None


@respx.mock
def test_floor_boundary_fires_at_abs_floor():
    """exactly SURGE_ABS_FLOOR requests qualifies (>=)."""
    counts = [50, 1, 0, 0, 0, 0, 0, 0]
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        side_effect=[httpx.Response(200, json=_stats_response(c)) for c in counts])
    assert surge.compute()["tier"] == "Major"


@respx.mock
def test_empty_baseline_no_crash_below_floor():
    """Crash-safety on an empty baseline, decoupled from the floor boundary."""
    counts = [10, 0, 0, 0, 0, 0, 0, 0]
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        side_effect=[httpx.Response(200, json=_stats_response(c)) for c in counts])
    r = surge.compute()
    assert r["baseline"] == 1 and r["tier"] is None
