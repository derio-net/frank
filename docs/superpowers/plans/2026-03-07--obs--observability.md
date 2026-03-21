# Observability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy VictoriaMetrics (metrics), VictoriaLogs (logs), Fluent Bit (log shipper), and Grafana (dashboards) into the `monitoring` namespace via ArgoCD, with Grafana exposed at `192.168.55.203`.

**Architecture:** Three ArgoCD apps (`victoria-metrics`, `victoria-logs`, `fluent-bit`) all in the `monitoring` namespace. VictoriaMetrics k8s-stack handles metrics scraping + Grafana. VictoriaLogs handles log storage. Fluent Bit DaemonSet ships pod logs from all nodes to VictoriaLogs. Grafana has both as datasources.

**Tech Stack:** `victoria-metrics/victoria-metrics-k8s-stack`, `victoria-metrics/victoria-logs-single`, `fluent/fluent-bit`, Longhorn PVCs, Cilium L2 LoadBalancer.
**Status:** Deployed

---

## Task 1: Create monitoring namespace

**Files:**
- Create: `apps/root/templates/ns-monitoring.yaml`

**Step 1: Create the namespace manifest**

```yaml
# apps/root/templates/ns-monitoring.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: monitoring
```

**Step 2: Verify ArgoCD picks it up**

```bash
source .env
argocd app sync root --port-forward --port-forward-namespace argocd
argocd app get root --port-forward --port-forward-namespace argocd
```

Expected: `root` app shows the new namespace template, no errors.

**Step 3: Commit**

```bash
git add apps/root/templates/ns-monitoring.yaml
git commit -m "feat(monitoring): add monitoring namespace"
```

---

## Task 2: Add victoria-metrics ArgoCD Application

**Files:**
- Create: `apps/victoria-metrics/values.yaml`
- Create: `apps/root/templates/victoria-metrics.yaml`

**Step 1: Check latest chart version**

```bash
helm repo add victoria-metrics https://victoriametrics.github.io/helm-charts/
helm repo update
helm search repo victoria-metrics/victoria-metrics-k8s-stack --versions | head -5
```

Note the latest version — use it in the Application CR below.

**Step 2: Create values file**

```yaml
# apps/victoria-metrics/values.yaml

# Disable alerting — Layer 8+
vmalert:
  enabled: false
alertmanager:
  enabled: false

# VMSingle — single-node metrics storage
vmsingle:
  spec:
    retentionPeriod: "1"   # 1 month
    storage:
      volumeClaimTemplate:
        spec:
          storageClassName: longhorn
          resources:
            requests:
              storage: 20Gi

# Grafana — exposed via Cilium L2 LoadBalancer
grafana:
  enabled: true
  service:
    type: LoadBalancer
    loadBalancerIP: 192.168.55.203
  persistence:
    enabled: true
    storageClassName: longhorn
    size: 1Gi
  # Install VictoriaLogs datasource plugin
  plugins:
    - victoriametrics-logs-datasource
  additionalDataSources:
    - name: VictoriaLogs
      type: victoriametrics-logs-datasource
      access: proxy
      url: http://victoria-logs-victoria-logs-single.monitoring.svc.cluster.local:9428
      isDefault: false
```

**Step 3: Create Application CR**

Replace `<VERSION>` with the latest chart version found in Step 1.

```yaml
# apps/root/templates/victoria-metrics.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: victoria-metrics
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://victoriametrics.github.io/helm-charts/
      chart: victoria-metrics-k8s-stack
      targetRevision: "<VERSION>"
      helm:
        releaseName: victoria-metrics
        valueFiles:
          - $values/apps/victoria-metrics/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: monitoring
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

**Step 4: Sync and verify namespace exists**

```bash
argocd app sync root --port-forward --port-forward-namespace argocd
kubectl get namespace monitoring
```

Expected: namespace `monitoring` exists.

**Step 5: Commit**

```bash
git add apps/victoria-metrics/values.yaml apps/root/templates/victoria-metrics.yaml
git commit -m "feat(monitoring): add victoria-metrics-k8s-stack ArgoCD app"
```

---

## Task 3: Deploy victoria-metrics and verify

**Step 1: Push and watch rollout**

```bash
git push
argocd app sync victoria-metrics --port-forward --port-forward-namespace argocd
kubectl -n monitoring get pods -w
```

Expected: pods for `vmsingle`, `vmagent`, `node-exporter` (one per node), `kube-state-metrics`, `grafana` all reach `Running`.

**Step 2: Verify Grafana is reachable**

```bash
curl -s http://192.168.55.203/api/health | python3 -m json.tool
```

Expected: `{"database": "ok", "version": "...", ...}`

Default credentials: `admin` / `prom-operator` (or check the generated secret):

```bash
kubectl -n monitoring get secret victoria-metrics-grafana \
  -o jsonpath='{.data.admin-password}' | base64 -d
```

**Step 3: Verify VMSingle is scraping**

Open Grafana at `http://192.168.55.203`. Navigate to **Explore → VictoriaMetrics datasource**.

Run query:
```
up
```

Expected: multiple time series, one per scraped target. Confirm nodes, pods, kube-state-metrics are all present.

**Step 4: Verify node-exporter is on all nodes**

```bash
kubectl -n monitoring get pods -l app.kubernetes.io/name=node-exporter -o wide
```

Expected: 7 pods — one per node (mini-1/2/3, gpu-1, pc-1, raspi-1/2).

---

## Task 4: Add victoria-logs ArgoCD Application

**Files:**
- Create: `apps/victoria-logs/values.yaml`
- Create: `apps/root/templates/victoria-logs.yaml`

**Step 1: Check latest chart version**

```bash
helm search repo victoria-metrics/victoria-logs-single --versions | head -5
```

Note the latest version.

**Step 2: Create values file**

```yaml
# apps/victoria-logs/values.yaml
server:
  retentionPeriod: 14d
  persistentVolume:
    enabled: true
    size: 20Gi
    storageClass: longhorn
  service:
    type: ClusterIP
    port: 9428
```

**Step 3: Create Application CR**

Replace `<VERSION>` with the latest chart version.

```yaml
# apps/root/templates/victoria-logs.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: victoria-logs
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://victoriametrics.github.io/helm-charts/
      chart: victoria-logs-single
      targetRevision: "<VERSION>"
      helm:
        releaseName: victoria-logs
        valueFiles:
          - $values/apps/victoria-logs/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: monitoring
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
```

**Step 4: Commit**

```bash
git add apps/victoria-logs/values.yaml apps/root/templates/victoria-logs.yaml
git commit -m "feat(monitoring): add victoria-logs-single ArgoCD app"
```

---

## Task 5: Deploy victoria-logs and verify

**Step 1: Push and sync**

```bash
git push
argocd app sync root --port-forward --port-forward-namespace argocd
argocd app sync victoria-logs --port-forward --port-forward-namespace argocd
kubectl -n monitoring get pods -l app.kubernetes.io/name=victoria-logs-single -w
```

Expected: `victoria-logs-victoria-logs-single-*` pod reaches `Running`.

**Step 2: Verify VictoriaLogs endpoint**

```bash
kubectl -n monitoring port-forward svc/victoria-logs-victoria-logs-single 9428:9428 &
curl -s http://localhost:9428/health
```

Expected: `OK`

Kill the port-forward: `kill %1`

**Step 3: Verify PVC is bound**

```bash
kubectl -n monitoring get pvc
```

Expected: PVC for victoria-logs shows `Bound` on Longhorn.

---

## Task 6: Add fluent-bit ArgoCD Application

**Files:**
- Create: `apps/fluent-bit/values.yaml`
- Create: `apps/root/templates/fluent-bit.yaml`

**Step 1: Check latest chart version**

```bash
helm repo add fluent https://fluent.github.io/helm-charts
helm repo update
helm search repo fluent/fluent-bit --versions | head -5
```

Note the latest version.

**Step 2: Create values file**

Fluent Bit ships all pod logs to VictoriaLogs. Needs tolerations to run on control-plane and GPU nodes.

```yaml
# apps/fluent-bit/values.yaml

# Tolerate all node types so we collect logs from every node
tolerations:
  - key: node-role.kubernetes.io/control-plane
    operator: Exists
    effect: NoSchedule
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule

# Pipeline configuration
config:
  inputs: |
    [INPUT]
        Name              tail
        Path              /var/log/containers/*.log
        multiline.parser  docker, cri
        Tag               kube.*
        Mem_Buf_Limit     5MB
        Skip_Long_Lines   On

  filters: |
    [FILTER]
        Name                kubernetes
        Match               kube.*
        Kube_URL            https://kubernetes.default.svc:443
        Kube_CA_File        /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
        Kube_Token_File     /var/run/secrets/kubernetes.io/serviceaccount/token
        Kube_Tag_Prefix     kube.var.log.containers.
        Merge_Log           On
        Keep_Log            Off
        K8S-Logging.Parser  On
        K8S-Logging.Exclude On

  outputs: |
    [OUTPUT]
        Name            http
        Match           kube.*
        Host            victoria-logs-victoria-logs-single.monitoring.svc.cluster.local
        Port            9428
        URI             /insert/jsonline?_stream_fields=stream,kubernetes_pod_name,kubernetes_namespace_name,kubernetes_container_name&_msg_field=log&_time_field=time
        Format          json_lines
        Json_Date_Key   time
        Json_Date_Format iso8601
        Retry_Limit     False
```

**Step 3: Create Application CR**

Replace `<VERSION>` with the latest chart version.

```yaml
# apps/root/templates/fluent-bit.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: fluent-bit
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  sources:
    - repoURL: https://fluent.github.io/helm-charts
      chart: fluent-bit
      targetRevision: "<VERSION>"
      helm:
        releaseName: fluent-bit
        valueFiles:
          - $values/apps/fluent-bit/values.yaml
    - repoURL: {{ .Values.repoURL }}
      targetRevision: {{ .Values.targetRevision }}
      ref: values
  destination:
    server: {{ .Values.destination.server }}
    namespace: monitoring
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
```

**Step 4: Commit**

```bash
git add apps/fluent-bit/values.yaml apps/root/templates/fluent-bit.yaml
git commit -m "feat(monitoring): add fluent-bit ArgoCD app"
```

---

## Task 7: Deploy fluent-bit and verify log flow

**Step 1: Push and sync**

```bash
git push
argocd app sync root --port-forward --port-forward-namespace argocd
argocd app sync fluent-bit --port-forward --port-forward-namespace argocd
kubectl -n monitoring get pods -l app.kubernetes.io/name=fluent-bit -o wide
```

Expected: one Fluent Bit pod per node (7 total), all `Running`.

**Step 2: Check Fluent Bit logs for errors**

```bash
kubectl -n monitoring logs -l app.kubernetes.io/name=fluent-bit --tail=20
```

Expected: no HTTP error responses to VictoriaLogs. Lines like `[engine] flush chunk ... succeeded` are good.

**Step 3: Verify logs arriving in VictoriaLogs**

```bash
kubectl -n monitoring port-forward svc/victoria-logs-victoria-logs-single 9428:9428 &
curl -G http://localhost:9428/select/logsql/query \
  --data-urlencode 'query=*' \
  --data-urlencode 'limit=5'
```

Expected: JSON log entries from the cluster.

Kill the port-forward: `kill %1`

---

## Task 8: Verify VictoriaLogs datasource in Grafana

**Step 1: Open Grafana and check plugin**

Navigate to `http://192.168.55.203` → **Administration → Plugins**.

Search for `VictoriaLogs`. Expected: plugin installed and enabled.

If plugin is missing, check Grafana pod logs:
```bash
kubectl -n monitoring logs -l app.kubernetes.io/name=grafana | grep -i victorialogs
```

If needed, restart Grafana pod to force plugin install:
```bash
kubectl -n monitoring rollout restart deployment victoria-metrics-grafana
```

**Step 2: Verify datasource is configured**

Navigate to **Connections → Data sources**. Expected: two datasources:
- `VictoriaMetrics` (default)
- `VictoriaLogs`

Click **Test** on VictoriaLogs datasource. Expected: green success.

**Step 3: Query logs in Explore**

Navigate to **Explore → VictoriaLogs datasource**.

Run query:
```
{kubernetes_namespace_name="argocd"}
```

Expected: log lines from the ArgoCD namespace.

---

## Task 9: Verify pre-built dashboards

**Step 1: Check bundled dashboards**

In Grafana, navigate to **Dashboards**. The `victoria-metrics-k8s-stack` chart ships with dashboards for:
- Kubernetes cluster overview
- Node exporter (per-node stats)
- Pod resource usage
- VMSingle health

Expected: dashboards visible and showing data (may take 1-2 minutes for initial data).

**Step 2: Verify Longhorn and Cilium metrics appear**

In **Explore → VictoriaMetrics**, run:

```
# Longhorn volumes
longhorn_volume_actual_size_bytes

# Cilium
cilium_endpoint_state
```

Expected: both return data, confirming vmagent is scraping these existing exporters.

---

## Known Gotchas (discovered during deployment)

### 1. Stale ValidatingWebhookConfiguration blocks VMAgent/VMSingle deployment

**Symptom:** VMAgent and/or VMSingle pods never appear after the operator deploys, despite the CRDs existing. Operator logs show:
```
cannot patch finalizers: failed calling webhook "vmagents.operator.victoriametrics.com":
tls: failed to verify certificate: x509: certificate signed by unknown authority
```

**Cause:** A prior failed install left a `ValidatingWebhookConfiguration` with a stale CA bundle. The operator cannot re-register its webhook while the old config exists.

**Fix:** Delete the stale webhook config and let the operator re-register:
```bash
kubectl delete validatingwebhookconfiguration victoria-metrics-victoria-metrics-operator-admission
```
The operator will recreate it with the correct CA within ~10 seconds, and VMAgent/VMSingle will appear immediately after.

**Blog note:** Worth covering — this is a common `victoria-metrics-k8s-stack` first-install pain point.

### 2. Fluent Bit ConfigMap hostname vs actual service name

The `victoria-logs-single` chart appends `-server` to its service name (`victoria-logs-victoria-logs-single-server`), making it longer than expected. The Fluent Bit `Host` must use the full `-server` suffix or DNS resolution fails silently with repeated retry loops.

### 3. additionalDataSources not passed through by victoria-metrics-k8s-stack

The chart manages datasource provisioning via its own ConfigMap (`victoria-metrics-victoria-metrics-k8s-stack-grafana-ds`) and does not forward `grafana.additionalDataSources` from values to the Grafana subchart. The VictoriaLogs datasource must be added via Grafana API or a custom provisioning ConfigMap. See TODO in `apps/victoria-metrics/values.yaml`.

---

## Task 10: Final commit and push

**Step 1: Verify all apps healthy**

```bash
argocd app list --port-forward --port-forward-namespace argocd
```

Expected: `victoria-metrics`, `victoria-logs`, `fluent-bit` all show `Synced` / `Healthy`.

**Step 2: Verify all PVCs bound**

```bash
kubectl -n monitoring get pvc
```

Expected: 3 PVCs bound on Longhorn — VMSingle (20Gi), VictoriaLogs (20Gi), Grafana (1Gi).

**Step 3: Final commit**

```bash
git push
```

Confirm GitHub Actions / ArgoCD remains green.

---

## Task 11: Blog post — `07-observability`

**Files:**
- Create: `blog/content/posts/07-observability/index.md`
- Create: `blog/content/posts/07-observability/cover.png`

**Step 1: Create post directory and frontmatter**

```yaml
---
title: "Observability — VictoriaMetrics Over Prometheus"
date: 2026-MM-DD
draft: false
tags: ["observability", "victoriametrics", "grafana", "fluent-bit"]
summary: "Deploying a resource-efficient observability stack with VictoriaMetrics, VictoriaLogs, and Grafana — a Prometheus alternative that's kinder to RPi nodes."
weight: 8
cover:
  image: cover.png
  alt: "Frank the cluster monster peering into glowing dashboards filled with metrics and log streams"
  relative: true
---
```

**Step 2: Write post sections**

Structure:
1. Why not Prometheus? (resource comparison table)
2. The stack: VictoriaMetrics k8s-stack overview
3. Deploying via ArgoCD (show Application CR, values highlights)
4. VictoriaLogs + Fluent Bit pipeline
5. Grafana datasource configuration (show the plugin trick)
6. Screenshots: Grafana dashboards, log exploration, Cilium/Longhorn metrics
7. References

**Step 3: Generate cover image**

Prompt for Gemini/image generator:
> "A friendly Frankenstein monster sitting at a desk covered in glowing computer monitors, each showing colorful time-series graphs and log streams. The monster is holding a magnifying glass, studying the metrics with curiosity. Dark server room background with blue LED accents. Digital art, warm lighting."

**Step 4: Build and verify**

```bash
cd blog && hugo server --buildDrafts
```

Open `http://localhost:1313` and verify post renders correctly with images.

**Step 5: Publish and commit**

Set `draft: false` in frontmatter.

```bash
cd blog && hugo --minify
git add blog/content/posts/07-observability/
git commit -m "docs(blog): add Phase 7 observability post"
git push
```
