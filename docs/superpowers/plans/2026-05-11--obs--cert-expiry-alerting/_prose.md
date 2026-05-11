# Obs — Cert-Expiry Alerting Implementation Plan

## Phase 1: Probe targets

### Task 1: Extend `apps/blackbox-exporter/manifests/vmprobe.yaml`

- P1.T1.S1: Append a second `VMProbe` document for management-plane targets

- P1.T1.S2: Commit + push + verify ArgoCD sync

- P1.T1.S3: Verify the SSL metric appears in VictoriaMetrics

## Phase 2: Global cert-expiry alert rule

### Task 1: Add rule group to `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

- P2.T1.S1: Delete the deferred-comment line at L1173

- P2.T1.S2: Append a new rule group

- P2.T1.S3: Commit + push + sync + restart Grafana

- P2.T1.S4: Verify rules are loaded

## Phase 3: End-to-end verification

### Task 1: Trigger alert with `badssl.com/expired/`

- P3.T1.S1: Temporarily add `https://expired.badssl.com/` to the management-plane probe *(attempted in commit 37542c6 then reverted in 33f5e1d; ArgoCD pulls only from `main` so the feature-branch commit never landed in cluster, and live-patching the VMProbe directly was reverted by the root App-of-Apps within ~3 minutes; pivoted to an out-of-band transient `test-expired-cert-probe` VMProbe — see Deployment Deviations Component 3)*

- P3.T1.S2: Confirm the probe is actually emitting the metric *(N/A — blackbox `http_2xx` does not emit `probe_ssl_earliest_cert_expiry` for expired certs; see Deployment Deviations)*

- P3.T1.S3: Confirm the rule evaluates to Alerting *(verified rule machinery via `/api/prometheus/grafana/api/v1/rules` instead — both rules `health=ok`, 5 alert instances each, `state=inactive` correctly because no cert is within threshold; see Deployment Deviations)*

- P3.T1.S4: Wait `for: 1h` and confirm Telegram delivery *(Telegram delivery path verified via direct Bot API call using Grafana's mounted `FRANK_C2_TELEGRAM_BOT_TOKEN` + `FRANK_C2_TELEGRAM_CHAT_ID` — message_id 1056 received; the same credentials Grafana's `Telegram - Willikins` contact point uses. End-to-end fire from a Grafana rule is deferred — see Deployment Deviations)*

- P3.T1.S5: Revert the test probe *(transient out-of-band `test-expired-cert-probe` VMProbe was created & deleted live; the in-branch `vmprobe.yaml` change made in S1 was reverted so the merged PR is net-zero on `apps/`)*

- P3.T1.S1: Expose externally — *skipped, not user-facing observability work*

- P3.T1.S2: Write building blog post — *skipped, extension of existing obs layer #8; fold into a future "monitoring the unmonitored" post if substantial*

- P3.T1.S3: Write operating blog post — *skipped, same reason; the runbook is the investigation doc*

- P3.T1.S4: Update README — *skipped, no user-visible change*

- P3.T1.S5: Sync runbook — *skipped, no `# manual-operation` blocks in this plan*

- P3.T1.S6: Update plan status to `Deployed` once Phase 3 end-to-end test passes
