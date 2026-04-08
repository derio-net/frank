# Grafana Alerting as Code — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Codify Frank's Grafana alerting stack (5 alert rules, 2 contact points, notification policy, Feature Health dashboard) as Kubernetes ConfigMaps managed by ArgoCD, replacing API-provisioned resources.

**Architecture:** New `apps/grafana-alerting/` ArgoCD application with 4 ConfigMaps + 1 ExternalSecret. ConfigMaps mount into Grafana's provisioning directories via `extraConfigmapMounts` in the victoria-metrics Helm values. Secrets injected via `envFromSecrets` from an ExternalSecret-backed K8s Secret. Migration deletes API-provisioned duplicates after file-provisioned versions are verified.

**Tech Stack:** Kubernetes ConfigMaps, ArgoCD (raw manifests pattern), Grafana file-based provisioning, External Secrets Operator (Infisical), YAML/JSON

**Spec:** `docs/superpowers/specs/2026-04-08--obs--grafana-alerting-as-code-design.md`

---

## File Structure

```
apps/grafana-alerting/                    # NEW — raw manifests ArgoCD app
└── manifests/
    ├── alert-rules-cm.yaml               # ConfigMap: 5 alert rules (3 groups)
    ├── contact-points-cm.yaml            # ConfigMap: Telegram + Health Bridge webhook
    ├── notification-policy-cm.yaml       # ConfigMap: severity-based routing tree
    ├── dashboard-cm.yaml                 # ConfigMap: dashboard provider config + Feature Health JSON
    └── externalsecret.yaml               # ExternalSecret: Telegram + webhook secrets from Infisical

apps/root/templates/
└── grafana-alerting.yaml                 # NEW — ArgoCD Application CR

apps/victoria-metrics/
└── values.yaml                           # MODIFY — add extraConfigmapMounts + envFromSecrets
```

---

### Task 1: Create the ArgoCD Application CR

**Files:**
- Create: `apps/root/templates/grafana-alerting.yaml`

- [x] **Step 1: Create the Application CR**

Follow the raw-manifests pattern from `apps/root/templates/health-bridge.yaml`. The only differences: app name and path.

```yaml
# apps/root/templates/grafana-alerting.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: grafana-alerting
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ .Values.repoURL }}
    targetRevision: {{ .Values.targetRevision }}
    path: apps/grafana-alerting/manifests
  destination:
    server: {{ .Values.destination.server }}
    namespace: monitoring
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

- [x] **Step 2: Verify YAML syntax**

```bash
cd /var/tmp/vibe-kanban/worktrees/097c-read/frank
python3 -c "import yaml; yaml.safe_load(open('apps/root/templates/grafana-alerting.yaml').read().replace('{{ .Values.repoURL }}', 'x').replace('{{ .Values.targetRevision }}', 'x').replace('{{ .Values.destination.server }}', 'x'))"
```

Expected: no output (valid YAML after placeholder substitution).

- [x] **Step 3: Commit**

```bash
git add apps/root/templates/grafana-alerting.yaml
git commit -m "feat(obs): add grafana-alerting ArgoCD Application CR"
```

---

### Task 2: Create the Alert Rules ConfigMap

**Files:**
- Create: `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

**Context:** Grafana file-based provisioning reads YAML files from `/etc/grafana/provisioning/alerting/` at startup. Alert rules use the Grafana 12.x SSE 3-step format: A (datasource query) → B (reduce with `__expr__`, reducer: last) → C (threshold with `__expr__`). Classic condition format fails with `sse.parseError`. VictoriaMetrics datasource UID: `P4169E866C3094E38`.

- [x] **Step 1: Create the manifests directory**

```bash
mkdir -p apps/grafana-alerting/manifests
```

- [x] **Step 2: Create the alert rules ConfigMap**

Five groups — one per rule — because each rule has a different evaluation interval (Grafana evaluates all rules in a group at the group's `interval`). Groups are named by semantic pattern with interval suffix for clarity.

| Group | Rule | Interval | For |
|-------|------|----------|-----|
| `heartbeat-stale-5m` | exercise-reminder-stale | 5m | 1m |
| `heartbeat-stale-1m` | session-manager-stale | 1m | 5m |
| `heartbeat-stale-30m` | audit-digest-stale | 30m | 1h |
| `endpoint-down` | endpoint-down | 1m | 5m |
| `pod-not-running` | agent-pod-not-running | 1m | 5m |

```yaml
# apps/grafana-alerting/manifests/alert-rules-cm.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-alerting-rules
  namespace: monitoring
data:
  alert-rules.yaml: |
    apiVersion: 1
    groups:
      # --- Heartbeat-stale: exercise reminder (eval every 5m) ---
      - orgId: 1
        name: heartbeat-stale-5m
        folder: feature-health
        interval: 5m
        rules:
          - uid: exercise-reminder-stale
            title: Exercise Reminder Stale
            condition: C
            data:
              - refId: A
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'time() - willikins_heartbeat_last_success_timestamp{job="exercise_reminder"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings:
                    mode: dropNN
              - refId: C
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator:
                        type: gt
                        params:
                          - 10800
            noDataState: OK
            execErrState: Error
            for: 1m
            labels:
              severity: critical
              github_issue: "willikins#11"
            annotations:
              summary: Exercise reminder cron heartbeat is stale (>3h since last success)

      # --- Heartbeat-stale: session manager (eval every 1m) ---
      - orgId: 1
        name: heartbeat-stale-1m
        folder: feature-health
        interval: 1m
        rules:
          - uid: session-manager-stale
            title: Session Manager Stale
            condition: C
            data:
              - refId: A
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'time() - willikins_heartbeat_last_success_timestamp{job="session_manager"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings:
                    mode: dropNN
              - refId: C
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator:
                        type: gt
                        params:
                          - 600
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: critical
              github_issue: "willikins#13"
            annotations:
              summary: Session manager cron heartbeat is stale (>10m since last success)

      # --- Heartbeat-stale: audit digest (eval every 30m) ---
      - orgId: 1
        name: heartbeat-stale-30m
        folder: feature-health
        interval: 30m
        rules:
          - uid: audit-digest-stale
            title: Audit Digest Stale
            condition: C
            data:
              - refId: A
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'time() - willikins_heartbeat_last_success_timestamp{job="audit_digest"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings:
                    mode: dropNN
              - refId: C
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator:
                        type: gt
                        params:
                          - 93600
            noDataState: OK
            execErrState: Error
            for: 1h
            labels:
              severity: warning
              github_issue: "willikins#12"
            annotations:
              summary: Audit digest cron heartbeat is stale (>26h since last success)

      # --- Endpoint-down (eval every 1m) ---
      - orgId: 1
        name: endpoint-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: endpoint-down
            title: Endpoint Down
            condition: C
            data:
              - refId: A
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'probe_success{probe_group="feature_health"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings:
                    mode: dropNN
              - refId: C
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator:
                        type: lt
                        params:
                          - 1
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: critical
            annotations:
              summary: "HTTP endpoint probe failing"

      # --- Pod-not-running (eval every 1m) ---
      - orgId: 1
        name: pod-not-running
        folder: feature-health
        interval: 1m
        rules:
          - uid: agent-pod-not-running
            title: Agent Pod Not Running
            condition: C
            data:
              - refId: A
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_phase{namespace="secure-agent-pod", phase="Running"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings:
                    mode: dropNN
              - refId: C
                relativeTimeRange:
                  from: 600
                  to: 0
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator:
                        type: lt
                        params:
                          - 1
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: critical
              github_issue: "frank#8"
            annotations:
              summary: Secure agent pod is not in Running phase
```

- [x] **Step 3: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('apps/grafana-alerting/manifests/alert-rules-cm.yaml'))"
```

Expected: no output (valid YAML).

- [x] **Step 4: Commit**

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "feat(obs): add grafana alert rules ConfigMap (5 rules, 5 groups)"
```

---

### Task 3: Create the Contact Points ConfigMap

**Files:**
- Create: `apps/grafana-alerting/manifests/contact-points-cm.yaml`

**Context:** Grafana resolves `$ENV_VAR` syntax in provisioning files from pod environment variables. The Telegram contact point UID `efi04e0201jb4f` must be preserved — the notification policy references it. The Health Bridge webhook gets a new UID since it wasn't previously provisioned with a stable one.

- [x] **Step 1: Create the contact points ConfigMap**

```yaml
# apps/grafana-alerting/manifests/contact-points-cm.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-alerting-contact-points
  namespace: monitoring
data:
  contact-points.yaml: |
    apiVersion: 1
    contactPoints:
      - orgId: 1
        name: "Telegram - Willikins"
        receivers:
          - uid: efi04e0201jb4f
            type: telegram
            settings:
              bottoken: $FRANK_C2_TELEGRAM_BOT_TOKEN
              chatid: $FRANK_C2_TELEGRAM_CHAT_ID
              parse_mode: Markdown
      - orgId: 1
        name: "Health Bridge Webhook"
        receivers:
          - uid: health-bridge-webhook
            type: webhook
            settings:
              url: "http://health-bridge.monitoring.svc.cluster.local:8080/webhook"
              httpMethod: POST
              authorization_scheme: Bearer
              authorization_credentials: $HEALTH_BRIDGE_WEBHOOK_SECRET
```

- [x] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('apps/grafana-alerting/manifests/contact-points-cm.yaml'))"
```

- [x] **Step 3: Commit**

```bash
git add apps/grafana-alerting/manifests/contact-points-cm.yaml
git commit -m "feat(obs): add grafana contact points ConfigMap (Telegram + Health Bridge)"
```

---

### Task 4: Create the Notification Policy ConfigMap

**Files:**
- Create: `apps/grafana-alerting/manifests/notification-policy-cm.yaml`

**Context:** The routing tree sends severity-based alerts to Telegram with `continue: true` so they also match the folder-based route to Health Bridge. The folder matcher `grafana_folder=Feature Health` catches all alerts from the feature-health folder for GitHub lifecycle automation.

- [x] **Step 1: Create the notification policy ConfigMap**

```yaml
# apps/grafana-alerting/manifests/notification-policy-cm.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-alerting-notification-policy
  namespace: monitoring
data:
  notification-policy.yaml: |
    apiVersion: 1
    policies:
      - orgId: 1
        receiver: "Telegram - Willikins"
        group_wait: 30s
        group_interval: 3m
        repeat_interval: 3m
        routes:
          - receiver: "Telegram - Willikins"
            matchers:
              - severity=critical
            continue: true
          - receiver: "Telegram - Willikins"
            matchers:
              - severity=warning
            continue: true
          - receiver: "Health Bridge Webhook"
            matchers:
              - grafana_folder=Feature Health
            continue: false
```

- [x] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('apps/grafana-alerting/manifests/notification-policy-cm.yaml'))"
```

- [x] **Step 3: Commit**

```bash
git add apps/grafana-alerting/manifests/notification-policy-cm.yaml
git commit -m "feat(obs): add grafana notification policy ConfigMap (severity routing)"
```

---

### Task 5: Create the ExternalSecret for Alerting Env Vars

**Files:**
- Create: `apps/grafana-alerting/manifests/externalsecret.yaml`

**Context:** Grafana's contact point provisioning uses `$ENV_VAR` syntax. The 3 required env vars (`FRANK_C2_TELEGRAM_BOT_TOKEN`, `FRANK_C2_TELEGRAM_CHAT_ID`, `HEALTH_BRIDGE_WEBHOOK_SECRET`) must be available in the Grafana pod environment. This ExternalSecret pulls them from Infisical into a K8s Secret that Grafana references via `envFromSecrets`. Pattern matches `apps/health-bridge/manifests/externalsecret.yaml`.

- [x] **Step 1: Create the ExternalSecret**

```yaml
# apps/grafana-alerting/manifests/externalsecret.yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: grafana-alerting-secrets
  namespace: monitoring
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: grafana-alerting-secrets
    creationPolicy: Owner
  data:
    - secretKey: FRANK_C2_TELEGRAM_BOT_TOKEN
      remoteRef:
        key: FRANK_C2_TELEGRAM_BOT_TOKEN
    - secretKey: FRANK_C2_TELEGRAM_CHAT_ID
      remoteRef:
        key: FRANK_C2_TELEGRAM_CHAT_ID
    - secretKey: HEALTH_BRIDGE_WEBHOOK_SECRET
      remoteRef:
        key: HEALTH_BRIDGE_WEBHOOK_SECRET
```

- [x] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('apps/grafana-alerting/manifests/externalsecret.yaml'))"
```

- [x] **Step 3: Commit**

```bash
git add apps/grafana-alerting/manifests/externalsecret.yaml
git commit -m "feat(obs): add ExternalSecret for grafana alerting env vars"
```

---

### Task 6: Create the Dashboard ConfigMap

**Files:**
- Create: `apps/grafana-alerting/manifests/dashboard-cm.yaml`

**Context:** Grafana file-based dashboard provisioning requires two pieces: (1) a provider config YAML in `/etc/grafana/provisioning/dashboards/` that tells Grafana where to find JSON files, and (2) the dashboard JSON file(s) at the path specified in the provider config. Both are stored in this ConfigMap under separate keys and mounted at different paths via `extraConfigmapMounts`.

The dashboard UID `fh-overview` is preserved from the existing API-provisioned version (referenced in blog: `/d/fh-overview/feature-health`).

**Panel layout from spec:**
- Top-left (0,0): Alert Summary — `alertlist` panel showing firing alerts from feature-health folder
- Top-right (8,0): Cron Job Heartbeats — `table` panel with `(time() - willikins_heartbeat_last_success_timestamp) / 60`
- Middle (0,8): Endpoint Probes — `table` panel with `probe_success{probe_group="feature_health"}`
- Bottom (0,16): Pod Status — `table` panel with `kube_pod_status_phase{...}`

**Table panel gotcha:** Prometheus instant queries require `"format": "table"` on targets. Use `filterFieldsByName` transform (not `labelsToFields` with `mode: rows`).

- [x] **Step 1: Create the dashboard ConfigMap**

The ConfigMap has two keys:
- `feature-health-provider.yaml` — provider config (mounted to `/etc/grafana/provisioning/dashboards/`)
- `feature-health.json` — dashboard JSON (mounted to `/var/lib/grafana/dashboards/feature-health/`)

```yaml
# apps/grafana-alerting/manifests/dashboard-cm.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-alerting-dashboard
  namespace: monitoring
data:
  feature-health-provider.yaml: |
    apiVersion: 1
    providers:
      - name: feature-health
        folder: feature-health
        type: file
        disableDeletion: true
        editable: false
        options:
          path: /var/lib/grafana/dashboards/feature-health
  feature-health.json: |
    {
      "uid": "fh-overview",
      "title": "Feature Health",
      "tags": ["feature-health"],
      "timezone": "browser",
      "schemaVersion": 39,
      "refresh": "30s",
      "time": { "from": "now-1h", "to": "now" },
      "panels": [
        {
          "id": 1,
          "title": "Alert Summary",
          "type": "alertlist",
          "gridPos": { "h": 8, "w": 8, "x": 0, "y": 0 },
          "options": {
            "alertListType": "alertRules",
            "folder": { "title": "feature-health" },
            "stateFilter": {
              "firing": true,
              "pending": true,
              "noData": true,
              "normal": false,
              "error": true
            },
            "viewMode": "list"
          }
        },
        {
          "id": 2,
          "title": "Cron Job Heartbeats",
          "type": "table",
          "gridPos": { "h": 8, "w": 16, "x": 8, "y": 0 },
          "datasource": { "uid": "P4169E866C3094E38", "type": "prometheus" },
          "targets": [
            {
              "datasource": { "uid": "P4169E866C3094E38", "type": "prometheus" },
              "expr": "(time() - willikins_heartbeat_last_success_timestamp) / 60",
              "instant": true,
              "format": "table",
              "refId": "A"
            }
          ],
          "fieldConfig": {
            "defaults": {
              "custom": {
                "align": "auto",
                "cellOptions": { "type": "auto" },
                "inspect": false
              },
              "thresholds": {
                "mode": "absolute",
                "steps": [
                  { "color": "green", "value": null },
                  { "color": "yellow", "value": 60 },
                  { "color": "red", "value": 180 }
                ]
              }
            },
            "overrides": [
              {
                "matcher": { "id": "byName", "options": "Value" },
                "properties": [
                  { "id": "displayName", "value": "Minutes Since Last Success" },
                  { "id": "custom.cellOptions", "value": { "type": "color-background" } }
                ]
              }
            ]
          },
          "transformations": [
            {
              "id": "filterFieldsByName",
              "options": {
                "include": { "names": ["job", "Value"] }
              }
            }
          ]
        },
        {
          "id": 3,
          "title": "Endpoint Probes",
          "type": "table",
          "gridPos": { "h": 8, "w": 24, "x": 0, "y": 8 },
          "datasource": { "uid": "P4169E866C3094E38", "type": "prometheus" },
          "targets": [
            {
              "datasource": { "uid": "P4169E866C3094E38", "type": "prometheus" },
              "expr": "probe_success{probe_group=\"feature_health\"}",
              "instant": true,
              "format": "table",
              "refId": "A"
            }
          ],
          "fieldConfig": {
            "defaults": {
              "custom": {
                "align": "auto",
                "cellOptions": { "type": "auto" },
                "inspect": false
              },
              "mappings": [
                { "type": "value", "options": { "0": { "text": "DOWN", "color": "red" }, "1": { "text": "UP", "color": "green" } } }
              ]
            },
            "overrides": [
              {
                "matcher": { "id": "byName", "options": "Value" },
                "properties": [
                  { "id": "displayName", "value": "Success" },
                  { "id": "custom.cellOptions", "value": { "type": "color-background" } }
                ]
              }
            ]
          },
          "transformations": [
            {
              "id": "filterFieldsByName",
              "options": {
                "include": { "names": ["instance", "Value"] }
              }
            }
          ]
        },
        {
          "id": 4,
          "title": "Pod Status",
          "type": "table",
          "gridPos": { "h": 8, "w": 24, "x": 0, "y": 16 },
          "datasource": { "uid": "P4169E866C3094E38", "type": "prometheus" },
          "targets": [
            {
              "datasource": { "uid": "P4169E866C3094E38", "type": "prometheus" },
              "expr": "kube_pod_status_phase{namespace=~\"secure-agent-pod|n8n-01|paperclip-system\", phase=\"Running\"}",
              "instant": true,
              "format": "table",
              "refId": "A"
            }
          ],
          "fieldConfig": {
            "defaults": {
              "custom": {
                "align": "auto",
                "cellOptions": { "type": "auto" },
                "inspect": false
              }
            },
            "overrides": []
          },
          "transformations": [
            {
              "id": "filterFieldsByName",
              "options": {
                "include": { "names": ["namespace", "pod", "phase", "Value"] }
              }
            },
            {
              "id": "organize",
              "options": {
                "renameByName": { "Value": "Count" }
              }
            }
          ]
        }
      ]
    }
```

**Note:** The dashboard JSON may need fine-tuning after first deployment (panel sizing, field mappings, threshold colors). Use the scratch-dashboard workflow described in the spec: open the provisioned dashboard → "Save as" scratch copy → edit in UI → export JSON → update ConfigMap → commit → delete scratch.

- [x] **Step 2: Validate YAML syntax**

```bash
python3 -c "
import yaml, json
doc = yaml.safe_load(open('apps/grafana-alerting/manifests/dashboard-cm.yaml'))
# Verify the embedded JSON is valid
json.loads(doc['data']['feature-health.json'])
print('YAML and embedded JSON both valid')
"
```

Expected: `YAML and embedded JSON both valid`

- [x] **Step 3: Commit**

```bash
git add apps/grafana-alerting/manifests/dashboard-cm.yaml
git commit -m "feat(obs): add Feature Health dashboard ConfigMap (provider + JSON)"
```

---

### Task 7: Update victoria-metrics Values (Mounts + Secrets)

**Files:**
- Modify: `apps/victoria-metrics/values.yaml`

**Context:** The Grafana subchart in victoria-metrics-k8s-stack supports `extraConfigmapMounts` (list of volume mounts from ConfigMaps) and `envFromSecrets` (list of Secrets to inject as env vars). The existing `extraConfigmapMounts` has 1 entry (VictoriaLogs datasource). The existing `envFromSecret` (singular) references `grafana-oidc-secret`. We switch to `envFromSecrets` (plural, list format) to support multiple secrets.

- [x] **Step 1: Add extraConfigmapMounts entries**

In `apps/victoria-metrics/values.yaml`, append 5 mount entries to the existing `extraConfigmapMounts` list (3 alerting files + 2 dashboard files from the 4 ConfigMaps):

```yaml
  extraConfigmapMounts:
    - name: victorialogs-datasource
      mountPath: /etc/grafana/provisioning/datasources/victorialogs.yaml
      subPath: victorialogs-datasource.yaml
      configMap: grafana-victorialogs-datasource
      readOnly: true
    # --- Alerting provisioning (rules, contact points, notification policy) ---
    - name: alerting-rules
      mountPath: /etc/grafana/provisioning/alerting/alert-rules.yaml
      subPath: alert-rules.yaml
      configMap: grafana-alerting-rules
      readOnly: true
    - name: alerting-contact-points
      mountPath: /etc/grafana/provisioning/alerting/contact-points.yaml
      subPath: contact-points.yaml
      configMap: grafana-alerting-contact-points
      readOnly: true
    - name: alerting-notification-policy
      mountPath: /etc/grafana/provisioning/alerting/notification-policy.yaml
      subPath: notification-policy.yaml
      configMap: grafana-alerting-notification-policy
      readOnly: true
    # --- Dashboard provisioning (provider config + JSON) ---
    - name: dashboard-provider
      mountPath: /etc/grafana/provisioning/dashboards/feature-health-provider.yaml
      subPath: feature-health-provider.yaml
      configMap: grafana-alerting-dashboard
      readOnly: true
    - name: dashboard-json
      mountPath: /var/lib/grafana/dashboards/feature-health/feature-health.json
      subPath: feature-health.json
      configMap: grafana-alerting-dashboard
      readOnly: true
```

- [x] **Step 2: Switch envFromSecret to envFromSecrets**

Replace the singular `envFromSecret` with the plural `envFromSecrets` list format to support both the existing OIDC secret and the new alerting secrets:

```yaml
  # Replace this line:
  #   envFromSecret: grafana-oidc-secret
  # With:
  envFromSecrets:
    - name: grafana-oidc-secret
      optional: false
    - name: grafana-alerting-secrets
      optional: true
```

`optional: true` on the alerting secrets prevents Grafana from failing to start if the ExternalSecret hasn't synced yet (first-boot race condition). The OIDC secret is `optional: false` because Grafana OIDC login breaks without it.

- [x] **Step 3: Verify the complete values file**

The full `grafana:` section in `apps/victoria-metrics/values.yaml` should now look like:

```yaml
grafana:
  enabled: true
  service:
    type: LoadBalancer
    loadBalancerIP: 192.168.55.203
  persistence:
    enabled: true
    storageClassName: longhorn
    size: 1Gi
  plugins:
    - victoriametrics-logs-datasource
  extraConfigmapMounts:
    - name: victorialogs-datasource
      mountPath: /etc/grafana/provisioning/datasources/victorialogs.yaml
      subPath: victorialogs-datasource.yaml
      configMap: grafana-victorialogs-datasource
      readOnly: true
    - name: alerting-rules
      mountPath: /etc/grafana/provisioning/alerting/alert-rules.yaml
      subPath: alert-rules.yaml
      configMap: grafana-alerting-rules
      readOnly: true
    - name: alerting-contact-points
      mountPath: /etc/grafana/provisioning/alerting/contact-points.yaml
      subPath: contact-points.yaml
      configMap: grafana-alerting-contact-points
      readOnly: true
    - name: alerting-notification-policy
      mountPath: /etc/grafana/provisioning/alerting/notification-policy.yaml
      subPath: notification-policy.yaml
      configMap: grafana-alerting-notification-policy
      readOnly: true
    - name: dashboard-provider
      mountPath: /etc/grafana/provisioning/dashboards/feature-health-provider.yaml
      subPath: feature-health-provider.yaml
      configMap: grafana-alerting-dashboard
      readOnly: true
    - name: dashboard-json
      mountPath: /var/lib/grafana/dashboards/feature-health/feature-health.json
      subPath: feature-health.json
      configMap: grafana-alerting-dashboard
      readOnly: true
  envFromSecrets:
    - name: grafana-oidc-secret
      optional: false
    - name: grafana-alerting-secrets
      optional: true
  grafana.ini:
    server:
      root_url: https://grafana.frank.derio.net
    auth.generic_oauth:
      enabled: true
      name: Authentik
      client_id: grafana
      client_secret: ${GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET}
      scopes: openid profile email groups offline_access
      auth_url: https://auth.frank.derio.net/application/o/authorize/
      token_url: https://auth.frank.derio.net/application/o/token/
      api_url: https://auth.frank.derio.net/application/o/userinfo/
      role_attribute_path: "contains(groups[*], 'root-admins') && 'Admin' || contains(groups[*], 'root-devops') && 'Editor' || 'Viewer'"
      allow_assign_grafana_admin: true
```

- [x] **Step 4: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('apps/victoria-metrics/values.yaml'))"
```

- [x] **Step 5: Commit**

```bash
git add apps/victoria-metrics/values.yaml
git commit -m "feat(obs): wire grafana alerting ConfigMaps + secrets into victoria-metrics values"
```

---

### Task 8: Deploy and Verify File-Provisioned Resources

**Files:** None (cluster operations)

**Context:** After pushing, ArgoCD auto-syncs the new `grafana-alerting` Application and the updated `victoria-metrics` Application. The Grafana pod restarts to pick up the new mounts. At this point, both API-provisioned and file-provisioned resources coexist — Grafana does NOT deduplicate them.

- [ ] **Step 1: Push the branch and wait for ArgoCD sync**

```bash
git push origin HEAD
```

Watch for sync in ArgoCD (or use CLI):

```bash
source .env
argocd app list --port-forward --port-forward-namespace argocd | grep -E 'grafana-alerting|victoria-metrics'
```

Expected: `grafana-alerting` shows `Synced`/`Healthy`. `victoria-metrics` shows `Synced` (may briefly show `Progressing` as Grafana pod restarts).

- [ ] **Step 2: Verify the ExternalSecret synced**

```bash
kubectl get externalsecret -n monitoring grafana-alerting-secrets
```

Expected: `SecretSynced` status. If it shows `SecretSyncedError`, check that the 3 keys exist in Infisical.

- [ ] **Step 3: Verify Grafana pod is running with new mounts**

```bash
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana
kubectl describe pod -n monitoring -l app.kubernetes.io/name=grafana | grep -A2 "alerting\|dashboard"
```

Expected: Pod in `Running` state with the 5 new volume mounts visible.

- [ ] **Step 4: Verify file-provisioned alert rules appear**

```bash
GRAFANA_AUTH="admin:$(kubectl get secret -n monitoring victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)"
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules" | \
  python3 -c "import json,sys; rules=json.load(sys.stdin); [print(f'{r[\"uid\"]} (provenance: {r.get(\"provenance\",\"none\")})') for r in rules]"
```

Expected: Each rule UID appears **twice** — once with `provenance: file` (new) and once with `provenance: none` or `provenance: api` (old). This confirms file-provisioned versions loaded correctly.

- [ ] **Step 5: Verify file-provisioned contact points appear**

```bash
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/contact-points" | python3 -m json.tool
```

Expected: Contact points with `provenance: file` present. Telegram UID `efi04e0201jb4f` appears in file-provisioned version.

- [ ] **Step 6: Verify notification policy**

```bash
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/policies" | python3 -m json.tool
```

Expected: Routing tree with 3 routes (severity=critical, severity=warning, grafana_folder=Feature Health).

- [ ] **Step 7: Verify Feature Health dashboard in feature-health folder**

```bash
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/dashboards/uid/fh-overview" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Title: {d[\"dashboard\"][\"title\"]}, Folder: {d[\"meta\"][\"folderTitle\"]}, Panels: {len(d[\"dashboard\"][\"panels\"])}')"
```

Expected: `Title: Feature Health, Folder: feature-health, Panels: 4`

---

### Task 9: Delete API-Provisioned Duplicates (Migration)

**Files:** None (cluster API operations)

**Context:** API-provisioned resources must be deleted so only file-provisioned versions remain. Grafana treats them as separate objects — leaving both causes confusion in the UI (duplicate rules, duplicate contact points). Delete via the Grafana provisioning API. The blog post `operating/15-health-monitoring` documents the UIDs.

```yaml
# manual-operation
id: obs-grafana-alerting-delete-api-provisioned
layer: obs
app: grafana-alerting
plan: docs/superpowers/plans/2026-04-08--obs--grafana-alerting-as-code.md
when: After Task 8 verification confirms file-provisioned resources work
why_manual: API-provisioned Grafana resources can only be deleted via REST API calls
commands:
  - |
    GRAFANA_AUTH="admin:$(kubectl get secret -n monitoring victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)"

    # Delete API-provisioned alert rules (only deletes non-file-provisioned copies)
    for uid in exercise-reminder-stale session-manager-stale audit-digest-stale endpoint-down agent-pod-not-running; do
      echo "Deleting API-provisioned rule: $uid"
      curl -sk -u "$GRAFANA_AUTH" -X DELETE \
        "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules/$uid" \
        -H "X-Disable-Provenance: true"
    done

    # Note: File-provisioned rules with the same UID cannot be deleted via API
    # (Grafana returns 400 for file-provisioned resources). If the DELETE returns
    # 400 "cannot delete provisioned resource", the API version was already deleted
    # or never existed separately.
  - |
    # Delete the API-provisioned notification policy by resetting to default
    # File-provisioned policy takes precedence and will be reloaded on next restart
    # This step may not be needed if file-provisioning already overrides the API version
    echo "Notification policy — file-provisioned version takes precedence, skip manual delete"
  - |
    # Delete API-provisioned contact points if they exist as separate objects
    # Check for duplicates first:
    curl -sk -u "$GRAFANA_AUTH" \
      "https://grafana.frank.derio.net/api/v1/provisioning/contact-points" | \
      python3 -c "import json,sys; cps=json.load(sys.stdin); [print(f'{cp[\"uid\"]}: {cp[\"name\"]} (provenance: {cp.get(\"provenance\",\"none\")})') for cp in cps]"
    # Delete any with provenance != file (these are the API-provisioned originals)
  - |
    # Delete the old API-provisioned Feature Health dashboard (if it exists at root level)
    # The file-provisioned version lives in the feature-health folder with the same UID
    # Grafana may have already merged them or the old one may have a different internal ID
    curl -sk -u "$GRAFANA_AUTH" \
      "https://grafana.frank.derio.net/api/dashboards/uid/fh-overview" | python3 -m json.tool
    # If the response shows folderTitle != "feature-health", delete the old one:
    # curl -sk -u "$GRAFANA_AUTH" -X DELETE "https://grafana.frank.derio.net/api/dashboards/uid/fh-overview"
verify:
  - 'curl -sk -u "$GRAFANA_AUTH" "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules" | python3 -c "import json,sys; rules=json.load(sys.stdin); assert all(r.get(\"provenance\")==\"file\" for r in rules), \"Non-file rules still exist\"; print(f\"OK: {len(rules)} rules, all file-provisioned\")"'
  - 'curl -sk -u "$GRAFANA_AUTH" "https://grafana.frank.derio.net/api/v1/provisioning/contact-points" | python3 -c "import json,sys; cps=json.load(sys.stdin); print(f\"Contact points: {len(cps)}\"); [print(f\"  {cp[\"name\"]}: provenance={cp.get(\"provenance\",\"none\")}\") for cp in cps]"'
status: pending
```

- [ ] **Step 1: Set up auth variable**

```bash
source .env
GRAFANA_AUTH="admin:$(kubectl get secret -n monitoring victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)"
```

- [ ] **Step 2: Delete API-provisioned alert rules**

```bash
for uid in exercise-reminder-stale session-manager-stale audit-digest-stale endpoint-down agent-pod-not-running; do
  echo "Deleting API-provisioned rule: $uid"
  HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" -u "$GRAFANA_AUTH" -X DELETE \
    "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules/$uid" \
    -H "X-Disable-Provenance: true")
  echo "  HTTP $HTTP_CODE"
done
```

Expected: `HTTP 204` (deleted) or `HTTP 400` (already file-provisioned, no separate API copy). Both are OK.

- [ ] **Step 3: Check for duplicate contact points and delete API copies**

```bash
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/contact-points" | \
  python3 -c "
import json, sys
cps = json.load(sys.stdin)
for cp in cps:
    prov = cp.get('provenance', 'none')
    print(f'{cp[\"uid\"]}: {cp[\"name\"]} (provenance: {prov})')
    if prov != 'file' and cp['name'] in ['Telegram - Willikins', 'Health Bridge Webhook']:
        print(f'  → DELETE this one (API-provisioned duplicate)')
"
```

Delete any identified API-provisioned duplicates:

```bash
# Only run for UIDs identified as API-provisioned duplicates in the output above
# curl -sk -u "$GRAFANA_AUTH" -X DELETE \
#   "https://grafana.frank.derio.net/api/v1/provisioning/contact-points/<UID>" \
#   -H "X-Disable-Provenance: true"
```

- [ ] **Step 4: Restart Grafana pod to flush alertmanager dedup state**

Required after contact point changes (gotcha: alertmanager treats previously-fired alerts as "already notified" for the default repeat_interval after re-provisioning).

```bash
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
```

Wait for the pod to come back:

```bash
kubectl wait --for=condition=Ready pod -n monitoring -l app.kubernetes.io/name=grafana --timeout=120s
```

---

### Task 10: End-to-End Verification

**Files:** None (cluster verification)

**Context:** Verify the full alerting chain works after migration. This matches the verification checklist from the spec.

```yaml
# manual-operation
id: obs-grafana-alerting-e2e-verification
layer: obs
app: grafana-alerting
plan: docs/superpowers/plans/2026-04-08--obs--grafana-alerting-as-code.md
when: After Task 9 migration completes
why_manual: Requires inspecting Grafana UI, triggering test alerts, and checking Telegram delivery
commands:
  - 'GRAFANA_AUTH="admin:$(kubectl get secret -n monitoring victoria-metrics-grafana -o jsonpath='\''{.data.admin-password}'\'' | base64 -d)"'
  - 'curl -sk -u "$GRAFANA_AUTH" "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules" | python3 -c "import json,sys; rules=json.load(sys.stdin); [print(f\"{r[\"uid\"]}: provenance={r.get(\"provenance\")}\") for r in rules]"'
  - 'curl -sk -u "$GRAFANA_AUTH" "https://grafana.frank.derio.net/api/v1/provisioning/contact-points" | python3 -m json.tool'
  - 'curl -sk -u "$GRAFANA_AUTH" "https://grafana.frank.derio.net/api/v1/provisioning/policies" | python3 -m json.tool'
  - 'curl -sk -u "$GRAFANA_AUTH" "https://grafana.frank.derio.net/api/dashboards/uid/fh-overview" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"Folder: {d[\"meta\"][\"folderTitle\"]}, Panels: {len(d[\"dashboard\"][\"panels\"])}\")"'
verify:
  - 'All 5 rules visible, provenance=file'
  - 'Both contact points present, provenance=file'
  - 'Notification policy has 3 routes'
  - 'Dashboard in feature-health folder with 4 panels'
  - 'Telegram notification arrives for a test alert'
status: pending
```

- [ ] **Step 1: Verify all 5 alert rules are file-provisioned**

```bash
GRAFANA_AUTH="admin:$(kubectl get secret -n monitoring victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)"
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules" | \
  python3 -c "
import json, sys
rules = json.load(sys.stdin)
expected = {'exercise-reminder-stale', 'session-manager-stale', 'audit-digest-stale', 'endpoint-down', 'agent-pod-not-running'}
found = {r['uid'] for r in rules}
missing = expected - found
extra = found - expected
for r in rules:
    status = '✓' if r.get('provenance') == 'file' else '✗ NOT FILE'
    print(f'  {status} {r[\"uid\"]} (provenance: {r.get(\"provenance\", \"none\")})')
if missing: print(f'MISSING: {missing}')
if not missing: print(f'All {len(expected)} expected rules present')
"
```

Expected: All 5 rules present with `provenance: file`.

- [ ] **Step 2: Verify contact points and notification policy**

```bash
echo "=== Contact Points ==="
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/contact-points" | \
  python3 -c "import json,sys; [print(f'  {cp[\"name\"]}: provenance={cp.get(\"provenance\",\"none\")}') for cp in json.load(sys.stdin)]"

echo "=== Notification Policy ==="
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/policies" | \
  python3 -c "
import json, sys
p = json.load(sys.stdin)
print(f'  Root receiver: {p[\"receiver\"]}')
print(f'  Routes: {len(p.get(\"routes\", []))}')
for r in p.get('routes', []):
    print(f'    → {r[\"receiver\"]} (matchers: {r.get(\"object_matchers\", r.get(\"matchers\", []))}), continue: {r.get(\"continue\", False)}')
"
```

Expected: 2 contact points (both `provenance: file`), 3 routes in the policy.

- [ ] **Step 3: Verify dashboard**

```bash
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/dashboards/uid/fh-overview" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
meta = d['meta']
dash = d['dashboard']
print(f'Title: {dash[\"title\"]}')
print(f'Folder: {meta[\"folderTitle\"]}')
print(f'Provisioned: {meta.get(\"provisioned\", False)}')
print(f'Panels: {len(dash[\"panels\"])}')
for p in dash['panels']:
    print(f'  [{p[\"id\"]}] {p[\"title\"]} ({p[\"type\"]})')
"
```

Expected: Title `Feature Health`, Folder `feature-health`, Provisioned `True`, 4 panels.

- [ ] **Step 4: PVC loss simulation — restart Grafana and verify survival**

```bash
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl wait --for=condition=Ready pod -n monitoring -l app.kubernetes.io/name=grafana --timeout=120s
```

Then re-run Steps 1–3 above. All rules, contact points, policy, and dashboard should survive the restart (loaded from ConfigMaps, not PVC).

- [ ] **Step 5: Trigger test alert (optional live verification)**

Temporarily lower the `exercise-reminder-stale` threshold to 60s to trigger a test alert:

1. Edit `apps/grafana-alerting/manifests/alert-rules-cm.yaml` — change `10800` to `60` in the exercise-reminder-stale rule's threshold params
2. Commit and push — wait for ArgoCD sync
3. Restart Grafana pod to reload provisioning files
4. Wait ~5m for the alert to fire (the heartbeat may be >60s stale)
5. Verify: Telegram notification arrives, Health Bridge webhook fires
6. Restore threshold to `10800`, commit, push, restart Grafana

---

### Task 11: Update Blog Posts

**Files:**
- Modify: `blog/content/operating/15-health-monitoring/index.md`

**Context:** The operating post currently documents API-provisioned management commands (GET/PUT/DELETE via curl). After migration, alert rules are read-only in the UI (file-provisioned). Update the post to reflect the new management workflow.

- [x] **Step 1: Add a "File-Provisioned Alerting" section**

Add after the "Grafana Alert Management" section in `blog/content/operating/15-health-monitoring/index.md`:

```markdown
## File-Provisioned Alerting (as-code)

As of April 2026, all Grafana alerting configuration is file-provisioned via ConfigMaps in `apps/grafana-alerting/manifests/`:

| ConfigMap | Provisioning Path | Contents |
|-----------|-------------------|----------|
| `grafana-alerting-rules` | `/etc/grafana/provisioning/alerting/alert-rules.yaml` | 5 alert rules in 3 groups |
| `grafana-alerting-contact-points` | `/etc/grafana/provisioning/alerting/contact-points.yaml` | Telegram + Health Bridge webhook |
| `grafana-alerting-notification-policy` | `/etc/grafana/provisioning/alerting/notification-policy.yaml` | Severity-based routing tree |
| `grafana-alerting-dashboard` | `/etc/grafana/provisioning/dashboards/` + `/var/lib/grafana/dashboards/feature-health/` | Feature Health dashboard |

### Editing Alert Rules

File-provisioned rules are **read-only in the UI**. To modify:

1. Edit the ConfigMap YAML in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`
2. Commit and push — ArgoCD syncs the ConfigMap
3. Restart Grafana pod to reload provisioning files:
   ```bash
   kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
   ```

### Editing the Dashboard

1. Open the provisioned dashboard in Grafana UI, click "Save as" to create a scratch copy
2. Edit the scratch copy freely in the UI
3. Export the final JSON (Share → Export → Save to file)
4. Replace the `feature-health.json` content in `apps/grafana-alerting/manifests/dashboard-cm.yaml`
5. Commit, push, restart Grafana pod
6. Delete the scratch dashboard
```

- [x] **Step 2: Mark API commands as historical**

Add a note at the top of the existing "Grafana Alert Management" section:

```markdown
> **Historical:** The curl commands below were used when alerts were API-provisioned. Since April 2026, alerting is file-provisioned via ConfigMaps. See [File-Provisioned Alerting](#file-provisioned-alerting-as-code) above. These commands still work for **reading** alert state but not for modifying rules.
```

- [x] **Step 3: Commit**

```bash
git add blog/content/operating/15-health-monitoring/index.md
git commit -m "docs(obs): update health monitoring ops post for file-provisioned alerting"
```

---

### Task 12: Update Gotchas

**Files:**
- Modify: `.claude/rules/frank-gotchas.md`

- [x] **Step 1: Add provisioning gotcha**

Append to `.claude/rules/frank-gotchas.md`:

```markdown
- Grafana alerting (rules, contact points, notification policy) and the Feature Health dashboard are file-provisioned via ConfigMaps in `apps/grafana-alerting/manifests/`. They are read-only in the UI. Edit the ConfigMap YAML, commit, push, then restart the Grafana pod (`kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana`) — provisioning files are read at boot, not watched
```

- [x] **Step 2: Commit**

```bash
git add .claude/rules/frank-gotchas.md
git commit -m "docs(obs): add grafana file-provisioning gotcha"
```

---

## Summary

| Task | What | Type |
|------|------|------|
| 1 | ArgoCD Application CR | Code |
| 2 | Alert rules ConfigMap (5 rules, 5 groups by eval interval) | Code |
| 3 | Contact points ConfigMap (Telegram + Health Bridge) | Code |
| 4 | Notification policy ConfigMap (routing tree) | Code |
| 5 | ExternalSecret for alerting env vars | Code |
| 6 | Dashboard ConfigMap (provider + JSON) | Code |
| 7 | victoria-metrics values (mounts + secrets) | Code |
| 8 | Deploy + verify file-provisioned resources | Cluster ops |
| 9 | Delete API-provisioned duplicates | Manual migration |
| 10 | End-to-end verification | Manual verification |
| 11 | Update blog operating post | Docs |
| 12 | Update gotchas | Docs |

**Tasks 1–7** are pure code (can be parallelized by subagents). **Tasks 8–10** require cluster access and must be sequential. **Tasks 11–12** are docs updates that can run in parallel after migration.
