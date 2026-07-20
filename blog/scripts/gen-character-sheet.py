#!/usr/bin/env python3
"""Generate N candidate CHARACTER DESIGN SHEETS for the blog's persona.

The per-post generator (scripts/generate-images.py) composes SCENE covers via
image.composition_order — including the reference_guidance layer, which enforces
"exactly ONE figure per image". A character *model sheet* needs the opposite: the
SAME character repeated (turnaround + expression row). So this tool builds a
bespoke sheet prompt from image.layers.persona + image.layers.visual_constants
and skips the scene composition. The chosen sheet becomes the master reference
(image.reference_image, default static/images/reference.png) that anchors every
future cover, tile, and banner.

Usage:  python scripts/gen-character-sheet.py [COUNT] [KEY]
          COUNT  number of candidates (default 12)
          KEY    archive key / output stem (default "reference")
Env:    the API key named by image.api_key_env (default GEMINI_API_KEY); source .env first.
        BLOG_CRAFT_TEST_MODE=1 writes 1x1 PNGs instead of calling the API.
Writes: .regen-archive/<KEY>/<KEY>-<sha>.png (+ .txt) and contact-sheet.png
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml
from PIL import Image

SCRIPTS = Path(__file__).resolve().parent


def _load_config(start: Path):
    """Find .blog-craft.yaml by walking up (a site_dir blog keeps it ABOVE the
    site dir — frank: config at the repo root, scripts under blog/scripts).
    Returns (config_root, cfg)."""
    d = Path(start).resolve()
    for cand in [d, *d.parents]:
        f = cand / ".blog-craft.yaml"
        if f.is_file():
            return cand, (yaml.safe_load(f.read_text()) or {})
    raise SystemExit(f"no .blog-craft.yaml found from {start}")

# Reuse the exact archive + API plumbing from generate-images.py (hyphenated → importlib).
_spec = importlib.util.spec_from_file_location("genimg", SCRIPTS / "generate-images.py")
genimg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(genimg)

# Layer resolution comes from the same engine the per-post generator uses.
_cspec = importlib.util.spec_from_file_location("compose_for_sheet", SCRIPTS / "compose.py")
_compose = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(_compose)

# The character-defining layers when image.character_sheet.layers is absent —
# the pre-v4 hardcoding, kept as the default so existing blogs need no edit.
DEFAULT_CHARACTER_LAYERS = ["persona", "visual_constants"]

# Format directive only — the RENDERING style (chibi/painterly/outlines/palette) is
# carried by the blog's own persona + visual_constants, so this stays subject-neutral.
SHEET_STYLE = (
    "A professional character DESIGN REFERENCE SHEET (an animation model sheet): a clean "
    "reference document, NOT an atmospheric scene. Flat, even studio lighting; a plain neutral "
    "light-grey background; uncluttered model-sheet presentation. Render the character in the "
    "blog's own established illustration style as described below."
)
SHEET_LAYOUT = (
    "LAYOUT — the SAME single character shown several times for reference (a turnaround "
    "necessarily repeats the character; that repetition is expected and correct here):\n"
    "- Across the top: a full-body TURNAROUND — front view, three-quarter view, and side view, "
    "in a neutral relaxed pose, with identical proportions, costume, and colours in all three.\n"
    "- Below it: a row of 3–4 head-and-shoulders CLOSE-UPS showing different facial expressions.\n"
    "- Off to one side: a few small DETAIL CALLOUTS of the character's signature props, "
    "accessories, and distinctive costume details (whatever the description below emphasises).\n"
    "Do not render any real readable text or labels; keep any annotation marks abstract."
)


def build_prompt(image_cfg: dict) -> str:
    """Sheet prompt from the config-declared character layers (spec D8).

    `image.character_sheet.layers` names the layers that define the character
    (frank: [base_character]); absent -> DEFAULT_CHARACTER_LAYERS, where a
    missing layer is tolerated. An explicitly named layer that doesn't exist
    is an error — a silent skip would generate a sheet of nothing.
    """
    layers = image_cfg.get("layers", {}) or {}
    declared = (image_cfg.get("character_sheet") or {}).get("layers")
    names = declared or DEFAULT_CHARACTER_LAYERS
    parts = [SHEET_STYLE]
    first = True
    for name in names:
        if name not in layers:
            if declared:
                raise SystemExit(f"image.character_sheet.layers names '{name}' "
                                 f"but image.layers has no such layer")
            continue
        resolved = _compose.resolve_layer(name, layers.get(name), {}).strip()
        if not resolved:
            if declared:
                # e.g. a selector-table layer against an empty entry — declaring
                # it would silently produce a sheet of nothing
                raise SystemExit(f"image.character_sheet.layers names '{name}' "
                                 f"but it resolves to no prose (selector-table "
                                 f"layers need an entry; use scalar/list layers)")
            continue
        if first:
            parts.append(f"CHARACTER — draw THIS character:\n{resolved}")
            first = False
        elif isinstance(layers.get(name), list):
            parts.append(f"HOLD ALL OF THESE CONSTANT (they define the character):\n{resolved}")
        else:
            parts.append(resolved)
    if first:
        raise SystemExit(
            "no character-defining prose resolved — set image.character_sheet.layers "
            f"(tried: {', '.join(names)})")
    parts.append(SHEET_LAYOUT)
    return "\n\n".join(parts)


def main(argv: list[str]) -> int:
    count = int(argv[0]) if len(argv) > 0 else 12
    key = argv[1] if len(argv) > 1 else "reference"
    # walk up from the scripts dir: a site_dir blog keeps the config above the
    # site (frank: repo root); archive + reference paths resolve from there,
    # matching generate-images.py's config-relative convention
    ROOT, cfg = _load_config(SCRIPTS.parent)
    image_cfg = cfg.get("image", {}) or {}
    model = image_cfg.get("model", "gemini-3-pro-image-preview")
    dest = Path(image_cfg.get("reference_image", "static/images/reference.png"))
    cap = int((image_cfg.get("curation", {}) or {}).get("archive_cap", 30))
    prompt = build_prompt(image_cfg)
    entry = {"aspect_ratio": "4:3"}  # a model sheet wants room for two rows

    print(f"model={model}  key={key}  count={count}  prompt={len(prompt)} chars")
    variants = []
    for i in range(count):
        b = genimg._gen_bytes(prompt, None, model, image_cfg, entry, ROOT)
        if not b:
            print(f"  [{i+1}/{count}] no image returned", file=sys.stderr)
            continue
        arch = genimg.write_archive_entry(ROOT, key, b, prompt, None, model, dest, cap)
        variants.append((f"{i+1} · {arch.stem.split('-')[-1]}", arch))
        print(f"  [{i+1}/{count}] -> {arch.relative_to(ROOT)}")
    if variants:
        genimg._contact_sheet(
            [(lbl, Image.open(p)) for lbl, p in variants],
            ROOT / ".regen-archive" / key / "contact-sheet.png",
        )
        print(f"contact sheet -> .regen-archive/{key}/contact-sheet.png  ({len(variants)} candidates)")
        print(f"browse:  python scripts/build-gallery.py {key}")
        print(f"promote: cp .regen-archive/{key}/{key}-<sha>.png {dest}")
    return 0 if variants else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
