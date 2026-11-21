"""gpu-switcher manifest carries the speech group and a bumped image tag.

Grammar validity is enforced by the Go test TestShippedWorkloadsValueParses
(which feeds this very manifest to ParseWorkloads); this file only does a
minimal split to assert the speech/ollama membership. The image is built by
.github/workflows/build-gpu-switcher.yml on push to main; the Deployment pin
must equal the workflow's GPU_SWITCHER_VERSION or a merge pins a tag CI never
builds.
"""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "apps/gpu-switcher/manifests/deployment.yaml"
WORKFLOW = REPO / ".github/workflows/build-gpu-switcher.yml"
DECLARED_VERSION = "v0.1.2"


def _container():
    doc = yaml.safe_load(DEPLOY.read_text())
    return doc["spec"]["template"]["spec"]["containers"][0]


def _workloads():
    env = {e["name"]: e["value"] for e in _container()["env"]}
    out = []
    for entry in env["WORKLOADS"].split(","):
        name, namespace, rest = entry.split(":")
        deployment, _, group = rest.partition("@")
        out.append((name, namespace, deployment, group or None))
    return out


def test_speech_joins_the_ollama_group():
    by_name = {n: (ns, dep, grp) for n, ns, dep, grp in _workloads()}
    assert by_name["speech"] == ("speech", "speech", "ollama")
    assert by_name["ollama"][2] is None
    assert by_name["comfyui"][2] is None


def test_image_tag_matches_declared_version():
    assert _container()["image"] == f"ghcr.io/derio-net/gpu-switcher:{DECLARED_VERSION}"


def test_ci_builds_the_pinned_tag():
    wf = yaml.safe_load(WORKFLOW.read_text())
    assert wf["env"]["GPU_SWITCHER_VERSION"] == DECLARED_VERSION
    # PyYAML reads the bare `on:` key as boolean True.
    on = wf.get("on", wf.get(True))
    paths = on["push"]["paths"]
    assert "apps/gpu-switcher/app/**" in paths
    assert ".github/workflows/build-gpu-switcher.yml" in paths
    assert on["push"]["branches"] == ["main"]
    step = next(s for s in wf["jobs"]["build"]["steps"] if s.get("name") == "Build and push")
    assert step["with"]["context"] == "apps/gpu-switcher/app"
    assert "${{ env.GPU_SWITCHER_VERSION }}" in step["with"]["tags"]
