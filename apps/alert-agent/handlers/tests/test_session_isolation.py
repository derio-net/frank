"""Regression: autonomous analytical wakes must NOT share one persistent agent
session (frank#599).

The bug: webhook alert-triage, surge, and digest all drove ONE shared
`alert-agent-ops` session. The agent-session server keeps a long-lived claude
process per session id and only `/clear`s its context after IDLE_RESET_S (12h)
of idleness, so on any active day a prior wake's narrative (the resolved #594
CrowdSec-blind incident) stayed in the context window and bled into a later,
unrelated triage — surfaced as if current. Each analytical stream must ride its
OWN session id so a narrative from one can never bleed into another.

These tests pin the session id each handler drives (captured from the
`session_id` kwarg passed to the mocked `bridge.session_send`).
"""
from __future__ import annotations
import re
from datetime import datetime, timezone

from handlers import webhook
from handlers import orchestration as orch

T0 = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _capture(monkeypatch, module):
    """Patch a handler module's bridge.session_send to record the session_id it
    drives; return the list that receives each captured id."""
    ids: list[str] = []

    def fake_send(message, session_id=None, timeout_s=300):
        ids.append(session_id)
        return {"status": "ok", "payload": {"text": "n"}}

    monkeypatch.setattr(module.bridge, "session_send", fake_send)
    monkeypatch.setattr(module.bridge, "deliver", lambda resp, fb, **k: None)
    return ids


def test_webhook_alert_uses_dedicated_per_alertname_session(monkeypatch):
    ids = _capture(monkeypatch, webhook)
    monkeypatch.setattr(webhook.facts, "build_for_alert", lambda labels: {"alertname": labels.get("alertname")})
    webhook.handle_alert({"alertname": "FalcoCriticalEvent"})
    assert ids == ["alert-agent-webhook-falcocriticalevent"]


def test_webhook_session_is_per_alertname_and_never_the_shared_ops_session(monkeypatch):
    """Different alert types get different sessions (no cross-alert bleed); the same
    alert re-firing reuses its own; and none is the old shared `alert-agent-ops`."""
    ids = _capture(monkeypatch, webhook)
    monkeypatch.setattr(webhook.facts, "build_for_alert", lambda labels: {"alertname": labels.get("alertname")})
    webhook.handle_alert({"alertname": "CrowdSec decision burst"})
    webhook.handle_alert({"alertname": "Falco critical event"})
    webhook.handle_alert({"alertname": "CrowdSec decision burst"})   # re-fire → same id
    assert ids[0] != ids[1]          # different alert types isolated
    assert ids[0] == ids[2]          # same alert re-fire shares
    assert all(i.startswith("alert-agent-webhook-") for i in ids)
    assert "alert-agent-ops" not in ids


def test_webhook_session_id_is_server_safe_and_bounded():
    """The derived id honours the server's ^[A-Za-z0-9_-]{1,128} rule; a missing
    alertname degrades to the bare prefix (never an empty/invalid id)."""
    sid = webhook._session_id_for({"alertname": "CrowdSec decision burst!! (edge)"})
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid)
    assert sid == "alert-agent-webhook-crowdsec-decision-burst-edge"
    assert webhook._session_id_for({}) == "alert-agent-webhook"


def test_surge_uses_dedicated_session(monkeypatch, tmp_path):
    ids = _capture(monkeypatch, orch)
    monkeypatch.setattr(orch, "load_state", lambda path=None: {})
    monkeypatch.setattr(orch, "save_state", lambda state, path=None: None)
    monkeypatch.setattr(orch.surge, "compute", lambda: {"tier": "Major", "current": 600, "baseline": 30, "ratio": 20})
    monkeypatch.setattr(orch.facts, "build_for_surge", lambda a, b: {"top_paths": [], "top_referrers": []})
    orch.run_surge(now=T0)
    assert ids == ["alert-agent-surge"]


def test_digest_uses_dedicated_session(monkeypatch):
    ids = _capture(monkeypatch, orch)
    monkeypatch.setattr(orch.facts, "build_for_digest", lambda a, b, c: {"edge_requests_total": 1})
    orch.run_digest(now=T0)
    assert ids == ["alert-agent-digest"]


def test_the_three_autonomous_streams_are_mutually_isolated(monkeypatch, tmp_path):
    """The core invariant: no two autonomous analytical streams share a session id,
    and none reuses the old shared `alert-agent-ops` — so a narrative from one can
    never bleed into another (the #594 cross-stream bleed)."""
    seen: dict[str, str] = {}

    w = _capture(monkeypatch, webhook)
    monkeypatch.setattr(webhook.facts, "build_for_alert", lambda labels: {"alertname": labels.get("alertname")})
    webhook.handle_alert({"alertname": "X"})
    seen["webhook"] = w[0]

    s = _capture(monkeypatch, orch)
    monkeypatch.setattr(orch, "load_state", lambda path=None: {})
    monkeypatch.setattr(orch, "save_state", lambda state, path=None: None)
    monkeypatch.setattr(orch.surge, "compute", lambda: {"tier": "Major", "current": 600, "baseline": 30, "ratio": 20})
    monkeypatch.setattr(orch.facts, "build_for_surge", lambda a, b: {"top_paths": [], "top_referrers": []})
    orch.run_surge(now=T0)
    seen["surge"] = s[0]

    d = _capture(monkeypatch, orch)
    monkeypatch.setattr(orch.facts, "build_for_digest", lambda a, b, c: {"edge_requests_total": 1})
    orch.run_digest(now=T0)
    seen["digest"] = d[0]

    assert len(set(seen.values())) == 3, f"streams must not share a session: {seen}"
    assert "alert-agent-ops" not in seen.values(), "the shared bleeding session must be gone"
