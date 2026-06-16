"""grafana-webhook: alert triage path, malformed→400, /healthz→200."""
from __future__ import annotations
import json

import pytest

from handlers import webhook


@pytest.fixture
def wired(monkeypatch):
    calls = []
    monkeypatch.setattr(webhook.facts, "build_for_alert", lambda labels: {"alertname": labels.get("alertname"), "events_in_window": 3})
    monkeypatch.setattr(webhook.bridge, "session_send", lambda *a, **k: calls.append("session") or {"status": "ok", "payload": {"text": "n"}})
    monkeypatch.setattr(webhook.bridge, "deliver", lambda resp, fb, **k: calls.append(("deliver", fb)))
    return calls


def test_firing_alert_triaged_and_delivered(wired):
    body = json.dumps({"alerts": [{"status": "firing", "labels": {"alertname": "FalcoCriticalEvent"}}]}).encode()
    code, obj = webhook.process_request("POST", "/", body)
    assert code == 200 and obj["triaged"] == 1
    assert "session" in wired and any(c[0] == "deliver" for c in wired if isinstance(c, tuple))


def test_resolved_alert_not_triaged(wired):
    body = json.dumps({"alerts": [{"status": "resolved", "labels": {"alertname": "X"}}]}).encode()
    code, obj = webhook.process_request("POST", "/", body)
    assert code == 200 and obj["triaged"] == 0
    assert "session" not in wired


def test_malformed_body_400(wired):
    code, obj = webhook.process_request("POST", "/", b"not json{")
    assert code == 400 and "session" not in wired   # no delivery on bad input


def test_healthz_200():
    code, obj = webhook.process_request("GET", "/healthz", b"")
    assert code == 200 and obj["status"] == "ok"


def test_fallback_text_has_no_html_specials():
    """The deterministic fallback must be plain (no <>& that 400s Telegram HTML)."""
    txt = webhook._render_alert({"alertname": "L11 Inference"}, {"alertname": "L11 Inference", "events_in_window": 2})
    assert "<" not in txt and ">" not in txt and "&" not in txt
