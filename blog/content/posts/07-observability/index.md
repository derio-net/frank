---
title: "Observability — Metrics and Logs with VictoriaMetrics"
date: 2026-03-08
draft: false
tags: ["observability", "victoriametrics", "grafana", "fluent-bit", "victoria-logs"]
summary: "Deploying a resource-efficient observability stack with VictoriaMetrics, VictoriaLogs, and Grafana — and the three gotchas that made it interesting."
weight: 8
cover:
  image: cover.png
  alt: "Frank the cluster monster peering into glowing dashboards filled with metrics and log streams"
  relative: true
---

A Kubernetes cluster without observability is just a box of mystery. Pods crash silently. Memory leaks hide behind restart counts. Network blips become finger-pointing exercises. Phase 7 fixes that: a full metrics and logging stack built around VictoriaMetrics, VictoriaLogs, and Grafana, managed by ArgoCD, backed by Longhorn storage.

Three gotchas made the deployment more interesting than expected. They are documented in full below.

## Why VictoriaMetrics Instead of Prometheus?

The standard choice is `kube-prometheus-stack` — Prometheus, Alertmanager, Grafana, and a bundle of exporters packaged together. It works well and has a huge ecosystem. But it is heavy, and on a homelab cluster where the control-plane nodes are also running workloads, baseline resource consumption matters.

The comparison is not subtle:

| Component | kube-prometheus-stack | victoria-metrics-k8s-stack |
|---|---|---|
| Prometheus / VMSingle | ~1–2 GB RAM | ~50–150 MB RAM |
| Full stack baseline | ~2–4 GB RAM | ~200–400 MB RAM |
| Storage format | TSDB (per-sample blocks) | custom compressed format |
| Ingestion throughput | good | 2–5x higher per benchmark |
| Long-term retention | needs Thanos / Cortex | built-in, single binary |
| PromQL compatibility | native | full (MetricsQL superset) |

VictoriaMetrics is not a drop-in replacement in the sense that it requires rethinking the architecture — but the `victoria-metrics-k8s-stack` Helm chart is deliberately structured to be familiar to anyone who has used `kube-prometheus-stack`. It ships the same CRD patterns (`VMServiceMonitor`, `VMPodMonitor`, analogous to their Prometheus equivalents), the same Grafana dashboards, and the same node-exporter and kube-state-metrics exporters.

For Frank, the Talos Cluster, the math is easy: fewer wasted gigabytes on the control-plane nodes means more headroom for actual workloads. VictoriaMetrics wins.

## The Stack

Four ArgoCD Applications make up the observability layer:

**`victoria-metrics`** — The core chart (`victoria-metrics-k8s-stack` v0.72.4). Deploys:
- `VMSingle` — single-node time-series database with a 20Gi Longhorn PVC and 1-month retention
- `vmagent` — metrics scraping engine; reads `VMServiceMonitor` and `VMPodMonitor` CRDs
- `node-exporter` — DaemonSet on all 6 nodes, exposing hardware and OS metrics
- `kube-state-metrics` — Kubernetes object metrics (pod state, deployment replicas, etc.)
- Grafana — with a Longhorn-backed 1Gi PVC for dashboard persistence, exposed at `192.168.55.203`

**`victoria-logs`** — Separate chart (`victoria-logs-single` v0.11.28). Deploys a single-node log storage server with a 20Gi Longhorn PVC and 14-day retention, accessible within the cluster at port 9428.

**`fluent-bit`** — DaemonSet on all nodes (including GPU and control-plane). Ships container logs from every node to VictoriaLogs via HTTP jsonline.

**Note:** `vmalert` and `alertmanager` are disabled in this phase. Alerting is planned for Phase 9 after the alert rules have been properly tuned. Running alertmanager without tuned rules just produces noise.

## ArgoCD Deployment

Three Application CRs live in `apps/root/templates/`. All three follow the same dual-source pattern: the upstream Helm chart from the VictoriaMetrics or Fluent chart repositories, plus this Git repo as the values reference.

### victoria-metrics Application

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
      targetRevision: "0.72.4"
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

Two sync options deserve attention. `ServerSideApply=true` avoids the annotation size limit that trips up large Helm charts — the victoria-metrics chart generates resources with enough metadata that client-side apply reliably hits the 256KB annotation limit. `RespectIgnoreDifferences=true` works in conjunction with the `ignoreDifferences` block, which tells ArgoCD to stop flagging Secret `/data` as drifted. The chart manages Grafana credentials in a Secret; ArgoCD should not fight it.

### victoria-metrics values highlights

```yaml
# apps/victoria-metrics/values.yaml
vmalert:
  enabled: false
alertmanager:
  enabled: false

# Disabled: service name exceeds 63 chars with this release name
kubeControllerManager:
  enabled: false

vmsingle:
  spec:
    retentionPeriod: "1"   # 1 month
    storage:
      storageClassName: longhorn
      accessModes:
        - ReadWriteOnce
      resources:
        requests:
          storage: 20Gi

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
```

The `kubeControllerManager` scrape is disabled for an unglamorous reason: the generated service name (`victoria-metrics-victoria-metrics-k8s-stack-kube-controller-manager`) is 65 characters long, and Kubernetes service names must be 63 characters or fewer. The chart does not expose a way to override the release name in that specific component, so it goes off for now.

### victoria-logs Application

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
      targetRevision: "0.11.28"
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

The values for VictoriaLogs are deliberately minimal:

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

VictoriaLogs does not need a LoadBalancer service — nothing outside the cluster talks to it directly. Fluent Bit writes to it, and Grafana queries it, both from inside the cluster.

---

## Gotcha 1: The Stale ValidatingWebhookConfiguration

This one cost about an hour.

### Symptom

After the initial sync, `VMSingle` came up healthy. But `vmagent` never appeared — no Deployment, no pods, no events. The ArgoCD UI showed the Application as `Synced/Degraded` with a cryptic error about the `VMAgent` custom resource not reconciling. Running `kubectl get vmagent -n monitoring` showed the object existed. Running `kubectl describe vmagent -n monitoring victoria-metrics-victoria-metrics-agent` showed... nothing obviously wrong.

### Diagnosis

The victoria-metrics operator uses a `ValidatingWebhookConfiguration` to validate its custom resources on creation and update. The sequence of events was:

1. First install: operator deployed, registered webhook with its own CA bundle
2. Something went wrong mid-install (likely the 63-char service name issue above)
3. The Application was deleted and re-installed to start clean
4. On reinstall, the old `ValidatingWebhookConfiguration` remained — it was not owned by the Helm release, so Helm did not delete it
5. The stale webhook pointed at the old operator's TLS certificate, which no longer matched the new pod's certificate
6. Every time the operator tried to reconcile the `VMAgent` resource, the API server called the webhook, the TLS handshake failed, and the reconciliation was silently dropped

The giveaway was in `kubectl get events -n monitoring --sort-by='.lastTimestamp'`:

```text
Warning  FailedCreate  validatingwebhookconfiguration/victoria-metrics-victoria-metrics-operator-admission
  x509: certificate signed by unknown authority
```

### Fix

Delete the stale webhook configuration. The operator re-registers it within seconds:

```bash
kubectl delete validatingwebhookconfiguration \
  victoria-metrics-victoria-metrics-operator-admission
```

Within about 30 seconds, the operator re-created the webhook with a fresh CA bundle matching the current pod's certificate. The `VMAgent` Deployment appeared immediately, pods started, and scraping began.

**The lesson:** When a Kubernetes operator uses admission webhooks and the install/reinstall cycle is not clean, always check for stale `ValidatingWebhookConfiguration` or `MutatingWebhookConfiguration` objects. They survive Helm releases and cause exactly this kind of ghost-in-the-machine behavior where objects exist but nothing happens to them.

---

## Gotcha 2: The Fluent Bit Hostname

### Symptom

Fluent Bit DaemonSet was running on all nodes. No errors in `kubectl logs`. But querying VictoriaLogs showed zero documents. The Fluent Bit logs showed continuous retry loops with no error messages — just `[engine] flush chunk ... retry=true`.

### Diagnosis

Fluent Bit's `[OUTPUT]` block uses an HTTP plugin to forward logs. The `Host` field must resolve to a valid in-cluster DNS name. The initial configuration used:

```text
Host  victoria-logs-victoria-logs-single.monitoring.svc.cluster.local
```

That hostname does not exist. The `victoria-logs-single` chart names its Service with a `-server` suffix: the actual Service name is `victoria-logs-victoria-logs-single-server`. The chart does not document this clearly, and the default Helm release name (`victoria-logs`) combined with the chart name (`victoria-logs-single`) produces a long, non-obvious service name.

To find the correct service name:

```bash
kubectl get svc -n monitoring | grep victoria-logs
```

```text
victoria-logs-victoria-logs-single-server   ClusterIP   10.96.x.x   <none>   9428/TCP
```

### Fix

Update the `Host` in the Fluent Bit output config to use the correct service name:

```yaml
# apps/fluent-bit/values.yaml (correct)
config:
  outputs: |
    [OUTPUT]
        Name            http
        Match           kube.*
        Host            victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local
        Port            9428
        URI             /insert/jsonline?_stream_fields=stream,kubernetes_pod_name,kubernetes_namespace_name,kubernetes_container_name&_msg_field=log&_time_field=time
        Format          json_lines
        Json_Date_Key   time
        Json_Date_Format iso8601
        Retry_Limit     False
```

After the fix was committed and synced, log data started appearing in VictoriaLogs within the next Fluent Bit flush cycle (a few seconds).

**The lesson:** DNS failures in Kubernetes are silent killers. Fluent Bit does not differentiate between "server returned an error" and "DNS lookup failed" in its retry log output. When a log shipper shows retries with no error detail, the first check should always be whether the destination hostname resolves at all — a one-liner from any pod in the namespace confirms it: `kubectl exec -n monitoring <any-pod> -- nslookup <hostname>`.

---

## VictoriaLogs + Fluent Bit: The Pipeline

With the hostname corrected, the pipeline is clean. Fluent Bit runs as a DaemonSet across all nodes — including the GPU node and control-plane nodes, which carry taints that would normally prevent scheduling:

```yaml
# apps/fluent-bit/values.yaml (tolerations)
tolerations:
  - key: node-role.kubernetes.io/control-plane
    operator: Exists
    effect: NoSchedule
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
```

Without these tolerations, the control-plane nodes (mini-1, mini-2, mini-3) and the GPU node (gpu-1) would not get a Fluent Bit pod, leaving their container logs uncollected.

The full pipeline is three stages:

**INPUT — tail:** Reads from `/var/log/containers/*.log` on the host filesystem. The `multiline.parser docker, cri` handles both Docker-format logs (from older container runtimes) and CRI-format logs (what Talos uses with containerd). `Mem_Buf_Limit 5MB` prevents the buffer from consuming unbounded memory on a busy node.

**FILTER — kubernetes:** Enriches each log line with Kubernetes metadata — pod name, namespace, container name, labels, and annotations — by querying the Kubernetes API. `Merge_Log On` flattens JSON logs written by applications into the top-level log record rather than nesting them under a `log` key. `K8S-Logging.Exclude On` respects the `fluentbit.io/exclude: "true"` pod annotation, giving individual workloads an opt-out.

**OUTPUT — http (VictoriaLogs jsonline):** Sends the enriched log lines to VictoriaLogs via HTTP POST. The URI encodes four important parameters:

```text
/insert/jsonline
  ?_stream_fields=stream,kubernetes_pod_name,kubernetes_namespace_name,kubernetes_container_name
  &_msg_field=log
  &_time_field=time
```

- `_stream_fields` tells VictoriaLogs which fields define a log stream (equivalent to Loki's labels). Choosing pod name, namespace, and container name gives per-container granularity without over-cardinality.
- `_msg_field=log` maps Fluent Bit's `log` field to VictoriaLogs' message field.
- `_time_field=time` tells VictoriaLogs to use the log's original timestamp rather than the ingestion time.

`Retry_Limit False` means Fluent Bit will retry indefinitely on failure. This is appropriate for a homelab — we would rather have Fluent Bit buffering logs and retrying than dropping them silently when VictoriaLogs restarts for maintenance.

---

## Gotcha 3: additionalDataSources Does Not Work

### Symptom

After deploying both VictoriaMetrics and VictoriaLogs, Grafana had the VictoriaMetrics datasource pre-configured (handled by the chart), but VictoriaLogs was absent. Adding it via `grafana.additionalDataSources` in the victoria-metrics values had no effect regardless of how many times the Application was synced.

### Diagnosis

The `victoria-metrics-k8s-stack` chart manages Grafana datasource provisioning through its own ConfigMap — `victoria-metrics-victoria-metrics-k8s-stack-grafana-ds` — rather than delegating to the Grafana subchart's standard provisioning mechanism. This ConfigMap is templated and controlled by the VictoriaMetrics chart directly.

The consequence: `grafana.additionalDataSources`, which works by adding entries to the Grafana subchart's own datasource provisioning ConfigMap, is never consulted. The chart simply does not pass that value through. The VictoriaMetrics chart's own datasource ConfigMap overwrites whatever the subchart would have generated.

### Fix

The solution is a standalone provisioning ConfigMap mounted into Grafana via `extraConfigmapMounts` — bypassing the chart's own provisioning entirely:

```yaml
# apps/victoria-metrics/manifests/grafana-victorialogs-ds.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-victorialogs-datasource
  namespace: monitoring
data:
  victorialogs-datasource.yaml: |
    apiVersion: 1
    datasources:
      - name: VictoriaLogs
        type: victoriametrics-logs-datasource
        access: proxy
        url: http://victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local:9428
        isDefault: false
        editable: false
```

This ConfigMap is deployed as a third source in the `victoria-metrics` ArgoCD Application and mounted into Grafana at `/etc/grafana/provisioning/datasources/victorialogs.yaml` via:

```yaml
grafana:
  extraConfigmapMounts:
    - name: victorialogs-datasource
      mountPath: /etc/grafana/provisioning/datasources/victorialogs.yaml
      subPath: victorialogs-datasource.yaml
      configMap: grafana-victorialogs-datasource
      readOnly: true
```

On pod restart, Grafana reads the provisioning file and adopts the datasource — marking it `readOnly` (non-editable in the UI). The datasource is now fully declarative: it will be recreated correctly on any Grafana redeploy, regardless of PVC state.

**The lesson:** Helm chart composition is leaky. When chart A embeds chart B as a subchart, chart A can intercept and override anything chart B would have done. Relying on subchart values working end-to-end is not safe without reading the parent chart's templates. The escape hatch is `extraConfigmapMounts` — it operates at the Pod level and is independent of the chart's own provisioning logic.

---

## What Is Visible Now

With all three Applications healthy, the cluster has full observability:

**Grafana at `http://192.168.55.203`** ships pre-built dashboards:

- **Node Exporter Full** — per-node CPU, memory, disk I/O, network throughput, filesystem usage. The mini nodes' iGPU and the RTX 5070 show up in system metrics.
- **Kubernetes / Compute Resources / Cluster** — cluster-wide CPU and memory requests vs limits vs usage.
- **Kubernetes / Compute Resources / Namespace** — same broken down per namespace.
- **Kubernetes / Networking** — pod-to-pod traffic, DNS query rates, connection counts.
- **VMAgent** — internal metrics for the scraping engine: targets scraped, samples/sec, queue depth.

**VictoriaLogs** is queryable via Grafana's Explore tab using LogQL-like syntax. Useful starting queries:

```text
# All logs from the argocd namespace
{kubernetes_namespace_name="argocd"}

# Logs from a specific pod
{kubernetes_pod_name=~"victoria-metrics.*"}

# Error lines across the cluster
{kubernetes_namespace_name=~".+"} |= "error"
```

**node-exporter** is running on all six nodes (the Raspberry Pis count — raspi-1 and raspi-2 each contribute their ARM metrics to the same dashboards).

**What is not yet visible:** alerting. VMAlert and Alertmanager are disabled pending alert rule tuning. That is Phase 9.

## References

- [VictoriaMetrics Helm Charts](https://github.com/VictoriaMetrics/helm-charts) — Source for both `victoria-metrics-k8s-stack` and `victoria-logs-single`
- [VictoriaLogs Documentation](https://docs.victoriametrics.com/victorialogs/) — Ingestion API, query language, retention configuration
- [Fluent Bit Documentation](https://docs.fluentbit.io/) — Input/filter/output plugin reference, multiline parsing, Kubernetes filter
- [victoria-metrics-k8s-stack Chart](https://github.com/VictoriaMetrics/helm-charts/tree/master/charts/victoria-metrics-k8s-stack) — Chart source, values reference, CRD documentation
