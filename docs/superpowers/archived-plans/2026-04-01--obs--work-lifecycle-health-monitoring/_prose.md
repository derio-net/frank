# Work Lifecycle Tracking — M2: Health Monitoring Infrastructure (Frank)

## Phase 1: Work Lifecycle Tracking — M2: Health Monitoring Infrastructure (Frank)

### Task 1: Deploy Blackbox Exporter

- P1.T1.S1: Create Blackbox Exporter ConfigMap

- P1.T1.S2: Create Blackbox Exporter Deployment + Service

- P1.T1.S3: Apply and verify

- P1.T1.S4: Configure VictoriaMetrics to scrape probes

- P1.T1.S5: Test a probe

- P1.T1.S6: Commit

### Task 2: Deploy Pushgateway

- P1.T2.S1: Create Pushgateway Deployment + Service

- P1.T2.S2: Apply and verify

- P1.T2.S3: Configure VictoriaMetrics to scrape Pushgateway

- P1.T2.S4: Verify end-to-end push and scrape

- P1.T2.S5: Verify agent pod can reach Pushgateway

- P1.T2.S6: Commit

### Task 3: Verify kube-state-metrics

- P1.T3.S1: Check if kube-state-metrics is deployed

- P1.T3.S2: If not deployed, install *(skipped — already deployed via victoria-metrics-k8s-stack)*

- P1.T3.S3: Verify pod metrics are available

### Task 4: Configure Grafana Telegram Contact Point

- P1.T4.S1: Create Telegram contact point

- P1.T4.S2: Test notification

- P1.T4.S3: Create notification policy

### Task 5: Create Grafana Alert Rules

- P1.T5.S1: Create alert folder

- P1.T5.S2: Create heartbeat stale alerts

- P1.T5.S3: Create endpoint probe alerts

- P1.T5.S4: Create pod health alert

- P1.T5.S5: Verify alert rules are evaluating

### Task 6: Create Grafana Feature Health Dashboard

- P1.T6.S1: Create dashboard

- P1.T6.S2: Save dashboard and note URL

### Task 7: End-to-End Verification

- P1.T7.S1: Trigger exercise cron and verify heartbeat

- P1.T7.S2: Check Grafana dashboard

- P1.T7.S3: Verify stale heartbeat → Telegram alert

- P1.T7.S4: Check Blackbox probes

- P1.T7.S5: Update GitHub Issue lifecycle states

- P1.T7.S6: Commit remaining changes
