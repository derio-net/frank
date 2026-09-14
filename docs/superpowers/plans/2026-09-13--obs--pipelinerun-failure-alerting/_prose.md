# PipelineRun Outcome Alerting — implementation plan

**Spec:** `docs/superpowers/specs/2026-09-13--obs--pipelinerun-failure-alerting-design.md`
**Issue:** [#790](https://github.com/derio-net/frank/issues/790)

## What this closes

`stoa-status-bridge` failed 100% of its runs for 39 days and nothing registered it — not an
alert, not a tile, not an issue. It was found by eye, from the pod count. The bridge bug itself
is fixed in #789; this plan closes the detection gap that let it run.

Frank alerts on whether the CI/CD *platform* is up (`layer-25-cicd-down`, Deployment
replication in `gitea|tekton-pipelines|zot`). Nothing asks whether the pipelines it runs
actually succeed. A CI platform can be fully green on the first question while failing the
second, indefinitely.

## Shape of the work

Two halves, and the first is easy to miss: **the signal already exists and is simply not
collected.** `tekton-pipelines-controller` v1.6.0 serves per-pipeline outcome counters on
`:9090`; there is no `VMServiceScrape` for `tekton-pipelines`; VMSingle answers
`{__name__=~"tekton.*"}` with an empty list.

So: phase 1 makes the signal visible, phases 2–3 alert on it, phase 4 ties the halves together
and writes down what was learned, phase 5 proves it on the cluster.

## Why the phases are ordered this way

**Phase 1 is the walking skeleton** because the scrape is the load-bearing unknown. It is the
first `VMServiceScrape` in this repo outside the `monitoring` namespace, and if VMAgent does not
select it, every rule in phases 2–3 is decoration. It also carries the cardinality drop, which
must exist from the first sync rather than be added later: 87.1% of the controller's series are
`taskruns_pod_latency_milliseconds`, labelled by TaskRun pod name, and a month of retention on
that would repeat the kube-state-metrics blinding of 2026-07-27 — with the twist that a *fix*
does not un-store what was already ingested.

**Phase 2 before phase 3** because the ratio rule establishes the group, the routing, and the
test helpers the dead-man rules reuse. Phase 3 depends on phase 2 for those helpers, not merely
for ordering.

**Phase 4 exists because the two halves can silently disagree.** A rule querying a metric the
scrape drops is a rule that can never fire, and no other test in the repo would notice. That
cross-check only works because both halves are in git.

**Phase 5 is manual and back-loaded.** Everything it does needs the cluster — an ArgoCD sync, a
Grafana restart, a synthetic failing PipelineRun. No agentic phase depends on it, so the PR
ships with it unimplemented and the operator drives it after merge.

## Testing posture

Every agentic test runs **offline**. `.github/workflows/repo-tripwires.yml` gates every PR and
states "Nothing in this suite talks to Frank or Hop — by design"; a test needing a cluster would
break the repo. The evidence is committed instead: two fixtures under
`scripts/tests/fixtures/tekton/`, captured from the live controller on 2026-09-13 — a verbatim
metrics sample and a census of true per-metric series counts.

The census is not decoration. It lets the cardinality test say *"the manifest drops whichever
metric the measured data shows is unbounded"* rather than *"the manifest mentions a string
someone typed"*, so re-capturing after a Tekton upgrade re-checks the premise instead of
preserving a stale one.

## The three PromQL traps this plan is built around

Each is a rule that looks right, passes structural review, and does nothing.

1. **`unless`, not `and ... == 0`.** For a pipeline that has never succeeded there is *no
   success series*. `failed >= 3 and success == 0` drops the whole result on the vector match —
   for exactly the pipelines the rule exists to catch.

2. **`or vector(0)` is useless under `sum by (pipeline)`.** `vector(0)` carries no labels, and
   `or` returns its right side only where the left has *no* matching series at all. One rule
   watching two pipelines would only fire if both died at once. Hence one rule per pipeline.

3. **`absent_over_time()` is the wrong question.** The controller keeps emitting a pipeline's
   histogram once it has run, so a pipeline that stopped ten hours ago still has a present,
   unchanging series. `increase()` is what "did it run" actually means.

## Where the numbers come from

Dead-man windows are sized from measured cadence, not chosen:

| pipeline | runs/day | max observed idle gap | window | `for` |
|---|---:|---:|---:|---:|
| `stoa-status-bridge` | 148.1 | 0.5h | `[6h]` | `1h` |
| `github-pull-sync` | 10.4 | 15.7h | `[72h]` | `2h` |

A single shared 24h window — the obvious first instinct, and what the first draft had — gives
the first 48× headroom and the second about 1.5×, against a 79-hour sample containing no quiet
weekend. It would have paged on the first Sunday nobody pushed.

## Known and accepted

`github-pull-sync`'s `for: 2h` narrows but does not eliminate a false positive after a
controller restart that coincides with a quiet period. Worst case is one warning-severity
Telegram message that self-clears on the next sync, at an observed restart rate of roughly once
a month. The alternative was 39 days of silence. It is written into the rule's comment so
whoever meets one recognises it.

## Out of scope

`derio-homelab-pull-sync` is failing 100% right now — 24 failed, 0 success, zero retained runs —
a live second instance of this exact blind spot, found while researching the spec. By operator
decision it gets its own issue and becomes this rule's first real-world catch, rather than
widening this PR into an unrelated root cause.
