#!/usr/bin/env python3
"""Shared parser for Frank Papers research dossiers.

Dossiers are markdown files where each `## H2` header begins a
section whose body is YAML. Two consumers depend on this parser:
`scripts/validate-dossier.py` (the gate validator) and
`scripts/sync-dossier-to-data.py` (the blog data sync).
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any

import yaml


def parse_dossier(path: Path) -> dict[str, Any]:
    """Parse a dossier markdown file into a sections dict.

    Strips YAML frontmatter if present, then walks the body line
    by line. Each `## ...` line begins a new section; its
    contents are yaml.safe_load'd.
    """
    text = path.read_text()
    fm_match = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if fm_match:
        text = text[fm_match.end():]

    sections: dict[str, Any] = {}
    current_key: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_key:
                try:
                    sections[current_key] = yaml.safe_load("\n".join(current_lines)) or []
                except yaml.YAMLError:
                    sections[current_key] = current_lines
            current_key = (
                line[3:].strip().lower()
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
            )
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)
    if current_key:
        try:
            sections[current_key] = yaml.safe_load("\n".join(current_lines)) or []
        except yaml.YAMLError:
            sections[current_key] = current_lines
    return sections


def get_primary_sources(sections: dict[str, Any]) -> list[dict]:
    """Return the parsed `## Primary sources` list.

    The H2 header in dossiers includes a parenthetical
    annotation (e.g., `## Primary sources (≥5, ≥3 distinct
    type values)`), so look up by prefix.
    """
    for k, v in sections.items():
        if k.startswith("primary_sources"):
            return v or []
    return []
