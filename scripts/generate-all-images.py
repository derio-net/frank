#!/usr/bin/env python3
"""Generate all blog images using Gemini with a consistent character reference.

Reads prompts from blog/prompt_for_images.yaml.

Each prompt's master reference is auto-picked per series:
    .reference-pool/papers/reference-papers.png
    .reference-pool/building/reference-building.png
    .reference-pool/operating/reference-operating.png
    .reference-pool/generic/reference-generic.png   (fallback)

Series is taken from the prompt entry's `series:` field, or inferred
from the image key prefix (`paper-` → papers, `building-` → building,
`ops-` → operating; anything else → generic).

Usage:
    ./scripts/generate-all-images.py --only banner-papers
    ./scripts/generate-all-images.py --only building-04-gpu-compute,paper-09-cover
    ./scripts/generate-all-images.py --list
    ./scripts/generate-all-images.py --dry-run

    # Override the per-series pick — applies to every image in this run:
    ./scripts/generate-all-images.py -r path/to/custom-reference.png --only foo

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
# Default aspect ratio when an image entry doesn't set one. Without this,
# the model occasionally adopts the dimensions of a wide secondary reference
# (banner-building.png and banner-operating.png are both 6:1) — see
# ops-23-argocd-drift-detective for the canonical leak case.
DEFAULT_ASPECT_RATIO = "16:9"
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


def select_reference_path(img: dict, override: Path | None) -> Path:
    """Pick the master reference image for this prompt entry.

    Resolution order:
      1. --reference CLI override (applies to every image)
      2. Explicit `series:` field on the entry
      3. _key_to_series(key) prefix-based fallback
      4. .reference-pool/generic/reference-generic.png

    Fails loudly (FileNotFoundError) if NONE of the candidates exist —
    the previous behaviour silently returned a non-existent path and let
    PIL crash later with an opaque error mid-run, after some images had
    already cost API credits.
    """
    if override is not None:
        return override
    series = img.get("series") or _key_to_series(img["key"]) or "generic"
    candidate = POOL_DIR / series / f"reference-{series}.png"
    if candidate.exists():
        return candidate
    generic = POOL_DIR / "generic" / "reference-generic.png"
    if generic.exists():
        return generic
    def _display(p: Path) -> str:
        try:
            return str(p.relative_to(REPO_ROOT))
        except ValueError:
            return str(p)
    raise FileNotFoundError(
        f"no master reference found for series '{series}' on image '{img.get('key', '?')}'. "
        f"Expected {_display(candidate)} (per-series) or "
        f"{_display(generic)} (generic fallback). "
        f"Generate one via scripts/extract-subject.swift or crop a subjects/*.png."
    )


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
    # Render in composition order.
    order = (
        "base_character",
        "base_atmosphere",
        "reference_guidance",
        "torso",
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
    contents.extend(explicit_images)
    refs_log.extend(explicit_refs)
    contents.extend(pool_images)
    refs_log.extend(pool_refs)

    print(f"\n{'='*60}")
    print(f"  [{key}] → {output_path.relative_to(REPO_ROOT)}")
    print(f"{'='*60}")
    print(f"  Model: {model}")
    if series_label:
        print(f"  Series: {series_label}")
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


def _resolve_reference_guidance(raw) -> str:
    """Return the base reference-guidance text.

    Accepts either the legacy string form or the dict form
    `{base: <text>, ...}`. Any other dict keys (the old auto-attached
    `series.<name>.banner` wiring lived here) are ignored — reference
    images are now picked explicitly per image entry via `references:`.
    """
    if isinstance(raw, str):
        return raw
    return raw.get("base", "")


def _key_to_torso_default(key: str, series: str | None) -> str:
    """Default torso variant when an image entry doesn't set `torso:` explicitly.

    Falls back to series, then key prefix (matching `_key_to_series`), then
    "generic". Both prefix-routing functions recognise the SAME prefixes
    (paper-, building-, ops-) — keep them in sync if extending.
    """
    if series in ("papers", "building", "operating"):
        return series
    inferred = _key_to_series(key)
    return inferred if inferred is not None else "generic"


def main() -> None:
    config = load_prompts(PROMPTS_FILE)
    base_character = config.get("base_character", "")
    base_atmosphere = config.get("base_atmosphere", "")
    base_guidance = _resolve_reference_guidance(config["reference_guidance"])
    # Torso variants may be either a single string (legacy) or a list of
    # alternative phrasings (new). We normalise to list-form here so the
    # picker downstream has a uniform shape.
    raw_torso = config.get("torso_variants", {}) or {}
    torso_variants: dict[str, list[str]] = {
        k: ([v] if isinstance(v, str) else list(v or []))
        for k, v in raw_torso.items()
    }
    mood_presets: dict[str, str] = config.get("moods", {}) or {}
    images = config["images"]

    all_keys = [img["key"] for img in images]

    parser = argparse.ArgumentParser(
        description="Generate all blog images with a consistent character reference"
    )
    parser.add_argument(
        "--reference", "-r", default=None,
        help=(
            "Master reference image to use for EVERY generated image "
            "(overrides per-series selection). Default: auto-pick "
            ".reference-pool/<series>/reference-<series>.png based on the "
            "prompt's series: field or the image key prefix."
        ),
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
        "--pool-generic", type=int, default=0,
        help=(
            "Number of images to RANDOMLY sample from .reference-pool/generic/ "
            "per call (default: 0 — explicit `references:` on the image entry "
            "are the canonical path; opt into sampling with --pool-generic N)"
        ),
    )
    parser.add_argument(
        "--pool-series", type=int, default=0,
        help=(
            "Number of images to RANDOMLY sample from .reference-pool/<series>/ "
            "per call (default: 0 — see --pool-generic). Sampling reads from the "
            "series ROOT (curated whole-image anchors), not from subjects/."
        ),
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

    # --reference is now an override. When provided, it wins for every image.
    # When omitted, each image picks its own reference based on series. We
    # cache opened PIL.Image handles by path so repeated picks don't re-open.
    override_ref_path: Path | None = None
    if args.reference:
        p = Path(args.reference)
        override_ref_path = p if p.is_absolute() else (REPO_ROOT / p).resolve()

    _ref_cache: dict[Path, Image.Image] = {}

    def load_reference(path: Path) -> Image.Image:
        if path not in _ref_cache:
            _ref_cache[path] = Image.open(path)
        return _ref_cache[path]

    print(f"Model: {args.model}")
    if override_ref_path is not None:
        print(f"Reference (override, applies to all): {args.reference}")
    else:
        print("Reference: per-image auto-pick from .reference-pool/<series>/reference-<series>.png")
    print(f"Prompts: {PROMPTS_FILE.relative_to(REPO_ROOT)}")
    print(f"Generating {len(targets)} images...")

    succeeded = 0
    failed = []
    timeout_ms = args.timeout_seconds * 1000
    fallback_model = args.fallback_model.strip() or None

    for i, img in enumerate(targets):
        key = img["key"]
        output_path = REPO_ROOT / img["output"]
        prompt = img["prompt"]

        series_name = img.get("series")

        # Per-image master reference (override wins; else pick by series).
        reference_path = select_reference_path(img, override_ref_path)
        reference = load_reference(reference_path)

        # Torso variant: per-image `torso:` wins, else derived from series/key.
        torso_key = img.get("torso") or _key_to_torso_default(key, series_name)
        torso_options = torso_variants.get(torso_key, [])
        if torso_key and torso_key not in torso_variants:
            print(
                f"  WARN: torso '{torso_key}' not found in torso_variants — "
                "passing empty",
                file=sys.stderr,
            )

        # Pick one variant from the list. Per-image override via
        # `torso_variant:` may be either an integer index (0-based into the
        # options list) or a string. A string that exactly matches one of
        # the options selects it by content; any other string is treated as
        # a free-form override and used verbatim (chosen_idx stays None).
        # No override → random pick from the options.
        variant_override = img.get("torso_variant")
        chosen_idx: int | None = None
        if variant_override is None:
            if torso_options:
                chosen_idx = rng.randrange(len(torso_options))
                torso_text = torso_options[chosen_idx]
            else:
                torso_text = ""
        elif isinstance(variant_override, int):
            if not torso_options:
                print(
                    f"  WARN: torso_variant={variant_override} on '{key}' but "
                    f"no options for torso '{torso_key}' — passing empty",
                    file=sys.stderr,
                )
                torso_text = ""
            elif not (0 <= variant_override < len(torso_options)):
                print(
                    f"  ERROR: torso_variant index {variant_override} out of "
                    f"range for torso '{torso_key}' "
                    f"({len(torso_options)} options) on '{key}'",
                    file=sys.stderr,
                )
                sys.exit(1)
            else:
                chosen_idx = variant_override
                torso_text = torso_options[chosen_idx]
        elif isinstance(variant_override, str):
            if variant_override in torso_options:
                chosen_idx = torso_options.index(variant_override)
                torso_text = variant_override
            else:
                # Free-form override — pass through verbatim. The sidecar
                # records "(custom)" so we can still see this happened.
                torso_text = variant_override
        else:
            print(
                f"  ERROR: torso_variant on '{key}' has unsupported type "
                f"{type(variant_override).__name__}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Compose the label that will be recorded in the sidecar so we can
        # trace later which variant produced which image.
        if chosen_idx is not None:
            torso_label = f"{torso_key}[{chosen_idx}]"
        elif variant_override is None and not torso_options:
            torso_label = torso_key
        else:
            torso_label = f"{torso_key}(custom)"

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
            aspect_ratio=img.get("aspect_ratio", DEFAULT_ASPECT_RATIO),
            image_size=img.get("image_size"),
            explicit_refs=explicit_refs,
            series_label=series_name,
            torso_label=torso_label,
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
                aspect_ratio=img.get("aspect_ratio", DEFAULT_ASPECT_RATIO),
                image_size=img.get("image_size"),
                explicit_refs=explicit_refs,
                series_label=series_name,
                torso_label=torso_label,
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
