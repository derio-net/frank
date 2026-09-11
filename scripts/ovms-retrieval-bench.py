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
  1. Rerank latency — one query against 20 candidate passages, N timed
     iterations after a warm-up, reporting p50 / p95 / max.
  2. Embedding dimensionality — read from the response, never hardcoded.
  3. Embedding latency and throughput (items/sec) — single request and
     batch-32, each warmed at its OWN shape before being timed.

Every run rotates the query and the candidate set across iterations. Sending
one identical body N times measures a best case with fully warm caches and
zero tokenizer variance; rotation costs nothing and is far more honest for a
number that gets quoted. Text length is held roughly constant so rotation
varies content without varying the amount of work per call.

## What `--arm` is, and what it is not

`--arm gpu|cpu` is REQUIRED and recorded verbatim, but it is an operator
ASSERTION, not evidence. The phase-5 workflow runs one arm against the
default URL and the other against a separately-stood-up pod, so a forgotten
flag would otherwise produce a well-formed record attributing one device's
latency to the other. To make that falsifiable, every record also carries,
unconditionally:

  * `base_url` — which endpoint was actually measured;
  * `timestamp` — UTC, ISO-8601;
  * `server_config` — a snapshot of `GET {base_url}/v1/config`, taken once at
    startup: per-servable name/version/state plus the raw response verbatim.

If that snapshot reports a target device, it is cross-checked against `--arm`
and a disagreement is FATAL (exit 4, message on stderr) before any timing
runs. **OVMS's `/v1/config` reports servable state, not target device** — on
that server the cross-check therefore records `not-reported` and the device
claim rests on which model repository was seeded (`target_device` is baked
into each servable's `graph.pbtxt` at export time). The harness records what
it can observe and labels the rest as unverified; it does not claim a
guarantee it cannot make.

## What the reported latencies include

`_time_call` wraps a full client request. Each sample therefore includes a
fresh TCP connection (no keep-alive), the HTTP round-trip, server compute,
and client-side `json.loads` of the response body — several hundred KB for
batch-32 by 1024-dim vectors, parsed in this process and attributed to the
server. These are end-to-end in-cluster client latencies, not isolated
server-side inference times. The same note is written into the payload as
`timing_includes` so a quoted figure carries its own methodology.

The candidate/query text below is GENERIC invented filler — never an external
client's corpus, queries, or document titles. See
agents/rules/third-party-privacy.md and the spec's "Scope discipline".

This module is structured so every piece of logic (percentile maths, request
construction, response parsing, config-snapshot assembly, the arm
cross-check, degeneracy detection, throughput maths, argument parsing, and
payload assembly) is a pure function with no I/O, importable and testable
without a network or a cluster. Only `_post_json`, `fetch_server_config` and
the functions that call them talk to a socket.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

DEFAULT_BASE_URL = "http://ovms-retrieval.retrieval.svc.cluster.local:8000"
DEFAULT_EMBEDDINGS_MODEL = "bge-m3"
DEFAULT_RERANK_MODEL = "bge-reranker-v2-m3"

RERANK_CANDIDATES = 20
RERANK_ITERATIONS = 30
RERANK_WARMUP = 3
EMBEDDING_BATCH_SIZE = 32
EMBEDDING_WARMUP = 3
REQUEST_TIMEOUT_S = 30

EXIT_REQUEST_FAILED = 1
EXIT_DEGENERATE_SCORES = 2
EXIT_ARM_CONTRADICTED = 4

# Signature (a): a reranker served as the wrong model class collapses every
# relevance score into the near-zero floor (measured at ~1e-6 and below). The
# benchmark query deliberately MATCHES one candidate topic, so a healthy
# reranker must produce at least one clearly-high score — which is what makes
# a tiny maximum evidence of failure rather than evidence of an irrelevant
# candidate set.
DEGENERACY_MAGNITUDE_CEILING = 1e-6

# Signature (b): no separation between candidates at ANY magnitude — the model
# returns essentially the same score for everything, so it is not ranking.
# Relative and scale-free on purpose: an absolute floor is meaningless when
# the whole score set lives at 1e-9.
DEGENERACY_RELATIVE_SEPARATION_FLOOR = 0.01

TIMING_INCLUDES_NOTE = (
    "Wall-clock around a full client request: a fresh TCP connection per call "
    "(no keep-alive), the HTTP round-trip, server compute, and client-side "
    "json.loads of the response body (several hundred KB for a batch of "
    "high-dimensional vectors, parsed in-process and attributed here to the "
    "server). End-to-end in-cluster client latency, not isolated server-side "
    "inference time."
)

# A failed call's body is the server's own account of why it refused. Capped,
# because an unexpected failure can return an arbitrarily large page and the
# record is meant to be read.
SWEEP_BODY_CAPTURE_CHARS = 2000

# `_post_json` returns only on 2xx and discards the response code, so a
# successful sweep call is recorded as 200. Failures carry the server's actual
# status. Stated in the record rather than left for a reader to discover.
SWEEP_STATUS_NOTE = (
    "status 200 on success means '2xx, code not retained' — _post_json "
    "returns a parsed body, not a response object. A non-2xx status is the "
    "server's own, read from the raised HTTPError; null means no response "
    "reached the client at all (closed or refused socket)."
)

CROSS_CHECK_CONFIRMED = "confirmed"
CROSS_CHECK_CONTRADICTED = "contradicted"
CROSS_CHECK_NOT_REPORTED = "not-reported"
CROSS_CHECK_UNAVAILABLE = "unavailable"

_DEVICE_KEYS = {"target_device", "device"}
_KNOWN_DEVICE_TOKENS = ("gpu", "cpu", "npu")

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

# The word pool `--rerank-words` pads from: the words the filler passages are
# already built out of, nothing else. Padding a 200-word document has to come
# from somewhere, and "somewhere" must not be newly-written prose that could
# read as anyone's corpus — so the pool is derived from the text above rather
# than authored. Order is deterministic (`dict.fromkeys`) so a given
# (passage index, word count) always produces the same bytes.
_FILLER_SENTENCE_WORDS = (
    "this is a general-purpose passage about written as filler candidate "
    "text for a retrieval benchmark"
).split()

_FILLER_VOCABULARY = tuple(
    dict.fromkeys(
        _FILLER_SENTENCE_WORDS
        + [word for topic in _FILLER_TOPICS for word in topic.split()]
    )
)


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


def throughput_items_per_s(latency_ms: float, items: int) -> float:
    """Items processed per second implied by a per-request latency."""
    if latency_ms <= 0:
        raise ValueError("throughput_items_per_s() requires a positive latency")
    if items <= 0:
        raise ValueError("throughput_items_per_s() requires a positive item count")
    return items * 1000.0 / latency_ms


# --------------------------------------------------------------------------
# filler passage generation — generic, invented, never an external corpus
# --------------------------------------------------------------------------

def generate_filler_query(index: int = 0) -> str:
    """Rotating query. Each one names a topic that IS in the candidate set, so
    a healthy reranker has something to score highly — see the degeneracy
    note above."""
    topic = _FILLER_TOPICS[index % len(_FILLER_TOPICS)]
    return f"What should someone getting started know about {topic}?"


def generate_filler_passages(n: int, offset: int = 0, words: int | None = None) -> list[str]:
    """`offset` rotates which topic lands at which candidate position, so
    successive iterations do not send a byte-identical body.

    `words` pads each passage to EXACTLY that many words, from this module's
    own filler vocabulary. `None` (the default) is the unpadded ~20-word
    passage this harness has always sent, so the parent spec's published
    numbers are unaffected.

    Why the knob exists: the rerank calculator builds one tensor of shape
    `{batch, longest_document_tokens}`, so peak memory is B x T. The OOM this
    is used to measure reproduced at 200-word documents; a sweep at the stock
    length sends roughly a tenth of the tokens per document and can fail to
    reproduce it at ANY batch size while looking like a clean run.

    Padding is drawn from `_FILLER_VOCABULARY` — words already present in the
    text above — deliberately: this must stay obviously-invented filler and
    never drift into plausible-sounding corpus prose. See
    agents/rules/third-party-privacy.md."""
    passages = []
    for i in range(n):
        index = i + offset
        topic = _FILLER_TOPICS[index % len(_FILLER_TOPICS)]
        variant = index // len(_FILLER_TOPICS)
        suffix = f" (note {variant})" if variant else ""
        passage = (
            f"This is a general-purpose passage about {topic}, written as "
            f"filler candidate text for a retrieval benchmark{suffix}."
        )
        if words is not None:
            passage = _pad_to_word_count(passage, words, seed=index)
        passages.append(passage)
    return passages


def _pad_to_word_count(text: str, words: int, seed: int) -> str:
    """Extend `text` to exactly `words` words with vocabulary it already uses.

    Refuses to shorten. A request for fewer words than the base sentence
    already carries cannot be honoured without either truncating the topic
    anchor the degeneracy check depends on, or recording a word count that was
    never sent — so it raises instead of silently doing one of those."""
    if words < 1:
        raise ValueError(f"words must be positive, got {words}")
    current = text.split()
    if words < len(current):
        raise ValueError(
            f"cannot pad to {words} words: the base filler passage is already "
            f"{len(current)} words. Use a larger --rerank-words, or the "
            "default (no padding)."
        )
    padding = [
        _FILLER_VOCABULARY[(seed + i) % len(_FILLER_VOCABULARY)]
        for i in range(words - len(current))
    ]
    return " ".join(current + padding)


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
# server config snapshot — what can contradict `--arm` after the fact
# --------------------------------------------------------------------------

def summarize_servables(raw: Any) -> list[dict[str, Any]]:
    """Per-servable name / version / state from a `GET /v1/config` response.

    Tolerant by design: an unexpected shape yields fewer rows, never an
    exception — the raw response is recorded alongside this summary anyway."""
    if not isinstance(raw, dict):
        return []
    servables: list[dict[str, Any]] = []
    for name, entry in sorted(raw.items()):
        if not isinstance(entry, dict):
            continue
        for status in entry.get("model_version_status", []) or []:
            if not isinstance(status, dict):
                continue
            servables.append(
                {
                    "name": name,
                    "version": status.get("version"),
                    "state": status.get("state"),
                }
            )
    return servables


def extract_reported_device(raw: Any) -> str | None:
    """First device string the server reports anywhere in its config, or None.

    OVMS's `/v1/config` does NOT expose the target device, so None is the
    expected result there — the caller must treat it as "cannot cross-check",
    not as agreement."""
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(key, str) and key.lower() in _DEVICE_KEYS:
                if isinstance(value, str) and value.strip():
                    return value
            found = extract_reported_device(value)
            if found is not None:
                return found
    elif isinstance(raw, list):
        for item in raw:
            found = extract_reported_device(item)
            if found is not None:
                return found
    return None


def device_cross_check(arm: str, reported_device: str | None) -> str:
    """Compare the operator's `--arm` against the server's own report.

    `not-reported` covers both "no device field" and a device string this
    harness cannot read (`AUTO`, a bare plugin name) — an inconclusive check
    must never be recorded as a confirmation."""
    if not reported_device or not reported_device.strip():
        return CROSS_CHECK_NOT_REPORTED
    normalized = reported_device.strip().lower()
    if arm in normalized:
        return CROSS_CHECK_CONFIRMED
    if any(token in normalized for token in _KNOWN_DEVICE_TOKENS):
        return CROSS_CHECK_CONTRADICTED
    return CROSS_CHECK_NOT_REPORTED


def build_server_config_snapshot(
    *,
    base_url: str,
    arm: str,
    raw: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    endpoint = f"{base_url}/v1/config"
    if error is not None:
        return {
            "endpoint": endpoint,
            "available": False,
            "error": error,
            "servables": [],
            "reported_device": None,
            "arm_cross_check": CROSS_CHECK_UNAVAILABLE,
            "raw": None,
        }
    device = extract_reported_device(raw)
    return {
        "endpoint": endpoint,
        "available": True,
        "error": None,
        "servables": summarize_servables(raw),
        "reported_device": device,
        "arm_cross_check": device_cross_check(arm, device),
        "raw": raw,
    }


# --------------------------------------------------------------------------
# score-degeneracy detection
# --------------------------------------------------------------------------

def scores_are_degenerate(scores: list[float]) -> bool:
    """True when the rerank output shows either signature of an unusable
    reranker:

    (a) **tiny magnitude** — the whole score set sits below
        `DEGENERACY_MAGNITUDE_CEILING`, the measured signature of a reranker
        served as the wrong model class. This is decisive on its own here
        *because* the benchmark query matches a candidate topic: a working
        cross-encoder must score that candidate highly, so a maximum below
        1e-6 means nothing scored as relevant to a directly-relevant passage.

    (b) **no separation** — the spread is under
        `DEGENERACY_RELATIVE_SEPARATION_FLOOR` of the maximum, at any
        magnitude. A model that returns the same score for every candidate is
        not ranking.

    Scoped to score sets with a positive maximum: all-zero or all-negative
    (raw-logit) output is a different failure mode this check does not claim
    to cover.
    """
    if len(scores) < 2:
        return False
    hi = max(scores)
    lo = min(scores)
    if hi <= 0:
        return False
    tiny_magnitude = hi < DEGENERACY_MAGNITUDE_CEILING
    poor_separation = ((hi - lo) / hi) < DEGENERACY_RELATIVE_SEPARATION_FLOOR
    return tiny_magnitude or poor_separation


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_sweep_sizes(raw: str) -> list[int]:
    """`"10,20,30"` -> `[10, 20, 30]`, sorted ascending and de-duplicated.

    Ascending is not cosmetic. A size large enough to kill the server leaves
    it refusing connections for about ten seconds, so any smaller size
    measured after it would record a restart rather than a batch cost. The
    sweep therefore always walks small to large, whatever order the operator
    typed."""
    sizes: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            raise ValueError(f"empty batch size in --rerank-sweep {raw!r}")
        try:
            size = int(token)
        except ValueError:
            raise ValueError(f"batch size {token!r} is not an integer") from None
        if size < 1:
            raise ValueError(f"batch size {size} is not positive")
        sizes.append(size)
    if not sizes:
        raise ValueError("--rerank-sweep needs at least one batch size")
    return sorted(set(sizes))


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
            "REQUIRED, no default: which device the operator believes produced "
            "this measurement. Recorded verbatim AND cross-checked against the "
            "server's own reported device where one is exposed; a disagreement "
            "is fatal."
        ),
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OVMS REST base URL")
    parser.add_argument("--embeddings-model", default=DEFAULT_EMBEDDINGS_MODEL)
    parser.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    parser.add_argument("--rerank-candidates", type=int, default=RERANK_CANDIDATES)
    parser.add_argument("--rerank-iterations", type=int, default=RERANK_ITERATIONS)
    parser.add_argument("--rerank-warmup", type=int, default=RERANK_WARMUP)
    parser.add_argument(
        "--rerank-sweep",
        type=parse_sweep_sizes,
        default=None,
        help=(
            "SWEEP MODE. Comma-separated batch sizes, e.g. "
            "'10,20,30,40,50,51'. Replaces the timed rerank+embeddings "
            "benchmark with one rerank call per size, ascending, recording "
            "latency, HTTP status and the response body on failure. A refusal "
            "or a killed server is RECORDED and the sweep continues — those "
            "are the results it exists to capture."
        ),
    )
    parser.add_argument(
        "--rerank-words",
        type=int,
        default=None,
        help=(
            "Pad every candidate passage to this many words. Default: no "
            "padding (the stock ~20-word passage). Peak server memory is "
            "batch x LONGEST-DOCUMENT tokens, so a sweep at the stock length "
            "measures roughly a tenth of the tokens per document and may not "
            "reproduce an OOM at any batch size."
        ),
    )
    parser.add_argument(
        "--embedding-iterations",
        type=int,
        default=RERANK_ITERATIONS,
        help=(
            "Timed embedding iterations per shape. Independent of "
            "--rerank-iterations, which used to drive this silently."
        ),
    )
    parser.add_argument(
        "--embedding-warmup",
        type=int,
        default=EMBEDDING_WARMUP,
        help=(
            "Warm-up calls per embedding SHAPE. Both the single and the "
            "batch body are warmed: changing the batch dimension makes the "
            "OpenVINO GPU plugin recompile."
        ),
    )
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

def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_result_payload(
    *,
    arm: str,
    base_url: str,
    timestamp: str,
    server_config: dict[str, Any],
    rerank_model: str,
    embeddings_model: str,
    rerank_candidates: int,
    rerank_iterations: int,
    rerank_summary: dict[str, float],
    embedding_dimension: int,
    embedding_iterations: int,
    embedding_single_summary: dict[str, float],
    embedding_batch_summary: dict[str, float],
    embedding_batch_size: int,
    degenerate: bool,
) -> dict[str, Any]:
    """`arm`, `base_url`, `timestamp` and `server_config` are all keyword-only
    with no defaults: a record cannot be assembled without the evidence that
    would let a reader contradict its `arm` label."""
    return {
        "arm": arm,
        "base_url": base_url,
        "timestamp": timestamp,
        "server_config": server_config,
        "timing_includes": TIMING_INCLUDES_NOTE,
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
            "iterations": embedding_iterations,
            "batch_size": embedding_batch_size,
            "single_latency_ms": embedding_single_summary,
            "batch_latency_ms": embedding_batch_summary,
            "throughput_items_per_s": {
                "single": throughput_items_per_s(embedding_single_summary["p50"], 1),
                "batch": throughput_items_per_s(
                    embedding_batch_summary["p50"], embedding_batch_size
                ),
                "basis": "derived from p50 latency",
            },
        },
    }


def build_sweep_payload(
    *,
    arm: str,
    base_url: str,
    timestamp: str,
    server_config: dict[str, Any],
    sweep: dict[str, Any],
) -> dict[str, Any]:
    """The sweep's own record section, under the same provenance every other
    record here carries.

    Keyword-only with no defaults, for the same reason `build_result_payload`
    is: the curve this produces sets the guard's two numbers and will be
    quoted in a spec. A curve without the endpoint and the arm it came from is
    a number from nowhere — and the two arms run against different URLs, so a
    forgotten flag would otherwise attribute one device's cliff to the
    other."""
    return {
        "arm": arm,
        "base_url": base_url,
        "timestamp": timestamp,
        "server_config": server_config,
        "timing_includes": TIMING_INCLUDES_NOTE,
        "sweep": sweep,
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


def fetch_server_config(base_url: str, timeout: float = REQUEST_TIMEOUT_S) -> Any:
    """GET {base_url}/v1/config — the servable-state diagnostic, fetched once
    at startup so the record carries observed server state, not just a flag."""
    request = urllib.request.Request(f"{base_url}/v1/config", method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _time_call(fn) -> tuple[float, Any]:
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return elapsed_ms, result


def _timed_iterations(fn, n: int) -> tuple[list[float], list[Any]]:
    """Run `fn(i)` for i in range(n), returning (latencies_ms, results).

    `fn` takes the iteration index so callers can rotate the request body —
    see the rotation note in the module docstring."""
    latencies: list[float] = []
    results: list[Any] = []
    for i in range(n):
        elapsed_ms, result = _time_call(lambda: fn(i))
        latencies.append(elapsed_ms)
        results.append(result)
    return latencies, results


def _run_rerank_benchmark(args: argparse.Namespace) -> tuple[dict[str, float], bool]:
    url = f"{args.base_url}/v3/rerank"

    def body_for(index: int) -> dict[str, Any]:
        return build_rerank_request(
            args.rerank_model,
            generate_filler_query(index),
            generate_filler_passages(
                args.rerank_candidates, offset=index, words=args.rerank_words
            ),
        )

    for i in range(args.rerank_warmup):
        _post_json(url, body_for(i))

    latencies, responses = _timed_iterations(
        lambda i: _post_json(url, body_for(i)), args.rerank_iterations
    )
    last_scores = parse_rerank_scores(responses[-1]) if responses else []

    return summarize_latencies(latencies), scores_are_degenerate(last_scores)


def _run_rerank_sweep(args: argparse.Namespace) -> dict[str, Any]:
    """Walk `--rerank-sweep` ascending, one rerank call per size, recording
    latency / status / body per size and NEVER propagating a failure.

    Both outcomes worth measuring arrive as exceptions, because `_post_json`
    wraps `urlopen`: a guard refusing an oversized batch is an `HTTPError`,
    and a server killed by one is a `RemoteDisconnected` followed by
    `URLError` for as long as the pod takes to restart. A sweep that let those
    out would abort at exactly the size it was run to measure, and report a
    tidy curve of the sizes that happened to survive.

    Warm-up runs at the SMALLEST size only. Warming at a size about to be
    proven fatal spends a restart, and the next size is then measured against
    a cold server — recording a plugin recompile as batch cost."""
    url = f"{args.base_url}/v3/rerank"
    sizes = args.rerank_sweep
    smallest = sizes[0]

    def attempt(documents: int, index: int) -> dict[str, Any]:
        passages = generate_filler_passages(
            documents, offset=index, words=args.rerank_words
        )
        body = build_rerank_request(
            args.rerank_model, generate_filler_query(index), passages
        )
        # Measured from the passages actually built, not echoed back from the
        # flag: a padding bug then shows in the record instead of being
        # papered over by it.
        words_sent = max(len(p.split()) for p in passages)

        start = time.perf_counter()
        status: int | None = None
        error: str | None = None
        response_body: str | None = None
        results_returned: int | None = None
        ok = False
        try:
            response = _post_json(url, body)
        except urllib.error.HTTPError as exc:
            # Subclass of URLError — must be caught first or a refusal loses
            # its status code and its message.
            status = exc.code
            error = f"HTTPError: {exc}"
            response_body = _read_error_body(exc)
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            # No status at all: the socket closed, or never opened. Recording
            # 0 or 500 here would invent a response the server never sent.
            error = f"{type(exc).__name__}: {exc}"
        else:
            ok = True
            status = 200
            results_returned = len(response.get("results", []))
        latency_ms = (time.perf_counter() - start) * 1000.0

        return {
            "documents": documents,
            "words_per_document": words_sent,
            "status": status,
            "latency_ms": latency_ms,
            "ok": ok,
            "error": error,
            "body": response_body,
            "results_returned": results_returned,
        }

    warmup_attempts = [attempt(smallest, i) for i in range(max(args.rerank_warmup, 0))]
    results = [attempt(size, i) for i, size in enumerate(sizes)]

    return {
        "model": args.rerank_model,
        "sizes": list(sizes),
        "words_per_document_requested": args.rerank_words,
        "warmup": {
            "documents": smallest,
            "calls": len(warmup_attempts),
            "attempts": warmup_attempts,
        },
        "status_note": SWEEP_STATUS_NOTE,
        "results": results,
    }


def _read_error_body(exc: urllib.error.HTTPError) -> str | None:
    """The server's own words about why it refused — the thing Test Plan row 6
    records rather than asserts. Best-effort: a body that cannot be read must
    not turn a recorded refusal into a crashed sweep."""
    try:
        raw = exc.read()
    except Exception:  # pragma: no cover - defensive; fp may be absent/closed
        return None
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    if len(text) > SWEEP_BODY_CAPTURE_CHARS:
        return text[:SWEEP_BODY_CAPTURE_CHARS] + "... [truncated]"
    return text


def _run_embeddings_benchmark(args: argparse.Namespace) -> tuple[int, dict[str, float], dict[str, float]]:
    url = f"{args.base_url}/v3/embeddings"

    def single_body(index: int) -> dict[str, Any]:
        return build_embeddings_request(
            args.embeddings_model, [generate_filler_query(index)]
        )

    def batch_body(index: int) -> dict[str, Any]:
        return build_embeddings_request(
            args.embeddings_model,
            generate_filler_passages(args.embedding_batch_size, offset=index),
        )

    # Warm EACH SHAPE before timing it. The batch dimension change makes the
    # OpenVINO GPU plugin recompile for the new shape — seconds on a cold
    # iGPU — and an unwarmed batch loop puts that recompile straight into
    # `batch_latency_ms.max`, the figure a reader quotes as worst case.
    warm_response: dict[str, Any] | None = None
    for i in range(max(args.embedding_warmup, 1)):
        warm_response = _post_json(url, single_body(i))
    dimension = embedding_dimension(parse_embedding_vectors(warm_response))

    single_latencies, _ = _timed_iterations(
        lambda i: _post_json(url, single_body(i)), args.embedding_iterations
    )

    for i in range(max(args.embedding_warmup, 1)):
        _post_json(url, batch_body(i))

    batch_latencies, _ = _timed_iterations(
        lambda i: _post_json(url, batch_body(i)), args.embedding_iterations
    )

    return dimension, summarize_latencies(single_latencies), summarize_latencies(batch_latencies)


def _emit(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, indent=2)
    if output:
        with open(output, "w") as f:
            f.write(text + "\n")
    else:
        print(text)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    # Take the server's own account of itself BEFORE measuring anything, so a
    # contradicted arm costs nothing and produces no record at all.
    try:
        raw_config = fetch_server_config(args.base_url)
        server_config = build_server_config_snapshot(
            base_url=args.base_url, arm=args.arm, raw=raw_config
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        server_config = build_server_config_snapshot(
            base_url=args.base_url, arm=args.arm, error=f"{type(exc).__name__}: {exc}"
        )
        print(
            "ovms-retrieval-bench: WARNING — could not read "
            f"{server_config['endpoint']} ({exc}); the recorded arm "
            f"'{args.arm}' is UNVERIFIED.",
            file=sys.stderr,
        )

    if server_config["arm_cross_check"] == CROSS_CHECK_CONTRADICTED:
        print(
            "ovms-retrieval-bench: ARM MISMATCH — --arm "
            f"{args.arm} but {server_config['endpoint']} reports device "
            f"'{server_config['reported_device']}'. Refusing to record a "
            "measurement whose device attribution is wrong. Check --arm and "
            "--base-url (the two arms run against different endpoints).",
            file=sys.stderr,
        )
        return EXIT_ARM_CONTRADICTED

    if args.rerank_sweep:
        # Sweep mode REPLACES the timed benchmark rather than preceding it.
        # The sweep exists to find the size at which the server dies; running
        # a 30-iteration embeddings loop afterwards would measure a restarting
        # pod and report it as embedding latency.
        sweep_payload = build_sweep_payload(
            arm=args.arm,
            base_url=args.base_url,
            timestamp=utc_timestamp(),
            server_config=server_config,
            sweep=_run_rerank_sweep(args),
        )
        _emit(sweep_payload, args.output)
        return 0

    try:
        rerank_summary, degenerate = _run_rerank_benchmark(args)
        dimension, embed_single, embed_batch = _run_embeddings_benchmark(args)
    except (urllib.error.URLError, OSError) as exc:
        print(f"ovms-retrieval-bench: request to {args.base_url} failed: {exc}", file=sys.stderr)
        return EXIT_REQUEST_FAILED

    payload = build_result_payload(
        arm=args.arm,
        base_url=args.base_url,
        timestamp=utc_timestamp(),
        server_config=server_config,
        rerank_model=args.rerank_model,
        embeddings_model=args.embeddings_model,
        rerank_candidates=args.rerank_candidates,
        rerank_iterations=args.rerank_iterations,
        rerank_summary=rerank_summary,
        embedding_dimension=dimension,
        embedding_iterations=args.embedding_iterations,
        embedding_single_summary=embed_single,
        embedding_batch_summary=embed_batch,
        embedding_batch_size=args.embedding_batch_size,
        degenerate=degenerate,
    )

    _emit(payload, args.output)

    if degenerate:
        print(
            "ovms-retrieval-bench: DEGENERATE SCORES DETECTED — relevance "
            "scores are either all below the near-zero floor or show no "
            "separation between candidates, the signature of a reranker "
            "served as the wrong model class. See /v1/config.",
            file=sys.stderr,
        )
        return EXIT_DEGENERATE_SCORES

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
