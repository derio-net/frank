"""telegram-bridge: allowlist, single-consumer routing, deterministic fallback."""
from __future__ import annotations
import json
from types import SimpleNamespace

import pytest

from tg_bridge import bridge


@pytest.fixture
def calls(monkeypatch):
    """Record every _http_post_json call; return canned responses by URL fragment."""
    rec = SimpleNamespace(calls=[], canned={})

    def fake(url, payload, timeout=310):
        rec.calls.append((url, payload))
        for frag, resp in rec.canned.items():
            if frag in url:
                return resp
        return {}
    monkeypatch.setattr(bridge, "_http_post_json", fake)
    monkeypatch.setattr(bridge, "BOT_TOKEN", "T")
    monkeypatch.setattr(bridge, "DEFAULT_CHAT", "100")
    monkeypatch.setattr(bridge, "ALLOWED_CHATS", {"100"})
    return rec


def _sent(rec, method):
    return [p for (u, p) in rec.calls if u.endswith(method)]


def test_allowlisted_message_drives_agent_and_replies(calls):
    calls.canned["/session/send"] = {"status": "ok", "payload": {"text": "inference is on gpu-1"}}
    drove = bridge.process_update({"message": {"chat": {"id": 100}, "text": "why is X firing?"}})
    assert drove is True
    assert len(_sent(calls, "/session/send")) == 1            # agent driven once
    replies = _sent(calls, "/sendMessage")
    assert len(replies) == 1 and replies[0]["text"] == "inference is on gpu-1"
    assert replies[0]["chat_id"] == "100"


def test_non_allowlisted_chat_dropped(calls):
    drove = bridge.process_update({"message": {"chat": {"id": 999}, "text": "hi"}})
    assert drove is False
    assert _sent(calls, "/session/send") == []   # agent NOT driven
    assert _sent(calls, "/sendMessage") == []     # no reply


def test_outbound_sender_posts_to_configured_chat(calls):
    bridge.tg_send("digest: 1.2k requests, 0 critical")
    sent = _sent(calls, "/sendMessage")
    assert len(sent) == 1 and sent[0]["chat_id"] == "100"
    assert "digest" in sent[0]["text"]
    assert "parse_mode" not in sent[0]   # plain text — dodges the HTML-400 gotcha


def test_deliver_falls_back_on_timeout(calls):
    # agent timed out → no payload → the deterministic fallback text is posted
    resp = {"status": "timeout", "payload": None}
    bridge.deliver(resp, fallback_text="DETERMINISTIC DIGEST RENDER")
    sent = _sent(calls, "/sendMessage")
    assert len(sent) == 1 and sent[0]["text"] == "DETERMINISTIC DIGEST RENDER"


def test_deliver_uses_agent_payload_when_present(calls):
    resp = {"status": "ok", "payload": {"text": "agent narrative"}}
    bridge.deliver(resp, fallback_text="fallback")
    assert _sent(calls, "/sendMessage")[0]["text"] == "agent narrative"
