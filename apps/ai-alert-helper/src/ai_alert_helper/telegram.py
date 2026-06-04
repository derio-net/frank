"""Thin Telegram Bot API wrapper.

Uses the existing FRANK_C2_TELEGRAM_BOT_TOKEN + FRANK_C2_TELEGRAM_CHAT_ID
env vars (replicated from Frank's grafana-alerting-secrets).
"""
from __future__ import annotations
import os

import httpx

_TOKEN = os.environ.get("FRANK_C2_TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.environ.get("FRANK_C2_TELEGRAM_CHAT_ID", "")


def send(
    text: str,
    urgent: bool = False,
    *,
    chat_id: str | None = None,
    reply_to: int | None = None,
    pre: bool = False,
) -> None:
    """Post a plain-text Telegram message. parse_mode unset on purpose —
    per the existing grafana contact-points-cm.yaml comment, markdown
    interprets underscores as italic delimiters and silently strips them,
    which has caused real triage misdirection. Monospace blocks use the
    entities API instead (explicit offsets, no markdown parsing at all).
    """
    if urgent:
        text = "🔥 *URGENT* " + text
    if not _TOKEN or not (chat_id or _CHAT_ID):
        return
    payload: dict = {"chat_id": chat_id or _CHAT_ID, "text": text}
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    if pre:
        payload["entities"] = [{"type": "pre", "offset": 0, "length": len(text)}]
    httpx.post(
        f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
        json=payload,
        timeout=15,
    )
