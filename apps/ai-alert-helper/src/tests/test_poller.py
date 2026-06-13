"""Tests for poller.py — update routing, chat-ID gate, loop resilience —
and the POST /ask dry-run endpoint."""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient


def _reload_poller(monkeypatch):
    monkeypatch.setenv("FRANK_C2_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("FRANK_C2_TELEGRAM_CHAT_ID", "42")
    from ai_alert_helper import poller, telegram
    import importlib
    importlib.reload(telegram)
    importlib.reload(poller)
    return poller


def _update(text, chat_id=42, update_id=1, message_id=100):
    return {"update_id": update_id,
            "message": {"message_id": message_id,
                        "chat": {"id": chat_id}, "text": text}}


def test_foreign_chat_is_dropped_and_logged(monkeypatch, caplog):
    poller = _reload_poller(monkeypatch)
    sent = []
    monkeypatch.setattr(poller.telegram, "send", lambda *a, **k: sent.append((a, k)))
    with caplog.at_level(logging.WARNING):
        poller.handle_update(_update("/help", chat_id=666))
    assert sent == []
    assert any("666" in r.message for r in caplog.records)


def test_command_routes_to_dispatch_not_llm(monkeypatch):
    poller = _reload_poller(monkeypatch)
    sent = []
    monkeypatch.setattr(poller.telegram, "send", lambda text, **k: sent.append((text, k)))
    monkeypatch.setattr(poller.analyst, "answer",
                        lambda *a, **k: pytest.fail("LLM must not run for /commands"))
    poller.handle_update(_update("/help"))
    assert sent and "/scan_patterns" in sent[0][0]


def test_question_routes_to_analyst_with_reply(monkeypatch):
    poller = _reload_poller(monkeypatch)
    sent = []
    monkeypatch.setattr(poller.telegram, "send", lambda text, **k: sent.append((text, k)))
    monkeypatch.setattr(poller.analyst, "answer",
                        lambda q, chat: {"answer": f"echo:{q}", "tool_trace": []})
    poller.handle_update(_update("who scanned us?", message_id=321))
    text, kwargs = sent[0]
    assert text == "echo:who scanned us?"
    assert kwargs.get("reply_to") == 321


def test_reset_clears_history(monkeypatch):
    poller = _reload_poller(monkeypatch)
    cleared = []
    monkeypatch.setattr(poller.telegram, "send", lambda *a, **k: None)
    monkeypatch.setattr(poller.analyst, "reset", lambda chat: cleared.append(chat))
    poller.handle_update(_update("/reset"))
    assert cleared == ["42"]


def test_explain_suffix_narrates_result(monkeypatch):
    poller = _reload_poller(monkeypatch)
    sent = []
    monkeypatch.setattr(poller.telegram, "send", lambda text, **k: sent.append((text, k)))
    monkeypatch.setattr(poller.commands, "run_command",
                        lambda cmd: {"text": "raw rows", "pre": True, "result": {"rows": []}})
    monkeypatch.setattr(poller.analyst, "explain",
                        lambda result_text, command: "narrated meaning")
    poller.handle_update(_update("/scan_patterns 6h explain"))
    texts = [t for t, _ in sent]
    assert "raw rows" in texts and "narrated meaning" in texts


def test_handler_error_replies_in_channel(monkeypatch):
    poller = _reload_poller(monkeypatch)
    sent = []
    monkeypatch.setattr(poller.telegram, "send", lambda text, **k: sent.append(text))
    monkeypatch.setattr(poller.analyst, "answer",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    poller.handle_update(_update("question"))
    assert sent and "couldn't complete" in sent[0]


def test_poll_once_survives_get_updates_failure(monkeypatch):
    poller = _reload_poller(monkeypatch)
    def _raise(offset, timeout=30):
        raise ConnectionError("telegram down")
    monkeypatch.setattr(poller.telegram, "get_updates", _raise)
    assert poller.poll_once(17) == 17     # offset unchanged, no exception


def test_poll_once_advances_offset_past_processed(monkeypatch):
    poller = _reload_poller(monkeypatch)
    monkeypatch.setattr(poller.telegram, "get_updates",
                        lambda offset, timeout=30: [_update("/help", update_id=8),
                                                    _update("/help", update_id=9)])
    monkeypatch.setattr(poller.telegram, "send", lambda *a, **k: None)
    assert poller.poll_once(0) == 10      # max(update_id) + 1


def test_ask_endpoint_dry_runs_without_telegram(monkeypatch):
    from ai_alert_helper import api, analyst
    sent = []
    monkeypatch.setattr(api.telegram, "send", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(analyst, "answer",
                        lambda q, chat="default": {"answer": "A", "tool_trace": [{"tool": "x"}]})
    client = TestClient(api.app)
    r = client.post("/ask", params={"dry_run": "true"}, json={"question": "scans?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "A" and body["tool_trace"] == [{"tool": "x"}]
    assert sent == []
