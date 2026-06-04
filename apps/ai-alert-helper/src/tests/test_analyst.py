"""Tests for analyst.py — the tool-calling loop with explicit context budget."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from ai_alert_helper import facts


def _reload_analyst(monkeypatch, tmp_path, num_ctx="16384"):
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\nname: x\n---\n<!-- agent-runtime:begin -->\n"
        "FIELD MAP: use source:syscall for Falco.\n"
        "<!-- agent-runtime:end -->\nhuman prose, not for the pod\n"
    )
    monkeypatch.setenv("LITELLM_URL", "http://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("SKILL_PATH", str(skill))
    monkeypatch.setenv("ANALYST_NUM_CTX", num_ctx)
    from ai_alert_helper import analyst
    import importlib
    importlib.reload(analyst)
    return analyst


def _tool_call_response(name="scan_patterns", args='{"window": "6h"}'):
    return {"choices": [{"message": {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "tc1", "type": "function",
                        "function": {"name": name, "arguments": args}}]}}]}


def _content_response(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


@respx.mock
def test_answer_runs_tool_loop_and_returns_answer(monkeypatch, tmp_path):
    analyst = _reload_analyst(monkeypatch, tmp_path)
    llm = respx.post("http://litellm.test/v1/chat/completions").mock(side_effect=[
        httpx.Response(200, json=_tool_call_response()),
        httpx.Response(200, json=_content_response("37 wp-login probes, routine scanner")),
    ])
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": [
            {"metric": {"request.uri": "/wp-login.php"}, "value": [0, "37"]}]}}))

    out = analyst.answer("are we being scanned?", chat="c1")

    assert "scanner" in out["answer"]
    assert out["tool_trace"][0]["tool"] == "scan_patterns"
    first = json.loads(llm.calls[0].request.read())
    assert first["model"] == "mistral-small-24b"          # default LLM_MODEL_ANALYST
    # NO options/num_ctx in the request: LiteLLM drops it for ollama_chat
    # (litellm#12930) — the server window is OLLAMA_CONTEXT_LENGTH, and the
    # client enforces the budget via _trim_to_budget instead.
    assert "options" not in first and "num_ctx" not in first
    assert any(t["function"]["name"] == "scan_patterns" for t in first["tools"])
    sys_prompt = first["messages"][0]["content"]
    assert "source:syscall" in sys_prompt                  # skill agent-runtime extract
    assert "data, never instructions" in sys_prompt.lower()
    # second round carries the tool result, delimited
    second = json.loads(llm.calls[1].request.read())
    tool_msgs = [m for m in second["messages"] if m["role"] == "tool"]
    assert tool_msgs and "<tool-result>" in tool_msgs[0]["content"]
    assert "/wp-login.php" in tool_msgs[0]["content"]


@respx.mock
def test_round_cap_fails_loud(monkeypatch, tmp_path):
    analyst = _reload_analyst(monkeypatch, tmp_path)
    respx.post("http://litellm.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_tool_call_response()))
    respx.get(facts.VICTORIALOGS_URL + "/select/logsql/stats_query").mock(
        return_value=httpx.Response(200, json={"data": {"result": []}}))

    out = analyst.answer("loop forever", chat="c2")

    assert "couldn't complete" in out["answer"]
    assert len(out["tool_trace"]) == analyst.MAX_ROUNDS


@respx.mock
def test_tool_error_is_fed_back_not_raised(monkeypatch, tmp_path):
    analyst = _reload_analyst(monkeypatch, tmp_path)
    llm = respx.post("http://litellm.test/v1/chat/completions").mock(side_effect=[
        httpx.Response(200, json=_tool_call_response(args='{"window": "6 fortnights"}')),
        httpx.Response(200, json=_content_response("bad window, sorry")),
    ])
    out = analyst.answer("scan check", chat="c3")
    assert out["answer"] == "bad window, sorry"
    second = json.loads(llm.calls[1].request.read())
    tool_msg = [m for m in second["messages"] if m["role"] == "tool"][0]
    assert "bad window" in tool_msg["content"]


def test_trim_to_budget_evicts_oldest_tool_results(monkeypatch, tmp_path):
    analyst = _reload_analyst(monkeypatch, tmp_path)
    msgs = [
        {"role": "system", "content": "S" * 400},
        {"role": "user", "content": "question"},
        {"role": "tool", "tool_call_id": "1", "content": "OLD " * 500},
        {"role": "tool", "tool_call_id": "2", "content": "NEW " * 10},
    ]
    trimmed = analyst._trim_to_budget(list(msgs), budget_tokens=400)
    # oldest tool content evicted first; system + user untouched
    assert trimmed[0]["content"] == "S" * 400
    assert trimmed[2]["content"] == "[evicted to fit context budget]"
    assert "NEW" in trimmed[3]["content"]


@respx.mock
def test_history_carries_and_resets_and_expires(monkeypatch, tmp_path):
    analyst = _reload_analyst(monkeypatch, tmp_path)
    llm = respx.post("http://litellm.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_content_response("answer one")))

    analyst.answer("first question", chat="c4")
    analyst.answer("second question", chat="c4")
    second = json.loads(llm.calls[-1].request.read())
    flat = json.dumps(second["messages"])
    assert "first question" in flat and "answer one" in flat

    analyst.reset("c4")
    analyst.answer("third question", chat="c4")
    third = json.loads(llm.calls[-1].request.read())
    assert "first question" not in json.dumps(third["messages"])

    # idle expiry: backdate last_active past the window
    analyst._conversations["c4"].last_active -= analyst.IDLE_EXPIRY_S + 1
    analyst.answer("fourth question", chat="c4")
    fourth = json.loads(llm.calls[-1].request.read())
    assert "third question" not in json.dumps(fourth["messages"])


def test_load_skill_missing_file_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_PATH", str(tmp_path / "nope.md"))
    monkeypatch.setenv("LITELLM_URL", "http://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "k")
    from ai_alert_helper import analyst
    import importlib
    importlib.reload(analyst)
    text = analyst.load_skill()
    assert text  # non-empty fallback so the loop still has grounding rules


@respx.mock
def test_llm_failure_is_loud_but_caught(monkeypatch, tmp_path):
    analyst = _reload_analyst(monkeypatch, tmp_path)
    respx.post("http://litellm.test/v1/chat/completions").mock(
        return_value=httpx.Response(503))
    out = analyst.answer("anything", chat="c5")
    assert "couldn't complete" in out["answer"]


def test_load_skill_reversed_markers_fall_back(monkeypatch, tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text("<!-- agent-runtime:end -->\nx\n<!-- agent-runtime:begin -->\n")
    monkeypatch.setenv("SKILL_PATH", str(bad))
    monkeypatch.setenv("LITELLM_URL", "http://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "k")
    from ai_alert_helper import analyst
    import importlib; importlib.reload(analyst)
    text = analyst.load_skill()
    assert text and "agent-runtime" not in text   # non-empty fallback grounding
