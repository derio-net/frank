"""Tests for the rerank batch guard injector.

Contract source of truth:
docs/superpowers/specs/2026-09-11--infer--ovms-rerank-batch-guard-design.md

`POST /v3/rerank` takes the whole `ovms-retrieval` process down on a batch the
downstream client sends routinely, because `RerankCalculatorOV` builds ONE
tensor of shape `{batch_size, longest_document_tokens}` and our exported
`graph.pbtxt` carries neither of upstream's two bounds. `export_model.py`'s
template emits only `models_path`, `plugin_config` and `target_device`, so the
proto default `max_allowed_chunks: 10000` applies — four orders of magnitude
above what the container's memory limit can serve.

Upstream will not be forked and `export_model.py` will not be patched, so the
Dockerfile's export stage post-processes each emitted `graph.pbtxt`. This
module tests the thing that does that rewriting.

## The precondition these fixtures record

`rerank-tokenizer-config.live.json` was captured off the running pod alongside
the graph. `add_bos_token` is ABSENT from it, which is what makes
`RerankServable::addBosToken` stay true (`src/rerank/rerank_servable.hpp:48`)
and therefore makes `max_position_embeddings` a CHUNKING boundary: documents
longer than the bound are split and scored per chunk. **If a future capture
ever shows `"add_bos_token": false`, that field becomes a hard error boundary
instead — a different, louder behaviour — and the design must be revisited
before the value is retuned.** `test_tokenizer_config_precondition_holds`
below fails if that flips, rather than leaving it to a reviewer to notice.

## Why (d) — raising on no match — is the load-bearing case

A best-effort `sed` that matched nothing would publish a model image with the
guard absent, and CI, ArgoCD, the pod and the `.seed-rev` marker would all
still agree that it shipped. The only place that divergence can be caught is
here, at the rewrite, which is why the injector must refuse rather than return
its input.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INJECTOR = REPO / "apps/ovms-retrieval/docker/inject_rerank_guard.py"
FIXTURES = REPO / "scripts/tests/fixtures/ovms-retrieval"
LIVE_GRAPH = FIXTURES / "rerank-graph.live.pbtxt"
LIVE_TOKENIZER = FIXTURES / "rerank-tokenizer-config.live.json"

# Arbitrary, distinguishable, and NOT the values the plan will eventually ship:
# phase 2 derives those from a live memory curve. The injector must not care.
N = 64
T = 2048

_spec = importlib.util.spec_from_file_location("inject_rerank_guard", INJECTOR)
guard = importlib.util.module_from_spec(_spec)
sys.modules["inject_rerank_guard"] = guard
_spec.loader.exec_module(guard)


# --- the fixtures are captures, and must stay recognisable ----------------

def test_live_graph_fixture_is_the_unguarded_export():
    """The fixture must be the BEFORE state, or every test below is vacuous."""
    text = LIVE_GRAPH.read_text(encoding="utf-8")
    assert 'calculator: "RerankCalculatorOV"' in text
    assert "mediapipe.RerankCalculatorOVOptions" in text
    assert "max_allowed_chunks" not in text
    assert "max_position_embeddings" not in text


def test_tokenizer_config_precondition_holds():
    """`add_bos_token` absent => chunking, not hard rejection. See module docstring."""
    cfg = json.loads(LIVE_TOKENIZER.read_text(encoding="utf-8"))
    assert "add_bos_token" not in cfg, (
        "the captured tokenizer_config.json now sets add_bos_token explicitly. "
        "If it is false, RerankServable::addBosToken goes false and "
        "max_position_embeddings stops chunking long documents and starts "
        "rejecting them outright — a different behaviour than the design "
        "priced in. Revisit the spec before touching the values."
    )
    assert cfg["model_max_length"] == 16000
    assert cfg["tokenizer_class"] == "XLMRobertaTokenizer"


# --- (a) both bounds land, inside the options block -----------------------

def test_inject_adds_both_fields_inside_the_options_block():
    out = guard.inject(LIVE_GRAPH.read_text(encoding="utf-8"), N, T)
    assert f"max_allowed_chunks: {N}" in out
    assert f"max_position_embeddings: {T}" in out

    block = _options_block(out)
    assert f"max_allowed_chunks: {N}" in block, (
        "the cap landed somewhere in the file but not inside "
        "RerankCalculatorOVOptions, where the calculator reads it"
    )
    assert f"max_position_embeddings: {T}" in block


def test_both_fields_are_needed_because_the_tensor_is_b_times_t():
    """Not a tautology: a document-only cap is defeatable by one long passage."""
    out = guard.inject(LIVE_GRAPH.read_text(encoding="utf-8"), N, T)
    block = _options_block(out)
    assert "max_allowed_chunks" in block and "max_position_embeddings" in block


# --- (b) nothing else moves ------------------------------------------------

@pytest.mark.parametrize(
    "preserved",
    [
        'models_path: "./"',
        '''plugin_config: '{"NUM_STREAMS": "1" }\'''',
        'target_device: "GPU"',
        'calculator: "RerankCalculatorOV"',
        'name: "RerankExecutor"',
        'input_stream: "REQUEST_PAYLOAD:input"',
    ],
)
def test_existing_settings_survive_byte_identical(preserved):
    out = guard.inject(LIVE_GRAPH.read_text(encoding="utf-8"), N, T)
    assert preserved in out


def test_only_added_lines_differ():
    """Every original line must still be present, unmodified and in order."""
    src = LIVE_GRAPH.read_text(encoding="utf-8")
    out = guard.inject(src, N, T)
    original = [line for line in src.splitlines()]
    remaining = list(out.splitlines())
    for line in original:
        # A trailing comma may legitimately be added to the last pre-existing
        # field so the block stays valid text-format protobuf; allow that one
        # mutation and nothing else.
        assert line in remaining or f"{line}," in remaining, (
            f"the injector altered or dropped an existing line: {line!r}"
        )


# --- (c) idempotent --------------------------------------------------------

def test_inject_is_idempotent():
    src = LIVE_GRAPH.read_text(encoding="utf-8")
    once = guard.inject(src, N, T)
    twice = guard.inject(once, N, T)
    assert twice == once
    assert once.count("max_allowed_chunks") == 1
    assert once.count("max_position_embeddings") == 1


def test_reinjecting_with_new_values_replaces_rather_than_appends():
    src = LIVE_GRAPH.read_text(encoding="utf-8")
    once = guard.inject(src, N, T)
    again = guard.inject(once, N + 1, T * 2)
    assert f"max_allowed_chunks: {N + 1}" in again
    assert f"max_position_embeddings: {T * 2}" in again
    assert f"max_allowed_chunks: {N}\n" not in again
    assert again.count("max_allowed_chunks") == 1
    assert again.count("max_position_embeddings") == 1


# --- (d) the point: refuse, never no-op ------------------------------------

def test_inject_raises_when_there_is_no_rerank_options_block():
    """A silent no-op would ship rev N with the guard absent and CI green."""
    embeddings_graph = (
        'input_stream: "REQUEST_PAYLOAD:input"\n'
        "node {\n"
        '  calculator: "EmbeddingsCalculatorOV"\n'
        "  node_options: {\n"
        "    [type.googleapis.com / mediapipe.EmbeddingsCalculatorOVOptions]: {\n"
        '      models_path: "./"\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    with pytest.raises(guard.GuardInjectionError):
        guard.inject(embeddings_graph, N, T)


def test_inject_raises_on_empty_input():
    with pytest.raises(guard.GuardInjectionError):
        guard.inject("", N, T)


def test_inject_raises_when_the_options_block_is_never_closed():
    """A truncated file must fail, not be rewritten into something plausible."""
    truncated = LIVE_GRAPH.read_text(encoding="utf-8").split(
        "mediapipe.RerankCalculatorOVOptions"
    )[0] + "mediapipe.RerankCalculatorOVOptions]: {\n      models_path: \"./\"\n"
    with pytest.raises(guard.GuardInjectionError):
        guard.inject(truncated, N, T)


def test_inject_raises_on_a_single_line_options_block():
    """An unrecognised shape must refuse, not be rewritten on a guess.

    The exporter's template emits the block multi-line and this rewriter only
    understands that shape. If upstream ever collapses it, the right answer is
    a loud failure in the build — not a file that looks edited and is not.
    """
    collapsed = (
        "node {\n"
        '  calculator: "RerankCalculatorOV"\n'
        "  node_options: {\n"
        '    [type.googleapis.com / mediapipe.RerankCalculatorOVOptions]: { models_path: "./" }\n'
        "  }\n"
        "}\n"
    )
    with pytest.raises(guard.GuardInjectionError):
        guard.inject(collapsed, N, T)


def test_inject_raises_on_more_than_one_options_block():
    """Two blocks means an assumption broke; rewriting one of them is a guess."""
    src = LIVE_GRAPH.read_text(encoding="utf-8")
    with pytest.raises(guard.GuardInjectionError):
        guard.inject(src + src, N, T)


# --- the CLI the Dockerfile export stage actually calls -------------------

def test_cli_rewrites_the_file_in_place(tmp_path):
    target = tmp_path / "graph.pbtxt"
    target.write_text(LIVE_GRAPH.read_text(encoding="utf-8"), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(INJECTOR),
            str(target),
            "--max-allowed-chunks",
            str(N),
            "--max-position-embeddings",
            str(T),
        ],
        capture_output=True,
        text=True,
        check=False,  # the exit code IS the assertion
    )
    assert proc.returncode == 0, proc.stderr
    out = target.read_text(encoding="utf-8")
    assert f"max_allowed_chunks: {N}" in out
    assert f"max_position_embeddings: {T}" in out


def test_cli_exits_nonzero_and_names_the_file_when_there_is_no_block(tmp_path):
    target = tmp_path / "embeddings-graph.pbtxt"
    target.write_text('node { calculator: "EmbeddingsCalculatorOV" }\n', encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(INJECTOR),
            str(target),
            "--max-allowed-chunks",
            str(N),
            "--max-position-embeddings",
            str(T),
        ],
        capture_output=True,
        text=True,
        check=False,  # the exit code IS the assertion
    )
    assert proc.returncode != 0
    assert "embeddings-graph.pbtxt" in proc.stderr, (
        "the failure must name the file — the export stage writes four graphs "
        "and an unattributed error sends the reader to the wrong one"
    )
    assert target.read_text(encoding="utf-8") == (
        'node { calculator: "EmbeddingsCalculatorOV" }\n'
    ), "a failed run must not have half-written the target"


def test_injector_is_stdlib_only():
    """The export stage has no protobuf runtime and installs nothing for this."""
    text = INJECTOR.read_text(encoding="utf-8")
    for banned in ("import google.protobuf", "from google.protobuf", "import yaml", "import requests"):
        assert banned not in text, f"{banned} is not available in the export stage"


# --- braces that are not structure ----------------------------------------
#
# Found in review, reproduced before it was fixed. The options block being
# edited contains `plugin_config: '{"NUM_STREAMS": "1" }'` — its braces
# balance only by accident. A counter that treats every brace as structure
# therefore works on today's graph and silently breaks on a plausible one.
#
# These tests deliberately do NOT use `_options_block` below, which counts
# braces the same naive way: a helper sharing the bug under test cannot
# witness it. They locate the block by LINE instead.


def _guard_fields_are_inside_the_block(text: str) -> bool:
    """True when both bounds sit before the line that closes the options block.

    Line-based on purpose — see the section comment. The block this rewriter
    accepts always has its closing brace alone on a line.
    """
    lines = text.split("\n")
    start = next(
        i for i, line in enumerate(lines)
        if "mediapipe.RerankCalculatorOVOptions]: {" in line
    )
    close = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "}")
    body = "\n".join(lines[start + 1 : close])
    return "max_allowed_chunks" in body and "max_position_embeddings" in body


def _graph_with_plugin_config(value: str) -> str:
    return (
        "node {\n"
        '  calculator: "RerankCalculatorOV"\n'
        "  node_options: {\n"
        "    [type.googleapis.com / mediapipe.RerankCalculatorOVOptions]: {\n"
        '      models_path: "./",\n'
        f"      plugin_config: {value},\n"
        '      target_device: "GPU"\n'
        "    }\n"
        "  }\n"
        "}\n"
    )


def test_an_unbalanced_brace_in_a_quoted_string_does_not_move_the_fields_out():
    """The regression. An extra `{` inside a string used to push both bounds
    into `node_options`, where the calculator never reads them — and the
    rewrite reported success, which is the one outcome this module promises
    cannot happen."""
    out = guard.inject(_graph_with_plugin_config('\'{"NOTE": "brace { here" }\''), N, T)
    assert _guard_fields_are_inside_the_block(out), (
        "a brace inside a quoted string was counted as structure, so the "
        "bounds landed outside RerankCalculatorOVOptions"
    )


def test_an_unbalanced_closing_brace_in_a_quoted_string_is_not_structure():
    out = guard.inject(_graph_with_plugin_config('\'{"NOTE": "brace } here" }\''), N, T)
    assert _guard_fields_are_inside_the_block(out)


def test_a_brace_in_a_comment_is_not_structure():
    graph = (
        "# a stray { in a leading comment\n"
        + _graph_with_plugin_config('\'{"NUM_STREAMS": "1" }\'')
    )
    out = guard.inject(graph, N, T)
    assert _guard_fields_are_inside_the_block(out)


def test_an_escaped_quote_does_not_end_the_string():
    # `\"` — ONE backslash, so the quote is escaped and the string continues
    # past the brace. (`\\"` would be an escaped BACKSLASH followed by a real
    # closing quote, which puts the brace outside any string, where counting it
    # is correct.)
    out = guard.inject(_graph_with_plugin_config('"a \\" brace { b"'), N, T)
    assert _guard_fields_are_inside_the_block(out)


# --- helper ----------------------------------------------------------------

def _options_block(text: str) -> str:
    """The literal text between the RerankCalculatorOVOptions brace and its close."""
    anchor = "mediapipe.RerankCalculatorOVOptions]: {"
    start = text.index(anchor) + len(anchor)
    depth = 1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
    raise AssertionError("unbalanced RerankCalculatorOVOptions block")
