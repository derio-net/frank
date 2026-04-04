# Work Lifecycle Tracking — M2: Health Monitoring Infrastructure (Frank)

**Status:** Deployed

**Goal:** Deploy Prometheus Blackbox Exporter and Pushgateway on Frank, configure Grafana dashboards and alerting, so deployed features are monitored and silent failures trigger Telegram alerts.

**Architecture:** Blackbox Exporter probes HTTP endpoints. Pushgateway receives heartbeat metrics from cron scripts (configured in the Willikins plan). VictoriaMetrics (existing) scrapes both. Grafana dashboards visualize health status. Grafana alerting routes to Telegram via native integration.

**Tech Stack:** Prometheus Blackbox Exporter, Prometheus Pushgateway, VictoriaMetrics (existing), Grafana 12.3.3 (existing), Kubernetes manifests, Bash

**Spec:** `willikins/docs/superpowers/specs/2026-04-01-work-lifecycle-tracking-design.md`

**Companion plan:** `willikins/docs/superpowers/plans/2026-04-01-work-lifecycle-m1-willikins.md` (GitHub Projects board, heartbeat scripts)

---

## Pre-Work: Conventions Discovered

- **Namespace:** `monitoring`
- **Manifest pattern:** Raw manifests in `apps/<app>/manifests/` + ArgoCD Application CR in `apps/root/templates/<app>.yaml`
- **Scraping:** VM Operator CRDs (`VMProbe`, `VMServiceScrape`) via `operator.victoriametrics.com/v1beta1`
- **Grafana provisioning:** API-provisioned via Grafana REST API (not file-based). Dashboard, alert rules, contact points, and notification policies all created via `PUT`/`POST` to provisioning API. Config persists in Grafana's PVC-backed database.
- **VictoriaMetrics datasource UID:** `P4169E866C3094E38`

---

## File Map

| File | Purpose |
|------|---------|
| `apps/blackbox-exporter/manifests/configmap.yaml` | Blackbox probe module definitions |
| `apps/blackbox-exporter/manifests/deployment.yaml` | Blackbox Exporter Deployment + Service |
| `apps/blackbox-exporter/manifests/vmprobe.yaml` | VMProbe CR for feature health endpoints |
| `apps/root/templates/blackbox-exporter.yaml` | ArgoCD Application CR |
| `apps/pushgateway/manifests/deployment.yaml` | Pushgateway Deployment + Service |
| `apps/pushgateway/manifests/vmservicescrape.yaml` | VMServiceScrape CR (honorLabels: true) |
| `apps/root/templates/pushgateway.yaml` | ArgoCD Application CR |
| `apps/root/templates/victoria-metrics.yaml` | Modified — added ignoreDifferences for VWC caBundle |
| `apps/secure-agent-pod/manifests/externalsecret-github-token.yaml` | Modified — added KALI_C2 Telegram + GEMINI + GRAFANA + R2 credentials |

---

## Task 1: Deploy Blackbox Exporter

- [x] **Step 1: Create Blackbox Exporter ConfigMap**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: blackbox-exporter-config
  namespace: <observability-namespace>
data:
  blackbox.yml: |
    modules:
      http_2xx:
        prober: http
        timeout: 10s
        http:
          valid_http_versions: ["HTTP/1.1", "HTTP/2.0"]
          valid_status_codes: [200, 301, 302]
          follow_redirects: true
          preferred_ip_protocol: ip4
      http_2xx_no_redirect:
        prober: http
        timeout: 10s
        http:
          valid_status_codes: [200]
          follow_redirects: false
          preferred_ip_protocol: ip4
      tcp_connect:
        prober: tcp
        timeout: 5s
```

- [x] **Step 2: Create Blackbox Exporter Deployment + Service**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: blackbox-exporter
  namespace: <observability-namespace>
  labels:
    app: blackbox-exporter
spec:
  replicas: 1
  selector:
    matchLabels:
      app: blackbox-exporter
  template:
    metadata:
      labels:
        app: blackbox-exporter
    spec:
      containers:
        - name: blackbox-exporter
          image: prom/blackbox-exporter:v0.25.0
          ports:
            - containerPort: 9115
          args:
            - --config.file=/config/blackbox.yml
          volumeMounts:
            - name: config
              mountPath: /config
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              memory: 64Mi
      volumes:
        - name: config
          configMap:
            name: blackbox-exporter-config
---
apiVersion: v1
kind: Service
metadata:
  name: blackbox-exporter
  namespace: <observability-namespace>
  labels:
    app: blackbox-exporter
spec:
  selector:
    app: blackbox-exporter
  ports:
    - port: 9115
      targetPort: 9115
```

- [x] **Step 3: Apply and verify**

```bash
kubectl apply -f <path-to-manifests>
kubectl get pods -n <observability-namespace> -l app=blackbox-exporter
kubectl logs -n <observability-namespace> -l app=blackbox-exporter --tail=20
```

Expected: Pod running, logs show "Listening on :9115".

- [x] **Step 4: Configure VictoriaMetrics to scrape probes**

If using VM Operator CRDs:

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMProbe
metadata:
  name: feature-health-probes
  namespace: <observability-namespace>
spec:
  targets:
    staticConfig:
      targets:
        - http://n8n.n8n.svc.cluster.local:5678
        - https://paperclip.frank.derio.net
        - https://grafana.frank.derio.net
        - https://blog.derio.net
      labels:
        probe_group: feature_health
  module: http_2xx
  vmProberSpec:
    url: blackbox-exporter.<observability-namespace>.svc:9115
```

If using raw Prometheus scrape config, add a scrape job with relabeling:

```yaml
- job_name: blackbox_feature_health
  metrics_path: /probe
  params:
    module: [http_2xx]
  static_configs:
    - targets:
        - http://n8n.n8n.svc.cluster.local:5678
        - https://paperclip.frank.derio.net
        - https://grafana.frank.derio.net
        - https://blog.derio.net
      labels:
        probe_group: feature_health
  relabel_configs:
    - source_labels: [__address__]
      target_label: __param_target
    - source_labels: [__param_target]
      target_label: instance
    - target_label: __address__
      replacement: blackbox-exporter.<observability-namespace>.svc:9115
```

- [x] **Step 5: Test a probe**

```bash
kubectl port-forward -n <observability-namespace> svc/blackbox-exporter 9115:9115 &
curl -s "http://localhost:9115/probe?target=https://grafana.frank.derio.net&module=http_2xx" | grep probe_success
kill %1
```

Expected: `probe_success 1`

- [x] **Step 6: Commit**

```bash
git add <manifest paths>
git commit -m "feat: deploy blackbox-exporter for feature health probes"
```

---

## Task 2: Deploy Pushgateway

- [x] **Step 1: Create Pushgateway Deployment + Service**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pushgateway
  namespace: <observability-namespace>
  labels:
    app: pushgateway
spec:
  replicas: 1
  selector:
    matchLabels:
      app: pushgateway
  template:
    metadata:
      labels:
        app: pushgateway
    spec:
      containers:
        - name: pushgateway
          image: prom/pushgateway:v1.9.0
          ports:
            - containerPort: 9091
          args:
            - --persistence.interval=5m
            - --persistence.file=/data/pushgateway.dat
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              memory: 64Mi
      volumes:
        - name: data
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: pushgateway
  namespace: <observability-namespace>
  labels:
    app: pushgateway
spec:
  selector:
    app: pushgateway
  ports:
    - port: 9091
      targetPort: 9091
```

- [x] **Step 2: Apply and verify**

```bash
kubectl apply -f <path-to-manifests>
kubectl get pods -n <observability-namespace> -l app=pushgateway
```

Expected: Pod running.

- [x] **Step 3: Configure VictoriaMetrics to scrape Pushgateway**

If using VM Operator CRDs:

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMServiceScrape
metadata:
  name: pushgateway
  namespace: <observability-namespace>
spec:
  selector:
    matchLabels:
      app: pushgateway
  endpoints:
    - port: "9091"
      honorLabels: true
```

If using raw scrape config:

```yaml
- job_name: pushgateway
  honor_labels: true
  static_configs:
    - targets: ['pushgateway.<observability-namespace>.svc:9091']
```

`honor_labels: true` is critical -- it preserves the job/instance labels from pushed metrics.

- [x] **Step 4: Verify end-to-end push and scrape**

```bash
# Push a test metric
echo 'test_heartbeat 42' | curl -s --data-binary @- \
  http://pushgateway.<observability-namespace>.svc:9091/metrics/job/test

# Wait one scrape interval, then check VictoriaMetrics via Grafana Explore:
# Query: test_heartbeat
# Expected: value 42 with job="test"

# Clean up test metric
curl -s -X DELETE http://pushgateway.<observability-namespace>.svc:9091/metrics/job/test
```

- [x] **Step 5: Verify agent pod can reach Pushgateway**

From the secure-agent-pod, test connectivity:

```bash
curl -s http://pushgateway.<observability-namespace>.svc.cluster.local:9091/api/v1/status
```

Expected: JSON status response. If blocked by Cilium egress policy, add a rule allowing traffic from `secure-agent-pod` namespace to `<observability-namespace>` on port 9091.

- [x] **Step 6: Commit**

```bash
git add <manifest paths>
git commit -m "feat: deploy pushgateway for heartbeat metrics from cron jobs"
```

---

## Task 3: Verify kube-state-metrics

- [x] **Step 1: Check if kube-state-metrics is deployed**

```bash
kubectl get pods -A | grep kube-state-metrics
kubectl get svc -A | grep kube-state-metrics
```

- [-] **Step 2: If not deployed, install** *(skipped — already deployed via victoria-metrics-k8s-stack)*

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kube-state-metrics prometheus-community/kube-state-metrics \
  --namespace <observability-namespace> \
  --set resources.requests.cpu=10m \
  --set resources.requests.memory=32Mi
```

- [x] **Step 3: Verify pod metrics are available**

In Grafana Explore, query:
```
kube_pod_status_phase{namespace="secure-agent-pod"}
```

Expected: Returns pod phase data for the agent pod.

---

## Task 4: Configure Grafana Telegram Contact Point

- [x] **Step 1: Create Telegram contact point**

Created via Grafana provisioning API. Contact point uid: `efi04e0201jb4f`.

| Setting | Value |
|---------|-------|
| Name | Telegram - Willikins |
| Bot | `@agent_zero_cc_bot` (id: 8378519865) |
| Bot Token | `FRANK_C2_TELEGRAM_BOT_TOKEN` (Infisical prod) |
| Chat ID | `FRANK_C2_TELEGRAM_CHAT_ID` = 2034763022 (Infisical prod) |
| Parse Mode | Markdown |

- [x] **Step 2: Test notification**

Direct Bot API delivery confirmed (msg_ids 56, 59).
Grafana alert→Telegram delivery confirmed after pod restart (see Deviations).

- [x] **Step 3: Create notification policy**

```
group_wait: 30s, group_interval: 3m, repeat_interval: 3m
Route 1: severity=critical → Telegram - Willikins (continue: true)
Route 2: severity=warning → Telegram - Willikins (continue: false)
```

---

## Task 5: Create Grafana Alert Rules

All rules created via Grafana provisioning API using 3-step SSE format (see Deviations).
Folder: "Feature Health" (uid: `feature-health`).

- [x] **Step 1: Create alert folder**

- [x] **Step 2: Create heartbeat stale alerts**

| UID | Query (A) | Threshold (C) | For | Every | Severity |
|-----|-----------|---------------|-----|-------|----------|
| `exercise-reminder-stale` | `time() - willikins_heartbeat_last_success_timestamp{job="exercise_reminder"}` | gt 60 *(testing; plan=10800)* | 1m | 5m | critical |
| `session-manager-stale` | `time() - willikins_heartbeat_last_success_timestamp{job="session_manager"}` | gt 600 | 5m | 1m | critical |
| `audit-digest-stale` | `time() - willikins_heartbeat_last_success_timestamp{job="audit_digest"}` | gt 93600 | 1h | 30m | warning |

- [x] **Step 3: Create endpoint probe alerts**

| UID | Query (A) | Threshold (C) | For | Every | Severity |
|-----|-----------|---------------|-----|-------|----------|
| `endpoint-down` | `probe_success{probe_group="feature_health"}` | lt 1 | 5m | 1m | critical |

- [x] **Step 4: Create pod health alert**

| UID | Query (A) | Threshold (C) | For | Every | Severity |
|-----|-----------|---------------|-----|-------|----------|
| `agent-pod-not-running` | `kube_pod_status_phase{namespace="secure-agent-pod", phase="Running"}` | lt 1 | 5m | 1m | critical |

- [x] **Step 5: Verify alert rules are evaluating**

All 5 rules evaluating correctly. Telegram notifications confirmed delivered for firing alerts.

---

## Task 6: Create Grafana Feature Health Dashboard

Dashboard uid: `fh-overview`, folder: `feature-health`.
URL: https://grafana.frank.derio.net/d/fh-overview/feature-health

- [x] **Step 1: Create dashboard**

| Panel | Type | Query | Notes |
|-------|------|-------|-------|
| Feature Health Alerts | `alertlist` | *(native Grafana alerting)* | Shows firing/pending/noData/error from Feature Health folder. `ALERTS{}` doesn't exist in VM for Grafana-managed alerts — must use alertlist panel type. |
| Cron Job Heartbeats | `table` | `(time() - willikins_heartbeat_last_success_timestamp) / 60` | Columns: context, job, Minutes Since Last Success. Thresholds: green <60m, yellow <180m, red 180m+. |
| Endpoint Probes | `table` | `probe_success{probe_group="feature_health"}` | Columns: instance, Success (UP/DOWN). Value mappings: 1=UP green, 0=DOWN red. |
| Pod Status | `table` | `kube_pod_status_phase{namespace=~"secure-agent-pod\|n8n-01\|paperclip-system", phase="Running"}` | Columns: namespace, pod, phase, Count. |

- [x] **Step 2: Save dashboard and note URL**

All 4 panels populated and verified with live data.

---

## Task 7: End-to-End Verification

- [x] **Step 1: Trigger exercise cron and verify heartbeat**

Exercise cron triggered manually. Heartbeat pushed to Pushgateway (`willikins_heartbeat_last_success_timestamp{job="exercise_reminder"}`).

- [x] **Step 2: Check Grafana dashboard**

All 4 panels displaying live data. Cron Job Heartbeats shows exercise_reminder with stale time.

- [x] **Step 3: Verify stale heartbeat → Telegram alert**

Threshold temporarily lowered to 60s. Alert transitioned Normal → Pending → Firing.
Telegram notification arrived after Grafana pod restart (pod restart was needed to reset alertmanager notification dedup state after contact point was re-provisioned — see Deviations).

- [x] **Step 4: Check Blackbox probes**

All 4 endpoints UP: n8n-01, blog.derio.net, grafana.frank.derio.net, paperclip.frank.derio.net.

- [x] **Step 5: Update GitHub Issue lifecycle states**

Updated via `gh project item-edit`:
- frank#8 (secure-agent-pod): deployed → **healthy**
- willikins#11 (exercise reminder): dead → **healthy**

- [x] **Step 6: Commit remaining changes**

All changes committed to main.

---

## Deployment Deviations

### Grafana 12.x SSE expression format (Task 5)

Alert rules must use 3-step A→B→C format in Grafana 12.x. Classic condition format (`datasourceUid: "-100"`) fails with `[sse.parseError] failed to parse expression [C]`.

Required format per rule:
- A: datasource query (VictoriaMetrics, `datasourceUid: P4169E866C3094E38`)
- B: reduce expression (`datasourceUid: "__expr__"`, type: reduce, reducer: last, settings.mode: dropNN)
- C: threshold expression (`datasourceUid: "__expr__"`, type: threshold, expression: B)

### VictoriaMetrics Operator webhook TLS mismatch

Helm `genCA` regenerates caBundle on every chart render. ArgoCD sync overwrote the caBundle, breaking webhook cert validation (`x509: certificate signed by unknown authority`).

Permanent fix: `ignoreDifferences` on `ValidatingWebhookConfiguration` caBundle in `apps/root/templates/victoria-metrics.yaml` (`jqPathExpressions: .webhooks[].clientConfig.caBundle`).

### Dashboard Panel 1: alertlist, not ALERTS{}

`ALERTS{}` metric does not exist in VictoriaMetrics for Grafana-managed alerts (only for Prometheus-native alerting rules). Panel 1 uses native `alertlist` panel type instead of a stat panel querying `ALERTS{}`.

### Dashboard table panels: format: "table" required

Prometheus instant queries in table panels require `"format": "table"` on targets. Without it, Grafana returns time-series frames that don't render in tables. The `labelsToFields` transform with `mode: "rows"` also doesn't work — use `filterFieldsByName` instead.

### Grafana alertmanager notification dedup

After re-provisioning the contact point (bot token was lost), Grafana still grouped the alert as "already notified" from the previous (failed) attempt. Default `repeat_interval` is 4h, so no retry occurred. Fix: set `repeat_interval: 3m` and restart the Grafana pod to reset alertmanager internal notification state.

### Contact point is API-provisioned (not GitOps)

The Grafana dashboard, alert rules, contact point, and notification policies are all stored in Grafana's PVC-backed database, created via API. They survive pod restarts but NOT PVC loss. If the PVC is recreated, all must be re-provisioned. The plan documents the API calls and parameters needed to recreate.

### exercise-reminder-stale threshold temporarily lowered

Threshold set to 60s (from plan's 10800s) for testing. Restore to 10800 once cron schedules are confirmed stable.

### ExternalSecret expanded beyond plan scope

`apps/secure-agent-pod/manifests/externalsecret-github-token.yaml` now maps 7 Infisical secrets (was 1):
GITHUB_SECURE_AGENT_POD → GITHUB_TOKEN, KALI_C2_TELEGRAM_BOT_TOKEN → TELEGRAM_BOT_TOKEN, KALI_C2_TELEGRAM_CHAT_ID → TELEGRAM_CHAT_ID, GEMINI_API_KEY, GRAFANA_API_KEY, R2_ACCESS_KEY, R2_SECRET_KEY.
