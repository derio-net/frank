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


def tg_react(chat_id, message_id, emoji: str) -> None:
    """Set a single emoji reaction on a message — best-effort feedback (⚡ on
    receipt, 👍/🤔 on completion). A reaction failure must NEVER block or delay
    the reply, so any error is swallowed with a WARN. setMessageReaction REPLACES
    the reaction set, so ⚡ → 👍/🤔 reads as 'working → done'."""
    try:
        _tg("setMessageReaction", {"chat_id": chat_id, "message_id": message_id,
                                   "reaction": [{"type": "emoji", "emoji": emoji}]})
    except Exception as exc:  # noqa: BLE001
        print(f"WARN telegram-bridge: setMessageReaction failed: {exc}", file=sys.stderr)


# --- Slash commands ------------------------------------------------------------
# COMMANDS is the SINGLE source of truth for both the Telegram menu (setMyCommands)
# and routing. A command is never argument-parsed: a templated command becomes one
# English instruction for the agent (which has the frank-facts CLI as a shell tool),
# carrying a "use sensible defaults" suffix — so the argless-from-menu trap (Telegram
# sends a menu command bare) simply has no positional arg to be missing.
_DEFAULTS_SUFFIX = (
    " Use sensible defaults and answer now; if a parameter is truly needed, pick the "
    "obvious default and state which you used."
)

COMMANDS = {
    "/help": {"desc": "List the available commands", "kind": "static"},
    "/digest": {
        "desc": "On-demand daily digest",
        "kind": "prompt",
        "template": "Run the daily digest (`frank-facts digest`) and summarize for the operator.",
    },
    "/surge": {
        "desc": "Current traffic-surge status",
        "kind": "prompt",
        "template": "Report current surge status (`frank-facts surge`).",
    },
    "/edge-traffic": {
        "desc": "Hop edge traffic summary",
        "kind": "prompt",
        "template": (
            "Summarize Hop edge traffic — top scanned paths and attacker IPs "
            "(`frank-facts top-scanned-paths`, `top-attacker-ips`), last 24h by default."
        ),
    },
    "/security": {
        "desc": "Security picture (CrowdSec/Falco/scans)",
        "kind": "prompt",
        "template": (
            "Summarize the security picture — CrowdSec decisions and scan patterns "
            "(`frank-facts crowdsec`, `scan-patterns`) plus any notable Falco events."
        ),
    },
    "/status": {
        "desc": "Cluster + alert-agent health snapshot",
        "kind": "prompt",
        "template": (
            "Give a short cluster + alert-agent health snapshot from the HTTP probes you "
            "can reach (Derio Ops / blackbox)."
        ),
    },
}


def _help_text() -> str:
    lines = ["Commands:"] + [f"{cmd} — {spec['desc']}" for cmd, spec in COMMANDS.items()]
    return "\n".join(lines)


def expand_command(text: str):
    """Map a leading-slash message to (kind, payload).

    kind 'static'  → payload is text the bridge replies with directly (no agent).
    kind 'prompt'  → payload is the agent instruction (template + operator args + defaults).
    kind 'unknown' → payload is the not-found reply.
    """
    word, _, rest = text.strip().partition(" ")
    spec = COMMANDS.get(word)
    if spec is None:
        return "unknown", "Unknown command — try /help"
    if spec["kind"] == "static":
        return "static", _help_text()
    args = rest.strip()
    instruction = spec["template"] + ((" " + args) if args else "") + _DEFAULTS_SUFFIX
    return "prompt", instruction


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
    message_id = msg.get("message_id")
    text = (msg.get("text") or "").strip()
    if chat_id is None or not text:
        return False
    if not is_allowed(chat_id):
        print(f"WARN telegram-bridge: dropped message from non-allowlisted chat {chat_id}",
              file=sys.stderr)
        return False

    def react(emoji):
        if message_id is not None:
            tg_react(str(chat_id), message_id, emoji)

    react("⚡")   # receipt — fired BEFORE the (possibly slow) turn so feedback is instant
    # Slash command? Static/unknown are answered by the bridge directly (so /help
    # works even when the agent is cold); a prompt command expands to an agent
    # instruction. No leading slash → the unchanged free-text Q&A path.
    if text.startswith("/"):
        kind, payload = expand_command(text)
        if kind in ("static", "unknown"):
            tg_send(payload, str(chat_id))
            react("👍")
            return True
        message = payload
    else:
        message = text
    # Shorter timeout for an interactive DM than the cron 300s — a stuck turn
    # must not freeze the single getUpdates consumer for 5 minutes.
    resp = session_send(message, session_id=f"{SESSION_ID}-tg-{chat_id}", timeout_s=120)
    rendered = render_payload(resp)
    tg_send(rendered or "(the agent did not return a reply — it may be busy or unauthenticated)",
            str(chat_id))
    react("👍" if rendered is not None else "🤔")   # 🤔 = only the deterministic fallback was posted
    return True


def set_my_commands() -> None:
    """Register the Telegram command menu from COMMANDS (best-effort — a failure
    logs a WARN and the bridge runs anyway; the menu is a nicety, not a dependency)."""
    try:
        cmds = [{"command": c.lstrip("/"), "description": s["desc"]} for c, s in COMMANDS.items()]
        _tg("setMyCommands", {"commands": cmds})
    except Exception as exc:  # noqa: BLE001
        print(f"WARN telegram-bridge: setMyCommands failed: {exc}", file=sys.stderr)


def poll_loop(poll_timeout: int = 30) -> None:  # pragma: no cover - network loop
    """Long-poll getUpdates forever (single consumer per bot token)."""
    set_my_commands()
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
