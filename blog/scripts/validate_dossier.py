#!/usr/bin/env python3
"""Validate a papers research dossier against the config-driven gate.

Dossiers are markdown with `## H2` sections whose bodies are YAML (parsed by
dossier_parser). Sections are located by TOKEN (so `## Frank artefacts (...)`,
`## Artefacts`, or a plain `artefacts:` key all resolve). Gate thresholds come
from `content_types.papers.gate` in `.blog-craft.yaml` — nothing is hardcoded.

Library: `validate_dossier(sections: dict, gate: dict, *, source_types=None,
         artefact_kinds=None, url_checker=None) -> list[str]` (empty == pass).
CLI:     `validate_dossier.py --config <.blog-craft.yaml> <dossier.md> [--check-urls]`
"""
from __future__ import annotations

import sys

from dossier_parser import parse_dossier, section  # shipped alongside

DEFAULT_GATE = {
    "min_vendors": 3, "min_sources": 5, "min_source_types": 3,
    "min_artefacts": 3, "min_artefact_kinds": 2, "min_gaps": 1, "min_counterargs": 1,
}


def _distinct(items, key):
    return {i.get(key) for i in items if isinstance(i, dict) and i.get(key)}


def validate_dossier(sections: dict, gate: dict, *, source_types=None, artefact_kinds=None,
                     url_checker=None) -> list[str]:
    g = {**DEFAULT_GATE, **(gate or {})}
    f: list[str] = []

    vendors = section(sections, "vendors")
    if len(vendors) < g["min_vendors"]:
        f.append(f"vendors: need >={g['min_vendors']}, got {len(vendors)}")

    sources = section(sections, "primary_sources", "sources")
    if len(sources) < g["min_sources"]:
        f.append(f"primary_sources: need >={g['min_sources']}, got {len(sources)}")
    stypes = _distinct(sources, "type")
    if len(stypes) < g["min_source_types"]:
        f.append(f"primary_sources: need >={g['min_source_types']} distinct types, got {len(stypes)}")
    if source_types:
        bad = stypes - set(source_types)
        if bad:
            f.append(f"primary_sources: unknown type(s) {sorted(bad)} (allowed: {source_types})")
    if url_checker:
        for s in sources:
            u = s.get("url") if isinstance(s, dict) else None
            if u and not url_checker(u):
                f.append(f"primary_sources url unreachable: {u}")

    artefacts = section(sections, "artefacts")
    if len(artefacts) < g["min_artefacts"]:
        f.append(f"artefacts: need >={g['min_artefacts']}, got {len(artefacts)}")
    akinds = _distinct(artefacts, "kind")
    if len(akinds) < g["min_artefact_kinds"]:
        f.append(f"artefacts: need >={g['min_artefact_kinds']} distinct kinds, got {len(akinds)}")
    if artefact_kinds:
        bad = akinds - set(artefact_kinds)
        if bad:
            f.append(f"artefacts: unknown kind(s) {sorted(bad)} (allowed: {artefact_kinds})")

    if len(section(sections, "gaps")) < g["min_gaps"]:
        f.append(f"gaps: need >={g['min_gaps']}")
    if len(section(sections, "counter")) < g["min_counterargs"]:
        f.append(f"counter_arguments: need >={g['min_counterargs']}")
    return f


def _load_gate(config_path):
    import yaml
    cfg = yaml.safe_load(open(config_path))
    papers = ((cfg.get("content_types") or {}).get("papers") or {})
    return papers.get("gate") or {}, papers.get("source_types"), papers.get("artefact_kinds")


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("dossier")
    ap.add_argument("--check-urls", action="store_true")
    a = ap.parse_args(argv)
    gate, stypes, akinds = _load_gate(a.config)
    sections = parse_dossier(open(a.dossier).read())
    checker = None
    if a.check_urls:
        import urllib.request
        def checker(u):
            try:
                req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "blog-craft-dossier/1"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status < 400
            except Exception:
                return False
    failures = validate_dossier(sections, gate, source_types=stypes, artefact_kinds=akinds, url_checker=checker)
    if failures:
        print(f"DOSSIER GATE FAILED: {a.dossier}", file=sys.stderr)
        for x in failures:
            print(f"  x {x}", file=sys.stderr)
        return 1
    print(f"DOSSIER GATE PASSED: {a.dossier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
