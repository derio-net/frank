# Intel iGPU via DRA — gotchas

Covers `patches/phase05-mini-config/` (the DRA resource driver deployed at
`apps/intel-gpu-driver/`) and the first real consumer of it
(`apps/ovms-retrieval/`). All items below were verified live on the mini
control-plane nodes on 2026-08-02.

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
