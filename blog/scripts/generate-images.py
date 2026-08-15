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
  --out DIR              non-destructive: write DIR/<basename of `output:`>
                         (`DIR/<key>-<basename>` for every entry of a colliding
                         basename group, e.g. the many `cover.png`s; plus
                         DIR/<key>-<sha>.png per variant when --count > 1) and
                         NEVER the entry's `output:`, nor its post_process
                         derivatives — a run whose DIR would alias any `output:`
                         is refused. For curating candidates against a
                         hand-picked master.

Config knobs honored on every run: `image.fallback_model` (retried when the
primary model errors or returns no image part; if every configured model errors
the last exception propagates, so a hard failure stays hard) and
`image.timeout_ms` (HTTP cap, milliseconds).

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


def _contact_sheet(images: list, out: Path, cols: int | None = None,
                   tile_width: int = 400, tile_height: int | None = 260) -> None:
    """A screen-resolution review grid. Geometry is parameterized because
    frank's sticker regen sheet is cols=5 / tile_width=420 (its own
    scripts/lib/contact_sheet.py, called from generate-stickers.py:143) — a
    sheet the operator reviews by EYE, so silently reflowing it to 3 columns
    would be a visible regression. The defaults are exactly the values they
    replaced, so existing callers (the --count curation sheet) are unchanged.
    """
    from PIL import Image, ImageDraw
    # `None` means "unspecified" -> the historical 3. A specified 0 (or negative)
    # is a CALLER BUG — a computed column count that came out empty — and must not
    # be indistinguishable from "use the default", which `cols or 3` made it.
    if cols is None:
        cols = 3
    elif cols < 1:
        raise ValueError(f"_contact_sheet: cols must be >= 1 or None (got {cols!r})")
    # cols clamps to the image count: a wider request must not leave empty columns.
    cols = min(len(images), cols)
    rows = (len(images) + cols - 1) // cols
    tw = tile_width
    # tile_height=None derives the height from the default 400x260 tile ratio;
    # an explicit height (including the 260 default) is used verbatim.
    th = tile_height if tile_height is not None else round(tile_width * 260 / 400)
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
            # `size` is the square shorthand (as on `ico`); `target` writes the
            # derivative elsewhere (as on `crop_resize`) so a one-master ->
            # many-derivatives pass doesn't clobber the source it reads.
            s = step["resize"]
            w = s.get("width", s.get("size"))
            h = s.get("height", s.get("size"))
            im = Image.open(output)
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


_UNRESOLVED = object()


def payload_paths(entry: dict, image_cfg: dict, root: Path, override: Path | None = None,
                  primary: Path | None | object = _UNRESOLVED) -> list[Path]:
    """The reference payload in the ORDER it reaches the model: the primary master
    sheet first, then the entry's anchors in declared order.

    THE one place that order is assembled. It used to be spelled out in three:
    `_gen_bytes` (what actually ships to the model), the sticker shim's `--dry-run`
    (what the operator is shown), and `tests/unit/test_stickers_references.py` (the
    file whose whole purpose is that order — the one class the 18 prompt goldens are
    structurally blind to). Three copies that agree today, where a reordering inside
    `_gen_bytes` would leave the guard green.

    `primary` lets a caller that has ALREADY resolved the primary — `main`, which
    prints it and hands it to `_gen_bytes` — pass it in, so it is not resolved (and
    its miss not WARNed) a second time. Omit it and the primary is resolved here.
    """
    if primary is _UNRESOLVED:
        primary = primary_reference(entry, image_cfg, root, override)
    return ([primary] if primary else []) + entry_reference_paths(entry, root)


def _gen_bytes(prompt: str, ref: Path | None, model: str, image_cfg: dict, entry: dict,
               root: Path) -> bytes | None:
    if TEST_MODE:
        return _ONE_PX_PNG
    from google import genai
    client = genai.Client(api_key=os.environ[image_cfg.get("api_key_env", "GEMINI_API_KEY")])
    from PIL import Image
    contents: list = [prompt]
    # Order comes from `payload_paths`, never from this loop: the master sheet leads
    # (the composed `reference_guidance` prose declares the FIRST image canonical for
    # the face), entry anchors follow in declared order.
    payload = payload_paths(entry, image_cfg, root, primary=ref)
    # An unreadable MASTER stays fatal — generating without the face authority would
    # silently produce the wrong character — while an unreadable anchor is skipped
    # with a warning, as before.
    lead = 1 if ref else 0
    if lead:
        contents.append(Image.open(payload[0]))
    for p in payload[lead:]:
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
    # `image.timeout_ms` caps the HTTP request (the SDK's HttpOptions.timeout is
    # in milliseconds). Absent -> no http_options at all, so a config with no
    # knobs set stays `None` exactly as before.
    timeout_ms = image_cfg.get("timeout_ms")
    if timeout_ms:
        cfg_kwargs["http_options"] = genai.types.HttpOptions(timeout=int(timeout_ms))
    gen_cfg = genai.types.GenerateContentConfig(**cfg_kwargs) if cfg_kwargs else None
    # WHY the fallback: the configured primary is a *preview* model
    # (gemini-3-pro-image-preview) and preview endpoints 503/overload. frank's
    # private sticker generator carried exactly this retry —
    # gemini-3-pro-image-preview -> gemini-2.5-flash-image — for that reason
    # (generate-stickers.py:37-39,123-136), and dropping it when the stickers
    # moved onto this engine would have changed behavior on the failure path.
    # Like frank's loop, an image-LESS response counts as a failure worth
    # retrying, and every attempt is logged with its model name (never silent).
    #
    # ERROR CONTRACT (do not soften): the fallback adds a RETRY; it must not turn
    # a hard failure into a soft one. Once every configured model has been tried,
    # the last exception PROPAGATES. With no `fallback_model` that is exactly the
    # pre-fallback behavior — a single bare call whose error aborts the run — so
    # an existing blog's failure path is unchanged. Absorbing it would make a 401
    # or a network outage warn once per entry and grind on through all 90.
    # An image-LESS response raised nothing, so it stays SOFT: `None`, which the
    # caller reports as "no image returned" with rc=1, exactly as before.
    last_exc: BaseException | None = None
    for m in [model, image_cfg.get("fallback_model")]:
        if not m:
            continue
        try:
            resp = client.models.generate_content(model=m, contents=contents, config=gen_cfg)
        except Exception as exc:  # noqa: BLE001 - any API/transport error retries
            # The type matters: str(exc) truncated to 160 chars is often empty or
            # opaque, and the traceback the operator used to get is gone the
            # moment we catch. Keep diagnosis possible for the attempt whose
            # exception we do NOT re-raise.
            print(f"  WARN: {m} error: {type(exc).__name__}: {str(exc)[:160]}", file=sys.stderr)
            last_exc = exc
            continue
        for part in resp.parts:
            if part.inline_data is not None:
                return part.inline_data.data
        print(f"  WARN: {m} returned no image part", file=sys.stderr)
    if last_exc is not None:
        raise last_exc
    return None


def _out_dir_names(selected: list) -> dict:
    """`key -> filename` under `--out` (spec §5a). A function of the SELECTED SET.

    The file name is the BASENAME of the entry's `output:` — because frank's
    regen files are `sticker-<key>.png` (generate-stickers.py:118), the name of
    the master its README says to copy over, so a hardcoded `<key>.png` breaks
    the runbook. But 85 of frank's 91 cover entries publish to `.../cover.png`,
    so the basename alone would collapse 85 covers onto one file. Hence: when two
    or more SELECTED entries share a basename, EVERY colliding entry is written
    as `<key>-<basename>`.

    Computed for the whole set before anything generates, so the decision cannot
    depend on iteration order (never "the first one keeps the bare name"), and
    the extension always comes from `output:` rather than a hardcoded `.png`.
    """
    counts: dict = {}
    for _k, _e, _p, out in selected:
        counts[out.name] = counts.get(out.name, 0) + 1
    return {k: (f"{k}-{out.name}" if counts[out.name] > 1 else out.name)
            for k, _e, _p, out in selected}


def _output_alias(dest: Path, published: list):
    """`(key, path)` of the `output:` that `dest` would in fact overwrite, else None.

    `published` is `[(key, output_path, resolved_output_path)]`. Resolved-path
    equality catches the ordinary aliases (relative vs absolute, `..`, a
    symlinked directory); `samefile` additionally catches two real paths on one
    inode (a hard link), which resolution cannot see.
    """
    rdest = dest.resolve()
    for key, out, rout in published:
        if rdest == rout:
            return key, out
        if dest.is_file() and out.is_file() and dest.samefile(out):
            return key, out
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
    ap.add_argument("--out", help="non-destructive: write to <dir>/<basename of "
                                  "output:> (key-prefixed when basenames collide) "
                                  "and NEVER to the entry's output: path")
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
    out_dir = Path(a.out).expanduser() if a.out else None   # cwd-relative, like --reference
    model = image_cfg.get("model", "gemini-3-pro-image-preview")
    override = Path(a.reference) if a.reference else None
    curation = image_cfg.get("curation", {}) or {}
    cap = int(curation.get("archive_cap", 30))
    count = a.count if a.count is not None else int(curation.get("count_default", 1))

    # The selected set is resolved UP FRONT, because the --out file names are a
    # function of the whole set (see _out_dir_names) and the alias guard below
    # must be able to refuse the run before the first API call is spent.
    # `compose_for` is pure and API-free, so composing early changes nothing.
    selected = []
    for key, e in by_key.items():
        if only and key not in only:
            continue
        if e.get("operator_generated"):
            continue
        prompt = compose_for(e, image_cfg)
        if not prompt.strip():
            # LOUD, but not fatal. An entry that composes to nothing is skipped —
            # and used to be skipped in SILENCE, with rc 0, so a typo'd order name
            # produced no image and reported success (measured: a bare
            # `order: sticker` instead of `composition_orders[sticker]` yields all
            # 18 stickers, zero output, exit 0). Deliberately a WARN and not an
            # error: an operator may have a legitimately empty entry, and changing
            # the exit code would be a real behaviour change on the cover path that
            # every blog takes.
            print(f"  WARN: {key}: composed prompt is empty — the entry composes to "
                  f"nothing and is SKIPPED. Check composition.order (a bare name is "
                  f"not a reference: use composition_orders[<name>]), the modifiers "
                  f"its layers select on, and scene.", file=sys.stderr)
            continue
        out = root / e.get("output", f"{image_cfg.get('output_dir', 'static/images')}/{key}.png")
        selected.append((key, e, prompt, out))

    # Under --out, where each entry actually writes. NOT `output:` — and
    # --dry-run must say so rather than name a file it will never touch.
    names = _out_dir_names(selected) if out_dir is not None else {}
    if out_dir is not None:
        # --out's entire purpose is "never writes `output:`". A path-shaped
        # promise is not a guarantee: `--out static/images` from the blog root
        # resolves onto the very files `output:` names, and so does a symlink to
        # that directory. Refuse the whole run rather than write one.
        published = [(k, o, o.resolve()) for k, _e, _p, o in selected]
        refused = False
        for key, _e, _p, _out in selected:
            hit = _output_alias(out_dir / names[key], published)
            if not hit:
                continue
            okey, opath = hit
            whose = "its own" if okey == key else f"entry '{okey}'s"
            print(f"  ERROR: --out would write {out_dir / names[key]} for '{key}', "
                  f"which is {whose} published output: {opath} — refusing, because "
                  f"--out must never write a published asset. Point --out at a "
                  f"directory outside the published tree.", file=sys.stderr)
            refused = True
        if refused:
            return 1

    rc = 0
    for key, e, prompt, out in selected:
        dest = (out_dir / names[key]) if out_dir is not None else out
        ref = primary_reference(e, image_cfg, root, override)
        if a.dry_run:
            extra = entry_reference_paths(e, root)
            refs_used = ([ref] if ref else []) + extra
            print(f"[dry-run] {key} -> {dest}  (ref={ref}, {len(prompt)} chars, "
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
        # The archive FIFO cap prunes by mtime on EVERY write_archive_entry call,
        # so a --count run larger than `curation.archive_cap` deletes its own
        # earlier variants while it is still in flight. Everything downstream
        # (the contact sheet, and the --out copy) reads every variant, so drop
        # the pruned ones loudly rather than dying on a file we deleted.
        live = [(lbl, p) for lbl, p in variants if p.is_file()]
        if len(live) != len(variants):
            print(f"  WARN: {key}: {len(variants) - len(live)} variant(s) already pruned "
                  f"by archive_cap={cap}; raise it to keep a full --count run",
                  file=sys.stderr)
            variants = live
        if variants:
            if out_dir is not None:
                # NON-DESTRUCTIVE MODE. The entry's `output:` is a CURATED
                # artifact: frank's sticker workflow is "generate into regen/,
                # pick a winner, copy it over the master by hand"
                # (frank-stickers/README.md:28-29, generate-stickers.py:71,89).
                # Writing `output:` on every regen would destroy hand-picked
                # artwork — the thing the print workflow exists to protect — so
                # here we never touch it, never create its parent dirs, and skip
                # post_process (those steps target the PUBLISHED asset and would
                # clobber shipped derivatives).
                out_dir.mkdir(parents=True, exist_ok=True)
                if len(variants) > 1:
                    # curation: every candidate is visible side by side. Only for
                    # multi-variant runs, so a plain regen leaves exactly one file
                    # per key, as frank's regen/ dir has always had.
                    for _lbl, arch in variants:
                        (out_dir / arch.name).write_bytes(arch.read_bytes())
                # The reviewable name, written ONCE — below the variant loop, not
                # inside it (where an N-variant run wrote it N times, N-1 of them
                # immediately overwritten).
                dest.write_bytes(variants[-1][1].read_bytes())
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(variants[-1][1].read_bytes())
            if count > 1 and curation.get("contact_sheet", True):
                from PIL import Image
                _contact_sheet([(lbl, Image.open(p)) for lbl, p in variants],
                               root / ".regen-archive" / key / "contact-sheet.png")
            if out_dir is None and e.get("post_process"):
                post_process(out, e["post_process"])
            print(f"  {key} -> {dest}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
