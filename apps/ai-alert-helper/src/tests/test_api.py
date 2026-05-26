"""Tests for /surge-check's visitor-side decision matrix and notification dedup.

The visitor gate is the parent fix's safeguard; the edge-triggered + cooldown
dedup (rework-1) suppresses repeat Notables for bot/crawler surges. The dedup
state is process-global, so a fixture resets it between tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from ai_alert_helper import api, surge, facts, ai_adapter, telegram

client = TestClient(api.app)


@pytest.fixture(autouse=True)
def _reset_notify_state():
    api._last_notify.update(tier=None, at=None)
    yield
    api._last_notify.update(tier=None, at=None)


def _setup(monkeypatch, tier, visitors):
    """Stub compute()→tier, GoatCounter→visitors, capture every telegram.send.
    Returns (calls, state); mutate state['tier']/['visitors'] between calls."""
    state = {"tier": tier, "visitors": visitors}
    monkeypatch.setattr(surge, "compute", lambda: {
        "tier": state["tier"], "ratio": 12.0, "current": 600, "baseline": 50,
        "window_end": "2026-05-26T17:00:00+00:00",
    })
    monkeypatch.setattr(facts, "surge_visitor_pageviews", lambda a, b: state["visitors"])
    monkeypatch.setattr(facts, "build_for_surge", lambda a, b: {})
    monkeypatch.setattr(ai_adapter, "investigate", lambda labels, sheet: "narrative")
    calls: list = []
    monkeypatch.setattr(telegram, "send",
                        lambda msg, urgent=False: calls.append({"msg": msg, "urgent": urgent}))
    return calls, state


# --- visitor-side decision matrix (parent behavior, now one send per fresh state) ---

def test_major_with_humans_pages_urgent(monkeypatch):
    calls, _ = _setup(monkeypatch, "Major", visitors=50)
    r = client.post("/surge-check").json()
    assert r["triggered"] is True and len(calls) == 1 and calls[0]["urgent"] is True


def test_major_no_humans_downgrades_to_notable(monkeypatch):
    calls, _ = _setup(monkeypatch, "Major", visitors=0)
    r = client.post("/surge-check").json()
    assert r["tier"] == "Notable" and calls[0]["urgent"] is False


def test_major_goatcounter_unreachable_fails_open(monkeypatch):
    calls, _ = _setup(monkeypatch, "Major", visitors=None)
    client.post("/surge-check")
    assert calls[0]["urgent"] is True and "visitor data unavailable" in calls[0]["msg"]


def test_notable_is_not_urgent(monkeypatch):
    calls, _ = _setup(monkeypatch, "Notable", visitors=0)
    client.post("/surge-check")
    assert calls[0]["urgent"] is False


def test_no_tier_does_not_send(monkeypatch):
    calls, _ = _setup(monkeypatch, None, visitors=0)
    r = client.post("/surge-check").json()
    assert r["triggered"] is False and calls == []


# --- edge-triggered + cooldown dedup (rework-1) ---

def test_same_tier_within_cooldown_suppressed(monkeypatch):
    calls, _ = _setup(monkeypatch, "Notable", visitors=0)
    client.post("/surge-check")                       # rising None→Notable → send
    r2 = client.post("/surge-check").json()           # same tier, within cooldown
    assert len(calls) == 1 and r2.get("suppressed") is True


def test_escalation_sends_within_cooldown(monkeypatch):
    calls, state = _setup(monkeypatch, "Notable", visitors=0)
    client.post("/surge-check")                       # Notable → send
    state["tier"], state["visitors"] = "Major", 50    # humans arrive → Major
    client.post("/surge-check")                       # rising Notable→Major → send
    assert len(calls) == 2 and calls[1]["urgent"] is True


def test_same_tier_after_cooldown_sends(monkeypatch):
    calls, _ = _setup(monkeypatch, "Notable", visitors=0)
    client.post("/surge-check")                       # send
    api._last_notify["at"] = datetime.now(timezone.utc) - timedelta(hours=7)  # cooldown elapsed
    client.post("/surge-check")                       # cooled → send again
    assert len(calls) == 2


def test_de_escalation_suppressed(monkeypatch):
    calls, state = _setup(monkeypatch, "Major", visitors=50)
    client.post("/surge-check")                       # Major URGENT → send
    state["tier"], state["visitors"] = "Notable", 0   # drops to Notable
    r2 = client.post("/surge-check").json()           # de-escalation within cooldown
    assert len(calls) == 1 and r2.get("suppressed") is True


def test_dip_to_none_then_same_tier_suppressed(monkeypatch):
    calls, state = _setup(monkeypatch, "Notable", visitors=0)
    client.post("/surge-check")                       # Notable → send
    state["tier"] = None
    client.post("/surge-check")                       # None → no send, state untouched
    state["tier"] = "Notable"
    r3 = client.post("/surge-check").json()           # same tier, still within cooldown
    assert len(calls) == 1 and r3.get("suppressed") is True


def test_completed_hour_stability_sends_once(monkeypatch):
    # Four ticks of one hour see the SAME completed-hour (tier, visitors) → one send.
    calls, _ = _setup(monkeypatch, "Notable", visitors=2)
    for _ in range(4):
        client.post("/surge-check")
    assert len(calls) == 1
