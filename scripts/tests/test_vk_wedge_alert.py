"""Guard the VK executor-pool wedge alert (frank#692 follow-up).

Locks the load-bearing shape of the leaked-permit wedge detector. The two
easiest regressions to ship silently:

1. Rewriting the expr as a plain `and`-filter — healthy then becomes an EMPTY
   result (NoData), which collides with `noDataState: Alerting` and fires the
   wedge alert on every quiet day. The bool-product form always returns 0/1
   while the scrape is alive, so NoData is reserved for "scrape dead".
2. Losing the health_bridge_only route (or letting it drift BELOW the severity
   routes) — severity=critical would then page Telegram on every evaluation
   window, which this rule must never do (route order is load-bearing, see
   the canary_watchdog comment in the notification policy).
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
RULES_CM = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
POLICY_CM = REPO / "apps/grafana-alerting/manifests/notification-policy-cm.yaml"
UID = "vk-executor-pool-wedged"


def _find_rule():
    cm = yaml.safe_load(RULES_CM.read_text())
    for blob in cm["data"].values():
        doc = yaml.safe_load(blob)
        for grp in doc.get("groups", []):
            for rule in grp.get("rules", []):
                if rule.get("uid") == UID:
                    return rule
    raise AssertionError(f"rule {UID} not found in {RULES_CM}")


def _routes():
    cm = yaml.safe_load(POLICY_CM.read_text())
    doc = yaml.safe_load(cm["data"]["notification-policy.yaml"])
    return doc["policies"][0]["routes"]


def test_expr_is_bool_product_not_and_filter():
    expr = next(d for d in _find_rule()["data"] if d["refId"] == "A")["model"]["expr"]
    assert ">= bool vibekanban_max_executions" in expr
    assert "vibekanban_queued_executions >= bool 1" in expr
    assert ") * (" in expr, "must be a 0/1 product so healthy != NoData"
    assert " and " not in expr, "an and-filter makes healthy == NoData == Alerting"


def test_nodata_means_scrape_dead_and_fires():
    rule = _find_rule()
    assert rule["noDataState"] == "Alerting", "scrape death must surface, not go silent"
    assert rule["execErrState"] == "Error"
    c = next(d for d in rule["data"] if d["refId"] == "C")
    cond = c["model"]["conditions"][0]["evaluator"]
    assert cond["type"] == "gt" and cond["params"] == [0.5]


def test_flap_window_outlasts_a_legitimate_dispatch_storm():
    assert _find_rule()["for"] == "1h"


def test_critical_for_health_bridge_but_never_pages():
    labels = _find_rule()["labels"]
    assert labels["severity"] == "critical"        # dead→bug-issue lifecycle
    assert labels["health_bridge_only"] == "true"  # ...without paging Telegram
    assert labels["github_issue"] == "frank-ops#18"


def test_health_bridge_only_route_precedes_severity_routes():
    routes = _routes()

    def idx(pred):
        return next(i for i, r in enumerate(routes) if pred(r))

    hbo = idx(lambda r: 'health_bridge_only="true"' in r.get("matchers", []))
    sev = idx(lambda r: "severity=critical" in r.get("matchers", []))
    assert hbo < sev, "route order is load-bearing: severity=critical pages Telegram"
    assert routes[hbo]["receiver"] == "Health Bridge Webhook"
    assert routes[hbo]["continue"] is False
