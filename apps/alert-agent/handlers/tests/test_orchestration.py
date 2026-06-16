"""surge-gate gating (edge-trigger + cooldown) + digest delivery + fallback."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

import pytest

from handlers import orchestration as orch

T0 = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


# --- pure gate logic ---

def test_no_escalation_when_tier_none():
    esc, st = orch.should_escalate({"tier": None}, {}, T0)
    assert esc is False and st["last_rank"] == 0


def test_rising_edge_escalates():
    esc, st = orch.should_escalate({"tier": "Notable"}, {"last_rank": 0}, T0)
    assert esc is True and st["last_rank"] == 1


def test_same_tier_within_cooldown_suppressed():
    state = {"last_rank": 1, "last_ts": T0.isoformat()}
    esc, _ = orch.should_escalate({"tier": "Notable"}, state, T0 + timedelta(hours=2), cooldown_hours=6)
    assert esc is False


def test_same_tier_after_cooldown_re_notifies():
    state = {"last_rank": 1, "last_ts": T0.isoformat()}
    esc, _ = orch.should_escalate({"tier": "Notable"}, state, T0 + timedelta(hours=7), cooldown_hours=6)
    assert esc is True


def test_major_after_notable_is_rising_edge_even_within_cooldown():
    state = {"last_rank": 1, "last_ts": T0.isoformat()}
    esc, st = orch.should_escalate({"tier": "Major"}, state, T0 + timedelta(hours=1))
    assert esc is True and st["last_rank"] == 2


# --- run_surge wiring ---

@pytest.fixture
def wired(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(orch, "STATE_PATH", str(tmp_path / "s.json"))
    monkeypatch.setattr(orch, "load_state", lambda path=str(tmp_path / "s.json"): {})
    monkeypatch.setattr(orch, "save_state", lambda state, path=None: None)
    monkeypatch.setattr(orch.facts, "build_for_surge", lambda a, b: {"top_paths": [], "top_referrers": []})
    monkeypatch.setattr(orch.facts, "build_for_digest", lambda a, b, c: {"edge_requests_total": 1200})
    monkeypatch.setattr(orch.bridge, "session_send", lambda *a, **k: sent.append(("session", a, k)) or {"status": "ok", "payload": {"text": "n"}})
    monkeypatch.setattr(orch.bridge, "deliver", lambda resp, fb, **k: sent.append(("deliver", fb)))
    return sent


def test_run_surge_does_not_wake_agent_when_normal(wired, monkeypatch):
    monkeypatch.setattr(orch.surge, "compute", lambda: {"tier": None, "current": 10})
    woke = orch.run_surge(now=T0)
    assert woke is False
    assert not any(s[0] == "session" for s in wired)   # agent NOT driven


def test_run_surge_wakes_agent_and_delivers_on_escalation(wired, monkeypatch):
    monkeypatch.setattr(orch.surge, "compute", lambda: {"tier": "Major", "current": 600, "baseline": 30, "ratio": 20})
    woke = orch.run_surge(now=T0)
    assert woke is True
    assert any(s[0] == "session" for s in wired)        # agent driven once
    assert any(s[0] == "deliver" for s in wired)         # delivered


def test_run_digest_always_wakes_and_delivers_with_fallback(wired):
    orch.run_digest(now=T0)
    assert any(s[0] == "session" for s in wired)
    deliver = [s for s in wired if s[0] == "deliver"][0]
    assert "Daily digest" in deliver[1]                  # deterministic fallback text built
