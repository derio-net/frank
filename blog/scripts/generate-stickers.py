#!/usr/bin/env python3
"""Generate die-cut stickers through blog-craft's shared image engine.

A thin CLI-preserving shim over the sibling `generate-images.py`. frank's private
generator (`blog/_private/frank-stickers/generate-stickers.py`) described itself as
"mirrors the blog's generate-all-images.py" — the very engine blog-craft already
generalised — so the port deletes the fork and keeps the interface.

WHY a shim and not "just use generate-images.py". frank's README documents this
exact CLI, and preserving it is part of "no behavioral changes": the operator's
runbook and muscle memory survive the port. Three things the engine cannot supply
on its own live here:

  --list        the sticker listing (key, sheet/pos, description) rather than the
                engine's bare key dump;
  --dry-run     the FULL composed prompt plus the resolved reference filenames.
                frank's own --dry-run truncated at 300 chars
                (generate-stickers.py:101) — which is why his goldens had to be
                derived from compose_prompt() instead of the CLI. That truncation
                is a defect, and this deliberately fixes it;
  the run-level contact sheet across the KEYS generated (see below).

Usage:
    generate-stickers.py --list
    generate-stickers.py --only 01-wave,05-golden-key
    generate-stickers.py --dry-run
    generate-stickers.py                  # regenerate ALL into <blog root>/regen/

Config (`.blog-craft.yaml`):

    features:
      stickers:
        enabled: true                      # OFF by default; this script refuses
        prompts_file: blog/_private/stickers/stickers-prompts.yaml
        images_dir:   blog/_private/stickers/images
        sheets_dir:   blog/_private/stickers/sheets
                      # NOT `stickers.yaml`: tools/migrate_stickers.py REFUSES a
                      # prompts_file that resolves to the legacy source it reads,
                      # because writing there would destroy the only copy of the
                      # prose being migrated.

NON-DESTRUCTIVE BY DEFAULT — the load-bearing detail. The engine writes the last
variant straight to an entry's `output:`; frank's sticker workflow is the exact
opposite ("pick a winner from regen/ ... copy it over", README.md:28-29). So this
shim always passes `--out`, defaulting to `regen`. Porting the stickers as
ordinary entries without it would overwrite the curated masters the print workflow
exists to protect.

A relative `--out` resolves against the CONFIG ROOT, and the absolute path is what
reaches the engine: `--out` there is CWD-relative (like `--reference`), so a
relative hand-off would land wherever the operator happened to be standing. Note
this is a change of LOCATION from frank, whose `--out` was relative to the private
script directory (`blog/_private/frank-stickers/regen/`); the shipped script lives
at `<site_dir>/scripts/`, so that base no longer exists.

The file names inside `--out` are the engine's (spec 5a): the basename of the
entry's `output:`, which for stickers is exactly frank's `sticker-<key>.png` — the
name of the master his README says to copy over. No renaming layer here; if one
ever seems necessary, 5a is what changed.

`--count` is deliberately NOT exposed: frank's generator had none, and a `--count N`
run needs `curation.archive_cap >= N` or the archive FIFO prunes its own variants
mid-run (journal `p2-archive-cap-prunes-its-own-count-run`). Use
`generate-images.py --count` directly for a curation run, with the cap raised.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ENGINE = "generate-images.py"


def load_engine(directory: Path = HERE):
    """Import the sibling `generate-images.py` as a MODULE.

    Not a subprocess: the engine raises on a hard failure (an auth error, a dead
    endpoint) precisely so the operator sees a traceback, and shelling out would
    collapse that to an exit code. Sibling because `bootstrap-render.sh`
    materializes both scripts into the same `<site_dir>/scripts/` directory —
    which is also why the tests copy them side by side rather than running them
    from their template locations.
    """
    path = directory / ENGINE
    if not path.is_file():
        raise SystemExit(
            f"{ENGINE} not found next to {Path(__file__).name} (looked in {directory}). "
            f"Both ship into <site_dir>/scripts/; re-run /update if one is missing."
        )
    spec = importlib.util.spec_from_file_location("generate_images", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_images"] = module
    spec.loader.exec_module(module)
    return module


def sticker_config(cfg: dict, cfg_path: Path) -> dict:
    """`features.stickers`, or SystemExit naming the knob.

    Both shapes refuse, and both are real: after `migrations/006_to_007.py` every
    updated blog carries `features.stickers: {enabled: false}` explicitly, so
    `disabled` is the common case and `absent` the legacy one.
    """
    stk = ((cfg.get("features") or {}).get("stickers")) or {}
    if not isinstance(stk, dict) or not stk:
        raise SystemExit(
            f"features.stickers is not configured in {cfg_path} — set "
            f"features.stickers.enabled: true (plus prompts_file, images_dir and "
            f"sheets_dir) to use the sticker workflow."
        )
    if stk.get("enabled") is not True:
        raise SystemExit(
            f"features.stickers.enabled is not true in {cfg_path} — the sticker "
            f"workflow is off for this blog. Set features.stickers.enabled: true."
        )
    if not str(stk.get("prompts_file") or "").strip():
        raise SystemExit(f"features.stickers.prompts_file must be set in {cfg_path}")
    return stk


def sticker_entries(prompts: Path) -> dict:
    if not prompts.is_file():
        raise SystemExit(f"sticker prompts file not found: {prompts} "
                         f"(features.stickers.prompts_file)")
    entries = (yaml.safe_load(prompts.read_text()) or {}).get("images") or []
    return {e["key"]: e for e in entries if "key" in e}


def _place(entry: dict) -> str:
    if entry.get("sheet") and entry.get("pos"):
        return f"sheet{entry['sheet']}/pos{entry['pos']}"
    return "(unplaced)"


def _stamp(path: Path):
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _dest_candidates(key: str, name: str, out: Path, out_dir: Path) -> list:
    """Where the engine may have written this key's candidate.

    Normally exactly `_out_dir_names`' answer. The bare basename is kept as a
    second candidate because that helper is a function of the SELECTED SET, and the
    engine's set can be a subset of the shim's (it also drops `operator_generated`
    entries and any whose composed prompt is empty) — which could shrink a colliding
    basename group and turn a `<key>-<basename>` back into `<basename>`. Sticker
    basenames are unique by construction (`sticker-<key>.png`), so this is belt and
    braces, not a path anything takes today.
    """
    names = [name] if name == out.name else [name, out.name]
    return [out_dir / n for n in names]


def _run_level_contact_sheet(gi, out_dir: Path, generated: list) -> None:
    """frank's per-RUN sheet across the keys generated, at `<out>/contact-sheet.png`.

    WHY here and not in the engine (journal `p2-decision6-insufficient-for-frank-sheet`,
    spec Decision 6 correction): the engine's sheet is per-KEY across that key's
    variants and fires only on `--count > 1`. Since a sticker run generates one image
    per key, that sheet is never produced at all. These are two different artifacts,
    so the sticker-workflow layer owns the sticker-workflow one — and the engine's
    per-key sheet is left exactly as it was.

    `cols=5, tile_width=420` are frank's geometry (what Decision 6 parameterized).
    The LAYOUT is an accepted divergence: frank's helper drew aspect-preserving
    thumbnails with the label along the bottom, and it no longer exists (deleted by
    his own cutover, bd0415e6), so there is nothing to reproduce and nothing to
    regress. Declared in the CHANGELOG rather than hidden.

    `tile_height=420` is passed for the same reason `tile_width` is: this sheet is
    reviewed by EYE. Stickers are square (`aspect_ratio: '1:1'`), and
    `_contact_sheet` fits the thumbnail inside `(tw - 10, th - 30)` — so leaving the
    260 default reserved a 420x260 tile for a 230x230 thumbnail and spent ~45% of
    every tile on white. A square tile makes the width parameter actually buy
    resolution instead of margin.
    """
    from PIL import Image
    sheet = out_dir / "contact-sheet.png"
    gi._contact_sheet([(key, Image.open(path)) for key, path in generated],
                      sheet, cols=5, tile_width=420, tile_height=420)
    print(f"\nContact sheet: {sheet}")


def _delegate(gi, cfg: dict, cfg_path: Path, sticker_prompts_rel: str,
              engine_argv: list) -> int:
    """Run the engine over the STICKER prompts file.

    `generate-images.py` reads `image.prompts_file` and has no flag to override it,
    so the shim hands it a shadow config whose `image.prompts_file` is the sticker
    one. The shadow MUST sit in the same directory as the real config: the engine
    derives the blog root from `cfg_path.parent`, and every `output:`, every
    reference path, and the `--out` alias guard resolve against that root. A shadow
    in a temp directory would silently relocate all of them.

    Deleted in `finally`; the name is dotted and unique, and `find_config` looks
    for `.blog-craft.yaml` exactly, so it can never be picked up as a config.
    """
    shadow = dict(cfg)
    shadow["image"] = dict(cfg.get("image") or {}, prompts_file=sticker_prompts_rel)
    fd, tmp_name = tempfile.mkstemp(prefix=".blog-craft.stickers-", suffix=".yaml",
                                    dir=str(cfg_path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(yaml.safe_dump(shadow, sort_keys=False))
        return gi.main(["--config", str(tmp), *engine_argv])
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(
        description="Generate die-cut stickers via blog-craft's image engine.")
    ap.add_argument("--config", help="path to .blog-craft.yaml (default: search upward)")
    ap.add_argument("--only", default="", help="comma-separated sticker keys")
    ap.add_argument("--out", default="regen",
                    help="output dir; a relative path resolves against the config root")
    ap.add_argument("--list", action="store_true", help="list stickers and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the composed prompt and refs; no API call")
    a = ap.parse_args(argv)

    gi = load_engine()
    cfg_path = (Path(a.config) if a.config else gi.find_config(Path.cwd())).resolve()
    root = cfg_path.parent
    cfg = yaml.safe_load(cfg_path.read_text()) or {}
    stk = sticker_config(cfg, cfg_path)
    image_cfg = cfg.get("image") or {}

    prompts_rel = str(stk["prompts_file"]).strip()
    by_key = sticker_entries(root / prompts_rel)

    if a.list:
        for key, entry in by_key.items():
            print(f"  {key:18s} {_place(entry):16s} {entry.get('description', '')}")
        return 0

    keys = [k.strip() for k in a.only.split(",") if k.strip()] or list(by_key)
    unknown = [k for k in keys if k not in by_key]
    if unknown:
        raise SystemExit(f"unknown keys: {unknown}\nvalid: {list(by_key)}")

    if a.dry_run:
        for key in keys:
            entry = by_key[key]
            # the ENGINE's own assembly (`payload_paths`), not a second copy of the
            # order: what is shown here is what `_gen_bytes` would send.
            refs = gi.payload_paths(entry, image_cfg, root)
            print(f"\n=== {key} === refs: {[p.name for p in refs]}")
            print(gi.compose_for(entry, image_cfg))   # in FULL, never truncated
        return 0

    out_dir = Path(a.out).expanduser()
    out_dir = out_dir if out_dir.is_absolute() else (root / out_dir)

    # Where each key's candidate will land, per spec §5a — asked of the ENGINE's own
    # helper rather than guessed, so the shim can never disagree with it about a
    # filename. For stickers this is `sticker-<key>.png`, frank's own regen name,
    # which is why no renaming layer is needed here.
    default_dir = image_cfg.get("output_dir", "static/images")
    selected = [(key, by_key[key], gi.compose_for(by_key[key], image_cfg),
                 root / by_key[key].get("output", f"{default_dir}/{key}.png"))
                for key in keys]
    names = gi._out_dir_names(selected)
    candidates = {key: _dest_candidates(key, names[key], out, out_dir)
                  for key, _e, _p, out in selected}
    # Snapshot BEFORE the run: "generated" means succeeded in THIS run, as frank's
    # `done` list did. A leftover candidate from an earlier run must not pad the
    # contact sheet, and a key the engine failed on writes nothing at all.
    before = {p: _stamp(p) for paths in candidates.values() for p in paths}

    rc = _delegate(gi, cfg, cfg_path, prompts_rel, engine_argv=[
        *["--out", str(out_dir)],
        *(["--only", ",".join(keys)] if a.only else []),
    ])

    generated = []
    for key in keys:
        for path in candidates[key]:
            stamp = _stamp(path)
            if stamp is not None and stamp != before.get(path):
                generated.append((key, path))
                break
    if len(generated) >= 2:
        _run_level_contact_sheet(gi, out_dir, generated)
    print(f"\nDone: {len(generated)}/{len(keys)} succeeded")
    failed = [k for k in keys if k not in {g for g, _p in generated}]
    if failed:
        print(f"Failed: {failed}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
