<!-- fr:journal-schema=4 -->
# Journal: 2026-11-13-life-pre-phase7-quiet

<!-- fr:journal kind=repro scope=debug id=56f2167d8b49 created=2026-11-13T22:34:54+00:00 -->
### 56f2167d8b49 · repro · Pre-phase-7 degraded-by-design state is noisy

Live 2026-11-13: cluster-update-fr pod Init:CrashLoopBackOff (tailscale sidecar, no TS_AUTHKEY -> interactive 'tailscale up' killed after ~60s, also registers a pending node request with Headscale each restart); alerts life-report/hop-scan heartbeat-stale critical; renovate app Degraded; trivy-server-0 CreateContainerConfigError (Secret trivy-operator-trivy-config missing).
