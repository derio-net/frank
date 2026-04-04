---
title: "Operating on Health Bridge"
date: 2026-04-04
draft: false
tags: ["operations", "observability", "grafana", "github", "go", "alerting"]
summary: "Day-to-day commands for managing the health-bridge service — checking status, testing webhooks, managing alert labels, and troubleshooting GitHub API issues."
weight: 116
cover:
  image: cover.png
  alt: "Frank the cluster monster at a console routing alert signals between monitoring screens and project boards"
  relative: true
---

Companion to [Health Bridge — Closing the Loop from Grafana Alerts to GitHub Issues]({{< relref "/building/23-health-bridge" >}}).

## Quick Reference

| Component | Namespace | Port | Purpose |
|-----------|-----------|------|---------|
| health-bridge | monitoring | 8080 | Grafana webhook → GitHub lifecycle updates |
| Webhook endpoint | — | — | `POST /webhook` (Bearer auth) |
| Health check | — | — | `GET /healthz` |
| Readiness check | — | — | `GET /readyz` |

## Checking Service Status

```bash
# Pod status
kubectl get pods -n monitoring -l app=health-bridge

# Recent logs
kubectl logs -n monitoring -l app=health-bridge --tail=20

# Check readiness (should show project metadata loaded)
kubectl logs -n monitoring -l app=health-bridge | grep "Loaded project metadata"
# Expected: Loaded project metadata: id=..., field=..., 10 lifecycle states
```

## Testing the Webhook

```bash
# Get webhook secret
WEBHOOK_SECRET=$(kubectl get secret -n monitoring health-bridge-secrets \
  -o jsonpath='{.data.WEBHOOK_SECRET}' | base64 -d)

# Send a test alert (warning → degraded)
curl -s -X POST http://health-bridge.monitoring.svc.cluster.local:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {"alertname": "test-bridge", "severity": "warning", "github_issue": "willikins#11"},
      "annotations": {"summary": "Manual test alert"},
      "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }]
  }'
# Expected: {"processed": 1, "total": 1}

# Send a resolved alert to restore healthy state
curl -s -X POST http://health-bridge.monitoring.svc.cluster.local:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "resolved",
    "alerts": [{
      "status": "resolved",
      "labels": {"alertname": "test-bridge", "severity": "warning", "github_issue": "willikins#11"},
      "annotations": {"summary": "Manual test resolved"},
      "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
      "endsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    }]
  }'
# Expected: {"processed": 1, "total": 1}
```

## Checking ExternalSecret Sync

```bash
# Verify secrets are synced from Infisical
kubectl get externalsecret -n monitoring health-bridge-secrets
# Expected: STATUS=SecretSynced

# Check secret keys exist (don't print values)
kubectl get secret -n monitoring health-bridge-secrets -o jsonpath='{.data}' | jq 'keys'
# Expected: ["GITHUB_TOKEN", "WEBHOOK_SECRET"]
```

## Managing Alert Rule Labels

Alert rules need a `github_issue` label for the bridge to process them. Current mappings:

| Alert Rule UID | github_issue |
|---------------|-------------|
| exercise-reminder-stale | `willikins#11` |
| session-manager-stale | `willikins#13` |
| audit-digest-stale | `willikins#12` |
| agent-pod-not-running | `frank#8` |
| endpoint-down | _(none — future work)_ |

```bash
GRAFANA_AUTH="admin:$(kubectl get secret -n monitoring victoria-metrics-grafana \
  -o jsonpath='{.data.admin-password}' | base64 -d)"

# List all rules with their github_issue labels
curl -s -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules" | \
  jq '.[] | {title: .title, uid: .uid, github_issue: .labels.github_issue}'

# Add or update a github_issue label on a rule
RULE_UID="exercise-reminder-stale"
ISSUE="willikins#11"
RULE=$(curl -s -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules/$RULE_UID")
UPDATED=$(echo "$RULE" | jq --arg issue "$ISSUE" '.labels.github_issue = $issue')
curl -s -X PUT "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules/$RULE_UID" \
  -u "$GRAFANA_AUTH" \
  -H "Content-Type: application/json" \
  -d "$UPDATED"
```

## Managing the Grafana Contact Point

```bash
GRAFANA_AUTH="admin:$(kubectl get secret -n monitoring victoria-metrics-grafana \
  -o jsonpath='{.data.admin-password}' | base64 -d)"

# List contact points
curl -s -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/contact-points" | \
  jq '.[] | {uid: .uid, name: .name, type: .type}'

# Check notification policy routing
curl -s -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/policies" | jq .
```

## Verifying GitHub Integration

```bash
# Check a specific issue's lifecycle state on the project board
gh issue view 11 --repo derio-net/willikins --json projectItems \
  --jq '.projectItems[]'

# Check recent comments added by the bridge
gh issue view 11 --repo derio-net/willikins --json comments \
  --jq '.comments[] | select(.body | contains("health-bridge")) | {createdAt, body}'
```

## Troubleshooting

### Bridge not processing alerts

1. Check pod logs for errors:
   ```bash
   kubectl logs -n monitoring -l app=health-bridge --tail=50
   ```

2. Verify the webhook contact point exists in Grafana:
   ```bash
   curl -s -u "$GRAFANA_AUTH" \
     "https://grafana.frank.derio.net/api/v1/provisioning/contact-points" | \
     jq '.[] | select(.name == "Health Bridge Webhook")'
   ```

3. Verify the notification policy routes Feature Health alerts:
   ```bash
   curl -s -u "$GRAFANA_AUTH" \
     "https://grafana.frank.derio.net/api/v1/provisioning/policies" | \
     jq '.routes[] | select(.receiver == "Health Bridge Webhook")'
   ```

### "not ready" on readiness probe

The bridge couldn't load project metadata from GitHub on startup. Check:

```bash
# Pod logs will show the error
kubectl logs -n monitoring -l app=health-bridge | head -5

# Common causes:
# - GITHUB_TOKEN expired or missing scopes (needs repo, project, read:org)
# - Project number wrong (check PROJECT_NUMBER in configmap)
# - GitHub API rate limit hit
```

### Alerts skip the bridge (no github_issue label)

Bridge logs show `Alert <name> has no github_issue label, skipping`. Add the label to the alert rule — see "Managing Alert Rule Labels" above.

### GitHub API errors

```bash
# Check for GitHub API errors in logs
kubectl logs -n monitoring -l app=health-bridge | grep -i error

# Verify GitHub token scopes (from outside the cluster)
curl -sI -H "Authorization: Bearer $(kubectl get secret -n monitoring health-bridge-secrets \
  -o jsonpath='{.data.GITHUB_TOKEN}' | base64 -d)" \
  https://api.github.com/ | grep -i x-oauth-scopes
```

## Updating the Bridge

```bash
# In the health-bridge repo:
# 1. Make changes, run tests
go test -v ./...

# 2. Tag and push
git tag v0.2.0
git push origin v0.2.0
# GitHub Actions builds and pushes to GHCR

# 3. Update the image tag in frank repo
# Edit apps/health-bridge/manifests/deployment.yaml
# Change: image: ghcr.io/derio-net/health-bridge:v0.2.0
# Commit and push — ArgoCD syncs automatically
```
