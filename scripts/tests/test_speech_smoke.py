"""Smoke guard for the speech-service feature: its spec, plan and acceptance fragment exist.

fr archives a closed-out run's spec and plan to docs/superpowers/implemented/,
so each is looked up live first, then archived.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SLUG = "2026-11-16--infer--speech-service"


def _live_or_archived(rel):
    for base in ("docs/superpowers", "docs/superpowers/implemented"):
        p = REPO / base / rel
        if p.exists():
            return p
    return REPO / "docs/superpowers" / rel


def test_speech_spec_plan_and_acceptance_exist():
    assert _live_or_archived(f"specs/{SLUG}-design.md").is_file()
    plan = _live_or_archived(f"plans/{SLUG}")
    assert (plan / "_meta.yaml").is_file() and (plan / "ops.yaml").is_file()
    assert (REPO / f"docs/acceptance/features/{SLUG}.yaml").is_file()
