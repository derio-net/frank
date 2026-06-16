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


def _reactions(rec):
    """Emoji set on each setMessageReaction call, in call order."""
    return [p["reaction"][0]["emoji"] for (u, p) in rec.calls if u.endswith("/setMessageReaction")]


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


# --- Thread B: slash commands (expand_command + COMMANDS registry) -------------

CATALOG = ["/help", "/digest", "/surge", "/edge-traffic", "/security", "/status"]


def test_commands_registry_shape():
    # COMMANDS is the single source of truth for setMyCommands AND routing: a
    # dict keyed by the six /-prefixed commands, each with a menu description.
    assert set(bridge.COMMANDS) == set(CATALOG)
    for spec in bridge.COMMANDS.values():
        assert spec["desc"]  # non-empty menu text


def test_expand_command_help_is_static_and_lists_catalog():
    kind, payload = bridge.expand_command("/help")
    assert kind == "static"
    for cmd in CATALOG:
        assert cmd in payload   # the help body names every command


def test_expand_command_prompt_carries_defaults_suffix():
    kind, payload = bridge.expand_command("/digest")
    assert kind == "prompt"
    assert "frank-facts" in payload
    assert "sensible defaults" in payload   # Defaults-&-proceed, encoded once


def test_expand_command_appends_operator_args():
    kind, payload = bridge.expand_command("/edge-traffic hop-1")
    assert kind == "prompt"
    assert "hop-1" in payload   # operator-typed trailing args reach the agent


def test_expand_command_unknown():
    kind, payload = bridge.expand_command("/foo")
    assert kind == "unknown"
    assert payload == "Unknown command — try /help"


def test_slash_help_no_agent(calls):
    drove = bridge.process_update({"message": {"chat": {"id": 100}, "text": "/help"}})
    assert drove is True
    assert _sent(calls, "/session/send") == []          # static — agent NOT driven
    replies = _sent(calls, "/sendMessage")
    assert len(replies) == 1 and "/digest" in replies[0]["text"]


def test_slash_prompt_drives_agent(calls):
    calls.canned["/session/send"] = {"status": "ok", "payload": {"text": "digest narrative"}}
    bridge.process_update({"message": {"chat": {"id": 100}, "text": "/digest"}})
    sent = _sent(calls, "/session/send")
    assert len(sent) == 1
    assert "frank-facts" in sent[0]["message"] and "sensible defaults" in sent[0]["message"]
    assert _sent(calls, "/sendMessage")[0]["text"] == "digest narrative"


def test_slash_unknown_replies_directly(calls):
    bridge.process_update({"message": {"chat": {"id": 100}, "text": "/nope"}})
    assert _sent(calls, "/session/send") == []          # unknown — agent NOT driven
    assert _sent(calls, "/sendMessage")[0]["text"] == "Unknown command — try /help"


def test_freetext_still_drives_agent(calls):
    # No leading slash → the unchanged free-text Q&A path forwards verbatim.
    calls.canned["/session/send"] = {"status": "ok", "payload": {"text": "free answer"}}
    bridge.process_update({"message": {"chat": {"id": 100}, "text": "why is X firing?"}})
    sent = _sent(calls, "/session/send")
    assert len(sent) == 1 and sent[0]["message"] == "why is X firing?"


# --- Thread C: ack/answer reactions -------------------------------------------

def test_tg_react_posts_reaction(calls):
    bridge.tg_react("100", 7, "⚡")
    sent = _sent(calls, "/setMessageReaction")
    assert len(sent) == 1
    assert sent[0]["chat_id"] == "100" and sent[0]["message_id"] == 7
    assert sent[0]["reaction"] == [{"type": "emoji", "emoji": "⚡"}]


def test_tg_react_swallows_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("api down")
    monkeypatch.setattr(bridge, "_http_post_json", boom)
    monkeypatch.setattr(bridge, "BOT_TOKEN", "T")
    bridge.tg_react("100", 7, "⚡")   # best-effort: must NOT raise


def test_reaction_ack_then_thumbsup(calls):
    calls.canned["/session/send"] = {"status": "ok", "payload": {"text": "ok"}}
    bridge.process_update({"message": {"message_id": 42, "chat": {"id": 100}, "text": "hi"}})
    assert _reactions(calls) == ["⚡", "👍"]


def test_reaction_ack_then_thinking(calls):
    calls.canned["/session/send"] = {"status": "timeout", "payload": None}
    bridge.process_update({"message": {"message_id": 42, "chat": {"id": 100}, "text": "hi"}})
    assert _reactions(calls) == ["⚡", "🤔"]   # fallback → thinking-face, not thumbs-up


def test_reaction_on_slash_prompt(calls):
    calls.canned["/session/send"] = {"status": "ok", "payload": {"text": "d"}}
    bridge.process_update({"message": {"message_id": 9, "chat": {"id": 100}, "text": "/digest"}})
    assert _reactions(calls) == ["⚡", "👍"]


def test_reaction_on_static_help(calls):
    # /help never touches the agent but still gets receipt → done reactions.
    bridge.process_update({"message": {"message_id": 3, "chat": {"id": 100}, "text": "/help"}})
    assert _reactions(calls) == ["⚡", "👍"]
