"""Tripwire: the root Application is declared in git and tolerates controller-owned finalizers.

root sat OutOfSync for weeks (selfHeal retried 59 times, each retry filtered to
the drifting children) because ArgoCD 3.x adds pre-/post-delete finalizers to
Applications whose charts ship delete hooks, and root was never in git, so no
ignoreDifferences could exist (frank#956). Guards the declared manifest.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "apps/root/bootstrap/root-application.yaml"


def _load():
    return yaml.safe_load(MANIFEST.read_text())


def test_root_manifest_is_in_git_and_prunes():
    app = _load()
    assert app["kind"] == "Application" and app["metadata"]["name"] == "root"
    assert app["spec"]["source"]["path"] == "apps/root"
    assert app["spec"]["syncPolicy"]["automated"] == {"prune": True, "selfHeal": True}


def test_root_ignores_application_finalizers_in_the_diff_only():
    spec = _load()["spec"]
    rules = [r for r in spec["ignoreDifferences"] if r["kind"] == "Application"]
    assert rules and "/metadata/finalizers" in rules[0]["jsonPointers"]
    assert not any("jqPathExpressions" in r for r in spec["ignoreDifferences"])
    opts = spec["syncPolicy"].get("syncOptions", [])
    assert "RespectIgnoreDifferences=true" not in opts


def test_no_template_declares_controller_owned_finalizers():
    for f in (ROOT / "apps/root/templates").glob("*.yaml"):
        code = [l for l in f.read_text().splitlines() if not l.lstrip().startswith("#")]
        bad = [l for l in code if "pre-delete-finalizer" in l or "post-delete-finalizer" in l]
        assert not bad, f"{f.name} declares a controller-owned finalizer: {bad}"


def test_bootstrap_dir_is_outside_templates():
    assert MANIFEST.parent.name == "bootstrap"
    assert not list((ROOT / "apps/root/templates").glob("root*.yaml"))


def test_manual_op_documents_the_apply():
    ops = yaml.safe_load((ROOT / "docs/runbooks/manual-operations.yaml").read_text())
    ops = ops["operations"] if isinstance(ops, dict) else ops
    assert any(o["id"] == "argocd-root-bootstrap" for o in ops)
