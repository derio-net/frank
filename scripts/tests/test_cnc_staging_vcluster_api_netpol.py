"""Guard that the cnc-staging vCluster API stays reachable by BOTH consumers.

REGRESSION (2026-07-20): the vCluster's CoreDNS could not reach the vCluster API,
so it had no Service/EndpointSlice data and answered NOTHING — every in-vCluster
name NXDOMAINed. cncd's agent-session dispatch died at:

    dial tcp: lookup cnc-node on <kube-dns>:53: no such host

and the run failed instantly, before ever contacting the node.

Cause was an interaction between two individually-correct changes:
  - #656 added an ingress policy selecting the vCluster control-plane pod that
    allowed ONLY the argocd namespace, reasoning (correctly, at the time) that
    NetworkPolicies are additive and the chart's vc-cp-* policy already allowed
    in-vCluster pods.
  - #657 then DELETED the vc-* policies (their egress excluded 10/8 and blocked
    the stack's ClusterIP traffic).

The union collapsed to the argocd rule alone, and because ANY NetworkPolicy
selecting a pod makes it default-deny for unnamed ingress, the vCluster's own
pods lost API access. Neither PR was wrong alone — the break lived in the seam.

So this guards the invariant that outlived both: whatever policy selects the
vCluster control-plane pod must admit the vCluster's own namespace AND argocd.

LOCAL guards (frank does not run scripts/tests/ in CI); fail-closed.
"""

import subprocess
from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not skip

REPO = Path(__file__).resolve().parents[2]
HOST_APP = REPO / "apps/cnc-staging-host/manifests"
API_PORT = 8443


def _netpols():
    out = subprocess.run(
        ["kustomize", "build", str(HOST_APP)], capture_output=True, text=True
    )
    assert out.returncode == 0, f"kustomize build failed:\n{out.stderr}"
    return [
        d for d in yaml.safe_load_all(out.stdout)
        if d and d.get("kind") == "NetworkPolicy"
    ]


def _cp_policies():
    """Policies that select the vCluster control-plane pod (release=cnc-staging)."""
    hits = []
    for np in _netpols():
        sel = (np["spec"].get("podSelector") or {}).get("matchLabels") or {}
        if sel.get("release") == "cnc-staging":
            hits.append(np)
    assert hits, "no NetworkPolicy selects the vCluster control-plane pod"
    return hits


def _rules_allowing(np, predicate):
    for rule in np["spec"].get("ingress") or []:
        ports = [p.get("port") for p in (rule.get("ports") or [])]
        if API_PORT not in ports:
            continue
        for src in rule.get("from") or []:
            if predicate(src):
                return True
    return False


def test_argocd_can_reach_the_vcluster_api():
    """Without this ArgoCD cannot sync the apps INTO the vCluster (#656)."""
    ok = any(
        _rules_allowing(
            np,
            lambda s: (s.get("namespaceSelector") or {})
            .get("matchLabels", {})
            .get("kubernetes.io/metadata.name") == "argocd",
        )
        for np in _cp_policies()
    )
    assert ok, f"no ingress rule admits the argocd namespace on {API_PORT}"


def test_vcluster_own_pods_can_reach_the_vcluster_api():
    """THE REGRESSION GUARD. An empty podSelector in `from` means every pod in the
    policy's own namespace — where the vCluster's synced pods (CoreDNS!) run.

    Without it CoreDNS cannot watch Services/EndpointSlices, so it answers no
    in-vCluster name and cncd's dispatch dies on `no such host`.
    """
    ok = any(
        _rules_allowing(np, lambda s: s.get("podSelector") == {})
        for np in _cp_policies()
    )
    assert ok, (
        f"no ingress rule admits the vCluster's own namespace on {API_PORT} — "
        "CoreDNS will lose API access and every in-vCluster name will NXDOMAIN"
    )


def test_control_plane_policies_are_ingress_only():
    """These policies must not add an egress policyType: doing so would flip the
    control-plane pod to default-deny EGRESS too — the exact class of breakage
    #657 had to undo on the chart's vc-* policies."""
    for np in _cp_policies():
        types = np["spec"].get("policyTypes") or []
        assert "Egress" not in types, (
            f"{np['metadata']['name']} adds an Egress policyType; that would "
            "default-deny the control-plane pod's egress (see #657)"
        )
