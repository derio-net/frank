"""Guard: the PipelineRun TTL GC sweeps EVERY namespace git creates PipelineRuns in.

frank#791. The GC (`apps/tekton/manifests/pipelinerun-ttl-gc.yaml`) hard-coded
`-n tekton-pipelines`, and its Role existed only there. When the kid-laptops CI
trigger started creating PipelineRuns in `kid-laptops-ci` (2026-07-26), nothing
tied the two sets together. Those runs then sat unswept for 70+ days. Their
`longhorn-cicd` workspace PVCs never cascade-deleted, and each 1-replica volume
pinned a Longhorn instance-manager PDB at `disruptionsAllowed=0`, which stalled
`kubectl drain` during the #762 control-plane roll.

So the set the GC sweeps is DERIVED here from git: the namespace of every
PipelineRun a TriggerTemplate (or a raw manifest) creates. Adding a third CI
namespace without wiring the GC now fails a PR. Before this guard, it leaked
silently.
"""

import re
from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
GC = REPO / "apps/tekton/manifests/pipelinerun-ttl-gc.yaml"
GC_SA = "pipelinerun-ttl-gc"
GC_SA_NS = "tekton-pipelines"
SCAN_ROOTS = [REPO / "apps"]


def _docs(path: Path) -> list[dict]:
    try:
        return [d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict)]
    except yaml.YAMLError:
        return []  # Helm templates etc. — not plain manifests


def _pipelinerun_namespaces() -> set[str]:
    found: set[str] = set()
    for root in SCAN_ROOTS:
        for path in root.rglob("*.yaml"):
            if "vendor" in path.parts or "templates" in path.parts:
                continue
            for doc in _docs(path):
                doc_ns = (doc.get("metadata") or {}).get("namespace")
                if doc.get("kind") == "PipelineRun" and doc_ns:
                    found.add(doc_ns)
                if doc.get("kind") != "TriggerTemplate":
                    continue
                for rt in (doc.get("spec") or {}).get("resourcetemplates") or []:
                    if rt.get("kind") != "PipelineRun":
                        continue
                    ns = (rt.get("metadata") or {}).get("namespace") or doc_ns
                    assert ns, f"{path.relative_to(REPO)}: PipelineRun template with no namespace"
                    found.add(ns)
    return found


def _gc_docs() -> list[dict]:
    return _docs(GC)


def _gc_script() -> str:
    cron = next(d for d in _gc_docs() if d.get("kind") == "CronJob")
    container = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    return "\n".join(container["args"])


def _gc_namespaces() -> set[str]:
    m = re.search(r'^\s*NAMESPACES="([^"]+)"', _gc_script(), re.MULTILINE)
    assert m, 'GC script must declare its sweep set as NAMESPACES="ns1 ns2 ..."'
    return set(m.group(1).split())


def test_derivation_sees_both_known_pipelinerun_namespaces() -> None:
    # Positive control: if the scan silently found nothing, every assertion
    # below would pass vacuously.
    assert {"tekton-pipelines", "kid-laptops-ci"} <= _pipelinerun_namespaces()


def test_gc_sweeps_every_namespace_git_creates_pipelineruns_in() -> None:
    missing = _pipelinerun_namespaces() - _gc_namespaces()
    assert not missing, (
        f"PipelineRuns are created in {sorted(missing)} but pipelinerun-ttl-gc "
        "never sweeps them — they accumulate forever and leak their workspace PVCs "
        "(frank#791). Add them to NAMESPACES plus a Role/RoleBinding."
    )


def test_gc_script_has_no_hardcoded_namespace() -> None:
    script = _gc_script()
    assert not re.search(r"-n\s+tekton-pipelines\b", script), (
        "every kubectl call must target the loop's $ns, not a literal namespace"
    )


def test_every_swept_namespace_has_gc_rbac() -> None:
    docs = _gc_docs()
    for ns in sorted(_gc_namespaces()):
        roles = [
            d for d in docs
            if d.get("kind") == "Role" and d["metadata"].get("namespace") == ns
        ]
        verbs = {
            v
            for r in roles
            for rule in r.get("rules", [])
            if "pipelineruns" in rule.get("resources", [])
            and "tekton.dev" in rule.get("apiGroups", [])
            for v in rule.get("verbs", [])
        }
        assert {"list", "delete"} <= verbs, f"no Role granting list/delete pipelineruns in {ns}"
        role_names = {r["metadata"]["name"] for r in roles}
        bound = [
            d for d in docs
            if d.get("kind") == "RoleBinding"
            and d["metadata"].get("namespace") == ns
            and d["roleRef"]["kind"] == "Role"
            and d["roleRef"]["name"] in role_names
            and any(
                s.get("kind") == "ServiceAccount"
                and s.get("name") == GC_SA
                and s.get("namespace") == GC_SA_NS
                for s in d.get("subjects", [])
            )
        ]
        assert bound, f"no RoleBinding for {GC_SA_NS}/{GC_SA} in {ns}"


def test_summary_line_reports_per_namespace() -> None:
    # The summary line is the only thing that makes a silent GC failure
    # visible (#723); it must say WHICH namespace each count belongs to.
    assert re.search(
        r"pipelinerun-ttl-gc result namespace=\$\{?ns\}?", _gc_script()
    ), "summary line must carry namespace=${ns}"
