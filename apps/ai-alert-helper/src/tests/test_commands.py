"""Tests for commands.py — slash-command parsing and Telegram result formatting.
Everything renders from the tools.TOOLS registry: one source, no drift."""
from __future__ import annotations

import json

import httpx
import respx

from ai_alert_helper import commands, facts, tools


# --- parsing ---

def test_non_command_text_returns_none():
    assert commands.parse_command("who scanned the blog today?") is None
    assert commands.parse_command("") is None


def test_help_lists_every_command_with_usage():
    cmd = commands.parse_command("/help")
    assert cmd["kind"] == "help"
    text = commands.render_help()
    for name, t in tools.TOOLS.items():
        assert t["usage"] in text, name
    assert "/reset" in text and "/tools" in text


def test_tools_listing_renders_from_registry():
    cmd = commands.parse_command("/tools")
    assert cmd["kind"] == "tools"
    text = commands.render_tools()
    for name in tools.TOOLS:
        assert name in text


def test_reset_command():
    assert commands.parse_command("/reset")["kind"] == "reset"


def test_tool_command_positional_and_kwargs():
    cmd = commands.parse_command("/edge_traffic 1h group_by=host")
    assert cmd == {"kind": "tool", "name": "edge_traffic",
                   "args": {"window": "1h", "group_by": "host"}, "explain": False}


def test_tool_command_two_positionals():
    cmd = commands.parse_command("/attacker_profile 1.2.3.4 24h")
    assert cmd["name"] == "attacker_profile"
    assert cmd["args"] == {"ip": "1.2.3.4", "window": "24h"}


def test_explain_suffix_pops_flag():
    cmd = commands.parse_command("/scan_patterns 6h explain")
    assert cmd["explain"] is True
    assert cmd["args"] == {"window": "6h"}


def test_logsql_command_takes_raw_tail():
    q = 'request.host:"blog.derio.net" _time:1h | stats by (status) count()'
    cmd = commands.parse_command(f"/logsql {q}")
    assert cmd["name"] == "logsql_query"
    assert cmd["args"]["query"] == q


def test_missing_required_arg_yields_usage_error():
    cmd = commands.parse_command("/attacker_profile")
    assert cmd["kind"] == "error"
    assert tools.TOOLS["attacker_profile"]["usage"] in cmd["text"]


def test_unknown_command_hints_help():
    cmd = commands.parse_command("/frobnicate now")
    assert cmd["kind"] == "error"
    assert "/help" in cmd["text"]


def test_bot_commands_for_setmycommands_come_from_registry():
    cmds = commands.bot_commands()
    names = {c["command"] for c in cmds}
    assert set(tools.TOOLS) <= names
    assert {"help", "tools", "reset"} <= names
    for c in cmds:
        assert c["description"]
        assert len(c["description"]) <= 256   # Telegram BotCommand limit


# --- formatting ---

def test_format_result_is_compact_and_bounded():
    rows = {"rows": [{"path": f"/x{i}", "count": i} for i in range(200)]}
    text = commands.format_result(rows)
    assert len(text) <= commands.MAX_REPLY_CHARS
    assert "/x0" in text


def test_format_result_handles_empty():
    assert "no results" in commands.format_result({"rows": []}).lower()


# --- end-to-end command run (no LLM involved) ---

@respx.mock
def test_run_command_executes_tool_and_formats():
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": [
            {"metric": {"request.uri": "/wp-login.php"}, "value": [0, "37"]}]}}))
    cmd = commands.parse_command("/scan_patterns 6h")
    reply = commands.run_command(cmd)
    assert "/wp-login.php" in reply["text"]
    assert reply["pre"] is True


@respx.mock
def test_run_command_tool_error_returns_usage_not_traceback():
    cmd = commands.parse_command("/edge_traffic 1h group_by=password")
    reply = commands.run_command(cmd)
    assert "group_by" in reply["text"]
    assert "Traceback" not in reply["text"]


# --- telegram.send extension: entities-based pre, chat_id/reply_to overrides ---

@respx.mock
def test_telegram_send_pre_uses_entities_not_parse_mode(monkeypatch):
    monkeypatch.setenv("FRANK_C2_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("FRANK_C2_TELEGRAM_CHAT_ID", "42")
    from ai_alert_helper import telegram
    import importlib; importlib.reload(telegram)
    route = respx.post("https://api.telegram.org/bottok/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True}))
    telegram.send("col1  col2\na     b", pre=True, chat_id="99", reply_to=1234)
    body = json.loads(route.calls.last.request.read())
    assert body["chat_id"] == "99"
    assert body["reply_to_message_id"] == 1234
    assert "parse_mode" not in body          # module-wide rule: never parse_mode
    assert body["entities"] == [{"type": "pre", "offset": 0,
                                 "length": len("col1  col2\na     b")}]


@respx.mock
def test_telegram_send_defaults_unchanged(monkeypatch):
    monkeypatch.setenv("FRANK_C2_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("FRANK_C2_TELEGRAM_CHAT_ID", "42")
    from ai_alert_helper import telegram
    import importlib; importlib.reload(telegram)
    route = respx.post("https://api.telegram.org/bottok/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True}))
    telegram.send("plain", urgent=True)
    body = json.loads(route.calls.last.request.read())
    assert body["chat_id"] == "42"
    assert body["text"].startswith("🔥 *URGENT* ")
    assert "entities" not in body and "reply_to_message_id" not in body
