import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _load(name):
    path = ROOT / "versions" / f"{name}.yaml"
    text = path.read_text()
    return text, yaml.safe_load(text)


def _check(name, managed_by):
    text, data = _load(name)
    assert text.lstrip().startswith("#"), "header comment required"
    for key in ("talos", "kubernetes"):
        assert isinstance(data[key], str) and SEMVER.match(data[key]), key
    assert data["managed_by"] == managed_by


def test_frank_versions():
    _check("frank", "omni")


def test_hop_versions():
    _check("hop", "talosctl")


def test_omni_version_pinned():
    text = (ROOT / "omni/omni/omni.env.template").read_text()
    m = re.search(r"^OMNI_VERSION=(.*)$", text, re.M)
    assert m and re.fullmatch(r"v\d+\.\d+\.\d+", m.group(1).strip())
