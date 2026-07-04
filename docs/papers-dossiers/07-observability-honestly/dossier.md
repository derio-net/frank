---
paper: 07-observability-honestly
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Grafana + Prometheus + Loki
  positioning: "The LGTM stack — Grafana for visualization, Prometheus for metrics, Loki for logs, Tempo (optional) for traces. The OSS reference assembly."
  primary_url: "https://grafana.com/oss/grafana/"
- name: VictoriaMetrics
  positioning: "Prometheus-compatible TSDB optimised for high-cardinality and low-resource clusters — Frank's actual metrics backend."
  primary_url: "https://victoriametrics.com/"
- name: Grafana Mimir
  positioning: "HA Prometheus replacement at enterprise scale — horizontal sharding, multi-tenancy, object-store backed."
  primary_url: "https://grafana.com/oss/mimir/"
- name: Tempo / Jaeger
  positioning: "OSS distributed tracing — Tempo is Grafana's object-store backend; Jaeger is the CNCF predecessor with its own UI."
  primary_url: "https://grafana.com/oss/tempo/"
- name: Datadog / New Relic
  positioning: "Commercial all-in-one SaaS observability — agents on every host, billable per host and per GB ingested, contract-grade SLA."
  primary_url: "https://www.datadoghq.com/"
- name: OpenSearch / Elastic
  positioning: "Logs-first stack — full-text search across log volumes, dashboards, alerts. Heavier than Loki but indexes at write time."
  primary_url: "https://opensearch.org/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Prometheus Operator — Getting Started"
  type: vendor-docs
  url: "https://prometheus-operator.dev/docs/getting-started/introduction/"
  quoted_passages:
    - "The Prometheus Operator provides Kubernetes native deployment and management of Prometheus and related monitoring components."
    - "ServiceMonitor, which declaratively specifies how groups of Kubernetes services should be monitored. The Operator automatically generates Prometheus scrape configuration based on the current configuration of the API objects."
  relevance: "Anchors the §3 architecture diagram for the LGTM stack — defines the ServiceMonitor model Frank actually uses for in-cluster discovery and the operator-managed reconciliation loop that produces the live Prometheus scrape config."

- title: "VictoriaMetrics — Overview & Architecture"
  type: vendor-docs
  url: "https://docs.victoriametrics.com/"
  quoted_passages:
    - "VictoriaMetrics is a fast, cost-effective and scalable monitoring solution and time series database."
    - "It is optimized for storage with high-latency IO and low IOPS (HDD and network storage in AWS, GCP, Azure, etc.) compared to other solutions."
  relevance: "Vendor's own articulation of the small-cluster wins — low IOPS, low RAM, Prometheus wire-compatible. Anchors the §2 vendor positioning and the §4 'metric cardinality' callout that drives Frank's choice of VM over a stock Prometheus TSDB."

- title: "Google SRE Book — Monitoring Distributed Systems (Chapter 6)"
  type: paper
  url: "https://sre.google/sre-book/monitoring-distributed-systems/"
  quoted_passages:
    - "Monitoring a very complex application is a significant engineering endeavor in and of itself. Even with substantial existing infrastructure for instrumentation, collection, display, and alerting in place, a Google SRE team with 10–12 members typically has one or sometimes two members whose primary assignment is to build and maintain monitoring systems for their service."
    - "Your monitoring system should address two questions: what's broken, and why? The 'what's broken' indicates the symptom; the 'why' indicates a (possibly intermediate) cause."
  relevance: "The foundational text on what an observability system is FOR — symptom vs cause, the four golden signals, the cost of monitoring as engineering effort. Cited in §1 to frame the capability and in §5 to ground Frank's choice to provision alerts from code, not click-ops."

- title: "Grafana Alerting — Documentation"
  type: vendor-docs
  url: "https://grafana.com/docs/grafana/latest/alerting/"
  quoted_passages:
    - "Grafana Alerting is a unified alerting system, where alerts are managed in a single location for all your data sources."
    - "Alert rules: Define the conditions that trigger alerts. Each rule consists of one or more queries and expressions, a condition that needs to be met, and an interval at which the rule should be evaluated."
  relevance: "Underwrites §3 (alerting architecture diagram) and §5 (the 12.x SSE alert rules need a 3-step A→B→C — the classic-condition format that worked in Grafana 11 breaks with sse.parseError on 12.x). Vendor's authoritative description of the alert-rule shape Frank's alerts must conform to."

- title: "SigNoz — Loki vs Elasticsearch (practitioner comparison)"
  type: postmortem
  url: "https://signoz.io/blog/loki-vs-elasticsearch/"
  quoted_passages:
    - "Loki indexes only metadata (labels) for log entries, while Elasticsearch indexes the full content of logs. This fundamental design choice has significant implications for storage costs, query performance, and use cases."
    - "Loki is significantly more cost-effective for storing large volumes of logs because of its index-light design and use of object storage backends like S3, GCS, or local filesystems."
  relevance: "Practitioner-level head-to-head with concrete trade-offs on the index-at-write vs index-at-query split. Used in §3 to explain why Loki's log model is structurally different from OpenSearch/Elastic, and in §4 to ground the log-volume-vs-query-cost callout."

- title: "VictoriaMetrics — Benchmarking Prometheus-compatible time series databases"
  type: benchmark
  url: "https://victoriametrics.com/blog/remote-write-benchmark/"
  quoted_passages:
    - "vmagent uses 3.2x/1.6x less CPU and 2.7x/3.0x less memory than competing scrape agents (OpenTelemetry Collector and Prometheus 3.x)."
    - "VictoriaMetrics uses 5x-10x less RAM than Prometheus for the same data."
  relevance: "Vendor-published benchmark — biased but reproducible. Anchors the §4 cardinality / resource-cost callout that justifies Frank's swap from stock Prometheus to VictoriaMetrics on a small-cluster footprint."

- title: "Frank — Grafana gotchas (file-provisioned alerts, SSE alert format, ALERTS{} in VM)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "File-provisioned alerts/dashboards in apps/grafana-alerting/manifests/ are read-only in UI; edit ConfigMap, push, restart pod (provisioning files are read at boot, not watched)."
    - "12.x SSE alert rules need 3-step A→B→C; classic-condition format fails with sse.parseError."
    - "ALERTS{} does NOT exist in VM for Grafana-managed alerts — use alertlist panel type."
  relevance: "Frank's own running postmortem registry — concrete operational scars accumulated while running the Grafana stack against VictoriaMetrics. Provides the source-of-truth one-liners and recovery commands for §5 scar callouts."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/grafana-alerting/manifests/"
  date: 2026-04-12
  demonstrates: "Frank's alerts and dashboards are file-provisioned via ConfigMaps in this directory. The read-only-in-UI scar is baked into this layout by design — every alert here is sourced from git, not edited live. The price is the four-step reconcile (edit ConfigMap → push → ArgoCD sync → restart Grafana pod) for every alert tweak."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-04-20
  demonstrates: "File-provisioned alerts/dashboards are read-only in the Grafana UI; provisioning files are read at pod boot, not watched live. The UI lets you click Edit and lets you click Save — but the changes survive only until the next pod restart. Twice rediscovered before it earned its place in the gotcha registry."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/grafana.md"
  date: 2026-04-15
  demonstrates: "Grafana 12.x SSE alert rules need a 3-step A->B->C (query, reduce, threshold) form. The classic-condition format that worked in Grafana 11 fails with sse.parseError on 12.x. Half of Frank's file-provisioned alerts went dark on a minor-version bump until each rule was rewritten."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/grafana.md"
  date: 2026-05-02
  demonstrates: "VictoriaMetrics does not expose Prometheus's internal ALERTS{} time series for Grafana-managed alerts. The alertlist panel type is the only first-class way to render currently-firing Grafana alerts when VM is the TSDB. A trap that the VM docs only mention in a side-note."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/grafana.md"
  date: 2026-04-18
  demonstrates: "Cannot change provenance from api to file — once an alert exists with provenance: api in Grafana's sqlite, the file-provisioning loader refuses to overwrite it. Recovery requires scale-down, DELETE FROM alert_rule, then scale-up — a write-then-revert dance at the database level. Live evidence that Grafana's alert provenance model treats UI-created and file-provisioned alerts as separate ownership domains, not as views over the same resource."

- kind: grafana-screenshot
  path_or_url: "blog/content/docs/papers/07-observability-honestly/grafana-honest-dashboard.png"
  date: 2026-05-19
  demonstrates: "Grafana UI snapshot showing real cluster metrics with a visible scar / spike from a past incident — the alertlist panel rendering currently-firing alerts against VictoriaMetrics as the TSDB. Placeholder PNG retained until a cluster-side capture is made; cluster access is not available from this worktree."

## Diagrams planned
- landscape:
    x_axis: "OSS ↔ Commercial"
    y_axis: "Assembled ↔ Unified"
    vendors_plotted: ["Grafana + Prometheus + Loki", "VictoriaMetrics", "Grafana Mimir", "Tempo / Jaeger", "Datadog / New Relic", "OpenSearch / Elastic"]
- architecture_comparison:
    vendors: ["Grafana + Prometheus + Loki (Frank)", "Grafana Mimir", "Tempo / Jaeger", "Datadog / New Relic", "OpenSearch / Elastic"]
- decision_tree:
    leaves: 4
    description: "Question: who renders your one-screen view of the cluster? Branches on scale + shape (laptop, small-cluster-OSS, multi-tenant-SaaS, regulated logs-first), terminating in: Docker stats + Grafana Cloud free, Grafana + Prom + Loki (Frank), Mimir+Tempo+Loki or Datadog/New Relic, OpenSearch + Filebeat."

## Named gaps (≥1)
- "No published TCO comparison of OSS LGTM(-without-T) vs commercial all-in-one (Datadog, New Relic) at <=10-node scale that accounts for operational burden — only $/host or $/GB ingested. Every available comparison either (a) quotes Datadog's headline numbers at enterprise scale where the percentage saved is the story, or (b) ignores the alert-engine maintenance + dashboard-drift hours that the OSS stack charges in operator time. The single most useful number for a small team — how many hours per month does each option cost you? — is not published anywhere reliable, and the bias of who would publish it (Grafana Labs, Datadog, the practitioner who chose one and not the other) makes the gap structural, not just unfilled."

## Counter-arguments considered (≥1)
- "Commercial all-in-one (Datadog, New Relic) is two orders of magnitude faster to stand up than the OSS LGTM assembly, erases the alert-engine bug surface (no sse.parseError, no file-provisioning sqlite-recovery dance), and ships with a contract — why doesn't that win for Frank? Answer: same as Paper 00. Frank is a learning platform. The reason to run Grafana + Prometheus + Loki is to encounter the file-provisioned-alerts read-only-in-UI scar, the Grafana 12.x SSE alert format break, the ALERTS{}-doesn't-exist-in-VM trap — first-hand. Commercial SaaS hides exactly the failure modes the cluster exists to teach. For a production team with a real on-call rotation and revenue depending on the 3 AM page being delivered, the counter-argument wins; for Frank, that is the point."
