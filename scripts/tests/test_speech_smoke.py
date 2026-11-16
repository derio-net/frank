"""Smoke guard for the speech-service feature: the design spec exists."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_speech_spec_exists():
    spec = REPO / "docs/superpowers/specs/2026-11-16--infer--speech-service-design.md"
    assert spec.is_file()
