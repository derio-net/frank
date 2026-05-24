---
title: "Operating on Health Bridge"
date: 2026-04-04
draft: false
tags: ["operations", "observability", "grafana", "github", "go", "alerting"]
summary: "Day-to-day commands for managing the health-bridge service — checking status, testing webhooks, managing alert labels, and troubleshooting GitHub API issues."
weight: 116
---

Companion to [Health Bridge — Closing the Loop from Grafana Alerts to GitHub Issues]({{< relref "/docs/building/23-health-bridge" >}}).

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

### Duplicate bug issues appearing

**Symptom:** Multiple identical `[Bug] ... is dead` issues created for the same alert.

**Cause:** Before v0.2.0, the bridge had no dedup logic. If you're running v0.1.0 or earlier, upgrade.

**If running v0.2.0+:** This can happen once after a pod restart (in-memory state is lost). The GitHub search safety net should prevent all but the first duplicate. If duplicates persist, check pod restart frequency.

**Cleanup:** Close duplicates with `gh issue close <number> --repo derio-net/<repo> --comment "Duplicate"`, keeping the earliest one open.

### A Layer flaps to degraded after a Job or one-off pod runs

**Symptom:** A Layer tile goes `degraded` (and an `L<N> ... failing` alert fires) with no real outage. The named `component` is a pod that has already `Completed` — typically a `Job` pod or a one-off `kubectl`-applied debug pod.

**Cause:** A pod reports `kube_pod_status_ready{condition="true"}=0` the instant it terminates. Rules that select a whole namespace — the Layer 8 Observability rule sweeps all of `monitoring` — pick those corpses up as if they were unready workloads.

**Fix:** The Layer 8 rule already excludes terminated pods with `unless on(namespace,pod) kube_pod_status_phase{phase=~"Succeeded|Failed"} == 1`. If a *new* namespace-wide rule shows the same flap, add the same guard. To find the culprit and clear a stray corpse:

```bash
# Which monitoring pods currently report ready=0?
kubectl exec -n monitoring deploy/blackbox-exporter -- wget -qO- \
  'http://vmsingle-victoria-metrics-victoria-metrics-k8s-stack:8428/api/v1/query?query=kube_pod_status_ready{namespace="monitoring",condition="true"}==0'

# Leftover Completed pods in the namespace?
kubectl get pods -n monitoring --field-selector=status.phase=Succeeded
# Delete a confirmed corpse:
kubectl delete pod <name> -n monitoring
```

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

## Layer trackers (Pass 3)

As of 2026-04-20, the 20 Layer tracker Issues on the Derio Ops board were relocated from the public `derio-net/frank` to the private `derio-net/frank-ops` repo, with Issue numbers aligned 1:1 to Layer numbers (so `frank-ops#13` is Layer 13 Authentik). Each Layer has one Grafana alert rule with `github_issue: "frank-ops#<LAYER>"` driving its Lifecycle field automatically.

<!-- MEDIA: screenshot | Derio Ops board showing all 20 Layer trackers with their Lifecycle tiles | Open the private derio-net/frank-ops board, filter to the Lifecycle view, capture the full grid of Layer tracker tiles -->
<!-- {{</* screenshot src="derio-ops-layer-grid.png" caption="Derio Ops board: every Layer tracker showing its current Lifecycle state driven by Grafana rules" */>}} -->

### Smoke-testing a Layer via direct webhook

The direct-Bridge test bypasses Grafana's rule evaluation, which is handy for verifying the Bridge + GitHub path without waiting for a real metric to dip:

```bash
export WEBHOOK_SECRET=$(kubectl get secret -n monitoring health-bridge-secrets \
  -o jsonpath='{.data.WEBHOOK_SECRET}' | base64 -d)
kubectl port-forward -n monitoring svc/health-bridge 8080:8080 &

# Fire a critical alert at Layer 13 (Authentik)
curl -s -X POST http://localhost:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{
    "status":"firing",
    "labels":{"alertname":"smoke","severity":"critical","github_issue":"frank-ops#13"},
    "annotations":{"summary":"Smoke test"},
    "startsAt":"2026-04-20T00:00:00Z"
  }]}'
# Response: {"processed": 1, "total": 1}
```

### Checking a Layer's current Lifecycle state

```bash
gh api graphql -f query='
{
  repository(owner:"derio-net", name:"frank-ops") {
    issue(number:13) {
      projectItems(first:5) {
        nodes {
          fieldValueByName(name:"Lifecycle") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
        }
      }
    }
  }
}' --jq '.data.repository.issue.projectItems.nodes[].fieldValueByName.name'
# → healthy  (or degraded, dead, etc.)
```

### Reloading rules after editing the ConfigMap

Grafana's provisioning files are read at boot, not watched. After editing `apps/grafana-alerting/manifests/alert-rules-cm.yaml`:

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "feat(obs): ..."
git push origin main

# Wait for ArgoCD to sync the ConfigMap
kubectl annotate application -n argocd grafana-alerting \
  argocd.argoproj.io/refresh=hard --overwrite

# Restart Grafana to pick up the new ConfigMap
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
```

Two gotchas learned the hard way:

1. **RWO PVC + RollingUpdate deadlock.** Grafana's PVC is `ReadWriteOnce`. When the Deployment rolls due to a ConfigMap checksum change, the new pod can't mount the volume while the old pod holds it. If the rollout hangs, scale the Deployment to 0 briefly to force a detach, then back up. A more durable fix (switch `strategy.type` to `Recreate`) is tracked as a follow-up.
2. **Listen for `parseError` in the new pod's logs** before trusting that a rule change took effect:
   ```bash
   kubectl logs -n monitoring -l app.kubernetes.io/name=grafana --tail=200 | grep -iE 'parseError|provisioning.*error'
   ```

### Verifying a rule is loaded via the Grafana API

```bash
GRAFANA_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana \
  -o jsonpath='{.items[0].metadata.name}')
ADMIN_PASS=$(kubectl get secret -n monitoring victoria-metrics-grafana \
  -o jsonpath='{.data.admin-password}' | base64 -d)

kubectl exec -n monitoring "$GRAFANA_POD" -c grafana -- \
  curl -s -u admin:"$ADMIN_PASS" \
  http://localhost:3000/api/v1/provisioning/alert-rules/layer-13-auth-down \
  | jq '{uid, title, labels, annotations}'
```

