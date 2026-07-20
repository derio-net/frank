#!/usr/bin/env python3
"""Approach-A generic prompt concatenator (spec §4.1, config schema v4).

The image generator is a dumb concatenator: it walks `composition_order` and
resolves each named layer from `layers` + the per-image `entry`, then joins the
non-empty sections with a blank line — byte-compatible with frank's
generate-all-images.py (`"\\n\\n".join(s for s in sections if s)`).

The engine hardcodes NO layer vocabulary. A dict layer resolves through a
config-declared selector walk (`_select`); `_`-prefixed table keys are
directives, never prose.
"""
from __future__ import annotations

RESERVED_SCENE = "scene"


def resolve_layer(name: str, layer, entry: dict) -> str:
    """Resolve one layer to its section string ("" => dropped)."""
    if name == RESERVED_SCENE:
        return entry.get("prompt") or ""
    if layer is None:
        return ""
    if isinstance(layer, str):
        return layer
    if isinstance(layer, list):
        return "\n".join(f"- {item}" for item in layer)
    if isinstance(layer, dict):
        return _resolve_selector_walk(name, layer, entry)
    return str(layer)


def _resolve_selector_walk(name: str, table: dict, entry: dict) -> str:
    """Walk the table by the entry fields `_select` declares (default: [name]).

    Each step is an entry-field name or a list of names (first present wins).
    Descend by dict key / int list index. A value that doesn't select passes
    through verbatim at the LAST step only (free-form prose); an intermediate
    miss, a missing field, or a walk that dead-ends on a container skips the
    layer ("").
    """
    steps = table.get("_select") or [name]
    value = {k: v for k, v in table.items() if not str(k).startswith("_")}
    for i, step in enumerate(steps):
        fields = step if isinstance(step, list) else [step]
        sel = next((entry[f] for f in fields if entry.get(f) is not None), None)
        if sel is None:
            return ""
        last = i == len(steps) - 1
        # bool is an int subclass (`torso_variant: yes` -> True) — never an index
        is_index = isinstance(sel, int) and not isinstance(sel, bool)
        if isinstance(value, dict) and isinstance(sel, (str, int)) and sel in value:
            value = value[sel]
        elif isinstance(value, list) and is_index and 0 <= sel < len(value):
            value = value[sel]
        elif last and isinstance(sel, str):
            return sel                    # free-form passthrough
        else:
            return ""                     # intermediate miss / bad index / bad type
    return value if isinstance(value, str) else ""


def compose(composition_order: list[str], layers: dict, entry: dict) -> str:
    sections = [resolve_layer(n, layers.get(n), entry) for n in composition_order]
    return "\n\n".join(s for s in sections if s)
