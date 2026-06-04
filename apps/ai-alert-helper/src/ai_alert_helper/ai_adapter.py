"""LiteLLM-backed implementation of the AI adapter swap contract.

Future Sympozium swap replaces only this module. The summarize() /
investigate() signatures and the fact-sheet shape are the contract —
don't change them without a follow-up plan.
"""
from __future__ import annotations
import os
from pathlib import Path

import httpx

_LITELLM_URL = os.environ.get("LITELLM_URL", "")
_LITELLM_KEY = os.environ.get("LITELLM_API_KEY", "")
_PRIMARY = os.environ.get("LLM_MODEL_PRIMARY", "qwen-think-14b")
# Empty default = NO fallback (2026-06-04 local-only policy). The old
# hardcoded claude-haiku-4-5 default pointed at an alias removed from
# LiteLLM and 400'd on every attempt — a fallback that can't work is
# worse than failing loud.
_FALLBACK = os.environ.get("LLM_MODEL_FALLBACK", "")
_PROMPTS = Path(__file__).parent / "prompts"


def _call_once(model: str, prompt: str) -> str:
    resp = httpx.post(
        f"{_LITELLM_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {_LITELLM_KEY}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call(prompt: str) -> str:
    try:
        return _call_once(_PRIMARY, prompt)
    except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.HTTPError):
        # Retry only on a real, distinct fallback — an identical retry adds
        # latency without resilience (the primary's failure mode, gpu-1
        # saturation, doesn't clear in seconds).
        if not _FALLBACK or _FALLBACK == _PRIMARY:
            raise
        return _call_once(_FALLBACK, prompt)


def summarize(facts: dict) -> str:
    """Daily digest — ~200-word narrative from a structured facts dict."""
    template = (_PROMPTS / "digest.txt").read_text()
    return _call(template.format(facts=facts))


def investigate(alert: dict, facts: dict) -> str:
    """Alert enrichment — 1-paragraph 'what happened, what's the risk'."""
    kind = "surge" if "Surge" in alert.get("alertname", "") else "generic"
    template = (_PROMPTS / f"investigate-{kind}.txt").read_text()
    return _call(template.format(alert=alert, facts=facts))
