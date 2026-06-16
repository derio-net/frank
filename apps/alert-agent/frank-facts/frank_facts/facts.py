"""Fact-sheet builders (stdlib-only port of ai-alert-helper/facts.py).

Each function returns a structured dict the agent consumes. The single HTTP seam
is `_http_get` (urllib) — swapped in for httpx so this runs on the image's
system python3 with no third-party deps. Logic + query strings are unchanged.
"""
from __future__ import annotations
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

VICTORIALOGS_URL = os.environ.get(
    "VICTORIALOGS_URL",
    "http://victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local:9428",
)
# In-cluster Service by default: the public counter.cluster.derio.net ingress is
# behind Authentik forward-auth (302s API token requests to SSO). Overridden via env.
GOATCOUNTER_URL = os.environ.get(
    "GOATCOUNTER_URL", "http://goatcounter.goatcounter-system.svc.cluster.local:8080"
)
GOATCOUNTER_TOKEN = os.environ.get("OBS_GOATCOUNTER_API_TOKEN", "")

# Self-controlled UA that Frank's blackbox probes carry; the edge definition
# excludes Frank's own probe identity. MUST match
# apps/blackbox-exporter/manifests/configmap.yaml.
PROBE_UA_TOKEN = "Frank-Blackbox-Probe"


def _http_get(url: str, params: dict | None = None, headers: dict | None = None,
              timeout: float = 15) -> str:
    """GET `url` with query `params` + optional `headers`; return the body text.

    Raises on a non-2xx status (urllib raises HTTPError for >=400) or transport
    error — callers wrap in try/except and fail soft, exactly like the old
    httpx `.raise_for_status()` pattern. This is the single seam the tests patch.
    """
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (in-cluster)
        return resp.read().decode("utf-8", "replace")


def edge_filter(host: str | None = None, *, exclude_probes: bool = True) -> str:
    """Canonical Hop-edge Caddy access-log filter — single source of truth so the
    surge alert, surge narrative, and digest agree on what "blog traffic" is."""
    f = 'kubernetes.host:hop-1 AND _msg:"handled request"'
    if host:
        f += f' AND `request.host`:"{host}"'
    if exclude_probes:
        f += f' AND -`request.headers.User-Agent`:"{PROBE_UA_TOKEN}"'
    return f


def _logsql_count(query: str) -> int:
    """`... | stats count() as c` → integer count. 0 on any error."""
    try:
        body = _http_get(f"{VICTORIALOGS_URL}/select/logsql/stats_query",
                         params={"query": query})
        result = json.loads(body).get("data", {}).get("result", [])
        if not result:
            return 0
        return int(result[0]["value"][1])
    except Exception:  # noqa: BLE001 — fact builders must not crash callers
        return 0


def _logsql_group(query: str, label: str, top: int | None = None) -> list[dict]:
    """`... | stats by (<label>) count() as c` → [{label: val, count: int}], desc."""
    try:
        body = _http_get(f"{VICTORIALOGS_URL}/select/logsql/stats_query",
                         params={"query": query})
        result = json.loads(body).get("data", {}).get("result", [])
    except Exception:  # noqa: BLE001
        return []
    rows = [
        {label: r["metric"].get(label, ""), "count": int(r["value"][1])}
        for r in result
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:top] if top else rows


def _goatcounter_raw(path: str, params: dict) -> dict | None:
    """GET a GoatCounter /api/v0 endpoint with Bearer auth.

    `None` when GoatCounter is unreachable/errors — so the surge cross-check can
    distinguish "down" from "genuinely zero". `_goatcounter` coerces None to {}.
    """
    if not GOATCOUNTER_TOKEN:
        return None
    try:
        body = _http_get(f"{GOATCOUNTER_URL}{path}", params=params,
                         headers={"Authorization": f"Bearer {GOATCOUNTER_TOKEN}"})
        return json.loads(body)
    except Exception:  # noqa: BLE001
        return None


def _goatcounter(path: str, params: dict) -> dict:
    """GET a GoatCounter /api/v0 endpoint. {} on error/empty (digest back-compat)."""
    return _goatcounter_raw(path, params) or {}


def surge_visitor_pageviews(window_start: datetime, window_end: datetime) -> int | None:
    """Human pageviews (GoatCounter) in the surge window. None when unreachable."""
    data = _goatcounter_raw(
        "/api/v0/stats/total",
        {
            "start": window_start.replace(minute=0, second=0, microsecond=0).isoformat(),
            "end": window_end.replace(minute=0, second=0, microsecond=0).isoformat(),
        },
    )
    return None if data is None else int(data.get("total", 0))


def _digest_blog_facts(since: datetime, until: datetime) -> dict:
    """Blog reader metrics from GoatCounter for the calendar day [since, until)."""
    window = {"start": since.date().isoformat(), "end": until.date().isoformat()}
    total = _goatcounter("/api/v0/stats/total", window)
    hits = _goatcounter("/api/v0/stats/hits", {**window, "limit": 10})
    refs = _goatcounter("/api/v0/stats/toprefs", {**window, "limit": 10})
    return {
        "blog_pageviews": int(total.get("total", 0)),
        "blog_top_pages": [
            {"path": h.get("path", ""), "count": int(h.get("count", 0))}
            for h in hits.get("hits", [])
        ],
        "blog_top_referrers": [
            {"name": r.get("name") or "direct", "count": int(r.get("count", 0))}
            for r in refs.get("stats", [])
        ],
    }


def _digest_security_facts(since: datetime, security_until: datetime) -> dict:
    """Falco (all priorities) + CrowdSec over [since, security_until)."""
    sw = f"_time:[{since.isoformat()},{security_until.isoformat()}]"
    by_priority = _logsql_group(
        f"{sw} source:syscall | stats by (priority) count() as c", "priority"
    )
    top_rules = _logsql_group(
        f"{sw} source:syscall | stats by (rule) count() as c", "rule", top=5
    )
    critical_rules = _logsql_group(
        f"{sw} source:syscall AND priority:Critical | stats by (rule) count() as c",
        "rule", top=5,
    )
    return {
        "falco_by_priority": [
            {"priority": r["priority"], "count": r["count"]} for r in by_priority
        ],
        "falco_top_rules": [{"rule": r["rule"], "count": r["count"]} for r in top_rules],
        "falco_critical_rules": [
            {"rule": r["rule"], "count": r["count"]} for r in critical_rules
        ],
        "crowdsec_decisions": _logsql_count(
            f"{sw} kubernetes.namespace_name:crowdsec-system "
            f"AND log:Adding AND log:decisions | stats count() as c"
        ),
        "scan_pattern_counts": scan_pattern_counts(since, security_until),
        "top_attacker_ips": top_attacker_ips(since, security_until, top=5),
        "crowdsec_activity": crowdsec_activity(since, security_until),
    }


def build_for_digest(since: datetime, until: datetime, security_until: datetime) -> dict:
    """Daily digest fact sheet. Traffic = calendar day [since, until); security =
    [since, security_until) so an overnight Critical surfaces same-day."""
    tw = f"_time:[{since.isoformat()},{until.isoformat()}]"
    edge = f"{tw} {edge_filter()}"
    by_vhost = _logsql_group(f"{edge} | stats by (request.host) count() as c", "request.host", top=10)
    by_status = _logsql_group(f"{edge} | stats by (status) count() as c", "status")
    status_class: dict[str, int] = {}
    for row in by_status:
        cls = (str(row["status"])[:1] or "?") + "xx"
        status_class[cls] = status_class.get(cls, 0) + row["count"]
    sheet = {
        "traffic_window": {"since": since.isoformat(), "until": until.isoformat()},
        "security_window": {"since": since.isoformat(), "until": security_until.isoformat()},
        "edge_requests_total": _logsql_count(f"{edge} | stats count() as c"),
        "edge_requests_by_vhost": [{"host": r["request.host"], "count": r["count"]} for r in by_vhost],
        "edge_requests_by_status_class": status_class,
    }
    sheet.update(_digest_blog_facts(since, until))
    sheet.update(_digest_security_facts(since, security_until))
    return sheet


def _bare_ua(v: str) -> str:
    """Strip VictoriaLogs' bracketed-array wrapper: `["<ua>"]` -> `<ua>`."""
    v = v.strip()
    if v.startswith('["') and v.endswith('"]'):
        return v[2:-2]
    return v


def build_for_surge(window_start: datetime, window_end: datetime) -> dict:
    """Surge fact sheet — counts + top referrers/paths/user-agents for the window."""
    window = f"_time:[{window_start.isoformat()},{window_end.isoformat()}]"
    ef = edge_filter(host="blog.derio.net")
    gcw = {
        "start": window_start.replace(minute=0, second=0, microsecond=0).isoformat(),
        "end": window_end.replace(minute=0, second=0, microsecond=0).isoformat(),
    }
    refs = _goatcounter("/api/v0/stats/toprefs", {**gcw, "limit": 5})
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "total_requests": _logsql_count(f"{window} {ef} | stats count() as c"),
        "top_paths": [
            {"path": r["request.uri"], "count": r["count"]}
            for r in _logsql_group(f"{window} {ef} | stats by (request.uri) count() as c", "request.uri", top=5)
        ],
        "top_user_agents": [
            {"ua": _bare_ua(r["request.headers.User-Agent"]), "count": r["count"]}
            for r in _logsql_group(f"{window} {ef} | stats by (request.headers.User-Agent) count() as c", "request.headers.User-Agent", top=5)
        ],
        "top_referrers": [
            {"name": r.get("name") or "direct", "count": int(r.get("count", 0))}
            for r in refs.get("stats", [])
        ],
    }


# Classic scan-probe paths. Grouped, not exhaustive. Keep in sync with the SKILL playbook.
SCAN_PROBE_PATHS = [
    "/wp-login.php", "/xmlrpc.php", "/.env", "/.git/config", "/wp-admin",
    "/phpmyadmin", "/admin", "/.aws/credentials", "/config.json", "/backup",
]


def _window(since: datetime, until: datetime) -> str:
    return f"_time:[{since.isoformat()},{until.isoformat()}]"


def _error_edge(since: datetime, until: datetime) -> str:
    """Edge filter scoped to client errors — shared so the attacker/scan aggs can't drift."""
    return f'{_window(since, until)} {edge_filter()} AND status:~"4.."'


def scan_pattern_counts(since: datetime, until: datetime) -> list[dict]:
    """Hit counts for the classic probe paths, probe-excluded, desc-sorted."""
    uri_filter = " OR ".join(f'`request.uri`:"{p}"' for p in SCAN_PROBE_PATHS)
    q = f"{_window(since, until)} {edge_filter()} AND ({uri_filter}) | stats by (request.uri) count() as c"
    return [{"path": r["request.uri"], "count": r["count"]} for r in _logsql_group(q, "request.uri")]


def top_attacker_ips(since: datetime, until: datetime, top: int = 10) -> list[dict]:
    """IPs behind the 4xx noise (`request.client_ip`, trusted-proxy aware)."""
    q = f"{_error_edge(since, until)} | stats by (request.client_ip) count() as c"
    return [{"ip": r["request.client_ip"], "count": r["count"]} for r in _logsql_group(q, "request.client_ip", top=top)]


def top_scanned_paths(since: datetime, until: datetime, top: int = 10) -> list[dict]:
    """Most-probed paths across all 4xx traffic."""
    q = f"{_error_edge(since, until)} | stats by (request.uri) count() as c"
    return [{"path": r["request.uri"], "count": r["count"]} for r in _logsql_group(q, "request.uri", top=top)]


_BLOCKLIST_RE = re.compile(
    r'time="(?P<time>[^"]+)".*community-blocklist : added (?P<added>\d+) entries, '
    r"deleted (?P<deleted>\d+) entries"
)


def crowdsec_activity(since: datetime, until: datetime, limit: int = 200) -> dict:
    """CrowdSec activity from VictoriaLogs (Hop's LAPI is unreachable from Frank).
    Blocklist syncs are parsed; any OTHER line is passed through raw (an
    unrecognized line is the story — never guess against an unobserved format)."""
    q = (
        f"{_window(since, until)} kubernetes.namespace_name:crowdsec-system "
        f"AND (log:alert OR log:decision OR log:ban) "
        f"| sort by (_time desc) | limit {limit}"
    )
    try:
        text = _http_get(f"{VICTORIALOGS_URL}/select/logsql/query", params={"query": q})
        raw_lines = text.splitlines()
    except Exception:  # noqa: BLE001 — fail-soft like every fact builder
        return {"blocklist_syncs": [], "other_lines": []}
    lines = []
    for l in raw_lines:  # per-line fault isolation
        if not l.strip():
            continue
        try:
            lines.append(json.loads(l))
        except ValueError:
            continue
    syncs, other = [], []
    for entry in lines:
        log = entry.get("log", "")
        m = _BLOCKLIST_RE.search(log)
        if m:
            syncs.append({"time": m.group("time"), "added": int(m.group("added")),
                          "deleted": int(m.group("deleted"))})
        else:
            other.append(log[:300])
    return {"blocklist_syncs": syncs, "other_lines": other[:20]}


def build_for_alert(alert: dict) -> dict:
    """Dispatch to an alert-type-specialised fact sheet based on alertname."""
    name = alert.get("alertname", "")
    sheet: dict = {"alertname": name}
    if "CrowdSec" in name:
        sheet["decisions_in_window"] = _logsql_count(
            '_time:5m kubernetes.namespace_name:crowdsec-system AND log:Adding AND log:decisions | stats count() as c'
        )
    elif "Falco" in name:
        sheet["events_in_window"] = _logsql_count(
            '_time:5m source:syscall AND priority:Critical | stats count() as c'
        )
    return sheet
