---
title: "Operating on Observability"
date: 2026-03-13
draft: false
tags: ["operations", "victoriametrics", "grafana", "fluent-bit", "observability"]
summary: "Day-to-day commands for querying metrics and logs, managing Grafana dashboards, and debugging the observability pipeline."
weight: 105
cover:
  image: cover.png
  alt: "Frank monitoring his own vital signs through surgical instruments"
  relative: true
---

This is the operational companion to [Building Observability]({{< relref "/building/07-observability" >}}). That post covers the architecture decisions and deployment gotchas. This one covers what you actually type when you need to find out why something is broken, slow, or eating memory.

## Overview

Frank's observability stack has four moving parts:

- **VictoriaMetrics** (VMSingle + vmagent) -- time-series metrics database and scraping engine, running in the `monitoring` namespace with a 20Gi Longhorn PVC and 1-month retention
- **Grafana** at `http://192.168.55.203` -- dashboards and exploration, with OIDC auth via Authentik
- **Fluent Bit** -- DaemonSet on all nodes (including tainted control-plane and GPU nodes), shipping container logs
- **VictoriaLogs** -- log storage with 14-day retention, queryable through Grafana's Explore tab

Supporting collectors: **node-exporter** (hardware metrics on all nodes) and **kube-state-metrics** (Kubernetes object metrics).

## Observing State

### Grafana Dashboards

Open `http://192.168.55.203` in a browser. The stack ships with pre-built dashboards under the "VictoriaMetrics" folder:

- **Node Exporter Full** -- per-node CPU, memory, disk I/O, network, filesystem
- **Kubernetes / Compute Resources / Cluster** -- cluster-wide CPU and memory requests vs limits vs actual usage
- **Kubernetes / Compute Resources / Namespace** -- the same, broken down by namespace
- **VMAgent** -- scrape targets, samples/sec, queue depth

These dashboards are provisioned by the Helm chart and survive Grafana pod restarts.

### Querying Metrics with MetricsQL

For ad-hoc metric exploration, port-forward to VMSingle and use its built-in UI:

```bash
kubectl port-forward -n monitoring svc/vmsingle-victoria-metrics-victoria-metrics-k8s-stack 8429:8429
```

Then open `http://localhost:8429/vmui` in your browser. MetricsQL is a superset of PromQL -- any PromQL query works, plus extensions like `keep_metric_names` and `range_median`.

Some useful starter queries:

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

You can also query from the command line with curl:

```bash
kubectl port-forward -n monitoring svc/vmsingle-victoria-metrics-victoria-metrics-k8s-stack 8429:8429 &
curl -s 'http://localhost:8429/api/v1/query?query=up' | jq '.data.result[] | {instance: .metric.instance, up: .value[1]}'
```

### Querying Logs with VictoriaLogs

Logs are queryable through Grafana's Explore tab -- select the "VictoriaLogs" datasource and use LogsQL syntax:

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

For CLI access, port-forward to VictoriaLogs directly:

```bash
kubectl port-forward -n monitoring svc/victoria-logs-victoria-logs-single-server 9428:9428
curl -s 'http://localhost:9428/select/logsql/query?query={kubernetes_namespace_name="monitoring"}&limit=10' | jq .
```

### Checking Pipeline Health

Verify all pieces are running:

```bash
# vmagent is scraping
kubectl get pods -n monitoring -l app.kubernetes.io/name=vmagent
kubectl logs -n monitoring -l app.kubernetes.io/name=vmagent --tail=5

# Fluent Bit is running on all nodes
kubectl get ds -n monitoring fluent-bit
# DESIRED and READY counts should match (7 nodes)

# VictoriaLogs is accepting writes
kubectl logs -n monitoring -l app=victoria-logs-single-server --tail=5
```

## Routine Operations

### Creating and Importing Grafana Dashboards

To import a community dashboard (for example, dashboard ID 1860 for Node Exporter Full):

1. Open Grafana at `http://192.168.55.203`
2. Go to Dashboards > Import
3. Enter the dashboard ID and click Load
4. Select the VictoriaMetrics datasource and click Import

To make an imported dashboard persistent across pod restarts, Grafana's 1Gi Longhorn PVC handles that automatically. Dashboards saved in the UI are written to the PVC and survive restarts.

### Adjusting Retention

Metrics retention is set in `apps/victoria-metrics/values.yaml`:

```yaml
vmsingle:
  spec:
    retentionPeriod: "1"  # 1 month
```

Log retention is in `apps/victoria-logs/values.yaml`:

```yaml
server:
  retentionPeriod: 14d
```

Change the value, commit, and let ArgoCD sync. The pods will restart with the new retention window. Existing data outside the new window is garbage-collected on the next retention pass.

### Checking What vmagent Is Scraping

vmagent exposes its target list via its own UI:

```bash
kubectl port-forward -n monitoring svc/vmagent-victoria-metrics-victoria-metrics-k8s-stack 8429:8429
```

Open `http://localhost:8429/targets` to see every scrape target, its status (up/down), last scrape time, and error messages. This is the first place to look when a metric is missing.

### Exploring Available Metrics

To find what metrics exist:

```bash
# List all metric names
curl -s 'http://localhost:8429/api/v1/label/__name__/values' | jq '.data[:20]'

# Search for metrics by keyword
curl -s 'http://localhost:8429/api/v1/label/__name__/values' | jq '.data[] | select(test("gpu|nvidia"))'
```

## Debugging

### Missing Metrics

If a metric you expect is not showing up:

1. **Check the scrape target** -- is the exporter pod running?
   ```bash
   kubectl get pods -n monitoring -l app.kubernetes.io/name=node-exporter
   kubectl get pods -n monitoring -l app.kubernetes.io/name=kube-state-metrics
   ```

2. **Check vmagent targets** -- is it scraping the endpoint?
   ```bash
   kubectl port-forward -n monitoring svc/vmagent-victoria-metrics-victoria-metrics-k8s-stack 8429:8429
   # Open http://localhost:8429/targets and look for the target
   ```

3. **Check VMServiceMonitor** -- does the CRD exist and match the service labels?
   ```bash
   kubectl get vmservicemonitors -n monitoring
   kubectl describe vmservicemonitor <name> -n monitoring
   ```

4. **Check the exporter directly** -- does it actually expose the metric?
   ```bash
   kubectl port-forward -n monitoring <exporter-pod> <port>:<port>
   curl http://localhost:<port>/metrics | grep <metric-name>
   ```

### Fluent Bit Not Shipping Logs

If logs are not appearing in VictoriaLogs:

1. **Check Fluent Bit pods** -- are they running on all nodes?
   ```bash
   kubectl get ds -n monitoring fluent-bit
   kubectl get pods -n monitoring -l app.kubernetes.io/name=fluent-bit -o wide
   ```

2. **Check Fluent Bit logs** for output errors:
   ```bash
   kubectl logs -n monitoring -l app.kubernetes.io/name=fluent-bit --tail=50
   ```
   Look for `retry` lines. Silent retries with no error detail usually mean DNS resolution failure -- the output hostname is wrong or the target service is down.

3. **Verify the destination hostname resolves**:
   ```bash
   kubectl exec -n monitoring <fluent-bit-pod> -- nslookup \
     victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local
   ```

4. **Check tail file positions** -- Fluent Bit tracks where it left off reading each log file. If positions are stale, it may be re-reading or skipping:
   ```bash
   kubectl exec -n monitoring <fluent-bit-pod> -- ls -la /var/log/flb_kube.db
   ```

### High Cardinality

If VMSingle memory usage is climbing or queries are slow, high cardinality labels are usually the cause:

```bash
# Check top series by cardinality
curl -s 'http://localhost:8429/api/v1/status/tsdb' | jq '.data.seriesCountByMetricName[:10]'
```

If a metric has an unbounded label (like a request ID or session token), either drop the label in vmagent's relabeling config or exclude the metric entirely.

### VictoriaLogs Query Returns No Results

1. **Check VictoriaLogs is receiving data**:
   ```bash
   kubectl port-forward -n monitoring svc/victoria-logs-victoria-logs-single-server 9428:9428
   curl -s 'http://localhost:9428/select/logsql/query?query=*&limit=5' | jq .
   ```
   If this returns results, the problem is your query syntax, not the pipeline.

2. **Check the Grafana datasource** -- the VictoriaLogs datasource must point to `http://victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local:9428`. Go to Grafana > Configuration > Data Sources and verify.

3. **Check retention** -- if logs are older than 14 days, they have been garbage-collected.

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

- [VictoriaMetrics Documentation](https://docs.victoriametrics.com/) -- MetricsQL reference, VMSingle operations, retention
- [VictoriaLogs Documentation](https://docs.victoriametrics.com/victorialogs/) -- LogsQL syntax, ingestion API
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/) -- Dashboard management, datasource provisioning
- [Fluent Bit Documentation](https://docs.fluentbit.io/) -- Pipeline debugging, tail input, HTTP output
- [Building Observability]({{< relref "/building/07-observability" >}}) -- Architecture decisions and deployment gotchas
