"""Grafana view + dead-man's switches for the update/security lifecycle (spec R8, R12).

Grafana is NEVER the alarm source: the console raises alarms. Grafana only watches that the
console and the scanners are still producing, and routes to health-bridge, not Telegram.
"""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = ROOT / "apps/grafana-alerting/manifests"
DASH_CM = MANIFESTS / "life-dashboard-cm.yaml"
RULES_CM = MANIFESTS / "alert-rules-cm.yaml"
VM_VALUES = ROOT / "apps/victoria-metrics/values.yaml"
LOGS_DS = "affdoo4s9258gc"
VM_DS = "P4169E866C3094E38"
UIDS = ("life-scan-heartbeat-stale", "life-report-heartbeat-stale", "life-hop-scan-heartbeat-stale",
        "life-hop-scan-unhealthy")


def rules():
    doc = yaml.safe_load(yaml.safe_load(RULES_CM.read_text())["data"]["alert-rules.yaml"])
    return {r["uid"]: (g, r) for g in doc["groups"] for r in g["rules"]}


def q(rule, ref="A"):
    return next(d for d in rule["data"] if d["refId"] == ref)


def dashboard():
    cm = yaml.safe_load(DASH_CM.read_text())
    assert cm["kind"] == "ConfigMap" and cm["metadata"]["namespace"] == "monitoring"
    return cm, json.loads(cm["data"]["life-dashboard.json"])


def exprs(dash):
    return [t["expr"] for p in dash["panels"] for t in p.get("targets", [])]


def test_dashboard_has_the_four_views():
    cm, dash = dashboard()
    assert "life-dashboard-provider.yaml" in cm["data"]
    assert dash["uid"] and dash["title"]
    joined = "\n".join(exprs(dash))
    assert "cluster_update_versions_behind" in joined
    assert "cluster_update_vulns_open" in joined
    assert "trivy_image_vulnerabilities" in joined, "trivy summary metrics (severity)"
    assert "cluster_update_last_report_timestamp_seconds" in joined
    assert "cluster_update_last_scan_timestamp_seconds" in joined
    for p in dash["panels"]:
        for t in p.get("targets", []):
            assert t["datasource"]["uid"] == VM_DS


def test_versions_behind_is_per_cluster_and_vulns_by_severity():
    _, dash = dashboard()
    joined = "\n".join(exprs(dash))
    assert "by (cluster" in joined and "cluster_update_versions_behind" in joined
    assert "by (severity" in joined


def test_dashboard_is_mounted_twice_in_grafana():
    text = VM_VALUES.read_text()
    assert "configMap: grafana-life-dashboard" in text
    cm, _ = dashboard()
    assert cm["metadata"]["name"] == "grafana-life-dashboard"
    assert "mountPath: /etc/grafana/provisioning/dashboards/life-provider.yaml" in text
    assert "mountPath: /var/lib/grafana/dashboards/life/life-dashboard.json" in text
    provider = yaml.safe_load(cm["data"]["life-dashboard-provider.yaml"])
    assert provider["providers"][0]["options"]["path"] == "/var/lib/grafana/dashboards/life"


def test_the_three_dead_mans_switches_exist_in_feature_health():
    r = rules()
    for uid in UIDS:
        assert uid in r, uid
        assert len(uid) <= 40, "a longer uid crash-loops Grafana"
        group, rule = r[uid]
        assert group["folder"] == "feature-health"
        assert rule["noDataState"] and rule["execErrState"]


def test_grafana_is_never_the_alarm_source():
    for uid in UIDS:
        labels = rules()[uid][1]["labels"]
        assert labels.get("health_bridge_only") == "true", "health-bridge only"
        assert "telegram_direct" not in labels
        assert labels["severity"] == "critical"  # drives health-bridge's dead->bug lifecycle


def test_console_metric_rules_stay_loud_when_the_metric_vanishes():
    for uid, metric in (("life-scan-heartbeat-stale", "cluster_update_last_scan_timestamp_seconds"),
                        ("life-report-heartbeat-stale", "cluster_update_last_report_timestamp_seconds")):
        rule = rules()[uid][1]
        a = q(rule)
        assert a["datasourceUid"] == VM_DS
        assert metric in a["model"]["expr"]
        assert "or vector(" in a["model"]["expr"], "absent metric must read as stale, not as NoData"
        ev = q(rule, "C")["model"]["conditions"][0]["evaluator"]
        assert ev["type"] == "gt" and ev["params"][0] >= 36 * 3600  # daily job + slack
        assert rule["noDataState"] == "Alerting"


def test_hop_scan_logs_rule_uses_msg_and_stats():
    rule = rules()["life-hop-scan-heartbeat-stale"][1]
    a = q(rule)
    assert a["datasourceUid"] == LOGS_DS
    assert a["model"]["queryType"] == "stats"
    expr = a["model"]["expr"]
    assert '_msg:"hop-scan heartbeat"' in expr and "log:" not in expr
    assert '_msg:"\\"healthy\\": true"' in expr, "only HEALTHY heartbeats count as alive"
    assert "kubernetes.namespace_name:hop-scan" in expr
    assert expr.rstrip().endswith("| stats count() as value")
    assert a["relativeTimeRange"]["from"] >= 36 * 3600
    ev = q(rule, "C")["model"]["conditions"][0]["evaluator"]
    assert (ev["type"], ev["params"][0]) == ("lt", 1)
    assert rule["noDataState"] == "OK", "blindness is not death"


def test_rules_chain_a_b_c():
    for uid in UIDS:
        rule = rules()[uid][1]
        assert [d["refId"] for d in rule["data"]] == ["A", "B", "C"]
        assert rule["condition"] == "C"
        assert q(rule, "B")["model"]["type"] == "reduce"
        assert q(rule, "C")["model"]["type"] == "threshold"
        assert rule["annotations"]["summary"] and rule["annotations"]["runbook"]


# ---- p3-r3: captured heartbeat lines -------------------------------------------------------
import re  # noqa: E402
import runpy  # noqa: E402
import contextlib  # noqa: E402
import io  # noqa: E402

REPORT = ROOT / "apps/hop-scan/manifests/files/report.py"


def heartbeat(tmp_path, status, images, scanned_ok):
    g = runpy.run_path(str(REPORT))
    tmp_path = tmp_path / f"run{len(list(tmp_path.iterdir()))}"
    tmp_path.mkdir()
    (tmp_path / "results").mkdir(exist_ok=True)
    (tmp_path / "status").write_text(status)
    names = [f"img{i}:1" for i in range(images)]
    (tmp_path / "images.sorted").write_text("\n".join(names) + ("\n" if names else ""))
    for i in range(scanned_ok):
        (tmp_path / "results" / f"{i}.json").write_text('{"Results": []}')
    g["main"].__globals__["WORK"] = str(tmp_path)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        g["main"]()
    (line,) = [l for l in out.getvalue().splitlines() if l.startswith("hop-scan heartbeat ")]
    return line


def phrases(expr):
    """The positive and negated _msg phrases of a LogsQL filter (all we use)."""
    pos, neg = [], []
    for m in re.finditer(r'(NOT )?_msg:"((?:[^"\\]|\\.)*)"', expr):
        (neg if m.group(1) else pos).append(m.group(2).replace('\\"', '"'))
    return pos, neg


def matches(expr, line):
    pos, neg = phrases(expr)
    return all(p in line for p in pos) and not any(n in line for n in neg)


def test_healthy_rule_counts_only_healthy_heartbeats(tmp_path):
    expr = q(rules()["life-hop-scan-heartbeat-stale"][1])["model"]["expr"]
    healthy = heartbeat(tmp_path, "ok", 3, 3)
    skipped = heartbeat(tmp_path, "skipped: no hop-readonly-kubeconfig", 0, 0)
    empty_ok = heartbeat(tmp_path, "ok", 0, 0)
    all_failed = heartbeat(tmp_path, "ok", 3, 0)
    assert matches(expr, healthy)
    for blind in (skipped, empty_ok, all_failed):
        assert not matches(expr, blind), blind


def test_unhealthy_rule_fires_on_blind_heartbeats_only(tmp_path):
    rule = rules()["life-hop-scan-unhealthy"][1]
    expr = q(rule)["model"]["expr"]
    assert q(rule)["datasourceUid"] == LOGS_DS and q(rule)["model"]["queryType"] == "stats"
    assert "kubernetes.namespace_name:hop-scan" in expr
    assert expr.rstrip().endswith("| stats count() as value")
    ev = q(rule, "C")["model"]["conditions"][0]["evaluator"]
    assert (ev["type"], ev["params"][0]) == ("gt", 0)
    assert rule["noDataState"] == "OK"
    healthy = heartbeat(tmp_path, "ok", 3, 3)
    for blind in (heartbeat(tmp_path, "skipped: hop kube API unreachable", 0, 0),
                  heartbeat(tmp_path, "ok", 3, 0), heartbeat(tmp_path, "ok", 0, 0)):
        assert matches(expr, blind), blind
    assert not matches(expr, healthy)
