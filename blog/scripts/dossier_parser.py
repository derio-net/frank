#!/usr/bin/env python3
"""Parse a papers research dossier.

A dossier is a markdown file where each `## H2` header begins a section whose
body is YAML. An optional `---` frontmatter block at the top is skipped. Section
keys are lowercased with spaces->`_` and parentheses stripped, so an H2 like
`## Primary sources (>=5, >=3 distinct type values)` becomes the key
`primary_sources_>=5,_>=3_distinct_type_values`.

Shared by validate_dossier.py + sync_dossier_to_data.py (both ship into the blog
at scripts/, so a plain-python CI runs them without the plugin).
"""
from __future__ import annotations

import re

import yaml


def _load(buf: list[str]):
    try:
        return yaml.safe_load("\n".join(buf)) or []
    except yaml.YAMLError:
        return buf


def parse_dossier(text: str) -> dict:
    """Parse dossier markdown text into a {section_key: yaml_value} dict."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if m:
        text = text[m.end():]
    sections: dict = {}
    key: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if key is not None:
                sections[key] = _load(buf)
            key = line[3:].strip().lower().replace(" ", "_").replace("(", "").replace(")", "")
            buf = []
        elif key is not None:
            buf.append(line)
    if key is not None:
        sections[key] = _load(buf)
    return sections


def section(sections: dict, *tokens: str) -> list:
    """The first section whose key CONTAINS any token — tolerant of the
    parenthetical annotations frank's H2 headers carry (`primary_sources_>=5...`)
    and per-blog prefixes (`frank_artefacts`). Also matches a plain-key dict
    (e.g. `{"vendors": [...]}`), so structured fixtures work unchanged."""
    for k, v in sections.items():
        if any(t in k for t in tokens):
            return v if isinstance(v, list) else ([] if v is None else v)
    return []
