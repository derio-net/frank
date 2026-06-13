#!/usr/bin/env python3
"""Generate Frank die-cut stickers from stickers.yaml.

Mirrors the blog's generate-all-images.py, but for the sticker set: a flat
pure-white sticker atmosphere (not the dark server-room one), an identity lock
on Frank's face, and a white-bleed + dark-green keyline die-cut finish.

Composition order per sticker:
    base_character + sticker_atmosphere + reference_guidance + face_pins
    + clothing + "Frank's expression: <mood>." + scene + border_spec

References (order matters — first is the face authority):
    references.canon_face, then references.style_anchors (09 & 20 head/hair),
    then the per-sticker clothing subject from references.subjects_dir.

Usage (run from anywhere; paths resolve against the repo root):
    source .env_common   # GEMINI_API_KEY
    ./generate-stickers.py --list
    ./generate-stickers.py --only 11-coffee
    ./generate-stickers.py --only 01-wave,05-golden-key --out regen
    ./generate-stickers.py            # regenerate ALL into ./regen/
"""
import argparse
import sys
from pathlib import Path

import yaml
from google import genai
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]          # blog/_private/frank-stickers -> repo root
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.contact_sheet import compose_contact_sheet  # noqa: E402

YAML = HERE / "stickers.yaml"
MODEL = "gemini-3-pro-image-preview"
FALLBACK_MODEL = "gemini-2.5-flash-image"
TIMEOUT_MS = 120_000


def resolve(p: str) -> Path:
    """Resolve a yaml reference path against the repo root."""
    path = Path(p)
    return path if path.is_absolute() else (REPO_ROOT / path)


def compose_prompt(cfg: dict, s: dict) -> str:
    return "\n\n".join([
        cfg["base_character"], cfg["sticker_atmosphere"],
        cfg["reference_guidance"], cfg["face_pins"],
        s["clothing"], f"Frank's expression: {s['mood']}.",
        s["scene"], cfg["border_spec"],
    ])


def scene_refs(cfg: dict, s: dict) -> list[Path]:
    refs = [resolve(cfg["references"]["canon_face"])]
    refs += [resolve(a) for a in cfg["references"]["style_anchors"]]
    anchor = s.get("clothing_anchor")
    if anchor:
        p = resolve(cfg["references"]["subjects_dir"]) / anchor
        if p.exists():
            refs.append(p)
    return [r for r in refs if r.exists()]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="", help="comma-separated sticker keys")
    ap.add_argument("--out", default="regen", help="output dir (under this folder)")
    ap.add_argument("--list", action="store_true", help="list keys and exit")
    ap.add_argument("--dry-run", action="store_true", help="show prompts, don't call the API")
    args = ap.parse_args()

    cfg = yaml.safe_load(YAML.read_text())
    stickers = {s["key"]: s for s in cfg["stickers"]}

    if args.list:
        for k, s in stickers.items():
            print(f"  {k:18s} sheet{s['sheet']}/pos{s['pos']}  {s['description']}")
        return

    keys = [k.strip() for k in args.only.split(",") if k.strip()] or list(stickers)
    unknown = [k for k in keys if k not in stickers]
    if unknown:
        sys.exit(f"unknown keys: {unknown}\nvalid: {list(stickers)}")

    out = HERE / args.out
    out.mkdir(parents=True, exist_ok=True)
    gen_cfg = genai.types.GenerateContentConfig(
        http_options=genai.types.HttpOptions(timeout=TIMEOUT_MS),
        image_config=genai.types.ImageConfig(
            aspect_ratio=cfg.get("defaults", {}).get("aspect_ratio", "1:1")),
    )

    if args.dry_run:
        for k in keys:
            s = stickers[k]
            print(f"\n=== {k} === refs: {[p.name for p in scene_refs(cfg, s)]}")
            print(compose_prompt(cfg, s)[:300] + " ...")
        return

    import os
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY not set (source .env_common)")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    _cache: dict[Path, Image.Image] = {}

    def img(p: Path):
        if p not in _cache:
            _cache[p] = Image.open(p)
        return _cache[p]

    done, labels, failed = [], [], []
    for i, k in enumerate(keys):
        s = stickers[k]
        out_path = out / f"sticker-{k}.png"
        prompt = compose_prompt(cfg, s)
        refs = [img(p) for p in scene_refs(cfg, s)]
        print(f"\n[{k}] → {out_path.name}  (refs: {[p.name for p in scene_refs(cfg, s)]})", flush=True)
        ok = False
        for model in (MODEL, FALLBACK_MODEL):
            try:
                resp = client.models.generate_content(
                    model=model, contents=[prompt, *refs], config=gen_cfg)
                for part in resp.parts:
                    if part.inline_data is not None:
                        part.as_image().save(str(out_path))
                        print(f"   saved ({model})", flush=True)
                        ok = True
                        break
                if ok:
                    break
            except Exception as e:  # noqa: BLE001
                print(f"   {model} error: {str(e)[:160]}", file=sys.stderr)
        (done if ok else failed).append(out_path if ok else k)
        if ok:
            labels.append(k)

    if len(done) >= 2:
        sheet = out / "contact-sheet.png"
        compose_contact_sheet(done, labels=labels, cols=5, tile_width=420).save(sheet)
        print(f"\nContact sheet: {sheet}")
    print(f"\nDone: {len(done)}/{len(keys)} succeeded")
    if failed:
        print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
