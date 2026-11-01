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


def _env(name):
    text = (ROOT / "omni/omni/omni.env.template").read_text()
    m = re.search(rf"^{name}=(.*)$", text, re.M)
    return m.group(1).strip() if m else None


def test_omni_version_pinned_and_effective():
    """compose.yaml consumes OMNI_IMG_TAG; the template may be copied to .env with no
    shell expansion, so the effective tag must be a literal, equal to the Renovate anchor."""
    version, tag = _env("OMNI_VERSION"), _env("OMNI_IMG_TAG")
    assert version and re.fullmatch(r"v\d+\.\d+\.\d+", version)
    assert tag == version, "OMNI_IMG_TAG must be the literal pinned tag, not ${...}"
    assert "${OMNI_IMG_TAG}" in (ROOT / "omni/omni/compose.yaml").read_text()
