"""Tripwire: the mermaid bundle Hextra fetches at build time must be pinned.

THE FAILURE. Hextra's `_partials/scripts/mermaid.html` (v0.12.3) defaults
`params.mermaid.base` to `https://cdn.jsdelivr.net/npm/mermaid@latest/dist` and
`resources.GetRemote`s the bundle on every build. go.mod pins Hextra, not
mermaid, so the diagram layout a production build ships floats with whatever
mermaid published last. mermaid 11.17.0 (2026-08-19) changed flowchart layout
enough to push 8 of frank's 186 diagrams past the 1400px width gate — the
operating/11-public-edge topology went from 1367px to 2214px — with zero
changes to any diagram source. #787's blog-validate went red on a PR that never
touched a diagram, and the next blog/** push to main would have failed
identically. Proof: the same built public/ with the 11.16.1 bundle swapped in
passes 186/186 (widest 1363px).

THE FIX. `[params.mermaid] base` in blog/hugo.toml pins an exact version, so a
mermaid bump becomes a deliberate, reviewable diff that re-runs the width gate,
not background drift that flips CI red or ships readers a diagram that cannot
be followed by scrolling. To upgrade: bump the version there, rebuild, run
`node blog/scripts/validate_mermaid_layout.mjs --public blog/public`.

Pure-python: reads the TOML, never builds.
"""
import os
import re
import tomllib

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HUGO_TOML = os.path.join(REPO, "blog", "hugo.toml")

PINNED_BASE = re.compile(r"https://cdn\.jsdelivr\.net/npm/mermaid@(\d+\.\d+\.\d+)/dist")


def test_mermaid_cdn_base_is_pinned_to_an_exact_version():
    with open(HUGO_TOML, "rb") as f:
        cfg = tomllib.load(f)
    base = ((cfg.get("params") or {}).get("mermaid") or {}).get("base")
    assert base, (
        "params.mermaid.base is unset in blog/hugo.toml — Hextra falls back to "
        "mermaid@latest and diagram layout floats between builds"
    )
    assert PINNED_BASE.fullmatch(base), (
        "params.mermaid.base must pin an exact mermaid release "
        f"(https://cdn.jsdelivr.net/npm/mermaid@X.Y.Z/dist), got {base!r}"
    )
