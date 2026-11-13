#!/usr/bin/env python3
"""Re-pin one agent-images image across manifests (used by agent-images-bump.yml).

A reference is `ghcr.io/derio-net/<img>:<hex-tag>` optionally followed by `@sha256:<64 hex>`.
Tag-only refs get the new tag. Digest-pinned refs get the new tag AND the new tag's digest,
resolved from the registry: runtimes pull by digest and ignore the tag, so rewriting only the tag
leaves the OLD image running under a NEW tag (bump PR frank#965). If the digest cannot be
resolved the run fails; the old digest is never kept.
"""
import re
import subprocess
import sys
from pathlib import Path


class DigestUnresolved(RuntimeError):
    pass


def ref_re(img: str) -> re.Pattern:
    return re.compile(r"(ghcr\.io/derio-net/" + re.escape(img) + r":)[a-f0-9]+(@sha256:[a-f0-9]{64})?")


def repin(text: str, img: str, sha: str, resolve) -> str:
    """Rewrite every `img` ref in `text`. `resolve(img, sha)` -> 'sha256:<64 hex>'."""
    cache: dict[str, str] = {}

    def sub(m: re.Match) -> str:
        if m.group(2) is None:
            return f"{m.group(1)}{sha}"
        if "d" not in cache:
            d = resolve(img, sha)
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", d or ""):
                raise DigestUnresolved(f"{img}:{sha}: unusable digest {d!r}")
            cache["d"] = d
        return f"{m.group(1)}{sha}@{cache['d']}"

    return ref_re(img).sub(sub, text)


def resolve_with_buildx(img: str, sha: str) -> str:
    ref = f"ghcr.io/derio-net/{img}:{sha}"
    out = subprocess.run(["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{.Manifest.Digest}}"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise DigestUnresolved(f"{ref}: {out.stderr.strip() or 'imagetools inspect failed'}")
    return out.stdout.strip()


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("usage: agent_images_repin.py IMAGE SHA FILE...", file=sys.stderr)
        return 2
    img, sha, files = argv[1], argv[2], argv[3:]
    try:
        for f in files:
            p = Path(f)
            old = p.read_text()
            new = repin(old, img, sha, resolve_with_buildx)
            if new != old:
                p.write_text(new)
    except DigestUnresolved as e:
        print(f"::error::cannot resolve digest, refusing to keep the old one: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
