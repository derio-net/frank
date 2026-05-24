"""Thin Telegram Bot API wrapper.

Uses the existing FRANK_C2_TELEGRAM_BOT_TOKEN + FRANK_C2_TELEGRAM_CHAT_ID
env vars (replicated from Frank's grafana-alerting-secrets).
"""
from __future__ import annotations
import os

import httpx

_TOKEN = os.environ.get("FRANK_C2_TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.environ.get("FRANK_C2_TELEGRAM_CHAT_ID", "")


def send(text: str, urgent: bool = False) -> None:
    """Post a plain-text Telegram message. parse_mode unset on purpose —
    per the existing grafana contact-points-cm.yaml comment, markdown
    interprets underscores as italic delimiters and silently strips them,
    which has caused real triage misdirection.
    """
    if urgent:
        text = "🔥 *URGENT* " + text
    if not _TOKEN or not _CHAT_ID:
        return
    httpx.post(
        f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
        json={"chat_id": _CHAT_ID, "text": text},
        timeout=15,
    )
