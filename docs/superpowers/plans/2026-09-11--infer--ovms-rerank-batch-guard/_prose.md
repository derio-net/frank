## What this plan does

`POST /v3/rerank` takes the whole `ovms-retrieval` server down on a 50-document
batch — the batch an external client sends by default — and because that server
hosts the embeddings servable too, one oversized rerank call evicts embeddings
for every caller for about ten seconds. This plan makes the oversized call
**refused** instead of **fatal**, and raises the ceiling so the batch the client
actually sends is no longer oversized.

Design: `docs/superpowers/specs/2026-09-11--infer--ovms-rerank-batch-guard-design.md`.
Issue: [#793](https://github.com/derio-net/frank/issues/793).

## The one thing to understand before editing anything

The rerank calculator builds **one** inference tensor of shape
`{batch_size, longest_document_tokens}` and runs a single inference over it. So
peak memory is **B × T**, where T is set by the longest document in the request
and padded across every other document.

Two consequences run through every phase:

- A cap on **document count alone does not bound the worst case.** The model
  context is about 8194 tokens; one long passage at a permissive cap is a far
  bigger tensor than fifty short ones. That is why the plan sets
  `max_position_embeddings` as well as `max_allowed_chunks`.
- A **measurement taken with short documents measures the wrong thing.** The
  benchmark harness's existing filler is ~20 words per passage; the issue
  reproduced at 200. Phase 2 adds the length knob before phase 3 measures
  anything, and the recorded curve carries the word count it used.

The guard itself already exists upstream and is simply not configured:
`max_allowed_chunks` has a proto default of 10000, and `export_model.py`'s
rerank graph template never emits the field. Confirmed live on
`ovms-retrieval-9675d55d-8mzp7` — the deployed `graph.pbtxt` carries exactly
`models_path`, `plugin_config` and `target_device`.

## Shape of the work

| Phase | What lands | Why here |
|---|---|---|
| 1 | Fixtures captured from the live pod; the injector, TDD; `SCANNED_PATHS` extended | Walking skeleton: a real artefact, a real transformation, a real CI run, before anything expensive |
| 2 | Benchmark sweep mode with failure tolerance and a passage-length knob | The instrument has to be right before the measurement, not after |
| 3 | **The live measurement.** Sweep at 6Gi, patch to 10Gi, re-sweep, derive `N` and `T` | Everything downstream is parameterised by these two numbers |
| 4 | The injector wired into the Dockerfile export stage; `MODELS_REV` 1 → 2 | The guard ships as model-image bytes, per the operator's decision |
| 5 | Deployment pinned to `:2`; `limits.memory` 6Gi → 10Gi | The deploy |
| 6 | Gotcha one-liner, runbook prose, retroactive post edits | Fix/extension workflow — extend the layer-11 posts, do not add one |

## Phase 3 is executed inline, not dispatched

Every other phase is dispatched to a phase executor. Phase 3 is not. It
deliberately OOM-kills a live service and it suspends ArgoCD self-heal on the
**root** App-of-Apps in order to patch a memory limit on an **etcd member**. A
suspended GitOps loop plus a running control-plane workload is not something to
hand to a subagent, and the operator's authorisation for the disruption was
given to this session.

Its restore path is written as its own task rather than a trailing step,
because the two ways this repo has been bitten before both live there: a
`--type=merge` patch of `syncPolicy.automated` **replaces** the nested map, so
flipping `selfHeal` alone silently deletes its `prune: false` sibling; and a
manually-triggered sync does **not** inherit `spec.syncPolicy.syncOptions`.
Phase 3 ends by asserting the live object is back to 6Gi and both Applications
read `Synced` — not merely `Healthy`.

## What this plan does not do

- **It does not make the refusal a 4xx.** The calculator raises
  `std::runtime_error`, `Process()` catches it into `absl::InternalError`, and
  that conventionally maps to HTTP 500. The load-bearing property — a response
  instead of a dead process — holds. The Test Plan **records** the observed
  status code rather than asserting 4xx, and does not fail on 500.
- **It does not fix the client.** The client fails open silently; this plan
  stops it taking the embeddings service down with it, and cannot make it
  notice. That half lives in another repo.
- **It does not bound the embeddings servable.** Same process, same limit, and
  the issue notes one restart under a batch embeddings load. Separate question,
  deliberately unanswered here.
- **It does not split the two servables into separate Deployments.** That would
  contain the blast radius properly, and it is the parent spec's central
  decision to reverse. Out of proportion to a fix, and it rests on an unverified
  premise about whether two ResourceClaims can hold one iGPU device.

## Verification

CI guards manifest, Dockerfile and injector **shape**; it cannot prove serving
behaviour. The three acceptance rows this plan advances are therefore all
live-proof, owed post-merge, and their evidence is the spec's Test Plan —
notably rows 5–8, where a batch of 50 succeeds, an oversized batch returns a
response rather than a closed socket, the very next small call still returns
200, and the restart count has not moved.
