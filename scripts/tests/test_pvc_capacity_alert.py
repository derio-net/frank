"""Guard the PVC capacity alert rules and their 4h-repeat route (frank#722).

Three rules in group `pvc-capacity` (folder feature-health) watch kubelet
volume stats. Easy regressions to ship silently:

1. Dropping the `> 0` guard on the denominator: a zero capacity gives +Inf
   and the rule fires forever.
2. Dropping `max by`: a volume that moves between nodes briefly has two series.
3. Losing the pvc_capacity route (or letting it drift below the severity
   routes): the condition only clears by operator action, so without the 4h
   repeat it would re-page every 3m for days.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
RULES_CM = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
POLICY_CM = REPO / "apps/grafana-alerting/manifests/notification-policy-cm.yaml"

BY = "max by (namespace, persistentvolumeclaim)"
# uid -> (used metric, capacity metric, threshold, for, severity)
EXPECTED = {
    "pvc-capacity-warning": ("kubelet_volume_stats_used_bytes", "kubelet_volume_stats_capacity_bytes", 85, "30m", "warning"),
    "pvc-capacity-critical": ("kubelet_volume_stats_used_bytes", "kubelet_volume_stats_capacity_bytes", 95, "5m", "critical"),
    "pvc-inodes-warning": ("kubelet_volume_stats_inodes_used", "kubelet_volume_stats_inodes", 90, "30m", "warning"),
}


def _rules():
    cm = yaml.safe_load(RULES_CM.read_text())
    out = {}
    for blob in cm["data"].values():
        doc = yaml.safe_load(blob)
        for grp in doc.get("groups", []):
            for rule in grp.get("rules", []):
                out[rule["uid"]] = (grp, rule)
    return out


def _routes():
    cm = yaml.safe_load(POLICY_CM.read_text())
    doc = yaml.safe_load(cm["data"]["notification-policy.yaml"])
    return doc["policies"][0]["routes"]


def test_rules_exist_in_pvc_capacity_group():
    rules = _rules()
    for uid in EXPECTED:
        assert uid in rules, f"{uid} missing"
        grp, _ = rules[uid]
        assert grp["name"] == "pvc-capacity"
        assert grp["folder"] == "feature-health"


def test_expr_is_max_by_ratio_with_guarded_denominator():
    for uid, (used, cap, *_rest) in EXPECTED.items():
        _, rule = _rules()[uid]
        expr = " ".join(next(d for d in rule["data"] if d["refId"] == "A")["model"]["expr"].split())
        assert expr == f"100 * {BY} ({used}) / ({BY} ({cap}) > 0)", (uid, expr)


def test_threshold_for_and_severity():
    for uid, (_u, _c, thr, for_, sev) in EXPECTED.items():
        _, rule = _rules()[uid]
        c = next(d for d in rule["data"] if d["refId"] == "C")
        ev = c["model"]["conditions"][0]["evaluator"]
        assert ev["type"] == "gt" and ev["params"] == [thr], uid
        assert rule["for"] == for_, uid
        assert rule["labels"]["severity"] == sev, uid
        b = next(d for d in rule["data"] if d["refId"] == "B")["model"]
        assert b["type"] == "reduce" and b["reducer"] == "last"
        assert b["settings"] == {"mode": "dropNN"}


def test_labels_states_and_summary():
    for uid in EXPECTED:
        _, rule = _rules()[uid]
        assert rule["labels"]["github_issue"] == "frank-ops#4", uid
        assert rule["labels"]["pvc_capacity"] == "true", uid
        assert rule["noDataState"] == "OK", uid
        assert rule["execErrState"] == "Error", uid
        assert len(uid) <= 40, uid
        summary = rule["annotations"]["summary"]
        assert not any(ch in summary for ch in "<>&"), summary
        assert "$labels.namespace" in summary and "$labels.persistentvolumeclaim" in summary


def test_route_present_with_4h_repeat_before_severity_routes():
    routes = _routes()
    idx = next(i for i, r in enumerate(routes) if 'pvc_capacity="true"' in r.get("matchers", []))
    route = routes[idx]
    assert route["repeat_interval"] == "4h"
    assert route["continue"] is False
    kids = route["routes"]
    assert [k["receiver"] for k in kids] == ["Telegram - Willikins", "Health Bridge Webhook"]
    assert kids[0]["continue"] is True
    first_sev = next(i for i, r in enumerate(routes) if any(m.startswith("severity=") for m in r.get("matchers", [])))
    assert idx < first_sev
    hbo = next(i for i, r in enumerate(routes) if "health_bridge_only=\"true\"" in r.get("matchers", []))
    assert idx > hbo
