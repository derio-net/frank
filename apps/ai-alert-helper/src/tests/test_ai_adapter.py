"""Tests for ai_adapter.{summarize,investigate} — the swap contract.

These ensure the LiteLLM-backed implementation:
- picks the right prompt template
- retries with the fallback model on primary failure
- preserves the {facts}/{alert} substitution shape
"""
from __future__ import annotations
import os
import respx
import httpx
import pytest


def _chat_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


@respx.mock
def test_summarize_calls_primary_model():
    os.environ["LITELLM_URL"] = "http://litellm.test"
    os.environ["LITELLM_API_KEY"] = "test-key"
    from ai_alert_helper import ai_adapter
    # Reload module to pick up env
    import importlib; importlib.reload(ai_adapter)

    route = respx.post("http://litellm.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("digest narrative")),
    )

    out = ai_adapter.summarize({"top_pages": [{"path": "/p", "count": 1}]})

    assert out == "digest narrative"
    assert route.called
    body = route.calls.last.request.read().decode()
    assert "qwen-think-14b" in body  # default primary


@respx.mock
def test_call_falls_back_to_secondary_on_5xx():
    os.environ["LITELLM_URL"] = "http://litellm.test"
    os.environ["LITELLM_API_KEY"] = "test-key"
    os.environ["LLM_MODEL_FALLBACK"] = "gemma-12b"   # distinct fallback configured
    from ai_alert_helper import ai_adapter
    import importlib; importlib.reload(ai_adapter)

    # Primary returns 503, fallback returns 200
    route = respx.post("http://litellm.test/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json=_chat_response("fallback worked")),
        ],
    )

    out = ai_adapter.summarize({"x": 1})

    assert out == "fallback worked"
    assert route.call_count == 2
    # Second call should reference the fallback model
    body = route.calls[-1].request.read().decode()
    assert "gemma-12b" in body
    del os.environ["LLM_MODEL_FALLBACK"]


# --- optional fallback (2026-06-04: no-fallback policy, local-only inference) ---

@respx.mock
def test_no_fallback_env_means_single_attempt_and_loud_failure():
    """LLM_MODEL_FALLBACK unset → exactly one attempt; the error propagates.
    The old hardcoded claude-haiku-4-5 default 400'd silently for weeks."""
    os.environ["LITELLM_URL"] = "http://litellm.test"
    os.environ["LITELLM_API_KEY"] = "test-key"
    os.environ.pop("LLM_MODEL_FALLBACK", None)
    from ai_alert_helper import ai_adapter
    import importlib; importlib.reload(ai_adapter)

    route = respx.post("http://litellm.test/v1/chat/completions").mock(
        return_value=httpx.Response(503))

    with pytest.raises(httpx.HTTPStatusError):
        ai_adapter.summarize({"x": 1})
    assert route.call_count == 1


@respx.mock
def test_fallback_equal_to_primary_means_single_attempt():
    """fallback == primary → no pointless identical retry (doubles latency in
    the exact gpu-1-saturation scenario the fallback was meant to cover)."""
    os.environ["LITELLM_URL"] = "http://litellm.test"
    os.environ["LITELLM_API_KEY"] = "test-key"
    os.environ["LLM_MODEL_FALLBACK"] = "qwen-think-14b"   # == default primary
    from ai_alert_helper import ai_adapter
    import importlib; importlib.reload(ai_adapter)

    route = respx.post("http://litellm.test/v1/chat/completions").mock(
        return_value=httpx.Response(503))

    with pytest.raises(httpx.HTTPStatusError):
        ai_adapter.summarize({"x": 1})
    assert route.call_count == 1
    del os.environ["LLM_MODEL_FALLBACK"]


@respx.mock
def test_investigate_picks_surge_template_for_BlogTrafficSurge_alert():
    os.environ["LITELLM_URL"] = "http://litellm.test"
    os.environ["LITELLM_API_KEY"] = "test-key"
    from ai_alert_helper import ai_adapter
    import importlib; importlib.reload(ai_adapter)

    route = respx.post("http://litellm.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("surge narrative")),
    )

    out = ai_adapter.investigate(
        {"alertname": "BlogTrafficSurgeMajor"},
        {"current": 500, "baseline": 50, "ratio": 10.0},
    )

    assert out == "surge narrative"
    body = route.calls.last.request.read().decode()
    # Should embed surge-specific words from the surge prompt template
    assert "surge" in body.lower() or "spike" in body.lower() or "traffic" in body.lower()


@respx.mock
def test_investigate_picks_generic_template_for_unknown_alert():
    os.environ["LITELLM_URL"] = "http://litellm.test"
    os.environ["LITELLM_API_KEY"] = "test-key"
    from ai_alert_helper import ai_adapter
    import importlib; importlib.reload(ai_adapter)

    respx.post("http://litellm.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_chat_response("ok")),
    )

    out = ai_adapter.investigate(
        {"alertname": "CrowdSecDecisionBurst"},
        {"decisions": 12},
    )

    assert out == "ok"
