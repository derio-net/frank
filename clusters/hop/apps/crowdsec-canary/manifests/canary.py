#!/usr/bin/env python3
"""CrowdSec ban-pipeline canary (Hop).

Detects the silent-failure class that bit the Hop pipeline three times in three days
(#583 lost persistence, docker-runtime parse break, #594 rotation-blindness): the agent
stays Running and ArgoCD stays green while the pipeline silently stops banning.

Each run (CronJob, */5) scrapes the agent's :6060/metrics ONCE and compares to the
previous run's persisted sample (cross-run delta over ~5 min — single short scrape keeps
the pod ~5s/run, ~2% duty cycle on the constrained hop-1). Three checks, each mapped to a
historical failure:

  - acquisition  : cs_filesource_hits_total delta == 0          -> rotation-blindness (#594)
  - parsing      : caddy-logs parsed delta == 0 while reads grow -> docker runtime
  - agent_alive  : /metrics unreachable / empty                  -> #583 crashloop

Pages Telegram directly on the 2nd CONSECUTIVE failed run (persisted fail-counter); emits a
`verdict=` heartbeat to stdout every run (fluent-bit -> Frank VictoriaLogs, where a Grafana
dead-man's switch watches for staleness). Telegram creds are OPTIONAL: absent -> heartbeat
only (so the CronJob is healthy before the manual secret phase). Stdlib only (python:3-alpine).
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

METRICS_URL = os.environ.get(
    "METRICS_URL", "http://crowdsec-agent-service.crowdsec-system:6060/metrics"
)
STATE_DIR = os.environ.get("STATE_DIR", "/state")
FAIL_THRESHOLD = int(os.environ.get("FAIL_THRESHOLD", "2"))
SCRAPE_TIMEOUT = float(os.environ.get("SCRAPE_TIMEOUT", "10"))

_LINE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(.+)$')
_KV = re.compile(r'([a-zA-Z0-9_]+)="((?:[^"\\]|\\.)*)"')


def parse_metrics(text):
    """Prometheus text -> {metric_name: [(labels_dict, value), ...]}. Skips #-comments."""
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        name, labelstr, valstr = m.group(1), m.group(2), m.group(3)
        try:
            val = float(valstr.split()[0])  # drop any trailing timestamp
        except ValueError:
            continue
        labels = dict(_KV.findall(labelstr[1:-1])) if labelstr else {}
        out.setdefault(name, []).append((labels, val))
    return out


def extract_signals(metrics):
    """Pull the three load-bearing signals from parsed metrics."""
    filesource = sum(
        v for labels, v in metrics.get("cs_filesource_hits_total", [])
        if "caddy" in labels.get("source", "")
    )
    caddy_parsed = sum(
        v for labels, v in metrics.get("cs_node_hits_ok_total", [])
        if labels.get("name") == "crowdsecurity/caddy-logs"
    )
    return {"filesource": filesource, "caddy_parsed": caddy_parsed, "alive": bool(metrics)}


def evaluate(prev, cur):
    """Compare the current sample to the previous run's. Returns a verdict dict."""
    if prev is None:
        return {"ok": True, "failed_checks": [], "deltas": {}, "bootstrap": True}
    if not cur["alive"]:
        return {"ok": False, "failed_checks": ["agent_alive"], "deltas": {}}
    fs_delta = cur["filesource"] - prev.get("filesource", 0)
    parsed_delta = cur["caddy_parsed"] - prev.get("caddy_parsed", 0)
    if fs_delta < 0 or parsed_delta < 0:
        # A NEGATIVE delta means a cumulative counter went backwards: the agent
        # restarted (counters reset to 0) or the Caddy pod rolled (new container-id
        # -> new source path -> this run's sum starts low). That is a re-baseline,
        # NOT a frozen pipeline -> return OK so a benign restart never pages.
        return {
            "ok": True, "failed_checks": [], "reset": True,
            "deltas": {"filesource": fs_delta, "caddy_parsed": parsed_delta},
        }
    failed = []
    if fs_delta <= 0:
        # no new lines read at all while the blog edge is always being probed -> acquisition hung
        failed.append("acquisition")
    elif parsed_delta <= 0:
        # lines read but none parsed as Caddy -> parser/runtime break
        failed.append("parsing")
    return {
        "ok": not failed,
        "failed_checks": failed,
        "deltas": {"filesource": fs_delta, "caddy_parsed": parsed_delta},
    }


def update_gate(fail_count, ok, threshold=None):
    """Consecutive-fail gate: page only on the Nth straight failure."""
    threshold = FAIL_THRESHOLD if threshold is None else threshold
    if ok:
        return 0, False
    n = fail_count + 1
    return n, n >= threshold


def build_message(verdict, fail_count):
    """Plain-text Telegram body. No < > & (the documented Telegram HTML-400 silent-drop)."""
    d = verdict.get("deltas", {})
    checks = ", ".join(verdict.get("failed_checks", [])) or "unknown"
    return (
        "CrowdSec ban-pipeline canary FAIL on Hop "
        f"(consecutive run {fail_count}/{FAIL_THRESHOLD}).\n"
        f"Failed checks: {checks}.\n"
        f"filesource_delta={d.get('filesource', 'n/a')} "
        f"caddy_parsed_delta={d.get('caddy_parsed', 'n/a')}.\n"
        "The pipeline may be silently not banning. "
        "Check crowdsec-system: agent /metrics, filesource vs caddy delta."
    )


def telegram_notify(token, chat_id, text):
    """POST to Telegram (plain text). Missing creds -> skip, return False, never raise."""
    if not token or not chat_id:
        print("crowdsec-ban-canary telegram skipped (no creds)", file=sys.stderr)
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        with urllib.request.urlopen(url, data=data, timeout=SCRAPE_TIMEOUT) as r:
            return r.status == 200
    except Exception as exc:  # noqa: BLE001 - a page failure must not crash the run
        print(f"crowdsec-ban-canary telegram error: {exc}", file=sys.stderr)
        return False


def _state_path():
    return os.path.join(STATE_DIR, "state.json")


def load_state(path=None):
    path = path or _state_path()
    try:
        with open(path) as f:
            s = json.load(f)
        return s.get("signals"), int(s.get("fail_count", 0))
    except (FileNotFoundError, ValueError, KeyError):
        return None, 0


def save_state(signals, fail_count, path=None):
    path = path or _state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"signals": signals, "fail_count": fail_count}, f)
    os.replace(tmp, path)


def scrape(url=METRICS_URL):
    try:
        with urllib.request.urlopen(url, timeout=SCRAPE_TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - unreachable agent == agent-down signal
        print(f"crowdsec-ban-canary scrape error: {exc}", file=sys.stderr)
        return ""


def main():
    text = scrape()
    cur = extract_signals(parse_metrics(text))
    prev, fail_count = load_state()
    verdict = evaluate(prev, cur)
    new_fail, should_page = update_gate(fail_count, verdict["ok"])

    d = verdict.get("deltas", {})
    ts = datetime.now(timezone.utc).isoformat()
    checks = ",".join(verdict.get("failed_checks", [])) or "none"
    print(
        f"crowdsec-ban-canary verdict={'ok' if verdict['ok'] else 'fail'} "
        f"checks={checks} filesource_delta={d.get('filesource', 'na')} "
        f"caddy_delta={d.get('caddy_parsed', 'na')} fail_count={new_fail} "
        f"bootstrap={verdict.get('bootstrap', False)} ts={ts}"
    )

    if should_page:
        telegram_notify(
            os.environ.get("TELEGRAM_TOKEN"),
            os.environ.get("TELEGRAM_CHATID"),
            build_message(verdict, new_fail),
        )

    save_state(cur, new_fail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
