"""Tripwire: the second public edge site is actually watched.

Adding a site to the edge without adding it to the probe and the alert rule
produces the worst kind of monitoring: dashboards that look complete while one
of the two public sites can be down indefinitely with nothing firing.

Layer 17 stays a SINGLE rule covering both instances rather than growing a
per-site copy — the alert summary already interpolates {{ $labels.instance }},
so the firing alert names which site broke without a second rule to keep in
sync.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VMPROBE = REPO_ROOT / "apps/blackbox-exporter/manifests/vmprobe.yaml"
ALERTS = REPO_ROOT / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"

WWW = "https://www.derio.net"
BLOG = "https://blog.derio.net"


def _feature_health_targets() -> list[str]:
    for doc in yaml.safe_load_all(VMPROBE.read_text()):
        if doc and doc.get("metadata", {}).get("name") == "feature-health-probes":
            return doc["spec"]["targets"]["staticConfig"]["targets"]
    raise AssertionError("feature-health-probes VMProbe not found")


def test_www_is_probed() -> None:
    targets = _feature_health_targets()
    assert WWW in targets, (
        f"{WWW} is not probed — an outage would be invisible. targets={targets}"
    )
    # The blog must not be dropped while adding www.
    assert BLOG in targets


def test_layer_17_rule_covers_both_public_sites() -> None:
    raw = ALERTS.read_text()
    assert "layer-17-edge-down" in raw

    # Scope to the layer-17 rule itself. Other rules probe *.frank.derio.net,
    # so a naive grep for "probe_success ... derio.net" picks up the wrong one.
    start = raw.index("uid: layer-17-edge-down")
    block = raw[start : start + 2500]

    exprs = [ln for ln in block.splitlines() if "probe_success" in ln]
    assert exprs, "no probe_success expression inside the layer-17 rule"
    expr = exprs[0]

    assert "instance=~" in expr, (
        "the Layer 17 expression must match both edge instances with a regex; "
        f"found a single-instance matcher: {expr.strip()}"
    )
    # Both hostnames must be reachable by the matcher.
    assert "blog" in expr and "www" in expr, (
        f"expression does not name both sites: {expr.strip()}"
    )


def test_alert_configmap_still_parses() -> None:
    """A malformed rules file provisions nothing and Grafana stays silent."""
    cm = yaml.safe_load(ALERTS.read_text())
    assert cm["kind"] == "ConfigMap"
    payloads = [v for k, v in cm["data"].items() if k.endswith((".yaml", ".yml"))]
    assert payloads, "no rule documents in the ConfigMap"
    for body in payloads:
        yaml.safe_load(body)
