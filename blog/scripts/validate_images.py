#!/usr/bin/env python3
"""Validate prompt_for_images.yaml against the blog config (spec D8).

The generator warns-and-continues at generation time; this gate catches entry
rot in CI instead: duplicate keys, missing required fields, dead `references:`
paths, escaping `output:` paths, and — the subtle one — selector walks that
silently resolve to "" (an out-of-range `torso_variant`, an unknown group, a
walk that dead-ends on a container). A silently dropped layer corrupts every
future regen of that cover, which is exactly the class of drift a text-parity
check can't see.

A selector field that is absent from the entry — at ANY step of the walk — is
a deliberate skip (the engine's own semantics): `series` is a standard field
every entry carries, so a head like `[[torso, series], torso_variant]` is
"present" on every tile and banner; only entries whose selector VALUES are all
given yet fail to resolve are flagged. An entry with `prompt: ""` is the
shipped placeholder convention (bootstrap tiles await fill-in) and passes;
only a MISSING `prompt` key on a non-operator_generated entry is flagged.

Usage: validate_images.py --config <path/to/.blog-craft.yaml>
Exit 0 clean; 1 with per-entry reasons on stderr.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compose import _resolve_selector_walk, resolve_layer  # noqa: E402  (sibling: tools/ or scripts/)

REQUIRED = ("key", "output")
_ORDER_REF = __import__("re").compile(r"^composition_orders\[([A-Za-z0-9_-]+)\]$")


def _all_step_fields_present(name: str, table: dict, entry: dict) -> bool:
    """True when every walk step has a selector value on the entry."""
    steps = table.get("_select") or [name]
    for step in steps:
        fields = step if isinstance(step, list) else [step]
        if not any(entry.get(f) is not None for f in fields):
            return False
    return True


def _entry_order(e: dict, image: dict, errors: list, key: str) -> list:
    """The token list this entry composes with; flags an unknown order name."""
    comp = e.get("composition") or {}
    orders = image.get("composition_orders") or {}
    o = comp.get("order")
    if isinstance(o, list):
        return o
    if isinstance(o, str):
        m = _ORDER_REF.match(o.strip())
        if not m or m.group(1) not in orders:
            errors.append(f"{key}: unknown composition order reference: {o}")
            return []
        return orders[m.group(1)]
    if orders:
        return orders.get("hero", [])
    return image.get("composition_order") or []


def validate_images(cfg: dict, entries: list, root: Path) -> list[str]:
    errors: list[str] = []
    image = cfg.get("image") or {}
    layers = image.get("layers") or {}

    seen: set = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            errors.append(f"images[{i}]: entry is not a mapping")
            continue
        key = e.get("key") or f"images[{i}]"
        comp = e.get("composition")
        missing = [f for f in REQUIRED if not e.get(f)]
        # An EMPTY scene/prompt string is the shipped placeholder convention
        # (bootstrap tiles await fill-in); only a missing field on a
        # generatable entry is a defect.
        if comp is not None:
            if "scene" not in comp and not e.get("operator_generated"):
                missing.append("composition.scene")
        elif "prompt" not in e and not e.get("operator_generated"):
            missing.append("prompt")
        if missing:
            errors.append(f"{key}: missing required field(s): {', '.join(missing)}")
        if e.get("key"):
            if e["key"] in seen:
                errors.append(f"{e['key']}: duplicate key")
            seen.add(e["key"])

        out = e.get("output")
        if isinstance(out, str) and (out.startswith("/") or ".." in Path(out).parts):
            errors.append(f"{key}: output escapes the blog tree: {out}")

        # reference files must exist: v5 explicit reference_images, v4 references:
        if comp is not None:
            ri = comp.get("reference_images") or {}
            rels = ([ri["primary"]] if ri.get("primary") else []) + list(ri.get("clothing") or [])
        else:
            rels = e.get("references") or []
        for rel in rels:
            if not (root / str(rel)).is_file():
                errors.append(f"{key}: reference not found: {rel}")

        # selector health, against the fields this entry actually composes with
        selectors = dict((comp.get("modifiers") or {})) if comp is not None else e
        order = _entry_order(e, image, errors, key)
        order_bases = {t.split("[", 1)[0] for t in order}
        dict_layers = {n: v for n, v in layers.items()
                       if isinstance(v, dict) and n in order_bases}
        for name, table in dict_layers.items():
            if "_select" in table:
                if not _all_step_fields_present(name, table, selectors):
                    continue                 # deliberate skip — engine semantics
                resolved = _resolve_selector_walk(name, table, selectors)
            else:
                if selectors.get(name) is None:
                    continue                 # deliberate skip — no modifier given
                resolved = resolve_layer(name, table, selectors)
            if resolved == "":
                errors.append(
                    f"{key}: layer '{name}' selector resolves to nothing "
                    f"(bad bracket path, out-of-range index, or unknown group) "
                    f"— the layer would silently drop from this cover"
                )
    return errors


def _main(argv: list[str]) -> int:
    import argparse

    import yaml
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args(argv)
    cfg_path = Path(a.config).resolve()
    cfg = yaml.safe_load(cfg_path.read_text()) or {}
    root = cfg_path.parent
    prompts_rel = (cfg.get("image") or {}).get("prompts_file", "prompt_for_images.yaml")
    prompts_path = root / prompts_rel
    if not prompts_path.is_file():
        print(f"INVALID: prompts file not found: {prompts_path}", file=sys.stderr)
        return 1
    prompts = yaml.safe_load(prompts_path.read_text()) or {}
    entries = prompts.get("images") or []
    errors = validate_images(cfg, entries, root)
    if errors:
        print(f"INVALID: {prompts_path} ({len(errors)} problem(s))", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK: {prompts_path} ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
