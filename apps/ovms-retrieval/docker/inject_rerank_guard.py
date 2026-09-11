#!/usr/bin/env python3
"""Bound the rerank batch by rewriting an exported `graph.pbtxt`.

Design: docs/superpowers/specs/2026-09-11--infer--ovms-rerank-batch-guard-design.md

`RerankCalculatorOV` builds ONE inference tensor of shape
`{batch_size, longest_document_tokens}`, so its peak allocation scales with
B x T — the batch size times the length of the *longest* document in the
request, padded across the batch. Upstream already ships both bounds
(`RerankCalculatorOVOptions.max_allowed_chunks`, checked once before any token
is allocated and twice more inside `chunkDocuments`; and
`max_position_embeddings`, which is what actually bounds T). Neither is emitted
by `export_model.py`'s `rerank_graph_ov_template`, so the proto default of
10000 documents is what a freshly exported servable runs with.

`export_model.py` is fetched from a pinned upstream ref and is not forked, so
the Dockerfile's export stage runs this script over each emitted
`graph.pbtxt` instead.

## Why it raises instead of returning the input

A `sed` that silently matched nothing would publish a model image with the
guard absent, and every downstream signal — CI green, ArgoCD Synced, pod
Ready, the `.seed-rev` marker at the new rev — would still agree that it
shipped. Nothing downstream can tell "the guard is set" from "the rewrite
matched nothing", so the rewrite is the only place the difference is
observable. Every unexpected shape is therefore a hard failure that names the
file.

## Why it is textual

`graph.pbtxt` is protobuf TEXT format, and the export stage has no protobuf
runtime for the mediapipe/OVMS message definitions (they are C++-side). This
script is stdlib-only for the same reason. It anchors on the
`[... RerankCalculatorOVOptions]: {` line and brace-matches from there, rather
than matching braces loosely.

Usage:

    python inject_rerank_guard.py /out/gpu/<model>/graph.pbtxt \
        --max-allowed-chunks 64 --max-position-embeddings 2048
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

__all__ = ["GuardInjectionError", "inject", "main"]

#: The two fields this script owns. Any pre-existing copy is replaced, which is
#: what makes a re-run idempotent.
GUARD_FIELDS = ("max_allowed_chunks", "max_position_embeddings")

#: The block to edit. Matched as a WHOLE LINE so that a brace elsewhere in the
#: file cannot be mistaken for the start of the options block. The type URL is
#: matched loosely (`[type.googleapis.com / mediapipe.<name>]`, with or without
#: the spaces upstream's template happens to emit) but the message name is not.
_OPTIONS_ANCHOR = re.compile(
    r"^(?P<indent>[ \t]*)\[[^\]\n]*\bRerankCalculatorOVOptions\s*\]\s*:\s*\{[ \t]*$",
    re.MULTILINE,
)


class GuardInjectionError(RuntimeError):
    """The graph was not the shape this rewriter understands.

    Always fatal: see the module docstring on why a no-op is worse than a
    crash here.
    """


def inject(
    text: str,
    max_allowed_chunks: int,
    max_position_embeddings: int,
    *,
    source: str = "<graph.pbtxt>",
) -> str:
    """Return `text` with both bounds set inside its rerank options block.

    Raises `GuardInjectionError` unless the text contains exactly one
    `RerankCalculatorOVOptions` block in the multi-line shape upstream's
    template emits. Idempotent: re-running replaces the fields rather than
    appending a second copy.
    """
    match = _find_options_block(text, source)
    body_start = match.end()
    body_end = _find_block_close(text, body_start, source)

    fields, closing_indent = _split_block_body(text[body_start:body_end], source)
    rebuilt = _rebuild_body(
        fields,
        block_indent=match.group("indent"),
        closing_indent=closing_indent,
        max_allowed_chunks=max_allowed_chunks,
        max_position_embeddings=max_position_embeddings,
    )
    return text[:body_start] + rebuilt + text[body_end:]


# --- shape checks, each of which is a refusal ------------------------------


def _find_options_block(text: str, source: str) -> re.Match[str]:
    matches = list(_OPTIONS_ANCHOR.finditer(text))
    if not matches:
        raise GuardInjectionError(
            f"{source}: no `[... mediapipe.RerankCalculatorOVOptions]: {{` line. "
            "This file is not a rerank graph, or the exporter's template "
            "changed. Refusing rather than leaving the graph unguarded — an "
            "unguarded graph publishes and looks identical to a guarded one."
        )
    if len(matches) > 1:
        raise GuardInjectionError(
            f"{source}: found {len(matches)} RerankCalculatorOVOptions blocks, "
            "expected exactly 1. Which one bounds the served batch is a guess, "
            "and a guess here ships an unguarded servable."
        )
    return matches[0]


def _find_block_close(text: str, body_start: int, source: str) -> int:
    """Index of the `}` closing the block whose `{` precedes `body_start`.

    Braces inside QUOTED STRINGS and `#` COMMENTS are not structure and must
    not be counted. This is not hypothetical tidiness: the very block being
    edited contains `plugin_config: '{"NUM_STREAMS": "1" }'`, whose braces
    balance only by accident. One extra `{` in such a string — a `CACHE_DIR`
    with a template in it, any nested JSON — makes a naive counter overshoot
    to the brace closing `node_options`, and the rewriter then writes both
    bounds OUTSIDE the options block and reports success. The calculator would
    never read them, the image would publish unguarded, and every downstream
    signal would agree it shipped: exactly the silent no-op this module exists
    to make impossible.
    """
    depth = 1
    quote: str | None = None
    in_comment = False
    index = body_start
    while index < len(text):
        char = text[index]
        if in_comment:
            if char == "\n":
                in_comment = False
        elif quote is not None:
            if char == "\\":
                index += 1  # skip the escaped character, whatever it is
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#":
            in_comment = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise GuardInjectionError(
        f"{source}: the RerankCalculatorOVOptions block is never closed — the "
        "file is truncated or malformed."
    )


def _split_block_body(body: str, source: str) -> tuple[list[str], str]:
    """Split a block body into its field lines and the indent before its `}`."""
    lines = body.split("\n")
    if len(lines) < 2 or lines[-1].strip():
        raise GuardInjectionError(
            f"{source}: the RerankCalculatorOVOptions block is not in the "
            "multi-line form this rewriter understands (one field per line, "
            "closing brace on its own line). Upstream's template emits that "
            "form; if it changed, update this script deliberately rather than "
            "letting a partial rewrite through."
        )
    return lines[1:-1], lines[-1]


# --- rebuilding the block --------------------------------------------------


def _rebuild_body(
    fields: list[str],
    *,
    block_indent: str,
    closing_indent: str,
    max_allowed_chunks: int,
    max_position_embeddings: int,
) -> str:
    """Return the block body with our two fields set, replacing any existing pair.

    Dropping the existing guard fields before re-adding them is what makes a
    re-run idempotent — and what lets phase 3 change the values without
    stacking a second copy the calculator would read in some order nobody
    chose.
    """
    kept = [line for line in fields if not _is_guard_field(line)]
    indent = _field_indent(kept, block_indent)
    if kept:
        kept[-1] = _with_trailing_comma(kept[-1])
    kept.append(f"{indent}max_allowed_chunks: {int(max_allowed_chunks)},")
    kept.append(f"{indent}max_position_embeddings: {int(max_position_embeddings)}")
    return "\n" + "\n".join(kept) + "\n" + closing_indent


# --- small helpers ---------------------------------------------------------


def _is_guard_field(line: str) -> bool:
    stripped = line.strip()
    return any(stripped.startswith(f"{field}:") for field in GUARD_FIELDS)


def _with_trailing_comma(line: str) -> str:
    """Fields are comma-separated in this template; our lines follow the last one."""
    line = line.rstrip()
    return line if line.endswith(",") else line + ","


def _field_indent(fields: list[str], block_indent: str) -> str:
    for line in fields:
        if line.strip():
            return line[: len(line) - len(line.lstrip())]
    return block_indent + "  "


# --- CLI -------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Set max_allowed_chunks and max_position_embeddings in an exported "
            "rerank graph.pbtxt. Fails loudly if the fields cannot be placed."
        )
    )
    parser.add_argument("graph", type=Path, help="path to graph.pbtxt (rewritten in place)")
    parser.add_argument(
        "--max-allowed-chunks",
        type=int,
        required=True,
        help="document AND post-chunking chunk cap; requests above it are refused",
    )
    parser.add_argument(
        "--max-position-embeddings",
        type=int,
        required=True,
        help="per-chunk token ceiling; this is what bounds the padded tensor width",
    )
    args = parser.parse_args(argv)

    try:
        original = args.graph.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"inject_rerank_guard: cannot read {args.graph}: {exc}", file=sys.stderr)
        return 2

    try:
        rewritten = inject(
            original,
            args.max_allowed_chunks,
            args.max_position_embeddings,
            source=str(args.graph),
        )
    except GuardInjectionError as exc:
        print(f"inject_rerank_guard: {exc}", file=sys.stderr)
        return 1

    args.graph.write_text(rewritten, encoding="utf-8")
    print(
        f"inject_rerank_guard: {args.graph}: max_allowed_chunks="
        f"{args.max_allowed_chunks} max_position_embeddings={args.max_position_embeddings}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
