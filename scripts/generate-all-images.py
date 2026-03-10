#!/usr/bin/env python3
"""Generate all blog images using Gemini with a consistent character reference.

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

from google import genai
from PIL import Image

BASE_STYLE = (
    "Cartoon illustration, vibrant colors, thick outlines, chibi proportions. "
    "Dark background with electric blue lightning accents. "
    "Tech-horror aesthetic, playful not scary."
)

MODEL = "gemini-3-pro-image-preview"

# Each entry: (key, output_path, prompt)
IMAGES = [
    (
        "banner-hero",
        "blog/static/images/banner-hero.png",
        'A wide banner illustration of a wise Frankenstein-like monster made entirely of server hardware. His torso is a rack-mount server chassis with blinking LEDs, shoulders are CPU heatsinks with spinning fans, arms are bundles of ethernet cables and PCIe risers, legs are stacked NVMe SSDs. Bolts on his neck are RJ45 connectors crackling with blue electricity. He stands triumphantly on a pile of Raspberry Pis and NUC mini-PCs, one arm a fist on his side, the other raised, holding a glowing Talos Linux Logo as though saying "To Talos or not to Talos...". His eyes are glowing blue LED status lights. Behind him, a glowing Kubernetes wheel logo floats like a full moon. Wide cinematic aspect ratio.',
    ),
    (
        "banner-thin",
        "blog/static/images/banner-thin.png",
        'A horizontal masthead strip banner in extreme wide-and-short format (about 8:1 aspect ratio). On the left: Frank the Frankenstein monster made of server hardware in chibi proportions, striding confidently to the right, much smaller than in the hero banner — only about 60% the strip height. His torso is a rack-mount server chassis, neck bolts are RJ45 connectors sparking blue electricity, eyes are LED status lights glowing cyan. Centered or right-of-center: the title "Building Frank" in bold chunky retro-tech lettering, glowing electric blue, with subtle circuit-trace underlines. The full width background is a dark circuit board surface with faint PCB green traces, electric blue lightning arcs scattered sparsely across the width. Small decorative icons along the bottom edge: a Raspberry Pi, a NUC mini-PC, an SSD, a Kubernetes wheel — each tiny and icon-like. The composition fades gracefully at both edges into the dark background. Ultra-wide strip, dark background, cartoon illustration, thick outlines, vibrant colors, tech-horror aesthetic playful not scary.',
    ),
    (
        "favicon",
        "blog/static/images/favicon.png",
        "A simple square icon of a green Frankenstein monster head made of computer parts. Flat-top head is a CPU die with circuit traces, neck bolts are USB-C connectors sparking with blue electricity, eyes are blue LED status lights, stitches across forehead are solder traces. Minimal detail, icon-friendly, works at 32x32px. Solid dark background.",
    ),
    (
        "post-00",
        "blog/content/posts/00-overview/cover.png",
        "A Frankenstein monster made of server hardware standing at a workbench, assembling himself. One arm is already attached (ethernet cables), the other is being bolted on (GPU card arm). On the workbench: scattered Raspberry Pis, NUC computers, SSDs, RAM sticks, and a blueprint/schematic showing the full monster design. Electric sparks where parts connect.",
    ),
    (
        "post-01",
        "blog/content/posts/01-introduction/cover.png",
        "A Frankenstein monster made of computer parts sitting at a desk, sketching blueprints of himself on paper. The desk has scattered components — a Raspberry Pi, a NUC mini-PC, a GPU card, ethernet cables. A thought bubble above his head shows a cloud with a red X through it (rejecting cloud). Cozy workshop/lab setting with server rack shelves in background.",
    ),
    (
        "post-02",
        "blog/content/posts/02-foundation/cover.png",
        "A Frankenstein monster made of server hardware laying the foundation of a building. He's placing server nodes like bricks — three identical NUC-shaped bricks for the base layer, connected by glowing green eBPF/cilium network threads that weave between them like mortar. A hexagonal bee (Cilium logo reference) flies nearby. Construction site setting.",
    ),
    (
        "post-03",
        "blog/content/posts/03-storage/cover.png",
        "A Frankenstein monster made of computer parts riding a longhorn bull made of stacked hard drives and SSDs. The bull's horns are SATA cables, its body is a RAID array of glowing drives. The monster holds reins made of iSCSI cables. Three glowing copies of a data block float behind them (representing 3 replicas). Western/ranch setting with server racks as fence posts.",
    ),
    (
        "post-04",
        "blog/content/posts/04-gpu-compute/cover.png",
        "A Frankenstein monster made of server hardware with one massive arm that's an NVIDIA RTX GPU card (green, glowing, oversized) and one regular arm with a smaller Intel Arc GPU (blue glow). The GPU arm crackles with energy but has a red warning sign on it (broken). The Intel arm works perfectly, with a small blue spark. Lightning bolts between the two arms. The monster looks frustrated at the big arm and pleased with the small one.",
    ),
    (
        "post-05",
        "blog/content/posts/05-gitops/cover.png",
        'A Frankenstein monster made of computer parts conducting an orchestra. Each orchestra member is a different Kubernetes pod/container (small box-shaped robots). The monster holds a conductor\'s baton that\'s a git branch, and sheet music on the stand shows YAML code. An octopus (ArgoCD reference) sits on his shoulder, its tentacles reaching out to touch each orchestra member. Musical notes are replaced with sync arrows and checkmarks.',
    ),
    (
        "post-06",
        "blog/content/posts/06-fun-stuff/cover.png",
        'A Frankenstein monster made of server hardware standing in front of a mirror, admiring himself. His chest fans glow with rainbow RGB lighting. He holds a tiny git commit message that says "color: red" and his fans are changing from rainbow to red. A small ArgoCD octopus on his shoulder holds a paintbrush. The monster looks proud and slightly vain. Disco ball made of a CPU die hangs from ceiling.',
    ),
    (
        "post-07",
        "blog/content/posts/07-observability/cover.png",
        "A Frankenstein monster made of server hardware sitting at a desk covered in glowing monitors, each showing colorful time-series graphs, log streams, and Grafana dashboards. His eyes are replaced with magnifying glasses, zooming into the screens. One hand holds a tiny Fluent Bit (a small bird made of log lines), feeding log entries into a funnel on his chest that leads to a glowing database in his torso. A VMSingle label on the database. The monster looks satisfied and analytical. Dark server room background.",
    ),
    (
        "post-08",
        "blog/content/posts/08-backup/cover.png",
        'A Frankenstein monster made of server hardware carefully pouring a glowing stream of data cubes from a Longhorn bull (miniature, made of stacked hard drives) into a large orange bucket labeled "R2" with the Cloudflare logo. The bucket floats in the air like a cloud. In the corner, a Synology NAS box sits on a shelf with a drooping, disconnected NFS cable and a small sad face — a sticky note reads "Soon™". The monster looks focused and responsible. Dark server room background with electric blue lightning accents.',
    ),
    (
        "post-09",
        "blog/content/posts/09-secrets/cover.png",
        'A Frankenstein monster made of server hardware standing in front of a large glowing vault door, carefully placing labeled key-shaped data blocks inside. Each key is engraved with a secret name (DATABASE_URL, REDIS_URL, API_KEY). A small helpful robot labeled "ESO" stands nearby with a stack of sealed envelopes, each addressed to a different pod (small box-shaped robots). The monster looks focused and security-conscious. The vault glows with blue encryption lines. Dark server room background with electric blue lightning accents.',
    ),
    (
        "post-10",
        "blog/content/posts/10-local-inference/cover.png",
        'A Frankenstein monster made of server hardware standing at a grand switchboard console, routing glowing data streams. His left hand pulls a lever connected to a small GPU server rack (labeled with a tiny llama icon), while his right hand gestures toward a cloud portal with multiple provider logos streaming through it. Bright neural-network-style lines flow from both sources into a single unified pipe that feeds into a row of small robot consumers (chatbots, document scanners, coding assistants) waiting eagerly below. The switchboard has a glowing sign reading "LiteLLM". Dark server room background with electric blue and purple lightning accents.',
    ),
    (
        "post-11",
        "blog/content/posts/11-agentic-control-plane/cover.png",
        "A Frankenstein monster made of server hardware standing in a command tower high above a factory floor. Below him, rows of small identical robot workers (agent pods) march in orderly lines, each carrying a glowing task card. The monster holds a large glowing policy scroll in one hand and a conductor's baton in the other, directing the robots. Some robots have green badges (allowed), others have red stop signs (denied by policy). A large glowing screen behind the monster shows a Kubernetes dashboard with CRD icons. A small NATS-branded mailbox sits in the corner, with glowing event streams flowing between the robots and the tower. Dark server room background with electric blue and orange lightning accents.",
    ),
    (
        "post-12",
        "blog/content/posts/12-gpu-talos-fix/cover.png",
        'A Frankenstein monster made of server hardware crouching inside a giant GPU card, using oversized wrenches and soldering irons to reconnect glowing circuit traces. The GPU card\'s casing is open like a panel, revealing tangled wires and blinking validation checkmarks appearing one by one. Sparks fly where connections are being repaired. Around the monster, floating error messages ("Init:0/1", "ContainerCreating", "resource already exists") dissolve into green "Running" status badges as the fixes land. A small Talos Linux penguin-shield logo sits in the corner, watching approvingly. Dark server room background with electric blue and green lightning accents.',
    ),
]

REPO_ROOT = Path(__file__).resolve().parent.parent


def generate_one(
    client: genai.Client, reference: Image.Image, key: str, output_path: Path, prompt: str,
    model: str = MODEL,
) -> bool:
    full_prompt = (
        f"{BASE_STYLE}\n\n"
        f"Use the attached image as the master character reference. "
        f"Keep the character's design exactly consistent.\n\n"
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
    all_keys = [key for key, _, _ in IMAGES]

    parser = argparse.ArgumentParser(
        description="Generate all blog images with a consistent character reference"
    )
    parser.add_argument(
        "--reference", "-r", required=True, help="Path to the master reference image"
    )
    parser.add_argument(
        "--only",
        help=f"Comma-separated list of image keys to generate (default: all)",
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
        for key, path, prompt in IMAGES:
            print(f"  {key:20s} → {path}")
        return

    # Filter images
    if args.only:
        selected = set(args.only.split(","))
        unknown = selected - set(all_keys)
        if unknown:
            print(f"Error: Unknown keys: {', '.join(unknown)}", file=sys.stderr)
            print(f"Valid keys: {', '.join(all_keys)}", file=sys.stderr)
            sys.exit(1)
        targets = [(k, p, pr) for k, p, pr in IMAGES if k in selected]
    else:
        targets = IMAGES

    if args.dry_run:
        print(f"Dry run — would generate {len(targets)} images:\n")
        for key, path, prompt in targets:
            print(f"  {key:20s} → {path}")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    reference = Image.open(args.reference)

    print(f"Model: {MODEL}")
    print(f"Reference: {args.reference}")
    print(f"Generating {len(targets)} images...")

    succeeded = 0
    failed = []

    for i, (key, rel_path, prompt) in enumerate(targets):
        output_path = REPO_ROOT / rel_path

        ok = generate_one(client, reference, key, output_path, prompt, model=args.model)
        if ok:
            succeeded += 1
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
