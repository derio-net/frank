"""Manifest invariants for the cert-expiry canary (issue #251, option 1).

Spec: docs/superpowers/specs/2026-06-07--obs--cert-expiry-canary-design.md

Guards the load-bearing config shape: the insecure-TLS blackbox module and the
expired-cert canary VMProbe (phase 1); the notification-policy mute routing and
the absent()-watchdog rule (phase 2). The routing-order assertions matter most:
the watchdog alert also carries canary="true", so the watchdog route must
precede the mute route or the watchdog is silently muted.

Run:
    uv run --with pyyaml --with pytest pytest scripts/tests/test_cert_expiry_canary.py -q
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
BLACKBOX_CM = REPO / "apps/blackbox-exporter/manifests/configmap.yaml"
VMPROBE_FILE = REPO / "apps/blackbox-exporter/manifests/vmprobe.yaml"
NOTIF_POLICY_CM = REPO / "apps/grafana-alerting/manifests/notification-policy-cm.yaml"
ALERT_RULES_CM = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"

# Keep in sync with facts.PROBE_UA_TOKEN in
# apps/ai-alert-helper/src/ai_alert_helper/facts.py (see blackbox configmap note).
PROBE_UA = "Frank-Blackbox-Probe/1.0 (+https://blog.derio.net)"


def _blackbox_modules():
    cm = yaml.safe_load(BLACKBOX_CM.read_text())
    return yaml.safe_load(cm["data"]["blackbox.yml"])["modules"]


def _vmprobe_docs():
    return [d for d in yaml.safe_load_all(VMPROBE_FILE.read_text()) if d]


# --- Phase 1: blackbox module + canary VMProbe ------------------------------


def test_insecure_tls_module_shape():
    modules = _blackbox_modules()
    assert "http_2xx_insecure_tls" in modules, "module http_2xx_insecure_tls missing"
    http = modules["http_2xx_insecure_tls"]["http"]
    assert http["tls_config"]["insecure_skip_verify"] is True
    assert http["valid_status_codes"] == [200]
    assert http["follow_redirects"] is False
    assert http["preferred_ip_protocol"] == "ip4"
    assert http["headers"]["User-Agent"] == PROBE_UA


def test_existing_modules_untouched():
    modules = _blackbox_modules()
    for name in ("http_2xx", "http_2xx_no_redirect", "tcp_connect"):
        assert name in modules, f"pre-existing module {name} went missing"
    # insecure_skip_verify must stay scoped to the canary module only
    for name, mod in modules.items():
        if name == "http_2xx_insecure_tls":
            continue
        tls = mod.get("http", {}).get("tls_config", {})
        assert not tls.get("insecure_skip_verify"), f"{name} must not skip TLS verify"


def test_canary_vmprobe_shape():
    probes = {d["metadata"]["name"]: d for d in _vmprobe_docs()}
    assert "expired-cert-canary" in probes, "VMProbe expired-cert-canary missing"
    probe = probes["expired-cert-canary"]
    assert probe["metadata"]["namespace"] == "monitoring"
    spec = probe["spec"]
    static = spec["targets"]["staticConfig"]
    assert static["targets"] == ["https://expired.badssl.com/"]
    # canary="true" drives the mute route; probe_group keeps feature-health clean
    assert static["labels"]["canary"] == "true"
    assert static["labels"]["probe_group"] == "cert_canary"
    assert spec["module"] == "http_2xx_insecure_tls"
    # cross-file invariant: the probe's module must actually exist in the
    # blackbox config — a rename on either side would otherwise pass both
    # single-file tests yet emit nothing
    assert spec["module"] in _blackbox_modules()
    assert spec["vmProberSpec"]["url"] == "blackbox-exporter.monitoring.svc:9115"


def test_existing_vmprobes_untouched():
    names = {d["metadata"]["name"] for d in _vmprobe_docs()}
    assert {"feature-health-probes", "management-plane-probes"} <= names


# --- Phase 2: notification-policy mute routing + watchdog rule ---------------


def _notif_provisioning():
    cm = yaml.safe_load(NOTIF_POLICY_CM.read_text())
    return yaml.safe_load(cm["data"]["notification-policy.yaml"])


def _routes():
    return _notif_provisioning()["policies"][0]["routes"]


def _rule_groups():
    cm = yaml.safe_load(ALERT_RULES_CM.read_text())
    return yaml.safe_load(cm["data"]["alert-rules.yaml"])["groups"]


def test_perma_mute_interval_provisioned():
    prov = _notif_provisioning()
    mts = {m["name"]: m for m in prov.get("muteTimes", [])}
    assert "perma-mute" in mts, "muteTimes perma-mute missing"
    mt = mts["perma-mute"]
    assert mt["orgId"] == 1
    # 00:00–24:00 with no weekday/month restriction = always active
    assert mt["time_intervals"][0]["times"] == [
        {"start_time": "00:00", "end_time": "24:00"}
    ]


def test_watchdog_route_is_first():
    """severity=critical on the watchdog must reach health-bridge, never Telegram."""
    r = _routes()[0]
    assert r["receiver"] == "Health Bridge Webhook"
    assert r["matchers"] == ['canary_watchdog="true"']
    assert r["continue"] is False


def test_canary_mute_route_is_second():
    """The watchdog also carries canary="true" (absent() propagates its selector's
    equality matchers) — the mute route must come AFTER the watchdog route."""
    r = _routes()[1]
    assert r["matchers"] == ['canary="true"']
    assert r["mute_time_intervals"] == ["perma-mute"]
    assert r["continue"] is False


def test_existing_routes_preserved_in_order():
    # pin the total so a stray route inserted between the canary pair and the
    # tail can't hide in the [2:] slice
    assert len(_routes()) == 7
    tail = _routes()[2:]
    expected = [
        ("AI Helper Webhook", ['grafana_folder="blog-edge"'], False),
        # GPU-timeshare feature-health: early continue:false to Health Bridge only
        # (degraded tile, no Telegram) — must precede the severity routes so a
        # gpu_timeshare alert never pages. See frank-gotchas "gpu_timeshare".
        ("Health Bridge Webhook", ['gpu_timeshare="true"'], False),
        ("Telegram - Willikins", ["severity=critical"], True),
        ("Telegram - Willikins", ["severity=warning"], True),
        ("Health Bridge Webhook", ['grafana_folder="feature-health"'], False),
    ]
    actual = [(r["receiver"], r["matchers"], r["continue"]) for r in tail]
    assert actual == expected


def _watchdog_rule():
    groups = {g["name"]: g for g in _rule_groups()}
    assert "tls-cert-expiry-1h" in groups
    rules = {r["uid"]: r for r in groups["tls-cert-expiry-1h"]["rules"]}
    assert "tls-cert-canary-absent" in rules, "watchdog rule missing"
    return rules["tls-cert-canary-absent"]


def test_watchdog_rule_query_and_states():
    rule = _watchdog_rule()
    a = rule["data"][0]
    assert a["model"]["expr"] == 'absent(probe_ssl_earliest_cert_expiry{canary="true"})'
    assert a["datasourceUid"] == "P4169E866C3094E38"
    # absent() returns EMPTY when the metric exists → noData is the HEALTHY path
    assert rule["noDataState"] == "OK"
    assert rule["execErrState"] == "Error"
    assert rule["for"] == "3h"  # generous — tolerates transient badssl outages
    assert rule["condition"] == "C"


def test_watchdog_rule_sse_three_step_shape():
    """Grafana 12 SSE gotcha: rules need the 3-step A→B→C shape."""
    rule = _watchdog_rule()
    refs = [d["refId"] for d in rule["data"]]
    assert refs == ["A", "B", "C"]
    b = rule["data"][1]["model"]
    assert (b["type"], b["reducer"]) == ("reduce", "last")
    c = rule["data"][2]["model"]
    assert c["type"] == "threshold"
    assert c["conditions"][0]["evaluator"] == {"type": "gt", "params": [0]}


def test_watchdog_rule_labels_route_to_health_bridge():
    labels = _watchdog_rule()["labels"]
    # critical → health-bridge maps firing to dead → creates the bug issue
    assert labels["severity"] == "critical"
    # without github_issue, health-bridge skips the alert entirely (bridge.go)
    assert labels["github_issue"] == "frank-ops#8"
    # first-position route key — keeps critical away from Telegram
    assert labels["canary_watchdog"] == "true"


def test_existing_tls_cert_rules_untouched():
    groups = {g["name"]: g for g in _rule_groups()}
    rules = {r["uid"]: r for r in groups["tls-cert-expiry-1h"]["rules"]}
    assert rules["tls-cert-expiring-14d"]["labels"]["severity"] == "warning"
    assert rules["tls-cert-expiring-7d"]["labels"]["severity"] == "critical"
