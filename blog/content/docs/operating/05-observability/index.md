---
title: "Operating on Observability"
series: ["operating"]
layer: obs
date: 2026-03-13
draft: false
tags: ["operations", "victoriametrics", "grafana", "fluent-bit", "observability", "troubleshooting"]
summary: "Day-to-day commands for querying metrics and logs, managing Grafana dashboards, and debugging the observability pipeline."
weight: 6
reader_goal: "Query metrics and logs, check pipeline health, adjust retention, and debug common failures (missing metrics, Fluent Bit not shipping, high cardinality) across VictoriaMetrics, Grafana, Fluent Bit, and VictoriaLogs."
diataxis: [how-to, reference]
last_updated: 2026-07-15
last_updated_commit: https://github.com/derio-net/frank/commit/a8bed9a1d358b7ad87bb6dcaa9b0162e5fb0e127
---

{{< last-updated >}}

This is the operational companion to [Building Observability]({{< relref "/docs/building/07-observability" >}}). That post covers the architecture decisions and deployment gotchas. This one covers what you actually type when you need to find out why something is broken, slow, or eating memory.

Source your environment before running commands:

```bash
source .env   # sets KUBECONFIG
```

## Overview

Frank's observability stack has four moving parts:

- **VictoriaMetrics** (VMSingle + vmagent) — time-series metrics database and scraping engine, 20Gi Longhorn PVC, 1-month retention
- **Grafana** at `http://192.168.55.203` — dashboards and exploration, OIDC auth via Authentik
- **Fluent Bit** — DaemonSet on all nodes (including tainted CP and GPU nodes), shipping container logs
- **VictoriaLogs** — log storage, 14-day retention, queryable through Grafana's Explore tab

### Verify

```bash
# vmagent scraping
kubectl get pods -n monitoring -l app.kubernetes.io/name=vmagent

# Fluent Bit on all nodes
kubectl get ds -n monitoring fluent-bit
# DESIRED and READY should match (7 nodes)

# VictoriaLogs accepting writes
kubectl logs -n monitoring -l app=victoria-logs-single-server --tail=5
```

## Observing State

### Grafana Dashboards

Open `http://192.168.55.203`. Provisioned dashboards under "VictoriaMetrics" folder:

- **Node Exporter Full** — per-node CPU, memory, disk I/O
- **Kubernetes / Compute Resources / Cluster** — cluster-wide CPU/memory usage
- **Kubernetes / Compute Resources / Namespace** — same, by namespace
- **VMAgent** — scrape targets, samples/sec, queue depth

{{< screenshot src="grafana-dashboards.png" caption="Grafana dashboard list showing available views" >}}

### Querying Metrics with MetricsQL

```bash
kubectl port-forward -n monitoring svc/vmsingle-victoria-metrics-victoria-metrics-k8s-stack 8429:8429
```

Then open `http://localhost:8429/vmui`. MetricsQL is a superset of PromQL.

Useful starter queries:

```promql
# CPU usage by node (1m average)
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)

# Memory usage percentage by node
(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100

# Pod restart counts in the last hour
increase(kube_pod_container_status_restarts_total[1h]) > 0

# Disk usage on Longhorn volumes
kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes * 100
```

CLI query:

```bash
kubectl port-forward -n monitoring svc/vmsingle-victoria-metrics-victoria-metrics-k8s-stack 8429:8429 &
curl -s 'http://localhost:8429/api/v1/query?query=up' | jq '.data.result[] | {instance: .metric.instance, up: .value[1]}'
```

### Querying Logs with VictoriaLogs

Logs are queryable through Grafana's Explore tab — select "VictoriaLogs" datasource and use LogsQL:

```text
# All logs from a namespace
{kubernetes_namespace_name="argocd"}

# Logs from a specific pod
{kubernetes_pod_name=~"victoria-metrics.*"}

# Error lines across the entire cluster
{kubernetes_namespace_name=~".+"} |= "error"

# Logs from the GPU node
{kubernetes_host="gpu-1"} | level:error
```

CLI access:

```bash
kubectl port-forward -n monitoring svc/victoria-logs-victoria-logs-single-server 9428:9428
curl -s 'http://localhost:9428/select/logsql/query?query={kubernetes_namespace_name="monitoring"}&limit=10' | jq .
```

## Routine Operations

### Creating and Importing Grafana Dashboards

Open Grafana at `http://192.168.55.203` → Dashboards → Import → enter dashboard ID (e.g. 1860 for Node Exporter Full) → select VictoriaMetrics datasource.

Dashboards are written to Grafana's 1Gi Longhorn PVC and survive pod restarts.

### Adjusting Retention

Metrics retention (`apps/victoria-metrics/values.yaml`):

```yaml
vmsingle:
  spec:
    retentionPeriod: "1"  # 1 month
```

Log retention (`apps/victoria-logs/values.yaml`):

```yaml
server:
  retentionPeriod: 14d
```

Change the value, commit, and let ArgoCD sync. Existing data outside the new window is GC'd on the next retention pass.

### Checking What vmagent Is Scraping

```bash
kubectl port-forward -n monitoring svc/vmagent-victoria-metrics-victoria-metrics-k8s-stack 8429:8429
```

Open `http://localhost:8429/targets` to see every scrape target, status (up/down), last scrape time, and errors.

### Exploring Available Metrics

```bash
# List all metric names
curl -s 'http://localhost:8429/api/v1/label/__name__/values' | jq '.data[:20]'

# Search by keyword
curl -s 'http://localhost:8429/api/v1/label/__name__/values' | jq '.data[] | select(test("gpu|nvidia"))'
```

## Runbook

### False Positives from kube_pod_status_ready in Batch Namespaces

If a Layer alert fires intermittently for a namespace running Tekton or Argo Workflows, `kube_pod_status_ready{condition="true"}` reports `0` for pods in `Completed`/`Error` state — those are by-design not-Ready post-completion.

Fix: switch the query to `kube_deployment_status_replicas_unavailable{namespace=~"…"}` — Deployments are the long-running things; task pods are naturally excluded. This fixed the `layer-25-cicd-down` alert on 2026-05-14 (`apps/grafana-alerting/manifests/alert-rules-cm.yaml`). The TTL CronJob in `apps/tekton/manifests/pipelinerun-ttl-gc.yaml` handles the complementary hygiene.

### Missing Metrics

If a metric you expect is missing:

1. **Check the exporter pod:**
   ```bash
   kubectl get pods -n monitoring -l app.kubernetes.io/name=node-exporter
   kubectl get pods -n monitoring -l app.kubernetes.io/name=kube-state-metrics
   ```

2. **Check vmagent targets:**
   ```bash
   kubectl port-forward -n monitoring svc/vmagent-victoria-metrics-victoria-metrics-k8s-stack 8429:8429
   # Open http://localhost:8429/targets
   ```

3. **Check VMServiceMonitor:**
   ```bash
   kubectl get vmservicemonitors -n monitoring
   kubectl describe vmservicemonitor <name> -n monitoring
   ```

4. **Check the exporter directly:**
   ```bash
   kubectl port-forward -n monitoring <exporter-pod> <port>:<port>
   curl http://localhost:<port>/metrics | grep <metric-name>
   ```

### Fluent Bit Not Shipping Logs

1. **Check DaemonSet:**
   ```bash
   kubectl get ds -n monitoring fluent-bit
   kubectl get pods -n monitoring -l app.kubernetes.io/name=fluent-bit -o wide
   ```

2. **Check Fluent Bit logs for `retry` lines:**
   ```bash
   kubectl logs -n monitoring -l app.kubernetes.io/name=fluent-bit --tail=50
   ```

3. **Verify destination hostname resolution:**
   ```bash
   kubectl exec -n monitoring <fluent-bit-pod> -- nslookup victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local
   ```

4. **Check tail file positions:**
   ```bash
   kubectl exec -n monitoring <fluent-bit-pod> -- ls -la /var/log/flb_kube.db
   ```

### High Cardinality

If VMSingle memory is climbing or queries are slow:

```bash
curl -s 'http://localhost:8429/api/v1/status/tsdb' | jq '.data.seriesCountByMetricName[:10]'
```

Drop the offending label in vmagent's relabeling config or exclude the metric entirely.

### VictoriaLogs Query Returns No Results

1. **Check VictoriaLogs is receiving data:**
   ```bash
   kubectl port-forward -n monitoring svc/victoria-logs-victoria-logs-single-server 9428:9428
   curl -s 'http://localhost:9428/select/logsql/query?query=*&limit=5' | jq .
   ```

2. **Check Grafana datasource** points to `http://victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local:9428`.

3. **Check retention** — logs older than 14 days are GC'd.

## Missteps

| What we assumed | Why it was wrong | What it cost |
|-----------------|------------------|-------------|
| `kube_pod_status_ready` is a reliable health signal for all namespaces | Batch namespaces (Tekton, Argo Workflows) have pods that are intentionally not-Ready post-completion | False-positive `layer-25-cicd-down` alert until query was switched to `kube_deployment_status_replicas_unavailable`. |
| VictoriaLogs datasource auto-configures | Grafana needs the exact internal SVC URL | Queries returned nothing until datasource was pointed to `victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local:9428`. |
| High cardinality is always an application problem | Unbounded labels on infrastructure metrics (node-exporter, kube-state-metrics) can also blow up series count | Memory pressure on VMSingle until the offending label was dropped in vmagent relabeling. |

## Quick Reference

| Command | What It Does |
|---------|-------------|
| `kubectl port-forward -n monitoring svc/vmsingle-... 8429:8429` | Access VMSingle UI and API |
| `kubectl port-forward -n monitoring svc/victoria-logs-...-server 9428:9428` | Access VictoriaLogs API |
| `kubectl get ds -n monitoring fluent-bit` | Check Fluent Bit DaemonSet status |
| `kubectl logs -n monitoring -l app.kubernetes.io/name=fluent-bit --tail=50` | Fluent Bit output logs |
| `kubectl logs -n monitoring -l app.kubernetes.io/name=vmagent --tail=50` | vmagent scrape logs |
| `kubectl get vmservicemonitors -n monitoring` | List all metric scrape configs |
| `curl localhost:8429/api/v1/query?query=up` | Query metrics via API |
| `curl localhost:9428/select/logsql/query?query=*&limit=10` | Query logs via API |
| `curl localhost:8429/targets` | List vmagent scrape targets |
| `curl localhost:8429/api/v1/status/tsdb` | TSDB cardinality stats |

## References

- [VictoriaMetrics Documentation](https://docs.victoriametrics.com/) — MetricsQL reference, VMSingle operations, retention
- [VictoriaLogs Documentation](https://docs.victoriametrics.com/victorialogs/) — LogsQL syntax, ingestion API
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/) — Dashboard management, datasource provisioning
- [Fluent Bit Documentation](https://docs.fluentbit.io/) — Pipeline debugging, tail input, HTTP output
- [Building Observability]({{< relref "/docs/building/07-observability" >}}) — Architecture decisions and deployment gotchas
