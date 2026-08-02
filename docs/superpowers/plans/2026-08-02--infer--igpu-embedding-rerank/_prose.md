# Retrieval models on the mini iGPUs — implementation

**Spec:** `docs/superpowers/specs/2026-08-02--infer--igpu-embedding-rerank-design.md`

Serve `bge-m3` (embeddings) and `bge-reranker-v2-m3` (rerank) on the Intel Arc
iGPU of a control-plane mini via the DRA resource driver, exposed in-cluster
over OpenVINO Model Server, and **measure it**.

## Discretion constraint

The requesting repo is private; this one is public. No artifact produced by this
plan — code, test, doc, commit message, PR body, blog text — may name the
consumer repo, its product or its corpus, or reproduce its benchmark queries or
document titles. The multilingual property is kept, because it is the generic
technical reason for choosing these two models over English-centric ones.
Treat a breach as a blocking review finding.

## What is already proven

The spec's runtime gate was run during design rather than deferred here, so this
plan starts from measured ground:

- The iGPU **computes** inside a container on a Talos control-plane node —
  `openvino/model_server:2026.2.1-gpu` on mini-1 logs `Available devices for
  Open VINO: CPU, GPU`.
- A DRA `ResourceClaim` is what injects `/dev/dri`; the identical pod without one
  has no `/dev/dri` at all (negative control run).
- The render node is `crw-rw-rw-`, so no `supplementalGroups` work is needed.
- The iGPUs are idle: zero `ResourceClaims` cluster-wide. This is Frank's first
  DRA consumer.

## What the gate disproved, and why phase 1 exists

The spec originally had initContainers running `ovms --pull`. That cannot work:
pull downloads raw HuggingFace weights that will not load (`openvino_tokenizer.xml
was not provided`); triggering conversion with `--weight-format` fails with
`missing optimum-intel`, which no published OVMS image carries; and the
pre-converted `OpenVINO/` HF org offers only **English** bge variants — the exact
model class this request exists to move away from.

So phase 1 builds a model image in CI. The runtime stays stock upstream; the only
thing Frank maintains is a bag of model files. An OVMS upgrade is then a tag bump,
not a rebuild of a forked server.

## Three traps this plan is deliberately shaped around

Each is a failure this repo has already had, in a different app:

1. **`/v2/health/ready` lies.** It returned 200 while the only servable sat in
   `LOADING_PRECONDITION_FAILED`. Readiness must be model-level, or the outcome is
   a Ready pod, a green Application, and every request failing.
2. **Seed-if-absent never updates.** The comfyui custom-nodes PVC has this bug
   documented: an image update never reaches an already-seeded volume. The seed is
   version-gated by a marker, so the first model bump actually deploys.
3. **A `push: main`-only build workflow ships unbuilt Dockerfiles.** Every build
   workflow in this repo has that shape, and the agent-images equivalent is a
   documented trap — a PR looks green while nothing was compiled. This workflow
   adds a `pull_request` build-only job so the PR validates itself.

## Shape

Phases 1–4 are agentic and fully offline-testable: they author the model image,
the manifests, the benchmark harness and the documentation, each pinned by
tripwire tests that run in CI via `repo-tripwires.yml`. Nothing in them needs the
cluster.

Phase 5 is the single `[manual]` phase and is **last**, with nothing depending on
it. It is manual for a structural reason rather than a preference: ArgoCD syncs
from `main`, so the service cannot exist — and therefore cannot be measured —
until the PR merges. It ships unimplemented; the operator pushes its results to
the same PR.

## The measurement is the deliverable

This is a spike. The artifacts exist to produce numbers: rerank p50/p95/max for a
20-passage batch, the embedding dimension, and a **CPU control arm on the same
node**. The minis are 14-core and ~95% idle, so "the iGPU beats these CPUs for a
568M cross-encoder" is a hypothesis. If the CPU arm wins, the DRA plumbing was
unnecessary complexity and the plan should say so rather than bury it.

The requester's own recall benchmark is **not** verifiable here —
it depends on a corpus this cluster does not have and this repo must not contain.
Frank's job ends at making it runnable and reporting the latency and dimension
back.
