#!/usr/bin/env python3
"""Validate a post against the educational-writing methodology gate.

The gate is *structural* — it enforces the evidence a genuinely useful teaching
post carries, not prose quality (which no validator can judge). It answers one
question mechanically: "if a reader lands here at 2am with 10 minutes to fix
something, does this post give them what they need?" See
`skills/educational-writing/` for the methodology and `docs/CONFIG.md` for the
`quality` config block that tunes these thresholds.

Enforced (each toggle lives in `quality.gate`):
  - reader_goal      frontmatter states what the reader can DO after reading
  - diataxis         frontmatter declares the Diataxis mode(s) the post serves
  - command blocks   >= min_command_blocks fenced code blocks (mermaid excluded)
  - actionable       >= 1 heading a reader can follow under pressure
                     (Reproduce / Runbook / Steps / Verify / Recover / ...)
  - diagram          how-to / tutorial posts carry >= 1 ```mermaid block
                     (waive one post with `diagram_exempt: <reason>`)

Scope: only `content_type: posts` posts. Papers and explainers ship their own
validators and their own structure, so a post whose series is a papers/explainers
content-type is skipped. A post may opt out with `quality_exempt: <reason>` in
frontmatter (use sparingly — e.g. a pure announcement).

Library:
  validate_post(fm: dict, body: str, gate: dict | None = None) -> list[str]
  split_frontmatter(text: str) -> tuple[dict, str]
CLI:
  validate_educational.py --config <.blog-craft.yaml> <index.md> [<index.md> ...]
"""
from __future__ import annotations

import re
import sys

# Canonical Diataxis modes (see references/diataxis.md). Aliases normalize in.
_DIATAXIS = {"tutorial", "how-to", "reference", "explanation"}
_DIATAXIS_ALIASES = {
    "howto": "how-to",
    "how_to": "how-to",
    "how to": "how-to",
    "how-to-guide": "how-to",
    "guide": "how-to",
    "ref": "reference",
    "explain": "explanation",
    "explanatory": "explanation",
}

# Headings a reader in a hurry can act on. Matched case-insensitively against
# the heading text (not the leading #s).
_ACTIONABLE = re.compile(
    r"(reproduce|try\s+it\s+yourself|run\s*book|step[\s-]*by[\s-]*step|"
    r"\bsteps\b|\bprocedure\b|\bhow\s+to\b|\bverify\b|\brecover\b|"
    r"\brollback\b|\bchecklist\b|\bwalkthrough\b|\brunbook\b)",
    re.IGNORECASE,
)

_DEFAULT_GATE = {
    "require_reader_goal": True,
    "require_diataxis_mode": True,
    "min_command_blocks": 1,
    "require_actionable_section": True,
    "require_diagram": True,
}

# Diátaxis modes that teach a procedure — these must carry a diagram.
_DIAGRAM_MODES = {"how-to", "tutorial"}


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_after_frontmatter)."""
    import yaml
    if not text.startswith("---"):
        raise ValueError("missing opening `---` frontmatter")
    rest = text.split("\n", 1)[1]
    m = re.search(r"^---\s*$", rest, re.MULTILINE)
    if m is None:
        raise ValueError("missing closing `---` frontmatter")
    data = yaml.safe_load(rest[: m.start()])
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    body = rest[m.end():]
    return data, body


def _normalize_modes(value) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[,\s]+", value.strip())
    elif isinstance(value, (list, tuple)):
        raw = [str(v) for v in value]
    else:
        return []
    out = []
    for r in raw:
        if not r:
            continue
        k = r.strip().lower()
        out.append(_DIATAXIS_ALIASES.get(k, k))
    return out


def _count_command_blocks(body: str) -> int:
    """Count fenced code blocks, excluding ```mermaid (diagrams, not evidence)."""
    count = 0
    in_block = False
    is_mermaid = False
    for line in body.splitlines():
        stripped = line.strip()
        fence = re.match(r"^(`{3,}|~{3,})(.*)$", stripped)
        if fence is None:
            continue
        info = fence.group(2).strip().lower()
        if not in_block:
            in_block = True
            is_mermaid = info.startswith("mermaid")
        else:
            # closing fence
            in_block = False
            if not is_mermaid:
                count += 1
            is_mermaid = False
    return count


def _has_mermaid(body: str) -> bool:
    """True if the body contains at least one ```mermaid fenced block.

    Only the opening fence's info string is inspected — a bare "mermaid"
    mentioned in prose or inside another code block never counts.
    """
    in_block = False
    for line in body.splitlines():
        fence = re.match(r"^(`{3,}|~{3,})(.*)$", line.strip())
        if fence is None:
            continue
        if not in_block:
            in_block = True
            if fence.group(2).strip().lower().startswith("mermaid"):
                return True
        else:
            in_block = False
    return False


def _has_actionable_heading(body: str) -> bool:
    for line in body.splitlines():
        m = re.match(r"^#{2,6}\s+(.*)$", line)
        if m and _ACTIONABLE.search(m.group(1)):
            return True
    return False


def validate_post(fm: dict, body: str, gate: dict | None = None) -> list[str]:
    """Structural checks. Returns a list of failure strings (empty == pass)."""
    g = dict(_DEFAULT_GATE)
    if gate:
        g.update({k: v for k, v in gate.items() if v is not None})
    fails: list[str] = []

    if g.get("require_reader_goal"):
        rg = fm.get("reader_goal")
        if not (isinstance(rg, str) and rg.strip()):
            fails.append(
                "missing `reader_goal`: state in one line what the reader can DO "
                "after reading (frontmatter `reader_goal:`)"
            )

    if g.get("require_diataxis_mode"):
        modes = _normalize_modes(fm.get("diataxis"))
        if not modes:
            fails.append(
                "missing `diataxis`: declare the mode(s) this post serves — one or "
                "more of tutorial / how-to / reference / explanation "
                "(frontmatter `diataxis:`)"
            )
        else:
            bad = [m for m in modes if m not in _DIATAXIS]
            if bad:
                fails.append(
                    f"invalid `diataxis` value(s) {bad}: allowed are "
                    f"{sorted(_DIATAXIS)}"
                )

    min_blocks = int(g.get("min_command_blocks", 0) or 0)
    if min_blocks > 0:
        n = _count_command_blocks(body)
        if n < min_blocks:
            fails.append(
                f"too little evidence: found {n} command/output code block(s), "
                f"need >= {min_blocks}. Show real commands and their output, not a "
                f"description of the session (mermaid fences don't count)"
            )

    if g.get("require_actionable_section"):
        if not _has_actionable_heading(body):
            fails.append(
                "no actionable section: add a heading a reader under pressure can "
                "follow (e.g. 'Reproduce', 'Runbook', 'Steps', 'Verify', 'Recover')"
            )

    if g.get("require_diagram") and not fm.get("diagram_exempt"):
        modes = _normalize_modes(fm.get("diataxis"))
        if (_DIAGRAM_MODES & set(modes)) and not _has_mermaid(body):
            fails.append(
                "missing diagram: a how-to/tutorial post should carry at least one "
                "```mermaid block — add a topology/flow diagram so visual learners "
                "can follow the architecture in seconds (or set "
                "`diagram_exempt: <reason>` to waive just this check)"
            )

    return fails


# --------------------------------------------------------------------------- CLI

def _non_posts_series_keys(cfg: dict) -> set[str]:
    """Series keys whose content_type is NOT plain `posts` (papers/explainers/...)."""
    keys = set()
    for s in cfg.get("series") or []:
        if isinstance(s, dict) and s.get("content_type", "posts") != "posts":
            k = s.get("key")
            if isinstance(k, str):
                keys.add(k)
    return keys


def _series_values(series_field) -> list[str]:
    if isinstance(series_field, str):
        return [s.strip() for s in series_field.split(",") if s.strip()]
    if isinstance(series_field, list):
        return [s for s in series_field if isinstance(s, str)]
    return []


def _main(argv):
    import argparse
    import yaml
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)

    cfg = yaml.safe_load(open(a.config)) or {}
    gate = ((cfg.get("quality") or {}).get("gate") or {})
    skip_series = _non_posts_series_keys(cfg)

    failed: dict[str, list[str]] = {}
    checked = 0
    skipped = 0
    for p in a.paths:
        try:
            fm, body = split_frontmatter(open(p).read())
        except Exception as e:  # noqa: BLE001
            failed[p] = [f"parse error: {e}"]
            continue
        # Skip papers/explainers posts — they have their own validators + structure.
        if skip_series and set(_series_values(fm.get("series"))) & skip_series:
            skipped += 1
            continue
        # Per-post opt-out (use sparingly).
        if fm.get("quality_exempt"):
            skipped += 1
            continue
        fails = validate_post(fm, body, gate)
        checked += 1
        if fails:
            failed[p] = fails

    if failed:
        print("POST QUALITY GATE FAILED (educational-writing)", file=sys.stderr)
        for p, fs in failed.items():
            print(f"  {p}:", file=sys.stderr)
            for x in fs:
                print(f"    x {x}", file=sys.stderr)
        print(
            "\n  See skills/educational-writing/ for the methodology, set "
            "`quality_exempt: <reason>` to opt a non-teaching post out, or "
            "`diagram_exempt: <reason>` to waive just the diagram check.",
            file=sys.stderr,
        )
        return 1
    print(f"POST QUALITY OK: {checked} post(s) checked, {skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
