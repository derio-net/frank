"""Guard the alert-agent credential-expiry dead-man's-switch alert rule.

Locks the load-bearing shape of the heartbeat-staleness rule embedded in the
grafana-alerting ConfigMap. The single most important pin is the **`_msg` field**:
Frank's VictoriaLogs carries the log message in `_msg`, NOT `log` (the Hop crowdsec
rule uses `log:` because Hop's fluent-bit maps differently — verified live:
`_msg:"..."` matches, `log:"..."` returns 0). A copy-paste of the Hop query would
make this dead-man rule permanently blind (always 0 → always firing / meaningless).
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CM = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
UID = "alert-agent-cred-expiry-heartbeat-stale"


def _find_rule():
    cm = yaml.safe_load(CM.read_text())
    for blob in cm["data"].values():
        doc = yaml.safe_load(blob)
        for grp in doc.get("groups", []):
            for rule in grp.get("rules", []):
                if rule.get("uid") == UID:
                    return rule
    raise AssertionError(f"rule {UID} not found in {CM}")


def test_query_uses_frank_msg_field_not_hop_log_field():
    expr = next(d for d in _find_rule()["data"] if d["refId"] == "A")["model"]["expr"]
    assert '_msg:"cred-expiry-check"' in expr, "Frank VictoriaLogs message field is _msg"
    assert 'log:"cred-expiry-check"' not in expr, "the Hop `log:` field returns 0 on Frank"
    assert "kubernetes.namespace_name:alert-agent" in expr
    assert "stats count() as value" in expr


def test_fires_on_zero_heartbeats_and_is_blind_safe():
    rule = _find_rule()
    c = next(d for d in rule["data"] if d["refId"] == "C")
    cond = c["model"]["conditions"][0]["evaluator"]
    assert cond["type"] == "lt" and cond["params"] == [1]   # fires when heartbeat count < 1
    assert rule["noDataState"] == "OK"                       # VL outage = blind, not dead
    assert rule["labels"]["severity"] == "critical"


def _cadence_s() -> int:
    """Largest gap between consecutive runs of the cred-expiry cron line (wraps midnight)."""
    cron = (REPO / "apps/alert-agent/manifests/files/.crontab").read_text()
    line = next(ln for ln in cron.splitlines()
                if "cred-expiry-check" in ln and not ln.lstrip().startswith("#"))
    hours = sorted(int(h) for h in line.split()[1].split(","))
    gaps = [b - a for a, b in zip(hours, hours[1:])] + [hours[0] + 24 - hours[-1]]
    return max(gaps) * 3600


def test_pages_telegram_directly_and_window_tolerates_one_missed_run():
    rule = _find_rule()
    cadence = _cadence_s()
    # window must span two cadences (one miss tolerated) yet stay well under a day
    # and a half so a dead check is caught the same day (frank#746)
    for d in rule["data"]:
        w = d["relativeTimeRange"]["from"]
        assert 2 * cadence < w < 30 * 3600, f"window {w}s vs cadence {cadence}s"
    # silence is the enemy: this rule pages Telegram directly, not the quiet route
    assert rule["labels"].get("telegram_direct") == "true"
    assert "canary_watchdog" not in rule["labels"]


def test_flap_suppression_and_error_handling_pinned():
    rule = _find_rule()
    assert rule["for"] == "2h"                 # a slightly-late run must not flap
    assert rule["execErrState"] == "Error"     # a query error is surfaced, not hidden
