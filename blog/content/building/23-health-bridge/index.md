---
title: "Health Bridge — Closing the Loop from Grafana Alerts to GitHub Issues"
date: 2026-04-04
draft: false
tags: ["observability", "grafana", "github", "go", "alerting", "automation", "argocd"]
summary: "A lightweight Go service that receives Grafana webhook alerts and automatically updates GitHub Project lifecycle states — turning monitoring signals into actionable project board updates."
weight: 24
cover:
  image: cover.png
  alt: "Frank the cluster monster routing alert signals from a Grafana dashboard into a GitHub project board"
  relative: true
---

The [previous post]({{< relref "/building/22-health-monitoring" >}}) added feature-level health monitoring — Blackbox probes, Pushgateway heartbeats, and Grafana alerts to Telegram. But alerts only tell you something is wrong. They don't update the project board, they don't track which features are degraded, and they don't create bug tickets when things die.

This post adds the final piece: a bridge service that maps Grafana alerts to GitHub Project lifecycle states. When an alert fires, the feature's Issue on the project board moves from `healthy` to `degraded` or `dead`. When it resolves, it moves back to `healthy`. No manual triage needed.

## The Problem

Frank's monitoring stack already knows when features break. Grafana alert rules watch for stale heartbeats, failed probes, and missing pods. Telegram notifications arrive within minutes.

But the project board — a GitHub Projects v2 board with a custom "Lifecycle" field — still requires manual updates. Someone has to see the Telegram alert, open GitHub, find the right Issue, and change its lifecycle state. That's exactly the kind of toil that should be automated.

## Architecture

A stateless Go HTTP server sits in the monitoring namespace. Grafana's notification policy routes alerts to it via webhook. The bridge parses each alert, extracts the `github_issue` label (e.g., `willikins#11`), maps the alert severity to a lifecycle state, and updates the GitHub Project item via GraphQL.

```
Grafana Alert Rule
       │
       ▼
Notification Policy
       │
       ├──▶ Telegram (continue: true)
       │
       └──▶ Health Bridge Webhook
                    │
                    ▼
            Parse github_issue label
                    │
                    ▼
            Map severity → lifecycle state
            ┌────────────────────────────┐
            │ resolved     → healthy     │
            │ firing/warn  → degraded    │
            │ firing/crit  → dead        │
            └────────────────────────────┘
                    │
                    ▼
            GitHub GraphQL API
            ├── Update Lifecycle field
            ├── Add Issue comment
            └── Create bug Issue (on dead)
```

The mapping is intentionally simple:

| Alert Status | Severity | Lifecycle State |
|-------------|----------|-----------------|
| resolved | any | healthy |
| firing | warning | degraded |
| firing | critical | dead |

On `dead` transitions, the bridge also creates a new bug Issue linked to the feature Issue — an automatic incident record.

## The Service

Three Go files, no external dependencies beyond the standard library:

**`main.go`** — Entry point. Reads config from environment variables, creates the bridge, sets up HTTP routes:

- `POST /webhook` — Grafana webhook receiver
- `GET /healthz` — Liveness probe
- `GET /readyz` — Readiness probe (checks project metadata is loaded)

**`bridge.go`** — Core logic. Handles webhook authentication (Bearer token), JSON parsing, alert processing, state mapping, and comment formatting. Each alert is processed independently — a failure on one doesn't block others.

**`github.go`** — GitHub API client. On startup, loads project metadata via GraphQL (project ID, Lifecycle field ID, option IDs for each state). At runtime, finds the project item for an issue and updates its Lifecycle field. Uses REST API for issue comments and bug issue creation.

### Webhook Authentication

Grafana sends a Bearer token in the Authorization header. The bridge validates it against the `WEBHOOK_SECRET` environment variable. This prevents unauthorized callers from changing lifecycle states.

```go
authHeader := r.Header.Get("Authorization")
if authHeader != "Bearer "+secret {
    http.Error(w, "unauthorized", http.StatusUnauthorized)
    return
}
```

### Alert-to-Issue Mapping

Each Grafana alert rule carries a `github_issue` label in the format `repo#number`:

| Alert Rule | github_issue |
|-----------|-------------|
| Exercise Reminder Stale | `willikins#11` |
| Session Manager Stale | `willikins#13` |
| Audit Digest Stale | `willikins#12` |
| Agent Pod Not Running | `frank#8` |

The bridge parses this label, finds the corresponding project item, and updates its lifecycle state.

### Issue Comments

Every state transition adds a comment to the GitHub Issue with full context — alert name, severity, summary, timestamp, and a link back to Grafana. This creates an audit trail of health transitions directly on the issue.

### Alert Deduplication (v0.2.0)

Grafana sends a webhook on every alert evaluation cycle (typically every few minutes). Without dedup, a persistently firing alert would create a new bug issue and comment on every cycle.

Two-layer dedup prevents this:

1. **In-memory state tracking** — The bridge tracks the last known lifecycle state per issue reference. Comments and bug issues are only created on actual state *transitions* (e.g., healthy → dead), not on repeated evaluations of the same state.
2. **GitHub search before bug creation** — As a restart safety net (in-memory state is lost on pod restart), the bridge searches for existing open bug issues with a matching title before creating a new one.

The lifecycle state update itself (the GraphQL mutation) remains unconditional — it's idempotent, so repeated calls are harmless.

## Deployment

The service runs as a single-replica Deployment in the monitoring namespace, managed by ArgoCD.

**Configuration:** Non-secret values (org name, project number, port) live in a ConfigMap. Secrets (GitHub PAT, webhook secret) come from Infisical via ExternalSecret.

**Resources:** The bridge is tiny — 10m CPU request, 16Mi memory request, 32Mi memory limit. The Go binary in a distroless image is under 15MB.

**Health checks:** Kubernetes liveness probe hits `/healthz`, readiness probe hits `/readyz`. The readiness probe returns 503 until the bridge has successfully loaded project metadata from GitHub.

**Self-monitoring:** The bridge's own healthz endpoint is added to the Blackbox Exporter's VMProbe, monitored by the same Grafana stack it feeds into. Dogfooding.

## Grafana Configuration

Two changes to the existing alerting setup:

**Contact point:** A webhook contact point named "Health Bridge Webhook" sends to the cluster-internal URL `http://health-bridge.monitoring.svc.cluster.local:8080/webhook` with Bearer token authentication.

**Notification policy:** A new route catches all alerts from the "Feature Health" folder and sends them to the webhook. The existing Telegram routes have `continue: true`, so alerts still reach Telegram *and* the bridge.

```
Default receiver: grafana-default-email
Routes:
  severity=critical → Telegram (continue: true)
  severity=warning  → Telegram (continue: true)
  grafana_folder=Feature Health → Health Bridge Webhook
```

## CI/CD

The health-bridge repo has a GitHub Actions workflow that triggers on version tags. It runs tests, builds the Docker image, and pushes to GHCR. The Kubernetes Deployment references a specific image tag — image updates require a manifest change in the frank repo, which ArgoCD picks up automatically.

```
git tag v0.1.0 → GitHub Actions → ghcr.io/derio-net/health-bridge:v0.1.0
                                          │
                                          ▼
                                  frank repo manifest
                                          │
                                          ▼
                                      ArgoCD sync
```

## Verification

Sending a test firing alert:

```bash
curl -X POST http://health-bridge.monitoring.svc.cluster.local:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{
    "status":"firing",
    "labels":{"alertname":"test","severity":"warning","github_issue":"willikins#11"},
    "annotations":{"summary":"Test alert"},
    "startsAt":"2026-04-04T18:30:00Z"
  }]}'
```

Response: `{"processed": 1, "total": 1}`. Issue #11 on the Derio Ops board moves to `degraded`, with a comment documenting the alert.

Sending a resolved alert moves it back to `healthy`. Round-trip verified.

## What's Next

The `endpoint-down` alert covers multiple targets but currently has no `github_issue` label — per-endpoint mapping to individual Issues is future work. Adding Prometheus metrics to the bridge itself (`health_bridge_alerts_processed_total`, `health_bridge_github_errors_total`) would enable dashboards on bridge throughput and error rates.

This completes M3 of the Work Lifecycle Tracking design. M1 set up the GitHub Projects board and lifecycle field. M2 added the monitoring probes and alerts. M3 closes the loop — monitoring signals now flow automatically into project state.

## References

- [Grafana Webhook Contact Point](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/#webhook)
- [GitHub Projects V2 GraphQL API](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects)
- [Distroless Container Images](https://github.com/GoogleContainerTools/distroless)
