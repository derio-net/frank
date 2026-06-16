"""telegram-bridge core (stdlib-only).

`_http_post_json` is the single HTTP seam (Telegram API + the local agent-session
endpoint) the tests patch. Telegram messages are sent as PLAIN TEXT (no parse_mode)
— the HTML parse_mode 400s on a bare `<`/`>`/`&` in a narrative (frank-gotchas).
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request

BOT_TOKEN = os.environ.get("FRANK_C2_TELEGRAM_BOT_TOKEN", "")
# Allowlist of chat ids permitted to drive the agent (comma-separated). The
# default chat is the first; outbound narratives go there.
_CHATS = [c.strip() for c in os.environ.get("FRANK_C2_TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
DEFAULT_CHAT = _CHATS[0] if _CHATS else ""
ALLOWED_CHATS = set(_CHATS)

SESSION_URL = os.environ.get("AGENT_SESSION_URL", "http://localhost:8765")
SESSION_AGENT = os.environ.get("AGENT_SESSION_AGENT", "claude")
SESSION_ID = os.environ.get("AGENT_SESSION_ID", "alert-agent")


def _http_post_json(url: str, payload: dict, timeout: float = 310) -> dict:
    """POST JSON, return parsed JSON. The single seam tests patch."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8", "replace") or "{}")


def _tg(method: str, params: dict, timeout: float = 35) -> dict:
    return _http_post_json(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", params, timeout)


def tg_send(text: str, chat_id: str | None = None) -> dict:
    """Send PLAIN TEXT to a chat (default the configured operator chat)."""
    return _tg("sendMessage", {"chat_id": chat_id or DEFAULT_CHAT, "text": text})


def is_allowed(chat_id) -> bool:
    return str(chat_id) in ALLOWED_CHATS


def session_send(message: str, session_id: str | None = None, timeout_s: float = 300) -> dict:
    """Drive the persistent agent session. Returns the agent-session response
    {session_id, agent, status, turn, payload}; status 'timeout' → payload None."""
    return _http_post_json(
        f"{SESSION_URL}/session/send",
        {"session_id": session_id or SESSION_ID, "agent": SESSION_AGENT,
         "message": message, "timeout_s": timeout_s},
        timeout=timeout_s + 10,
    )


def render_payload(resp: dict) -> str | None:
    """Human text from an agent-session response, or None if it didn't complete.

    The agent's output contract (taught in SKILL.md): write {"text": "..."}. We
    accept a bare string payload too. None when status != ok or payload is empty.
    """
    if not resp or resp.get("status") != "ok":
        return None
    payload = resp.get("payload")
    if payload is None:
        return None
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return payload.get("text") or json.dumps(payload)
    return json.dumps(payload)


def deliver(resp: dict, fallback_text: str, chat_id: str | None = None) -> dict:
    """Post an agent narrative; if the agent timed out / returned no payload, post
    the deterministic fallback instead — so a stuck agent never silences the digest."""
    text = render_payload(resp)
    if text is None:
        text = fallback_text
    return tg_send(text, chat_id)


def process_update(update: dict) -> bool:
    """Handle one getUpdates entry. Allowlisted message → agent → reply.
    Returns True if it drove the agent, False if dropped. Non-allowlisted chats
    are dropped with a WARN (the gate working, not the bot broken)."""
    msg = update.get("message") or update.get("edited_message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if chat_id is None or not text:
        return False
    if not is_allowed(chat_id):
        print(f"WARN telegram-bridge: dropped message from non-allowlisted chat {chat_id}",
              file=sys.stderr)
        return False
    resp = session_send(text, session_id=f"{SESSION_ID}-tg-{chat_id}")
    reply = render_payload(resp) or "(the agent did not return a reply — it may be busy or unauthenticated)"
    tg_send(reply, str(chat_id))
    return True


def poll_loop(poll_timeout: int = 30) -> None:  # pragma: no cover - network loop
    """Long-poll getUpdates forever (single consumer per bot token)."""
    offset = 0
    while True:
        try:
            resp = _tg("getUpdates", {"offset": offset, "timeout": poll_timeout}, timeout=poll_timeout + 10)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN telegram-bridge: getUpdates failed: {exc}", file=sys.stderr)
            time.sleep(3)
            continue
        for upd in resp.get("result", []):
            offset = max(offset, upd.get("update_id", 0) + 1)
            try:
                process_update(upd)
            except Exception as exc:  # noqa: BLE001 — one bad update must not kill the loop
                print(f"WARN telegram-bridge: update handling failed: {exc}", file=sys.stderr)
