"""Tripwire: Frank's etcd scrape, across the two files that must agree.

Frank did not scrape its own etcd for 148 days, and the reason is worth
restating because this guard exists to stop it recurring. `kubeEtcd.enabled`
is `true` by default in `victoria-metrics-k8s-stack` and Frank never disabled
it, so a headless Service, a `VMServiceScrape` and an `Endpoints` object have
existed since the cluster was built — the Endpoints object **empty the whole
time**, because the chart's Service selects pods labelled `component: etcd`
(the kubeadm layout) and Talos runs etcd as a host system service. Zero
endpoints, zero targets, zero series, and no error anywhere. Same family as
the kube-state-metrics `maxScrapeSize` drop written up in
`apps/victoria-metrics/values.yaml`: something silently yields nothing and the
only symptom is an absence.

The fix has two halves that live in different worlds:

* `patches/phase08-obs/omni-configpatch-etcd-metrics.yaml` opens etcd's
  dedicated metrics listener on `0.0.0.0:2381`. Applied by `omnictl`, by an
  operator, out of band.
* `apps/victoria-metrics/values.yaml` points a **static** `Endpoints` object at
  the three control-plane minis on that port. Applied by ArgoCD.

Nothing else in the repo connects them. A port typo in either file, or a node
IP that moves, reproduces exactly the silent-empty-target failure being fixed —
which is why the cross-file assertions here are written as *derivations* (parse
the port out of the ConfigPatch URL, parse the IPs out of the repo's own
machine table) rather than as a third hardcoded copy of the same values.
"""
from __future__ import annotations

import pathlib
import re
from typing import Any
from urllib.parse import urlparse

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]

CONFIGPATCH = (
    REPO / "patches" / "phase08-obs" / "omni-configpatch-etcd-metrics.yaml"
)
VM_VALUES = REPO / "apps" / "victoria-metrics" / "values.yaml"
INFRA_RULE = REPO / "agents" / "rules" / "frank-infrastructure.md"

# The Omni resource type and the machine set the patch must be scoped to.
# etcd runs only on control planes; a fleet-wide patch would push etcd args at
# four workers that run no etcd at all.
CONFIGPATCH_TYPE = "ConfigPatches.omni.sidero.dev"
CLUSTER_LABEL = "omni.sidero.dev/cluster"
MACHINE_SET_LABEL = "omni.sidero.dev/machine-set"
CONTROL_PLANE_MACHINE_SET = "frank-control-planes"


# The machine table in `agents/rules/frank-infrastructure.md` is the repo's own
# statement of which node is what. Deriving the control-plane addresses from it
# — rather than restating them here — is what keeps this guard from becoming
# the THIRD place Frank's node IPs live.
_MACHINE_ROW = re.compile(
    r"^\|\s*(?P<host>[\w-]+)\s*\|\s*(?P<ip>\d+\.\d+\.\d+\.\d+)\s*\|"
    r"\s*(?P<role>[\w-]+)\s*\|"
)


def _documented_control_plane_ips() -> list[str]:
    """Control-plane IPs, in table order, parsed out of the machine table."""
    text = INFRA_RULE.read_text(encoding="utf-8")
    ips: list[str] = []
    for line in text.splitlines():
        match = _MACHINE_ROW.match(line.strip())
        if match and match.group("role") == "control-plane":
            ips.append(match.group("ip"))
    assert len(ips) == 3, (
        f"expected 3 control-plane rows in {INFRA_RULE.relative_to(REPO)}'s "
        f"machine table, parsed {len(ips)}: {ips}. Either the table's shape "
        "changed and this derivation is now reading nothing, or Frank's "
        "control plane is no longer three nodes — in which case "
        "kubeEtcd.endpoints needs revisiting, not this regex."
    )
    return ips


CONTROL_PLANE_IPS = _documented_control_plane_ips()


def _load_configpatch() -> dict[str, Any]:
    """The outer Omni ConfigPatch document."""
    assert CONFIGPATCH.exists(), (
        f"{CONFIGPATCH.relative_to(REPO)} does not exist — the Talos "
        "ConfigPatch that opens etcd's metrics listener is the half of this "
        "change that makes the scrape target reachable at all"
    )
    return yaml.safe_load(CONFIGPATCH.read_text(encoding="utf-8"))


def _configpatch_machine_config() -> dict[str, Any]:
    """The Talos machine config embedded in `spec.data`.

    `spec.data` is a YAML document carried as a *string*, so reading anything
    inside it needs two loads — the same double-load shape as the Grafana alert
    ConfigMap and the headscale config guard.
    """
    document = _load_configpatch()
    spec = document.get("spec") or {}
    data = spec.get("data")
    assert isinstance(data, str), (
        f"{CONFIGPATCH.relative_to(REPO)} has no `spec.data` YAML string — an "
        "Omni ConfigPatch carries the Talos machine config as an embedded "
        f"document, not as nested mapping keys. Got: {type(data).__name__}"
    )
    inner = yaml.safe_load(data)
    assert isinstance(inner, dict), (
        f"{CONFIGPATCH.relative_to(REPO)}'s `spec.data` does not parse to a "
        "mapping — the embedded machine config is malformed"
    )
    return inner


def _listen_metrics_urls() -> str:
    inner = _configpatch_machine_config()
    extra_args = (
        ((inner.get("cluster") or {}).get("etcd") or {}).get("extraArgs") or {}
    )
    assert "listen-metrics-urls" in extra_args, (
        f"{CONFIGPATCH.relative_to(REPO)} does not set "
        "`cluster.etcd.extraArgs.listen-metrics-urls`. Without it etcd serves "
        "/metrics only on its client port (2379) behind mutual TLS, and the "
        f"scrape has nothing to reach. Found extraArgs: {sorted(extra_args)}"
    )
    return str(extra_args["listen-metrics-urls"])


def test_configpatch_opens_the_metrics_listener():
    """The ConfigPatch is a control-plane-scoped patch opening 0.0.0.0:2381.

    Plain HTTP is deliberate and is argued in the design spec: the metrics
    listener serves `/metrics` and `/health` only and carries no key material,
    whereas scraping 2379 needs an etcd client certificate that also grants
    full read/write to cluster state.

    The machine-set assertion is the load-bearing one here.
    """
    document = _load_configpatch()
    metadata = document.get("metadata") or {}

    assert metadata.get("type") == CONFIGPATCH_TYPE, (
        f"{CONFIGPATCH.relative_to(REPO)} must declare "
        f"`metadata.type: {CONFIGPATCH_TYPE}` so `omnictl apply` recognises it "
        f"as a ConfigPatch. Got: {metadata.get('type')!r}"
    )

    labels = metadata.get("labels") or {}
    assert labels.get(CLUSTER_LABEL) == "frank", (
        f"{CONFIGPATCH.relative_to(REPO)} must be scoped to the frank cluster "
        f"via `{CLUSTER_LABEL}`. Got: {labels.get(CLUSTER_LABEL)!r}"
    )
    assert labels.get(MACHINE_SET_LABEL) == CONTROL_PLANE_MACHINE_SET, (
        f"{CONFIGPATCH.relative_to(REPO)} must be scoped to the "
        f"`{CONTROL_PLANE_MACHINE_SET}` machine set via "
        f"`{MACHINE_SET_LABEL}`. etcd runs only on control planes, so a "
        "fleet-wide patch would push etcd args to four workers that run no "
        f"etcd. Got: {labels.get(MACHINE_SET_LABEL)!r}"
    )

    assert _listen_metrics_urls() == "http://0.0.0.0:2381", (
        "expected `listen-metrics-urls: http://0.0.0.0:2381` — the dedicated "
        "read-only metrics listener. Got: " f"{_listen_metrics_urls()!r}"
    )


# ---------------------------------------------------------------------------
# The GitOps half: chart values pointing a STATIC Endpoints object at the three
# control-plane minis.
#
# The negative assertions below matter more than the positive ones. The chart's
# DEFAULT `vmScrape` uses `scheme: https` plus a ServiceAccount bearer token and
# is aimed at port 2379 — the kubeadm layout, where etcd's client port is what
# you scrape. Inheriting any part of that default against 2381 produces a target
# that fails forever while the configuration looks entirely plausible in a diff.
# ---------------------------------------------------------------------------

METRICS_PORT_NAME = "http-metrics"


def _vm_values() -> dict[str, Any]:
    return yaml.safe_load(VM_VALUES.read_text(encoding="utf-8"))


def _kube_etcd() -> dict[str, Any]:
    values = _vm_values()
    assert "kubeEtcd" in values, (
        f"{VM_VALUES.relative_to(REPO)} has no `kubeEtcd` block. The chart "
        "defaults it to enabled with a pod selector that can never match on "
        "Talos, which is how this scrape stayed inert and silent for 148 days "
        f"— leaving it unstated is the bug. Top-level keys: {sorted(values)}"
    )
    return values["kubeEtcd"]


def _kube_etcd_scrape_endpoints() -> list[dict[str, Any]]:
    kube_etcd = _kube_etcd()
    endpoints = (
        ((kube_etcd.get("vmScrape") or {}).get("spec") or {}).get("endpoints")
    )
    assert endpoints, (
        "kubeEtcd.vmScrape.spec.endpoints is missing or empty — without an "
        "explicit override the chart's default endpoint applies, which scrapes "
        "https with a ServiceAccount bearer token and can never succeed "
        "against etcd's plain-HTTP metrics listener"
    )
    return list(endpoints)


def test_kube_etcd_values_target_the_control_planes():
    """The scrape points at a static Endpoints object on the metrics port.

    Supplying `endpoints:` is what switches the chart from selector-based pod
    discovery to a static `Endpoints` object — the only shape that can address
    a host system service. Everything else here exists to stop the chart
    default leaking back in.
    """
    kube_etcd = _kube_etcd()

    assert kube_etcd.get("enabled") is True, (
        "kubeEtcd.enabled must be explicitly True. It is the chart default, "
        "but stating it is what makes this block's intent legible next to the "
        f"kubeControllerManager disable above it. Got: {kube_etcd.get('enabled')!r}"
    )

    service = kube_etcd.get("service") or {}
    assert service.get("port") == 2381 and service.get("targetPort") == 2381, (
        "kubeEtcd.service.port and .targetPort must both be 2381, etcd's "
        "dedicated metrics listener. The chart default is 2379, the mutual-TLS "
        f"client port. Got port={service.get('port')!r}, "
        f"targetPort={service.get('targetPort')!r}"
    )

    assert kube_etcd.get("endpoints") == CONTROL_PLANE_IPS, (
        "kubeEtcd.endpoints must list the three control-plane minis in order. "
        "Omitting it leaves the chart on pod-selector discovery, which matches "
        "nothing on Talos and yields the empty Endpoints object this whole "
        f"change exists to fix. Got: {kube_etcd.get('endpoints')!r}"
    )

    endpoints = _kube_etcd_scrape_endpoints()
    assert len(endpoints) == 1, (
        "expected exactly one kubeEtcd.vmScrape.spec.endpoints entry; the "
        f"override REPLACES the chart default wholesale. Got {len(endpoints)}"
    )
    endpoint = endpoints[0]

    assert endpoint.get("scheme") == "http", (
        "the etcd scrape endpoint must use `scheme: http`. The metrics "
        "listener is plain HTTP by design; the chart's default `https` "
        f"produces a target that fails forever. Got: {endpoint.get('scheme')!r}"
    )
    assert endpoint.get("port") == METRICS_PORT_NAME, (
        f"the etcd scrape endpoint must name port `{METRICS_PORT_NAME}` — the "
        "port name the chart gives the Service it renders. Got: "
        f"{endpoint.get('port')!r}"
    )

    forbidden = sorted(
        key
        for key in ("bearerTokenFile", "bearerTokenSecret", "tlsConfig")
        if key in endpoint
    )
    assert not forbidden, (
        "the etcd scrape endpoint carries chart-default authentication: "
        f"{forbidden}. Port 2381 is unauthenticated plain HTTP — a bearer "
        "token or TLS config there is not merely redundant, it is the "
        "kubeadm-shaped default that makes the target fail while the values "
        "read as careful."
    )


# ---------------------------------------------------------------------------
# The two halves cannot drift apart.
#
# These are the whole reason this file exists. The ConfigPatch and the chart
# values live in different directories and are applied by different tools —
# `omnictl`, by hand, by an operator; and ArgoCD, from `main` — so no deploy,
# no sync status and no review of either file alone can notice that they no
# longer agree. A port typo in either, or a node IP that moves, reproduces
# precisely the silent empty-target failure this layer was written to fix:
# configuration that looks complete, produces no error, and yields no data.
#
# Both are written as DERIVATIONS. Restating the port or the addresses here
# would make this file a third copy that drifts alongside the other two, which
# is the opposite of a guard.
# ---------------------------------------------------------------------------


def test_listener_port_matches_the_scrape_target_port():
    """The port etcd listens on is the port the scrape dials.

    Parsed out of the ConfigPatch's URL rather than asserted as a literal, so
    the test cannot agree with a typo it also contains.
    """
    url = _listen_metrics_urls()
    listener_port = urlparse(url).port
    assert listener_port is not None, (
        f"could not parse a port out of `listen-metrics-urls: {url}` in "
        f"{CONFIGPATCH.relative_to(REPO)} — etcd needs an explicit port here, "
        "and this guard cannot compare what it cannot read"
    )

    target_port = (_kube_etcd().get("service") or {}).get("targetPort")

    assert listener_port == target_port, (
        "PORT MISMATCH between the two halves of the etcd scrape:\n"
        f"  {CONFIGPATCH.relative_to(REPO)} opens etcd's metrics listener on "
        f"port {listener_port} (listen-metrics-urls: {url})\n"
        f"  {VM_VALUES.relative_to(REPO)} dials kubeEtcd.service.targetPort = "
        f"{target_port!r}\n"
        "These files are applied by different tools and nothing else connects "
        "them, so a mismatch does not fail a deploy — it produces a scrape "
        "target that is down forever while both files look correct in "
        "isolation. That is the exact failure this layer exists to fix."
    )


def test_endpoints_match_the_documented_control_plane_ips():
    """The scrape targets the nodes the repo says are the control plane.

    Frank's node IPs are static, fixed by Talos machine config — so this is not
    guarding against drift in the addresses so much as against the chart values
    and the machine table disagreeing about which machines run etcd. A stale IP
    here scrapes nothing and reports nothing.
    """
    documented = CONTROL_PLANE_IPS
    configured = _kube_etcd().get("endpoints")

    assert configured == documented, (
        "ENDPOINT MISMATCH between the etcd scrape and the repo's machine "
        "table:\n"
        f"  {VM_VALUES.relative_to(REPO)} kubeEtcd.endpoints = {configured!r}\n"
        f"  {INFRA_RULE.relative_to(REPO)} control-plane rows = {documented!r}\n"
        "etcd runs on the control plane and nowhere else. An address that is "
        "in one list and not the other is either a node that is scraped but "
        "runs no etcd, or an etcd member that is not scraped at all — and "
        "neither shows up as an error, only as missing series."
    )
