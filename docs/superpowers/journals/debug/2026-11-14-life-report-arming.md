<!-- fr:journal-schema=4 -->
# Journal: 2026-11-14-life-report-arming

<!-- fr:journal kind=root-cause scope=debug id=eb2bccc7694e created=2026-11-14T18:38:47+00:00 -->
### eb2bccc7694e · root-cause · Console exports last_report=0 from boot; arming term counted it

cluster-update-fr internal/metrics: ts(zero)=0 means never sent, exported from boot; count(last_over_time(...))>0 was true for a 0 series, so time()-max became ~now (huge). Fix: only a value >0 is a report (age and arming). Live-checked in VM: report=now-3600 -> 3600, now-200000 -> 200000 (fires), 0 -> empty (NoData=OK). hop-scan rule is log-driven and its gate excludes the by-design no-kubeconfig heartbeat (live heartbeat 2026-11-14T03:17Z) so it has no such trap. Second gap: cluster-update-fr app Degraded from its 4 ExternalSecrets; ignore-healthcheck tied by test to PENDING-MANUAL-PHASE in clustergenerators.yaml.

<!-- fr:journal kind=review scope=debug id=7a62dc84b63f created=2026-11-14T18:38:49+00:00 -->
### 7a62dc84b63f · review · Review

Self-review only, no reviewer dispatched.
