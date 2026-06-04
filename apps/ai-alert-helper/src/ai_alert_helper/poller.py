"""Telegram getUpdates poller — the analyst's inbound path.

Long-polls with the SAME bot token the alert pipeline sends with (Telegram
allows exactly one getUpdates consumer per token — replicas:1 + Recreate on
the Deployment exist for this). Updates from any chat other than the
operator's are dropped and logged at WARNING: someone probing the bot is
itself a security signal.
"""
from __future__ import annotations

import asyncio
import logging
import os

from . import analyst, commands, telegram

log = logging.getLogger("ai_alert_helper.analyst")

_ALLOWED_CHAT = os.environ.get("FRANK_C2_TELEGRAM_CHAT_ID", "")


def handle_update(update: dict) -> None:
    """Route one update. Never raises — errors reply in-channel."""
    msg = update.get("message") or {}
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    text = msg.get("text") or ""
    reply_to = msg.get("message_id")
    if not text:
        return
    if not _ALLOWED_CHAT or chat_id != _ALLOWED_CHAT:
        log.warning("dropped update from non-allowlisted chat %s: %.60r", chat_id, text)
        return
    try:
        cmd = commands.parse_command(text)
        if cmd is None:
            out = analyst.answer(text, chat=chat_id)
            telegram.send(out["answer"], chat_id=chat_id, reply_to=reply_to)
            return
        if cmd["kind"] == "reset":
            analyst.reset(chat_id)
            telegram.send("history cleared", chat_id=chat_id, reply_to=reply_to)
            return
        reply = commands.run_command(cmd)
        telegram.send(reply["text"], chat_id=chat_id, reply_to=reply_to,
                      pre=reply.get("pre", False))
        if cmd.get("explain") and "result" in reply:
            telegram.send(analyst.explain(reply["text"], text),
                          chat_id=chat_id, reply_to=reply_to)
    except Exception as e:  # noqa: BLE001 — fail loud, in-channel, never silent
        log.error("handle_update failed: %s", e)
        telegram.send(f"couldn't complete: {type(e).__name__}",
                      chat_id=chat_id, reply_to=reply_to)


def poll_once(offset: int) -> int:
    """One getUpdates round. Returns the next offset; swallows transport
    errors (the loop backs off and continues)."""
    try:
        updates = telegram.get_updates(offset, timeout=30)
    except Exception as e:  # noqa: BLE001
        log.error("getUpdates failed: %s", e)
        return offset
    for u in updates:
        handle_update(u)
        offset = max(offset, u.get("update_id", 0) + 1)
    return offset


async def poll_loop() -> None:
    """Background task: register the command menu, then poll forever."""
    try:
        telegram.set_my_commands(commands.bot_commands())
    except Exception:  # noqa: BLE001 — menu is best-effort
        pass
    offset = 0
    backoff = 1.0
    log.info("analyst poller started (chat gate: %s)", _ALLOWED_CHAT or "UNSET")
    while True:
        try:
            new_offset = await asyncio.to_thread(poll_once, offset)
            backoff = 1.0 if new_offset != offset else min(backoff, 30.0)
            if new_offset == offset:
                await asyncio.sleep(0)  # long poll already waited server-side
            offset = new_offset
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — a dead poller must restart itself
            log.error("poll_loop iteration failed: %s — backing off %.0fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
