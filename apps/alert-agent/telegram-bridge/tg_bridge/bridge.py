"""telegram-bridge core (stdlib-only).

`_http_post_json` is the single HTTP seam (Telegram API + the local agent-session
endpoint) the tests patch. Narratives are sent as PLAIN TEXT (no parse_mode);
structured REPORTS opt into parse_mode=HTML with `<pre>` monospace tables and
STRICT per-value `html.escape` — the HTML parse_mode 400s on a bare `<`/`>`/`&`
(frank-gotchas), so `send_reply` retries once as plain text on a 400, and a
formatting bug can degrade readability but never delivery.
"""
from __future__ import annotations
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
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
# How long to wait for an interactive DM turn. Per-session worker threads (Fix D)
# mean a slow turn blocks only a second DM to the SAME chat, never the getUpdates
# consumer or static /help — so this bound is purely about operator responsiveness.
# Bounded so a probe-sweeping turn can't leave the operator waiting minutes. A
# focused turn (≤2 probes, per the SKILL) finishes well inside this; when the
# model over-investigates past it, _run_agent_turn posts a deterministic
# frank-facts snapshot instead of the useless "(no reply)" — the mechanical
# backstop the soft prompt nudge lacks (a --resume'd session can ignore it).
DM_TIMEOUT_S = float(os.environ.get("DM_TIMEOUT_S", "150"))


def _http_post_json(url: str, payload: dict, timeout: float = 310) -> dict:
    """POST JSON, return parsed JSON. The single seam tests patch."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8", "replace") or "{}")


def _tg(method: str, params: dict, timeout: float = 35) -> dict:
    return _http_post_json(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", params, timeout)


def _send_message(params: dict) -> dict:
    """sendMessage with a 4xx caught and RETURNED (not raised) as an error dict.

    `_http_post_json` wraps `urlopen`, which raises `HTTPError` on a 4xx — a bare
    `<`/`>`/`&` slipping past escaping would then 400 and, unhandled, crash the
    reply. Returning `{"ok": False, "error_code": N}` instead lets `send_reply`
    detect the failure and retry as plain text — and makes a real 400 look
    identical to a test's canned error dict."""
    try:
        return _tg("sendMessage", params)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error_code": exc.code}


def tg_send(text: str, chat_id: str | None = None, parse_mode: str | None = None) -> dict:
    """Send text to a chat (default the configured operator chat). `parse_mode` is
    opt-in: default None keeps the zero-risk PLAIN-TEXT path (the HTML-400 dodge);
    only the report path passes parse_mode='HTML' (with strictly escaped values)."""
    params = {"chat_id": chat_id or DEFAULT_CHAT, "text": text}
    if parse_mode is not None:
        params["parse_mode"] = parse_mode
    return _send_message(params)


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


_ROW_CAP = 10   # rows shown per table before a "+N more" footer


def _humanize(key: str) -> str:
    """`top_attacker_ips` -> `Top attacker ips` — a readable section header."""
    return str(key).replace("_", " ").strip().capitalize()


def _wrap_pre(body: str) -> str:
    """The ONLY producer of `<pre>` markup. `body` is already fully html-escaped;
    the tags are the sole literal `<`/`>` in any rendered report — which is what
    lets the sender detect 'this is an HTML report' by a `<pre>` substring test."""
    return f"<pre>{body}</pre>"


def _esc(v) -> str:
    """A scalar cell/line, HTML-escaped. Non-scalars (a nested dict/list buried
    inside a row cell) compact to single-line JSON first, then escape — a leaf,
    never a nested table."""
    if isinstance(v, (dict, list)):
        v = json.dumps(v, separators=(",", ":"), ensure_ascii=False)
    return html.escape(str(v), quote=False)


def _fmt_table(rows: list[dict]) -> str:
    """Aligned monospace column table body (no `<pre>` wrapper — the caller wraps).

    Columns are the UNION of keys across rows in first-seen order (a key appearing
    only in a later row is appended). Missing key -> blank cell (never the literal
    `None`). All cells are html-escaped. Capped at _ROW_CAP data rows with a
    `+N more` footer; column widths are computed AFTER the cap so the footer never
    widens the table. A column whose every present cell is numeric is right-aligned."""
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)

    shown = rows[:_ROW_CAP]
    extra = len(rows) - len(shown)

    def cell(r: dict, c: str) -> str:
        return _esc(r[c]) if c in r else ""

    numeric = {
        c: all(
            isinstance(r.get(c), bool) is False and isinstance(r.get(c), (int, float))
            for r in shown if c in r
        ) and any(c in r for r in shown)
        for c in cols
    }
    heads = {c: c.upper() for c in cols}
    widths = {
        c: max([len(heads[c])] + [len(cell(r, c)) for r in shown])
        for c in cols
    }

    def render_row(values: dict) -> str:
        parts = []
        for c in cols:
            val = values[c]
            parts.append(val.rjust(widths[c]) if numeric[c] else val.ljust(widths[c]))
        return "  ".join(parts).rstrip()

    lines = [render_row(heads)]
    lines.append("  ".join("-" * widths[c] for c in cols))
    for r in shown:
        lines.append(render_row({c: cell(r, c) for c in cols}))
    if extra > 0:
        lines.append(f"+{extra} more")
    return "\n".join(lines)


def _is_list_of_dicts(v) -> bool:
    return isinstance(v, list) and len(v) > 0 and all(isinstance(x, dict) for x in v)


def render_report(payload: dict) -> str:
    """Render an agent's domain dict as HTML monospace `<pre>` tables — so the
    operator NEVER sees raw json.dumps. The bridge owns presentation: the
    agent-session server hands the agent's raw JSON result straight through and
    the model routinely writes a domain-shaped object (no `text` field) despite
    the prompt, so a mechanism the model can't override is the only reliable fix.

    Layout per top-level key:
      - scalars (str/int/float/bool/None)  -> one `key  value` line, all grouped
        into a leading summary `<pre>` block;
      - list-of-dicts                      -> a humanized header + a `<pre>` table
        (`_fmt_table`: union-of-keys columns, 10-row cap, +N more);
      - list-of-scalars                    -> header + `<pre>`, one escaped item
        per line (10 + +N more);
      - empty list                         -> a `key  (none)` scalar line;
      - nested dict                        -> header + `<pre>` of one-level-indented
        `key: value` (deeper levels compact to single-line JSON as a leaf).

    Every interpolated value is html-escaped; the `<pre>` tags are the only literal
    markup (see `_wrap_pre`)."""
    if not payload:
        return _wrap_pre("(empty result)")

    scalars: list[str] = []
    blocks: list[str] = []

    def section(key, body: str) -> None:
        blocks.append(f"{html.escape(_humanize(key), quote=False)}\n{_wrap_pre(body)}")

    for k, v in payload.items():
        if isinstance(v, list) and not v:
            scalars.append((k, "(none)"))
        elif _is_list_of_dicts(v):
            section(k, _fmt_table(v))
        elif isinstance(v, list):                       # list of scalars
            shown = v[:_ROW_CAP]
            body = "\n".join(_esc(x) for x in shown)
            if len(v) > len(shown):
                body += f"\n+{len(v) - len(shown)} more"
            section(k, body)
        elif isinstance(v, dict):                       # nested dict, one level
            body = "\n".join(f"  {_esc(kk)}: {_esc(vv)}" for kk, vv in v.items())
            section(k, body)
        else:                                           # scalar
            scalars.append((k, _esc(v)))

    out_blocks: list[str] = []
    if scalars:
        w = max(len(html.escape(str(k), quote=False)) for k, _ in scalars)
        summary = "\n".join(
            f"{html.escape(str(k), quote=False):<{w}}  {val}" for k, val in scalars
        )
        out_blocks.append(_wrap_pre(summary))
    out_blocks.extend(blocks)
    return "\n\n".join(out_blocks)


def render_payload(resp: dict) -> str | None:
    """Human text from an agent-session response, or None if it didn't complete.

    The session-server contract is a JSON file result. The preferred shape is
    {"text": "<compact plain-text table>"} → we return `text`. But the model often
    ignores that and writes a domain-shaped dict with no `text` field; rather than
    leak raw JSON, we render ANY such dict as HTML `<pre>` monospace tables
    (`render_report`). A bare string passes through; a string that parses to a
    dict is handled the same way (unwrap `text`, else report). None when status !=
    ok or payload is empty. A `<pre>` in the return signals HTML to the sender.
    """
    if not resp or resp.get("status") != "ok":
        return None
    payload = resp.get("payload")
    if payload is None:
        return None
    if isinstance(payload, str):
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError):
            return payload                      # genuine plain text
        payload = obj if isinstance(obj, dict) else payload
        if not isinstance(payload, dict):
            return payload                      # non-dict JSON (list/number) — leave as-is
    if isinstance(payload, dict):
        text = payload.get("text")
        return text if isinstance(text, str) else render_report(payload)
    return str(payload)                          # non-str, non-dict (list/number)


_TG_LIMIT = 4096   # Telegram's per-message character ceiling


def _html_to_plain(html_text: str) -> str:
    """Strip `<pre>` markup and unescape entities — the plain-text body for the
    400 fallback. The table's alignment survives (it's just spaces); only the tags
    and escapes go, so a formatting-driven 400 still delivers readable data."""
    stripped = html_text.replace("<pre>", "").replace("</pre>", "")
    return html.unescape(stripped)


def _split_for_telegram(html_text: str, limit: int = _TG_LIMIT) -> list[str]:
    """Split a rendered HTML report into parts each ≤ `limit`, never cutting inside
    a `<pre>` tag. Splits on blank-line block boundaries; a single `<pre>` block
    whose body alone exceeds the limit is split on WHOLE ROWS, each fragment
    re-wrapped in `<pre>...</pre>`. >1 part → each gets an `(i/n)` prefix line
    (outside any `<pre>`); a single part gets no prefix.

    The prefix is added AFTER packing, so packing budgets against `limit` with a
    small reserve for the longest possible prefix."""
    blocks = [b for b in html_text.split("\n\n") if b != ""]

    # Explode any oversized <pre> block into row-wise <pre> fragments first.
    exploded: list[str] = []
    for b in blocks:
        if len(b) <= limit or not b.startswith("<pre>"):
            exploded.append(b)
            continue
        rows = b[len("<pre>"):-len("</pre>")].split("\n")
        cur: list[str] = []
        cur_len = len("<pre></pre>")
        for row in rows:
            add = len(row) + 1
            if cur and cur_len + add > limit:
                exploded.append(_wrap_pre("\n".join(cur)))
                cur, cur_len = [], len("<pre></pre>")
            cur.append(row)
            cur_len += add
        if cur:
            exploded.append(_wrap_pre("\n".join(cur)))

    # Pack blocks into parts. Reserve room for an "(nn/nn)\n" prefix.
    reserve = 12
    parts: list[str] = []
    cur = ""
    for b in exploded:
        candidate = b if not cur else f"{cur}\n\n{b}"
        if cur and len(candidate) + reserve > limit:
            parts.append(cur)
            cur = b
        else:
            cur = candidate
    if cur:
        parts.append(cur)
    if not parts:
        return [html_text]
    if len(parts) == 1:
        return parts
    n = len(parts)
    return [f"({i}/{n})\n{p}" for i, p in enumerate(parts, 1)]


def send_reply(resp: dict, chat_id: str | None, fallback) -> None:
    """Post an agent reply, owning HTML-vs-plain routing and the 400 fallback.

    - No completed payload → post `fallback` (a str, or a zero-arg callable invoked
      lazily) as plain text — so a stuck/timed-out turn never silences the channel.
    - An HTML report (the rendered string contains a `<pre>` block — the only
      producer is `render_report`) → split at 4096 on block/row boundaries and post
      each part with parse_mode=HTML; if a part 400s, retry it ONCE as plain text
      (tags stripped, entities unescaped). The 400→plain retry is the non-negotiable
      safety net: a formatting bug can degrade readability but never delivery.
    - A plain narrative → post as-is (no parse_mode)."""
    text = render_payload(resp)
    if text is None:
        text = fallback() if callable(fallback) else fallback
        tg_send(text, chat_id)
        return
    if "<pre>" in text:
        for part in _split_for_telegram(text):
            r = tg_send(part, chat_id, parse_mode="HTML")
            if r.get("ok") is False and r.get("error_code") == 400:
                tg_send(_html_to_plain(part), chat_id)   # one plain retry — never silent
        return
    tg_send(text, chat_id)


def deliver(resp: dict, fallback_text: str, chat_id: str | None = None) -> None:
    """Back-compat shim over `send_reply` (cron digest/surge handlers import it):
    post the agent narrative/report, else the deterministic fallback text."""
    send_reply(resp, chat_id, fallback_text)


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


def _deterministic_snapshot() -> str:
    """A fast, deterministic frank-facts snapshot for the DM fallback — so a slow
    or failed agent turn still returns REAL data, never a bare '(no reply)'. Pure
    stdlib: shells the frank-facts CLI (the same tool the agent uses), defensive on
    any failure. Patched in tests."""
    try:
        # `surge-compute` returns the verdict {tier,current,baseline,ratio};
        # `-m frank_facts.cli` avoids depending on the bin dir being on PATH
        # (frank_facts is on PYTHONPATH=/opt/pylib in the bridge container).
        out = subprocess.run([sys.executable, "-m", "frank_facts.cli", "surge-compute"],
                             capture_output=True, text=True, timeout=20)
        verdict = json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else {}
    except Exception as exc:  # noqa: BLE001 — the fallback must never itself raise
        print(f"WARN telegram-bridge: deterministic snapshot failed: {exc}", file=sys.stderr)
        verdict = {}
    if verdict:
        return ("agent busy — deterministic snapshot: surge "
                f"tier={verdict.get('tier')} current={verdict.get('current')} "
                f"baseline={verdict.get('baseline')} (x{verdict.get('ratio', 0)})")
    return ("the agent is taking too long — try again shortly, or use a slash "
            "command like /status")


def _run_agent_turn(chat_id, message_id, message) -> None:
    """Drive the agent for one turn under the per-session lock, reply, react 👍/🤔.
    The lock serializes same-session turns; the wait spans only session_send so a
    finished turn frees the session immediately. A transport failure OR a timed-out/
    empty turn NEVER kills the thread silently — it posts a deterministic snapshot."""
    react = _react_fn(chat_id, message_id)
    session_id = f"{SESSION_ID}-tg-{chat_id}"
    try:
        with _session_lock(session_id):
            resp = session_send(message, session_id=session_id, timeout_s=DM_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — an HTTP timeout/error must not drop the reply
        print(f"WARN telegram-bridge: session_send failed: {exc}", file=sys.stderr)
        resp = None
    answered = render_payload(resp) is not None
    # pass the snapshot as a CALLABLE so it's computed only when there's no answer
    send_reply(resp, str(chat_id), _deterministic_snapshot)
    react("👍" if answered else "🤔")   # 🤔 = deterministic fallback was posted


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
