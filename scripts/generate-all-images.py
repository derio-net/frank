#!/usr/bin/env python3
"""Generate all blog images using Gemini with a consistent character reference.

Reads prompts from blog/prompt_for_images.yaml.

Usage:
    ./scripts/generate-all-images.py --reference <ref.png>
    ./scripts/generate-all-images.py --reference <ref.png> --only banner-hero,post-03
    ./scripts/generate-all-images.py --reference <ref.png> --list
    ./scripts/generate-all-images.py --reference <ref.png> --dry-run

Requires GEMINI_API_KEY env var.
"""

import argparse
import hashlib
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from google import genai
from PIL import Image

MODEL = "gemini-3-pro-image-preview"
FALLBACK_MODEL = "gemini-2.5-flash-image"
# Per-request timeout in milliseconds (genai SDK convention). The default
# is essentially "wait forever," which turned model-side stalls into
# unrecoverable hangs in practice. 120s is enough headroom for a successful
# image gen and short enough to fall back fast on a real stall.
REQUEST_TIMEOUT_MS = 120_000
REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = REPO_ROOT / "blog" / "prompt_for_images.yaml"

# Per-key archive of every successful generation, with a sidecar .txt that
# records the exact prompt sections and reference images used. Lets us look
# at the iteration history of a given cover and curate the reference pool.
# Gitignored — see .gitignore.
ARCHIVE_DIR = REPO_ROOT / ".regen-archive"
ARCHIVE_DEFAULT_CAP = 30

# Optional pool of "known-good" reference images, split by blog series so
# each series can anchor its own visual style. Subdirs:
#   generic/    — Frank character signature (applies to every key)
#   papers/     — Papers covers (dark navy + glasses + tie)
#   building/   — Building Frank covers
#   operating/  — Operating Frank covers
# Curated by the operator; tracked in git so the canonical style stays
# discoverable across machines.
POOL_DIR = REPO_ROOT / ".reference-pool"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _sha256_short(data: bytes, n: int = 12) -> str:
    return hashlib.sha256(data).hexdigest()[:n]


def _sha256_file_short(path: Path, n: int = 12) -> str:
    return _sha256_short(path.read_bytes(), n)


def _key_to_series(key: str) -> str | None:
    """Map an image key to its series subdir under .reference-pool/.

    Keys not matching a known prefix get None — they'll still pull from
    .reference-pool/generic/ if it exists.
    """
    if key.startswith("paper-"):
        return "papers"
    if key.startswith("building-"):
        return "building"
    if key.startswith("ops-"):
        return "operating"
    return None


def load_pool_refs(
    key: str, n_generic: int, n_series: int, rng: random.Random
) -> list[Path]:
    """Pick reference-pool images for this key.

    Returns up to n_generic from .reference-pool/generic/ plus n_series from
    the key's series subdir. Missing or empty pools simply contribute fewer
    references — no error. Selection within each pool is random per call.
    """
    refs: list[Path] = []

    def _sample_from(subdir: str, n: int) -> list[Path]:
        if n <= 0:
            return []
        d = POOL_DIR / subdir
        if not d.is_dir():
            return []
        candidates = sorted(
            p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTS and p.is_file()
        )
        if not candidates:
            return []
        return rng.sample(candidates, min(n, len(candidates)))

    refs.extend(_sample_from("generic", n_generic))
    series = _key_to_series(key)
    if series:
        refs.extend(_sample_from(series, n_series))
    return refs


def write_archive_entry(
    key: str,
    image_bytes: bytes,
    prompt_sections: dict[str, str],
    refs_used: list[Path],
    model: str,
    output_path: Path,
    cap: int = ARCHIVE_DEFAULT_CAP,
    extra_meta: dict[str, str] | None = None,
) -> Path:
    """Save the just-generated image and a sidecar with full provenance.

    Archive layout: .regen-archive/<key>/<key>-<sha12>.{png,txt}
    Identical bytes produce the same sha → idempotent overwrite.
    """
    sha = _sha256_short(image_bytes)
    archive_root = ARCHIVE_DIR / key
    archive_root.mkdir(parents=True, exist_ok=True)
    img_path = archive_root / f"{key}-{sha}.png"
    txt_path = archive_root / f"{key}-{sha}.txt"
    img_path.write_bytes(image_bytes)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_rel = (
        output_path.relative_to(REPO_ROOT)
        if str(output_path).startswith(str(REPO_ROOT))
        else output_path
    )
    lines = [
        f"key: {key}",
        f"image_sha256: {sha}",
        f"generated_at: {now}",
        f"model: {model}",
        f"output_path: {out_rel}",
    ]
    for k, v in (extra_meta or {}).items():
        lines.append(f"{k}: {v}")
    lines.extend([
        "",
        "=== references (in order, as passed to model) ===",
    ])
    if not refs_used:
        lines.append("(none)")
    for i, p in enumerate(refs_used, 1):
        try:
            ref_sha = _sha256_file_short(p)
        except OSError:
            ref_sha = "unreadable"
        rel = (
            p.relative_to(REPO_ROOT)
            if str(p).startswith(str(REPO_ROOT))
            else p
        )
        lines.append(f"{i}. {rel}  (sha256: {ref_sha})")
    lines.append("")
    lines.append("=== prompt sections (joined with \\n\\n) ===")
    # Render in composition order; legacy keys are still accepted in case
    # any older sidecar consumers read the file.
    order = (
        "base_character",
        "base_atmosphere",
        "base_style",
        "reference_guidance",
        "torso",
        "series_modifiers",
        "mood",
        "prompt",
    )
    seen: set[str] = set()
    for label in order:
        if label in prompt_sections:
            section = prompt_sections[label]
            lines.append("")
            lines.append(f"[{label}]")
            lines.append(section if section else "(empty)")
            seen.add(label)
    # Any extra keys the caller passed in (forward-compat) get appended.
    for label, section in prompt_sections.items():
        if label in seen:
            continue
        lines.append("")
        lines.append(f"[{label}]")
        lines.append(section if section else "(empty)")
    txt_path.write_text("\n".join(lines) + "\n")

    # FIFO cap by file mtime (latest survives).
    if cap > 0:
        snaps = sorted(
            archive_root.glob(f"{key}-*.png"), key=lambda p: p.stat().st_mtime
        )
        excess = len(snaps) - cap
        if excess > 0:
            for old in snaps[:excess]:
                old.unlink(missing_ok=True)
                old.with_suffix(".txt").unlink(missing_ok=True)

    return img_path


def load_prompts(path: Path) -> dict:
    """Load the YAML prompts file and return parsed config."""
    with open(path) as f:
        return yaml.safe_load(f)


def post_process(source_path: Path, steps: list[dict]) -> None:
    """Run post-processing steps: resize, crop_resize, or ICO conversion."""
    img = Image.open(source_path)

    for step in steps:
        if "crop_resize" in step:
            # Crop to target aspect ratio, then scale to final size.
            # Optional "gravity" (0.0=top/left, 0.5=center, 1.0=bottom/right)
            # controls where the crop window sits. Default: 0.5 (center).
            cfg = step["crop_resize"]
            target = REPO_ROOT / cfg["target"]
            tw, th = cfg["width"], cfg["height"]
            gravity = cfg.get("gravity", 0.5)
            target_ratio = tw / th
            src_w, src_h = img.size
            src_ratio = src_w / src_h

            if src_ratio > target_ratio:
                # Source is wider — crop sides
                new_w = int(src_h * target_ratio)
                left = int((src_w - new_w) * gravity)
                cropped = img.crop((left, 0, left + new_w, src_h))
            else:
                # Source is taller — crop top/bottom
                new_h = int(src_w / target_ratio)
                top = int((src_h - new_h) * gravity)
                cropped = img.crop((0, top, src_w, top + new_h))

            resized = cropped.resize((tw, th), Image.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            resized.save(str(target))
            print(f"    Crop+Resize → {target.relative_to(REPO_ROOT)} ({tw}x{th})")
            # Update img for subsequent steps
            img = resized

        elif "resize" in step:
            cfg = step["resize"]
            target = REPO_ROOT / cfg["target"]
            width = cfg.get("width")
            height = cfg.get("height")
            size = cfg.get("size")  # shorthand for square
            if size:
                width, height = size, size
            resized = img.resize((width, height), Image.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            resized.save(str(target))
            print(f"    Resized → {target.relative_to(REPO_ROOT)} ({width}x{height})")

        elif "ico" in step:
            cfg = step["ico"]
            target = REPO_ROOT / cfg["target"]
            size = cfg["size"]
            ico_img = img.resize((size, size), Image.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            ico_img.save(str(target), format="ICO", sizes=[(size, size)])
            print(f"    ICO     → {target.relative_to(REPO_ROOT)} ({size}x{size})")


def _is_transient_error(exc: Exception) -> bool:
    """Heuristic for 'this looks worth retrying on a different model.'

    Covers httpx ReadTimeout (model stalled at TCP layer), genai-wrapped
    5xx responses ('UNAVAILABLE', '503', '504'), and the SDK's own
    timeout exception. Permission/auth errors and 4xx bad-prompt errors
    return False so we don't waste a fallback call.
    """
    msg = str(exc).upper()
    if "TIMEOUT" in msg or "TIMED OUT" in msg:
        return True
    if "UNAVAILABLE" in msg or "503" in msg or "504" in msg or "502" in msg:
        return True
    if "DEADLINE EXCEEDED" in msg:
        return True
    return False


def generate_one(
    client: genai.Client,
    reference_path: Path,
    reference_image: Image.Image,
    key: str,
    output_path: Path,
    prompt: str,
    base_character: str,
    base_atmosphere: str,
    reference_guidance: str,
    torso_text: str,
    mood_text: str,
    model: str = MODEL,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    reference_2_path: Path | None = None,
    reference_2_image: Image.Image | None = None,
    explicit_refs: list[Path] | None = None,
    series_label: str | None = None,
    torso_label: str | None = None,
    mood_label: str | None = None,
    pool_refs: list[Path] | None = None,
    archive_cap: int = ARCHIVE_DEFAULT_CAP,
    request_timeout_ms: int = REQUEST_TIMEOUT_MS,
) -> "bool | str":
    """Generate one image.

    Returns True on success, the string 'retry' when the failure looks
    transient (timeout / 5xx / model overload), False otherwise.

    Composition order: base_character → base_atmosphere → reference_guidance
    → torso → mood → prompt.

    On success, also writes the same image bytes + a sidecar prompt log
    to .regen-archive/<key>/ for retrospective curation.
    """
    sections = [
        base_character,
        base_atmosphere,
        reference_guidance,
        torso_text,
        mood_text,
        prompt,
    ]
    full_prompt = "\n\n".join(s for s in sections if s)

    explicit_refs = explicit_refs or []
    pool_refs = pool_refs or []
    explicit_images: list[Image.Image] = []
    for p in explicit_refs:
        try:
            explicit_images.append(Image.open(p))
        except OSError as exc:
            print(f"  WARN: explicit ref unreadable, skipping: {p} ({exc})", file=sys.stderr)
    pool_images: list[Image.Image] = []
    for p in pool_refs:
        try:
            pool_images.append(Image.open(p))
        except OSError as exc:
            print(f"  WARN: pool ref unreadable, skipping: {p} ({exc})", file=sys.stderr)

    contents: list = [full_prompt, reference_image]
    refs_log: list[Path] = [reference_path]
    if reference_2_image is not None:
        contents.append(reference_2_image)
        if reference_2_path is not None:
            refs_log.append(reference_2_path)
    contents.extend(explicit_images)
    refs_log.extend(explicit_refs)
    contents.extend(pool_images)
    refs_log.extend(pool_refs)

    print(f"\n{'='*60}")
    print(f"  [{key}] → {output_path.relative_to(REPO_ROOT)}")
    print(f"{'='*60}")
    print(f"  Model: {model}")
    if series_label:
        print(f"  Series: {series_label} (+ secondary reference)")
    if torso_label:
        print(f"  Torso variant: {torso_label}")
    if mood_label:
        print(f"  Mood: {mood_label}")
    if explicit_refs:
        print(f"  Explicit refs: {len(explicit_refs)} image(s) from `references:` field")
    if pool_refs:
        print(f"  Pool refs: {len(pool_refs)} image(s) from .reference-pool/")
    if aspect_ratio or image_size:
        print(f"  Image config: aspect_ratio={aspect_ratio}, image_size={image_size}")
    print(f"  Prompt: {prompt[:80]}...")
    print(f"  Generating (timeout {request_timeout_ms // 1000}s)...", flush=True)

    try:
        # Build generation config if aspect_ratio or image_size specified
        gen_config_kwargs: dict = {
            "http_options": genai.types.HttpOptions(timeout=request_timeout_ms),
        }
        if aspect_ratio or image_size:
            image_config_kwargs = {}
            if aspect_ratio:
                image_config_kwargs["aspect_ratio"] = aspect_ratio
            if image_size:
                image_config_kwargs["image_size"] = image_size
            gen_config_kwargs["image_config"] = genai.types.ImageConfig(**image_config_kwargs)

        gen_config = genai.types.GenerateContentConfig(**gen_config_kwargs)

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=gen_config,
        )

        for part in response.parts:
            if part.inline_data is not None:
                image = part.as_image()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                # Archive the EXISTING file (if any) BEFORE we overwrite it.
                # This is the load-bearing piece — without it, iterating on
                # a cover destroys the previous version with no recovery.
                if archive_cap > 0 and output_path.exists():
                    try:
                        existing_bytes = output_path.read_bytes()
                        existing_sha = _sha256_short(existing_bytes)
                        archive_root = ARCHIVE_DIR / key
                        archive_root.mkdir(parents=True, exist_ok=True)
                        existing_path = archive_root / f"{key}-{existing_sha}.png"
                        if not existing_path.exists():
                            existing_path.write_bytes(existing_bytes)
                            # No sidecar — we don't know the prompt that
                            # produced this prior image. The next call to
                            # write_archive_entry will add one for the new
                            # gen.
                            print(
                                f"  Pre-archived existing cover: "
                                f"{existing_path.relative_to(REPO_ROOT)}"
                            )
                    except OSError as exc:
                        print(
                            f"  WARN: could not pre-archive existing cover: {exc}",
                            file=sys.stderr,
                        )
                image.save(str(output_path))
                print(f"  Saved: {output_path.relative_to(REPO_ROOT)}")
                # Archive the exact bytes we just wrote, plus a sidecar log.
                # We re-read instead of using part.inline_data.data so the
                # sha matches the on-disk PNG, which may have been re-encoded
                # by PIL.
                if archive_cap > 0:
                    image_bytes = output_path.read_bytes()
                    prompt_sections = {
                        "base_character": base_character or "",
                        "base_atmosphere": base_atmosphere or "",
                        "reference_guidance": reference_guidance or "",
                        "torso": torso_text or "",
                        "mood": mood_text or "",
                        "prompt": prompt or "",
                    }
                    extra_meta = {
                        "series": series_label or "(none)",
                        "torso_variant": torso_label or "(none)",
                        "mood_key": mood_label or "(none)",
                    }
                    archived = write_archive_entry(
                        key=key,
                        image_bytes=image_bytes,
                        prompt_sections=prompt_sections,
                        refs_used=refs_log,
                        model=model,
                        output_path=output_path,
                        cap=archive_cap,
                        extra_meta=extra_meta,
                    )
                    print(f"  Archived: {archived.relative_to(REPO_ROOT)}")
                return True
            elif part.text is not None:
                print(f"  Model text: {part.text[:200]}", file=sys.stderr)

        print(f"  FAILED: No image in response", file=sys.stderr)
        return False

    except Exception as e:
        if _is_transient_error(e):
            print(f"  TRANSIENT ERROR ({type(e).__name__}): {str(e)[:200]}", file=sys.stderr)
            return "retry"
        print(f"  ERROR: {e}", file=sys.stderr)
        return False


def _resolve_reference_guidance(raw) -> tuple[str, dict[str, dict]]:
    """Accept either legacy string form or dict form {base, series.{name}.{banner,modifiers}}.

    Returns (base_guidance_text, series_map). series_map is keyed by series name
    (papers, building, operating) and each entry has 'banner' (repo-relative path
    or absolute) and 'modifiers' (string injected into the prompt).
    """
    if isinstance(raw, str):
        return raw, {}
    base = raw.get("base", "")
    series = {}
    for name, cfg in (raw.get("series") or {}).items():
        if not isinstance(cfg, dict):
            continue
        series[name] = {
            "banner": cfg.get("banner"),
            "modifiers": cfg.get("modifiers", ""),
        }
    return base, series


def _key_to_torso_default(key: str, series: str | None) -> str:
    """Default torso variant when an image entry doesn't set `torso:` explicitly.

    Falls back to series, then key prefix, then "generic".
    """
    if series in ("papers", "building", "operating"):
        return series
    if key.startswith("paper-"):
        return "papers"
    if key.startswith("building-"):
        return "building"
    if key.startswith("ops-") or key.startswith("operating-"):
        return "operating"
    return "generic"


def main() -> None:
    config = load_prompts(PROMPTS_FILE)
    # New schema uses `base_character` + `base_atmosphere`; old schema used
    # `base_style`. Accept either for graceful transition.
    base_character = config.get("base_character") or config.get("base_style", "")
    base_atmosphere = config.get("base_atmosphere", "")
    base_guidance, series_map = _resolve_reference_guidance(config["reference_guidance"])
    torso_variants: dict[str, str] = config.get("torso_variants", {}) or {}
    mood_presets: dict[str, str] = config.get("moods", {}) or {}
    images = config["images"]

    all_keys = [img["key"] for img in images]

    parser = argparse.ArgumentParser(
        description="Generate all blog images with a consistent character reference"
    )
    parser.add_argument(
        "--reference", "-r", required=True, help="Path to the master reference image"
    )
    parser.add_argument(
        "--only",
        help="Comma-separated list of image keys to generate (default: all)",
    )
    parser.add_argument(
        "--list", action="store_true", help="List all image keys and exit"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be generated without calling the API"
    )
    parser.add_argument(
        "--model", "-m", default=MODEL, help=f"Gemini model (default: {MODEL})"
    )
    parser.add_argument(
        "--fallback-model", default=FALLBACK_MODEL,
        help=(
            "Model to retry with when --model times out or returns 5xx. "
            f"Pass an empty string to disable. Default: {FALLBACK_MODEL}"
        ),
    )
    parser.add_argument(
        "--timeout-seconds", type=int, default=REQUEST_TIMEOUT_MS // 1000,
        help=f"Per-request timeout in seconds (default: {REQUEST_TIMEOUT_MS // 1000})",
    )
    parser.add_argument(
        "--delay", type=int, default=5,
        help="Seconds to wait between API calls to avoid rate limits (default: 5)"
    )
    parser.add_argument(
        "--pool-generic", type=int, default=1,
        help="Number of images to sample from .reference-pool/generic/ per call (default: 1; 0 to disable)"
    )
    parser.add_argument(
        "--pool-series", type=int, default=2,
        help="Number of images to sample from the key's series subdir of .reference-pool/ per call (default: 2; 0 to disable)"
    )
    parser.add_argument(
        "--archive-cap", type=int, default=ARCHIVE_DEFAULT_CAP,
        help=f"Max archived entries to keep per key under .regen-archive/<key>/ (FIFO by mtime; default: {ARCHIVE_DEFAULT_CAP}; 0 disables archiving)"
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Seed the random source used to sample reference-pool images (default: system entropy)"
    )
    args = parser.parse_args()
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    if args.list:
        print("Available image keys:")
        for img in images:
            desc = img.get("description", "")
            print(f"  {img['key']:20s} → {img['output']}  ({desc})")
        return

    # Filter images
    if args.only:
        selected = set(args.only.split(","))
        unknown = selected - set(all_keys)
        if unknown:
            print(f"Error: Unknown keys: {', '.join(unknown)}", file=sys.stderr)
            print(f"Valid keys: {', '.join(all_keys)}", file=sys.stderr)
            sys.exit(1)
        targets = [img for img in images if img["key"] in selected]
    else:
        targets = images

    if args.dry_run:
        print(f"Dry run — would generate {len(targets)} images:\n")
        for img in targets:
            has_pp = " [+post-process]" if img.get("post_process") else ""
            print(f"  {img['key']:20s} → {img['output']}{has_pp}")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    reference_path = Path(args.reference)
    if not reference_path.is_absolute():
        reference_path = (REPO_ROOT / reference_path).resolve()
    reference = Image.open(reference_path)

    print(f"Model: {args.model}")
    print(f"Reference: {args.reference}")
    print(f"Prompts: {PROMPTS_FILE.relative_to(REPO_ROOT)}")
    print(f"Generating {len(targets)} images...")

    # Lazy cache for per-series banner images — load each at most once.
    series_ref_cache: dict[str, tuple[Path, Image.Image]] = {}

    def _series_ref(series_name: str) -> tuple[Path, Image.Image] | tuple[None, None]:
        if series_name in series_ref_cache:
            return series_ref_cache[series_name]
        cfg = series_map.get(series_name)
        if not cfg or not cfg.get("banner"):
            return None, None
        banner_path = Path(cfg["banner"])
        if not banner_path.is_absolute():
            banner_path = REPO_ROOT / banner_path
        if not banner_path.exists():
            print(f"  WARN: series '{series_name}' banner not found at {banner_path}", file=sys.stderr)
            return None, None
        loaded = Image.open(banner_path)
        series_ref_cache[series_name] = (banner_path, loaded)
        return banner_path, loaded

    succeeded = 0
    failed = []
    timeout_ms = args.timeout_seconds * 1000
    fallback_model = args.fallback_model.strip() or None

    for i, img in enumerate(targets):
        key = img["key"]
        output_path = REPO_ROOT / img["output"]
        prompt = img["prompt"]

        series_name = img.get("series")
        ref2_path, ref2_image = _series_ref(series_name) if series_name else (None, None)

        # Torso variant: per-image `torso:` wins, else derived from series/key.
        torso_key = img.get("torso") or _key_to_torso_default(key, series_name)
        torso_text = torso_variants.get(torso_key, "")
        if torso_key and torso_key not in torso_variants:
            print(
                f"  WARN: torso '{torso_key}' not found in torso_variants — "
                "passing empty",
                file=sys.stderr,
            )

        # Mood: per-image `mood:` is either a key into `moods` or a free-form
        # string. Empty / missing → no mood line.
        mood_raw = img.get("mood")
        mood_text = ""
        mood_label = ""
        if mood_raw:
            if mood_raw in mood_presets:
                mood_text = mood_presets[mood_raw]
                mood_label = mood_raw
            else:
                mood_text = mood_raw
                mood_label = "(custom)"

        # Explicit per-image references — paths relative to REPO_ROOT or absolute.
        explicit_refs: list[Path] = []
        for r in img.get("references", []) or []:
            p = Path(r)
            if not p.is_absolute():
                p = REPO_ROOT / p
            if p.exists():
                explicit_refs.append(p)
            else:
                print(
                    f"  WARN: references entry not found: {p} — skipping",
                    file=sys.stderr,
                )

        pool_refs = load_pool_refs(key, args.pool_generic, args.pool_series, rng)

        result = generate_one(
            client, reference_path, reference, key, output_path, prompt,
            base_character, base_atmosphere, base_guidance,
            torso_text, mood_text,
            model=args.model,
            aspect_ratio=img.get("aspect_ratio"),
            image_size=img.get("image_size"),
            reference_2_path=ref2_path,
            reference_2_image=ref2_image,
            explicit_refs=explicit_refs,
            series_label=series_name,
            torso_label=torso_key,
            mood_label=mood_label,
            pool_refs=pool_refs,
            archive_cap=args.archive_cap,
            request_timeout_ms=timeout_ms,
        )

        # Fallback path: when the primary model stalls or 5xxs, retry once
        # with the fallback model (unless --fallback-model "" or the fallback
        # is the same as the primary).
        if result == "retry" and fallback_model and fallback_model != args.model:
            print(f"  Falling back to {fallback_model}...", flush=True)
            result = generate_one(
                client, reference_path, reference, key, output_path, prompt,
                base_character, base_atmosphere, base_guidance,
                torso_text, mood_text,
                model=fallback_model,
                aspect_ratio=img.get("aspect_ratio"),
                image_size=img.get("image_size"),
                reference_2_path=ref2_path,
                reference_2_image=ref2_image,
                explicit_refs=explicit_refs,
                series_label=series_name,
                torso_label=torso_key,
                mood_label=mood_label,
                pool_refs=pool_refs,
                archive_cap=args.archive_cap,
                request_timeout_ms=timeout_ms,
            )

        if result is True:
            succeeded += 1
            # Run post-processing if defined (e.g., favicon resizing)
            if img.get("post_process"):
                print(f"  Post-processing {key}...")
                post_process(output_path, img["post_process"])
        else:
            failed.append(key)

        # Rate limit delay between calls (skip after last)
        if i < len(targets) - 1:
            print(f"  Waiting {args.delay}s before next request...")
            time.sleep(args.delay)

    print(f"\n{'='*60}")
    print(f"  Done: {succeeded}/{len(targets)} succeeded")
    if failed:
        print(f"  Failed: {', '.join(failed)}")
        print(f"\n  Retry failed with: --only {','.join(failed)}")
    print(f"{'='*60}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
