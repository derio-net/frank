#!/usr/bin/env python3
"""blog-craft image generator (Approach A; config schemas v4 + v5).

Reads composition config from `.blog-craft.yaml` (`image.composition_orders`
named map — v5 — or the legacy single `image.composition_order`) and per-image
entries from the prompts file, composes each prompt via the generic
concatenator (compose.py), and generates covers through Google Gemini. The
generator hardcodes no layer vocabulary — frank, gondor and stoa ship
different orders/layers and all are pure data.

v5 entries carry a `composition:` block — `scene` (was `prompt`), `modifiers`
(the selector fields), `order` (a `composition_orders[name]` reference or an
inline token list; absent -> `hero`), and `reference_images`
(`{primary, clothing: [...]}`), which REPLACES the v4 reference precedence
chain for that entry: what is declared is sent, nothing else. Legacy v4
entries (top-level `prompt` + selector fields) keep the old behavior — one
engine serves both, so /update can ship it to blogs on either schema.

Modes:
  --list                 list all image keys
  --print-prompt KEY     print the composed prompt for KEY (no API; deterministic)
  --dry-run              show what would generate (no API)
  --only KEY[,KEY...]    generate only these keys
  --count N              generate N variants + a contact sheet (curation)
  --reference PATH       override the master reference for every image

Env BLOG_CRAFT_TEST_MODE=1 writes a 1x1 PNG instead of calling the API (tests).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose import compose  # shipped alongside this script

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
TEST_MODE = os.environ.get("BLOG_CRAFT_TEST_MODE") == "1"
_ONE_PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def find_config(start: Path) -> Path:
    d = start.resolve()
    for cand in [d, *d.parents]:
        f = cand / ".blog-craft.yaml"
        if f.is_file():
            return f
    raise FileNotFoundError("no .blog-craft.yaml found from " + str(start))


def _sha12(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def select_reference(entry: dict, image_cfg: dict, root: Path, override: Path | None) -> Path | None:
    """Master reference: CLI override -> image.reference_image (single) ->
    reference_pool/<series>/reference-<series>.png -> generic fallback."""
    if override is not None:
        return override
    ref_img = image_cfg.get("reference_image")
    if ref_img:
        p = root / ref_img
        if p.exists():
            return p
    pool = root / image_cfg.get("reference_pool", ".reference-pool")
    series = entry.get("series") or "generic"
    cand = pool / series / f"reference-{series}.png"
    if cand.exists():
        return cand
    generic = pool / "generic" / "reference-generic.png"
    if generic.exists():
        return generic
    return None  # generation can proceed prompt-only


_ORDER_REF = re.compile(r"^composition_orders\[([A-Za-z0-9_-]+)\]$")


def order_tokens(entry: dict, image_cfg: dict) -> list:
    """The token list this entry composes with (spec: v5 named orders).

    Entry `composition.order` may be an inline list or a
    `composition_orders[name]` reference; absent -> `hero` from the config's
    named orders, falling back to the legacy single `composition_order`.
    """
    comp = entry.get("composition") or {}
    orders = image_cfg.get("composition_orders") or {}
    o = comp.get("order")
    if isinstance(o, list):
        return o
    if isinstance(o, str):
        m = _ORDER_REF.match(o.strip())
        return orders.get(m.group(1), []) if m else []
    if orders:
        return orders.get("hero", [])
    return image_cfg.get("composition_order", [])


def selector_source(entry: dict) -> dict:
    """The dict layers select against: v5 -> modifiers + scene; legacy -> the entry."""
    comp = entry.get("composition")
    if comp is None:
        return entry
    sel = dict(comp.get("modifiers") or {})
    sel["prompt"] = comp.get("scene") or ""
    return sel


def compose_for(entry: dict, image_cfg: dict) -> str:
    return compose(order_tokens(entry, image_cfg), image_cfg.get("layers", {}) or {},
                   selector_source(entry))


def write_archive_entry(root: Path, key: str, image_bytes: bytes, prompt: str,
                        ref: Path | None, model: str, output: Path, cap: int) -> Path:
    sha = _sha12(image_bytes)
    adir = root / ".regen-archive" / key
    adir.mkdir(parents=True, exist_ok=True)
    img_path = adir / f"{key}-{sha}.png"
    img_path.write_bytes(image_bytes)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (adir / f"{key}-{sha}.txt").write_text(
        f"key: {key}\nimage_sha256: {sha}\ngenerated_at: {now}\nmodel: {model}\n"
        f"output: {output}\nreference: {ref if ref else '(none)'}\n\n"
        f"=== composed prompt ===\n{prompt}\n"
    )
    # FIFO cap by mtime; the '<key>-*.png' glob must never match contact-sheet.png.
    if cap > 0:
        snaps = sorted(adir.glob(f"{key}-*.png"), key=lambda p: p.stat().st_mtime)
        for old in snaps[:max(0, len(snaps) - cap)]:
            old.unlink(missing_ok=True)
            old.with_suffix(".txt").unlink(missing_ok=True)
    return img_path


def _contact_sheet(images: list, out: Path) -> None:
    from PIL import Image, ImageDraw
    cols = min(len(images), 3)
    rows = (len(images) + cols - 1) // cols
    tw, th = 400, 260
    sheet = Image.new("RGB", (cols * tw, rows * th), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(images):
        thumb = im.convert("RGB").copy()
        thumb.thumbnail((tw - 10, th - 30))
        x, y = (i % cols) * tw, (i // cols) * th
        sheet.paste(thumb, (x + 5, y + 25))
        draw.text((x + 5, y + 5), label, fill="black")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(out))


def post_process(output: Path, steps: list) -> None:
    from PIL import Image
    for step in steps or []:
        if "resize" in step:
            s = step["resize"]
            im = Image.open(output)
            w = s.get("width", s.get("size"))
            h = s.get("height", s.get("size"))
            im.resize((w, h), Image.LANCZOS).save(str(s.get("target", output)))
        elif "crop_resize" in step:
            s = step["crop_resize"]
            im = Image.open(output).convert("RGB")
            tw, th = s["width"], s["height"]
            gravity = s.get("gravity", 0.5)
            w, h = im.size
            target_ratio = tw / th
            if w / h > target_ratio:
                nw = int(h * target_ratio)
                x = int((w - nw) * gravity)
                im = im.crop((x, 0, x + nw, h))
            else:
                nh = int(w / target_ratio)
                y = int((h - nh) * gravity)
                im = im.crop((0, y, w, y + nh))
            im.resize((tw, th), Image.LANCZOS).save(str(s.get("target", output)))
        elif "ico" in step:
            s = step["ico"]
            Image.open(output).save(str(s["target"]), sizes=[(s.get("size", 32), s.get("size", 32))])


def entry_reference_paths(entry: dict, root: Path) -> list[Path]:
    """Resolve an entry's ADDITIONAL anchors against the blog root.

    v5: `composition.reference_images.clothing`; legacy: top-level
    `references:`. Either way these are the clothing/pose anchors the composed
    `reference_guidance` prose describes. The primary/master sheet is selected
    separately and MUST stay first in the payload — that prose tells the model
    the FIRST image is canonical for the face.

    A missing anchor is skipped with a warning rather than failing the run: a
    stale path in one entry should not block generating its cover.
    """
    comp = entry.get("composition")
    if comp is not None:
        rels = (comp.get("reference_images") or {}).get("clothing") or []
    else:
        rels = entry.get("references") or []
    out: list[Path] = []
    for rel in rels:
        p = (root / str(rel)).expanduser()
        if p.is_file():
            out.append(p)
        else:
            print(f"  WARN: reference not found, skipping: {rel}", file=sys.stderr)
    return out


def primary_reference(entry: dict, image_cfg: dict, root: Path, override: Path | None) -> Path | None:
    """The FIRST payload image. v5 composition entries are EXPLICIT: their
    declared `reference_images.primary` (or nothing) — the legacy precedence
    chain never kicks in for them. Legacy entries keep select_reference().
    A CLI --reference override beats both (debugging escape)."""
    if override is not None:
        return override
    comp = entry.get("composition")
    if comp is not None:
        rel = (comp.get("reference_images") or {}).get("primary")
        if not rel:
            return None
        p = (root / str(rel)).expanduser()
        if p.is_file():
            return p
        print(f"  WARN: primary reference not found, skipping: {rel}", file=sys.stderr)
        return None
    return select_reference(entry, image_cfg, root, None)


def _gen_bytes(prompt: str, ref: Path | None, model: str, image_cfg: dict, entry: dict,
               root: Path) -> bytes | None:
    if TEST_MODE:
        return _ONE_PX_PNG
    from google import genai
    client = genai.Client(api_key=os.environ[image_cfg.get("api_key_env", "GEMINI_API_KEY")])
    from PIL import Image
    contents: list = [prompt]
    if ref:
        contents.append(Image.open(ref))
    # Entry-level anchors follow the master sheet, in declared order.
    for p in entry_reference_paths(entry, root):
        try:
            contents.append(Image.open(p))
        except OSError as exc:
            print(f"  WARN: reference unreadable, skipping: {p} ({exc})", file=sys.stderr)
    cfg_kwargs: dict = {}
    if entry.get("aspect_ratio") or entry.get("image_size"):
        ic = {}
        if entry.get("aspect_ratio"):
            ic["aspect_ratio"] = entry["aspect_ratio"]
        if entry.get("image_size"):
            ic["image_size"] = entry["image_size"]
        cfg_kwargs["image_config"] = genai.types.ImageConfig(**ic)
    resp = client.models.generate_content(
        model=model, contents=contents,
        config=genai.types.GenerateContentConfig(**cfg_kwargs) if cfg_kwargs else None,
    )
    for part in resp.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--only")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--print-prompt")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--reference")
    a = ap.parse_args(argv)

    cfg_path = Path(a.config) if a.config else find_config(Path.cwd())
    root = cfg_path.parent
    cfg = yaml.safe_load(cfg_path.read_text())
    image_cfg = cfg.get("image", {}) or {}
    prompts_file = root / image_cfg.get("prompts_file", "prompt_for_images.yaml")
    entries = (yaml.safe_load(prompts_file.read_text()) or {}).get("images", []) if prompts_file.exists() else []
    by_key = {e["key"]: e for e in entries if "key" in e}

    if a.list:
        for k in by_key:
            print(k)
        return 0

    if a.print_prompt:
        e = by_key.get(a.print_prompt)
        if not e:
            print(f"unknown key: {a.print_prompt}", file=sys.stderr)
            return 1
        print(compose_for(e, image_cfg))
        return 0

    only = set(a.only.split(",")) if a.only else None
    model = image_cfg.get("model", "gemini-3-pro-image-preview")
    override = Path(a.reference) if a.reference else None
    curation = image_cfg.get("curation", {}) or {}
    cap = int(curation.get("archive_cap", 30))
    count = a.count if a.count is not None else int(curation.get("count_default", 1))

    rc = 0
    for key, e in by_key.items():
        if only and key not in only:
            continue
        if e.get("operator_generated"):
            continue
        prompt = compose_for(e, image_cfg)
        if not prompt.strip():
            continue
        out = root / e.get("output", f"{image_cfg.get('output_dir', 'static/images')}/{key}.png")
        ref = primary_reference(e, image_cfg, root, override)
        if a.dry_run:
            extra = entry_reference_paths(e, root)
            refs_used = ([ref] if ref else []) + extra
            print(f"[dry-run] {key} -> {out}  (ref={ref}, {len(prompt)} chars, "
                  f"{len(refs_used)} image(s) to model)")
            for i, p in enumerate(refs_used, 1):
                kind = "master" if (ref and p == ref and i == 1) else "entry"
                try:
                    rel = p.relative_to(root)
                except ValueError:
                    rel = p
                print(f"           ref {i} ({kind}): {rel}")
            continue
        variants = []
        for i in range(max(1, count)):
            b = _gen_bytes(prompt, ref, model, image_cfg, e, root)
            if not b:
                print(f"  {key}: no image returned", file=sys.stderr)
                rc = 1
                break
            arch = write_archive_entry(root, key, b, prompt, ref, model, out, cap)
            variants.append((f"{i+1} · {arch.stem.split('-')[-1]}", arch))
        if variants:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(variants[-1][1].read_bytes())
            if count > 1 and curation.get("contact_sheet", True):
                from PIL import Image
                _contact_sheet([(lbl, Image.open(p)) for lbl, p in variants],
                               root / ".regen-archive" / key / "contact-sheet.png")
            if e.get("post_process"):
                post_process(out, e["post_process"])
            print(f"  {key} -> {out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
