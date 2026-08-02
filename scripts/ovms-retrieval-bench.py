#!/usr/bin/env python3
"""Benchmark harness for the ovms-retrieval Deployment — the deliverable of
the whole iGPU embed+rerank spike is a *number*, and this is what produces it.

Contract source of truth:
docs/superpowers/specs/2026-08-02--infer--igpu-embedding-rerank-design.md
("Measurement — the actual deliverable")

Run from INSIDE the cluster (laptop-side timing measures the LAN, not the
GPU). The target defaults to the phase-2 Service,
`ovms-retrieval.retrieval.svc.cluster.local:8000`.

Measures, per the spec:
  1. Rerank latency — one query against 20 candidate passages, N=30 timed
     iterations after a warm-up, reporting p50 / p95 / max.
  2. Embedding dimensionality — read from the response, never hardcoded.
  3. Embedding throughput — single request and batch-32.
  4. `--arm gpu|cpu` is REQUIRED, with no default, so a recorded measurement
     can never be ambiguous about which device produced it. The CPU arm is a
     genuine control (the minis are 14-core and ~95% idle) — see the spec's
     "Counter-arguments considered" for why a CPU win is a legitimate result,
     not a failure of this harness.

The candidate/query text below is GENERIC invented filler — never the
requester's corpus, queries, or document titles. See
agents/rules/third-party-privacy.md and the spec's "Scope discipline".

This module is structured so every piece of logic (percentile maths, request
construction, response parsing, degeneracy detection, argument parsing, and
payload assembly) is a pure function with no I/O, importable and testable
without a network or a cluster. `main()` is the only thing that talks to a
socket.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://ovms-retrieval.retrieval.svc.cluster.local:8000"
DEFAULT_EMBEDDINGS_MODEL = "bge-m3"
DEFAULT_RERANK_MODEL = "bge-reranker-v2-m3"

RERANK_CANDIDATES = 20
RERANK_ITERATIONS = 30
RERANK_WARMUP = 3
EMBEDDING_BATCH_SIZE = 32
REQUEST_TIMEOUT_S = 30

# Measured signature of a reranker served as the wrong model class: relevance
# scores clustered near-zero (roughly 1e-9..1e-12) with almost no separation
# between candidates. Both conditions must hold — small magnitude alone is
# not evidence of anything (a confident, well-scaled score set can be tiny).
DEGENERACY_MAGNITUDE_CEILING = 1e-6
DEGENERACY_SEPARATION_FLOOR = 1e-9

# Generic, invented topics for filler passages — deliberately bland and
# unrelated to any real retrieval corpus.
_FILLER_TOPICS = [
    "seasonal gardening schedules",
    "the history of postal routing",
    "basic bicycle maintenance",
    "regional weather patterns",
    "the rules of chess openings",
    "public library cataloguing systems",
    "the physics of soap bubbles",
    "traditional bread baking",
    "amateur astronomy equipment",
    "the geography of river deltas",
    "beekeeping for hobbyists",
    "the mechanics of pulley systems",
    "coastal erosion measurement",
    "the etiquette of board games",
    "urban tree canopy planning",
    "the acoustics of concert halls",
    "vintage typewriter repair",
    "the migration habits of songbirds",
    "compost bin temperature control",
    "the design of covered bridges",
]


# --------------------------------------------------------------------------
# percentile maths
# --------------------------------------------------------------------------

def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (numpy's default 'linear' method)."""
    if not values:
        raise ValueError("percentile() requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    k = (len(ordered) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(ordered[int(k)])
    d0 = ordered[f] * (c - k)
    d1 = ordered[c] * (k - f)
    return float(d0 + d1)


def summarize_latencies(samples: list[float]) -> dict[str, float]:
    return {
        "p50": percentile(samples, 50),
        "p95": percentile(samples, 95),
        "max": percentile(samples, 100),
        "n": len(samples),
    }


# --------------------------------------------------------------------------
# filler passage generation — generic, invented, never the requester's corpus
# --------------------------------------------------------------------------

def generate_filler_query() -> str:
    return "What are some practical tips for getting started with a new hobby?"


def generate_filler_passages(n: int) -> list[str]:
    passages = []
    for i in range(n):
        topic = _FILLER_TOPICS[i % len(_FILLER_TOPICS)]
        variant = i // len(_FILLER_TOPICS)
        suffix = f" (note {variant})" if variant else ""
        passages.append(
            f"This is a general-purpose passage about {topic}, written as "
            f"filler candidate text for a retrieval benchmark{suffix}."
        )
    return passages


# --------------------------------------------------------------------------
# rerank request/response shape — POST /v3/rerank
# --------------------------------------------------------------------------

def build_rerank_request(model: str, query: str, documents: list[str]) -> dict[str, Any]:
    return {"model": model, "query": query, "documents": documents}


def parse_rerank_scores(response: dict[str, Any]) -> list[float]:
    """Return relevance scores ordered by the ORIGINAL candidate index —
    OVMS returns `results` re-ordered by relevance, not input order."""
    results = sorted(response.get("results", []), key=lambda r: r["index"])
    return [r["relevance_score"] for r in results]


# --------------------------------------------------------------------------
# embeddings request/response shape — POST /v3/embeddings (OpenAI-shaped)
# --------------------------------------------------------------------------

def build_embeddings_request(model: str, inputs: list[str]) -> dict[str, Any]:
    return {"model": model, "input": inputs}


def parse_embedding_vectors(response: dict[str, Any]) -> list[list[float]]:
    return [item["embedding"] for item in response.get("data", [])]


def embedding_dimension(vectors: list[list[float]]) -> int:
    if not vectors:
        raise ValueError("embedding_dimension() requires at least one vector")
    dims = {len(v) for v in vectors}
    if len(dims) != 1:
        raise ValueError(f"inconsistent embedding dimensions across vectors: {sorted(dims)}")
    return next(iter(dims))


# --------------------------------------------------------------------------
# score-degeneracy detection
# --------------------------------------------------------------------------

def scores_are_degenerate(scores: list[float]) -> bool:
    """True when scores show the measured signature of a reranker served as
    the wrong model class: all near-zero AND barely separated from each
    other. Either condition alone is not evidence — a legitimately tiny but
    well-separated score set is not degenerate."""
    if len(scores) < 2:
        return False
    hi = max(scores)
    lo = min(scores)
    if hi <= 0:
        return False
    tiny_magnitude = hi < DEGENERACY_MAGNITUDE_CEILING
    poor_separation = (hi - lo) < DEGENERACY_SEPARATION_FLOOR
    return tiny_magnitude and poor_separation


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark the ovms-retrieval rerank and embeddings servables. "
            "Run from inside the cluster."
        )
    )
    parser.add_argument(
        "--arm",
        choices=["gpu", "cpu"],
        required=True,
        default=None,
        help=(
            "REQUIRED, no default: which device produced this measurement. "
            "Recorded verbatim in the JSON output so a result can never be "
            "ambiguous about its source."
        ),
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OVMS REST base URL")
    parser.add_argument("--embeddings-model", default=DEFAULT_EMBEDDINGS_MODEL)
    parser.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    parser.add_argument("--rerank-candidates", type=int, default=RERANK_CANDIDATES)
    parser.add_argument("--rerank-iterations", type=int, default=RERANK_ITERATIONS)
    parser.add_argument("--rerank-warmup", type=int, default=RERANK_WARMUP)
    parser.add_argument("--embedding-batch-size", type=int, default=EMBEDDING_BATCH_SIZE)
    parser.add_argument(
        "--output",
        default=None,
        help="Write JSON result here instead of stdout.",
    )
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)


# --------------------------------------------------------------------------
# result payload assembly
# --------------------------------------------------------------------------

def build_result_payload(
    *,
    arm: str,
    rerank_model: str,
    embeddings_model: str,
    rerank_candidates: int,
    rerank_iterations: int,
    rerank_summary: dict[str, float],
    embedding_dimension: int,
    embedding_single_summary: dict[str, float],
    embedding_batch_summary: dict[str, float],
    embedding_batch_size: int,
    degenerate: bool,
) -> dict[str, Any]:
    return {
        "arm": arm,
        "rerank": {
            "model": rerank_model,
            "candidates": rerank_candidates,
            "iterations": rerank_iterations,
            "latency_ms": rerank_summary,
            "degenerate_scores": degenerate,
        },
        "embeddings": {
            "model": embeddings_model,
            "dimension": embedding_dimension,
            "batch_size": embedding_batch_size,
            "single_latency_ms": embedding_single_summary,
            "batch_latency_ms": embedding_batch_summary,
        },
    }


# --------------------------------------------------------------------------
# network I/O — the only part not covered by offline tests
# --------------------------------------------------------------------------

def _post_json(url: str, payload: dict[str, Any], timeout: float = REQUEST_TIMEOUT_S) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _time_call(fn) -> tuple[float, Any]:
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return elapsed_ms, result


def _timed_iterations(fn, n: int) -> tuple[list[float], list[Any]]:
    """Run `fn()` n times, returning (per-call latencies_ms, per-call results)."""
    latencies: list[float] = []
    results: list[Any] = []
    for _ in range(n):
        elapsed_ms, result = _time_call(fn)
        latencies.append(elapsed_ms)
        results.append(result)
    return latencies, results


def _run_rerank_benchmark(args: argparse.Namespace) -> tuple[dict[str, float], bool]:
    query = generate_filler_query()
    documents = generate_filler_passages(args.rerank_candidates)
    body = build_rerank_request(args.rerank_model, query, documents)
    url = f"{args.base_url}/v3/rerank"

    for _ in range(args.rerank_warmup):
        _post_json(url, body)

    latencies, responses = _timed_iterations(lambda: _post_json(url, body), args.rerank_iterations)
    last_scores = parse_rerank_scores(responses[-1]) if responses else []

    return summarize_latencies(latencies), scores_are_degenerate(last_scores)


def _run_embeddings_benchmark(args: argparse.Namespace) -> tuple[int, dict[str, float], dict[str, float]]:
    url = f"{args.base_url}/v3/embeddings"
    single_body = build_embeddings_request(args.embeddings_model, [generate_filler_query()])
    batch_inputs = generate_filler_passages(args.embedding_batch_size)
    batch_body = build_embeddings_request(args.embeddings_model, batch_inputs)

    # Warm up once so the first-call cold path doesn't skew the timed loop.
    warm_response = _post_json(url, single_body)
    dimension = embedding_dimension(parse_embedding_vectors(warm_response))

    single_latencies, _ = _timed_iterations(lambda: _post_json(url, single_body), args.rerank_iterations)
    batch_latencies, _ = _timed_iterations(lambda: _post_json(url, batch_body), args.rerank_iterations)

    return dimension, summarize_latencies(single_latencies), summarize_latencies(batch_latencies)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        rerank_summary, degenerate = _run_rerank_benchmark(args)
        dimension, embed_single, embed_batch = _run_embeddings_benchmark(args)
    except (urllib.error.URLError, OSError) as exc:
        print(f"ovms-retrieval-bench: request to {args.base_url} failed: {exc}", file=sys.stderr)
        return 1

    payload = build_result_payload(
        arm=args.arm,
        rerank_model=args.rerank_model,
        embeddings_model=args.embeddings_model,
        rerank_candidates=args.rerank_candidates,
        rerank_iterations=args.rerank_iterations,
        rerank_summary=rerank_summary,
        embedding_dimension=dimension,
        embedding_single_summary=embed_single,
        embedding_batch_summary=embed_batch,
        embedding_batch_size=args.embedding_batch_size,
        degenerate=degenerate,
    )

    text = json.dumps(payload, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(text + "\n")
    else:
        print(text)

    if degenerate:
        print(
            "ovms-retrieval-bench: DEGENERATE SCORES DETECTED — relevance "
            "scores are near-zero with poor separation, the signature of a "
            "reranker served as the wrong model class. See /v1/config.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
