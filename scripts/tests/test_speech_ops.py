"""The speech plan's fr ops must ACT, and must be runnable where `fr ops gate` runs.

Two failures shipped in this plan's first draft and passed `fr plan self-review`
(super-fr#1614):

* mutating ops whose `apply` only echoed instructions ("Build and push …"), so
  `fr ops apply` would have performed nothing;
* checks that called `docker`, which frank's ops devcontainer does not have.

These tests pin both properties for this plan's ops.yaml.
"""
import json
import re
import shlex
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "docs/superpowers/plans/2026-11-16--infer--speech-service/ops.yaml"
OPS_PROFILE = REPO / ".devcontainer/ops/devcontainer.json"
CHECK_SCRIPT = REPO / "scripts/ghcr-tag-pullable.sh"

# Commands available in frank's ops devcontainer: the base image's shell
# utilities plus its features (gh, kubectl/helm, python, uv). No docker.
OPS_TOOLS = {
    "bash", "sh", "test", "sleep", "seq", "for", "do", "done", "break", "grep", "cut",
    "curl", "python3", "gh", "kubectl", "helm", "fr", "uv", "true", "false",
}
PRINT_ONLY = {"echo", "printf", "cat"}


def _ops():
    return yaml.safe_load(OPS.read_text())["ops"]


def _commands(script):
    """First word of every simple command in a one-line shell script."""
    # Drop $(...) substitutions: their contents are checked separately below.
    subs = re.findall(r"\$\(([^()]*)\)", script)
    flat = re.sub(r"\$\([^()]*\)", "X", script)
    words = []
    for part in re.split(r"&&|\|\||;|\||\n", flat):
        part = part.strip()
        if not part:
            continue
        toks = shlex.split(part, posix=True)
        while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
            toks = toks[1:]
        if toks:
            words.append(toks[0])
    for s in subs:
        words.extend(_commands(s))
    return words


def test_every_mutating_apply_does_more_than_print():
    for op in _ops():
        if not op["mutating"]:
            continue
        cmds = _commands(op["apply"])
        assert cmds, op["id"]
        assert set(cmds) - PRINT_ONLY, f"{op['id']}: apply only prints {cmds}"


def test_every_command_exists_in_the_ops_profile():
    profile = json.loads(OPS_PROFILE.read_text())
    features = " ".join(profile.get("features", {}))
    assert "docker" not in features, "ops profile gained docker; revisit OPS_TOOLS"
    for op in _ops():
        for field in ("apply", "check"):
            for cmd in _commands(op[field]):
                assert cmd in OPS_TOOLS, f"{op['id']}.{field}: '{cmd}' is not in the ops profile"


def test_image_ops_check_anonymous_pullability():
    by_id = {op["id"]: op for op in _ops()}
    for op_id, repo in (("postmerge-gpu-switcher-image", "derio-net/gpu-switcher"),
                        ("postmerge-speech-image", "derio-net/speech")):
        op = by_id[op_id]
        assert op["phase"] == "post-merge"
        assert f"scripts/ghcr-tag-pullable.sh {repo}" in op["check"]
        assert "gh workflow run" in op["apply"] and "--exit-status" in op["apply"]


def test_check_script_refuses_bad_arguments_offline():
    for args in ([], ["noslash", "v1"], ["derio-net/x", "v1;rm"]):
        r = subprocess.run(["bash", str(CHECK_SCRIPT), *args], capture_output=True, text=True)
        assert r.returncode == 2, (args, r.stderr)


GPU_OPERATOR_VALUES = REPO / "apps/gpu-operator/values.yaml"
GPU_OPERATOR_APP = REPO / "apps/root/templates/gpu-operator.yaml"


def test_timeslice_op_patches_the_clusterpolicy_with_the_declared_config():
    """ArgoCD never applies the ClusterPolicy spec: the gpu-operator Application
    ignores /spec (the operator's webhook fills in defaults). The first gate run
    synced both apps, read OPEN, and the live ClusterPolicy had no
    devicePlugin.config (2026-11-21). So the op must patch the live object with
    exactly the block values.yaml declares for a fresh install."""
    assert "- /spec" in GPU_OPERATOR_APP.read_text(), "ClusterPolicy /spec no longer ignored: revisit this op"
    op = {o["id"]: o for o in _ops()}["postmerge-timeslice-allocatable"]
    m = re.search(r"kubectl patch clusterpolicy cluster-policy --type=merge -p '(\{.*?\})'", op["apply"])
    assert m, "apply must patch the live ClusterPolicy"
    patched = json.loads(m.group(1))["spec"]["devicePlugin"]["config"]
    declared = yaml.safe_load(GPU_OPERATOR_VALUES.read_text())["devicePlugin"]["config"]
    assert patched == declared
    assert "patch application" not in op["apply"], "syncing ArgoCD apps cannot change an ignored /spec"
    assert op["mutating"] is True
    assert op.get("side_effects"), "the plugin roll briefly drops gpu-1's GPU resource: declare it"
    assert "/spec/devicePlugin/config" in op.get("undo", "")
