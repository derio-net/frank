# Frank Gotchas — Argo Rollouts

Long-form companion to the **Argo Rollouts** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

Most of the meatier discoveries here came out of the litellm canary rehearsal on 2026-05-04 — see `building/19-progressive-delivery` (Update section) and `docs/superpowers/specs/2026-05-04--deploy--litellm-canary-metric-source-design.md`.

## Only `canary` and `blueGreen` strategies — no `recreate`

Stateful apps with RWO PVCs that need Recreate behavior must stay as plain Deployments.

## `AnalysisTemplate` has no `inconclusiveCondition` field

NaN results (0 traffic) implicitly match neither `successCondition` nor `failureCondition`, so they are automatically treated as inconclusive. Use `inconclusiveLimit` to cap retries.

## `workloadRef` scales the referenced Deployment to 0

Add `ignoreDifferences` on `spec.replicas` (`group: apps`, `kind: Deployment`) in the ArgoCD Application to prevent ArgoCD from fighting the Rollout controller.

## `workloadRef` "leaks" to a healthy-looking Helm Deployment when reconcile aborts pre-workload-phase

If the Rollout spec references a missing/unloadable traffic-router plugin, missing CRD permissions, an absent AnalysisTemplate, or anything else that aborts reconcile before the workload-management phase, the controller never invokes `workloadRef`-scaling. The Helm-managed `Deployment` therefore stays at its chart-default `replicas: N` and continues serving traffic via standard kube-proxy.

ArgoCD reports `Synced/Healthy` because the manifests apply. `kubectl get rollout` returns `Status: Progressing, Step: 0/6, Desired: 1, Current: 0` — which looks identical to the way a steady-state Rollout *also* shows "Progressing waiting for spec update to be observed", so the failure is invisible from every standard surface. The only authoritative signal is the controller pod log:

```bash
kubectl logs -n argo-rollouts deploy/argo-rollouts --tail=100 \
  | grep -iE "error|failed|plugin"
```

We discovered this on the litellm canary on 2026-05-04 after 39 days of vanilla RollingUpdates masquerading as canaries. Sanity check whenever you add a new Rollout with a `trafficRouting` plugin: confirm the corresponding entry exists in `argo-rollouts-config` ConfigMap *and* that the controller log is free of `failed to get traffic router plugin` errors.

## `workloadRef.scaleDown` defaults to `never`, NOT `onsuccess`

Without explicitly setting `scaleDown: onsuccess` (or `progressively`) on the Rollout's `workloadRef`, the Argo Rollouts controller never scales the referenced Helm-managed `Deployment` to 0 even after the Rollout reaches `Healthy`. Result: both the Rollout's own ReplicaSets *and* the Helm Deployment's pod template-hash ReplicaSet serve traffic simultaneously (e.g. 5 + 1 = 6 pods total when Rollout `replicas: 5` and chart default `replicas: 1`). Always specify `scaleDown: onsuccess` explicitly on `workloadRef`. Discovered on the litellm canary 2026-05-04, fixed in PR #214.

## `Error`-phase measurements retry at 10s, not the configured `interval`

Argo Rollouts retries `Error`-phase measurements at 10s cadence, not the AnalysisTemplate's configured `interval`. `interval: 1m` only applies to successful or failed measurements; when the metric provider returns `Error` (e.g. Prometheus query panics, network failure), Argo Rollouts re-attempts every ~10 seconds and counts each toward `consecutiveErrorLimit` (default 4). Net: a zero-data canary aborts in ~50 seconds, NOT the ~5+ minutes one would expect from `interval: 1m, count: 5`.

Caught by the data-plane observer during the 2026-05-04 canary rehearsal — runbooks that promise "5+ minutes of buffer for analysis" are wrong if the failure mode is `Error` rather than `Inconclusive`.

## AnalysisTemplate error queries must catch 4xx, not just 5xx

A query like `sum(rate(metric{status=~"5.."})) / sum(rate(metric))` will silently green-light a canary serving 100% 4xx responses (e.g. broken upstream returning 404 "no endpoints", or 429 rate-limit) because 4xx requests only increment the denominator. The canary evaluates as `0 numerator / N denominator = 0%` error rate, well under any reasonable threshold, and gets auto-promoted while completely broken to consumers.

Use `status!~"2..|3.."` (anything not 2xx success or 3xx redirect counts as a canary error) instead. Discovered during the 2026-05-04 canary rehearsal when a synthetic-traffic loop hit 0/114 success on `mistralai/mistral-small-3.1-24b-instruct:free` (upstream-broken at OpenRouter).

## Prometheus provider panics on empty result vector

Argo Rollouts Prometheus provider panics with `reflect: slice index out of range` when the query returns an empty result vector — happens on `result[0]` indexing without a bounds-check. The panic is reported as metric `phase: Error` (not `Inconclusive`), so the 10s-cadence-Error retry kicks in and the canary aborts in ~50 seconds (per the cadence gotcha above).

The query returns empty when (a) the metric exists but has no samples in the window, OR (b) the metric doesn't exist at all (typo, missing scrape config, missing exporter). Always verify the metric is being scraped *and* has recent samples before relying on it for canary gating:

```bash
kubectl exec -n monitoring deploy/victoria-metrics-grafana -- wget -qO- \
  'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack.monitoring.svc.cluster.local:8428/api/v1/series?match[]=METRIC_NAME'
```

Should return non-empty.

Also note: Prometheus provider `successCondition`/`failureCondition` use `result[0]` syntax (not `result`) for scalar query results.

## LiteLLM Prometheus is Enterprise-only — OSS image emits no `litellm_*` metrics

`litellm_request_total`, `litellm_total_tokens`, etc. don't exist on our deployment. The chart's Service has no metrics port; pods return HTTP 404 on `/metrics`. Any AnalysisTemplate referencing these metrics will see empty result vectors → Prometheus provider panics → canary aborts (per the gotcha above).

Workarounds:
- (a) JSON-log → Prometheus sidecar exporter that tails LiteLLM's stdout and emits the same metric names (~50 lines of Python with `prometheus_client`)
- (b) Cilium Hubble L7 stats (`hubble_http_responses_total{destination_workload="litellm"}` carries `destination_pod` natively for per-RS labels)
- (c) AR `web` provider against `/health/readiness` (coarsest, doesn't catch model-routing regressions)

Three-option tradeoff captured in `docs/superpowers/specs/2026-05-04--deploy--litellm-canary-metric-source-design.md`.
