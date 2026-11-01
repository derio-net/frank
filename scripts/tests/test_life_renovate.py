"""renovate.json5 is generated from update-policy.yaml and never automerges (spec R4-R7)."""
import json
import os
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
        return [m for m in managers if any(re.search(p[1:-1], path) for p in m["managerFilePatterns"])]

    for cluster in ("frank", "hop"):
        assert {m["depNameTemplate"] for m in covering(f"versions/{cluster}.yaml")} == {
            f"{cluster}/talos", f"{cluster}/kubernetes"}
    upstream = {m["depNameTemplate"]: m["packageNameTemplate"] for m in managers if "packageNameTemplate" in m}
    assert upstream["hop/talos"] == "siderolabs/talos" and upstream["frank/kubernetes"] == "kubernetes/kubernetes"
    assert [m["depNameTemplate"] for m in covering("omni/omni/omni.env.template")] == ["siderolabs/omni"]
    for m in managers:
        assert m["datasourceTemplate"] == "github-releases"
    # the match strings really pick the declared value out of the real files
    for rel, dep in (("versions/frank.yaml", "frank/talos"), ("versions/frank.yaml", "frank/kubernetes"),
                     ("versions/hop.yaml", "hop/talos"), ("versions/hop.yaml", "hop/kubernetes"),
                     ("omni/omni/omni.env.template", "siderolabs/omni")):
        m = next(m for m in covering(rel) if m["depNameTemplate"] == dep)
        assert re.search(m["matchStrings"][0].replace("(?<", "(?P<"), (ROOT / rel).read_text()), (rel, dep)


def test_no_rule_groups_updates_because_the_console_builds_the_batch():
    assert "groupName" not in json.dumps(load()), "the console builds the batch; Renovate opens one PR per dependency"


def test_commits_are_created_through_the_api_so_github_verifies_them():
    assert load()["platformCommit"] == "enabled"


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


def _validator():
    exe = shutil.which("renovate-config-validator")
    if exe:
        return [exe]
    if os.environ.get("CI") == "true" and shutil.which("npx"):
        return ["npx", "--yes", "renovate@44.198.3", "renovate-config-validator"]
    return None


def test_renovate_config_validator_passes():
    cmd = _validator()
    if cmd is None:
        if os.environ.get("CI") == "true":
            pytest.fail("CI must validate renovate.json5: neither renovate-config-validator nor npx is available")
        pytest.skip("renovate-config-validator is not on PATH and CI is not set (no npm installs here)")
    # Renovate 44's validator has no --strict ("error: unknown option '--strict'"), so the
    # check --strict used to make — a config that needs migrating is a failure — is asserted
    # here on the validator's own output instead of being silently dropped.
    done = subprocess.run(cmd + [str(FILE)], capture_output=True, text=True, cwd=ROOT, timeout=900)
    out = done.stdout + done.stderr
    assert done.returncode == 0, out
    assert "migration" not in out.lower(), "renovate.json5 needs migrating:\n" + out


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield f"{path}/{k}", k, v
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def test_every_automerge_key_anywhere_is_false_and_there_is_no_automerge_type():
    found = 0
    for where, key, value in _walk(load()):
        if "automerge" in key.lower():
            found += 1
            assert key != "automergeType", where
            assert value is False, where
    assert found > 10


def test_deprecated_fileMatch_and_null_values_are_not_emitted():
    for where, key, value in _walk(load()):
        assert key != "fileMatch", where
        assert value is not None, where


# ---------------------------------------------------------------- simulated Renovate matching
def _glob(pattern):
    rx = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.compile(rx + r"\Z")


def simulate(rules, *, file=None, package=None, dep=None, update="patch"):
    """Last matching packageRule wins for `labels`; a rule matches when ALL its matchers match."""
    label = None
    for rule in rules:
        if "matchUpdateTypes" in rule and update not in rule["matchUpdateTypes"]:
            continue
        if "matchFileNames" in rule and not (file and any(_glob(g).match(file) for g in rule["matchFileNames"])):
            continue
        if "matchPackageNames" in rule and package not in rule["matchPackageNames"]:
            continue
        if "matchDepNames" in rule and dep not in rule["matchDepNames"]:
            continue
        label = rule["labels"][0].removeprefix("path:")
    return label


def _concrete(globs):
    return [g.replace("/**", "/some/file.yaml") for g in globs]


def test_generated_rules_agree_with_resolve_for_every_app_chart_and_dep():
    rules = load()["packageRules"]
    facts = life_policy.load_facts()
    for ut in life_policy.UPDATE_TYPES:
        for key, f in facts.items():
            want = life_policy.resolve({"app": key}, ut)
            for file in _concrete(f["paths"]):
                got = simulate(rules, file=file, update=ut)
                assert got == want, (key, file, ut, got, want)
                for chart in f["charts"] or [None]:
                    got = simulate(rules, file=file, package=chart, update=ut)
                    # a chart shared with a stricter app may only make the result stricter
                    assert life_policy.RANK[got] >= life_policy.RANK[want], (key, chart, ut, got, want)
        for chart in {c for f in facts.values() for c in f["charts"]}:
            want = life_policy.resolve({"chart": chart}, ut)
            assert simulate(rules, file="unrelated.yaml", package=chart, update=ut) in (want, life_policy.policy_default(ut)), (chart, ut)
        for dep, name in life_policy.DEP_NAMES.items():
            want = life_policy.resolve({"dep": dep}, ut)
            got = simulate(rules, dep=name, update=ut)
            assert got == want, (dep, ut, got, want)


def test_unattended_tool_images_simulate_to_session():
    rules = load()["packageRules"]
    for image in ("renovate/renovate", "ghcr.io/derio-net/cluster-update-fr", "ghcr.io/derio-net/upgrade-session"):
        for ut in life_policy.UPDATE_TYPES:
            assert simulate(rules, file="apps/renovate/manifests/cronjob.yaml", package=image, update=ut) == "session"
