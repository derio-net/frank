"""Guard the CrowdSec canary dead-man's-switch alert rule.

The rule lives embedded as a YAML string inside the grafana-alerting ConfigMap.
This loads the ConfigMap, parses the embedded provisioning YAML, and locks the
heartbeat-staleness rule's load-bearing shape: VictoriaLogs stats query (wide
series), a `lt 1` threshold (fires when the heartbeat count drops to zero), and
noDataState OK (a datasource outage must not be mistaken for canary death).
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CM = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
UID = "crowdsec-canary-heartbeat-stale"


def _find_rule():
    cm = yaml.safe_load(CM.read_text())
    for blob in cm["data"].values():
        doc = yaml.safe_load(blob)
        for grp in doc.get("groups", []):
            for rule in grp.get("rules", []):
                if rule.get("uid") == UID:
                    return rule
    raise AssertionError(f"rule {UID} not found in {CM}")


def test_rule_exists_and_uses_victorialogs_stats():
    rule = _find_rule()
    a = next(d for d in rule["data"] if d["refId"] == "A")
    assert a["model"]["queryType"] == "stats", "VictoriaLogs alert must use queryType stats (wide series)"
    assert "stats count() as value" in a["model"]["expr"]
    assert "crowdsec-system" in a["model"]["expr"]


def test_rule_fires_on_zero_heartbeats_and_is_blind_safe():
    rule = _find_rule()
    c = next(d for d in rule["data"] if d["refId"] == "C")
    cond = c["model"]["conditions"][0]["evaluator"]
    assert cond["type"] == "lt" and cond["params"] == [1], "must fire when heartbeat count < 1"
    # A VictoriaLogs outage must read as 'blind', not 'canary dead'.
    assert rule["noDataState"] == "OK"
    assert rule["labels"]["severity"] == "critical"
