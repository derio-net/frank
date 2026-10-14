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
