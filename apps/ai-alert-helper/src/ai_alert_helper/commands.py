"""Slash-command layer: parse, run, format.

Commands bypass the LLM entirely — deterministic dispatch over tools.TOOLS,
so the query path works even when gpu-1 is saturated or down. Everything
renders from the registry: /help, /tools, and Telegram's setMyCommands all
read tools.TOOLS, so the surfaces cannot drift from the code.
"""
from __future__ import annotations

import json

from . import tools

# Telegram message limit is 4096; leave headroom for the pre-block wrapper.
MAX_REPLY_CHARS = 3500

_META = {
    "help": "list all commands with usage",
    "tools": "list the analyst's query tools",
    "reset": "clear the conversation history",
}


def parse_command(text: str) -> dict | None:
    """None for plain questions (LLM path); a command dict for /commands."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return None
    head, _, tail = text[1:].partition(" ")
    head = head.split("@", 1)[0]  # strip @botname suffix Telegram appends in groups
    if head in ("help", "start"):
        return {"kind": "help"}
    if head == "tools":
        return {"kind": "tools"}
    if head == "reset":
        return {"kind": "reset"}
    name = "logsql_query" if head == "logsql" else head
    tool = tools.TOOLS.get(name)
    if tool is None:
        return {"kind": "error", "text": f"unknown command /{head} — try /help"}
    if name == "logsql_query":
        # raw tail IS the query — no tokenization (LogsQL contains spaces/pipes)
        args: dict = {"query": tail.strip()} if tail.strip() else {}
        explain = False
    else:
        tokens = tail.split() if tail else []
        explain = bool(tokens) and tokens[-1] == "explain"
        if explain:
            tokens = tokens[:-1]
        args = {}
        positional = [k for k in tool["required"] if k not in args]
        extras = [k for k in tool["properties"] if k not in tool["required"]]
        order = positional + extras
        pos_i = 0
        for tok in tokens:
            if "=" in tok:
                k, _, v = tok.partition("=")
                args[k] = v
            elif pos_i < len(order):
                args[order[pos_i]] = tok
                pos_i += 1
            else:
                return {"kind": "error",
                        "text": f"too many args. Usage: {tool['usage']}"}
    missing = [r for r in tool["required"] if r not in args]
    if missing:
        return {"kind": "error",
                "text": f"missing {', '.join(missing)}. Usage: {tool['usage']}"}
    return {"kind": "tool", "name": name, "args": args, "explain": explain}


def render_help() -> str:
    lines = ["Analyst commands (no LLM — these work even when the GPU is busy):"]
    lines += [f"  {t['usage']}" for t in tools.TOOLS.values()]
    lines += [f"  /{name} — {desc}" for name, desc in _META.items() if name != "help"]
    lines.append("  /help — this text")
    lines.append("Append 'explain' to any tool command for an LLM narration.")
    lines.append("Plain (non-/) messages go to the analyst LLM.")
    return "\n".join(lines)


def render_tools() -> str:
    return "\n".join(
        f"{name}: {t['description']}\n  {t['usage']}" for name, t in tools.TOOLS.items()
    )


def bot_commands() -> list[dict]:
    """BotCommand list for Telegram setMyCommands — straight from the registry."""
    cmds = [
        {"command": name, "description": t["description"][:256]}
        for name, t in tools.TOOLS.items()
    ]
    cmds += [{"command": name, "description": desc[:256]} for name, desc in _META.items()]
    return cmds


def format_result(result: dict) -> str:
    """Compact fixed-width rendering of a tool result, bounded for Telegram."""
    rows = result.get("rows") if isinstance(result, dict) else None
    if isinstance(rows, list):
        if not rows:
            return "no results"
        keys = list(rows[0].keys())
        widths = {k: max(len(str(k)), *(len(str(r.get(k, ""))) for r in rows)) for k in keys}
        lines = ["  ".join(str(k).ljust(widths[k]) for k in keys)]
        for r in rows:
            lines.append("  ".join(str(r.get(k, "")).ljust(widths[k]) for k in keys))
        extra = {k: v for k, v in result.items() if k != "rows"}
        if extra:
            lines.append(json.dumps(extra))
        text = "\n".join(lines)
    else:
        text = json.dumps(result, indent=1, default=str)
    if len(text) > MAX_REPLY_CHARS:
        text = text[: MAX_REPLY_CHARS - 15] + "\n…(truncated)"
    return text


def run_command(cmd: dict) -> dict:
    """Execute a parsed command → {"text": str, "pre": bool}. Never raises."""
    kind = cmd["kind"]
    if kind == "help":
        return {"text": render_help(), "pre": False}
    if kind == "tools":
        return {"text": render_tools(), "pre": False}
    if kind == "error":
        return {"text": cmd["text"], "pre": False}
    if kind == "reset":
        return {"text": "history cleared", "pre": False}
    try:
        result = tools.dispatch(cmd["name"], cmd["args"])
    except tools.ToolError as e:
        return {"text": str(e), "pre": False}
    except Exception as e:  # noqa: BLE001 — user-facing, never a traceback
        return {"text": f"couldn't complete: {type(e).__name__}", "pre": False}
    return {"text": format_result(result), "pre": True, "result": result}
