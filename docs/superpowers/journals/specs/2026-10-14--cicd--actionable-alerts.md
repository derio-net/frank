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
