# Spec: LiteLLM Canary Metric-Gated Promotion (Path B)

**Status:** Skeleton — pending brainstorm
**Layer:** deploy
**Filed:** 2026-05-04
**Filed by:** Terminal #1 (canary-rehearsal coordinator), with input from Terminal #2 (data-plane observer) and Terminal #3 (synthetic traffic driver)
**Related:** `docs/superpowers/archived-plans/2026-03-25--deploy--argo-rollouts.md` (original layer plan), `docs/runbooks/litellm-canary-observation.md` (operating runbook), `apps/litellm/manifests/rollout.yaml` (currently pause-only canary), `apps/litellm/manifests/analysis-template.yaml` (orphaned scaffold)

---

## Problem

The LiteLLM Argo Rollouts canary on Frank lacks a working metric source for gated promotion. The original `AnalysisTemplate` queries `litellm_request_total` from VictoriaMetrics, but **that metric does not exist on this cluster** because:

- LiteLLM's Prometheus integration is part of LiteLLM Enterprise (paid). The OSS Helm chart we deploy does not emit any `litellm_*` metrics.
- The chart's Service has no metrics port; pods return HTTP 404 on `/metrics`.
- No `ServiceMonitor` or `VMServiceScrape` was ever added for LiteLLM.

The defect was latent for 39 days because the canary itself was stuck on a separate broken plumbing (the never-published Cilium traffic-router plugin — see `building/19-progressive-delivery` postmortem). It surfaced on 2026-05-04 during the first end-to-end rehearsal: with no metric series, the AnalysisRun's query returned an empty vector, the Argo Rollouts Prometheus provider panicked with `reflect: slice index out of range` on `result[0]`, hit `consecutiveErrorLimit: 4`, and the controller correctly failed closed — aborted the canary, scaled stable back to 5/5.

As of 2026-05-04, the LiteLLM canary in `apps/litellm/manifests/rollout.yaml` is **pause-only** (no analysis gating). Operator promotes manually at each step. This works for a homelab where the operator is also the user, but loses the value proposition of metric-gated progressive delivery.

This spec captures the design space for restoring metric-gated promotion, with three concrete candidate signal sources that don't require LiteLLM Enterprise.

---

## Goals

1. **A working `litellm_request_total` (or equivalent) metric in VictoriaMetrics**, scraped from a non-Enterprise source.
2. **Per-pod / per-ReplicaSet labelling** on the metric, so the AnalysisTemplate query can filter to the canary RS only — sidesteps the dilution problem in the current "union-of-stable+canary" aggregation (a 100%-broken canary at 20% weight only contributes 20% of total to a union error rate, which is exactly at the 5% threshold's noise floor for marginal regressions).
3. **Failure-mode coverage** that catches the 4xx silent-pass risk (already addressed in PR #216 by switching the query from `status=~"5.."` to `status!~"2..|3.."`, but moot until the metric exists).
4. **Operating-runbook viability** — the new signal source must be inspectable from `kubectl exec` / `wget` for a human debugging "why did this canary abort?" without needing Grafana access.

## Non-goals

- Replacing Argo Rollouts itself.
- Adding LiteLLM Enterprise to the cluster (out of scope; cost/value mismatch for a homelab).
- Re-architecting LiteLLM's exposure pattern (raw Cilium L2 LB at `192.168.55.206:4000` + Traefik IngressRoute `litellm.cluster.derio.net` stays).

---

## Candidate signal sources

### Option 1 — Cilium Hubble L7 stats (Terminal #3's preferred)

**Idea:** Use `hubble_http_responses_total{destination_workload="litellm", destination_pod=~"litellm-<canary-hash>-.*"}` from the Hubble metrics endpoint already running on this cluster.

**Pros:**
- Zero app-side changes. LiteLLM stays exactly as-is.
- Per-pod labelling is free. Hubble carries `destination_pod` natively.
- Catches things app-side metrics can't: connection-level RST, 502 from a sidecar/proxy, kube-proxy mis-routing.
- Hubble metrics are already scraped on Frank.

**Cons:**
- Requires Hubble L7 visibility to be enabled cluster-wide for the LiteLLM namespace (currently L4 only by default; check `apps/cilium/values.yaml`).
- Granularity is HTTP request — no per-model bucketing (would need URL-path inspection or LiteLLM-specific request attributes Hubble doesn't see).
- Cardinality: per-pod × per-status-code × per-source-app explosion if not labelled-down at scrape time.

**Open questions:**
- What's the cardinality cost of enabling L7 visibility for the LiteLLM namespace?
- Does Hubble's `destination_pod` label survive the canary-pod hash being a moving target across rollouts?
- How does the AnalysisTemplate query reference the canary RS hash (which only Argo Rollouts knows)? Likely needs a templating layer or `metricArgs` from the Rollout spec.

### Option 2 — JSON-log → Prometheus sidecar exporter (Terminal #3's "cheap and concrete")

**Idea:** ~50-line Python sidecar in each LiteLLM pod that tails LiteLLM's JSON access logs from a shared `emptyDir`, parses `request_completed` events, emits `litellm_request_total{model, status, api_user}` as a Prometheus counter on `:9090`. ServiceMonitor scrapes it.

Sketch (from Terminal #3's note in `docs/agentic-discussion/terminal-3.md`):
```python
import json, sys
from prometheus_client import Counter, start_http_server

req = Counter("litellm_request_total", "Requests",
              ["model", "status", "api_user"])
start_http_server(9090)
for line in sys.stdin:
    try:
        e = json.loads(line)
        if e.get("event") == "request_completed":
            req.labels(e["model"], str(e["status_code"]),
                       e.get("api_user", "anon")).inc()
    except (ValueError, KeyError): pass
```

**Pros:**
- Carries the *exact* metric name our existing `AnalysisTemplate` references — once deployed, AnalysisTemplate query is unchanged.
- Per-pod by construction (each sidecar emits its own pod's traffic).
- Per-model labelling is free (closes Terminal #3's "single-model probing has a blind spot" concern).
- No upstream license cost.

**Cons:**
- New code to maintain (sidecar image needs a CI pipeline).
- Requires LiteLLM JSON logging to be configured (env var `LITELLM_LOG=JSON` or similar — needs verification).
- Sidecar fails → metrics gap. Need a probe story.
- Adds a sidecar to every LiteLLM pod (5 of them) — cumulative resource cost.

**Open questions:**
- Does LiteLLM OSS's structured-log output actually carry `model`, `status_code`, `api_user` reliably for every request? Need to capture a sample.
- Where does the sidecar image live? `agent-images` repo, or new `derio-net/litellm-metrics-exporter`?
- How is the sidecar wired into the Helm chart's pod template — fork the chart, or override via `extraContainers`?

### Option 3 — Argo Rollouts `web` provider against `/health/readiness` (cheapest, coarsest)

**Idea:** Drop the Prometheus provider entirely. AnalysisTemplate uses AR's `web` provider to GET each canary pod's `/health/readiness` (which is a real LiteLLM endpoint, returns 200 when the proxy is up). Treat consecutive 5xx or non-200 as failure.

**Pros:**
- Zero new infrastructure. AR ships with `web` provider out of the box.
- Cheap to implement (~10 min PR).
- Catches the "pod is up and the proxy responds" failure mode — which is at least *something* gated.

**Cons:**
- Coarsest signal. Doesn't catch per-route degradations (e.g. mistral-small upstream-flap), per-model 4xx spikes, latency regressions, or anything that happens *after* the readiness probe.
- Health-probe failures already gate readiness at the kubelet level. Adding a probe-based AR is largely redundant with what the kubelet does — we'd just be making the same signal "manual-promotion-blocking" instead of just "pod-removed-from-Service-endpoints."

**Open questions:**
- Is there any non-trivial signal `/health/readiness` catches that the kubelet's existing readinessProbe doesn't already act on?
- Can AR `web` provider hit per-pod URLs (vs Service URLs)? Per-pod is needed for canary-vs-stable distinction.

---

## Decision criteria

In rough priority order:

1. **Does it catch the failure modes we discovered on 2026-05-04?** Specifically: (a) the empty-vector / NaN trap in the current Prometheus path, (b) the silent-4xx-pass risk PR #216 closed, (c) per-model degradation hidden by aggregate metrics.
2. **Per-RS / per-pod labelling — yes/no.** Without it, dilution makes the threshold meaningless at low canary weights.
3. **Operating cost** — new code? new image? new sidecar? new license?
4. **Inspectability without Grafana** — can a human curl/exec to debug "why did this canary abort?"
5. **Compatibility with the existing `AnalysisTemplate` shape** — minimises blast radius of the change.

| Criterion | Hubble L7 | Sidecar exporter | Web provider |
|---|---|---|---|
| Catches 2026-05-04 failure modes | ✅ all | ✅ all | ⚠️ partial (only pod-up) |
| Per-pod labelling | ✅ free | ✅ by construction | ⚠️ manual URL-per-pod |
| New code/image | ❌ none | ✅ ~50 LOC + image | ❌ none |
| New scrape config | ✅ already scraped | ✅ ServiceMonitor | ❌ none |
| Inspectable via curl | ⚠️ requires Hubble Relay access | ✅ `wget pod:9090/metrics` | ✅ `wget pod:4000/health/readiness` |
| Reuses existing `AnalysisTemplate` | ❌ different query, different metric name | ✅ literally unchanged | ❌ different provider entirely |
| Operating cost | low (config only) | medium (new image, sidecar in every pod) | very low (config only) |

---

## Tentative recommendation (for the brainstorm to confirm or push back)

**Hybrid: Sidecar exporter (Option 2) + Hubble L7 (Option 1) as a defence-in-depth pair.**

- **Sidecar exporter as the primary AR signal** — carries the exact metric name our existing `AnalysisTemplate` references, per-pod by construction, per-model labelling closes Terminal #3's blind-spot concern. Cheapest to wire into AR.
- **Hubble L7 as the secondary signal** for things app-side metrics can't see (kube-proxy mis-routing, RSTs, 502 from anything between the pod and the LB). Could be a separate AR step, or just a Grafana alert that pages the operator out-of-band.
- **Web provider rejected** — too coarse, redundant with the kubelet's readiness gating.

Pure Option 1 vs pure Option 2 trade-off: Option 2 carries more surface area (image to maintain, sidecar in every pod) but reuses the existing `AnalysisTemplate` and gives per-model labels. Option 1 is zero app-side change but requires per-canary-RS templating in the AR query and doesn't see model-level failures. The hybrid uses each for what it's best at.

---

## Adjacent improvements to fold in (out of scope for the metric-source decision proper, but logged here so they don't get lost)

- **`lifecycle.preStop` hook on canary pods** that `tar`s `/var/log` to a known PVC mount before scale-down — captures canary pod logs at the exact moment we need them most (post-abort), which is the exact moment they vanish today. Suggested by Terminal #2. Cheap, idempotent, doesn't touch the chart.
- **Migration Job nodeSelector** — pin the LiteLLM `litellm-migrations` PreSync hook to amd64 so it doesn't land on raspi-1 and pay a 4-minute cold-pull tax on a 714 MB ARM image per canary. Suggested by Terminal #2.
- **Synthetic-traffic-driver split** — the role Terminal #3 played today (1 req/sec curl loop) doesn't need an LLM. Convert to a Tekton task with a Telegram webhook on non-200, free the agent slot for narrative observation. Suggested by Terminal #3.
- **Multi-model traffic loop** — synthetic traffic should rotate through *all* important model classes, not pick one. Today Terminal #3 picked qwen3.5 (all-200) which would have *masked* a per-route degradation in mistral-small if the canary had been gating on it. Suggested by Terminal #3.
- **PR #215's date-coded synthetic-trigger env var → counter or nonce** — `CANARY_REHEARSAL_2026_05_04: "1"` doesn't differentiate same-day repeats. Recommend `CANARY_REHEARSAL_NONCE: "<uuid>"` or `CANARY_REHEARSAL_COUNT: "<int>"`. Suggested by Terminal #3.
- **Pre-merge query smoke test** — Tekton task that runs proposed AR queries against live VM with a healthy time window and asserts non-empty result. Would have caught Bug #5 at PR #216 review time. Suggested by Terminal #3.

---

## Open questions for the brainstorm

1. Hybrid (Hubble + sidecar exporter) vs pure-sidecar-exporter — is the defence-in-depth worth the extra moving piece?
2. If sidecar-exporter is chosen: where does the sidecar image live (which repo, which CI), and how does it get into the LiteLLM Helm chart's pod template (chart fork, override, or admission webhook)?
3. If Hubble is in the picture: what's the cardinality cost of enabling L7 visibility on the litellm namespace, and what scrape-time labelling do we need to keep series count sane?
4. Should this layer also pick up the adjacent improvements above, or split them off into separate plans?

---

## Implementation phases (sketch, for whoever picks this up)

- **Phase 1 — confirm signal source.** Manually run the chosen approach against the live cluster (e.g., shell into a LiteLLM pod, configure JSON logging, pipe to a local exporter, verify metric shape). Capture the time-series and decide whether the per-pod / per-model resolution is what we expected.
- **Phase 2 — wire it into the chart.** Image, sidecar config, ServiceMonitor / VMServiceScrape, RBAC if needed.
- **Phase 3 — re-introduce `analysis: { templates: ... }` to the canary.** Update `apps/litellm/manifests/rollout.yaml` to put an analysis step back between each `setWeight` and the next `pause`. Update or replace the existing `apps/litellm/manifests/analysis-template.yaml` with the new query.
- **Phase 4 — third end-to-end rehearsal.** Synthetic env-var trigger, three-terminal observation, capture real metric-gated outputs. Compare to PR 1.5/1.6's pause-only outputs. Update the operating runbook to document the metric-gated path as the canonical operation.

---

*This skeleton is intentionally opinionated to give the brainstorm a starting point. Push back hard, especially on the hybrid recommendation — the "use both" instinct is often wrong when one of them does 80% of the job for half the cost.*
