<!-- fr:journal-schema=2 -->
# Journal: 2026-10-14--cicd--actionable-alerts

<!-- fr:journal kind=discovery scope=spec id=operator-brief created=2026-10-14T17:29:35+00:00 input=true -->
### operator-brief · discovery · Operator brief

yes but when nothing happens to be needing CI, it's just noise. I would prefer my notifications to mean that something is actually wrong. What can be done?

I don't want another issue that I might forget to run. Now it's the time to implement it. If we need a normal fr-goal so be it.

<!-- fr:journal kind=decision scope=spec id=real-work-checks created=2026-10-14T17:29:35+00:00 decided_by=operator -->
### real-work-checks · decision · Implement real-work delivery checks now

Operator chose Real-work checks (Recommended): replace both idle alerts, check overdue mirror refs and missing/stale forwarded statuses, and monitor the checker. No follow-up issue for delivery detection. One agentic phase covers this single coherent alerting change.

<!-- fr:journal kind=decision scope=spec id=verification-policy created=2026-10-14T17:29:35+00:00 decided_by=operator -->
### verification-policy · decision · Behavioural tests and live reads; DevOps close-out

Operator chose Tests + live reads (Recommended). Offline behavioural tests and authenticated read-only forge probes before merge where credentials permit; deployment, scrape and Grafana rule deletion verified in this run's post-merge DevOps-gated close-out.

<!-- fr:journal kind=review scope=spec id=spec-plan-review created=2026-10-14T17:33:46+00:00 -->
### spec-plan-review · review · Independent spec and plan review passed

fr-spec-reviewer-hard reviewed both artifacts in a separate context and found no
correctness or completeness findings. Verified real-work and verification decisions
in docs/superpowers/journals/specs/2026-10-14--cicd--actionable-alerts.md:11,16;
mirror coverage/schedule in apps/tekton/manifests/mirror-reconcile.yaml:322,358;
source-ref routing in apps/tekton/triggers/eventlistener-github.yaml:133,197;
status mapping in apps/tekton/triggers/eventlistener.yaml:74,87 and
apps/tekton/pipelines/stoa-status-bridge.yaml:45; existing Secret contracts in
apps/tekton/manifests/externalsecret-stoa-github-mirror.yaml:14,
externalsecret-derio-homelab-github-mirror.yaml:19, externalsecret-gitea-token.yaml:12;
Pushgateway Service/scrape and Layer 25 rule group/idle UIDs; application recursive
source ownership. Plan is exactly one agentic phase with linked acceptance rows and
red/green/refactor sequencing. Live authenticated Gitea probes remain owed.

<!-- fr:journal kind=decision scope=spec id=exit-baseline created=2026-10-14T17:33:47+00:00 -->
### exit-baseline · decision · exit when spec-review resolved

The exit when spec-review resolved; `fr verification set` and `deliver` compare against it.

```yaml
row_gates:
  ci-delivery-checker-visible: devops
  ci-quiet-no-idle-alert: devops
  ci-real-work-delivery: devops
row_kinds:
  ci-delivery-checker-visible: live
  ci-quiet-no-idle-alert: live
  ci-real-work-delivery: live
run_gate: devops
run_kind: live
```

<!-- fr:journal kind=discovery scope=spec id=test-plan-step-1 created=2026-10-14T19:39:33+00:00 -->
### test-plan-step-1 · discovery · Test Plan step 1: ran

Step: Ensure tekton-extras and grafana-alerting actually applied the merge revision; assert the live CronJob/script content, not merely ArgoCD Synced status.

Evidence: 2026-10-14: PR869 merge 5ac6e0b verified. tekton-extras initially stale and CronJob absent; explicit HEAD sync succeeded. Live CronJob schedule */5, mounted existing Secrets, non-root and deadline match merged manifest. Live script SHA256 6ab62a1e240cd4a1056cb431c339482dbc6b17c441fea19f12a07fc2df7626fc and Grafana CM SHA256 64fa6515ac843b7ccd36909545381380897045e1ab2c7c62556aaf21565d3d3b equal merged artifacts.

<!-- fr:journal kind=discovery scope=spec id=test-plan-step-2 created=2026-10-14T19:42:00+00:00 -->
### test-plan-step-2 · discovery · Test Plan step 2: ran

Step: Load the Grafana provisioning changes using the documented restart/reload procedure. Assert both idle UIDs are absent through Grafana's API and all existing CI fault rules plus the three new delivery rules exist.

Evidence: 2026-10-14: operator-authorized Grafana deployment restart completed. Authenticated provisioning API: both idle UIDs absent; all nine expected Layer25 rules present (six fault rules and three delivery rules); 60 total stored rules. See docs/investigations/2026-10-14--cicd--delivery-url-closeout.md.

<!-- fr:journal kind=discovery scope=spec id=test-plan-step-3 created=2026-10-14T19:42:03+00:00 -->
### test-plan-step-3 · discovery · Test Plan step 3: ran

Step: Observe a scheduled checker run using existing Secret mounts, verify no credential-bearing logs, and query the scraped timestamp/count/error gauges. Inspect any positive findings against the source/destination APIs.

Evidence: Scheduled 19:25 and 19:30 Jobs succeeded with existing Secret mounts. No mounted token values in latest logs. Grafana datasource proxy returned 37 scraped gauges, timestamp age 249s, all read errors and mirror overdue counts zero. All 22 positive status findings independently checked against authenticated forge APIs: matching state/description, equivalent relative/absolute URLs; false positives tracked by frank#870. See investigation.

<!-- fr:journal kind=owed scope=spec id=test-plan-step-4 created=2026-10-14T19:42:06+00:00 -->
### test-plan-step-4 · owed · Test Plan step 4 owed

what: Confirm healthy quiet refs/statuses yield zero overdue counts. Use the offline failure fixtures for deliberate missing/read-error/recovery cases; do not break live webhooks for verification. Record evidence on the linked acceptance rows and clear the DevOps gate only when deployment is verified.
why: 79 offline checker/outcome tests pass, and quiet repos have zero counts, but 22 healthy delivered statuses warn due to relative Gitea vs absolute GitHub target URLs. frank#870 must be fixed, deployed and re-walked before clearing DevOps gate or archiving. Read-only URL-resolution probe yielded zero counts for all 12 repos; no live forge writes.
how: fr journal resolve --scope spec --slug 2026-10-14--cicd--actionable-alerts --id test-plan-step-4 --state fixed --note "<evidence>"
owed_key: spec:2026-10-14--cicd--actionable-alerts#step4

<!-- fr:journal kind=finding scope=spec id=test-plan-step-4-resolved created=2026-10-14T20:25:08+00:00 state=fixed resolves=test-plan-step-4 -->
### test-plan-step-4-resolved · finding [fixed] · resolves test-plan-step-4: Test Plan step 4 owed

2026-10-14 live recovery verified after PR872 d3574040 exact-revision sync. Live script SHA256 5c8d65f39cbfd6a7a723c81fba7df98bd7a183091c88d77c5491c6ac34a1b8fa matches fix. Scheduled 20:20 Job succeeded; all 24 overdue and 12 read-error gauges zero, fresh timestamp, empty credential-free logs. Grafana delivery-overdue recovered; all three delivery rules inactive/healthy at 20:23:30Z. All nine CI rules retained, idle UIDs absent. 94 offline missing/read-error/recovery and URL regression tests passed. Passing ci-real-work-delivery walk recorded. See investigation recovery section.
