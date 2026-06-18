"""telegram-bridge core (stdlib-only).

`_http_post_json` is the single HTTP seam (Telegram API + the local agent-session
endpoint) the tests patch. Telegram messages are sent as PLAIN TEXT (no parse_mode)
— the HTML parse_mode 400s on a bare `<`/`>`/`&` in a narrative (frank-gotchas).
"""
from __future__ import annotations
import json
import os
import re
import sys
import threading
import time
import urllib.request

# Telegram's command-id rule: lowercase letters, digits, underscore; 1–32 chars
# (NO hyphens). One invalid id makes setMyCommands 400 and rejects the WHOLE menu.
_TG_COMMAND_ID_RE = re.compile(r"^[a-z0-9_]{1,32}$")

BOT_TOKEN = os.environ.get("FRANK_C2_TELEGRAM_BOT_TOKEN", "")
# Allowlist of chat ids permitted to drive the agent (comma-separated). The
# default chat is the first; outbound narratives go there.
_CHATS = [c.strip() for c in os.environ.get("FRANK_C2_TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
DEFAULT_CHAT = _CHATS[0] if _CHATS else ""
ALLOWED_CHATS = set(_CHATS)

SESSION_URL = os.environ.get("AGENT_SESSION_URL", "http://localhost:8765")
SESSION_AGENT = os.environ.get("AGENT_SESSION_AGENT", "claude")
SESSION_ID = os.environ.get("AGENT_SESSION_ID", "alert-agent")
# How long to wait for an interactive DM turn. The old 120s cut off legitimate
# answers — a thorough probe-based "cluster status" investigation runs ~5 min. The
# 120s was a pre-threading guard against freezing the single getUpdates consumer;
# Fix D moved turns to per-session worker threads, so a slow turn no longer blocks
# the consumer or static /help — only a second DM to the SAME chat waits. So allow
# DM turns to run long enough to actually finish.
DM_TIMEOUT_S = float(os.environ.get("DM_TIMEOUT_S", "600"))


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
    the reaction set, so ⚡ → 👍/🤔 reads as 'working → done'.

    NOTE: `emoji` MUST be from Telegram's fixed reaction allowlist (⚡ 👍 🤔 are);
    an off-list emoji 400s and — by design — fails silently here."""
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
    "/edge_traffic": {
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
    parts = text.strip().split(None, 1)   # split on any whitespace run, not just " "
    word = parts[0] if parts else ""
    spec = COMMANDS.get(word)
    if spec is None:
        return "unknown", "Unknown command — try /help"
    if spec["kind"] == "static":
        return "static", _help_text()
    args = parts[1].strip() if len(parts) > 1 else ""
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


# Per-session_id locks serialize same-session agent turns so two DMs never
# interleave pastes into one tmux session. A registry lock guards lazy creation.
# Different sessions and static commands never contend.
_session_locks: dict[str, threading.Lock] = {}
_session_locks_registry = threading.Lock()


def _session_lock(session_id: str) -> threading.Lock:
    with _session_locks_registry:
        lock = _session_locks.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _session_locks[session_id] = lock
        return lock


def _react_fn(chat_id, message_id):
    def react(emoji):
        if message_id is not None:
            tg_react(str(chat_id), message_id, emoji)
    return react


def _prepare(update: dict):
    """Parse + allowlist one getUpdates entry. Returns (chat_id, message_id, text)
    or None if the update is empty / from a non-allowlisted chat (dropped, WARNed)."""
    msg = update.get("message") or update.get("edited_message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")
    text = (msg.get("text") or "").strip()
    if chat_id is None or not text:
        return None
    if not is_allowed(chat_id):
        print(f"WARN telegram-bridge: dropped message from non-allowlisted chat {chat_id}",
              file=sys.stderr)
        return None
    return chat_id, message_id, text


def _receipt_and_route(chat_id, message_id, text):
    """Fire the ⚡ receipt and answer static/unknown slash commands INLINE (so /help
    works even when the agent is cold/slow). Returns the agent instruction to run,
    or None when the update was already fully handled inline."""
    react = _react_fn(chat_id, message_id)
    react("⚡")   # receipt — fired BEFORE the (possibly slow) turn so feedback is instant
    if text.startswith("/"):
        kind, payload = expand_command(text)
        if kind in ("static", "unknown"):
            tg_send(payload, str(chat_id))
            react("👍")
            return None
        return payload
    return text   # no leading slash → free-text Q&A verbatim


def _run_agent_turn(chat_id, message_id, message) -> None:
    """Drive the agent for one turn under the per-session lock, reply, react 👍/🤔.
    The lock serializes same-session turns (no interleaved pastes); the wait spans
    only session_send so a finished turn frees the session immediately."""
    react = _react_fn(chat_id, message_id)
    session_id = f"{SESSION_ID}-tg-{chat_id}"
    with _session_lock(session_id):
        # Long enough for a thorough turn to finish (DM_TIMEOUT_S). Safe under
        # threading: a slow turn holds only THIS session's lock, not the consumer.
        resp = session_send(message, session_id=session_id, timeout_s=DM_TIMEOUT_S)
    rendered = render_payload(resp)
    tg_send(rendered or "(the agent did not return a reply — it may be busy or unauthenticated)",
            str(chat_id))
    react("👍" if rendered is not None else "🤔")   # 🤔 = only the deterministic fallback was posted


def process_update(update: dict) -> bool:
    """Synchronous handler (one update end-to-end) — the inline core and the unit
    contract. poll_loop uses dispatch_update for non-blocking turns. Returns True
    if handled (driven or static reply), False if dropped."""
    prepared = _prepare(update)
    if prepared is None:
        return False
    chat_id, message_id, text = prepared
    message = _receipt_and_route(chat_id, message_id, text)
    if message is not None:
        _run_agent_turn(chat_id, message_id, message)
    return True


def dispatch_update(update: dict):
    """Non-blocking entry the poll loop calls. ⚡ receipt + static/unknown replies
    are answered INLINE in the single getUpdates consumer; an agent turn runs in a
    per-session-serialized worker thread so a slow/stuck turn never head-of-line-
    blocks the consumer (or a static /help). Returns the worker Thread for an agent
    turn, else None (handled inline / dropped)."""
    prepared = _prepare(update)
    if prepared is None:
        return None
    chat_id, message_id, text = prepared
    message = _receipt_and_route(chat_id, message_id, text)
    if message is None:
        return None
    t = threading.Thread(target=_run_agent_turn, args=(chat_id, message_id, message), daemon=True)
    t.start()
    return t


def set_my_commands() -> None:
    """Register the Telegram command menu from COMMANDS (best-effort — a failure
    logs a WARN and the bridge runs anyway; the menu is a nicety, not a dependency)."""
    try:
        cmds = []
        for c, s in COMMANDS.items():
            ident = c.lstrip("/")
            if not _TG_COMMAND_ID_RE.match(ident):
                # Skip (don't send) an invalid id — a single bad one would 400 the
                # whole menu. Fail-soft: that command is just absent from the menu.
                print(f"WARN telegram-bridge: skipping invalid command id {c!r} "
                      f"(not {_TG_COMMAND_ID_RE.pattern})", file=sys.stderr)
                continue
            cmds.append({"command": ident, "description": s["desc"]})
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
                dispatch_update(upd)   # non-blocking: agent turn threads, consumer keeps reading
            except Exception as exc:  # noqa: BLE001 — one bad update must not kill the loop
                print(f"WARN telegram-bridge: update handling failed: {exc}", file=sys.stderr)
