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
                # a callable canned response is invoked with (url, payload) — lets a
                # test return a 400 on the first sendMessage and success on the retry
                return resp(url, payload) if callable(resp) else resp
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


def test_render_payload_leaves_non_dict_json_verbatim():
    # A non-JSON string, or a JSON *non-dict* (list/number), is not a report —
    # returned unchanged, no accidental mangling of a normal answer.
    assert bridge.render_payload({"status": "ok", "payload": "not json {"}) == "not json {"
    assert bridge.render_payload({"status": "ok", "payload": '["a", "b"]'}) == '["a", "b"]'


def test_render_payload_dict_branch_unchanged():
    assert bridge.render_payload({"status": "ok", "payload": {"text": "x"}}) == "x"


# --- render_payload renders ANY dict as a table (the mechanical anti-JSON-leak) ---
# The agent-session server hands the agent's raw JSON result straight through, and
# the model often writes a domain-shaped object (no `text` field) despite the prompt.
# render_payload must table it, NEVER post raw json.dumps — a mechanism the agent's
# per-turn wrapper cannot override.

def test_render_payload_textless_dict_becomes_report():
    # A text-less dict is now rendered as an HTML <pre> report, never raw JSON.
    out = bridge.render_payload(
        {"status": "ok", "payload": {"gpu_mode": "comfyui", "firing_alerts": "none"}})
    assert "gpu_mode" in out and "comfyui" in out
    assert "firing_alerts" in out and "none" in out
    assert not out.lstrip().startswith("{")        # NOT raw JSON
    assert "<pre>" in out                            # HTML report → sender opts into HTML


def test_render_payload_textless_dict_string_becomes_report():
    out = bridge.render_payload({"status": "ok", "payload": '{"a": 1, "b": "two"}'})
    assert not out.lstrip().startswith("{")
    assert "a" in out and "b" in out and "two" in out
    assert "<pre>" in out


def test_render_payload_nested_dict_rendered_not_raw_json():
    out = bridge.render_payload(
        {"status": "ok", "payload": {"summary": {"overall": "quiet"}, "count": 5}})
    assert "<pre>" in out
    assert "summary" in out.lower() and "count" in out   # summary → humanized header
    assert "overall" in out                          # nested value rendered, not dropped
    assert not out.lstrip().startswith("{")


def test_render_payload_non_string_text_key_is_tabled_not_raw():
    # {"text": <non-string>} is not a valid envelope → tabled, never posted raw.
    out = bridge.render_payload({"status": "ok", "payload": '{"text": 123}'})
    assert not out.lstrip().startswith("{")
    assert "text" in out and "123" in out


# --- render_report: monospace <pre> tables from a domain dict --------------------
# The captured live /edge_traffic payload is the primary fixture: a leading scalar,
# a list-of-dicts with a RAGGED key set (one row carries `country`, others don't),
# and a scalar list of raw log lines (some with HTML-sensitive characters).

def _edge_payload():
    return {
        "window": "last_24h",
        "top_scanned_paths": [
            {"path": f"/scan/{i}.php", "count": 20 - i} for i in range(11)
        ],  # 11 rows → forces the 10-row cap
        "top_attacker_ips": [
            {"ip": "52.152.150.151", "count": 266, "org": "Microsoft Corporation", "banned": False},
            {"ip": "4.204.201.85", "count": 144, "org": "Microsoft Corporation", "banned": False},
            # ragged: this row ALSO carries `country`
            {"ip": "45.148.10.244", "count": 45, "org": "TECHOFF SRV LIMITED", "country": "AD", "banned": False},
            {"ip": "20.220.225.223", "count": 42, "org": "Microsoft Corporation", "banned": True},
        ],
        "crowdsec_bans": [
            'time="2026-07-21T21:00:36Z" level=info msg="4h ban on Ip 20.220.225.223"',
            'ua="Mozilla/5.0 <bot> & spider" note=blocked',  # HTML-sensitive: < > &
        ],
    }


def test_render_report_list_of_dicts_is_aligned_table():
    out = bridge.render_report(_edge_payload())
    # header names present (upper-cased), one line per row, real IP value present
    assert "IP" in out and "COUNT" in out and "ORG" in out and "BANNED" in out
    assert "52.152.150.151" in out
    # NOT escaped one-line JSON
    assert "[{" not in out
    assert '":"' not in out and '","' not in out


def test_render_report_ragged_keys_single_country_column_blank_cell():
    out = bridge.render_report(_edge_payload())
    assert out.count("COUNTRY") == 1              # the ragged key appears exactly once
    assert "AD" in out                             # present for the row that has it
    # a row without `country` must render blank, never the literal None
    assert "None" not in out


def test_render_report_column_order_is_first_seen():
    out = bridge.render_report(_edge_payload())
    hdr = next(ln for ln in out.splitlines() if "IP" in ln and "COUNT" in ln)
    assert hdr.index("IP") < hdr.index("COUNT") < hdr.index("ORG") < hdr.index("BANNED")
    assert hdr.index("BANNED") < hdr.index("COUNTRY")   # country first seen later → last


def test_render_report_row_cap_ten_plus_more_no_midcut():
    out = bridge.render_report(_edge_payload())
    assert "+1 more" in out                         # 11 scanned paths → 10 shown + 1 more
    # the 10 shown paths appear whole (never truncated mid-value)
    for i in range(10):
        assert f"/scan/{i}.php" in out
    assert "/scan/10.php" not in out               # the 11th is folded into "+1 more"


def test_render_report_scalar_list_one_per_line_whole():
    out = bridge.render_report(_edge_payload())
    # each ban log line appears WHOLE (not truncated at 200 chars, not JSON-listed)
    assert '4h ban on Ip 20.220.225.223' in out
    assert '["' not in out                          # not a json.dumps'd list


def test_render_report_html_escapes_all_values():
    out = bridge.render_report(_edge_payload())
    # the HTML-sensitive ban line is escaped
    assert "&lt;bot&gt;" in out and "&amp; spider" in out
    # the ONLY literal angle brackets in the whole output are the <pre> tags
    stripped = out.replace("<pre>", "").replace("</pre>", "")
    assert "<" not in stripped and ">" not in stripped


def test_render_report_pre_tags_balanced():
    out = bridge.render_report(_edge_payload())
    assert out.count("<pre>") == out.count("</pre>") >= 1


# --- Transport: opt-in HTML parse_mode, 4096 split, 400 -> plain fallback --------

def test_tg_send_parse_mode_opt_in(calls):
    bridge.tg_send("x", parse_mode="HTML")
    sent = _sent(calls, "/sendMessage")
    assert sent[-1]["parse_mode"] == "HTML"


def test_tg_send_default_still_plain(calls):
    # the default path is unchanged — no parse_mode key (the HTML-400 dodge)
    bridge.tg_send("x")
    assert "parse_mode" not in _sent(calls, "/sendMessage")[-1]


def test_split_for_telegram_single_block_no_prefix():
    body = bridge._wrap_pre("short")
    parts = bridge._split_for_telegram(body)
    assert len(parts) == 1
    assert not parts[0].startswith("(")            # no (i/n) prefix for a single part


def test_split_for_telegram_multi_part_balanced_and_prefixed():
    # a report far larger than the limit → multiple parts, each ≤ limit, each with
    # balanced <pre> tags and a (i/n) prefix
    big = "\n\n".join(bridge._wrap_pre("row " + "x" * 500) for _ in range(20))
    parts = bridge._split_for_telegram(big, limit=4096)
    assert len(parts) >= 2
    for i, p in enumerate(parts, 1):
        assert len(p) <= 4096
        assert p.count("<pre>") == p.count("</pre>")
        assert p.startswith(f"({i}/{len(parts)})")


def test_split_oversized_single_pre_splits_on_rows():
    # one <pre> whose body alone exceeds the limit is split on whole rows, each
    # fragment re-wrapped — never a cut inside a tag
    rows = "\n".join(f"row-{i} " + "y" * 80 for i in range(200))
    parts = bridge._split_for_telegram(bridge._wrap_pre(rows), limit=2000)
    assert len(parts) >= 2
    for p in parts:
        assert p.count("<pre>") == p.count("</pre>") >= 1
        assert "row-0 " in p or "row-" in p          # rows preserved whole


def test_send_reply_report_posts_html(calls):
    resp = {"status": "ok", "payload": {"a": 1, "b": 2}}
    bridge.send_reply(resp, "100", fallback="fb")
    sent = _sent(calls, "/sendMessage")
    assert sent[-1]["parse_mode"] == "HTML"
    assert "<pre>" in sent[-1]["text"]


def test_send_reply_narrative_posts_plain(calls):
    resp = {"status": "ok", "payload": {"text": "just prose"}}
    bridge.send_reply(resp, "100", fallback="fb")
    sent = _sent(calls, "/sendMessage")
    assert sent[-1]["text"] == "just prose"
    assert "parse_mode" not in sent[-1]
    assert "<pre>" not in sent[-1]["text"]


def test_send_reply_400_falls_back_to_plain(calls):
    # first HTML sendMessage 400s → exactly one retry, no parse_mode, data preserved,
    # no <pre> in the fallback body
    state = {"n": 0}

    def sender(url, payload):
        state["n"] += 1
        return {"ok": False, "error_code": 400} if state["n"] == 1 else {"ok": True}
    calls.canned["/sendMessage"] = sender
    resp = {"status": "ok", "payload": {"marker_key": "marker_val"}}
    bridge.send_reply(resp, "100", fallback="fb")
    sent = _sent(calls, "/sendMessage")
    assert len(sent) == 2                             # one HTML attempt + one plain retry
    assert sent[0]["parse_mode"] == "HTML"
    assert "parse_mode" not in sent[1]
    assert "<pre>" not in sent[1]["text"]
    assert "marker_key" in sent[1]["text"] and "marker_val" in sent[1]["text"]


def test_send_reply_fallback_callable_used_only_on_none(calls):
    used = {"called": False}

    def fb():
        used["called"] = True
        return "LAZY FALLBACK"
    # a completed turn must NOT invoke the callable
    bridge.send_reply({"status": "ok", "payload": {"text": "ok"}}, "100", fallback=fb)
    assert used["called"] is False
    # an empty turn invokes it lazily
    bridge.send_reply({"status": "timeout", "payload": None}, "100", fallback=fb)
    assert used["called"] is True
    assert _sent(calls, "/sendMessage")[-1]["text"] == "LAZY FALLBACK"


# --- DM path: deterministic fallback (never a bare "(no reply)" / silent death) ---

def test_dm_timeout_posts_deterministic_fallback(calls, monkeypatch):
    # A timed-out/empty agent turn must post a DETERMINISTIC snapshot, not the
    # bare "(the agent did not return a reply…)" that reads as a dead bot.
    calls.canned["/session/send"] = {"status": "timeout", "payload": None}
    monkeypatch.setattr(bridge, "_deterministic_snapshot", lambda: "SNAPSHOT surge tier=None")
    bridge.process_update({"message": {"message_id": 5, "chat": {"id": 100}, "text": "/status"}})
    replies = _sent(calls, "/sendMessage")
    assert replies and "SNAPSHOT" in replies[-1]["text"]
    assert "did not return a reply" not in replies[-1]["text"]
    assert _reactions(calls)[-1] == "🤔"     # fallback → thinking-face, not thumbs-up


def test_dm_session_exception_does_not_kill_turn(calls, monkeypatch):
    # If session_send RAISES (HTTP timeout), the turn must survive and still post
    # the deterministic fallback — never die silently leaving the operator with
    # nothing (the original silent-no-reply bug).
    def boom(*a, **k):
        raise RuntimeError("http read timed out")
    monkeypatch.setattr(bridge, "session_send", boom)
    monkeypatch.setattr(bridge, "_deterministic_snapshot", lambda: "SNAPSHOT fallback")
    bridge.process_update({"message": {"message_id": 6, "chat": {"id": 100}, "text": "why is X firing?"}})
    replies = _sent(calls, "/sendMessage")
    assert replies and "SNAPSHOT fallback" in replies[-1]["text"]


def test_dm_success_still_posts_agent_text(calls, monkeypatch):
    # The happy path is unchanged: a real payload is posted, 👍, no fallback.
    calls.canned["/session/send"] = {"status": "ok", "payload": {"text": "real answer"}}
    monkeypatch.setattr(bridge, "_deterministic_snapshot", lambda: "SHOULD NOT APPEAR")
    bridge.process_update({"message": {"message_id": 7, "chat": {"id": 100}, "text": "hi"}})
    replies = _sent(calls, "/sendMessage")
    assert replies[-1]["text"] == "real answer"
    assert _reactions(calls)[-1] == "👍"


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
