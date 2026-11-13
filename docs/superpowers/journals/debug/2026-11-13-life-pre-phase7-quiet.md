<!-- fr:journal-schema=4 -->
# Journal: 2026-11-13-life-pre-phase7-quiet

<!-- fr:journal kind=repro scope=debug id=56f2167d8b49 created=2026-11-13T22:34:54+00:00 -->
### 56f2167d8b49 · repro · Pre-phase-7 degraded-by-design state is noisy

Live 2026-11-13: cluster-update-fr pod Init:CrashLoopBackOff (tailscale sidecar, no TS_AUTHKEY -> interactive 'tailscale up' killed after ~60s, also registers a pending node request with Headscale each restart); alerts life-report/hop-scan heartbeat-stale critical; renovate app Degraded; trivy-server-0 CreateContainerConfigError (Secret trivy-operator-trivy-config missing).

<!-- fr:journal kind=root-cause scope=debug id=754249d82342 created=2026-11-13T22:34:57+00:00 -->
### 754249d82342 · root-cause · Four independent causes

1) containerboot with empty TS_AUTHKEY falls into interactive login and exits (same container shape in hop-scan CronJob). 2) heartbeat rules treat 'never reported' as 'went stale'. 3) renovate Degraded is the ExternalSecret renovate-github-token (SecretSyncedError: PEM Secret + placeholder appID), NOT the suspended CronJob - ArgoCD's ExternalSecret health. 4) trivy: hand-made token Secret never created; it is not a session credential so it can be generated now.

<!-- fr:journal kind=hypothesis scope=debug id=e89573635095 created=2026-11-13T22:34:59+00:00 -->
### e89573635095 · hypothesis · Renovate Degraded is caused by suspend:true

Brief's hypothesis. Ruled out: CronJob suspend has no health impact; resources list shows the ES Ready=False reason SecretSyncedError (message 'could not get secret data from provider') and ESO logs error on the renovate ExternalSecret.

<!-- fr:journal kind=finding scope=debug id=8e40b5e79695 created=2026-11-13T23:10:18+00:00 state=fixed -->
### 8e40b5e79695 · finding [fixed] · Quiet pre-phase-7 state, armed by the phase-7 inputs

Sidecar waits on an OPTIONAL secret volume (env cannot see a later Secret; proven by test_a_key_that_appears_later... and in the real tailscale image); session shape/admission/golden untouched. Heartbeat rules armed by first report / first configured heartbeat; unhealthy ignores only 'no hop-readonly-kubeconfig'. Renovate ES ignore-healthcheck tied to suspend:true by test. Trivy token: scripts/trivy-token/bootstrap.sh + manual-op life-trivy-token (operator runs). Full suite: 2193 passed.
