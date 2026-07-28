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

Lint layer (warnings-first; config block `quality.lint`, data from the fenced
yaml block in skills/educational-writing/references/ai-tells.md — in a
materialized blog, the sibling scripts/ai-tells.md):
  - ai-vocabulary hits FAIL by default; em-dash / negative-parallelism / triad
    densities, cliche conclusion openers, and a missing what-transfers section
    on tutorial/explanation posts WARN. Per-check severity: fail | warn | off.
    Lint failures exit nonzero alongside gate failures; warnings never do.
    `quality.lint.enabled: false` skips the lint (gate-only run).

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
from pathlib import Path

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
#
# Verb stems, NOT `\bword\b`. Writers inflect: real headings say "Verifying the
# Bootstrap" and "Recovery Path", not "Verify" and "Recover". The anchored form
# rejected exactly the sections this check exists to find — on one 83-post blog,
# 27 of 34 gate failures already had such a heading. Trailing `\w*` handles
# verify/verifying/verification and recover/recovery/recovering.
#
# Kept deliberately narrow at the other end: a pattern that matches any heading
# is as useless as one that matches none. `\bsteps\b` stays anchored so
# "Missteps" is not a hit, and narrative headings (Background, Architecture,
# Data Flow) must keep failing — pinned by
# test_narrative_headings_still_do_not_count_as_actionable.
_ACTIONABLE = re.compile(
    r"(reproduce|try\s+it\s+yourself|run\s*book|step[\s-]*by[\s-]*step|"
    r"\bsteps\b|\bprocedure\b|\bhow\s+to\b|\bverif\w*|\brecover\w*|"
    r"\brollback\b|\bchecklist\b|\bwalkthrough\b|\brunbook\b|"
    r"\btroubleshoot\w*|\bdiagnos\w*|\bsmoke\s*test)",
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

# Lint layer (warnings-first, spec §5): built-in per-check severities. Only the
# conservative vocabulary list fails by default — densities warn so prose is
# never written to a regex. Overridable via `quality.lint.severities`
# (fail | warn | off). Thresholds come from the ai-tells data block,
# overridable via `quality.lint.thresholds`.
_LINT_SEVERITIES = {
    "vocabulary": "fail",
    "em_dash": "warn",
    "negative_parallelism": "warn",
    "triad": "warn",
    "conclusion": "warn",
    "what_transfers": "warn",
}


def load_lint_data(path: str | None = None) -> dict:
    """Parse the fenced yaml block in ai-tells.md (single source for lint data).

    Resolution order: explicit `path` → the plugin checkout
    (skills/educational-writing/references/ai-tells.md) → a sibling ai-tells.md
    next to this script (how a materialized blog ships it — scripts/ has no
    skills/ tree). Raises FileNotFoundError when no candidate exists; the CLI
    turns that into a loud LINT SKIPPED, never a crash.
    """
    import yaml
    here = Path(__file__).resolve().parent
    candidates = (
        [Path(path)]
        if path
        else [
            here.parent / "skills/educational-writing/references/ai-tells.md",
            here / "ai-tells.md",
        ]
    )
    for p in candidates:
        if not p.is_file():
            continue
        m = re.search(r"```yaml\n(.*?)```", p.read_text(encoding="utf-8"), re.DOTALL)
        if not m:
            raise ValueError(f"no fenced yaml block in {p}")
        return yaml.safe_load(m.group(1))
    raise FileNotFoundError(
        "ai-tells.md not found (looked at: "
        + ", ".join(str(p) for p in candidates)
        + ")"
    )


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


# ------------------------------------------------------------------ lint layer

def _prose_lines(body: str) -> list[str]:
    """The lines of *body* outside fenced code blocks.

    Fence tracking follows CommonMark's closing rule: a block opened by a
    fence of N backticks/tildes closes only on a fence of the SAME character
    at least N long — so a ````markdown block that itself contains ``` lines
    stays one block, and its inner content never leaks into the prose scan.
    """
    out: list[str] = []
    fence_char = ""
    fence_len = 0
    for line in body.splitlines():
        m = re.match(r"^(`{3,}|~{3,})", line.strip())
        if m:
            marker = m.group(1)
            if not fence_char:  # opening fence
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                fence_char = ""  # closing fence
                fence_len = 0
            # else: a shorter/other-char fence inside an open block is content
            continue
        if fence_char:
            continue
        out.append(line)
    return out


def _prose_only(body: str) -> str:
    """Prose with fenced code blocks, inline code spans, and heading markup gone.

    The lint must never fire on code — a command containing "delve" is not a
    tell. Heading TEXT stays (it is prose); only the leading #s are stripped.
    Typographic apostrophes normalize to ASCII so "isn’t" matches "isn't".
    """
    out = [re.sub(r"^#{1,6}\s+", "", line) for line in _prose_lines(body)]
    text = re.sub(r"`[^`\n]+`", " ", "\n".join(out))
    return text.replace("’", "'")


def lint_post(
    fm: dict, body: str, lint_cfg: dict | None = None, data: dict | None = None
) -> tuple[list[str], list[str]]:
    """AI-tells lint (warnings-first). Returns (failures, warnings).

    `lint_cfg` is the config's `quality.lint` dict (may be None); `data` is the
    parsed ai-tells block (defaults to load_lint_data()). Matching is
    case-insensitive and runs over _prose_only(body) — code and frontmatter
    never trip the lint.
    """
    if data is None:
        data = load_lint_data()
    cfg = lint_cfg or {}
    severities = dict(_LINT_SEVERITIES)
    severities.update(cfg.get("severities") or {})
    thresholds = dict(data.get("thresholds") or {})
    thresholds.update(cfg.get("thresholds") or {})

    prose = _prose_only(body)
    low = prose.lower()
    words = max(len(prose.split()), 1)
    failures: list[str] = []
    warnings: list[str] = []

    def emit(check: str, msg: str) -> None:
        sev = severities.get(check, "warn")
        if sev == "fail":
            failures.append(msg)
        elif sev == "warn":
            warnings.append(msg)
        # "off" drops the message entirely

    # vocabulary: word/phrase-boundary count per entry
    for term in data.get("vocabulary") or []:
        n = len(re.findall(r"\b" + re.escape(str(term).lower()) + r"\b", low))
        if n:
            emit("vocabulary", f"ai-vocabulary: '{term}' ({n}x)")

    # em-dash density per 1000 words
    t = thresholds.get("em_dash_per_1000")
    if t is not None:
        d = prose.count("—") * 1000.0 / words
        if d > t:
            emit("em_dash", f"em-dash density {d:.1f}/1000 words (threshold {t})")

    # regex-pattern densities per 1000 words
    patterns = data.get("patterns") or {}
    for check, tkey, label in (
        ("negative_parallelism", "negative_parallelisms_per_1000",
         "negative-parallelism (not X, but Y)"),
        ("triad", "triads_per_1000", "triad (rule of three)"),
    ):
        pat = patterns.get(check)
        t = thresholds.get(tkey)
        if pat and t is not None:
            d = len(list(re.finditer(pat, low))) * 1000.0 / words
            if d > t:
                emit(check, f"{label} density {d:.1f}/1000 words (threshold {t})")

    # what-transfers: tutorial/explanation posts end with what the reader KEEPS.
    # Keys off the diataxis frontmatter ONLY — never series names.
    if set(_normalize_modes(fm.get("diataxis"))) & {"tutorial", "explanation"}:
        marks = [str(h).lower() for h in data.get("transfer_headings") or []]
        # Headings are collected from prose lines only — a `# takeaway:`
        # comment inside a fenced code block is code, not a heading.
        heads = [
            m.group(1).lower()
            for m in (re.match(r"^#{1,6}\s+(.*)$", ln) for ln in _prose_lines(body))
            if m
        ]
        if not any(mark in head for head in heads for mark in marks):
            emit(
                "what_transfers",
                "no what-transfers closing section "
                "(expected for tutorial/explanation posts)",
            )

    # cliche conclusion openers: any paragraph starting with one. Boundary-
    # aware — "In the ending scene..." must not trip "in the end".
    openers = [str(o).lower() for o in data.get("conclusion_openers") or []]
    for para in re.split(r"\n\s*\n", low):
        p = para.strip()
        for opener in openers:
            if re.match(re.escape(opener) + r"(?!\w)", p):
                emit("conclusion", f"cliche conclusion opener: '{opener}'")
                break

    return failures, warnings


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
    quality = (cfg.get("quality") or {})
    gate = (quality.get("gate") or {})
    lint_cfg = (quality.get("lint") or {})
    skip_series = _non_posts_series_keys(cfg)

    # Lint runs unless explicitly disabled; missing data skips it LOUDLY
    # (a materialized blog whose scripts/ predates ai-tells.md stays gate-only).
    lint_data = None
    if lint_cfg.get("enabled") is not False:
        try:
            lint_data = load_lint_data()
        except (FileNotFoundError, ValueError) as e:
            print(
                f"LINT SKIPPED: {e} — running the structural gate only",
                file=sys.stderr,
            )

    failed: dict[str, list[str]] = {}
    lint_failed = False
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
        if lint_data is not None:
            lfails, lwarns = lint_post(fm, body, lint_cfg, lint_data)
            for msg in lfails:
                print(f"LINT FAIL: {p}: {msg}")
            for msg in lwarns:
                print(f"LINT WARN: {p}: {msg}")
            if lfails:
                lint_failed = True

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
    if lint_failed:
        print(
            "POST LINT FAILED (ai-tells): see LINT FAIL lines above — rewrite "
            "the hits or tune severities under `quality.lint` (fail | warn | off)",
            file=sys.stderr,
        )
    if failed or lint_failed:
        return 1
    print(f"POST QUALITY OK: {checked} post(s) checked, {skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
