"""Test the shared dossier parser against real fixtures.

Uses Paper 09 (9 sources covering all 5 type values) as the
comprehensive fixture, plus Paper 04 (4 types incl. `paper`)
and Paper 14 (4 types incl. one `postmortem`).
"""
from pathlib import Path
import pytest

from scripts.lib.dossier_parser import parse_dossier, get_primary_sources

REPO_ROOT = Path(__file__).resolve().parents[2]
DOSSIERS = REPO_ROOT / "docs" / "papers-dossiers"


def test_paper_09_has_nine_sources_all_five_types():
    sections = parse_dossier(DOSSIERS / "09-secrets-bootstrap" / "dossier.md")
    sources = get_primary_sources(sections)
    assert len(sources) == 9, f"expected 9 sources, got {len(sources)}"
    types = {s["type"] for s in sources}
    assert types == {"vendor-docs", "paper", "postmortem", "talk", "benchmark"}, (
        f"expected all 5 types, got {types}"
    )


def test_paper_04_includes_paper_type():
    sections = parse_dossier(DOSSIERS / "04-distributed-storage" / "dossier.md")
    sources = get_primary_sources(sections)
    types = {s["type"] for s in sources}
    assert "paper" in types
    assert len(types) >= 3


def test_paper_14_includes_postmortem_type():
    sections = parse_dossier(DOSSIERS / "14-progressive-delivery" / "dossier.md")
    sources = get_primary_sources(sections)
    types = {s["type"] for s in sources}
    assert "postmortem" in types
    assert len(types) >= 3


def test_every_source_has_required_fields():
    sections = parse_dossier(DOSSIERS / "09-secrets-bootstrap" / "dossier.md")
    sources = get_primary_sources(sections)
    for s in sources:
        assert "title" in s and s["title"]
        assert "url" in s and s["url"]
        assert "type" in s and s["type"]
        assert "quoted_passages" in s and isinstance(s["quoted_passages"], list) and s["quoted_passages"]
        assert "relevance" in s and s["relevance"]
