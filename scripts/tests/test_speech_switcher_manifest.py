"""gpu-switcher manifest carries the speech group and a bumped image tag.

Mirrors the Go grammar (ParseWorkloads): name:namespace:deployment[@group].
"""
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "apps/gpu-switcher/manifests/deployment.yaml"
ENTRY = re.compile(r"^([^:@,]+):([^:@,]+):([^:@,]+)(?:@([^:@,]+))?$")
DECLARED_VERSION = "v0.1.2"


def _container():
    doc = yaml.safe_load(DEPLOY.read_text())
    return doc["spec"]["template"]["spec"]["containers"][0]


def _workloads():
    env = {e["name"]: e["value"] for e in _container()["env"]}
    out = []
    for entry in env["WORKLOADS"].split(","):
        m = ENTRY.match(entry)
        assert m, f"malformed WORKLOADS entry: {entry!r}"
        out.append(m.groups())
    return out


def test_speech_joins_the_ollama_group():
    by_name = {n: (ns, dep, grp) for n, ns, dep, grp in _workloads()}
    assert by_name["speech"] == ("speech", "speech", "ollama")
    assert by_name["ollama"][2] is None
    assert by_name["comfyui"][2] is None


def test_image_tag_matches_declared_version():
    assert _container()["image"] == f"ghcr.io/derio-net/gpu-switcher:{DECLARED_VERSION}"
