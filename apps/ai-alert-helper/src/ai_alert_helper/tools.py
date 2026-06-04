"""Curated tool registry for the analyst.

Six read-only tools over VictoriaLogs: five purpose-built wrappers around the
facts.py query layer plus a guarded LogsQL escape hatch. The registry is the
single source for everything tool-shaped — OpenAI tool schemas for the LLM
loop, usage lines for /help, and Telegram's setMyCommands list all render
from TOOLS, so they cannot drift.

Hard caps live in dispatch(), OUTSIDE the per-tool code and outside the
model's control: ≤MAX_ROWS rows and ≤MAX_BYTES serialized bytes per call.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import httpx

from . import facts

MAX_ROWS = 50
MAX_BYTES = 4096
LOGSQL_MAX_LIMIT = 200


class ToolError(Exception):
    """Validation or execution error meant to be shown to the user verbatim."""


_WINDOW_RE = re.compile(r"^(\d+)([mhd])$")
_WINDOW_UNITS = {"m": "minutes", "h": "hours", "d": "days"}
_WINDOW_MAX = timedelta(days=30)  # VictoriaLogs retention


def parse_window(s: str) -> timedelta:
    m = _WINDOW_RE.match(s or "")
    if not m:
        raise ToolError(f"bad window {s!r} — use e.g. 30m, 6h, 2d")
    td = timedelta(**{_WINDOW_UNITS[m.group(2)]: int(m.group(1))})
    if td <= timedelta(0) or td > _WINDOW_MAX:
        raise ToolError(f"window {s!r} out of range (retention is 30d)")
    return td


def _window_bounds(window: str) -> tuple[datetime, datetime]:
    until = datetime.now(timezone.utc)
    return until - parse_window(window), until


_GROUP_FIELDS = {
    "host": "request.host",
    "path": "request.uri",
    "ua": "request.headers.User-Agent",
    "status": "status",
    "ip": "request.client_ip",
}


def _edge_traffic(window: str, group_by: str = "host",
                  host: str | None = None, status_class: str | None = None) -> dict:
    if group_by not in _GROUP_FIELDS:
        raise ToolError(f"group_by must be one of {sorted(_GROUP_FIELDS)}")
    since, until = _window_bounds(window)
    field = _GROUP_FIELDS[group_by]
    flt = f"{facts._window(since, until)} {facts.edge_filter(host=host)}"
    if status_class:
        if not re.match(r"^[1-5]xx$", status_class):
            raise ToolError("status_class must look like 4xx")
        flt += f' AND status:~"{status_class[0]}.."'
    rows = facts._logsql_group(f"{flt} | stats by ({field}) count() as c", field)
    out = [{group_by: facts._bare_ua(r[field]) if group_by == "ua" else r[field],
            "count": r["count"]} for r in rows]
    return {"rows": out}


def _attacker_profile(ip: str, window: str = "24h") -> dict:
    since, until = _window_bounds(window)
    base = (f"{facts._window(since, until)} {facts.edge_filter()} "
            f'AND `request.client_ip`:"{ip}"')
    paths = facts._logsql_group(f"{base} | stats by (request.uri) count() as c",
                                "request.uri", top=15)
    statuses = facts._logsql_group(f"{base} | stats by (status) count() as c", "status")
    uas = facts._logsql_group(
        f"{base} | stats by (request.headers.User-Agent) count() as c",
        "request.headers.User-Agent", top=5)
    seen = {}
    for label, order in (("first_seen", "asc"), ("last_seen", "desc")):
        try:
            resp = httpx.get(
                f"{facts.VICTORIALOGS_URL}/select/logsql/query",
                params={"query": f"{base} | sort by (_time {order}) | limit 1"},
                timeout=15)
            resp.raise_for_status()
            line = resp.text.strip().splitlines()
            seen[label] = json.loads(line[0]).get("_time") if line else None
        except Exception:  # noqa: BLE001 — profile stays useful without timestamps
            seen[label] = None
    return {
        "ip": ip,
        "total": sum(r["count"] for r in statuses),
        "paths": [{"path": r["request.uri"], "count": r["count"]} for r in paths],
        "status_mix": [{"status": r["status"], "count": r["count"]} for r in statuses],
        "user_agents": [{"ua": facts._bare_ua(r["request.headers.User-Agent"]),
                         "count": r["count"]} for r in uas],
        **seen,
    }


def _falco_events(window: str, priority: str | None = None, rule: str | None = None) -> dict:
    since, until = _window_bounds(window)
    flt = f"{facts._window(since, until)} source:syscall"
    if priority:
        flt += f' AND priority:"{priority}"'
    if rule:
        flt += f' AND rule:"{rule}"'
    by_rule = facts._logsql_group(f"{flt} | stats by (rule) count() as c", "rule", top=15)
    by_priority = facts._logsql_group(
        f"{flt} | stats by (priority) count() as c", "priority")
    return {
        "by_priority": [{"priority": r["priority"], "count": r["count"]} for r in by_priority],
        "by_rule": [{"rule": r["rule"], "count": r["count"]} for r in by_rule],
    }


def _crowdsec_decisions(window: str) -> dict:
    since, until = _window_bounds(window)
    return facts.crowdsec_activity(since, until)


def _scan_patterns(window: str) -> dict:
    since, until = _window_bounds(window)
    return {"rows": facts.scan_pattern_counts(since, until)}


def _logsql_query(query: str, limit: int = 50) -> dict:
    """Escape hatch. Guards: a `_time:` filter is required (unbounded scans are
    never what anyone wants), the row limit is clamped, and the HTTP layer only
    ever calls /select/* — the read-only guarantee lives there, not in parsing."""
    # Check for _time: OUTSIDE quoted strings — `foo:"_time:1h"` is a phrase
    # match, not a time filter, and would otherwise smuggle an unbounded
    # 30d scan past the guard (review finding, 2026-06-05).
    unquoted = re.sub(r'"[^"]*"', '""', query)
    if "_time:" not in unquoted:
        raise ToolError("query must contain a _time: filter (e.g. _time:1h)")
    limit = max(1, min(int(limit), LOGSQL_MAX_LIMIT))
    try:
        if "| stats" in query:
            resp = httpx.get(
                f"{facts.VICTORIALOGS_URL}/select/logsql/stats_query",
                params={"query": query}, timeout=15)
            resp.raise_for_status()
            result = resp.json().get("data", {}).get("result", [])
            rows = [{**r.get("metric", {}), "value": r["value"][1]} for r in result]
            rows = [{k: v for k, v in r.items() if k != "__name__"} for r in rows]
        else:
            resp = httpx.get(
                f"{facts.VICTORIALOGS_URL}/select/logsql/query",
                params={"query": f"{query} | limit {limit}"}, timeout=15)
            resp.raise_for_status()
            rows = []
            for line in resp.text.splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                rows.append({k: str(v)[:200] for k, v in entry.items()
                             if not k.startswith(("_stream", "kubernetes.annotations",
                                                  "kubernetes.labels"))})
    except ToolError:
        raise
    except Exception as e:  # noqa: BLE001 — surfaced to the user, never a traceback
        raise ToolError(f"query failed: {type(e).__name__}") from e
    return {"rows": rows}


TOOLS: dict[str, dict] = {
    "edge_traffic": {
        "fn": _edge_traffic,
        "usage": "/edge_traffic <window> [group_by=host|path|ua|status|ip] [host=<vhost>] [status_class=4xx]",
        "description": "Hop-edge Caddy requests (probe-excluded), grouped. E.g. what hit the blog last hour.",
        "required": ["window"],
        "properties": {
            "window": {"type": "string", "description": "e.g. 1h, 24h, 7d"},
            "group_by": {"type": "string", "enum": sorted(_GROUP_FIELDS)},
            "host": {"type": "string", "description": "vhost filter, e.g. blog.derio.net"},
            "status_class": {"type": "string", "description": "e.g. 4xx"},
        },
    },
    "attacker_profile": {
        "fn": _attacker_profile,
        "usage": "/attacker_profile <ip> [window=24h]",
        "description": "Everything one IP did at the edge: paths, status mix, UAs, first/last seen.",
        "required": ["ip"],
        "properties": {
            "ip": {"type": "string", "description": "client IP to profile"},
            "window": {"type": "string", "description": "e.g. 24h"},
        },
    },
    "falco_events": {
        "fn": _falco_events,
        "usage": "/falco_events <window> [priority=Critical] [rule=<name>]",
        "description": "Falco runtime-security events grouped by priority and rule.",
        "required": ["window"],
        "properties": {
            "window": {"type": "string", "description": "e.g. 12h"},
            "priority": {"type": "string", "description": "e.g. Critical, Warning, Notice"},
            "rule": {"type": "string", "description": "exact Falco rule name"},
        },
    },
    "crowdsec_decisions": {
        "fn": _crowdsec_decisions,
        "usage": "/crowdsec_decisions <window>",
        "description": "CrowdSec activity: blocklist syncs parsed, any other detection lines raw.",
        "required": ["window"],
        "properties": {"window": {"type": "string", "description": "e.g. 24h"}},
    },
    "scan_patterns": {
        "fn": _scan_patterns,
        "usage": "/scan_patterns <window>",
        "description": "Hit counts for classic probe paths (wp-login, xmlrpc, .env, …).",
        "required": ["window"],
        "properties": {"window": {"type": "string", "description": "e.g. 6h"}},
    },
    "logsql_query": {
        "fn": _logsql_query,
        "usage": "/logsql <LogsQL with a _time: filter>",
        "description": "Escape hatch: run any LogsQL (read-only, _time: required, rows capped).",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "LogsQL, must contain _time:"},
            "limit": {"type": "integer", "description": "row cap (clamped to 200)"},
        },
    },
}


def openai_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": t["description"],
                "parameters": {
                    "type": "object",
                    "properties": t["properties"],
                    "required": t["required"],
                },
            },
        }
        for name, t in TOOLS.items()
    ]


def _cap(result: dict) -> dict:
    truncated = False
    rows = result.get("rows")
    if isinstance(rows, list) and len(rows) > MAX_ROWS:
        result = {**result, "rows": rows[:MAX_ROWS]}
        truncated = True
    while len(json.dumps(result)) > MAX_BYTES:
        # Shrink the LARGEST list field, wherever it lives — attacker_profile
        # (paths/status_mix/user_agents), falco_events (by_rule), and
        # crowdsec_decisions (other_lines) have no top-level "rows", and a
        # hard-truncated JSON blob is useless to both the LLM and the
        # operator (review finding, 2026-06-05).
        list_keys = [k for k, v in result.items() if isinstance(v, list) and v]
        if list_keys:
            biggest = max(list_keys, key=lambda k: len(json.dumps(result[k])))
            shrunk = result[biggest][: max(1, len(result[biggest]) // 2)]
            if shrunk == result[biggest]:   # single huge element — last resort
                return {"truncated": True,
                        "result": json.dumps(result)[: MAX_BYTES - 100]}
            result = {**result, biggest: shrunk}
            truncated = True
        else:  # nothing shrinkable — hard-truncate the serialized form
            return {"truncated": True,
                    "result": json.dumps(result)[: MAX_BYTES - 100]}
    if truncated:
        result = {**result, "truncated": True}
    return result


def dispatch(name: str, args: dict) -> dict:
    """Validate args against the registry, run the tool, cap the result."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"unknown tool {name!r} — see /tools")
    for req in tool["required"]:
        if req not in args or args[req] in (None, ""):
            raise ToolError(f"missing required arg {req!r}. Usage: {tool['usage']}")
    unknown = set(args) - set(tool["properties"])
    if unknown:
        raise ToolError(
            f"unknown arg(s) {sorted(unknown)}. Usage: {tool['usage']}")
    return _cap(tool["fn"](**args))
