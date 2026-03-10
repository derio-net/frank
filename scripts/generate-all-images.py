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
import os
import sys
import time
from pathlib import Path

import yaml
from google import genai
from PIL import Image

MODEL = "gemini-3-pro-image-preview"
REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = REPO_ROOT / "blog" / "prompt_for_images.yaml"


def load_prompts(path: Path) -> dict:
    """Load the YAML prompts file and return parsed config."""
    with open(path) as f:
        return yaml.safe_load(f)


def post_process_favicon(source_path: Path, steps: list[dict]) -> None:
    """Resize/convert the master favicon into required sizes."""
    img = Image.open(source_path)

    for step in steps:
        if "resize" in step:
            cfg = step["resize"]
            target = REPO_ROOT / cfg["target"]
            size = cfg["size"]
            resized = img.resize((size, size), Image.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            resized.save(str(target))
            print(f"    Resized → {target.relative_to(REPO_ROOT)} ({size}x{size})")

        elif "ico" in step:
            cfg = step["ico"]
            target = REPO_ROOT / cfg["target"]
            size = cfg["size"]
            ico_img = img.resize((size, size), Image.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            ico_img.save(str(target), format="ICO", sizes=[(size, size)])
            print(f"    ICO     → {target.relative_to(REPO_ROOT)} ({size}x{size})")


def generate_one(
    client: genai.Client,
    reference: Image.Image,
    key: str,
    output_path: Path,
    prompt: str,
    base_style: str,
    reference_guidance: str,
    model: str = MODEL,
) -> bool:
    full_prompt = (
        f"{base_style}\n\n"
        f"{reference_guidance}\n\n"
        f"{prompt}"
    )

    print(f"\n{'='*60}")
    print(f"  [{key}] → {output_path.relative_to(REPO_ROOT)}")
    print(f"{'='*60}")
    print(f"  Prompt: {prompt[:80]}...")
    print(f"  Generating...", flush=True)

    try:
        response = client.models.generate_content(
            model=model,
            contents=[full_prompt, reference],
        )

        for part in response.parts:
            if part.inline_data is not None:
                image = part.as_image()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(str(output_path))
                print(f"  Saved: {output_path.relative_to(REPO_ROOT)}")
                return True
            elif part.text is not None:
                print(f"  Model text: {part.text[:200]}", file=sys.stderr)

        print(f"  FAILED: No image in response", file=sys.stderr)
        return False

    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return False


def main() -> None:
    config = load_prompts(PROMPTS_FILE)
    base_style = config["base_style"]
    reference_guidance = config["reference_guidance"]
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
        "--delay", type=int, default=5,
        help="Seconds to wait between API calls to avoid rate limits (default: 5)"
    )
    args = parser.parse_args()

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
    reference = Image.open(args.reference)

    print(f"Model: {args.model}")
    print(f"Reference: {args.reference}")
    print(f"Prompts: {PROMPTS_FILE.relative_to(REPO_ROOT)}")
    print(f"Generating {len(targets)} images...")

    succeeded = 0
    failed = []

    for i, img in enumerate(targets):
        key = img["key"]
        output_path = REPO_ROOT / img["output"]
        prompt = img["prompt"]

        ok = generate_one(
            client, reference, key, output_path, prompt,
            base_style, reference_guidance, model=args.model,
        )
        if ok:
            succeeded += 1
            # Run post-processing if defined (e.g., favicon resizing)
            if img.get("post_process"):
                print(f"  Post-processing {key}...")
                post_process_favicon(output_path, img["post_process"])
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
