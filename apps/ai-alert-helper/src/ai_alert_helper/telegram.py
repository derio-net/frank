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
        # Telegram entity offsets/lengths are UTF-16 code units, not Python
        # code points — tool output can carry non-BMP chars (emoji in
        # attacker-controlled UAs/paths) that count as 2 units each.
        utf16_len = len(text.encode("utf-16-le")) // 2
        payload["entities"] = [{"type": "pre", "offset": 0, "length": utf16_len}]
    httpx.post(
        f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
        json=payload,
        timeout=15,
    )


def get_updates(offset: int, timeout: int = 30) -> list[dict]:
    """Long-poll getUpdates. ONE consumer per bot token (Telegram 409s a
    second poller) — the Deployment is replicas:1 + strategy:Recreate for
    exactly this reason. Client timeout wraps the server-side long poll."""
    if not _TOKEN:
        return []
    resp = httpx.get(
        f"https://api.telegram.org/bot{_TOKEN}/getUpdates",
        params={"offset": offset, "timeout": timeout},
        timeout=timeout + 5,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def set_my_commands(commands: list[dict]) -> None:
    """Register the slash-command menu (BotCommand list) — fail-soft."""
    if not _TOKEN:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{_TOKEN}/setMyCommands",
            json={"commands": commands},
            timeout=15,
        )
    except Exception:  # noqa: BLE001 — menu registration is best-effort
        pass
