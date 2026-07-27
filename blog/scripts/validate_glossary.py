#!/usr/bin/env python3
"""Validate the abbreviation glossary (docs/CONFIG.md §9).

Errors break the promise the feature makes to a reader — a marker with nothing
behind it, or an entry with no text to show. Warnings are hygiene and never fail
a build.

| Check                                             | Severity |
|---------------------------------------------------|----------|
| a {{< abbr >}} marker with no registry entry       | error    |
| an entry missing / blank `name` or `description`   | error    |
| `url` present but not an absolute http(s) URL      | error    |
| two keys differing only in case                    | error    |
| a key containing a double quote                     | error    |
| an entry no post references                        | warning  |
| the registry is not alphabetically sorted          | warning  |

Ships byte-identical at `templates/hugo-hextra/scripts/validate_glossary.py`
(with its `glossary_scan.py` companion) so a blog's plain-python CI runs it
without the plugin installed.

Library: `validate_glossary(registry, marked) -> (errors, warnings)`
         where `marked` is [(term, file, line), ...]
CLI:     `validate_glossary.py --config <cfg> <path…>` (exit 1 on any error)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glossary_scan import load_registry, markers_in  # noqa: E402

_REQUIRED = ("name", "description")


def validate_glossary(registry: dict,
                      marked: list[tuple[str, str, int]]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    registry = registry or {}

    for term, path, line in marked:
        if term not in registry:
            errors.append(
                f"{path}:{line}: {{{{< abbr \"{term}\" >}}}} has no entry in "
                f"data/glossary.yaml")

    for key, entry in registry.items():
        if not isinstance(entry, dict):
            errors.append(
                f"data/glossary.yaml: {key} must be a mapping with name + description")
            continue
        for field in _REQUIRED:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"data/glossary.yaml: {key} is missing a non-empty {field}")
        url = entry.get("url")
        if url is not None and not str(url).startswith(("http://", "https://")):
            errors.append(
                f"data/glossary.yaml: {key} url must be an absolute http(s) URL "
                f"(got {url!r})")

    for key in registry:
        if '"' in key:
            errors.append(
                f"data/glossary.yaml: {key!r} contains a double quote — the marker "
                f"is {{{{< abbr \"KEY\" >}}}}, so the key would terminate the argument "
                f"early and emit an unparseable shortcode")

    lowered: dict[str, str] = {}
    for key in registry:
        prior = lowered.get(key.lower())
        if prior is not None:
            errors.append(
                f"data/glossary.yaml: {prior!r} and {key!r} differ only in case — "
                f"keys are case-sensitive, so one of them can never match")
        lowered[key.lower()] = key

    used = {t for t, _, _ in marked}
    for key in registry:
        if key not in used:
            warnings.append(
                f"data/glossary.yaml: {key} is defined but no post references it")

    keys = list(registry)
    if keys != sorted(keys):
        warnings.append(
            "data/glossary.yaml: entries are not alphabetically sorted")

    return errors, warnings


def _main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Validate the abbreviation glossary.")
    ap.add_argument("--config", required=True)
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args(argv)

    registry = load_registry(a.config)
    marked: list[tuple[str, str, int]] = []
    for p in a.paths:
        with open(p) as f:
            text = f.read()
        marked.extend((term, p, line) for term, line in markers_in(text))

    errors, warnings = validate_glossary(registry, marked)
    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)
    if errors:
        print("INVALID glossary:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK: {len(registry)} glossary entries, {len(marked)} markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
