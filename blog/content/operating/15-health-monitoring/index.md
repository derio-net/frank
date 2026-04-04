---
title: "Operating on Health Monitoring"
date: 2026-04-04
draft: false
tags: ["operations", "observability", "blackbox-exporter", "pushgateway", "grafana", "telegram", "alerting"]
summary: "Day-to-day commands for managing feature health probes, heartbeat metrics, Grafana alerts, and Telegram notifications."
weight: 115
cover:
  image: cover.png
  alt: "Frank the cluster monster tuning heartbeat monitors and checking alert dashboards"
  relative: true
---

Companion to [Health Monitoring — Feature Probes, Heartbeats, and Telegram Alerts]({{< relref "/building/22-health-monitoring" >}}).

## Quick Reference

| Component | Namespace | Port | Purpose |
|-----------|-----------|------|---------|
| Blackbox Exporter | monitoring | 9115 | HTTP endpoint probing |
| Pushgateway | monitoring | 9091 | Heartbeat metric ingestion |
| Grafana | monitoring | 3000 (LB: 192.168.55.203) | Dashboards + alerting |
| Feature Health Dashboard | — | — | `/d/fh-overview/feature-health` |

## Checking Probe Status

```bash
# Port-forward to Blackbox Exporter
kubectl port-forward -n monitoring svc/blackbox-exporter 9115:9115 &

# Probe a specific endpoint
curl -s "http://localhost:9115/probe?target=https://grafana.frank.derio.net&module=http_2xx" | grep probe_success
# Expected: probe_success 1

# Check all feature health probes via VictoriaMetrics
GRAFANA_AUTH="admin:$(kubectl get secret -n monitoring victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)"
curl -sk -u "$GRAFANA_AUTH" "https://grafana.frank.derio.net/api/datasources/proxy/uid/P4169E866C3094E38/api/v1/query" \
  --data-urlencode 'query=probe_success{probe_group="feature_health"}'
```

## Checking Heartbeat Metrics

```bash
# Port-forward to Pushgateway
kubectl port-forward -n monitoring svc/pushgateway 9091:9091 &

# View all heartbeat metrics
curl -s http://localhost:9091/metrics | grep willikins_heartbeat

# Push a test heartbeat
echo "willikins_heartbeat_last_success_timestamp $(date +%s)" | \
  curl -s --data-binary @- http://localhost:9091/metrics/job/test_job

# Delete a test metric
curl -s -X DELETE http://localhost:9091/metrics/job/test_job
```

## Grafana Alert Management

```bash
GRAFANA_AUTH="admin:$(kubectl get secret -n monitoring victoria-metrics-grafana -o jsonpath='{.data.admin-password}' | base64 -d)"

# List all alert states
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/prometheus/grafana/api/v1/alerts" | \
  python3 -c "import json,sys; [print(f'{a[\"state\"]}: {a[\"labels\"][\"alertname\"]}') for a in json.load(sys.stdin)['data']['alerts']]"

# Check alertmanager active alerts
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/alertmanager/grafana/api/v2/alerts" | python3 -m json.tool

# Check notification policies
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/policies" | python3 -m json.tool

# View a specific alert rule
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules/exercise-reminder-stale" | python3 -m json.tool
```

### Alert Rule UIDs

| UID | What It Monitors |
|-----|-----------------|
| `exercise-reminder-stale` | Exercise reminder cron heartbeat (threshold: 3h) |
| `session-manager-stale` | Session manager cron heartbeat (threshold: 10m) |
| `audit-digest-stale` | Audit digest cron heartbeat (threshold: 26h) |
| `endpoint-down` | HTTP endpoint probes (any `probe_success=0`) |
| `agent-pod-not-running` | Secure agent pod not in Running phase |

### Updating Alert Thresholds

Alert rules use the Grafana 12.x SSE 3-step format (A→B→C). To update a threshold:

```bash
# 1. GET the current rule
curl -sk -u "$GRAFANA_AUTH" \
  "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules/<uid>" > /tmp/rule.json

# 2. Edit the threshold in the C refId's conditions[0].evaluator.params
#    (the value is in the model.conditions[0].evaluator.params array)

# 3. PUT it back
curl -sk -u "$GRAFANA_AUTH" -X PUT \
  "https://grafana.frank.derio.net/api/v1/provisioning/alert-rules/<uid>" \
  -H "Content-Type: application/json" \
  -H "X-Provision-Source: api" \
  -d @/tmp/rule.json
```

## Telegram Contact Point

| Setting | Value |
|---------|-------|
| Contact point UID | `efi04e0201jb4f` |
| Bot | `@agent_zero_cc_bot` (id: 8378519865) |
| Token secret | `FRANK_C2_TELEGRAM_BOT_TOKEN` (Infisical) |
| Chat ID | `FRANK_C2_TELEGRAM_CHAT_ID` = 2034763022 (Infisical) |

```bash
# Update contact point (e.g., after bot token rotation)
curl -sk -u "$GRAFANA_AUTH" -X PUT \
  "https://grafana.frank.derio.net/api/v1/provisioning/contact-points/efi04e0201jb4f" \
  -H "Content-Type: application/json" \
  -H "X-Provision-Source: api" \
  -d '{
    "uid": "efi04e0201jb4f",
    "name": "Telegram - Willikins",
    "type": "telegram",
    "settings": {
      "bottoken": "<FRANK_C2_TELEGRAM_BOT_TOKEN>",
      "chatid": "<FRANK_C2_TELEGRAM_CHAT_ID>",
      "parse_mode": "Markdown"
    }
  }'
```

### Notification Not Arriving?

If a firing alert isn't reaching Telegram:

1. **Check repeat interval** — default grouping suppresses re-notification for the configured `repeat_interval`
2. **Check contact point** — token may have been lost after Grafana pod restart
3. **Nuclear option** — restart Grafana pod to reset alertmanager notification dedup state:
   ```bash
   kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
   ```

## Cron Jobs (Supercronic)

The secure-agent-pod runs cron jobs via supercronic watching `~/.crontab`:

```bash
# Check crontab contents
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -- cat /home/claude/.crontab

# Check supercronic process
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -- ps aux | grep supercronic

# Update crontab (supercronic auto-reloads on file change)
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -- \
  cp /home/claude/repos/willikins/scripts/willikins-agent/crontab.txt /home/claude/.crontab
```

## Pod Health

```bash
# Check all monitoring pods
kubectl get pods -n monitoring -l 'app in (blackbox-exporter,pushgateway)'

# Check Blackbox Exporter logs
kubectl logs -n monitoring -l app=blackbox-exporter --tail=20

# Check Pushgateway logs
kubectl logs -n monitoring -l app=pushgateway --tail=20

# Check Grafana logs for alert/notification issues
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana -c grafana --tail=50 | \
  grep -iE "error|warn|notify|telegram"
```

## Troubleshooting

### VMProbe/VMServiceScrape not applying

If `kubectl apply` fails with `x509: certificate signed by unknown authority`:

```bash
# The VictoriaMetrics Operator webhook caBundle is out of sync
# Check if ArgoCD overwrote it:
kubectl get validatingwebhookconfiguration -l app.kubernetes.io/instance=victoria-metrics -o yaml | grep caBundle | head -1

# Fix: ensure ignoreDifferences is set in apps/root/templates/victoria-metrics.yaml
# Then restart the operator to regenerate certs:
kubectl rollout restart deployment -n monitoring victoria-metrics-operator
```

### Dashboard shows no data

- Verify datasource UID is `P4169E866C3094E38`
- Table panels require `"format": "table"` on targets
- `ALERTS{}` metric doesn't exist for Grafana-managed alerts — use `alertlist` panel type

## References

- [Prometheus Blackbox Exporter](https://github.com/prometheus/blackbox_exporter)
- [Prometheus Pushgateway](https://github.com/prometheus/pushgateway)
- [Grafana Alerting API](https://grafana.com/docs/grafana/latest/developers/http_api/alerting_provisioning/)
- [VictoriaMetrics Operator](https://docs.victoriametrics.com/operator/)
