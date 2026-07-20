#!/usr/bin/env python3
"""Approach-A generic prompt concatenator (spec §4.1; config schemas v4 + v5).

The image generator is a dumb concatenator: it walks an order of tokens and
resolves each from `layers` + the per-image selectors, then joins the
non-empty sections with a blank line — byte-compatible with frank's
generate-all-images.py (`"\\n\\n".join(s for s in sections if s)`).

The engine hardcodes NO layer vocabulary. Tokens (v5):
  scene           reserved — the entry's scene text (`prompt` in the selector
                  dict, kept for v4 compatibility)
  name            a layer: scalar verbatim, list as bullets, dict via the
                  selector rules below
  name[sub]       a dict layer's named chunk, resolved directly
                  (e.g. reference_guidance[anchor])

Dict-layer selection, in order:
  1. `_select` declared -> the v4 selector walk (entry fields, first-present
     alternatives, passthrough at last step);
  2. modifier value `grp[sub]` -> direct two-level descent;
  3. plain modifier value -> named lookup, free-form passthrough on miss —
     but a value that lands on a CONTAINER skips (bracket paths exist for
     nested tables; a bare group name must never dump a dict into the prompt).
`_`-prefixed table keys are directives, never prose.
"""
from __future__ import annotations

import re

RESERVED_SCENE = "scene"
_BRACKET = re.compile(r"^([A-Za-z0-9_-]+)\[([A-Za-z0-9_-]+)\]$")


def _chunk(value) -> str:
    """Render a resolved chunk: scalar verbatim, list as bullets, else ''."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    return ""


def resolve_token(token: str, layers: dict, entry: dict) -> str:
    """Resolve one order token (`scene` | `name` | `name[sub]`) to its section."""
    m = _BRACKET.match(token)
    if m:
        base, sub = m.group(1), m.group(2)
        table = layers.get(base)
        if isinstance(table, dict) and not sub.startswith("_"):
            return _chunk(table.get(sub))
        return ""
    return resolve_layer(token, layers.get(token), entry)


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
        if "_select" in layer:
            return _resolve_selector_walk(name, layer, entry)
        return _resolve_modifier(name, layer, entry)
    return str(layer)


def _resolve_modifier(name: str, table: dict, entry: dict) -> str:
    """v5 dict resolution: bracket path -> direct descent; plain -> named
    lookup with free-form passthrough; a container result skips."""
    sel = entry.get(name)
    if sel is None:
        return ""
    if isinstance(sel, str):
        m = _BRACKET.match(sel)
        if m:
            grp = table.get(m.group(1))
            if isinstance(grp, dict):
                return _chunk(grp.get(m.group(2)))
            return ""
        if sel in table and not sel.startswith("_"):
            return _chunk(table[sel])
        return sel                        # free-form passthrough
    return ""


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
    sections = [resolve_token(t, layers, entry) for t in composition_order]
    return "\n\n".join(s for s in sections if s)
