"""A Service pinned to a node's L2 announcement stays pinned.

Cilium 1.17 does not restrict the L2 election to nodes with a local endpoint, so an
externalTrafficPolicy: Local LoadBalancer can be announced by a node that cannot
serve it (paperclip-lb on raspi-1 while its pod ran on gpu-1: direct connections
refused). The fix is a label on the Service plus a node-pinned policy, AND the
default policy must exclude the label (policies are additive).
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
LABEL = "l2.derio.net/pinned"


def _policies() -> dict:
    docs = yaml.safe_load_all((REPO / "apps/cilium/manifests/l2-policy.yaml").read_text())
    return {d["metadata"]["name"]: d["spec"] for d in docs if d}


def test_default_policy_excludes_pinned_services():
    exprs = _policies()["default-l2-policy"].get("serviceSelector", {}).get("matchExpressions", [])
    assert {"key": LABEL, "operator": "DoesNotExist"} in exprs


def test_pinned_policy_selects_label_and_node():
    spec = _policies()["pinned-gpu-1-l2-policy"]
    assert spec["serviceSelector"]["matchLabels"] == {LABEL: "gpu-1"}
    assert spec["nodeSelector"]["matchLabels"] == {"kubernetes.io/hostname": "gpu-1"}


def test_paperclip_lb_is_pinned_to_the_node_its_pod_runs_on():
    svc = yaml.safe_load((REPO / "apps/paperclip/manifests/service-lb.yaml").read_text())
    assert svc["metadata"]["labels"][LABEL] == "gpu-1"
    assert svc["spec"]["externalTrafficPolicy"] == "Local"
    dep = next(
        d for d in yaml.safe_load_all((REPO / "apps/paperclip/manifests/deployment.yaml").read_text())
        if d and d["kind"] == "Deployment"
    )
    assert dep["spec"]["template"]["spec"]["nodeSelector"] == {"kubernetes.io/hostname": "gpu-1"}, (
        "the pin label names gpu-1; if the pod moves, move the label and policy with it"
    )
