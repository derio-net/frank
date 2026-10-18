"""Guard the runner / pc-1 alert rules (spec 2026-10-18 section 7, R19).

Traps pinned here:
- LogsQL series must be scoped to the watcher container and pod (Frank's
  VictoriaLogs field is `_msg`), and must not match `ci-runner-probe-error`.
- uid <= 40 chars (a longer one crash-loops Grafana).
- pc-1 /var is identified by the labels observed live 2026-10-18: node-exporter
  has no node label, so the identity is instance 192.168.55.71:9100,
  mountpoint /var, device /dev/sda4. A selector on a series that does not exist
  is silent under noDataState OK.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
RULES_CM = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
LOGS_DS = "affdoo4s9258gc"
VM_DS = "P4169E866C3094E38"
SCOPE = "kubernetes.namespace_name:tekton-pipelines AND kubernetes.container_name:watcher AND kubernetes.pod_name:ci-budget-watcher*"


def _rules():
    doc = yaml.safe_load(yaml.safe_load(RULES_CM.read_text())["data"]["alert-rules.yaml"])
    return {r["uid"]: (g, r) for g in doc["groups"] for r in g["rules"]}


def _q(rule, ref="A"):
    return next(d for d in rule["data"] if d["refId"] == ref)


def _threshold(rule):
    ev = _q(rule, "C")["model"]["conditions"][0]["evaluator"]
    return ev["type"], ev["params"][0]


def test_uids_fit_grafanas_limit():
    for uid in ("layer-25-runner-offline", "layer-25-runner-queue-wait", "layer-25-pc1-var-low"):
        assert uid in _rules() and len(uid) <= 40


def test_runner_offline_is_scoped_and_counts_zero_online_probes():
    _, r = _rules()["layer-25-runner-offline"]
    q = _q(r)
    assert q["datasourceUid"] == LOGS_DS and q["model"]["queryType"] == "stats"
    assert q["model"]["expr"].startswith(SCOPE)
    assert '_msg:"ci-runner-probe runners_online=0 "' in q["model"]["expr"]
    assert q["model"]["expr"].endswith("| stats count() as value")
    assert _threshold(r) == ("gt", 0)
    assert r["for"] == "10m" and r["noDataState"] == "OK"


def test_runner_queue_wait_extracts_oldest_wait_over_900s():
    _, r = _rules()["layer-25-runner-queue-wait"]
    q = _q(r)
    expr = q["model"]["expr"]
    assert q["datasourceUid"] == LOGS_DS and q["model"]["queryType"] == "stats"
    assert expr.startswith(SCOPE)
    assert 'extract "oldest_waiting_s=<age> waiting="' in expr
    assert expr.endswith("| stats max(age) as value")
    assert "ci-runner-probe-error" not in expr
    assert _threshold(r) == ("gt", 900)
    assert r["for"] == "10m" and r["noDataState"] == "OK"


def test_pc1_var_low_uses_the_observed_labels():
    g, r = _rules()["layer-25-pc1-var-low"]
    expr = _q(r)["model"]["expr"]
    sel = '{instance="192.168.55.71:9100",mountpoint="/var"}'
    assert _q(r)["datasourceUid"] == VM_DS
    assert f"node_filesystem_avail_bytes{sel}" in expr and f"node_filesystem_size_bytes{sel}" in expr
    assert _threshold(r) == ("lt", 0.15)
    assert r["for"] == "15m" and r["labels"]["severity"] == "warning"
    assert r["noDataState"] == "OK"
