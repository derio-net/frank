from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_spec_and_life_layer_exist():
    spec = ROOT / "docs/superpowers/specs/2026-10-31--life--update-security-lifecycle-design.md"
    assert spec.exists() and "## Requirements" in spec.read_text()
    layers = yaml.safe_load((ROOT / "docs/layers.yaml").read_text())["layers"]
    assert any(layer["code"] == "life" for layer in layers)
