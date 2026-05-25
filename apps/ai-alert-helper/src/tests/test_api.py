"""Tests for /surge-check's visitor-side decision matrix.

The GoatCounter cross-check is the safeguard that was specified but never
implemented (the bug that fired URGENT on Frank's own probe). Each row of the
matrix asserts the `urgent` flag actually passed to telegram.send.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from ai_alert_helper import api, surge, facts, ai_adapter, telegram


def _setup(monkeypatch, tier, visitors):
    """Stub compute() to return `tier`, GoatCounter to return `visitors`, and
    capture what telegram.send was called with."""
    monkeypatch.setattr(surge, "compute", lambda: {
        "tier": tier, "ratio": 12.0, "current": 600, "baseline": 50,
        "window_end": "2026-05-25T17:00:00+00:00",
    })
    monkeypatch.setattr(facts, "surge_visitor_pageviews", lambda a, b: visitors)
    monkeypatch.setattr(facts, "build_for_surge", lambda a, b: {})
    monkeypatch.setattr(ai_adapter, "investigate", lambda labels, sheet: "narrative")
    sent: dict = {}
    monkeypatch.setattr(telegram, "send",
                        lambda msg, urgent=False: sent.update(msg=msg, urgent=urgent))
    return sent


def test_major_with_humans_pages_urgent(monkeypatch):
    sent = _setup(monkeypatch, "Major", visitors=50)   # >= SURGE_VISITOR_FLOOR (10)
    r = TestClient(api.app).post("/surge-check").json()
    assert r["triggered"] is True
    assert sent["urgent"] is True


def test_major_no_humans_downgrades_to_notable(monkeypatch):
    sent = _setup(monkeypatch, "Major", visitors=0)    # < floor → not a human surge
    r = TestClient(api.app).post("/surge-check").json()
    assert r["tier"] == "Notable"
    assert sent["urgent"] is False


def test_major_goatcounter_unreachable_fails_open(monkeypatch):
    sent = _setup(monkeypatch, "Major", visitors=None)  # unreachable
    TestClient(api.app).post("/surge-check")
    assert sent["urgent"] is True
    assert "visitor data unavailable" in sent["msg"]


def test_notable_is_not_urgent(monkeypatch):
    sent = _setup(monkeypatch, "Notable", visitors=0)
    TestClient(api.app).post("/surge-check")
    assert sent["urgent"] is False


def test_no_tier_does_not_send(monkeypatch):
    sent = _setup(monkeypatch, None, visitors=0)
    r = TestClient(api.app).post("/surge-check").json()
    assert r["triggered"] is False
    assert sent == {}   # nothing sent
