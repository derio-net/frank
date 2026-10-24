"""Guard the runner / pc-1 alert rules (spec 2026-10-18 section 7, R19).

Traps pinned here:
- LogsQL series must be scoped to the watcher container and pod (Frank's
  VictoriaLogs field is `_msg`), and must not match `ci-runner-probe-error`.
- uid <= 40 chars (a longer one crash-loops Grafana).
- pc-1 /var is selected by NAME: node_filesystem_* has no node label, so the
  rule joins node_uname_info{nodename="pc-1"} on instance (verified live
  2026-10-18 to return the series, 0.363). A selector on a series that does
  not exist is silent under noDataState OK.
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


UIDS = ("layer-25-runner-offline", "layer-25-runner-queue-wait", "layer-25-runner-probe-blind", "layer-25-pc1-var-low")


def test_uids_fit_grafanas_limit():
    for uid in UIDS:
        assert uid in _rules() and len(uid) <= 40


def test_runner_offline_fires_only_when_every_probe_in_the_window_saw_zero():
    _, r = _rules()["layer-25-runner-offline"]
    q = _q(r)
    expr = q["model"]["expr"]
    assert q["datasourceUid"] == LOGS_DS and q["model"]["queryType"] == "stats"
    assert expr.startswith(SCOPE)
    assert '_msg:"ci-runner-probe runners_online="' in expr
    assert expr.endswith('| extract "runners_online=<n> " | stats max(n) as value')
    assert _threshold(r) == ("lt", 1)
    assert q["relativeTimeRange"]["from"] == 1200  # two 10m probe periods
    assert r["for"] in ("0s", "5m") and r["noDataState"] == "OK"


def test_runner_queue_wait_needs_every_sample_over_900s():
    _, r = _rules()["layer-25-runner-queue-wait"]
    q = _q(r)
    expr = q["model"]["expr"]
    assert q["datasourceUid"] == LOGS_DS and q["model"]["queryType"] == "stats"
    assert expr.startswith(SCOPE)
    assert expr.endswith('| extract "oldest_waiting_s=<age> waiting=" | stats min(age) as value')
    assert _threshold(r) == ("gt", 900)
    assert q["relativeTimeRange"]["from"] == 1200
    assert r["for"] in ("0s", "5m") and r["noDataState"] == "OK"


def test_probe_blind_pages_on_persistent_probe_errors():
    # The watcher logs exactly one of `ci-runner-probe ...` or
    # `ci-runner-probe-error ...` every run (a missing token is an error line
    # too), so error lines persisting is the whole blindness signal; a dead
    # watcher is the heartbeat rule's job.
    _, r = _rules()["layer-25-runner-probe-blind"]
    q = _q(r)
    assert q["datasourceUid"] == LOGS_DS and q["model"]["queryType"] == "stats"
    assert q["model"]["expr"] == SCOPE + ' AND _msg:"ci-runner-probe-error" | stats count() as value'
    assert q["relativeTimeRange"]["from"] == 2400
    assert _threshold(r) == ("gt", 3)
    assert r["noDataState"] == "OK"


def test_pc1_var_low_selects_pc1_by_name_not_by_ip():
    g, r = _rules()["layer-25-pc1-var-low"]
    expr = _q(r)["model"]["expr"]
    assert _q(r)["datasourceUid"] == VM_DS
    assert 'node_filesystem_avail_bytes{mountpoint="/var"}' in expr
    assert 'node_filesystem_size_bytes{mountpoint="/var"}' in expr
    assert '* on(instance) group_left() node_uname_info{nodename="pc-1"}' in expr
    assert "192.168.55" not in expr and "sda4" not in expr
    assert _threshold(r) == ("lt", 0.15)
    assert r["for"] == "15m" and r["labels"]["severity"] == "warning"
    assert r["noDataState"] == "OK"
