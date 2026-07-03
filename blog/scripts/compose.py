#!/usr/bin/env python3
"""Approach-A generic prompt concatenator (spec §4.1).

The image generator is a dumb concatenator: it walks `composition_order` and
resolves each named layer from `layers` + the per-image `entry`, then joins the
non-empty sections with a blank line — byte-compatible with frank's
generate-all-images.py (`"\\n\\n".join(s for s in sections if s)`).
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
        return _resolve_indexed(name, layer, entry)
    return str(layer)


def _resolve_indexed(name: str, table: dict, entry: dict) -> str:
    if name == "torso":
        group = entry.get("torso") or entry.get("series")
        idx = entry.get("torso_variant")
        if isinstance(idx, str):          # free-form torso text
            return idx
        opts = table.get(group, []) if group else []
        if isinstance(idx, int) and 0 <= idx < len(opts):
            return opts[idx]
        return ""
    if name == "mood":
        m = entry.get("mood")
        if m is None:
            return ""
        return table.get(m, m)            # named preset, else free-form passthrough
    # generic indexed-table: a same-named entry field selects
    sel = entry.get(name)
    if sel is not None and sel in table:
        return str(table[sel])
    return ""


def compose(composition_order: list[str], layers: dict, entry: dict) -> str:
    sections = [resolve_layer(n, layers.get(n), entry) for n in composition_order]
    return "\n\n".join(s for s in sections if s)
