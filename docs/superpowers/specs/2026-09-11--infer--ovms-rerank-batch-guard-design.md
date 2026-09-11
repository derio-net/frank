# Bounding the Rerank Batch — Turning an OOM-Kill into a Refusal

**Date:** 2026-09-11
**Layer:** `infer` (11) — Local Inference
**Status:** Designed — not deployed.
**Fixes:** [#793](https://github.com/derio-net/frank/issues/793)
**Extends:** `docs/superpowers/implemented/specs/2026-08-02--infer--igpu-embedding-rerank-design.md`

## Scope discipline

Same rule as the parent spec, and for the same reason: the consumer of this
endpoint lives in a **private downstream repo**, and this spec, its plan, the
PR body and any runbook text are all public.

- Do **not** name the consumer repo, its product, or its corpus.
- Do **not** reproduce its queries, document titles or corpus statistics.
- **Do** keep the generic, load-bearing fact: the client sends **25–50
  candidate passages per rerank call by default, and fails open silently when
  the call dies** — which is why a server that dies on 50 looks like a
  reranker that works and contributes nothing.

Every measurement in this spec uses the benchmark harness's own invented
filler text (`scripts/ovms-retrieval-bench.py`), never a real corpus.

## What is wrong

`POST /v3/rerank` against `ovms-retrieval` takes the whole server down on a
batch the downstream client sends routinely. Reproduced in-cluster with
synthetic documents of random words, one request each, in order:

| documents × words | body | result |
|---|---|---|
| 3 × 50 | 1 KiB | 200, 0.32 s |
| 20 × 200 | 27 KiB | 200, 1.48 s |
| 30 × 200 | 41 KiB | 200, **6.72 s** |
| 50 × 200 | 68 KiB | connection closed without response after 0.13 s |
| anything, next ~10 s | | connection refused |
| after restart, 3 × 50 | | 200 |

Cluster metrics agree on the mechanism: `container_memory_working_set_bytes`
for the `ovms` container idles at 2.2–3.0 GiB, reaches **6022 MiB — the limit
— under rerank load**, and `kube_pod_container_status_restarts_total`
increments once per failed call (1 → 9 over a week of light use, including one
restart under a batch embeddings load). Node conditions and apiserver latency
on mini-1 never moved, so this is a cgroup kill, not node pressure.

The blast radius is the whole server. `ovms-retrieval` hosts **both** the
embeddings and the rerank servable in one process behind one DRA device claim
(that consolidation is the parent spec's central decision and is not in
question here). So one oversized rerank call evicts the embeddings service
too, for every caller, for about ten seconds.

## Root cause — established from upstream source, not inferred

All references are `openvinotoolkit/model_server` at **`v2026.2.1`**, the ref
this deployment pins for both the runtime image and the export toolchain.

### The batch is one tensor, and its size is B × T

`src/rerank/rerank_calculator_ov.cc` builds a **single** inference input:

```cpp
size_t total_tokens_count_per_batch =
    tokens_count_of_longest_document + NUMBER_OF_SPECIAL_TOKENS + query_tokens.size();
size_t batch_size = out_input_ids.get_shape()[0];
auto input_ids      = ov::Tensor(ov::element::i64, ov::Shape{batch_size, total_tokens_count_per_batch});
auto attention_mask = ov::Tensor(ov::element::i64, ov::Shape{batch_size, total_tokens_count_per_batch});
```

then one `start_async()` / `wait()` over the whole thing. Two consequences
that shape the entire fix:

1. **Memory scales with B × T, not with B.** T is set by the *longest*
   document in the request, padded across the batch. Every other document is
   padded up to it.
2. **A cap on document count alone does not bound the worst case.** The model
   context here is about 8194 tokens; one long document at a permissive
   document cap is a far larger tensor than fifty short ones. Any guard that
   only counts documents is defeatable by a single long passage.

The activations of an XLM-RoBERTa-large cross-encoder over that tensor — not
the int8 weights, which are fixed and already resident in the 2.2–3.0 GiB idle
footprint — are what climbs into the limit. The 6.72 s at 30 documents against
1.48 s at 20 is that climb becoming visible before the kill.

### The guard already exists upstream — it is set to 10000

`src/rerank/rerank_calculator_ov.proto`:

```proto
message RerankCalculatorOVOptions {
    required string models_path = 1;
    optional uint64 max_allowed_chunks = 2 [default = 10000];
    optional uint64 max_position_embeddings = 3;
    optional string target_device = 4 [default = "CPU"];
    optional string plugin_config = 5 [default = ""];
}
```

`max_allowed_chunks` is checked **three times**, and the first check happens
before a single token is allocated (`rerank_calculator_ov.cc:152`):

```cpp
// Validate batch size before tokenizing
if (handler.getDocumentsList().size() > this->max_allowed_chunks)
    throw std::runtime_error("Number of documents exceeds max_allowed_chunks");
```

and twice more inside `chunkDocuments` (`src/rerank/rerank_utils.cpp:225` and
`:255`) — once on the pre-chunking batch and once on the post-chunking chunk
total. So the single field bounds **both** the document count and the total
chunk count.

It is absent from our servable. `export_model.py`'s `rerank_graph_ov_template`
emits only three fields:

```jinja
[type.googleapis.com / mediapipe.RerankCalculatorOVOptions]: {
  models_path: "{{model_path}}",
  plugin_config: '{"NUM_STREAMS": "{{num_streams}}" }',
  target_device: "{{target_device|default("CPU", true)}}"
}
```

so the proto default of **10000 documents** applies — four orders of magnitude
above what this container's memory limit can serve. The server has a bouncer;
nobody told him the room holds fifty.

### `--max_doc_length` is not the knob the issue hoped for

The issue proposed `export_model.py rerank_ov --max_doc_length` as a batch or
request-size cap. It is neither. The flag never reaches `graph.pbtxt`; its only
use is in `export_rerank_tokenizer`:

```python
hf_tokenizer = AutoTokenizer.from_pretrained(source_model)
hf_tokenizer.model_max_length = max_length
```

It sets the converted tokenizer's truncation length — a **per-document** token
ceiling baked in at export time (currently the default, 16000). It says nothing
about how many documents a request may carry. `--num_streams` is likewise
orthogonal: it is an OpenVINO plugin concurrency setting, and raising it would
increase peak memory, not bound it.

### The refusal is a 500, not a 4xx

The issue asked for "4xx rather than taking the process down". Upstream gives
the first half but not, apparently, the second. Every guard above raises
`std::runtime_error` (directly, or by wrapping the `absl::InvalidArgumentError`
that `chunkDocuments` returns), and `Process()` catches it at
`rerank_calculator_ov.cc:348`:

```cpp
} catch (std::runtime_error& e) {
    return absl::InternalError(e.what());
}
```

`InternalError` conventionally maps to HTTP **500**. The load-bearing property
— an oversized call returns a response, with a message naming the limit, and
every other caller keeps their server — is met. The status code is not ours to
choose without forking the calculator, which is out of proportion to the
problem. **The Test Plan records the actual observed status code rather than
asserting 4xx**, and the plan does not fail if it is 500.

## Design

Four changes, no new components.

### 1. Bound both dimensions, in `graph.pbtxt`

Add two fields to the rerank node's `node_options`, in **both** exported
repositories (`/out/gpu` and `/out/cpu` — the CPU control arm must stay a
like-for-like comparison):

```proto
max_allowed_chunks: <N>
max_position_embeddings: <T>
```

- `max_allowed_chunks: <N>` — the document-and-chunk cap. Set with headroom
  **above 50**, the batch the downstream client actually sends, per the
  operator decision below. Requests above it are refused before tokenization.
- `max_position_embeddings: <T>` — the per-chunk token ceiling, which is what
  actually bounds the padded tensor width. Documents longer than
  `T − query_tokens − NUMBER_OF_SPECIAL_TOKENS` are split into chunks, scored
  per chunk, and the chunk total is then checked against `<N>` — so a request
  of long documents is refused cleanly instead of allocating.

Together they bound peak allocation at roughly `N × T` tokens, which is the
quantity the measurement below pins to a number.

**Cost, stated plainly:** chunking changes scoring semantics for documents
longer than `T`. Such a document is no longer scored whole; it is scored per
chunk with the per-document score taken from its chunks. That is a visible
relevance-score change for the downstream client, accepted deliberately
(spec journal, `bound-sequence-length-too`) because the alternative leaves the
guard defeatable by a single long passage.

**Precondition to verify, not assume:** the chunking path only runs when
`RerankServable::addBosToken` is true. It defaults true and is set false only
when the exported `tokenizer_config.json` carries an explicit
`"add_bos_token": false` (`src/rerank/rerank_servable.hpp:48`). If it were
false for `bge-reranker-v2-m3`, `max_position_embeddings` would become a hard
error boundary for long documents rather than a chunking boundary — a
different, louder behaviour. Phase 1 reads the file off the running pod and
records the answer before any value is chosen.

### 2. The fields are written by the model image, not a deploy-time overlay

`export_model.py` cannot emit these fields and will not be forked. The
Dockerfile's **export stage** post-processes each generated
`graph.pbtxt` after the four `export_model.py` invocations, inserting the two
fields into the `RerankCalculatorOVOptions` block. `MODELS_REV` moves **1 → 2**,
which is already enforced (`test_models_rev_moves_when_the_dockerfile_changes`
fails a PR that edits the Dockerfile without bumping the rev), CI republishes
`ghcr.io/derio-net/ovms-retrieval-models:2`, the Deployment pin moves, and the
version-gated seed reseeds the PVC.

Rejected: a kustomize `configMapGenerator` mounted by `subPath` over
`/models/bge-reranker-v2-m3/graph.pbtxt`. It would make retuning a values edit
instead of a model rebuild, which is genuinely attractive — but it splits the
truth across two artifacts and layers a `subPath` mount over a `readOnly` PVC
path, a shape this repo has been bitten by before. Operator decision:
`cap-lives-in-model-image`. **Accepted cost:** retuning the cap later means a
full model rebuild (re-download and re-quantize both models) plus a 2.4 GiB
reseed, not a one-line change.

The insertion must be **assertive, not best-effort**. A `sed` that silently
matches nothing would publish rev 2 with the guard absent, and every downstream
check — CI green, ArgoCD Synced, pod Ready, the marker at rev 2 — would agree
that it shipped. The build therefore re-reads each emitted `graph.pbtxt` and
fails if the fields are not present.

### 3. Raise the memory limit to support the batch the client sends

`limits.memory` on the `ovms` container: **6Gi → 10Gi**. `requests.memory`
stays at 2Gi, so the scheduler's view of mini-1 is unchanged; only the ceiling
moves. CPU is untouched at 500m / 2.

This is the operator's decision (`raise-limit-support-fifty`) and it is a
deliberate reversal of the parent spec's posture. That spec kept the ceiling
small on purpose because mini-1 is an **etcd member** and the whole iGPU
experiment was sized to keep its failure domain away from the control plane.
The counter-argument, which won: a cap set below what the client sends makes
every default-configured call fail, which is a working reranker that reranks
nothing — the exact outcome the issue exists to end. mini-1 has the headroom
(measured 10% of 64 GB in use at the parent spec's survey), and the guard
below means the ceiling is now an unreachable backstop rather than the thing
the workload runs into.

Rejected: hold 6Gi and cap at the largest measured-safe batch (24–32), forcing
the client to chunk; pin at the already-proven 20 with no measurement at all.

### 4. A batch sweep in the benchmark harness

`scripts/ovms-retrieval-bench.py` already reranks a fixed 20 candidates — it
is the harness that produced the parent spec's numbers and it already has the
in-cluster invocation, the `--arm` assertion, the `/v1/config` snapshot and a
recorder-based test suite. It gains a sweep mode that walks a configurable
list of batch sizes (default 10, 20, 30, 40, 50, and `N+1` to prove the
refusal), recording per size: latency, HTTP status, and response body on
failure. `N+1` is expected to be refused, and a sweep in which it *succeeds*
is a failed run, not a lucky one.

Two constraints the current harness imposes, found in review and load-bearing
for whether the sweep measures the right thing at all:

- **`generate_filler_passages` emits a fixed ~20-word passage.** The
  reproduction in the issue used **200-word** documents, and the mechanism is
  B × T — so a sweep at the harness's present length would send roughly a tenth
  of the tokens per document and could easily fail to reproduce the OOM at any
  batch size, while looking like a clean run. The sweep needs a passage-length
  knob (`--rerank-words`, padding the existing filler rather than inventing new
  prose), and the recorded curve must carry the length it used. A number quoted
  without it is meaningless.
- **`_post_json` raises on anything but 2xx.** It wraps
  `urllib.request.urlopen`, so a refusal surfaces as `HTTPError` and a killed
  server as `URLError` / `RemoteDisconnected`. The sweep must catch both and
  record status and body as *data* — the refusal is the result it exists to
  capture — rather than aborting the run at the first failure. It must also not
  warm up at a size it is about to prove fatal: warm-up belongs at the smallest
  size only.

This is what converts the issue's closing offer — "I can re-run the
client-side measurement and report the numbers" — into something reproducible
rather than a one-off.

## Measurement — this is what sets the numbers

The cap and the sequence bound are **not** chosen from first principles. The
operator authorised driving the sweep against the live server
(`measure-live-before-shipping`), accepting several deliberate OOM-kills and
roughly ten seconds of refused connections each for the downstream client.

Procedure, from an in-cluster pod, before any manifest change:

1. Sample `container_memory_working_set_bytes` for the `ovms` container at
   idle.
2. Sweep 10, 20, 30, 40, 50 documents at a fixed ~200 words each, sampling the
   working set during each call and reading `restarts_total` after it.
3. Record, per size: peak working set, latency, and whether the pod restarted.
4. Repeat the sweep at 10Gi to find where the 50-document call actually peaks —
   the 6Gi arm can only report "hit the ceiling", never the true requirement.

### Measured, 2026-09-11, at the current 6Gi limit

Single calls, each read from `/sys/fs/cgroup/memory.peak` inside the `ovms`
container (vmagent scrapes at 20s; these transients last 0.1–2.5s, so metrics
cannot see them).

| documents | tokens/doc | peak | result |
|---|---|---|---|
| 64 | 332 | 3.50 GiB (58%) | 200 |
| 50 | 511 | 4.38 GiB (73%) | 200 |
| 64 | 415 | 4.81 GiB (80%) | 200 |
| 64 | 511 | — | **killed** |
| 50 | 664 | — | **killed** |
| 40 | 664 | — | **killed** |

Three things this settles.

**T dominates.** At 10 documents, T≈329 costs 0.285 GiB, T≈667 costs 0.947,
T≈1329 costs 3.220 — doubling length more than triples the cost, an exponent
near 1.7. That is attention: the scores tensor is `B × heads × T × T`, and
this is XLM-RoBERTa-large (24 layers, 16 heads). At T≈664 even **forty** rows
is fatal. So `max_position_embeddings` is the primary control and
`max_allowed_chunks` the secondary one — the reverse of how the issue framed
it.

**The report reproduces, at its own token density.** A first sweep at 200
words had 50 documents succeed, where the issue reports 50 dying. Measured
against the served tokenizer: this harness's padded filler is 1.66 tokens per
word, random dictionary words are 3.02. Their documents were ~1.8× denser at
the same word count, which at a 1.7 exponent is ~3× the length-dependent
memory. Their 50-document call sits at T≈605, between two measured kills.
Words are not tokens, and the mechanism is tokens.

**Memory is never released.** `memory.current` after a large call equals
`memory.peak` and stays there — idle 2.21 GiB, 4.90 GiB after a 50-document
call. The resident floor ratchets to the high-water of the largest call
served, which explains the issue's restart accumulation over a week of light
use far better than any single request does. It also means an ascending
sweep's per-size deltas are **not** per-call costs; every clean number above
comes from a single call on a freshly restarted container.

**Do not extrapolate.** A power-law fit over three points over-predicted one
independent check by 28% and then predicted ~4.9 GiB — comfortably inside
6 GiB — for a configuration that killed the server. Measure the pair you
intend to ship, at the limit you intend to ship it with.

The numbers derived from that curve:

- **`max_allowed_chunks` (`N`)** — headroom above 50, set from the 10Gi curve
  so that `N` documents at `T` tokens peaks at **no more than ~70% of 10Gi**.
- **`max_position_embeddings` (`T`)** — chosen so that the same product holds
  for a request of long documents, not only short ones. The measurement must
  therefore include at least one pass with documents long enough to chunk.

The 30-document call's 6.72 s is itself a datum worth resolving: if latency is
already climbing steeply at 30, the *supported* batch and the *refused* batch
may want to be different numbers — a cap at `N` that admits calls taking tens
of seconds is a worse outcome than a cap that refuses them. The sweep reports
latency alongside memory precisely so that this can be decided on evidence.

## Named gaps

1. **The status code is upstream's, not ours.** The refusal is expected to
   surface as HTTP 500 (`absl::InternalError`), not the 4xx the issue asked
   for. Recorded, not fixed. A 4xx would require forking `RerankCalculatorOV`.
2. **The downstream client still fails open.** This spec makes the server
   refuse cleanly; it cannot make the client notice. A client that silently
   swallows a 500 reranks nothing just as quietly as one whose server died —
   it merely stops taking the embeddings service down with it. The client-side
   half belongs to the downstream repo and is out of scope here.
3. **CI cannot prove serving behaviour.** The repo's tests guard manifest and
   Dockerfile *shape*; whether the running server actually refuses `N+1` is a
   live-proof matter. Hence the post-merge Test Plan.
4. **Chunked scoring is unvalidated for quality.** The parent spec's acceptance
   row proved score separation (~2400× relevant vs irrelevant) on whole
   documents. Nothing here re-proves it for documents scored per chunk. The
   Test Plan adds a separation check at the new `T`.
5. **The embeddings servable is unbounded.** The same process serves
   `/v3/embeddings`, and the issue notes one restart under a batch embeddings
   load. This spec bounds rerank only. Whether `embeddings_ov` needs an
   equivalent cap is a separate question and deliberately not answered here.
6. **Retuning is expensive by construction.** Consequence of decision
   `cap-lives-in-model-image`: the next value change is a full model rebuild
   plus reseed. If the first measured value turns out wrong, that cost is paid
   again.

## Counter-arguments considered

**"Just raise the limit and skip the cap."** mini-1 has 64 GB; 16Gi would make
50 documents comfortable with no guard at all. Rejected because it does not
remove the failure, it relocates it: some batch still kills the process, the
cliff is merely further out and now undiscovered, and the failure mode stays
"the whole server dies" rather than "this request is refused". A bound you have
measured is worth more than a ceiling you have not reached yet.

**"Put a proxy in front and cap the body size."** A request-size limit at an
ingress would be model-agnostic and need no rebuild. Rejected: it adds a
component to a service the parent spec deliberately kept unexposed (no
LoadBalancer, no IngressRoute, no LiteLLM alias), and body bytes are a poor
proxy for B × T — 68 KiB of one long document and 68 KiB of fifty short ones
cost very different amounts of memory.

**"Split the two servables into separate Deployments."** That would contain the
blast radius, so that a rerank OOM stops evicting embeddings. It is a real
option, and reversing the parent spec's central decision ("one Deployment, one
pod, one ResourceClaim, one iGPU — rather than two of everything"). Note that
spec argued from *simplicity*; it did not establish whether two ResourceClaims
can hold one iGPU device at all, which under DRA is not a given. So this is
both out of proportion to a fix and resting on an unverified premise. Worth
revisiting — with that premise checked first — if the guard proves
insufficient.

**"Set only `max_allowed_chunks` and leave sequence length alone."** Simplest
change, no scoring impact. Rejected on the mechanism: the tensor is B × T, T
comes from the longest document, and the model context is ~8194 — so a
document-only cap leaves a guard that one long passage walks straight past.

## Test Plan (post-merge, operator-driven)

| # | Action | Expected |
|---|---|---|
| 1 | `kubectl -n retrieval get deploy ovms-retrieval -o jsonpath='{.spec.template.spec.containers[?(@.name=="ovms")].resources.limits.memory}'` | `10Gi` |
| 2 | `kubectl -n retrieval exec deploy/ovms-retrieval -c ovms -- cat /models/.seed-rev` | `2` |
| 3 | `kubectl -n retrieval exec deploy/ovms-retrieval -c ovms -- cat /models/bge-reranker-v2-m3/graph.pbtxt` | carries both `max_allowed_chunks` and `max_position_embeddings` at the chosen values |
| 4 | `GET /v1/config` | both servables `AVAILABLE` — the new fields did not break loading |
| 5 | `POST /v3/rerank`, 50 documents × 200 words | **200**, with latency recorded |
| 6 | `POST /v3/rerank`, `N+1` documents | a response, not a closed socket; status code and body **recorded verbatim** (500 expected, not asserted) |
| 7 | Immediately after 6: `POST /v3/rerank`, 3 × 50 | **200** — the server survived the refusal |
| 8 | `kube_pod_container_status_restarts_total` across 5–7 | unchanged |
| 9 | Rerank one document long enough to chunk at `T` | scores still well-separated (not the degenerate 1e-9..1e-12 pattern), gap 4 |
| 10 | Bench sweep re-run, recorded to `docs/` | peak working set at every size ≤ ~70% of 10Gi |

Rows 5–8 are the acceptance evidence: a batch of 50 either succeeds or is
refused cleanly, which is the condition the issue set for re-running the
client-side measurement.

## Sequencing

1. Verify `add_bos_token` on the running pod; sweep the live server at 6Gi;
   record the curve. **This phase deliberately OOM-kills the server.**
2. Raise `limits.memory` to 10Gi; re-sweep; derive `N` and `T` from the curve.
3. Dockerfile post-processing + `MODELS_REV` 2 + build-workflow rev; assertive
   verification in the build; tests.
4. Deployment pin to `:2`; manifest tests.
5. Bench sweep mode + its recorder tests.
6. Docs: gotchas one-liner, per-topic prose in
   `docs/runbooks/frank-gotchas/igpu-dra.md`, and a retroactive correction to
   the building/operating posts for layer 11 per the fix/extension workflow.
7. **Append every artefact this work adds to `SCANNED_PATHS` in
   `scripts/tests/test_third_party_discretion.py`.** That file is the
   discretion control surface and it scans *only* the paths named in that list;
   it records that this exact omission already happened once, on frank#759,
   producing a green run that said nothing about the new branch's artefacts.
   The spec, its journal, the plan and its journal, and any new or changed
   script all belong there. (The checks were run ad hoc against this spec and
   its journal during review and pass; that is not a substitute for the list.)

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-09-11--infer--ovms-rerank-batch-guard | `derio-net/frank` | `2026-09-11--infer--ovms-rerank-batch-guard` | — |
