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

**The memory is pinned iGPU buffers, and `container_memory_rss` cannot see
them.** The iGPU has no VRAM, so every GPU allocation OpenVINO makes is a
shmem-backed host page, **unevictable** in this cgroup. Measured while the
server held 5.11 GiB:

```
shmem 5.11 GiB | unevictable 5.11 GiB | inactive_file 0 | active_file 0
anon 0.55 GiB  | swap.max 0
```

`shmem` and `unevictable` are the same number, there is no page cache to drop,
and there is no swap — so the kernel may reclaim **nothing** and OOM-kills
instead. `limits.memory` on this container is the **GPU's memory budget**, not
a margin around a process.

### Is anything actually using the retrieval tier?

Ask the metric, not the graphs. OVMS runs with `--metrics_enable` and is
scraped by `apps/ovms-retrieval/manifests/vmservicescrape.yaml`:

```promql
# requests served, per servable, over the last day
sum by (name) (increase(ovms_requests_accepted[1d]))

# guard refusals — an oversized batch being turned away
sum by (name) (increase(ovms_requests_fail[1d]))

# anything in flight right now
sum(ovms_current_requests)
```

**Not `ovms_requests_success`.** An earlier version of this page recommended
that series instead, and frank#813 measured why it is wrong: it is dominated
by `readinessProbe` traffic. `readinessProbe` hits
`/v2/models/bge-reranker-v2-m3/ready` every 10s (`deployment.yaml`), so the
reranker's `ovms_requests_success{method="ModelReady"}` accrues ~8,600/day
whether or not a single client ever calls it, while `bge-m3`'s only entry came
from its one-shot `startupProbe` and then never moved again — reading ~0
however much real traffic it serves. The query therefore invents usage for
one model and hides it for the other, which is exactly why the four-day
post-#793 silence below was so hard to interpret at the time: nobody could
tell whether "no `ovms_requests_success` movement" meant "no traffic" or "the
wrong series." `ovms_requests_accepted` has no `ModelReady` series at all, so
no probe filtering is needed.

**Why this exists.** Before the flag was set, `/metrics` answered 400 and the
only usage signal was `container_cpu_usage_seconds_total` and
`container_memory_working_set_bytes` — so "is anyone calling this?" had to be
inferred from graph shapes. That is how the whole #793 investigation had to
proceed, and after the fix shipped the endpoint served nothing for four days
in a way that was **indistinguishable from a downstream client that had
stopped calling**. That client fails open silently, so nothing else would have
reported it either.

**An idle retrieval tier is normal here** — five-day quiet stretches are in the
measured record — so there is deliberately no alert on zero traffic. The point
is to be able to answer the question, not to be paged about it.

**Diagnose from `memory.stat`, not from a proxy.** This point cost three
successive wrong explanations during the investigation, each from a different
proxy: `memory.current` counts shmem *and* page cache, so a high-water reading
looks like a leak; `container_memory_working_set_bytes` cannot separate the
two either; and `container_memory_rss` counts neither, sitting flat at
~0.45 GiB on used and idle days alike, which looks like proof that nothing is
accumulating. Only the breakdown distinguishes them.

**Nothing is released while the container lives**, and the pool grows toward
the largest request shape served. Measured:

| | |
|---|---|
| baseline after model load | 1.71 GiB (weights on the GPU) |
| one call, 64 docs × 600 tok | pool → 5.11 GiB (the call costs 3.40 GiB) |
| repeat a served shape | no growth |
| a new but *smaller* shape | no growth |
| an *ascending* sequence | more than the largest alone — fresh→50×500 gives 3.49 GiB, 20×500→50×500 gives 4.13 GiB |

The cleanest statement of the failure: **the same 60×500 request dies on a
warm pool and succeeds on a fresh one.** Proven in both directions. The model
predicts the kills exactly — 50×500 then 60×500 needs 1.71 + 1.77 + 2.10 + 0.5
= 6.08 GiB against a 6 GiB limit.

This is why the graph cap is necessary but **not sufficient**: it bounds what
one request may allocate, and cannot bound what a long-lived server
accumulates.

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
is 5.67 GiB as a SINGLE call — but 8.49 GiB as an ASCENDING sequence
(20 -> 40 -> 64 documents), which is the case that matters and the reason
the ceiling is 16Gi rather than 10Gi. Read
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

**And 64 is a cap on chunks AFTER splitting, which real traffic crosses.**
`chunkDocuments` checks the limit twice — on the document count before
chunking, then again on the chunk total after (`exceeding max_allowed_chunks
after chunking limit`). The Test Plan sent 600-token documents against a 640
cap, so one document was always one chunk and the second check was never
exercised. Measured 2026-09-16 against the live consumer corpus: 2142 chunks,
`token_count` p50 386 / p95 695 / max 1235, with **139 (6.5%) over the ~627
effective budget** (`max_position_embeddings − query_tokens − 4`). The client
sends **50** candidates, so a request carries `50 + k` chunks and refusal needs
`k >= 15`.

The base rate predicts `k ~ 3`. The measured median across eight real queries
is **9**, with one at **21 -> 71 chunks -> HTTP 400**, confirmed end to end
through the client's own audit log. **Retrieval returns the top 50 by
similarity and length correlates with matching**, so the reranker sees a
distribution enriched for exactly the documents the guard is most expensive
for. A cap sized against corpus statistics is sized against the wrong
population; size it against the *retrieved* distribution. Headroom on the
queries that pass is 3-11 chunks.

The two bounds are coupled in opposite directions: lowering
`max_position_embeddings` to save memory produces MORE chunks and pushes harder
against `max_allowed_chunks`. Move either and re-measure both. Tracked in
frank#793.

### `--max_doc_length` is not a batch cap, and the refusal is a 400

Two things that look like the answer and are not.

`export_model.py rerank_ov --max_doc_length` never reaches `graph.pbtxt`. Its
only use is `hf_tokenizer.model_max_length = max_length` while the tokenizer
is exported — a per-document truncation length baked in at export time, which
says nothing about how many documents one request may carry. `--num_streams`
is orthogonal too, and raising it would increase peak memory rather than bound
it.

A refused request returns HTTP **400**, measured live 2026-09-19 and matching
#805's own Test Plan row 6. An earlier draft of this entry predicted 500 by
reading the code — those guards raise `std::runtime_error`, `Process()` catches
it into `absl::InternalError`, and that maps to 500 — but the MediaPipe graph
wraps the failure before it reaches the HTTP layer, and the observed status is
400 with the limit named in the body:

```
HTTP 400  Chunking failed: exceeding max_allowed_chunks after chunking limit: 64; actual: 100
```

The load-bearing property is unchanged — the caller gets a response naming the
limit and everyone else keeps their server. **Assert 400**, and treat the
reasoning-from-source version as the cautionary case: the inference was sound
and the answer was still wrong, because nobody ran the request.

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

## A CPU-derived busy signal is blind to a GPU-offloaded server, and an idle clock that outlives its own restart turns one wrong reading into a loop

Two properties, and the first one generalises past this cluster: **a busy
signal built on container CPU cannot see work that the container handed to a
GPU**, and **an idle clock that a restart does not reset converts a single
misread tick into a restart every tick thereafter, with no rate limit.**
Neither is specific to OVMS. frank#813, 2026-09-19.

### What happened

`ovms-pool-watchdog` restarted `ovms-retrieval` five times in sixteen minutes
during a live downstream batch-index run and killed the job at batch 7 of 40.
The issue that reported it assumed the OOM-safety rule (Rule 1) was too
aggressive. The logs said otherwise — `critical-pool` never fired once in the
whole window; every restart was Rule 2, the hygiene rule, deciding the pod was
idle with an elevated buffer pool and reclaiming it:

```
19:26:12 action=restart reason=idle-with-elevated-pool  shmem=6641278976 millicores=4
19:36:12 action=restart reason=idle-with-elevated-pool  shmem=5104066560 millicores=5
19:38:12 action=restart reason=idle-with-elevated-pool  shmem=7238967296 millicores=29
19:40:12 action=restart reason=idle-with-elevated-pool  shmem=8313102336 millicores=41
19:42:12 action=restart reason=idle-with-elevated-pool  shmem=4089765888 millicores=5
```

That the decision line carries `shmem=` and `millicores=` beside the verdict
is what made this a single VictoriaLogs query instead of a guessing exercise:
the inputs the watchdog acted on are sitting right next to what it did with
them, so "was this the right call?" is answerable from the log alone.

### Root cause A — `busy` measured the CPU; the work was on the GPU

The watchdog derived `busy` from a `cpu.stat` delta against
`BUSY_MILLICORES=50`. The four ticks that restarted the pod read 4, 5, 29, 41
and 5 millicores — while `shmem` climbed 5.10 → 7.24 → 8.31 GiB across those
same ticks, i.e. the server was demonstrably working. OpenVINO offloads
inference to the iGPU, so a GPU-bound server's container CPU sits near zero
**by construction** — this is not a threshold that needed tuning, no value of
`BUSY_MILLICORES` separates "indexing" from "asleep" when the indexing barely
touches the CPU at all. Fixed by reading OVMS's own request counters
(`ovms_requests_accepted` + `ovms_requests_rejected`) instead of CPU — see
"Is anything actually using the retrieval tier?" above.

### Root cause B — the idle clock survived the restart, so one miss became a loop

The idle-tracking annotation lives on the **Deployment**, and `rollout
restart` does not touch it — it advances only on a positive `busy` sample.
Once root cause A pinned `busy=no`, the clock froze at its last-true value and
every following tick computed an idle duration well past the threshold. The
result has no rate limit: restart → pool refills within a tick or two →
elevated again → clock still stale → restart. That is why it was five restarts
in sixteen minutes and not one — **root cause A is why it started, root cause
B is why it did not stop**, and B is the more dangerous of the two, because it
turns *any* future regression in the activity signal into a restart loop
rather than a single unnecessary restart. A `pool-watchdog-restart-loop`
feature-health alert now watches for more than two restarts in 30 minutes, so
the next miss pages instead of running to exhaustion.

### Two near-misses on the fix itself

**`ovms_requests_success` looked like the obvious activity counter, and it is
the readiness-probe series.** It was the first thing reached for while fixing
root cause A — this repo's own gotchas file recommended it as the usage
signal at the time. Measured against the captured fixture: 449 of 450 samples
in the idle case are the reranker's `ModelReady` series, moved by
`readinessProbe` hitting `/v2/models/bge-reranker-v2-m3/ready` every 10s, not
by any client. Shipping it would have made `busy` read `yes` on every tick
forever — a quieter failure than the one being fixed, since Rule 2 would stop
reclaiming with no symptom until the pool reached the OOM ceiling. See "Is
anything actually using the retrieval tier?" above for the corrected query and
the three doc sites that used to recommend the wrong one.

**Porting `CRITICAL_PERCENT` from `shmem` to `memory.current` unchanged would
have moved the OOM trigger and re-killed the very index this work exists to
save.** A separate task in the same plan (frank#813) changed Rule 1's
numerator from `shmem` to `memory.current`, because that is what the kernel's
OOM killer actually compares against `memory.max`. `memory.current` runs a
roughly constant ~0.5 GiB **above** `shmem` (anon + kernel accounting on top
of the shmem-backed GPU buffers), and `CRITICAL_PERCENT=50` had been
calibrated against `shmem` — so carrying the same percentage across the
numerator swap silently tightens the trigger by several points of a 16Gi
limit. Checked against the incident's own log line: the peak `shmem` reading
(8313102336 bytes, 7.74 GiB) sat under the 8.00 GiB trigger, but the same
moment's `memory.current` was 8.17 GiB — over by 174 MiB. An unadjusted port
would have had Rule 1 kill the same batch-index run that Rule 2 killed, for a
third, unrelated reason. Caught by measuring the live gap rather than
reasoning that "the numerator change is safety-neutral in spirit"; the
percentage was recalibrated (50 → 53) to land back where the trigger already
sat in `shmem` terms. See docs/superpowers/plans/2026-09-19--infer--ovms-pool-watchdog-activity-signal for the full recalibration.
