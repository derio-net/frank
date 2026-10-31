"""renovate.json5 is generated from update-policy.yaml and never automerges (spec R4-R7)."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import life_policy  # noqa: E402

FILE = ROOT / "renovate.json5"


def load():
    """Minimal json5 loader: the file is JSON plus full-line // comments."""
    text = "\n".join(l for l in FILE.read_text().splitlines() if not l.lstrip().startswith("//"))
    return json.loads(text)


def test_automerge_is_false_globally_and_in_every_rule():
    cfg = load()
    assert cfg["automerge"] is False
    assert cfg["platformAutomerge"] is False
    assert cfg["packageRules"]
    for rule in cfg["packageRules"]:
        assert rule["automerge"] is False, rule
    assert cfg["vulnerabilityAlerts"]["automerge"] is False


def test_dashboard_and_approval():
    cfg = load()
    assert cfg["dependencyDashboard"] is True
    for rule in cfg["packageRules"]:
        path = rule["labels"][0].removeprefix("path:")
        assert rule["dependencyDashboardApproval"] is (path in ("session", "operator-runbook")), rule
    labels = {r["labels"][0] for r in cfg["packageRules"]}
    assert {"path:session", "path:operator-runbook", "path:batch-approve", "path:auto-merge"} <= labels


def test_vulnerability_alerts_are_labelled_security():
    va = load()["vulnerabilityAlerts"]
    assert va["enabled"] is True
    assert va["labels"] == ["security"]


def test_managers():
    cfg = load()
    assert {"argocd", "helm-values", "kubernetes", "kustomize"} <= set(cfg["enabledManagers"])


def test_custom_managers_cover_os_and_omni_declarations():
    managers = load()["customManagers"]

    def covering(path):
        return [m for m in managers if any(re.search(p, path) for p in m["fileMatch"])]

    deps = {m["depNameTemplate"] for m in covering("versions/frank.yaml")}
    assert deps == {"siderolabs/talos", "kubernetes/kubernetes"}
    assert {m["depNameTemplate"] for m in covering("versions/hop.yaml")} == deps
    assert [m["depNameTemplate"] for m in covering("omni/omni/omni.env.template")] == ["siderolabs/omni"]
    for m in managers:
        assert m["datasourceTemplate"] == "github-releases"
    # the match strings really pick the declared value out of the real files
    for rel, dep in (("versions/frank.yaml", "siderolabs/talos"), ("versions/frank.yaml", "kubernetes/kubernetes"),
                     ("versions/hop.yaml", "siderolabs/talos"), ("omni/omni/omni.env.template", "siderolabs/omni")):
        m = next(m for m in covering(rel) if m["depNameTemplate"] == dep)
        assert re.search(m["matchStrings"][0].replace("(?<", "(?P<"), (ROOT / rel).read_text()), (rel, dep)


def test_batch_approve_rules_share_one_group():
    rules = [r for r in load()["packageRules"] if r["labels"] == ["path:batch-approve"]]
    assert rules
    assert len({r["groupName"] for r in rules}) == 1 and rules[0]["groupName"]
    for r in load()["packageRules"]:
        if r["labels"] != ["path:batch-approve"]:
            assert r["groupName"] is None, r


def test_stateful_apps_are_never_batched_or_auto_merged():
    facts = life_policy.load_facts()
    cfg = load()
    for rule in cfg["packageRules"]:
        if rule["labels"][0] in ("path:auto-merge", "path:batch-approve"):
            files = set(rule.get("matchFileNames", []))
            for app, f in facts.items():
                if f["stateful"] or f["rollout"]:
                    assert not files & set(f["paths"]), (app, rule["description"])


def test_committed_file_equals_the_emitted_one():
    assert FILE.read_text() == life_policy.emit_renovate()


def test_renovate_config_validator_passes():
    exe = shutil.which("renovate-config-validator")
    if not exe:
        pytest.skip("renovate-config-validator is not on PATH (npm renovate not installed here)")
    done = subprocess.run([exe, "--strict", str(FILE)], capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done.stdout + done.stderr
