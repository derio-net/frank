"""Unit tests for the ovms-retrieval benchmark harness — the deliverable of
this whole spike. `scripts/ovms-retrieval-bench.py` measures rerank latency,
embedding dimensionality and throughput against the OVMS Service deployed in
phase 2, run with an explicit `--arm gpu|cpu` that is CROSS-CHECKED against
the server's own reported state rather than trusted as a label.

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


def test_generate_filler_query_rotates_across_iterations():
    # Sending one identical body 33 times measures a best case with fully warm
    # caches and zero tokenizer variance. Rotating the query costs nothing and
    # is far more honest for a number that gets quoted.
    queries = [bench.generate_filler_query(i) for i in range(8)]
    assert len(set(queries)) > 1
    assert all(isinstance(q, str) and q.strip() for q in queries)


def test_generate_filler_query_is_deterministic_per_index():
    assert bench.generate_filler_query(3) == bench.generate_filler_query(3)


def test_generate_filler_query_targets_a_candidate_topic():
    # The degeneracy magnitude gate is only meaningful if a HEALTHY reranker
    # would score at least one candidate highly. The query therefore names a
    # topic that is present in the candidate set.
    passages = bench.generate_filler_passages(20)
    for i in range(8):
        query = bench.generate_filler_query(i)
        topic = bench._FILLER_TOPICS[i % len(bench._FILLER_TOPICS)]
        assert topic in query
        assert any(topic in p for p in passages)


def test_generate_filler_passages_rotate_with_offset():
    base = bench.generate_filler_passages(20)
    rotated = bench.generate_filler_passages(20, offset=1)
    assert len(rotated) == 20
    assert rotated != base
    assert len(set(rotated)) == len(rotated)


def test_generate_filler_passages_keep_a_comparable_length_when_rotated():
    # Rotation is meant to defeat cache/tokenizer best-casing, NOT to change
    # the amount of work per call — a wildly different token count per
    # iteration would make the latency distribution meaningless.
    lengths = [
        len(p)
        for offset in range(4)
        for p in bench.generate_filler_passages(20, offset=offset)
    ]
    assert max(lengths) - min(lengths) <= 30


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
# Two signatures, either of which means the rerank output is not usable:
#   (a) every score below the magnitude ceiling (1e-6) — the measured
#       signature of a reranker served as the wrong model class, where the
#       whole score set collapses into the ~1e-6..1e-12 floor;
#   (b) no relative separation at ANY magnitude — the model returns
#       essentially the same score for every candidate, so it is not ranking.
# The harness only reaches (a) at all because the benchmark query is written
# to MATCH one candidate topic: a healthy reranker must produce at least one
# clearly-high score, which is what makes a tiny maximum evidence of failure
# rather than evidence of an irrelevant candidate set.

def test_degenerate_scores_are_flagged():
    scores = [1.2e-10, 3.4e-11, 8.9e-12, 5.6e-10, 2.1e-11]
    assert bench.scores_are_degenerate(scores) is True


def test_near_zero_cluster_spanning_orders_of_magnitude_is_flagged():
    # REGRESSION: squarely inside the ~1e-9..1e-12 range named as the measured
    # failure signature, yet the original absolute-separation gate
    # (max - min < 1e-9) did NOT flag it — the spread is 5e-9, wider than the
    # floor it was compared against.
    scores = [5e-9, 8e-10, 4e-11, 1e-12]
    assert bench.scores_are_degenerate(scores) is True


def test_sub_microsecond_score_cluster_is_flagged():
    # REGRESSION: the same blind spot one decade up.
    scores = [3e-7, 9e-8, 4e-8, 2e-8]
    assert bench.scores_are_degenerate(scores) is True


def test_degeneracy_boundary_at_1e_7():
    assert bench.scores_are_degenerate([1e-7, 5e-8, 1e-8]) is True


def test_degeneracy_boundary_at_1e_8():
    assert bench.scores_are_degenerate([1e-8, 5e-9, 1e-9]) is True


def test_scores_at_or_above_the_magnitude_ceiling_are_not_flagged():
    # The ceiling is exclusive: a maximum of exactly 1e-6 is not "below 1e-6".
    assert bench.scores_are_degenerate([1e-6, 1e-9, 1e-12]) is False
    assert bench.scores_are_degenerate([1e-5, 1e-9, 1e-12]) is False


def test_healthy_well_separated_scores_are_not_flagged():
    scores = [0.92, 0.81, 0.45, 0.12, 0.03]
    assert bench.scores_are_degenerate(scores) is False


def test_tiny_but_well_separated_scores_are_not_flagged():
    # A legitimately confident-but-scaled score set: the top score is well
    # clear of the magnitude ceiling and the spread is enormous in relative
    # terms, so neither signature applies.
    scores = [1e-3, 5e-5, 1e-7]
    assert bench.scores_are_degenerate(scores) is False


def test_unseparated_scores_at_healthy_magnitude_are_flagged():
    # Signature (b): a reranker that scores every candidate the same is not
    # ranking, whatever the magnitude. Relative and scale-free, so this holds
    # at 0.5 exactly as it would at 5e-9.
    scores = [0.500000, 0.500100, 0.499900, 0.500050]
    assert bench.scores_are_degenerate(scores) is True


def test_separation_just_wider_than_one_percent_is_not_flagged():
    scores = [1.0, 0.98, 0.97]
    assert bench.scores_are_degenerate(scores) is False


def test_single_score_is_never_degenerate():
    assert bench.scores_are_degenerate([0.5]) is False
    assert bench.scores_are_degenerate([]) is False


def test_all_zero_scores_are_not_flagged_by_this_specific_check():
    # Explicitly scoped to score sets with a positive maximum; an all-zero or
    # all-negative response (raw logits) is a different failure mode this
    # check does not claim to cover.
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


# --- CLI: embedding iterations are their own knob ------------------------
# `--rerank-iterations 5` used to silently shrink the embedding sample too,
# while the payload reported `rerank.iterations` as the only top-level count.

def test_embedding_iterations_has_its_own_flag_defaulting_to_the_shared_default():
    args = bench.parse_args(["--arm", "gpu"])
    assert args.embedding_iterations == bench.RERANK_ITERATIONS


def test_rerank_iterations_does_not_change_the_embedding_sample_size():
    args = bench.parse_args(["--arm", "gpu", "--rerank-iterations", "5"])
    assert args.rerank_iterations == 5
    assert args.embedding_iterations == bench.RERANK_ITERATIONS


def test_embedding_iterations_is_settable_independently():
    args = bench.parse_args(["--arm", "gpu", "--embedding-iterations", "7"])
    assert args.embedding_iterations == 7
    assert args.rerank_iterations == bench.RERANK_ITERATIONS


def test_embedding_warmup_has_its_own_flag():
    args = bench.parse_args(["--arm", "gpu", "--embedding-warmup", "2"])
    assert args.embedding_warmup == 2
    assert bench.parse_args(["--arm", "gpu"]).embedding_warmup == bench.EMBEDDING_WARMUP


# --- server config snapshot: `--arm` must be falsifiable ------------------
# `--arm` is free text. On its own it records an INTENTION, not a fact: the
# phase-5 workflow runs one arm against the default URL and the other against
# a throwaway pod, so a forgotten flag yields a well-formed record attributing
# one device's latency to the other. The snapshot below is what can contradict
# it after the fact.

OVMS_CONFIG_RESPONSE = {
    "bge-m3": {
        "model_version_status": [
            {"version": "1", "state": "AVAILABLE", "status": {"error_code": "OK"}}
        ]
    },
    "bge-reranker-v2-m3": {
        "model_version_status": [
            {"version": "1", "state": "AVAILABLE", "status": {"error_code": "OK"}}
        ]
    },
}


def test_summarize_servables_records_name_version_and_state():
    servables = bench.summarize_servables(OVMS_CONFIG_RESPONSE)
    assert servables == [
        {"name": "bge-m3", "version": "1", "state": "AVAILABLE"},
        {"name": "bge-reranker-v2-m3", "version": "1", "state": "AVAILABLE"},
    ]


def test_summarize_servables_records_a_failed_state_verbatim():
    raw = {
        "bge-m3": {
            "model_version_status": [
                {"version": "1", "state": "LOADING_PRECONDITION_FAILED"}
            ]
        }
    }
    assert bench.summarize_servables(raw)[0]["state"] == "LOADING_PRECONDITION_FAILED"


def test_summarize_servables_tolerates_an_unexpected_shape():
    assert bench.summarize_servables({"weird": "not a dict"}) == []
    assert bench.summarize_servables(None) == []


def test_extract_reported_device_returns_none_for_the_real_config_shape():
    # OVMS's /v1/config reports servable STATE, not target device. The harness
    # must record that honestly rather than pretend it verified the device.
    assert bench.extract_reported_device(OVMS_CONFIG_RESPONSE) is None


def test_extract_reported_device_finds_a_nested_device_field_if_exposed():
    raw = {"bge-m3": {"model_version_status": [{"target_device": "GPU.0"}]}}
    assert bench.extract_reported_device(raw) == "GPU.0"


def test_extract_reported_device_is_case_insensitive_about_the_key():
    raw = {"bge-m3": {"TARGET_DEVICE": "CPU"}}
    assert bench.extract_reported_device(raw) == "CPU"


def test_cross_check_confirms_a_matching_device():
    assert bench.device_cross_check("gpu", "GPU.0") == bench.CROSS_CHECK_CONFIRMED
    assert bench.device_cross_check("cpu", "CPU") == bench.CROSS_CHECK_CONFIRMED


def test_cross_check_contradicts_a_disagreeing_device():
    assert bench.device_cross_check("gpu", "CPU") == bench.CROSS_CHECK_CONTRADICTED
    assert bench.device_cross_check("cpu", "GPU.0") == bench.CROSS_CHECK_CONTRADICTED


def test_cross_check_is_inconclusive_when_no_device_is_reported():
    assert bench.device_cross_check("gpu", None) == bench.CROSS_CHECK_NOT_REPORTED
    assert bench.device_cross_check("gpu", "") == bench.CROSS_CHECK_NOT_REPORTED


def test_cross_check_is_inconclusive_for_a_device_string_it_cannot_read():
    assert bench.device_cross_check("gpu", "AUTO") == bench.CROSS_CHECK_NOT_REPORTED
    assert bench.device_cross_check("gpu", "HETERO:GPU,CPU") == bench.CROSS_CHECK_CONFIRMED


def test_snapshot_records_endpoint_servables_device_and_verdict():
    snapshot = bench.build_server_config_snapshot(
        base_url="http://example.invalid:8000", arm="gpu", raw=OVMS_CONFIG_RESPONSE
    )
    assert snapshot["endpoint"] == "http://example.invalid:8000/v1/config"
    assert snapshot["available"] is True
    assert snapshot["servables"][0]["state"] == "AVAILABLE"
    assert snapshot["reported_device"] is None
    assert snapshot["arm_cross_check"] == bench.CROSS_CHECK_NOT_REPORTED
    assert snapshot["raw"] == OVMS_CONFIG_RESPONSE


def test_snapshot_records_an_unreachable_config_endpoint_rather_than_faking_one():
    snapshot = bench.build_server_config_snapshot(
        base_url="http://example.invalid:8000", arm="gpu", error="connection refused"
    )
    assert snapshot["available"] is False
    assert "connection refused" in snapshot["error"]
    assert snapshot["servables"] == []
    assert snapshot["arm_cross_check"] == bench.CROSS_CHECK_UNAVAILABLE


# --- JSON result payload shape -------------------------------------------

def _payload(**overrides):
    """A fully-specified payload call; individual tests override one field."""
    kwargs = dict(
        arm="gpu",
        base_url="http://example.invalid:8000",
        timestamp="2026-08-02T12:00:00Z",
        server_config=bench.build_server_config_snapshot(
            base_url="http://example.invalid:8000", arm="gpu", raw=OVMS_CONFIG_RESPONSE
        ),
        rerank_model="bge-reranker-v2-m3",
        embeddings_model="bge-m3",
        rerank_candidates=20,
        rerank_iterations=30,
        rerank_summary={"p50": 10.0, "p95": 20.0, "max": 25.0, "n": 30},
        embedding_dimension=1024,
        embedding_iterations=30,
        embedding_single_summary={"p50": 5.0, "p95": 6.0, "max": 7.0, "n": 30},
        embedding_batch_summary={"p50": 50.0, "p95": 60.0, "max": 70.0, "n": 30},
        embedding_batch_size=32,
        degenerate=False,
    )
    kwargs.update(overrides)
    return bench.build_result_payload(**kwargs)


def test_build_result_payload_includes_arm_model_batch_iterations_and_percentiles():
    payload = _payload(
        arm="gpu",
        rerank_summary={"p50": 10.0, "p95": 20.0, "max": 25.0, "n": 30},
        embedding_single_summary={"p50": 5.0, "p95": 6.0, "max": 7.0, "n": 30},
        embedding_batch_summary={"p50": 50.0, "p95": 60.0, "max": 70.0, "n": 30},
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

    payload = _payload(arm="cpu", degenerate=True)
    json.dumps(payload)  # must not raise


def test_payload_records_the_base_url_it_measured():
    # Without this, a record cannot be contradicted: the phase-5 CPU arm runs
    # against a different URL, and a forgotten flag leaves no trace at all.
    payload = _payload(base_url="http://somewhere-else.invalid:8000")
    assert payload["base_url"] == "http://somewhere-else.invalid:8000"


def test_payload_records_a_utc_iso8601_timestamp():
    from datetime import datetime, timezone

    payload = _payload(timestamp="2026-08-02T12:00:00Z")
    stamp = payload["timestamp"]
    assert stamp.endswith("Z")
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)


def test_payload_requires_base_url_timestamp_and_server_config_unconditionally():
    # Keyword-only with no defaults: a caller cannot assemble an
    # authoritative-looking record that omits the evidence.
    for missing in ("base_url", "timestamp", "server_config"):
        kwargs = {
            "arm": "gpu",
            "base_url": "http://example.invalid:8000",
            "timestamp": "2026-08-02T12:00:00Z",
            "server_config": {},
            "rerank_model": "r",
            "embeddings_model": "e",
            "rerank_candidates": 20,
            "rerank_iterations": 30,
            "rerank_summary": {"p50": 1.0, "p95": 2.0, "max": 3.0, "n": 30},
            "embedding_dimension": 1024,
            "embedding_iterations": 30,
            "embedding_single_summary": {"p50": 1.0, "p95": 2.0, "max": 3.0, "n": 30},
            "embedding_batch_summary": {"p50": 1.0, "p95": 2.0, "max": 3.0, "n": 30},
            "embedding_batch_size": 32,
            "degenerate": False,
        }
        kwargs.pop(missing)
        with pytest.raises(TypeError):
            bench.build_result_payload(**kwargs)


def test_payload_embeds_the_server_config_snapshot():
    snapshot = bench.build_server_config_snapshot(
        base_url="http://example.invalid:8000", arm="gpu", raw=OVMS_CONFIG_RESPONSE
    )
    payload = _payload(server_config=snapshot)
    assert payload["server_config"]["servables"][0]["name"] == "bge-m3"
    assert payload["server_config"]["arm_cross_check"] == bench.CROSS_CHECK_NOT_REPORTED
    assert payload["server_config"]["raw"] == OVMS_CONFIG_RESPONSE


def test_payload_records_the_embedding_sample_size_separately_from_rerank():
    payload = _payload(
        rerank_iterations=5,
        embedding_iterations=30,
        rerank_summary={"p50": 1.0, "p95": 2.0, "max": 3.0, "n": 5},
    )
    assert payload["rerank"]["iterations"] == 5
    assert payload["embeddings"]["iterations"] == 30


def test_payload_reports_embedding_throughput_for_single_and_batch():
    payload = _payload(
        embedding_single_summary={"p50": 5.0, "p95": 6.0, "max": 7.0, "n": 30},
        embedding_batch_summary={"p50": 50.0, "p95": 60.0, "max": 70.0, "n": 30},
        embedding_batch_size=32,
    )
    throughput = payload["embeddings"]["throughput_items_per_s"]
    assert throughput["single"] == pytest.approx(1 * 1000.0 / 5.0)
    assert throughput["batch"] == pytest.approx(32 * 1000.0 / 50.0)
    assert "p50" in throughput["basis"]


def test_payload_states_what_the_measured_time_includes():
    # `_time_call` wraps a full client request: fresh TCP connection per call
    # plus client-side json.loads of a several-hundred-KB batch response. That
    # is attributed to the server unless the record says otherwise.
    note = _payload()["timing_includes"].lower()
    assert "json" in note
    assert "connection" in note
    assert "client" in note


# --- throughput maths -----------------------------------------------------

def test_throughput_items_per_s_maths():
    assert bench.throughput_items_per_s(50.0, 32) == pytest.approx(640.0)
    assert bench.throughput_items_per_s(5.0, 1) == pytest.approx(200.0)


def test_throughput_rejects_a_non_positive_latency():
    with pytest.raises(ValueError):
        bench.throughput_items_per_s(0.0, 32)


# --- timing / benchmark loops (offline, with a recording stub) ------------

class _Recorder:
    """Stands in for `_post_json` — records every request body, returns a
    well-shaped canned response. No socket is opened."""

    def __init__(self, dimension: int = 8):
        self.calls: list[tuple[str, dict]] = []
        self.dimension = dimension

    def __call__(self, url, payload, timeout=None):
        self.calls.append((url, payload))
        if url.endswith("/v3/rerank"):
            n = len(payload["documents"])
            return {
                "results": [
                    {"index": i, "relevance_score": 0.9 - (0.05 * i)} for i in range(n)
                ]
            }
        return {
            "data": [{"embedding": [0.1] * self.dimension} for _ in payload["input"]]
        }

    def bodies(self, path: str) -> list[dict]:
        return [p for (u, p) in self.calls if u.endswith(path)]


def test_batch_shape_is_warmed_before_the_timed_batch_loop(monkeypatch):
    # Changing the batch dimension makes the OpenVINO GPU plugin recompile for
    # the new shape — seconds on a cold iGPU. Unwarmed, that lands in
    # `embeddings.batch_latency_ms.max`: the exact figure quoted as worst case.
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        [
            "--arm", "gpu",
            "--embedding-iterations", "4",
            "--embedding-warmup", "2",
            "--embedding-batch-size", "3",
        ]
    )
    _dim, single, batch = bench._run_embeddings_benchmark(args)

    shapes = [len(p["input"]) for p in rec.bodies("/v3/embeddings")]
    assert single["n"] == 4
    assert batch["n"] == 4
    assert shapes.count(3) == 4 + 2, "batch body must be warmed before the timed loop"
    assert shapes.count(1) == 4 + 2
    # ...and the warm-up calls must come first, not be interleaved.
    first_batch = shapes.index(3)
    assert shapes[first_batch : first_batch + 2] == [3, 3]


def test_embedding_loop_uses_embedding_iterations_not_rerank_iterations(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        [
            "--arm", "gpu",
            "--rerank-iterations", "1",
            "--embedding-iterations", "6",
            "--embedding-warmup", "1",
        ]
    )
    _dim, single, batch = bench._run_embeddings_benchmark(args)
    assert single["n"] == 6
    assert batch["n"] == 6


def test_embedding_dimension_is_read_from_the_live_response(monkeypatch):
    rec = _Recorder(dimension=1024)
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--embedding-iterations", "2", "--embedding-warmup", "1"]
    )
    dimension, _single, _batch = bench._run_embeddings_benchmark(args)
    assert dimension == 1024


def test_rerank_rotates_the_query_across_timed_iterations(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-iterations", "6", "--rerank-warmup", "1"]
    )
    bench._run_rerank_benchmark(args)
    queries = [b["query"] for b in rec.bodies("/v3/rerank")]
    assert len(set(queries)) > 1, "identical body every call measures a best case only"


def test_rerank_warmup_calls_are_excluded_from_the_timed_sample(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-iterations", "5", "--rerank-warmup", "3"]
    )
    summary, degenerate = bench._run_rerank_benchmark(args)
    assert summary["n"] == 5
    assert len(rec.bodies("/v3/rerank")) == 8
    assert degenerate is False


# --- batch sweep mode: the instrument the rerank guard is measured with ---
# `docs/superpowers/specs/2026-09-11--infer--ovms-rerank-batch-guard-design.md`
# ("A batch sweep in the benchmark harness"). The sweep walks a list of batch
# sizes and records, per size, latency + HTTP status + body on failure. The
# cap the guard ships with is derived from that curve, so the curve has to be
# trustworthy before it is taken.

def test_parse_sweep_sizes_reads_a_comma_separated_list():
    assert bench.parse_sweep_sizes("10,20,30,40,50") == [10, 20, 30, 40, 50]


def test_parse_sweep_sizes_sorts_ascending_and_dedupes():
    # Ascending is not cosmetic: a size that kills the server leaves it
    # refusing connections for ~10s, so every smaller size must be measured
    # BEFORE it, not after.
    assert bench.parse_sweep_sizes("30,10,20,10") == [10, 20, 30]


def test_parse_sweep_sizes_tolerates_whitespace():
    assert bench.parse_sweep_sizes(" 10 , 20 ") == [10, 20]


def test_parse_sweep_sizes_rejects_garbage():
    for bad in ("", "10,,20", "abc", "10,0", "-5", "10,2.5"):
        with pytest.raises(ValueError):
            bench.parse_sweep_sizes(bad)


def test_rerank_sweep_flag_is_absent_by_default():
    assert bench.parse_args(["--arm", "gpu"]).rerank_sweep is None


def test_rerank_sweep_flag_parses_to_a_size_list():
    args = bench.parse_args(["--arm", "gpu", "--rerank-sweep", "10,20,30,40,50"])
    assert args.rerank_sweep == [10, 20, 30, 40, 50]


def test_sweep_issues_one_call_per_size_in_ascending_order(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-sweep", "40,10,30,20,50", "--rerank-warmup", "0"]
    )
    sweep = bench._run_rerank_sweep(args)

    sizes_sent = [len(b["documents"]) for b in rec.bodies("/v3/rerank")]
    assert sizes_sent == [10, 20, 30, 40, 50]
    assert sweep["sizes"] == [10, 20, 30, 40, 50]
    assert [r["documents"] for r in sweep["results"]] == [10, 20, 30, 40, 50]


def test_sweep_records_documents_words_status_and_latency_per_size(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        [
            "--arm", "gpu",
            "--rerank-sweep", "10,20",
            "--rerank-words", "200",
            "--rerank-warmup", "0",
        ]
    )
    sweep = bench._run_rerank_sweep(args)

    for result in sweep["results"]:
        assert set(["documents", "words_per_document", "status", "latency_ms"]) <= set(result)
        assert result["status"] == 200
        assert result["ok"] is True
        assert isinstance(result["latency_ms"], float) and result["latency_ms"] >= 0.0
        assert result["words_per_document"] == 200


def test_sweep_names_the_model_it_measured(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-sweep", "10", "--rerank-warmup", "0"]
    )
    assert bench._run_rerank_sweep(args)["model"] == bench.DEFAULT_RERANK_MODEL


# --- sweep failure tolerance: the refusal IS the datum --------------------
# `_post_json` wraps `urllib.request.urlopen`, which raises on anything but
# 2xx. So the two outcomes the sweep exists to capture — a guard refusing an
# oversized batch, and a server killed by one — both arrive as exceptions. A
# sweep that propagates them aborts at exactly the size it was run to measure,
# and reports a clean curve of the sizes that happened to survive.

class _FailingRecorder(_Recorder):
    """`_Recorder` that raises at or above a document threshold.

    Records EVERY attempt, including the ones it then fails, so a test can
    assert the sweep carried on to the next size rather than stopping."""

    def __init__(self, *, fail_from: int, error, dimension: int = 8):
        super().__init__(dimension=dimension)
        self.fail_from = fail_from
        self.error = error
        self.attempts: list[tuple[str, dict]] = []

    def __call__(self, url, payload, timeout=None):
        self.attempts.append((url, payload))
        if url.endswith("/v3/rerank") and len(payload["documents"]) >= self.fail_from:
            raise self.error(len(payload["documents"]))
        return super().__call__(url, payload, timeout)

    def attempted_sizes(self, path: str = "/v3/rerank") -> list[int]:
        return [len(p["documents"]) for (u, p) in self.attempts if u.endswith(path)]


def _http_error(documents: int):
    """What an upstream `max_allowed_chunks` refusal looks like on the wire:
    `std::runtime_error` -> `absl::InternalError` -> HTTP 500 with a message
    naming the limit. See the spec's "The refusal is a 500, not a 4xx"."""
    import email.message
    import io
    import urllib.error

    return urllib.error.HTTPError(
        "http://example.invalid:8000/v3/rerank",
        500,
        "Internal Server Error",
        email.message.Message(),
        io.BytesIO(b"Number of documents exceeds max_allowed_chunks"),
    )


def _remote_disconnected(documents: int):
    """What an OOM-killed server looks like: the socket closes mid-request."""
    import http.client

    return http.client.RemoteDisconnected(
        "Remote end closed connection without response"
    )


def _connection_refused(documents: int):
    """What the ~10s after the kill looks like, while the pod restarts."""
    import urllib.error

    return urllib.error.URLError("[Errno 111] Connection refused")


@pytest.mark.parametrize(
    "error_factory",
    [_http_error, _remote_disconnected, _connection_refused],
    ids=["http-500-refusal", "killed-server", "connection-refused"],
)
def test_sweep_records_a_failure_and_continues_to_the_next_size(
    monkeypatch, error_factory
):
    rec = _FailingRecorder(fail_from=30, error=error_factory)
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-sweep", "10,20,30,40,50", "--rerank-warmup", "0"]
    )

    sweep = bench._run_rerank_sweep(args)  # must not raise

    assert rec.attempted_sizes() == [10, 20, 30, 40, 50], (
        "every size must be attempted — a sweep that stops at the first "
        "failure measures only the sizes that happened to survive"
    )
    assert [r["documents"] for r in sweep["results"]] == [10, 20, 30, 40, 50]
    assert [r["ok"] for r in sweep["results"]] == [True, True, False, False, False]


def test_sweep_records_the_refusal_status_and_body_verbatim(monkeypatch):
    # The spec's Test Plan row 6 records the status code and body rather than
    # asserting 4xx. That is only possible if the sweep keeps them.
    rec = _FailingRecorder(fail_from=30, error=_http_error)
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-sweep", "20,30", "--rerank-warmup", "0"]
    )

    sweep = bench._run_rerank_sweep(args)
    refused = sweep["results"][-1]

    assert refused["status"] == 500
    assert "max_allowed_chunks" in refused["body"]
    assert "HTTPError" in refused["error"]


def test_sweep_records_a_killed_server_with_no_status_at_all(monkeypatch):
    # A closed socket has no HTTP status. Recording 0 or 500 here would invent
    # a response the server never sent; None says "no response".
    rec = _FailingRecorder(fail_from=30, error=_remote_disconnected)
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-sweep", "20,30", "--rerank-warmup", "0"]
    )

    killed = bench._run_rerank_sweep(args)["results"][-1]

    assert killed["status"] is None
    assert killed["body"] is None
    assert "RemoteDisconnected" in killed["error"]


def test_sweep_times_a_failed_call_too(monkeypatch):
    # "connection closed without response after 0.13 s" is a datum: a fast
    # failure is a kill, a slow one is a timeout.
    rec = _FailingRecorder(fail_from=10, error=_remote_disconnected)
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-sweep", "10", "--rerank-warmup", "0"]
    )

    result = bench._run_rerank_sweep(args)["results"][0]
    assert isinstance(result["latency_ms"], float)
    assert result["latency_ms"] >= 0.0


# --- sweep warm-up belongs at the smallest size ONLY ----------------------

def test_sweep_warms_up_only_at_the_smallest_size(monkeypatch):
    # Warming at a size the sweep is about to prove fatal spends a restart,
    # and the next size is then measured against a cold server — so the curve
    # records a recompile as batch cost.
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-sweep", "10,20,30", "--rerank-warmup", "2"]
    )
    sweep = bench._run_rerank_sweep(args)

    sizes_sent = [len(b["documents"]) for b in rec.bodies("/v3/rerank")]
    assert sizes_sent == [10, 10, 10, 20, 30], (
        "warm-up must be two extra calls at the SMALLEST size, before the "
        "timed sweep, and nowhere else"
    )
    assert sweep["warmup"]["documents"] == 10
    assert sweep["warmup"]["calls"] == 2
    # The warm-up calls are not part of the curve.
    assert [r["documents"] for r in sweep["results"]] == [10, 20, 30]


def test_sweep_warmup_failure_does_not_abort_the_sweep(monkeypatch):
    # If the server is already dead when the sweep starts, that is a datum
    # too — and the sizes still have to be attempted.
    rec = _FailingRecorder(fail_from=1, error=_connection_refused)
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-sweep", "10,20", "--rerank-warmup", "1"]
    )

    sweep = bench._run_rerank_sweep(args)

    assert rec.attempted_sizes() == [10, 10, 20]
    assert [r["ok"] for r in sweep["results"]] == [False, False]


# --- --rerank-words: the sweep must send documents the size of the fault --
# The issue reproduced at 200 words per document and the mechanism is
# batch x longest-document-tokens. The harness's stock filler is ~20 words, so
# a sweep at that length sends roughly a tenth of the tokens per document and
# may never reproduce the OOM at any batch size — while looking like a clean
# run. A curve recorded without its word count is not quotable.

def test_rerank_words_is_absent_by_default():
    assert bench.parse_args(["--arm", "gpu"]).rerank_words is None


def test_rerank_words_parses_as_an_int():
    assert bench.parse_args(["--arm", "gpu", "--rerank-words", "200"]).rerank_words == 200


def test_default_filler_passage_length_is_unchanged():
    # Regression guard on the default path: adding the knob must not move the
    # numbers the parent spec already published with this harness.
    assert bench.generate_filler_passages(3, offset=0) == [
        "This is a general-purpose passage about seasonal gardening "
        "schedules, written as filler candidate text for a retrieval "
        "benchmark.",
        "This is a general-purpose passage about the history of postal "
        "routing, written as filler candidate text for a retrieval "
        "benchmark.",
        "This is a general-purpose passage about basic bicycle "
        "maintenance, written as filler candidate text for a retrieval "
        "benchmark.",
    ]


def test_filler_passages_are_padded_to_the_requested_word_count():
    for passage in bench.generate_filler_passages(8, words=200):
        assert len(passage.split()) == 200


def test_padded_filler_passages_are_still_distinct():
    passages = bench.generate_filler_passages(20, words=200)
    assert len(set(passages)) == 20


def test_padded_filler_passages_still_carry_their_topic():
    # The degeneracy gate only means anything because the query matches a
    # candidate topic. Padding must not bury the anchor.
    for i, passage in enumerate(bench.generate_filler_passages(8, words=200)):
        assert bench._FILLER_TOPICS[i] in passage


def test_padding_reuses_the_existing_filler_vocabulary():
    # Pad, do not invent new prose: every padded word must already appear in
    # the module's own filler text. `scripts/tests/test_third_party_discretion.py`
    # scans this script, and inventing plausible-sounding corpus text is
    # exactly what it exists to prevent.
    # Punctuation is stripped on BOTH sides before comparing: a topic's final
    # word only ever appears comma-attached in the base sentence ("...about
    # basic bicycle maintenance, written as..."), so a bare "maintenance" in
    # the padding is the same word, not a new one.
    def _words(passages):
        return {w.strip(".,()").lower() for w in " ".join(passages).split()} - {""}

    base = _words(bench.generate_filler_passages(20))
    padded = _words(bench.generate_filler_passages(20, words=200))
    assert padded <= base


def test_filler_passages_reject_a_word_count_below_the_base_sentence():
    # Silently returning a 19-word passage for `--rerank-words 5` would make
    # the recorded word count a lie.
    with pytest.raises(ValueError):
        bench.generate_filler_passages(4, words=5)


def test_sweep_sends_passages_of_the_requested_length(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        [
            "--arm", "gpu",
            "--rerank-sweep", "10,20",
            "--rerank-words", "200",
            "--rerank-warmup", "0",
        ]
    )
    bench._run_rerank_sweep(args)

    for body in rec.bodies("/v3/rerank"):
        assert {len(d.split()) for d in body["documents"]} == {200}


def test_sweep_records_the_word_count_it_actually_sent_not_the_flag(monkeypatch):
    # Measured from the bodies, so a padding bug shows up in the record
    # instead of being papered over by echoing the flag back.
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    args = bench.parse_args(
        ["--arm", "gpu", "--rerank-sweep", "10", "--rerank-warmup", "0"]
    )
    sweep = bench._run_rerank_sweep(args)

    sent = max(len(d.split()) for d in rec.bodies("/v3/rerank")[0]["documents"])
    assert sweep["words_per_document_requested"] is None
    assert sweep["results"][0]["words_per_document"] == sent
    assert sent < 50, "the stock filler is the ~20-word passage this knob exists to replace"


# --- the sweep record carries the same provenance as every other record ---
# A curve gets quoted. Quoted without an endpoint and an arm it is a number
# from nowhere — and the two arms run against different URLs, so a forgotten
# flag would otherwise attribute one device's cliff to the other.

def _sweep_section():
    return {
        "model": "bge-reranker-v2-m3",
        "sizes": [10, 20],
        "words_per_document_requested": 200,
        "warmup": {"documents": 10, "calls": 1, "attempts": []},
        "status_note": bench.SWEEP_STATUS_NOTE,
        "results": [
            {
                "documents": 10,
                "words_per_document": 200,
                "status": 200,
                "latency_ms": 1.0,
                "ok": True,
                "error": None,
                "body": None,
                "results_returned": 10,
            }
        ],
    }


def test_sweep_payload_carries_arm_url_timestamp_and_server_config():
    snapshot = bench.build_server_config_snapshot(
        base_url="http://example.invalid:8000", arm="gpu", raw=OVMS_CONFIG_RESPONSE
    )
    payload = bench.build_sweep_payload(
        arm="gpu",
        base_url="http://example.invalid:8000",
        timestamp="2026-09-11T12:00:00Z",
        server_config=snapshot,
        sweep=_sweep_section(),
    )
    assert payload["arm"] == "gpu"
    assert payload["base_url"] == "http://example.invalid:8000"
    assert payload["timestamp"] == "2026-09-11T12:00:00Z"
    assert payload["server_config"]["servables"][0]["name"] == "bge-m3"
    assert payload["sweep"]["sizes"] == [10, 20]
    assert payload["sweep"]["results"][0]["documents"] == 10
    assert "json" in payload["timing_includes"].lower()


def test_sweep_payload_requires_its_provenance_unconditionally():
    for missing in ("arm", "base_url", "timestamp", "server_config", "sweep"):
        kwargs = {
            "arm": "gpu",
            "base_url": "http://example.invalid:8000",
            "timestamp": "2026-09-11T12:00:00Z",
            "server_config": {},
            "sweep": _sweep_section(),
        }
        kwargs.pop(missing)
        with pytest.raises(TypeError):
            bench.build_sweep_payload(**kwargs)


def test_sweep_payload_is_json_serializable():
    import json

    json.dumps(
        bench.build_sweep_payload(
            arm="cpu",
            base_url="http://example.invalid:8000",
            timestamp="2026-09-11T12:00:00Z",
            server_config={},
            sweep=_sweep_section(),
        )
    )


def test_main_in_sweep_mode_writes_a_sweep_record(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(
        bench, "fetch_server_config", lambda base_url: OVMS_CONFIG_RESPONSE
    )
    monkeypatch.setattr(bench, "_post_json", _Recorder())
    ran: list[str] = []
    _stub_benchmarks(monkeypatch, ran)
    out = tmp_path / "sweep.json"

    code = bench.main(
        [
            "--arm", "gpu",
            "--base-url", "http://example.invalid:8000",
            "--rerank-sweep", "10,20",
            "--rerank-words", "200",
            "--rerank-warmup", "1",
            "--output", str(out),
        ]
    )

    assert code == 0
    payload = json.loads(out.read_text())
    assert payload["arm"] == "gpu"
    assert payload["base_url"] == "http://example.invalid:8000"
    assert payload["timestamp"].endswith("Z")
    assert payload["server_config"]["servables"][0]["state"] == "AVAILABLE"
    assert [r["documents"] for r in payload["sweep"]["results"]] == [10, 20]
    assert payload["sweep"]["results"][0]["words_per_document"] == 200
    assert ran == [], (
        "sweep mode replaces the timed benchmark: running a 30-iteration "
        "embeddings loop against a server just deliberately OOM-killed "
        "measures the restart, not the server"
    )


def test_main_in_sweep_mode_records_failures_and_still_exits_zero(
    monkeypatch, tmp_path
):
    import json

    monkeypatch.setattr(
        bench, "fetch_server_config", lambda base_url: OVMS_CONFIG_RESPONSE
    )
    monkeypatch.setattr(
        bench, "_post_json", _FailingRecorder(fail_from=30, error=_http_error)
    )
    _stub_benchmarks(monkeypatch, [])
    out = tmp_path / "sweep.json"

    code = bench.main(
        ["--arm", "gpu", "--rerank-sweep", "20,30", "--rerank-warmup", "0",
         "--output", str(out)]
    )

    # A refused batch is the RESULT, not an error: the run that records it is
    # a successful run. Whether the refusal came at the right size is a
    # judgement made against the curve, not by this exit code.
    assert code == 0
    results = json.loads(out.read_text())["sweep"]["results"]
    assert [r["ok"] for r in results] == [True, False]
    assert results[-1]["status"] == 500


def test_main_in_sweep_mode_still_refuses_a_contradicted_arm(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        bench,
        "fetch_server_config",
        lambda base_url: {"bge-m3": {"target_device": "CPU"}},
    )
    rec = _Recorder()
    monkeypatch.setattr(bench, "_post_json", rec)
    out = tmp_path / "sweep.json"

    code = bench.main(
        ["--arm", "gpu", "--rerank-sweep", "10,20", "--output", str(out)]
    )

    assert code == bench.EXIT_ARM_CONTRADICTED
    assert rec.calls == [], "must not sweep a server that contradicts the arm"
    assert not out.exists()


# --- main(): the arm cross-check is enforced, not just recorded -----------

def _stub_benchmarks(monkeypatch, ran: list[str]):
    def _rerank(args):
        ran.append("rerank")
        return {"p50": 1.0, "p95": 2.0, "max": 3.0, "n": 30}, False

    def _embed(args):
        ran.append("embeddings")
        return (
            1024,
            {"p50": 1.0, "p95": 2.0, "max": 3.0, "n": 30},
            {"p50": 10.0, "p95": 20.0, "max": 30.0, "n": 30},
        )

    monkeypatch.setattr(bench, "_run_rerank_benchmark", _rerank)
    monkeypatch.setattr(bench, "_run_embeddings_benchmark", _embed)


def test_main_fails_loudly_when_the_server_contradicts_the_arm(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(
        bench,
        "fetch_server_config",
        lambda base_url: {"bge-m3": {"target_device": "CPU"}},
    )
    ran: list[str] = []
    _stub_benchmarks(monkeypatch, ran)
    out = tmp_path / "result.json"

    code = bench.main(["--arm", "gpu", "--output", str(out)])

    assert code != 0
    err = capsys.readouterr().err.lower()
    assert "gpu" in err and "cpu" in err
    assert ran == [], "must not measure against a server that contradicts the arm"
    assert not out.exists(), "must not write an authoritative-looking record"


def test_main_records_url_timestamp_and_config_when_the_arm_is_consistent(
    monkeypatch, tmp_path
):
    import json

    monkeypatch.setattr(
        bench, "fetch_server_config", lambda base_url: OVMS_CONFIG_RESPONSE
    )
    _stub_benchmarks(monkeypatch, [])
    out = tmp_path / "result.json"

    code = bench.main(
        ["--arm", "gpu", "--base-url", "http://example.invalid:8000", "--output", str(out)]
    )

    assert code == 0
    payload = json.loads(out.read_text())
    assert payload["base_url"] == "http://example.invalid:8000"
    assert payload["timestamp"].endswith("Z")
    assert payload["server_config"]["servables"][0]["state"] == "AVAILABLE"
    assert payload["server_config"]["arm_cross_check"] == bench.CROSS_CHECK_NOT_REPORTED


def test_main_still_records_when_the_config_endpoint_is_unreachable(
    monkeypatch, tmp_path, capsys
):
    import json
    import urllib.error

    def _boom(base_url):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(bench, "fetch_server_config", _boom)
    _stub_benchmarks(monkeypatch, [])
    out = tmp_path / "result.json"

    code = bench.main(["--arm", "gpu", "--output", str(out)])

    assert code == 0
    payload = json.loads(out.read_text())
    assert payload["server_config"]["available"] is False
    assert payload["server_config"]["arm_cross_check"] == bench.CROSS_CHECK_UNAVAILABLE
    assert "warning" in capsys.readouterr().err.lower()


# --- docstring honesty ----------------------------------------------------

def test_module_docstring_does_not_claim_an_unverifiable_guarantee():
    doc = bench.__doc__
    assert "can never be ambiguous" not in doc
    assert "cross-check" in doc.lower()


def test_module_docstring_states_what_the_timing_includes():
    doc = bench.__doc__.lower()
    assert "json.loads" in doc or "client-side" in doc
