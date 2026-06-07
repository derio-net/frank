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
    assert spec["vmProberSpec"]["url"] == "blackbox-exporter.monitoring.svc:9115"


def test_existing_vmprobes_untouched():
    names = {d["metadata"]["name"] for d in _vmprobe_docs()}
    assert {"feature-health-probes", "management-plane-probes"} <= names
