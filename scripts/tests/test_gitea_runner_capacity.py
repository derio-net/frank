"""Guard: runner memory limit 2Gi, pinned to pc-1, capacity 2 (frank#875, R18)."""

from pathlib import Path

import yaml

RUNNER_DIR = Path(__file__).resolve().parents[2] / "apps/gitea-runner/manifests"


def _deployment():
    for d in yaml.safe_load_all((RUNNER_DIR / "deployment.yaml").read_text()):
        if d and d.get("kind") == "Deployment":
            return d
    raise AssertionError("no Deployment")


def test_runner_container_memory_limit_is_2gi():
    spec = _deployment()["spec"]["template"]["spec"]
    runner = next(c for c in spec["containers"] if c["name"] == "runner")
    assert runner["resources"]["limits"]["memory"] == "2Gi"


def test_runner_stays_on_pc1():
    spec = _deployment()["spec"]["template"]["spec"]
    assert spec["nodeSelector"] == {"kubernetes.io/hostname": "pc-1"}


def test_runner_capacity_is_2():
    cfg = yaml.safe_load((RUNNER_DIR / "files/config.yaml").read_text())
    assert cfg["runner"]["capacity"] == 2
