# Intel iGPU via DRA — gotchas

Covers `patches/phase05-mini-config/` (the DRA resource driver deployed at
`apps/intel-gpu-driver/`) and the first real consumer of it
(`apps/ovms-retrieval/`). Items were verified live on the mini control-plane
nodes on 2026-08-02, except where a section carries its own date.

## `resource.k8s.io/v1` replaced the device plugin — the README drifted for a full API generation

`patches/phase05-mini-config/README.md` used to say the **Intel GPU Device
Plugin** was deployed "to expose `gpu.intel.com/i915` as a schedulable
resource", pointing at a since-removed `apps/intel-gpu-plugin/` path. What is
actually deployed is Intel's **DRA resource driver**
(`apps/intel-gpu-driver/`), and `resource.k8s.io/v1` is GA on this cluster
(Kubernetes v1.35.3). `gpu.intel.com/i915` does not exist as an extended
resource — querying `node.status.allocatable` for it returns nothing.
Workloads claim the device with a `ResourceClaim`/`ResourceClaimTemplate`
against DeviceClass `gpu.intel.com` instead. The drift survived undetected
because the README's own *Verify* section was already DRA-correct
(`kubectl get resourceslice`, `kubectl get deviceclass`) — only the
"What This Does" prose above it lagged. Corrected 2026-08-02; see the phase05
README's "Claiming the iGPU" section for the worked example.

## `capacity.memory: "0"` — do not put a capacity selector on the claim

The ResourceSlice for the iGPU on each mini reports `millicores: 1k` and
`memory: 0`. The iGPU has no dedicated VRAM; it borrows the node's 64 GB
through i915. A `ResourceClaim` that *requests* GPU memory can therefore
**never** be satisfied — the claim just sits unresolved with no event naming
the cause as "you asked for memory that doesn't exist." Select the device and
nothing else:

```yaml
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

The real memory backstop is the *container's* `resources.limits.memory` —
iGPU allocations come out of host RAM via i915, so that limit is not a
formality, it is the only ceiling that exists.

### The tripwire for this has to scan VALUES, not just keys

The obvious guard walks the claim's YAML and fails on a `capacity:` key. That
misses the form people actually write, because under `resource.k8s.io/v1` the
idiomatic way to filter on a device attribute is a CEL selector — where
`capacity` appears only inside a string:

```yaml
selectors:
  - cel:
      expression: device.capacity["gpu.intel.com"].memory.compareTo(quantity("2Gi")) >= 0
```

Fed to a key-only walker this produces zero violations. The claim then never
matches (`capacity.memory` is `"0"`), and the symptom is a pod stuck
`Pending` — which is indistinguishable from a pod that has simply not been
scheduled yet. `scripts/tests/test_ovms_retrieval_manifests.py` scans both
keys and string values; the value half was added after the key-only version
was shown, by mutation, to pass on exactly the selector above.

## `/dev/dri` is `crw-rw-rw-` root:root — skip the render-GID hunt

Proven with a live claim on mini-1:

```
--- /dev/dri ---
crw-rw-rw-  1 0 0 226,   0  card0
crw-rw-rw-  1 0 0 226, 128  renderD128
```

The usual Intel-GPU-on-Kubernetes tax — finding the host's `render` group GID
and setting `supplementalGroups` on the pod — **does not apply here**. Any
non-root uid (OVMS runs as uid 5000) can open the render node directly. Don't
copy a `supplementalGroups: [<render-gid>]` block from a generic Intel GPU
recipe onto Frank's minis; it's dead weight.

## CDI does not auto-inject the device, even with cluster-wide CDI discovery on

Frank's containerd has cluster-wide CDI device discovery enabled
(`patches/phase05-mini-config/05-mini-cdi-containerd.yaml`), which makes "the
device is just there for any pod" a plausible wrong assumption. It is not.
Proven by a negative control: an identical pod *without* a `ResourceClaim*`
had **no `/dev/dri` at all**. The claim is what triggers the injection — CDI
discovery only makes the *driver* able to advertise/inject devices when asked
via DRA; it does not put the device into every pod's namespace by default.

## `ovms --pull` downloads unservable raw weights

Running `ovms --pull` without `--weight-format` on a HuggingFace repo ID
downloads raw safetensors via git-lfs and writes a bare `graph.pbtxt`. The
model then fails to load:

```
Either openvino_tokenizer.xml was not provided or it was not loaded correctly
```

The download itself succeeds — the artifact set is simply not what OVMS needs
to serve (missing the converted OpenVINO IR and the tokenizer XML). Don't read
a successful `--pull` as evidence the model is servable.

## Conversion needs `optimum-intel`, which no published OVMS image carries

Adding `--weight-format int8` to force conversion on pull surfaces the real
error:

```
Trying to pull BAAI/bge-reranker-v2-m3 from HuggingFace but missing
optimum-intel. Use the ovms package with optimum-intel installed.
```

Docker Hub publishes only `2026.2.1` and `2026.2.1-gpu` for this OVMS
release, and **neither carries `optimum-intel`**. In-pod runtime conversion is
off the table on any stock image; conversion has to happen out-of-band (this
repo does it once, in CI, via OVMS's own `export_model.py`, and ships the
result as an image — see `apps/ovms-retrieval/docker/`).

## The `OpenVINO/` HuggingFace org only has English bge variants

Upstream's one-command pre-converted-model examples work because they
reference the `OpenVINO/` HF org, which publishes `bge-base-en-v1.5` and
`bge-reranker-base` — **English-only** variants. It does not publish
multilingual pairs. If a request needs a non-English or multilingual
embedding/reranker model, the pre-converted escape hatch does not cover it;
plan for a CI-built conversion image instead of assuming an upstream org has
already done the work.

## `/v2/health/ready` is SERVER-level — it returns 200 while a model is broken

OVMS answered `GET /v2/health/ready` with **200** while its only servable sat
in `LOADING_PRECONDITION_FAILED`. That endpoint reports whether the *server
process* is up, not whether any given model loaded. A Kubernetes readiness
probe pointed at it produces the worst available outcome: a `Ready` pod, a
green ArgoCD Application, and every inference request failing.

- **Readiness** must be model-level: `GET /v2/models/<name>/ready`.
- `GET /v1/config` is the per-servable diagnostic — it reports
  `AVAILABLE` vs `LOADING_PRECONDITION_FAILED` per model, and is what to check
  when a pod is `Running` but requests fail.
- Liveness may stay on `/v2/health/live` — restarting a healthy server whose
  model failed to load would crash-loop it instead of leaving it up long
  enough to report the failure via `/v1/config`.

This is the same silent-green failure family as the ConfigMap-doesn't-reach-
the-process traps already in this repo — the process answers, but the answer
isn't about the thing you actually need to know.

### Measured against a CLASSIC model only — MediaPipe-graph servables unverified

The 200-while-broken observation, and the per-model endpoint that replaces it,
were both taken against a **classic** OVMS model. `embeddings_ov` and
`rerank_ov` export **MediaPipe graph** servables, and
`/v2/models/<name>/ready` has never been exercised against one. Two outcomes,
one benign and one not: a 404 fails the startup probe and the pod
restart-loops, which is loud; a hardcoded 200 puts the silent-green failure
straight back, with `/v1/config` the only thing that would show it. Check
`/v1/config` before trusting `Ready` on a graph-backed servable.

## A first push to GHCR creates the package PRIVATE

Not iGPU-specific, but it is how an otherwise-correct first deploy fails. A
brand-new `ghcr.io/derio-net/<name>` package is created **private** by the
first push from Actions. Frank's convention is public packages pulled with no
`imagePullSecret` (see the comment in
`apps/cnc-base/manifests/statefulset-node.yaml`; `cnc-ghcr-pull` in
`apps/cnc-staging/manifests/` is the private-image alternative), so the first
sync of an app pinning that image is an `ImagePullBackOff` that **no change to
this repo can fix** — and it presents as a broken build or a broken sync.
Either set the package visibility to public at first publish, or ship a pull
secret with the app. Decide it before the sync, not during it.

## An immutable model-rev tag needs a gate, not a convention

`apps/ovms-retrieval` pins its model image to a rev tag and relies on that tag
being immutable in three separate places: `imagePullPolicy: IfNotPresent`, a
seed marker that compares `MODELS_REV` only, and a test tying the Deployment
tag to the workflow env. None of them notices a rev that fails to move. Change
the Dockerfile's quantization and leave `MODELS_REV` alone: CI republishes the
same tag with different bytes, the manifest is byte-identical so ArgoCD syncs
nothing, the node cache serves the old image, and even if the new image landed
the marker still matches so the seed skips. Old weights, indefinitely, with
everything green — the comfyui seed-if-absent bug one layer up.
`scripts/tests/test_ovms_retrieval_model_image.py::test_models_rev_moves_when_the_dockerfile_changes`
diffs the Dockerfile against `origin/main` and fails when the rev stayed put
(skipping, not erroring, where no baseline ref resolves).

## The rerank batch is one padded tensor, and its memory never comes back

Two facts about `POST /v3/rerank` on `ovms-retrieval`, and the second one is
the actual bug. Both measured 2026-09-11 against the served model (#793).

**Cost is near-quadratic in document LENGTH and only linear in document
COUNT.** The calculator builds a *single* inference input of shape `B × T` —
batch size by `tokens_count_of_longest_document` plus the special tokens and
the query — so T is set by the **longest** document in the request and every
other one is padded up to it (`src/rerank/rerank_calculator_ov.cc`, OVMS
v2026.2.1). The reranker is an XLM-RoBERTa-large cross-encoder (24 layers,
16 heads, model context 8194), so attention is `B × heads × T × T`. Measured,
cost per row is about `0.0202 GiB × (T/332)^1.78`: doubling T costs ~3.4×,
doubling B costs 2×. **`max_position_embeddings` is therefore the primary
control and `max_allowed_chunks` the secondary one** — the reverse of the
order they suggest themselves in, and a guard that only counts documents is
walked straight past by one long passage.

**Memory is never released.** `memory.current` after a large call equals
`memory.peak` and stays there: **2.21 GiB** idle, **4.90 GiB** resident after
a single 50-document call, with no return for the life of the container. The
resident floor ratchets up to the high-water mark of the largest call ever
served.

That ratchet, not request size, is what makes the failure intermittent. The
largest batch this endpoint is expected to serve costs 2.93 GiB at T≈605, so
on a freshly restarted pod it totalled 5.14 GiB and sat inside the old 6 GiB
limit comfortably. It died only once the floor had risen beneath it. A
reranker that works, then doesn't, then works again after a restart is a
ratchet — and it explains restarts accumulating 1 → 9 over a week of light
use, which no single request size does.

**So restarting the pod is a legitimate mitigation, and always was.**
`kubectl -n retrieval rollout restart deploy/ovms-retrieval` puts the floor
back to idle and buys the same headroom the guard buys, until the next large
call raises it again. It is also why a bug report and an attempt to reproduce
it can honestly disagree.

### The guard exists upstream, defaulted to 10000

`RerankCalculatorOVOptions` has always carried `max_allowed_chunks` (proto
default **10000**) and `max_position_embeddings`, and the chunk cap is checked
three times — once before a single token is allocated, then twice inside
`chunkDocuments`, on the pre-chunking batch and on the post-chunking chunk
total. Nothing was missing except a value. `export_model.py`'s
`rerank_graph_ov_template` emits only `models_path`, `plugin_config` and
`target_device`, so the proto defaults applied: four orders of magnitude above
what this container's memory limit can serve. The server had a bouncer; nobody
told him the room holds fifty.

Frank ships `max_allowed_chunks: 64` and `max_position_embeddings: 640`,
injected into every exported `graph.pbtxt` by the model image's build
(`apps/ovms-retrieval/docker/inject_rerank_guard.py`). Worst case at that pair
is 6.36 GiB — 64% of the 10Gi limit, and 106% of the 6Gi it replaced. Read
that the right way round: **the ceiling was raised because the guard's own
worst case must not itself OOM**, not to make room for a bigger workload.

The injection is assertive, not best-effort: the build re-reads each emitted
graph and fails if the fields are absent. A `sed` that silently matched
nothing would publish a model rev whose every downstream signal — CI green,
ArgoCD Synced, pod Ready, seed marker at the new rev — agreed that the guard
had shipped.

Cost of the sequence bound, stated plainly: a document longer than T minus the
query and the special tokens is no longer scored whole. It is split into
chunks, scored per chunk, and those chunks count against the same 64. That is
a visible relevance-score change, accepted deliberately, because the
alternative leaves a guard that one long passage defeats.

### `--max_doc_length` is not a batch cap, and the refusal is a 500

Two things that look like the answer and are not.

`export_model.py rerank_ov --max_doc_length` never reaches `graph.pbtxt`. Its
only use is `hf_tokenizer.model_max_length = max_length` while the tokenizer
is exported — a per-document truncation length baked in at export time, which
says nothing about how many documents one request may carry. `--num_streams`
is orthogonal too, and raising it would increase peak memory rather than bound
it.

A refused request returns HTTP **500**, not the 4xx that would be idiomatic.
Every one of those guards raises `std::runtime_error`, and `Process()` catches
it into `absl::InternalError`, which maps to 500. The load-bearing property
holds — the caller gets a response naming the limit, and everyone else keeps
their server — but **record the status code; do not assert 4xx**, or a test
fails on correct behaviour.

### Measure it with the cgroup peak, on a freshly restarted container

Two traps, both of which cost real time.

**A 20 s scrape cannot see these transients.** They last 0.1–2.5 s, so
`container_memory_working_set_bytes` steps straight over the peak and reports
a comfortable idle figure for a call that reached the limit. The instrument is
the cgroup's own high-water mark, read inside the `ovms` container:

```bash
kubectl -n retrieval exec deploy/ovms-retrieval -c ovms -- sh -c \
  'cat /sys/fs/cgroup/memory.peak /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max'
```

**Only single calls on a freshly restarted container are valid measurements.**
`memory.peak` is monotonic and the floor ratchets underneath it, so an
ascending sweep's per-size deltas are increments of a high-water mark rather
than per-call costs, and any kill part-way up the sweep is floor-plus-call,
not call. An earlier reading of exactly this data concluded that at T≈664 even
forty documents was fatal; those calls had each run on a container already
holding 3.5–4.8 GiB from the one before. The error runs in the direction that
makes you cap far too tightly. Restart between sizes, or the numbers describe
the sweep rather than the server.

One more, on extrapolation: a fit over the three measured points
over-predicted an independent check by 28%. The shipped pair is a short
extrapolation from measured anchors, not a derived bound, so re-measure at the
new ceiling rather than trusting the curve out to it.
