#!/usr/bin/env python3
"""Generate a blog cover image using Gemini image generation with a character reference.

Usage:
    ./scripts/generate-image.py --reference <ref.png> --prompt "Your prompt" --output out.png
    ./scripts/generate-image.py --reference <ref.png> --prompt "Your prompt"  # prints to stdout

Requires GEMINI_API_KEY env var (can be loaded by sourcing .env).
"""

import argparse
import os
import sys
from pathlib import Path

from google import genai
from PIL import Image

BASE_STYLE = (
    "Cartoon illustration, vibrant colors, thick outlines, chibi proportions. "
    "Dark background with electric blue lightning accents. "
    "Tech-horror aesthetic, playful not scary."
)

MODEL = "gemini-3-pro-image-preview"


def generate(reference_path: str, prompt: str, output_path: str | None, model: str = MODEL) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    reference = Image.open(reference_path)

    full_prompt = (
        f"{BASE_STYLE}\n\n"
        f"Use the attached image as the master character reference. "
        f"Keep the character's design exactly consistent.\n\n"
        f"{prompt}"
    )

    print(f"Model: {model}", file=sys.stderr)
    print(f"Reference: {reference_path}", file=sys.stderr)
    print(f"Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}", file=sys.stderr)
    print("Generating...", file=sys.stderr)

    response = client.models.generate_content(
        model=model,
        contents=[full_prompt, reference],
    )

    for part in response.parts:
        if part.inline_data is not None:
            image = part.as_image()
            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                image.save(output_path)
                print(f"Saved to {output_path}", file=sys.stderr)
            else:
                image.save(sys.stdout.buffer, format="PNG")
            return
        elif part.text is not None:
            print(f"Model text response: {part.text}", file=sys.stderr)

    print("Error: No image returned in response", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a blog image using Gemini with a character reference"
    )
    parser.add_argument(
        "--reference", "-r", required=True, help="Path to the master reference image"
    )
    parser.add_argument(
        "--prompt", "-p", required=True, help="Image generation prompt"
    )
    parser.add_argument(
        "--output", "-o", default=None, help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--model", "-m", default=MODEL, help=f"Gemini model (default: {MODEL})"
    )
    args = parser.parse_args()

    generate(args.reference, args.prompt, args.output, model=args.model)


if __name__ == "__main__":
    main()
