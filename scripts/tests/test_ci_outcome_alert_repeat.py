"""CI-outcome alerts re-page every 4h, not every 3m, and their runbooks work in any namespace.

`layer-25-pipeline-failing` evaluates a 24h window, so once it fires it stays
firing until a run succeeds or the failures age out — up to a day. Through the
generic severity=warning route it inherited the root `repeat_interval: 3m`
and re-sent the identical Telegram page every three minutes (2026-11-02,
kid-laptops-ci). It now carries `ci_outcome="true"`, routed like
`pvc_capacity` (4h, ahead of the severity routes).

Its runbook hint hard-coded `-n tekton-pipelines`, but kid-laptops-ci runs in
its own namespace (#791), so the suggested command listed nothing.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
RULES_CM = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
POLICY_CM = REPO / "apps/grafana-alerting/manifests/notification-policy-cm.yaml"

CI_OUTCOME_RULES = ["layer-25-pipeline-failing", "layer-25-pipelinerun-timeout"]
MATCHER = 'ci_outcome="true"'


def _rules():
    cm = yaml.safe_load(RULES_CM.read_text())
    out = {}
    for blob in cm["data"].values():
        doc = yaml.safe_load(blob)
        for grp in doc.get("groups", []):
            for rule in grp.get("rules", []):
                out[rule["uid"]] = rule
    return out


def _routes():
    cm = yaml.safe_load(POLICY_CM.read_text())
    doc = yaml.safe_load(cm["data"]["notification-policy.yaml"])
    return doc["policies"][0]["routes"]


def test_ci_outcome_rules_carry_the_label():
    rules = _rules()
    for uid in CI_OUTCOME_RULES:
        assert rules[uid]["labels"].get("ci_outcome") == "true", uid


def test_ci_outcome_route_repeats_every_4h_before_severity_routes():
    routes = _routes()
    idx = next(i for i, r in enumerate(routes) if MATCHER in r.get("matchers", []))
    route = routes[idx]
    assert route["repeat_interval"] == "4h"
    assert route["continue"] is False
    kids = route["routes"]
    # Replicates what the severity route (Telegram) + feature-health route
    # (Health Bridge) would have delivered.
    assert [k["receiver"] for k in kids] == ["Telegram - Willikins", "Health Bridge Webhook"]
    assert kids[0]["continue"] is True
    for k in kids:
        assert "matchers" not in k and "object_matchers" not in k, k
        assert "repeat_interval" not in k, k
    first_sev = next(
        i for i, r in enumerate(routes) if any(m.startswith("severity=") for m in r.get("matchers", []))
    )
    assert idx < first_sev
    hbo = next(i for i, r in enumerate(routes) if 'health_bridge_only="true"' in r.get("matchers", []))
    assert idx > hbo


def test_ci_outcome_runbooks_are_not_namespace_pinned():
    rules = _rules()
    for uid in CI_OUTCOME_RULES:
        runbook = rules[uid]["annotations"]["runbook"]
        assert "-n tekton-pipelines" not in runbook, (uid, runbook)
        assert "get pipelinerun -A " in runbook, (uid, runbook)
