"""Unit tests for the ovms-retrieval benchmark harness — the deliverable of
this whole spike. `scripts/ovms-retrieval-bench.py` measures rerank latency,
embedding dimensionality and throughput against the OVMS Service deployed in
phase 2, run with an explicit `--arm gpu|cpu` so a recorded number can never
be ambiguous about which device produced it.

Contract source of truth:
docs/superpowers/specs/2026-08-02--infer--igpu-embedding-rerank-design.md
("Measurement — the actual deliverable")

Everything here is OFFLINE and PURE: percentile maths, request-body
construction, response parsing, dimension extraction, degeneracy detection,
and CLI-argument handling. No network, no cluster, no subprocess hitting a
real socket — the script's I/O is a thin shell around these functions, which
is exactly what makes them testable without a live OVMS.

Candidate/filler text in here (and in the script) is invented generic filler,
never anything from a real corpus — see agents/rules/third-party-privacy.md
and the spec's "Scope discipline".
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/ovms-retrieval-bench.py"

_spec = importlib.util.spec_from_file_location("ovms_retrieval_bench", SCRIPT)
bench = importlib.util.module_from_spec(_spec)
sys.modules["ovms_retrieval_bench"] = bench
_spec.loader.exec_module(bench)


# --- percentile maths --------------------------------------------------

def test_percentile_p50_of_known_list():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert bench.percentile(values, 50) == pytest.approx(5.5)


def test_percentile_p95_of_known_list():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert bench.percentile(values, 95) == pytest.approx(9.55)


def test_percentile_max_equals_p100():
    values = [3.1, 9.9, 1.2, 7.5]
    assert bench.percentile(values, 100) == pytest.approx(9.9)


def test_percentile_single_value():
    assert bench.percentile([42.0], 50) == pytest.approx(42.0)


def test_percentile_rejects_empty():
    with pytest.raises(ValueError):
        bench.percentile([], 50)


def test_summarize_latencies_reports_p50_p95_max_and_n():
    samples = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    summary = bench.summarize_latencies(samples)
    assert summary["n"] == 10
    assert summary["p50"] == pytest.approx(bench.percentile(samples, 50))
    assert summary["p95"] == pytest.approx(bench.percentile(samples, 95))
    assert summary["max"] == pytest.approx(100.0)


# --- filler passage generation ------------------------------------------

def test_generate_filler_passages_returns_requested_count():
    passages = bench.generate_filler_passages(20)
    assert len(passages) == 20
    assert all(isinstance(p, str) and p.strip() for p in passages)


def test_generate_filler_passages_are_distinct():
    passages = bench.generate_filler_passages(20)
    assert len(set(passages)) == len(passages)


def test_generate_filler_query_is_a_nonempty_string():
    query = bench.generate_filler_query()
    assert isinstance(query, str) and query.strip()


# --- rerank request/response shape --------------------------------------

def test_build_rerank_request_shape():
    body = bench.build_rerank_request("bge-reranker-v2-m3", "a query", ["doc a", "doc b"])
    assert body == {
        "model": "bge-reranker-v2-m3",
        "query": "a query",
        "documents": ["doc a", "doc b"],
    }


def test_parse_rerank_scores_orders_by_index():
    # OVMS returns results re-ordered by relevance, not by input index.
    response = {
        "results": [
            {"index": 2, "relevance_score": 0.1},
            {"index": 0, "relevance_score": 0.9},
            {"index": 1, "relevance_score": 0.5},
        ]
    }
    assert bench.parse_rerank_scores(response) == [0.9, 0.5, 0.1]


def test_parse_rerank_scores_empty_results():
    assert bench.parse_rerank_scores({"results": []}) == []


# --- embeddings request/response shape ----------------------------------

def test_build_embeddings_request_shape_single():
    body = bench.build_embeddings_request("bge-m3", ["one passage"])
    assert body == {"model": "bge-m3", "input": ["one passage"]}


def test_build_embeddings_request_shape_batch():
    inputs = [f"passage {i}" for i in range(32)]
    body = bench.build_embeddings_request("bge-m3", inputs)
    assert body["input"] == inputs
    assert len(body["input"]) == 32


def test_parse_embedding_vectors_extracts_all_vectors():
    response = {
        "data": [
            {"embedding": [0.1, 0.2, 0.3]},
            {"embedding": [0.4, 0.5, 0.6]},
        ]
    }
    vectors = bench.parse_embedding_vectors(response)
    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


def test_embedding_dimension_reads_from_response_not_hardcoded():
    # Deliberately NOT 1024 — the function must read whatever the response says.
    response = {"data": [{"embedding": [0.0] * 777}]}
    vectors = bench.parse_embedding_vectors(response)
    assert bench.embedding_dimension(vectors) == 777


def test_embedding_dimension_rejects_inconsistent_vectors():
    vectors = [[0.1, 0.2, 0.3], [0.1, 0.2]]
    with pytest.raises(ValueError):
        bench.embedding_dimension(vectors)


def test_embedding_dimension_rejects_empty():
    with pytest.raises(ValueError):
        bench.embedding_dimension([])


# --- score-degeneracy detection -----------------------------------------
# Signature to catch: a reranker served as the wrong model class emits scores
# in the ~1e-9..1e-12 range with poor separation between candidates. Detecting
# it automatically beats eyeballing a printed list.

def test_degenerate_scores_are_flagged():
    scores = [1.2e-10, 3.4e-11, 8.9e-12, 5.6e-10, 2.1e-11]
    assert bench.scores_are_degenerate(scores) is True


def test_healthy_well_separated_scores_are_not_flagged():
    scores = [0.92, 0.81, 0.45, 0.12, 0.03]
    assert bench.scores_are_degenerate(scores) is False


def test_tiny_but_well_separated_scores_are_not_flagged():
    # Magnitude alone isn't the signal — it's tiny magnitude AND poor
    # separation together. A legitimately confident-but-scaled score set
    # should not trip the check just for being small.
    scores = [1e-3, 5e-5, 1e-7]
    assert bench.scores_are_degenerate(scores) is False


def test_single_score_is_never_degenerate():
    assert bench.scores_are_degenerate([0.5]) is False
    assert bench.scores_are_degenerate([]) is False


def test_all_zero_scores_are_not_flagged_by_this_specific_check():
    # Explicitly scoped to the measured signature (~1e-9..1e-12); an all-zero
    # response is a different failure mode this check does not claim to cover.
    assert bench.scores_are_degenerate([0.0, 0.0, 0.0]) is False


# --- CLI: --arm is required, no default ---------------------------------

def test_arm_is_required_with_no_default():
    with pytest.raises(SystemExit) as exc_info:
        bench.parse_args([])
    assert exc_info.value.code != 0


def test_arm_rejects_unknown_value():
    with pytest.raises(SystemExit) as exc_info:
        bench.parse_args(["--arm", "npu"])
    assert exc_info.value.code != 0


def test_arm_gpu_is_accepted():
    args = bench.parse_args(["--arm", "gpu"])
    assert args.arm == "gpu"


def test_arm_cpu_is_accepted():
    args = bench.parse_args(["--arm", "cpu"])
    assert args.arm == "cpu"


def test_arm_has_no_default_on_the_parser():
    parser = bench.build_arg_parser()
    arm_action = next(a for a in parser._actions if a.dest == "arm")
    assert arm_action.default is None
    assert arm_action.required is True


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc_info:
        bench.parse_args(["--help"])
    assert exc_info.value.code == 0


# --- JSON result payload shape -------------------------------------------

def test_build_result_payload_includes_arm_model_batch_iterations_and_percentiles():
    payload = bench.build_result_payload(
        arm="gpu",
        rerank_model="bge-reranker-v2-m3",
        embeddings_model="bge-m3",
        rerank_candidates=20,
        rerank_iterations=30,
        rerank_summary={"p50": 10.0, "p95": 20.0, "max": 25.0, "n": 30},
        embedding_dimension=1024,
        embedding_single_summary={"p50": 5.0, "p95": 6.0, "max": 7.0, "n": 30},
        embedding_batch_summary={"p50": 50.0, "p95": 60.0, "max": 70.0, "n": 30},
        embedding_batch_size=32,
        degenerate=False,
    )
    assert payload["arm"] == "gpu"
    assert payload["rerank"]["model"] == "bge-reranker-v2-m3"
    assert payload["rerank"]["candidates"] == 20
    assert payload["rerank"]["iterations"] == 30
    assert payload["rerank"]["latency_ms"]["p50"] == 10.0
    assert payload["rerank"]["latency_ms"]["p95"] == 20.0
    assert payload["rerank"]["latency_ms"]["max"] == 25.0
    assert payload["rerank"]["degenerate_scores"] is False
    assert payload["embeddings"]["model"] == "bge-m3"
    assert payload["embeddings"]["dimension"] == 1024
    assert payload["embeddings"]["batch_size"] == 32
    assert payload["embeddings"]["single_latency_ms"]["p50"] == 5.0
    assert payload["embeddings"]["batch_latency_ms"]["p50"] == 50.0


def test_build_result_payload_is_json_serializable():
    import json

    payload = bench.build_result_payload(
        arm="cpu",
        rerank_model="bge-reranker-v2-m3",
        embeddings_model="bge-m3",
        rerank_candidates=20,
        rerank_iterations=30,
        rerank_summary={"p50": 1.0, "p95": 2.0, "max": 3.0, "n": 30},
        embedding_dimension=1024,
        embedding_single_summary={"p50": 1.0, "p95": 2.0, "max": 3.0, "n": 30},
        embedding_batch_summary={"p50": 1.0, "p95": 2.0, "max": 3.0, "n": 30},
        embedding_batch_size=32,
        degenerate=True,
    )
    json.dumps(payload)  # must not raise
