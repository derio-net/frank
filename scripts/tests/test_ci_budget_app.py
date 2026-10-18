"""Guard: the ci-budget Application and its kustomize skeleton."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "apps/ci-budget"
TEMPLATE = REPO_ROOT / "apps/root/templates/ci-budget.yaml"


def _template():
    text = re.sub(r"\{\{.*?\}\}", "x", TEMPLATE.read_text())
    return yaml.safe_load(text)


def test_template_sync_options():
    spec = _template()["spec"]
    assert spec["source"]["path"] == "apps/ci-budget"
    assert spec["destination"]["namespace"] == "tekton-pipelines"
    sp = spec["syncPolicy"]
    assert sp["automated"]["selfHeal"] is True
    assert sp["automated"]["prune"] is True
    assert "CreateNamespace=false" in sp["syncOptions"]
    assert "ServerSideApply=true" in sp["syncOptions"]


def test_prune_true_is_explained():
    assert "configMapGenerator" in TEMPLATE.read_text()
    assert "ci-budget-state" in TEMPLATE.read_text()


def test_kustomization_has_no_top_level_namespace():
    k = yaml.safe_load((APP_DIR / "kustomization.yaml").read_text())
    assert "namespace" not in k


@pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl missing")
def test_kustomize_renders_hashed_config():
    out = subprocess.run(
        ["kubectl", "kustomize", str(APP_DIR)],
        capture_output=True, text=True, check=True,
    ).stdout
    docs = [d for d in yaml.safe_load_all(out) if d]
    cms = [d for d in docs if d["kind"] == "ConfigMap"]
    assert any(
        re.fullmatch(r"ci-budget-config-[a-z0-9]+", c["metadata"]["name"])
        and c["metadata"]["namespace"] == "tekton-pipelines"
        and "tiers.yaml" in c["data"]
        for c in cms
    ), [c["metadata"]["name"] for c in cms]
