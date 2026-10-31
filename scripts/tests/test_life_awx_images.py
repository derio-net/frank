"""R2: images the AWX operator would otherwise choose itself are pinned in the CR."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _spec():
    docs = yaml.safe_load_all((ROOT / "apps/awx/manifests/awx.yaml").read_text())
    return next(d for d in docs if d and d.get("kind") == "AWX")["spec"]


def test_awx_cr_pins_operator_chosen_images():
    spec = _spec()
    assert spec["postgres_image"] == "quay.io/sclorg/postgresql-15-c9s"
    assert spec["postgres_image_version"] == "20260527@sha256:da362fb44ceca3669d3f7d9272a4f18d198a0db057add34a307083cb3916338f"
    assert spec["redis_image"] == "docker.io/redis"
    assert spec["redis_image_version"] == "7@sha256:b2b95679e3b46fb51864949ed25ea976fc3a6bcc00a40a1bc00d568cb2822e50"
