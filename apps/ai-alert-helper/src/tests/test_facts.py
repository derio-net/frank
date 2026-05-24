"""Tests for facts builders.

Mock VictoriaLogs + GoatCounter responses; check that the right
dict shape comes out.
"""
from __future__ import annotations
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
