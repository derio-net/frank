"""telegram-bridge: allowlist, single-consumer routing, deterministic fallback."""
from __future__ import annotations
import json
import re
import threading
import time
from types import SimpleNamespace

import pytest

from tg_bridge import bridge

_TG_ID_RE = re.compile(r"^[a-z0-9_]{1,32}$")


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


def test_render_payload_unwraps_json_envelope_string():
    # The agent is taught to reply in plain text, but if a turn still emits the
    # legacy {"text": ...} envelope AS ITS MESSAGE, the session server hands it
    # back as a STRING payload — which must be unwrapped, not posted raw (else
    # the operator sees literal JSON in Telegram).
    assert bridge.render_payload(
        {"status": "ok", "payload": '{"text": "hello there"}'}) == "hello there"


def test_render_payload_passes_plain_string_through():
    assert bridge.render_payload({"status": "ok", "payload": "just words"}) == "just words"


def test_render_payload_leaves_non_envelope_json_verbatim():
    # A string that happens to start like JSON but isn't a {"text": ...} envelope
    # is returned unchanged — no accidental mangling of a normal answer.
    assert bridge.render_payload({"status": "ok", "payload": "not json {"}) == "not json {"
    # A JSON list, or a JSON object without a "text" key, is not an envelope.
    assert bridge.render_payload({"status": "ok", "payload": '["a", "b"]'}) == '["a", "b"]'


def test_render_payload_dict_branch_unchanged():
    assert bridge.render_payload({"status": "ok", "payload": {"text": "x"}}) == "x"


# --- Thread B: slash commands (expand_command + COMMANDS registry) -------------

CATALOG = ["/help", "/digest", "/surge", "/edge_traffic", "/security", "/status"]


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
    kind, payload = bridge.expand_command("/edge_traffic hop-1")
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


# --- Fix A: Telegram menu command ids (the setMyCommands 400) -------------------

def test_command_ids_are_valid_telegram():
    # Every COMMANDS key (sans leading /) must be a valid Telegram command id —
    # no hyphens. One invalid id makes setMyCommands 400 and rejects the WHOLE menu.
    for cmd in bridge.COMMANDS:
        ident = cmd.lstrip("/")
        assert _TG_ID_RE.match(ident), f"invalid Telegram command id: {cmd!r}"


def test_set_my_commands_sends_only_valid_ids(calls):
    # An invalid id must be SKIPPED (logged), never sent — so a single bad id can
    # never reject the whole batch (fail-soft: the menu just lacks that command).
    bridge.COMMANDS["/bad-id"] = {"desc": "temp invalid", "kind": "static"}
    try:
        bridge.set_my_commands()
    finally:
        del bridge.COMMANDS["/bad-id"]
    sent = _sent(calls, "/setMyCommands")
    assert len(sent) == 1
    ids = [c["command"] for c in sent[0]["commands"]]
    assert ids, "must still register the valid commands"
    assert all(_TG_ID_RE.match(i) for i in ids), f"setMyCommands sent an invalid id: {ids}"
    assert "bad-id" not in ids, "the invalid id must be skipped, not sent"


# --- Fix D: threaded turns off the poll loop (per-session lock) -----------------

def _gated_session_send(calls, monkeypatch, on_send):
    """Wrap the fixture's recording fake so /session/send runs `on_send(payload)`
    (e.g. block on an Event) before returning the canned response. Other calls
    (sendMessage / setMessageReaction) pass through to the recorder unchanged."""
    base = bridge._http_post_json
    def gated(url, payload, timeout=310):
        if url.endswith("/session/send"):
            on_send(payload)
        return base(url, payload, timeout)
    monkeypatch.setattr(bridge, "_http_post_json", gated)


def _texts(rec):
    return [p.get("text") for (u, p) in list(rec.calls) if u.endswith("/sendMessage")]


def test_slow_turn_does_not_block_static(calls, monkeypatch):
    # A slow free-text turn (blocks in session_send) must NOT head-of-line-block a
    # /help dispatched right after — /help is answered inline by the consumer.
    release = threading.Event()
    calls.canned["/session/send"] = {"status": "ok", "payload": {"text": "A answer"}}
    _gated_session_send(calls, monkeypatch, lambda payload: release.wait(5))

    t = bridge.dispatch_update({"message": {"message_id": 1, "chat": {"id": 100}, "text": "slow question"}})
    bridge.dispatch_update({"message": {"message_id": 2, "chat": {"id": 100}, "text": "/help"}})

    # /help's static reply lands while A is still blocked.
    assert any("/digest" in (txt or "") for txt in _texts(calls)), "/help must reply, not wait for the turn"
    assert "A answer" not in _texts(calls), "the blocked turn's reply must not have landed yet"

    release.set()
    t.join(5)
    assert "A answer" in _texts(calls), "the turn's reply lands once unblocked"


def test_same_session_turns_serialize(calls, monkeypatch):
    # Two turns for the SAME session_id serialize under a per-session lock — the
    # second session_send does not start until the first returns.
    order = []
    gate = threading.Event()
    calls.canned["/session/send"] = {"status": "ok", "payload": {"text": "x"}}

    def on_send(payload):
        order.append("start:" + payload["message"])
        if payload["message"] == "first":
            gate.wait(5)
        order.append("end:" + payload["message"])
    _gated_session_send(calls, monkeypatch, on_send)

    t1 = bridge.dispatch_update({"message": {"message_id": 1, "chat": {"id": 100}, "text": "first"}})
    t2 = bridge.dispatch_update({"message": {"message_id": 2, "chat": {"id": 100}, "text": "second"}})
    time.sleep(0.15)
    assert "start:second" not in order, "the second same-session turn must wait for the lock"
    gate.set()
    t1.join(5); t2.join(5)
    assert order == ["start:first", "end:first", "start:second", "end:second"]


def test_reaction_order_preserved_per_message(calls):
    # A threaded turn still reacts ⚡ before 👍/🤔 on its own message.
    calls.canned["/session/send"] = {"status": "ok", "payload": {"text": "ok"}}
    t = bridge.dispatch_update({"message": {"message_id": 42, "chat": {"id": 100}, "text": "hi"}})
    t.join(5)
    assert _reactions(calls) == ["⚡", "👍"]
