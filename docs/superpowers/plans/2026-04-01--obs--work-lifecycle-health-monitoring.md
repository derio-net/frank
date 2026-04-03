# Work Lifecycle Tracking — M2: Health Monitoring Infrastructure (Frank)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Prometheus Blackbox Exporter and Pushgateway on Frank, configure Grafana dashboards and alerting, so deployed features are monitored and silent failures trigger Telegram alerts.

**Architecture:** Blackbox Exporter probes HTTP endpoints. Pushgateway receives heartbeat metrics from cron scripts (configured in the Willikins plan). VictoriaMetrics (existing) scrapes both. Grafana dashboards visualize health status. Grafana alerting routes to Telegram via native integration.

**Tech Stack:** Prometheus Blackbox Exporter, Prometheus Pushgateway, VictoriaMetrics (existing), Grafana (existing), Kubernetes manifests, Bash

**Spec:** `willikins/docs/superpowers/specs/2026-04-01-work-lifecycle-tracking-design.md`

**Companion plan:** `willikins/docs/superpowers/plans/2026-04-01-work-lifecycle-m1-willikins.md` (GitHub Projects board, heartbeat scripts)

**Prerequisites:** The Willikins plan (M1) should be completed first so that GitHub Issue numbers are known for Grafana alert labels.

---

## Pre-Work: Identify Frank Repo Conventions

Before creating manifests, the implementer must determine:

1. **Observability namespace:** What namespace do VictoriaMetrics and Grafana live in? (Likely `observability` or `monitoring`)
2. **Manifest pattern:** Does the frank repo use Helm, Kustomize, raw manifests, or ArgoCD ApplicationSets?
3. **VictoriaMetrics scraping:** Is it via VM Operator CRDs (VMServiceScrape, VMProbe) or raw Prometheus scrape configs?
4. **Grafana provisioning:** Are dashboards/alerts managed via Grafana provisioning (YAML/JSON in repo) or UI-only?

Run these commands to discover:

```bash
# Namespace discovery
kubectl get ns | grep -iE "observ|monitor|grafana|victoria"

# Manifest pattern
gh api repos/derio-net/frank/git/trees/main --jq '.tree[].path' | head -50

# VictoriaMetrics Operator CRDs
kubectl api-resources | grep -i victoriametrics

# Grafana provisioning
kubectl get configmaps -n <obs-namespace> | grep -i grafana
```

Document the answers and adjust manifest formats in the tasks below accordingly.

---

## File Map

All files are created in the **frank repo** (derio-net/frank). Exact paths depend on the repo structure discovered in Pre-Work.

| File | Action | Purpose |
|------|--------|---------|
| `<obs-path>/blackbox-exporter/config.yaml` | Create | Blackbox probe module definitions |
| `<obs-path>/blackbox-exporter/deployment.yaml` | Create | Blackbox Exporter K8s Deployment + Service |
| `<obs-path>/blackbox-exporter/scrape.yaml` | Create | VMProbe or scrape config for Blackbox targets |
| `<obs-path>/pushgateway/deployment.yaml` | Create | Pushgateway K8s Deployment + Service |
| `<obs-path>/pushgateway/scrape.yaml` | Create | VMServiceScrape or scrape config for Pushgateway |
| `<obs-path>/grafana/dashboards/feature-health.json` | Create | Feature Health dashboard (if Grafana uses provisioning) |
| `<obs-path>/grafana/alerts/feature-health.yaml` | Create | Alert rules (if Grafana uses provisioning) |

---

## Task 1: Deploy Blackbox Exporter

- [ ] **Step 1: Create Blackbox Exporter ConfigMap**

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

- [ ] **Step 2: Create Blackbox Exporter Deployment + Service**

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

- [ ] **Step 3: Apply and verify**

```bash
kubectl apply -f <path-to-manifests>
kubectl get pods -n <observability-namespace> -l app=blackbox-exporter
kubectl logs -n <observability-namespace> -l app=blackbox-exporter --tail=20
```

Expected: Pod running, logs show "Listening on :9115".

- [ ] **Step 4: Configure VictoriaMetrics to scrape probes**

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

- [ ] **Step 5: Test a probe**

```bash
kubectl port-forward -n <observability-namespace> svc/blackbox-exporter 9115:9115 &
curl -s "http://localhost:9115/probe?target=https://grafana.frank.derio.net&module=http_2xx" | grep probe_success
kill %1
```

Expected: `probe_success 1`

- [ ] **Step 6: Commit**

```bash
git add <manifest paths>
git commit -m "feat: deploy blackbox-exporter for feature health probes"
```

---

## Task 2: Deploy Pushgateway

- [ ] **Step 1: Create Pushgateway Deployment + Service**

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

- [ ] **Step 2: Apply and verify**

```bash
kubectl apply -f <path-to-manifests>
kubectl get pods -n <observability-namespace> -l app=pushgateway
```

Expected: Pod running.

- [ ] **Step 3: Configure VictoriaMetrics to scrape Pushgateway**

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

- [ ] **Step 4: Verify end-to-end push and scrape**

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

- [ ] **Step 5: Verify agent pod can reach Pushgateway**

From the secure-agent-pod, test connectivity:

```bash
curl -s http://pushgateway.<observability-namespace>.svc.cluster.local:9091/api/v1/status
```

Expected: JSON status response. If blocked by Cilium egress policy, add a rule allowing traffic from `secure-agent-pod` namespace to `<observability-namespace>` on port 9091.

- [ ] **Step 6: Commit**

```bash
git add <manifest paths>
git commit -m "feat: deploy pushgateway for heartbeat metrics from cron jobs"
```

---

## Task 3: Verify kube-state-metrics

- [ ] **Step 1: Check if kube-state-metrics is deployed**

```bash
kubectl get pods -A | grep kube-state-metrics
kubectl get svc -A | grep kube-state-metrics
```

- [ ] **Step 2: If not deployed, install**

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kube-state-metrics prometheus-community/kube-state-metrics \
  --namespace <observability-namespace> \
  --set resources.requests.cpu=10m \
  --set resources.requests.memory=32Mi
```

- [ ] **Step 3: Verify pod metrics are available**

In Grafana Explore, query:
```
kube_pod_status_phase{namespace="secure-agent-pod"}
```

Expected: Returns pod phase data for the agent pod.

---

## Task 4: Configure Grafana Telegram Contact Point

- [ ] **Step 1: Create Telegram contact point**

In Grafana (https://grafana.frank.derio.net): Alerting > Contact points > Add contact point

```
Name: Telegram - Willikins
Type: Telegram
Bot Token: <TELEGRAM_BOT_TOKEN from Infisical>
Chat ID: <TELEGRAM_CHAT_ID from Infisical>
Message: |
  {{ if eq .Status "firing" }}🔴{{ else }}🟢{{ end }} {{ .CommonLabels.alertname }}
  Status: {{ .Status }}
  {{ range .Alerts }}
  - {{ .Labels.feature }}: {{ .Annotations.description }}
  {{ end }}
Parse Mode: Markdown
```

- [ ] **Step 2: Send test notification**

Use Grafana's "Test" button. Verify message arrives on Telegram.

- [ ] **Step 3: Create notification policy**

Alerting > Notification policies > Add nested policy:

```
Matching labels: severity = critical
Contact point: Telegram - Willikins
Continue matching: true

Matching labels: severity = warning
Contact point: Telegram - Willikins
Continue matching: false
```

---

## Task 5: Create Grafana Alert Rules

**Prerequisites:** Issue numbers from the Willikins plan (Task 2, Step 5).

- [ ] **Step 1: Create alert folder**

Alerting > Alert rules > New folder: `Feature Health`

- [ ] **Step 2: Create heartbeat stale alerts**

**Exercise Reminder Heartbeat:**
```
Name: Exercise Reminder Stale
Folder: Feature Health
Query A (VictoriaMetrics):
  time() - willikins_heartbeat_last_success_timestamp{job="exercise_reminder"} > 10800
Condition: A is above 0
Evaluate every: 5m
For: 10m
Labels:
  severity: critical
  feature: exercise-reminder
  github_issue: willikins#<issue number>
Annotations:
  summary: Exercise reminder heartbeat is stale
  description: No successful exercise reminder in over 3 hours.
```

**Session Manager Heartbeat:**
```
Name: Session Manager Stale
Query A: time() - willikins_heartbeat_last_success_timestamp{job="session_manager"} > 600
Evaluate every: 1m
For: 5m
Labels:
  severity: critical
  feature: session-manager
  github_issue: willikins#<issue number>
Annotations:
  summary: Session manager heartbeat is stale
  description: No successful session check in over 10 minutes.
```

**Audit Digest Heartbeat:**
```
Name: Audit Digest Stale
Query A: time() - willikins_heartbeat_last_success_timestamp{job="audit_digest"} > 93600
Evaluate every: 30m
For: 1h
Labels:
  severity: warning
  feature: audit-digest
  github_issue: willikins#<issue number>
Annotations:
  summary: Audit digest heartbeat is stale
  description: No successful audit digest in over 26 hours.
```

- [ ] **Step 3: Create endpoint probe alerts**

**Endpoint Down (generic):**
```
Name: Endpoint Down
Folder: Feature Health
Query A: probe_success{probe_group="feature_health"} == 0
Evaluate every: 1m
For: 5m
Labels:
  severity: critical
  feature: {{ $labels.instance }}
Annotations:
  summary: Endpoint {{ $labels.instance }} is down
  description: HTTP probe failing for over 5 minutes.
```

- [ ] **Step 4: Create pod health alert**

**Agent Pod Not Running:**
```
Name: Agent Pod Not Running
Folder: Feature Health
Query A: kube_pod_status_phase{namespace="secure-agent-pod", phase="Running"} != 1
Evaluate every: 1m
For: 5m
Labels:
  severity: critical
  feature: secure-agent-pod
  github_issue: frank#<issue number>
Annotations:
  summary: Secure agent pod is not running
  description: Pod not in Running state for 5+ minutes.
```

- [ ] **Step 5: Verify alert rules are evaluating**

Alerting > Alert rules > Feature Health folder. All rules should show "Normal" (green) or "Pending"/"Firing" if conditions are already met (e.g., heartbeats don't exist yet -- this is expected and validates the alerting works).

---

## Task 6: Create Grafana Feature Health Dashboard

- [ ] **Step 1: Create dashboard**

Name: "Feature Health"

**Panel 1: Health Status Overview (Stat)**
```
Title: Active Health Alerts
Query A: count(ALERTS{alertstate="firing", alertname=~".*Stale|.*Down|.*Not Running"}) or vector(0)
Thresholds: 0 = green, 1 = red
```

**Panel 2: Cron Job Heartbeats (Table)**
```
Title: Cron Job Heartbeats
Query A: (time() - willikins_heartbeat_last_success_timestamp) / 60
Format: Table
Column: job, context, Value ("Minutes Since Last Success")
Thresholds: 0-60 green, 60-180 yellow, 180+ red
```

**Panel 3: Endpoint Probes (Table)**
```
Title: Endpoint Probes
Query A: probe_success{probe_group="feature_health"}
Query B: probe_duration_seconds{probe_group="feature_health"}
Format: Table
Column: instance, Success (0/1), Duration
Thresholds on Success: 1 green, 0 red
```

**Panel 4: Pod Status (Table)**
```
Title: Pod Status
Query A: kube_pod_status_phase{namespace=~"secure-agent-pod|n8n|paperclip"}
Format: Table
Column: namespace, pod, phase
Value mapping: Running green, Pending yellow, Failed red
```

- [ ] **Step 2: Save dashboard and note URL**

Save. Note the URL for the health bridge service (M3) and for linking in GitHub Issue descriptions.

---

## Task 7: End-to-End Verification

Run from the **secure-agent-pod** after both plans (Willikins + Frank) are complete.

- [ ] **Step 1: Trigger exercise cron and verify heartbeat**

```bash
/home/claude/repos/willikins/scripts/willikins-agent/exercise-cron.sh desk
```

Expected: Telegram reminder received AND heartbeat pushed. Verify:

```bash
curl -s http://pushgateway.<observability-namespace>.svc.cluster.local:9091/api/v1/metrics | grep exercise_reminder
```

Expected: `willikins_heartbeat_last_success_timestamp` with a recent timestamp.

- [ ] **Step 2: Check Grafana dashboard**

Open Feature Health dashboard. "Cron Job Heartbeats" panel should show `exercise_reminder` with a small "Minutes Since Last Success" value.

- [ ] **Step 3: Simulate stale heartbeat**

Wait for the heartbeat threshold to expire (or temporarily lower it in Grafana). Verify:
- Alert transitions Normal > Pending > Firing
- Telegram notification arrives

- [ ] **Step 4: Check Blackbox probes**

Dashboard "Endpoint Probes" panel should show green for all configured endpoints.

- [ ] **Step 5: Update GitHub Issue lifecycle states**

For features confirmed healthy, update Issues from `deployed` to `healthy`:

```bash
# Use gh project item-edit to move Issues to "healthy" state
# (Use the helper function from the Willikins plan or edit directly)
```

- [ ] **Step 6: Commit any remaining changes**

```bash
git add <any modified manifests>
git commit -m "feat: complete M2 health monitoring -- probes, dashboards, alerting"
```
