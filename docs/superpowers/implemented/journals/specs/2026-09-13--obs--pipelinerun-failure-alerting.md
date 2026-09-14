# Journal: 2026-09-13--obs--pipelinerun-failure-alerting

<!-- fr:journal kind=decision scope=spec id=routing-warning-telegram created=2026-09-13T22:00:25 -->
### routing-warning-telegram · decision · Failure-ratio alert routes severity=warning: Telegram + degraded tile, no bug issue

Operator chose the posture already used by layer-25-cicd-down. severity=warning reaches Telegram via the existing severity=warning route in notification-policy-cm.yaml and marks the layer-25 tile degraded via the feature-health catch-all. It deliberately does NOT mint a frank-ops bug issue — health-bridge only does that at severity=critical (obs-digest.md, 'blindness != death'). Rejected: critical+health_bridge_only (tracker-loud, phone-silent) and bare critical (a broken PR pipeline would page).

<!-- fr:journal kind=decision scope=spec id=dead-man-two-pipelines created=2026-09-13T22:00:54 -->
### dead-man-two-pipelines · decision · Ratio rule is paired with a 24h idle dead-man on stoa-status-bridge and github-pull-sync

A ratio rule is structurally blind to a pipeline that never runs — the frank-gotchas 'live, correct and unreachable' trigger failure (site->www promotion, 2026-07-26) produced zero PipelineRuns and would not have been caught. Operator accepted a short hand-maintained list limited to the two genuinely high-cadence pipelines. Event-driven pipelines (cnc-promotion, site-promotion, cnc-ci) are legitimately idle for weeks and are deliberately excluded.

<!-- fr:journal kind=decision scope=spec id=test-plan-synthetic created=2026-09-13T22:01:26 -->
### test-plan-synthetic · decision · Post-merge verification uses a synthetic always-failing PipelineRun, not a real outage

Operator chose to prove the whole chain — scrape -> VMSingle -> query -> threshold -> routing — with a throwaway pipeline that exits 1 enough times to cross the threshold, then delete it. Rejected 'verify scrape only, wait for a real failure': shipping an unproven alert is how the 39-day gap in #790 happened in the first place.

<!-- fr:journal kind=decision scope=spec id=scope-detection-only created=2026-09-13T22:01:52 -->
### scope-detection-only · decision · derio-homelab-pull-sync stays out of scope — detection only, separate issue

Research found a live second instance of the blind spot: derio-homelab-pull-sync reads 24 failed / 0 success since controller start with zero retained runs. Operator chose to keep this run scoped to the detection gap #790 describes and file the broken pipeline separately, so it becomes the new rule's first real-world catch rather than a scope expansion.

<!-- fr:journal kind=discovery scope=spec id=metrics-not-scraped created=2026-09-13T22:06:05 -->
### metrics-not-scraped · discovery · Tekton controller metrics exist and are correct — they are simply not scraped

tekton-pipelines-controller v1.6.0 serves http-metrics on :9090 with tekton_pipelines_controller_pipelinerun_duration_seconds_count{namespace,pipeline,status}, status in {success,failed}. No VMServiceScrape exists for tekton-pipelines and VMSingle returns an empty list for {__name__=~"tekton.*"}. So #790 is two pieces of work, not one: make the signal visible, then alert on it. Verified: VMAgent has selectAllByDefault=true with no scrape selectors (all namespaces), and its ServiceAccount can list endpoints in tekton-pipelines.

<!-- fr:journal kind=discovery scope=spec id=cardinality-landmine created=2026-09-13T22:06:25 -->
### cardinality-landmine · discovery · 87% of the controller's series are unbounded per-pod — scraping naively repeats the KSM blinding

Of 6563 series on the controller endpoint, 5712 are tekton_pipelines_controller_taskruns_pod_latency_milliseconds, labelled by TaskRun POD NAME. That is one new permanent series per TaskRun ever reconciled, on a 1-month VMSingle retention, growing with CI volume — the same curve that pushed kube-state-metrics past maxScrapeSize on 2026-07-27 and silently blinded all 25 kube_* alert-rule references. The scrape MUST carry a metricRelabelConfigs drop for that metric. Dropping it leaves ~850 bounded series.

<!-- fr:journal kind=discovery scope=spec id=unless-not-equals-zero created=2026-09-13T22:06:53 -->
### unless-not-equals-zero · discovery · 'zero successes' must be written with unless, not '== 0' — the success series does not exist

For a pipeline that has never succeeded since controller start there is NO success series at all. 'failed >= N and success == 0' therefore drops the entire result on the vector match and the rule can never fire — precisely for the pipelines it exists to catch. The correct primitive is 'failed >= N unless success > 0'. Same family as the documented PromQL trap in frank-gotchas where 'metric == 0' is a FILTER, not a comparison. The idle dead-man has the mirror problem: sum() over an absent series returns empty, not 0, so it needs 'or vector(0)' or it is silently disarmed.

<!-- fr:journal kind=discovery scope=spec id=fr-acceptance-add-bug created=2026-09-13T22:14:14 -->
### fr-acceptance-add-bug · discovery · fr acceptance add (4.2.1) cannot append after a folded block scalar — rows added by hand

All three acceptance rows were rejected with 'append produced an invalid matrix, rolled back', pointing at the preceding row orch-hermes-shell-js-runtime, whose notes use a folded block scalar (notes: >-). fr appended the new row at the scalar's continuation indent rather than at the sequence indent, produced invalid YAML, and correctly rolled back. Rows were therefore hand-written at column 0 matching the file's own style, then validated: yaml.safe_load parses, ids are unique, and fr acceptance check lists all three as well-formed not-implemented rows. Worth filing upstream against super-fr.

<!-- fr:journal kind=review scope=spec id=review-or-vector-zero created=2026-09-13T22:19:08 -->
### review-or-vector-zero · review · Spec review: the shared-regex dead-man was broken — 'or vector(0)' only engages when ALL watched pipelines are absent

The first draft used one rule: sum by (pipeline) (increase(...{pipeline=~"a|b"}[24h])) or vector(0). vector(0) carries NO labels, and 'or' returns its right-hand side only where the left has no matching series at all — so with two watched pipelines, whichever one still has a series keeps the left side non-empty and the missing one contributes nothing. It would have been a dead-man that only works when both pipelines die at once. Fixed by splitting into one rule per pipeline, where sum() without 'by' genuinely collapses to empty. Guard test pins the split and forbids a multi-pipeline regex in an idle rule.

<!-- fr:journal kind=review scope=spec id=review-measured-windows created=2026-09-13T22:19:10 -->
### review-measured-windows · review · Spec review: a shared 24h dead-man window would have paged on the first quiet weekend

Measured retained PipelineRuns rather than assuming: stoa-status-bridge runs 148/day with a max observed idle gap of 0.5h; github-pull-sync runs 10.4/day with a max observed gap of 15.7h — inside a 79h sample containing no quiet weekend. A shared 24h window gives the first 48x headroom and the second ~1.5x. Windows are now per-pipeline and derived from the measurement (6h and 72h). Also corrected a stale figure carried in from the issue text: stoa-status-bridge is 148/day measured, not the 96/day 39-day average, which changed the ratio rule's stated detection latency.

<!-- fr:journal kind=review scope=spec id=review-sse-threshold-placement created=2026-09-13T22:19:13 -->
### review-sse-threshold-placement · review · Spec review: documented why the >= 3 must stay in the query and not move to the SSE threshold

Grafana SSE cannot express 'unless', so refId A carries the whole filter and C is 'gt 0' meaning 'did A return anything'. Moving the >= 3 into C as 'gt 2' reads as a tidy-up and breaks the rule — A would then return every pipeline with zero successes, including those with zero failures in the window. Written into the spec so the next reader does not re-derive it. Also pinned relativeTimeRange.from to 86400 to match the range selector, per the tls-cert-expiry-1h group's convention.
