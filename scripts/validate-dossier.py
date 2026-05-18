#!/usr/bin/env python3
"""Validate a Frank Papers research dossier against the gate rules.

Usage: python scripts/validate-dossier.py <dossier.md>

Exit 0 = pass. Exit 1 = fail (prints specific failures).
"""
import sys
import re
import urllib.request
import urllib.error
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def check_url(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "vk-dossier-validator/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vk-dossier-validator/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status < 400
        except Exception:
            return False


def validate(path: Path) -> list[str]:
    text = path.read_text()
    # Strip YAML frontmatter if present
    fm_match = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if fm_match:
        text = text[fm_match.end():]

    # Parse sections as YAML blocks delimited by ## headers
    # Each ## section becomes a top-level key
    sections: dict = {}
    current_key = None
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_key:
                try:
                    sections[current_key] = yaml.safe_load("\n".join(current_lines)) or []
                except yaml.YAMLError:
                    sections[current_key] = current_lines
            current_key = line[3:].strip().lower().replace(" ", "_").replace("(", "").replace(")", "")
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)
    if current_key:
        try:
            sections[current_key] = yaml.safe_load("\n".join(current_lines)) or []
        except yaml.YAMLError:
            sections[current_key] = current_lines

    failures: list[str] = []

    # Rule 1: vendors_in_scope >= 3
    vendors = sections.get("vendors_in_scope_≥3,_typically_4–6", sections.get("vendors_in_scope", []))
    if not isinstance(vendors, list) or len(vendors) < 3:
        failures.append(f"vendors_in_scope: need ≥3, got {len(vendors) if isinstance(vendors, list) else 0}")

    # Rule 2: primary_sources >= 5, spanning >= 3 distinct type values
    sources = sections.get("primary_sources_≥5,_≥3_distinct_type_values", sections.get("primary_sources", []))
    if not isinstance(sources, list) or len(sources) < 5:
        failures.append(f"primary_sources: need ≥5, got {len(sources) if isinstance(sources, list) else 0}")
    else:
        types = set()
        for s in sources:
            if isinstance(s, dict):
                types.add(s.get("type", ""))
        if len(types) < 3:
            failures.append(f"primary_sources: need ≥3 distinct type values, got {len(types)}: {types}")

    # Rule 3: all primary_sources[].url return HTTP 200
    if isinstance(sources, list):
        for s in sources:
            if isinstance(s, dict):
                url = s.get("url", "")
                if url and not check_url(url):
                    failures.append(f"primary_sources URL not reachable (non-200): {url}")

    # Rule 4: frank_artefacts >= 3, spanning >= 2 distinct kind values
    artefacts = sections.get("frank_artefacts_≥3,_≥2_distinct_kind_values", sections.get("frank_artefacts", []))
    if not isinstance(artefacts, list) or len(artefacts) < 3:
        failures.append(f"frank_artefacts: need ≥3, got {len(artefacts) if isinstance(artefacts, list) else 0}")
    else:
        kinds = set()
        for a in artefacts:
            if isinstance(a, dict):
                kinds.add(a.get("kind", ""))
        if len(kinds) < 2:
            failures.append(f"frank_artefacts: need ≥2 distinct kind values, got {len(kinds)}: {kinds}")

    # Rule 5: named_gaps >= 1
    gaps = sections.get("named_gaps_≥1", sections.get("named_gaps", []))
    if not isinstance(gaps, list) or len(gaps) < 1:
        failures.append("named_gaps: need ≥1")

    # Rule 6: counter_arguments_considered >= 1
    counters = sections.get("counter-arguments_considered_≥1", sections.get("counter-arguments_considered", []))
    if not isinstance(counters, list) or len(counters) < 1:
        failures.append("counter-arguments_considered: need ≥1")

    return failures


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <dossier.md>", file=sys.stderr)
        sys.exit(1)
    dossier_path = Path(sys.argv[1])
    if not dossier_path.exists():
        print(f"ERROR: {dossier_path} not found", file=sys.stderr)
        sys.exit(1)
    failures = validate(dossier_path)
    if failures:
        print(f"DOSSIER GATE FAILED: {dossier_path}", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        sys.exit(1)
    print(f"DOSSIER GATE PASSED: {dossier_path}")
    sys.exit(0)
