"""Guard: every Frank host must get internal DNS resolvers declaratively.

A Talos host with a STATIC interface (`dhcp: false`) and no
`machine.network.nameservers` falls back to Talos's built-in public resolvers
(1.1.1.1 / 8.8.8.8). The homelab blocks public DNS network-wide by ACL, so such
a host cannot resolve its NTP server, never syncs time, and Talos then gates
apid/kubelet/siderolink on time-sync — the node hangs "pinging but dead" (the
gpu-1 2026-07-12 incident). The fix is a cluster-wide nameservers ConfigPatch.

This is a pure-Python repo guard (no cluster access), mirroring the other
`scripts/tests/test_*.py` guards.
"""

from pathlib import Path

import pytest
import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip the guard

REPO = Path(__file__).resolve().parents[2]
PATCHES = REPO / "patches"

NAMESERVERS = {"192.168.10.11", "192.168.10.12"}
NS_PATCH_ID = "102-cluster-nameservers"


def _iter_configpatch_docs():
    """Yield (path, doc) for every YAML mapping doc under patches/."""
    for p in sorted(PATCHES.rglob("*.yaml")):
        try:
            for doc in yaml.safe_load_all(p.read_text()):
                if isinstance(doc, dict):
                    yield p, doc
        except yaml.YAMLError:
            continue


def _is_configpatch(doc):
    return (doc.get("metadata") or {}).get("type") == "ConfigPatches.omni.sidero.dev"


def _spec_data(doc):
    """Parse the inner Talos machine config carried in spec.data (a YAML string)."""
    data = (doc.get("spec") or {}).get("data")
    if not isinstance(data, str):
        return {}
    try:
        return yaml.safe_load(data) or {}
    except yaml.YAMLError:
        return {}


def _static_interfaces(machine_cfg):
    """Interfaces with dhcp:false AND a non-empty addresses list."""
    net = (machine_cfg.get("machine") or {}).get("network") or {}
    for iface in net.get("interfaces") or []:
        if isinstance(iface, dict) and iface.get("dhcp") is False and iface.get("addresses"):
            yield iface


def _find_nameservers_patch():
    for path, doc in _iter_configpatch_docs():
        if (doc.get("metadata") or {}).get("id") == NS_PATCH_ID:
            return path, doc
    return None, None


def test_cluster_nameservers_patch_exists_and_valid():
    path, doc = _find_nameservers_patch()
    assert doc is not None, (
        f"cluster-wide nameservers patch (id {NS_PATCH_ID}) not found under patches/"
    )
    labels = (doc.get("metadata") or {}).get("labels") or {}
    assert labels.get("omni.sidero.dev/cluster") == "frank", (
        f"{path}: must carry label omni.sidero.dev/cluster: frank (applies to all hosts)"
    )
    assert "omni.sidero.dev/cluster-machine" not in labels, (
        f"{path}: must be cluster-scoped, not pinned to a single machine"
    )
    machine = _spec_data(doc)
    ns = ((machine.get("machine") or {}).get("network") or {}).get("nameservers") or []
    assert set(ns) == NAMESERVERS, (
        f"{path}: machine.network.nameservers must be exactly {sorted(NAMESERVERS)}, got {ns}"
    )


def test_static_interfaces_are_covered_by_cluster_nameservers():
    """If any patch declares a static interface (dhcp:false + addresses), the
    cluster-wide nameservers patch MUST exist — otherwise that host falls back
    to ACL-blocked public DNS and hangs at boot."""
    static = []
    for path, doc in _iter_configpatch_docs():
        if not _is_configpatch(doc):
            continue
        for iface in _static_interfaces(_spec_data(doc)):
            static.append((str(path.relative_to(REPO)), iface.get("addresses")))
    if not static:
        pytest.skip("no static-interface patches in repo")
    _, ns_doc = _find_nameservers_patch()
    assert ns_doc is not None, (
        "static-interface patch(es) present without the cluster-wide nameservers "
        f"patch ({NS_PATCH_ID}) — those hosts would fall back to public DNS: {static}"
    )
