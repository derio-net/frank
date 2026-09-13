# PipelineRun Outcome Alerting (Frank)

**Layer:** obs (Frank — one VMServiceScrape under `apps/tekton/manifests/`, two Grafana rules under `apps/grafana-alerting/manifests/`)
**Status:** Draft
**Date:** 2026-09-13
**Repo:** `derio-net/frank`
**Motivated by:** [#790](https://github.com/derio-net/frank/issues/790) — `stoa-status-bridge` failed **100% of its runs for 39 days** (2026-08-02 → 2026-09-10, 298 PipelineRuns) and nothing anywhere registered it. Found by eye, from the pod count. Root cause of the bridge failure itself is fixed in #789; this spec closes the detection gap that let it run.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-09-13--obs--pipelinerun-failure-alerting | `derio-net/frank` | `2026-09-13--obs--pipelinerun-failure-alerting` | — |

## Problem

Frank alerts on whether the CI/CD *platform* is up. It does not alert on whether the CI/CD platform *works*.

`layer-25-cicd-down` asks `sum(kube_deployment_status_replicas_unavailable{namespace=~"gitea|tekton-pipelines|zot"}) > 0`. That is a correct question — and it was a deliberate improvement. The 2026-05-14 rewrite moved it off `kube_pod_status_ready` precisely because Tekton task pods report `Ready=False` by design once complete, and alerting on them produced a false-positive flood. The comment in `alert-rules-cm.yaml` records the reasoning.

But the rewrite left a hole nobody named: **a CI platform can be 100% green on "is the controller replicated?" while every pipeline it runs fails.** That is exactly what happened. Worse, the same comment describes completed task pods accumulating "until a GC sweep" — which is why 292 `Failed` corpses read as background noise rather than as signal.

### This is not a one-off

Read straight off the controller's metrics endpoint on 2026-09-13:

| pipeline | success | failed |
|---|---:|---:|
| `stoa-status-bridge` | 1727 | 3708 |
| `github-pull-sync` | 247 | 0 |
| `cnc-ci` | 2 | 0 |
| **`derio-homelab-pull-sync`** | **0** | **24** |

`derio-homelab-pull-sync` is wired to the GitHub EventListener (`apps/tekton/triggers/eventlistener-github.yaml:690`), has **never succeeded**, and has zero retained PipelineRuns. It is a live second instance of the same blind spot, sitting undetected right now. Per the brainstorm decision it stays out of scope here and gets its own issue — it becomes this rule's first real-world catch rather than a scope expansion.

### The signal was always there — it was never collected

`tekton-pipelines-controller` v1.6.0 already serves `http-metrics` on port 9090 with exactly the right series:

```
tekton_pipelines_controller_pipelinerun_duration_seconds_count{namespace,pipeline,status}   # status: success | failed
```

There is **no `VMServiceScrape` for `tekton-pipelines`**, and VMSingle answers `{__name__=~"tekton.*"}` with an empty list. So #790 is two pieces of work, not one: make the signal visible, then alert on it.

## Goals

- **Detect a pipeline that runs and never succeeds**, within hours rather than weeks, without re-opening the task-pod false-positive flood the 2026-05-14 rewrite escaped.
- **Detect a high-cadence pipeline that stops running at all** — the failure mode a ratio rule is structurally blind to.
- **Add the Tekton scrape without repeating the kube-state-metrics cardinality incident.**
- Reuse existing routing, folders and conventions; add no new service, no new datasource, no new CronJob.

## Non-goals (this iteration)

- Fixing `derio-homelab-pull-sync` (separate issue, per operator decision).
- Per-*task* failure alerting. `taskrun_duration_seconds{task,status}` exists and could be alerted on later; pipeline-level is the unit of "did CI work".
- A Grafana dashboard for Tekton. The scrape makes one possible; building it is not this change.
- Alerting on PipelineRun *duration* regressions.
- Touching `layer-25-cicd-down`. It answers a different, still-valid question and stays exactly as it is.

## Design

Three pieces: a scrape, a ratio rule, an idle dead-man. Plus guards.

### 1. Scrape — `VMServiceScrape`, with one mandatory drop

New manifest `apps/tekton/manifests/vmservicescrape-pipelines-controller.yaml`, namespace `tekton-pipelines`, owned by the **`tekton-extras`** Application (`path: apps/tekton`, `recurse: true`, `exclude: vendor/**`).

> Note the owning-app trap documented in `frank-gotchas.md`: the similarly-named `tekton-pipelines` Application serves `apps/tekton/vendor/pipelines` and will stay `Synced/Healthy` regardless of this file. Verify the sync against **`tekton-extras`**.

Selection is already permissive — verified on the live VMAgent CR: `selectAllByDefault: true` with `serviceScrapeSelector` and `serviceScrapeNamespaceSelector` both unset, so a scrape CR outside `monitoring` is picked up. `kubectl auth can-i list endpoints -n tekton-pipelines` as the vmagent ServiceAccount returns `yes`. This would nonetheless be the first VMServiceScrape outside `monitoring`; Phase 1 asserts the target actually goes `up`, rather than assuming.

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMServiceScrape
metadata:
  name: tekton-pipelines-controller
  namespace: tekton-pipelines
spec:
  selector:
    matchLabels:
      app: tekton-pipelines-controller
  endpoints:
    - port: http-metrics
      metricRelabelConfigs:
        # MANDATORY, not tidiness. See below.
        - action: drop
          source_labels: [__name__]
          regex: tekton_pipelines_controller_taskruns_pod_latency_milliseconds
```

**Why the drop is mandatory.** Of the 6,563 series on that endpoint, **5,712 (87%) are `taskruns_pod_latency_milliseconds`**, labelled by TaskRun **pod name**:

```
tekton_pipelines_controller_taskruns_pod_latency_milliseconds{namespace,pod="agentic-stoa-main-sync-2bv6k-pull-and-push-pod",task}
```

One new, permanent series per TaskRun ever reconciled, on a 1-month retention, growing with CI volume. That is the same curve that pushed kube-state-metrics to 21.6 MiB on 2026-07-27, tripped `-promscrape.maxScrapeSize`, and — because vmagent drops an oversized response **whole** — silently blinded all 25 `kube_*` references in the alert rules, including the rule meant to report a CronJob that stopped succeeding. Adding an unbounded Tekton metric on top of that is not a risk worth taking for a gauge nothing queries. Dropping it leaves ~850 bounded series.

### 2. Ratio rule — `layer-25-pipeline-failing`

Group `layer-25-pipeline-outcomes`, folder `feature-health`, `interval: 5m`.

```promql
sum by (pipeline) (
  increase(tekton_pipelines_controller_pipelinerun_duration_seconds_count{
    namespace="tekton-pipelines", status="failed"}[24h])
) >= 3
unless
sum by (pipeline) (
  increase(tekton_pipelines_controller_pipelinerun_duration_seconds_count{
    namespace="tekton-pipelines", status="success"}[24h])
) > 0
```

**`unless`, not `and ... == 0`.** For a pipeline that has never succeeded since controller start there is **no success series at all**. `failed >= 3 and success == 0` drops the entire result on the vector match and can never fire — for exactly the pipelines it exists to catch. This is the same shape as the trap already in `frank-gotchas.md`, where `metric == 0` is a *filter* rather than a comparison. `unless` is the set-difference operator and handles the absent right-hand side correctly. A guard test pins it.

**Thresholds.** `>= 3` is a noise floor separating "someone pushed a bad commit" from "this pipeline is broken". The discriminator is the **zero successes**, not the count. At measured cadence, `stoa-status-bridge` (148 runs/day) crosses 3 failures in under half an hour; `github-pull-sync` (10.4/day) takes roughly seven. Both are caught the same working day, and the alert **self-resolves on the first green run** — the `unless` clears immediately, with no dependence on the 24h window decaying. A pipeline that fails 3× and then stops running entirely decays out of the window after 24h, which is the dead-man's job and not this rule's.

**The comparison lives in the query, not in the threshold.** Grafana's server-side expressions cannot express `unless`, so refId A carries the whole filter and returns one series per *offending* pipeline (value = its failure count). B is `reduce last` (`mode: dropNN`, house style), and C is `threshold gt 0` — meaning "did A return anything at all". Moving the `>= 3` out of A and into C as `gt 2` would look like a tidy-up and would break the rule: A would then return every pipeline with zero successes including those with zero failures in the window. `relativeTimeRange.from` is set to `86400` to match the range selector, following the `tls-cert-expiry-1h` group's convention of tying the two together rather than leaving the default 600.

`for: 30m`, deliberately not `15m`: that window is reserved for DaemonSet-drain tolerance and the guard suite rejects borrowing it for general insensitivity.

Labels: `severity: warning`, `github_issue: "frank-ops#25"`. Routing follows the existing policy — the `severity=warning` route pages Telegram (`continue: true`), then the `grafana_folder="feature-health"` catch-all marks the layer-25 tile **degraded**. No bug issue: health-bridge only mints those at `severity: critical`. This matches how `layer-25-cicd-down` already behaves.

`noDataState: OK` — no completed runs at all is the dead-man's question, not this one's. `execErrState: Error`.

### 3. Idle dead-man — one rule per watched pipeline

Two rules, `layer-25-pipeline-idle-stoa-status-bridge` and `layer-25-pipeline-idle-github-pull-sync`, in the same group. Each asks the same question of one pipeline:

```promql
sum(
  increase(tekton_pipelines_controller_pipelinerun_duration_seconds_count{
    namespace="tekton-pipelines", pipeline="<name>"}[<window>])
) or vector(0)
```

Fires on `lt 1`. Note the selector carries **no `status` filter** — the question is "did this pipeline run at all", regardless of outcome. Failing runs are the ratio rule's business.

**Why one rule per pipeline, and not one rule with a regex.** The obvious shape — `sum by (pipeline) (increase(...{pipeline=~"a|b"}[24h])) or vector(0)` — is broken in a way that passes review. `vector(0)` produces a series with **no labels**, and `or` returns its right-hand side only where the left has *no matching series at all*. If `stoa-status-bridge` has a series and `github-pull-sync` does not, the left side is non-empty, the union keeps it unchanged, and the pipeline the dead-man exists to catch contributes nothing. It would be a switch that only works when **both** watched pipelines die simultaneously. Splitting per pipeline makes `sum()` (no `by`) genuinely collapse to an empty vector, which is the only condition under which the fallback engages. A guard test pins the split.

**Why `or vector(0)` at all.** `sum()` over an absent series returns an **empty vector**, not zero. Without the fallback, the one state the dead-man exists to detect produces no data, `noDataState: OK` swallows it, and the switch is silently disarmed — the same defect class as the `longhorn-manager-.*` selector that matched nothing and passed every structural assertion.

**Why `absent_over_time()` is the wrong primitive here.** It answers "was the series missing", not "did the counter move". The controller keeps emitting a pipeline's histogram on every scrape once that pipeline has run, so a pipeline that ran ten hours ago and then stopped still has a present, unchanging series — `absent_over_time` reads 0 and sees nothing. `increase()` is the question we actually mean.

**Windows are sized from measured cadence, not chosen round numbers.** Retained PipelineRuns on 2026-09-13:

| pipeline | runs/day | **max observed gap** | window | `for` | headroom |
|---|---:|---:|---:|---:|---:|
| `stoa-status-bridge` | 148.1 | **0.5h** | `[6h]` | `1h` | 12× |
| `github-pull-sync` | 10.4 | **15.7h** | `[72h]` | `2h` | 4.6× |

A single shared 24h window — the obvious first instinct — gives `stoa-status-bridge` 48× headroom and `github-pull-sync` about 1.5×, measured against a 79-hour sample that contained no quiet weekend. It would have paged on the first Sunday nobody pushed. These are push-driven pipelines; their idle tolerance is a property of each one's traffic, and cannot be one number.

**The `for` windows absorb a controller restart.** These counters are process-lifetime and reset when the controller pod restarts, so the series is briefly absent and `or vector(0)` reads 0. At 148 runs/day the first run lands within ~10 minutes, so `stoa-status-bridge` at `for: 1h` is comfortably safe. `github-pull-sync` at 10.4/day has a ~2.3h mean gap, so `for: 2h` **narrows but does not eliminate** a post-restart false positive. That is a deliberate, bounded trade: the worst case is one `severity: warning` Telegram message after a controller restart that coincides with a quiet period — roughly once a month at the observed restart rate, and only sometimes — which self-clears on the next sync. The alternative is 39 days of silence. The spec states this rather than hiding it, so a future reader meeting one such alert recognises it instead of re-deriving the cause.

Labels as for the ratio rule (`severity: warning`, `github_issue: "frank-ops#25"`). `noDataState: OK` — unreachable by construction, since `or vector(0)` guarantees a value. `execErrState: Error`.

**Why only these two pipelines.** A dead-man needs a known expected cadence. `cnc-promotion`, `site-promotion`, `cnc-ci`, `content-factory-ci`, `hum-ci`, `stoa-blog-ci` and `derio-homelab-pull-sync` are event-driven and legitimately idle for weeks — watching them would be a false-positive generator, which is how the previous attempt died.

**Why it matters separately from the ratio rule.** `frank-gotchas.md` records the site→www promotion failure of 2026-07-26: a trigger that was "live, correct and unreachable" because the per-repo Gitea webhook was never created. It produced **zero PipelineRuns**. A ratio rule sees nothing there; only a dead-man does.

### 4. Guards — `scripts/tests/test_pipelinerun_outcome_alerting.py`

The existing folder-wide guards in `test_feature_health_workload_metrics.py` already cover uid uniqueness, folder placement, severity vocabulary, explicit `noDataState`/`execErrState`, and the `frank-ops#N` label shape for `layer-*` uids. The new file guards what is specific to these rules — the three defects that would ship green:

1. The ratio rule uses `unless` and **not** `== 0` against the success series.
2. Each dead-man rule carries `or vector(0)` **and** selects exactly one pipeline by equality — never a regex over several, which would disarm the fallback.
3. The scrape carries the `taskruns_pod_latency_milliseconds` drop.
4. Neither rule references `kube_pod_status_ready` (the 2026-05-14 trap, re-asserted at this rule's own scope).
5. Every pipeline named by a dead-man rule exists in `apps/tekton/pipelines/`, so a renamed or deleted pipeline fails a PR instead of silently disarming the switch.

Points 2 and 5 are the lesson from the `cilium-.*` / `longhorn-manager-.*` selector rewrite: a selector that matches nothing returns no series, passes every structural assertion, and is a rule deleted in all but name.

## Risks and traps

| Risk | Mitigation |
|---|---|
| Scrape silently not selected (first VMServiceScrape outside `monitoring`) | Phase 1 asserts the vmagent target is `up` and the metric is queryable in VMSingle — not that the manifest synced. `selectAllByDefault: true` verified live. |
| ArgoCD reports `Synced` at a stale revision | Documented repo-wide. Assert on the artifact (`up{job=~".*tekton.*"}`, the series in VMSingle), never on sync status. |
| Checking the wrong Application | The scrape is owned by **`tekton-extras`**, not `tekton-pipelines`. Named in the plan. |
| Cardinality growth | The mandatory drop; Phase 1 records the post-drop series count as evidence. |
| Counter resets on controller restart | `increase()` handles resets. `stoa-status-bridge`'s `for: 1h` fully absorbs the post-restart gap at 148 runs/day; `github-pull-sync`'s `for: 2h` narrows but does not eliminate it — accepted and documented in §3. |
| Alert fires on a legitimately-broken-by-a-developer pipeline | Accepted. `>= 3` failures with **zero** successes in 24h is a broken pipeline, not a bad commit. |
| Grafana reads provisioning files at boot | A ConfigMap change does not reload rules. Verification restarts the Grafana pod and confirms the rules are **evaluating**, not merely present. |

## Test Plan (post-merge, operator-driven)

Per the brainstorm decision, a **synthetic always-failing PipelineRun**, because shipping an unproven alert is how the 39-day gap happened.

1. Confirm the scrape: vmagent target `up`, and `tekton_pipelines_controller_pipelinerun_duration_seconds_count` present in VMSingle with a `pipeline` label.
2. Confirm the cardinality drop: `tekton_pipelines_controller_taskruns_pod_latency_milliseconds` is **absent** from VMSingle.
3. Restart Grafana; confirm both rules appear and evaluate without `Error`.
4. Create a throwaway pipeline whose single task exits 1. Run it 3×.
5. Confirm `layer-25-pipeline-failing` fires within ~30m, reaches Telegram, and degrades the layer-25 tile.
6. Run a passing variant once; confirm the alert resolves on the first success.
7. Delete the throwaway pipeline and its runs.
8. Confirm neither `layer-25-pipeline-idle-*` rule is firing, and that each returns a **non-zero** value (a rule returning 0 while not firing would mean the threshold, not the traffic, is keeping it quiet).

## Acceptance rows

| Row | Claim |
|---|---|
| `pipelinerun-outcomes-visible` | Tekton PipelineRun outcomes are queryable in VictoriaMetrics per pipeline and status. |
| `pipeline-total-failure-alerts` | A pipeline that runs and never succeeds raises an alert that reaches the operator within hours. |
| `critical-pipeline-idle-alerts` | A high-cadence pipeline that stops running at all raises an alert, even though it produces no failures. |
