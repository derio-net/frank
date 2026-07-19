"""Guard the surgical ArgoCD Pod-exclusion that lets the cnc-staging vCluster be
registered as an ArgoCD cluster target WITHOUT crashing the application-controller.

Root cause (fr-debugging 2026-07-19, docs/superpowers/debugging/): ArgoCD v3.3.2
vendors kubectl v0.34.0, whose pod-resource helper panics
`assignment to entry in nil map` in
controller/cache.populatePodInfo -> kubectl resource.PodRequestsAndLimits ->
maxResourceList when the cluster cache lists a Pod from a remote vCluster that
ships a LimitRange (argo-cd#26529 / kubernetes#136533). The panic is UNCAUGHT in a
cache-sync goroutine, so it kills the whole controller process -> cluster-wide
CrashLoopBackOff on the next cold cache rebuild. The permanent fix ships in
ArgoCD 3.5 (client-go bumped to 1.36.1); it is NOT backported to 3.4.

Workaround (maintainer-endorsed in #26529): exclude Pod from the cluster cache,
but SCOPED to the vCluster server URL only. `resource.exclusions` matches on
apiGroups + kinds + `clusters` (a glob list of cluster URLs), so a scoped entry
skips Pods ONLY on the vCluster while the main cluster keeps full per-pod
visibility for all other apps.

The load-bearing invariant these guards lock is that the exclusion stays
SURGICAL. A GLOBAL Pod exclusion (empty/absent/over-broad `clusters`) would
silently strip the pod tree + health rollup from ALL ~60 main-cluster apps — a
catastrophic, quiet regression. That the panic is ACTUALLY gone on
re-registration is a RUNTIME fact, proven by the manual on-cluster spike, NOT
here (helm template proves schema only; trusting schema over runtime is exactly
the #651 trap).

LOCAL guards (frank does not run scripts/tests/ in CI); they shell out to
`helm template --repo https://argoproj.github.io/argo-helm` and are fail-closed
(non-zero return / missing render -> assertion error, never a false-green). In a
runner without helm or without egress they go red on infra, not logic.
"""

import subprocess
from fnmatch import fnmatch
from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not skip

REPO = Path(__file__).resolve().parents[2]
ARGOCD_VALUES = REPO / "apps/argocd/values.yaml"
CHART_REPO = "https://argoproj.github.io/argo-helm"
CHART_VERSION = "9.4.6"
VCLUSTER_URL = "https://cnc-staging.cnc-staging-vcluster.svc:443"
MAIN_CLUSTER_URL = "https://kubernetes.default.svc"


def _render(*extra_args: str) -> str:
    out = subprocess.run(
        [
            "helm", "template", "argocd", "argo-cd",
            "--repo", CHART_REPO, "--version", CHART_VERSION,
            *extra_args,
        ],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, f"helm template argo-cd failed:\n{out.stderr}"
    return out.stdout


def _cm_from(rendered: str) -> dict:
    for d in yaml.safe_load_all(rendered):
        if (
            d
            and d.get("kind") == "ConfigMap"
            and d.get("metadata", {}).get("name") == "argocd-cm"
        ):
            return d.get("data", {}) or {}
    raise AssertionError("argocd-cm ConfigMap not rendered by the argo-cd chart")


def _exclusions_of(data: dict) -> list:
    raw = data.get("resource.exclusions")
    assert raw, "argocd-cm has no resource.exclusions"
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, list), f"resource.exclusions must be a list, got {type(parsed)}"
    return parsed


def _exclusions() -> list:
    """Our effective exclusions (chart rendered WITH the repo values)."""
    return _exclusions_of(_cm_from(_render("-f", str(ARGOCD_VALUES))))


def _default_exclusions() -> list:
    """The chart's pristine default exclusions (rendered with NO overrides)."""
    return _exclusions_of(_cm_from(_render()))


def _pod_exclusion_entries(entries: list) -> list:
    """Entries that would exclude core-group Pods (kinds ~ Pod/*, apiGroups ~ ''/*)."""
    hits = []
    for e in entries:
        kinds = e.get("kinds") or []
        groups = e.get("apiGroups") or []
        if ("Pod" in kinds or "*" in kinds) and ("" in groups or "*" in groups):
            hits.append(e)
    return hits


def test_argocd_excludes_vcluster_pods():
    """A Pod exclusion scoped to the cnc-staging vCluster URL is present."""
    pods = _pod_exclusion_entries(_exclusions())
    assert pods, "no Pod exclusion entry found in resource.exclusions"
    assert any(
        any(fnmatch(VCLUSTER_URL, g) for g in (e.get("clusters") or []))
        for e in pods
    ), f"no Pod exclusion scoped to the vCluster URL {VCLUSTER_URL}"


def test_pod_exclusion_is_never_global():
    """CRITICAL: every Pod exclusion MUST carry a non-empty `clusters` scope.

    A global Pod exclusion would strip pod tree + health from ALL ~60
    main-cluster apps — the exact silent regression this fix must avoid.
    """
    for e in _pod_exclusion_entries(_exclusions()):
        clusters = e.get("clusters") or []
        assert clusters, f"Pod exclusion is GLOBAL (no `clusters` scope): {e}"


def test_main_cluster_pods_are_never_excluded():
    """No Pod-exclusion cluster glob may match the main cluster server URL."""
    for e in _pod_exclusion_entries(_exclusions()):
        for glob in (e.get("clusters") or []):
            assert not fnmatch(MAIN_CLUSTER_URL, glob), (
                f"Pod-exclusion glob {glob!r} matches the main cluster "
                f"{MAIN_CLUSTER_URL} — would strip pod info from every "
                f"main-cluster app: {e}"
            )


def _canon(entries: list) -> set:
    """Order-insensitive signature of each exclusion entry (ignores comments)."""
    return {
        (
            frozenset(e.get("apiGroups") or []),
            frozenset(e.get("kinds") or []),
            frozenset(e.get("clusters") or []),
        )
        for e in entries
    }


def test_chart_default_exclusions_are_preserved():
    """Setting resource.exclusions REPLACES the chart default, so a stale copy (or
    a chart bump) could silently drop the defaults (Endpoints, Lease, Cilium
    identities, Kyverno reports, ...). Assert every default entry still renders."""
    missing = _canon(_default_exclusions()) - _canon(_exclusions())
    assert not missing, (
        "our resource.exclusions dropped chart-default entries "
        f"(re-sync from the argo-cd {CHART_VERSION} default): {missing}"
    )
