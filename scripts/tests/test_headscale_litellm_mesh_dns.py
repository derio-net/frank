"""Guards for the Headscale MagicDNS record that lets mesh peers reach LiteLLM.

The kid laptops can already *route* to Frank's LAN (argonath subnet routers) and
LiteLLM's own Bearer auth already answers them — the only missing piece is a
mesh-resolvable name. Phase 1 adds `litellm-lb.cluster.derio.net` pointing
straight at LiteLLM's Cilium LoadBalancer (192.168.55.206:4000), bypassing
Traefik and therefore the Authentik forward-auth outpost.

Contract source of truth:
docs/superpowers/specs/2026-08-02--edge--litellm-mesh-dns-design.md

Note the file shape: `data["config.yaml"]` is a YAML *document embedded as a
string*, so every assertion here loads the ConfigMap and then loads that string
again. A clumsy hand-edit that drops a sibling record or re-nests the list would
still be valid YAML — hence the explicit shape assertions.
"""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIGMAP = REPO / "clusters/hop/apps/headscale/manifests/configmap.yaml"

LITELLM_RECORD = {
    "name": "litellm-lb.cluster.derio.net",
    "type": "A",
    "value": "192.168.55.206",
}
GITEA_SSH_RECORD = {
    "name": "gitea-ssh.cluster.derio.net",
    "type": "A",
    "value": "192.168.55.209",
}


def _headscale_config():
    cm = yaml.safe_load(CONFIGMAP.read_text())
    assert cm["kind"] == "ConfigMap", f"expected a ConfigMap, got {cm.get('kind')!r}"
    return yaml.safe_load(cm["data"]["config.yaml"])


def _extra_records():
    records = _headscale_config()["dns"]["extra_records"]
    assert isinstance(records, list), (
        "dns.extra_records must stay a LIST of mappings — an indentation slip in "
        f"the embedded document turned it into {type(records).__name__}"
    )
    for rec in records:
        assert isinstance(rec, dict), f"extra_records entry must be a mapping; got {rec!r}"
    return records


def test_litellm_lb_record_present():
    records = _extra_records()
    assert LITELLM_RECORD in records, (
        "dns.extra_records must carry the LiteLLM LoadBalancer record "
        f"{LITELLM_RECORD} — without it a mesh client has no name to resolve for "
        f"LiteLLM. Present records: {records!r}"
    )


def test_gitea_ssh_record_still_present():
    records = _extra_records()
    assert GITEA_SSH_RECORD in records, (
        "the pre-existing gitea-ssh record must survive any edit to this "
        f"hand-maintained embedded YAML — {GITEA_SSH_RECORD} is what makes "
        "git-over-ssh work for every mesh peer, and nothing else reports its loss. "
        f"Present records: {records!r}"
    )


def test_magic_dns_enabled():
    dns = _headscale_config()["dns"]
    assert dns.get("magic_dns") is True, (
        "dns.magic_dns must be true — extra_records are inert without MagicDNS, "
        f"so the record would resolve nowhere. Got {dns.get('magic_dns')!r}"
    )
