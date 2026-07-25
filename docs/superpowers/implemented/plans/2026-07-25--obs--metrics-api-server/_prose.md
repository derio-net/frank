# Metrics API on Frank — serve `metrics.k8s.io` (metrics-server)

**Spec:** `docs/superpowers/specs/2026-07-25--obs--metrics-api-server-design.md`
**Layer:** obs · **Issue:** #394

## What this plan does

Deploy the upstream `metrics-server` as a new ArgoCD App-of-Apps application so
Frank serves the aggregated resource Metrics API (`metrics.k8s.io`). This
restores `kubectl top nodes` / `kubectl top pods` and unblocks CPU/memory
HorizontalPodAutoscalers — both dead today because nothing is registered for
`v1beta1.metrics.k8s.io`.

The brainstorm settled the #394 design fork: **metrics-server now** (resource
API only), **VM-backed prometheus-adapter deferred** to a future obs layer
triggered by the first concrete custom-metric HPA. metrics-server serves ONLY
`metrics.k8s.io`; it and a later adapter coexist as independent aggregated
`APIService` registrations, so nothing here forecloses the custom/external path.

## Why metrics-server (not routing resource metrics through VictoriaMetrics)

The resource API is a solved, near-real-time problem. Routing every CPU/mem HPA
tick and `kubectl top` through the general-purpose vmsingle TSDB buys latency
and config fragility for the case Frank will hit first (plain CPU/mem HPA), with
a custom/external consumer count of zero today. metrics-server keeps a purpose-
built 15s in-memory window and its own cheap kubelet scrape (~KB/node/15s,
negligible at 7 nodes). See the spec for the full costed fork.

## Talos specifics (load-bearing)

- **`--kubelet-insecure-tls` is mandatory.** Talos kubelets present self-signed
  serving certs not signed by the cluster CA; without this flag every scrape
  fails `x509: certificate signed by unknown authority` and `top` stays empty
  while the pod looks Ready.
- **No `--kubelet-preferred-address-types` override needed.** The chart default
  is already `InternalIP,ExternalIP,Hostname` (InternalIP-first); Frank's nodes
  all have static InternalIPs, so kubelets resolve by IP and never hit the arm64
  raspi hostname-resolution fallback. The chart's `args` value *appends*, so
  re-specifying the flag would only duplicate it (review Finding 1).

## Phase map

1. **Author + validate the metrics-server ArgoCD app** (agentic) — `apps/
   metrics-server/values.yaml` + `apps/root/templates/metrics-server.yaml`
   (multi-source: upstream chart + `$values`), destination ns `kube-system`,
   plus the Talos gotcha one-liner. Local validation only.
2. **Deploy + verify end-to-end** (manual) — post-merge ArgoCD sync; prove
   `kubectl top nodes` on all 7 nodes, `top pods -A`, `APIService Available=True`,
   no `x509` in logs, and a throwaway CPU HPA showing a real `TARGETS` % (then
   deleted). Flip the two acceptance rows.
3. **Post-Deploy Checklist** (manual) — building + operating blog posts, README,
   plan status. External-exposure step skipped (internal control-plane API, no
   ingress / homepage tile).

## Verification is the deploy gate

"Not Deployed until the workflow is observed end-to-end." ArgoCD Synced/Healthy
proves the artifacts exist; only `kubectl top` returning real numbers on every
node and a live HPA `TARGETS` percentage prove the capability. Phase 2 owns that
proof.
