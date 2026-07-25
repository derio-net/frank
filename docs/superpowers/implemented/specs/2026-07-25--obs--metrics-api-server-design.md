# Metrics API on Frank — serve `metrics.k8s.io`

**Layer:** obs (Observability — new workload under `apps/`)
**Status:** Deployed
**Date:** 2026-07-25
**Repo:** `derio-net/frank`
**Motivated by:** #394 — `kubectl top nodes` fails with `error: Metrics API not available`.
The aggregated `metrics.k8s.io` API is unserved on Frank, so `kubectl top` and CPU/mem HPA
are dead. Surfaced while sizing nodes for runner placement (had to reason from allocatable
capacity instead of live utilization).

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-07-25--obs--metrics-api-server | `derio-net/frank` | `2026-07-25--obs--metrics-api-server` | — |

## Problem

Frank serves no resource Metrics API. Confirmed indirectly: `kubectl get nodes` works
(allocatable capacity reads from the node spec) but `kubectl top nodes/pods` fails —
nothing is registered for the aggregated `v1beta1.metrics.k8s.io` APIService. Everything
that depends on it is non-functional:

- `kubectl top nodes` / `kubectl top pods` — no live utilization at the CLI.
- **Horizontal Pod Autoscaler on CPU/memory** — can't read metrics, won't scale.
- VPA recommendations (if/when used).
- Any tooling that reads `metrics.k8s.io` rather than scraping VictoriaMetrics directly.

The raw CPU/mem data already exists: `victoria-metrics-k8s-stack` (v0.72.4, ns `monitoring`)
scrapes kubelet + cadvisor on all 7 nodes, and the amd64 cadvisor gap was already fixed via
the `labeldrop` in `apps/victoria-metrics/values.yaml`. The gap is specifically the
*aggregated Metrics API*, not data collection.

## The design fork (from #394) and how it resolved

The issue framed two paths:

1. **Standalone `metrics-server`** — canonical, serves `metrics.k8s.io` only, adds a second
   (cheap) scrape path polling the kubelet Summary API.
2. **`prometheus-adapter` backed by VictoriaMetrics** — serve `metrics.k8s.io` (+ `custom`/
   `external`) from data VM already holds; no double-scrape; unlocks custom-metric HPA; more
   PromQL-rules plumbing and per-control-loop TSDB query cost.

**Operator brainstorm decisions (settled):**

1. **HPA is wanted in the future; custom metrics "possibly, nothing concrete yet."** The
   first real need is CPU/mem HPA + `kubectl top` ergonomics — not a named custom metric.
2. **Decisive fact: `metrics-server` serves ONLY `metrics.k8s.io`.** It does not implement
   `custom.metrics.k8s.io` or `external.metrics.k8s.io`. The three APIs are three independent
   aggregated `APIService` registrations; only one component may own each. metrics-server and
   a VM-backed prometheus-adapter **coexist** cleanly — metrics-server owns the resource API,
   the adapter (when added) registers *only* `custom`/`external`.
3. **Chosen: ship `metrics-server` now** (this layer). The resource API is a solved,
   near-real-time problem metrics-server does better and cheaper than routing every CPU/mem
   HPA tick and `kubectl top` through a general-purpose TSDB. The "double scrape" objection is
   real but negligible at 7 nodes (~KB/node every 15s). Consumer count of the adapter-only
   `custom`/`external` path is **zero today**, so building it now is premature.
4. **Defer the VM-backed `prometheus-adapter`** (`custom`/`external` only) to its own future
   layer, triggered by the first concrete custom-metric HPA target — see §Deferred scope.
   Adapter *rules* are only writable against a real metric you intend to scale on, so this
   deferral is YAGNI-correct, not a capability loss.

## Goals

- `kubectl top nodes` returns live CPU/mem for **all 7 nodes** (mini-1/2/3, gpu-1, pc-1,
  raspi-1, raspi-2) — heterogeneous amd64 + arm64.
- `kubectl top pods -A` returns live CPU/mem for pods across namespaces.
- The `v1beta1.metrics.k8s.io` APIService reports `Available=True`.
- A **CPU/mem HPA is functional** end-to-end (proven with a throwaway HPA against an existing
  Deployment, then removed — "not Deployed until the workflow is observed end-to-end").
- Fully declarative: one new ArgoCD app under `apps/`, App-of-Apps managed, no `helm install`.

## Non-goals (this iteration)

- **`custom.metrics.k8s.io` / `external.metrics.k8s.io`.** Deferred to the VM-backed
  prometheus-adapter layer (§Deferred scope). metrics-server cannot serve these regardless.
- **Routing resource metrics through VictoriaMetrics.** Explicitly rejected above — strictly
  worse latency/fragility for the CPU/mem case that will be hit first.
- **A standing demo HPA.** The verification HPA is created, observed, and deleted; no HPA
  ships as a Frank workload (none exists today, and none has a concrete need yet).
- **Homepage tile / external ingress.** metrics-server is an internal control-plane API
  (consumed via the aggregation layer / `kubectl`), not a human-facing UI — Post-Deploy
  Step 1 is skipped.

## Architecture

```
  kubectl top / HPA controller
            │  (aggregation layer)
            ▼
  APIService  v1beta1.metrics.k8s.io   ──►  metrics-server (Deployment, ns kube-system)
                                                    │  polls /stats/summary
                                                    ▼
                                        kubelet on each of 7 nodes  (:10250, HTTPS)
```

- **Chart:** upstream `metrics-server/metrics-server` (kubernetes-sigs), multi-source
  Application mirroring the repo's pattern (upstream chart + `$values/apps/metrics-server/
  values.yaml`).
- **Namespace:** `kube-system` (convention; the Deployment and its RBAC/APIService are
  cluster-scoped control-plane plumbing, not a tenant workload).
- **Talos kubelet TLS:** Talos kubelets present **self-signed serving certs** not signed by
  the cluster CA, and metrics-server verifies the kubelet cert by default → scrapes would fail
  `x509: certificate signed by unknown authority`. Set `--kubelet-insecure-tls` (via chart
  `args`). This is the standard Talos requirement; kubelet cert rotation / a real serving-cert
  signer is out of scope for this layer.
- **Preferred address type:** `--kubelet-preferred-address-types=InternalIP` so metrics-server
  reaches kubelets by node InternalIP (matches how VM scrapes them; avoids hostname-resolution
  gaps on the raspis).
- **HA / footprint:** single replica (Frank is a learning cluster; metrics-server is
  stateless and cheaply restarted). Default resource requests are tiny; explicitly set modest
  `resources` so it schedules on the raspis' budget too. No PVC.
- **Availability nuance to document:** the `metrics.k8s.io` APIService gates the aggregation
  layer — if metrics-server is down/crashlooping, `kubectl` calls that *touch* discovery can
  slow. Single replica is acceptable here; note it in the operating post as a known tradeoff.

## Deferred scope — VM-backed `prometheus-adapter` (future `obs` layer)

Recorded now so the boundary is explicit and the follow-up is trackable:

- **Trigger:** the first concrete custom-metric HPA (e.g. scale a worker on queue depth, an
  API on RPS, an inference path on tokens/s).
- **Shape:** deploy `prometheus-adapter` pointed at the vmsingle Prometheus-compatible query
  endpoint in ns `monitoring`; register **only** `custom.metrics.k8s.io` (+ `external` if
  needed). metrics-server keeps `metrics.k8s.io`. Author adapter `rules` against the specific
  metric(s) the HPA scales on.
- **Why not now:** no consumer exists; adapter rules can't be meaningfully written or verified
  end-to-end without a real target metric ("not Deployed until the workflow is observed").
- **Action:** open a follow-up issue ("VM-backed prometheus-adapter for custom/external Metrics
  API") and link it from this spec + #394 at close.

## Verification (end-to-end, before marking Deployed)

1. `kubectl top nodes` — 7 rows, non-empty CPU/mem for every node incl. both raspis.
2. `kubectl top pods -A` — non-empty for a sample of pods.
3. `kubectl get apiservice v1beta1.metrics.k8s.io` → `AVAILABLE=True`.
4. `kubectl -n kube-system logs deploy/metrics-server` — no `x509`/`unable to fully scrape`
   errors after warm-up.
5. **HPA smoke:** create a throwaway CPU HPA against an existing low-risk Deployment,
   confirm `kubectl get hpa` shows a real `TARGETS` percentage (not `<unknown>`), then delete
   the HPA. Do not leave it running.

## Risks / gotchas

- **Talos self-signed kubelet cert** → `--kubelet-insecure-tls` is mandatory; without it every
  scrape 500s and `top` stays empty while the pod looks Ready. (New gotcha one-liner for
  `frank-gotchas.md` if not already implied elsewhere.)
- **raspi reachability:** the chart's default `--kubelet-preferred-address-types=InternalIP,
  ExternalIP,Hostname` (InternalIP-first) already avoids the arm64 hostname-resolution edge
  case — every Frank node has a static InternalIP, so no explicit override is needed (the
  chart's `args` value appends, so re-specifying would only duplicate the flag). Verify both
  raspis actually report rows (they pass the VM label limit already, so cadvisor data exists —
  but metrics-server has its own scrape path, so prove it independently).
- **Argo health:** metrics-server's APIService can read `Degraded` transiently until the first
  scrape lands; confirm it settles `Available=True` rather than assuming Synced == working.
- **Single replica + aggregation layer:** documented tradeoff, not a blocker at Frank's scale.

## Acceptance rows (matrix)

Presented at brainstorm close (below). Origin: `derio-net/frank:docs/superpowers/specs/
2026-07-25--obs--metrics-api-server-design.md`.
