# Observability — Design

**Date:** 2026-03-07

## Overview

Deploy a full observability stack covering metrics and logs for the Frank cluster. Uses VictoriaMetrics (metrics) and VictoriaLogs (logs) instead of the more common Prometheus + Loki combination — same Grafana dashboards, significantly lower resource usage, better suited for a mixed cluster with RPi nodes.

No alerting in this layer — alert rules will be defined once workloads are established.

## Stack

| Component | Tool | Chart |
|-----------|------|-------|
| Metrics storage + scraping | VictoriaMetrics (`victoria-metrics-k8s-stack`) | `victoria-metrics/victoria-metrics-k8s-stack` |
| Log storage | VictoriaLogs (`victoria-logs-single`) | `victoria-metrics/victoria-logs-single` |
| Log shipper | Fluent Bit | `fluent/fluent-bit` |
| Dashboards | Grafana (bundled in vm-k8s-stack) | — |

VMAlert and AlertManager are **disabled** in this layer.

## Architecture

### Metrics

`victoria-metrics-k8s-stack` deploys:
- **VMSingle** — single-node metrics storage (sufficient for homelab scale)
- **vmagent** — scrapes metrics from all cluster targets
- **node-exporter** — per-node hardware/OS metrics (DaemonSet)
- **kube-state-metrics** — K8s resource metrics
- **Grafana** — visualization, configured with VMSingle as datasource

Pre-built dashboards included: node stats, pod resource usage, Kubernetes cluster overview.

Cilium/Hubble and Longhorn exporters are already exposed in the cluster — vmagent will scrape them automatically via ServiceMonitor CRDs.

### Logs

`victoria-logs-single` deploys VictoriaLogs as a single-node log store.

Fluent Bit runs as a DaemonSet on all nodes, tailing pod logs from `/var/log/containers/` and shipping to VictoriaLogs. Grafana is configured with VictoriaLogs as a second datasource (LogQL-compatible).

## ArgoCD Apps

Both apps deploy to the `monitoring` namespace.

**`victoria-metrics`**
- Chart: `victoria-metrics/victoria-metrics-k8s-stack`
- Values: `apps/victoria-metrics/values.yaml`
- Disables: VMAlert, AlertManager
- Grafana LoadBalancer IP: `192.168.55.203`

**`victoria-logs`**
- Chart: `victoria-metrics/victoria-logs-single`
- Values: `apps/victoria-logs/values.yaml`
- Includes Fluent Bit subchart or separate Fluent Bit ArgoCD app
- ClusterIP only (Grafana connects internally)

## Storage

All volumes via Longhorn.

| Component | Size | Retention |
|-----------|------|-----------|
| VMSingle | 20Gi | 1 month (default) |
| VictoriaLogs | 20Gi | 14 days |
| Grafana | 1Gi | — |

## Exposure

| Service | IP | Notes |
|---------|----|-------|
| Grafana | `192.168.55.203` | Cilium L2 LoadBalancer |
| VMSingle | ClusterIP only | Internal to cluster |
| VictoriaLogs | ClusterIP only | Internal to cluster |

## Blog Post

**Title:** "Observability: Why We Chose VictoriaMetrics Over Prometheus"

**Angle:** Resource comparison between `kube-prometheus-stack` and `victoria-metrics-k8s-stack`. Show memory/CPU savings, demonstrate identical Grafana dashboards, highlight RPi-friendly footprint. Walk through the Fluent Bit → VictoriaLogs pipeline. Show log + metrics correlation in Grafana.
