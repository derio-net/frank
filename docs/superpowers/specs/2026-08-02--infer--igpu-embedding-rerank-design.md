# Retrieval Models on the mini iGPUs — Embeddings + Rerank via Intel DRA

**Date:** 2026-08-02
**Layer:** `infer` (11) — Local Inference
**Status:** Designed — not deployed.
**Prompted by:** an infrastructure request filed as issue #48 in a **private
downstream repo**. That repo owns the consumer; this repo owns the service. The
consumer is deliberately left unnamed here and in every artifact this work
produces — see the operator for the pointer.

## Scope discipline (read before writing any artifact)

This spec, its plan, the PR body, the runbook entries and any blog text are all
**public**. The requesting repo is not. Therefore:

- Do **not** name the consumer repo, its product, or its corpus.
- Do **not** reproduce the requester's benchmark queries, document titles, or
  corpus statistics. They are the private corpus's contents.
- **Do** keep the technical driver, which is generic and load-bearing: the
  consumer's corpus is multilingual across three European languages, which is
  why an English-centric embedding model under-ranked and why a *multilingual*
  pair was specified.

Everything below respects that line. Reviewers should treat a breach of it as a
blocking finding.

## What is being asked for

Two retrieval models, served on Frank, reachable in-cluster:

| Model | Role | Params | Why this one |
|---|---|---|---|
| `BAAI/bge-m3` | embeddings | 568M | multilingual — replaces an English-centric model that mis-ranked non-English notes |
| `BAAI/bge-reranker-v2-m3` | rerank | 568M | a **true cross-encoder**, and multilingual |

The requester's measured problem is **ranking, not recall**: the right document
is retrieved and then buried. A prior attempt at a local reranker failed with
degenerate scores because an LLM-style reranker was served as if it were a
cross-encoder — a model-class error, not a runtime fault. `bge-reranker-v2-m3`
is the correct class.

**This is a spike.** The deliverable that justifies it is a *number*: measured
rerank latency for a realistic candidate batch. Everything else is the harness
required to produce that number honestly.

## Verified state of the cluster — measured 2026-08-02, not assumed

The request arrived with two items marked "not verified". Both are now closed,
plus several the request did not raise.

| Fact | Result | How |
|---|---|---|
| iGPU idle? | **Yes — zero `ResourceClaims` cluster-wide** | `kubectl get resourceclaims -A` → `No resources found` |
| DRA slices healthy? | **All three minis** publish `gpu.intel.com`, `healthy: true`, driver `i915` | `kubectl get resourceslices` |
| Kubelet plugin coverage | **All three** (the request had seen only mini-1/2) | `kubectl -n intel-gpu-resource-driver get pods -o wide` |
| Ultra 5 SKU | **Core Ultra 5 125H** (Meteor Lake-P) — 14 logical cores, PCI `0x7d51`, **7 Xe-cores** | `.status.capacity.cpu: 14` + ResourceSlice `pciId` |
| Kubernetes / DRA API | v1.35.3, `resource.k8s.io/v1` **GA** | `kubectl version` |
| Node headroom | mini-1 **2% CPU / 10% mem** of 14 cores / 64 GB | `kubectl top nodes` |
| Existing DRA consumers | **None.** This is the first. | as above |

### Two findings that change the manifests

**1. The device advertises `capacity.memory: "0"`.** The ResourceSlice reports
`millicores: 1k` and `memory: 0` — the iGPU has no dedicated VRAM, it borrows
the node's 64 GB. A `ResourceClaim` that *requests* GPU memory can therefore
never be satisfied. **The claim must select the device and nothing else.**

**2. `/dev/dri` is `crw-rw-rw-` root:root.** Proven with a live claim on mini-1:

```
--- /dev/dri ---
crw-rw-rw-  1 0 0 226,   0  card0
crw-rw-rw-  1 0 0 226, 128  renderD128
```

The usual Intel-GPU-on-Kubernetes tax — hunting the `render` GID for
`supplementalGroups` — **does not apply**. OVMS's non-root uid 5000 can open the
render node directly.

**Negative control (run, not assumed):** the identical pod *without* a
ResourceClaim has no `/dev/dri` at all. This matters because Frank's containerd
has cluster-wide CDI discovery enabled (phase05), which could plausibly have
injected the device for free. It does not — the claim is what does it.

Also observed: **PodSecurity enforces `baseline` and only warns on
`restricted`** (a `hostPath` probe was rejected outright; a `runAsNonRoot`
violation merely warned). Manifests will be restricted-compliant regardless.

**Egress:** a pod on mini-1 reached `huggingface.co` successfully, so pulling
model weights at first boot is viable.

Both probes and their ResourceClaim were deleted; `kubectl get resourceclaims
-A` is back to empty.

## Why the minis and not gpu-1

The request argues this and the argument holds. Restated in Frank's terms:

- `OLLAMA_MAX_LOADED_MODELS=1` and a default chat model occupying ~14 GB of the
  RTX 5070 Ti's 16 GB. Chat is large and swap-tolerant; retrieval is small and
  called on **every** query and thousands of times per bulk import. Sharing one
  `MAX_LOADED_MODELS=1` Ollama makes each embedding call evict the chat model.
- gpu-1 additionally participates in the GPU time-share/scale-to-0 arrangement,
  so a retrieval path homed there inherits cold-start behaviour that a
  latency-critical service must not have.
- Two 568M models are ~1.1 GB each at fp16 against **64 GB shared** per mini.
  They fit trivially and stay resident.

## Runtime: OpenVINO Model Server

Chosen over llama.cpp-SYCL and Infinity-OpenVINO.

- **Intel's own runtime** for Intel silicon; the shortest path from "device node
  present" to "device actually computing".
- **One server hosts both models.** One Deployment, one pod, one ResourceClaim,
  one iGPU — rather than two of everything.
- **The rerank wire shape is already exactly right.** OVMS's `/v3/rerank`
  returns `{"results": [{"index": 0, "relevance_score": 0.38...}]}` — the shape
  the consumer drives, with no adapter.
- **`--target_device NPU` is a values change away.** Meteor Lake carries an NPU;
  moving int8 rerank onto it later would free the iGPU without redesigning the
  deployment. (Out of scope here — see Named gaps.)

Costs accepted: the OpenAI-compatible paths are `/v3/…`, not `/v1/…`; and model
weights need a pull/convert step before serving.

Rejected: **llama.cpp-SYCL** serves `/v1/embeddings` and `/v1/rerank` at the
literal expected paths, but needs one process per model (two Deployments, two
claims), has no NPU path, and SYCL on Meteor Lake is less first-class.
**Infinity + OpenVINO** would make LiteLLM rerank routing a one-line config via
the native `infinity/` provider, but its OpenVINO backend is the least-exercised
of the three — the wrong risk to take on a spike whose whole output is a
measurement.

## Architecture

```
                       namespace: retrieval
  ┌──────────────────────────────────────────────────────────┐
  │  Deployment ovms-retrieval  (replicas: 1, Recreate)      │
  │  nodeSelector: kubernetes.io/hostname=mini-1             │
  │  toleration: node-role.kubernetes.io/control-plane        │
  │                                                           │
  │  initContainer pull-embeddings ─┐                         │
  │  initContainer pull-rerank     ─┼─→ PVC /models (Longhorn)│
  │                                 │                         │
  │  container ovms  ───────────────┘                         │
  │    resources.claims: [igpu]  ──→ ResourceClaimTemplate    │
  │                                   deviceClass gpu.intel.com│
  │    :8000  /v3/embeddings                                  │
  │           /v3/rerank                                      │
  │           /v2/health/{live,ready}                          │
  └───────────────────────┬──────────────────────────────────┘
                          │
              Service ClusterIP :8000
        ovms-retrieval.retrieval.svc.cluster.local
```

### Files

```
apps/ovms-retrieval/manifests/
  kustomization.yaml
  namespace.yaml            # pod-security: enforce=baseline, audit/warn=restricted
  pvc.yaml                  # Longhorn RWO, 20Gi — model repository
  resourceclaimtemplate.yaml
  deployment.yaml
  service.yaml
apps/root/templates/ovms-retrieval.yaml   # Application CR, project: infrastructure
scripts/ovms-retrieval-bench.py           # the measurement harness
```

Raw manifests, not a chart: OVMS has no chart worth vendoring for a five-object
app, and the repo already prefers `apps/<app>/manifests/` in that case.

### The ResourceClaim

```yaml
apiVersion: resource.k8s.io/v1
kind: ResourceClaimTemplate
metadata:
  name: ovms-igpu
spec:
  spec:
    devices:
      requests:
        - name: gpu
          exactly:
            deviceClassName: gpu.intel.com
            allocationMode: ExactCount
            count: 1
```

No `capacity` selector — see finding (1) above. A `ResourceClaimTemplate` rather
than a shared `ResourceClaim` so the allocation is owned by the pod's lifecycle
and cannot dangle; with `strategy: Recreate` (forced anyway by the RWO PVC) only
one pod ever holds it.

### Model acquisition

OVMS pull mode downloads-and-exits, which is exactly an initContainer:

```
ovms --pull --source_model BAAI/bge-m3            --task embeddings \
     --model_name bge-m3            --model_repository_path /models
ovms --pull --source_model BAAI/bge-reranker-v2-m3 --task rerank \
     --model_name bge-reranker-v2-m3 --model_repository_path /models
```

Idempotent — skip when the model directory already exists, so a pod restart does
not re-download. Weights land on the Longhorn PVC and survive reschedules.

**If pull mode does not maintain `/models/config.json`,** the fallback is a
Kustomize `configMapGenerator` supplying it. That generator is mandatory rather
than a plain ConfigMap because of this repo's standing rule: a hash-suffixed
name is what makes ArgoCD roll the pod on a content change. Using the generator
requires the Application to set `prune: true`, with a per-resource
`Prune=false` on the PVC so a mis-sync can never destroy the model cache.

### Resource ceiling

The minis are the control plane and the etcd quorum. Both requests and limits
are set — a limit without a request lets the scheduler over-commit the node.

```yaml
resources:
  requests: { cpu: "500m",  memory: "2Gi" }
  limits:   { cpu: "2",     memory: "6Gi" }
```

2 of 14 cores and 6 of 64 GB. Note that iGPU allocations come out of host RAM
via i915, so the memory limit is the real backstop, not a formality.

### Placement

Pinned by hostname to **mini-1** — the node with the most headroom, so the
quorum risk of the experiment lands where there is most slack. mini-2 and mini-3
stay untouched and serve as the comparison arms for the control-plane-health
check. The pin is deliberate rather than letting the DRA scheduler choose: an
inference pod silently hopping between control-plane nodes is not something to
discover later.

### Image

`openvino/model_server:2026.2.1-gpu` — the newest released GPU tag (2026-07).
Pinned, never `latest-gpu`: the same image serves the initContainers, so an
unpinned tag would mean the puller and the server could silently diverge across
a pod restart.

### Security context

Restricted-compliant even though only `baseline` is enforced:
`runAsNonRoot: true`, `runAsUser: 5000` (the OVMS image's own non-privileged
user), `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`,
`seccompProfile: RuntimeDefault`. The world-readable render node means none of
this conflicts with GPU access.

**`fsGroup: 5000` is required**, and is the easiest thing here to get wrong. A
Longhorn PVC mounts root-owned, so without it the pull initContainer cannot
write the model repository and the pod fails at first boot — the same trap
already documented for Tekton workspaces in this repo. The failure is loud, but
only if you are watching the initContainer rather than the pod.

## Routing: in-cluster only

A ClusterIP Service at `ovms-retrieval.retrieval.svc.cluster.local:8000`, and
nothing else. No LoadBalancer IP, no IngressRoute, **and no LiteLLM change.**

This is the smallest thing that satisfies "reachable in-cluster", and it keeps
the blast radius off the chat gateway entirely. LiteLLM's rerank providers each
assume their own URL path, so fronting `/v3/rerank` would mean writing a shim —
real work, on the one part of the request that was itself hedged. Embeddings
*could* have been aliased cheaply via `openai/` + `api_base`; adding only half
the pair to the gateway would be more confusing than adding neither.

Laptop-side access, if needed, is `kubectl port-forward`.

Revisit if and when a second consumer appears — at that point a gateway earns
its keep.

## Measurement — the actual deliverable

A committed harness, `scripts/ovms-retrieval-bench.py`, run from inside the
cluster (laptop-side timing would measure the LAN, not the GPU):

1. **Rerank latency** — one query against **20 candidate passages**, N=30
   iterations after a warm-up, reporting p50 / p95 / max. This replaces the
   request's own estimate, which it correctly labels "arithmetic, not
   measurement".
2. **Embedding dimensionality** — recorded from the response, not assumed.
3. **Embedding throughput** — single and batch-32.
4. **A CPU control arm.** The same measurements with `--target_device CPU` on
   the same node.

Point 4 is not padding. The minis are 14-core and ~95% idle, so "the iGPU is
faster than these CPUs for a 568M cross-encoder" is a *hypothesis*. Without the
control arm the spike can only report that the iGPU works, not that it was worth
claiming. If CPU wins, that is a genuine and cheaper result.

### Control-plane health

Captured before / during warm load / after, from VictoriaMetrics:

- `etcd_server_leader_changes_seen_total` — **must not increase.**
- `etcd_disk_wal_fsync_duration_seconds` p99 on mini-1 vs mini-2/mini-3.
- `apiserver_request_duration_seconds` p99.
- mini-1 `Ready`, no `MemoryPressure`, container working set under the limit.

Comparing mini-1 against its two untouched peers is what makes this a
measurement rather than a vibe.

## Documentation corrections

`patches/phase05-mini-config/README.md` has drifted by a full API generation.
Its "What This Does" step 4 claims the **Intel GPU Device Plugin** is deployed
"to expose `gpu.intel.com/i915` as a schedulable resource", and points at
`apps/intel-gpu-plugin/`. What is actually deployed is Intel's **DRA resource
driver**, at `apps/intel-gpu-driver/`, and the extended resource does not exist
— querying it returns nothing. (The README's own *Verify* section is already
DRA-correct, which is exactly how the drift survived.) This work fixes it and
adds a claim example, since the correction alone still leaves a reader without
the replacement idiom.

A new gotchas topic file `docs/runbooks/frank-gotchas/igpu-dra.md` (plus its
index row and hot-file one-liners) captures: the zero-memory capacity trap, the
world-readable render node, the CDI-does-not-auto-inject negative control, and
the device-plugin-vs-DRA drift itself.

## Named gaps

1. **Compute is not proven, only the device node is.** `ls /dev/dri` says the
   device was injected; it does not say level-zero or OpenCL can enumerate it
   inside the OVMS container. This is the single largest technical risk and is
   the first phase's gate — if the GPU does not enumerate, the whole design is
   moot and the plan must stop there rather than build around it.
2. **OVMS pull-mode's `config.json` behaviour is unverified.** Fallback
   (configMapGenerator) is specified above, but which branch applies is unknown
   until it runs.
3. ~~The OVMS GPU image tag is not pinned.~~ **Closed during spec review** —
   pinned to `2026.2.1-gpu`. What remains unverified is whether *that specific
   build* enumerates a Meteor Lake iGPU under Talos's 6.18 kernel, which is
   gap (1), not a tagging question.
4. **The NPU is untested and out of scope.** Talos may not carry the
   `intel_vpu` module, `/dev/accel` was not checked, and the DRA driver
   publishes GPU devices only — an NPU would need a separate device plumbing
   story. Named because the request raised it, deferred because it is a second
   spike, not a corner of this one.
5. **Only bge-m3's *dense* head is exposed.** OVMS's embeddings servable
   returns dense vectors; bge-m3's sparse and multi-vector (ColBERT) heads are
   not surfaced. If the consumer later wants hybrid retrieval, that is a
   different runtime conversation.
6. **One replica means one iGPU serialising every request.** Fine for latency
   measurement and for interactive query traffic; a bulk corpus import will be
   slow. Scaling to three is a `replicas` change but is untested, and each
   additional replica is additional control-plane exposure.
7. **No authentication.** Any pod in the cluster can call the endpoint. This is
   consistent with how Ollama is exposed today, and is called out rather than
   silently accepted.
8. **The recall target cannot be verified in this repo.** See Test Plan.

## Counter-arguments considered

**"Just put it on gpu-1."** Rejected — residency conflict under
`MAX_LOADED_MODELS=1`, plus inherited scale-to-0 cold starts on a
latency-critical path. The request makes this case and it survives scrutiny.

**"Run it on the minis' CPUs; they are idle anyway."** This is the strongest
counter-argument and it is *not* dismissed — it is promoted into the test plan
as the CPU control arm. A 568M cross-encoder on 14 idle cores may well be fast
enough, in which case the iGPU claim, the DRA plumbing and the OVMS GPU image
are all unnecessary complexity. The spike should be able to say so.

**"Use pc-1 — it is a worker, not a control-plane node."** Rejected on hardware:
pc-1 is a 2013-era Z77/i5-3570K whose iGPU predates OpenVINO's supported
generations, and it has a documented reboot-instability history.

**"Front everything with LiteLLM for one base URL and spend tracking."**
Rejected for this spike — see Routing. The gateway's rerank support does not
line up with OVMS's paths, and building a shim is the highest-effort, lowest-
information part of the request.

**"Ship three replicas now — the issue says they are free."** They are free in
*hardware*; they are not free in control-plane exposure, and nothing has been
measured yet. One replica produces every number the spike needs.

## Test Plan (post-merge, operator-driven)

Frank can verify everything except the last row — the recall benchmark depends
on the private consumer's corpus, which this cluster does not have and this repo
must not contain. That row is owned by the requesting repo.

| # | Step | Pass condition | Owner |
|---|---|---|---|
| 1 | `kubectl -n retrieval get pod` after sync | pod `Running`, `/v2/health/ready` 200 | Frank |
| 2 | Confirm the GPU actually computes (device enumerated in OVMS logs, not just `/dev/dri` present) | GPU device listed by the runtime | Frank |
| 3 | `POST /v3/rerank`, 20 passages | `{results:[{index, relevance_score}]}`, scores well-separated (not the degenerate 1e-9..1e-12 pattern that sank the earlier attempt) | Frank |
| 4 | Rerank latency, N=30 after warm-up | p50 / p95 / max **recorded** | Frank |
| 5 | Same, `--target_device CPU` | CPU arm recorded; GPU-vs-CPU verdict stated | Frank |
| 6 | `POST /v3/embeddings` | dimensionality **recorded** (expect 1024) | Frank |
| 7 | Control-plane health across a warm load window | leader changes **unchanged**; etcd fsync p99 on mini-1 within noise of mini-2/3; node `Ready` throughout | Frank |
| 8 | `patches/phase05-mini-config/README.md` re-read | no device-plugin/extended-resource language; claim example present | Frank |
| 9 | The requester's 8-query benchmark, re-run against these endpoints | recall@5 ≥ 7/8 (baseline 5/8); recall@10 also reported | **Requesting repo** |

Row 9 is the request's headline acceptance criterion. Frank's job is to make it
*runnable*; whether the models actually fix the ranking is measured where the
corpus lives.

## Sequencing

1. **Gate** — prove the iGPU enumerates for compute inside an OVMS container on
   mini-1. Stop the plan here if it does not.
2. Model acquisition (initContainers) + PVC, pinned image tag.
3. Deployment / Service / ResourceClaimTemplate / Application CR.
4. Benchmark harness + the measurement run, including the CPU control arm.
5. Control-plane health verification.
6. Documentation: phase05 README correction, gotchas topic file, README sync.
7. Retroactive edits to the existing Layer 11 posts (this extends Local
   Inference; it is not a new layer, so no new posts) — reporting the *measured*
   numbers, and describing the consumer only as an external client.
