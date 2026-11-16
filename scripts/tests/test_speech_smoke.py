"""Smoke guard for the speech-service feature: its spec, plan and acceptance fragment exist."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SLUG = "2026-11-16--infer--speech-service"


def test_speech_spec_plan_and_acceptance_exist():
    assert (REPO / f"docs/superpowers/specs/{SLUG}-design.md").is_file()
    plan = REPO / f"docs/superpowers/plans/{SLUG}"
    assert (plan / "_meta.yaml").is_file() and (plan / "ops.yaml").is_file()
    assert (REPO / f"docs/acceptance/features/{SLUG}.yaml").is_file()
