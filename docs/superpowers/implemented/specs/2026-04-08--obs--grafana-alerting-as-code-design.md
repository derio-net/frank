# Grafana Alerting as Code — Design

**Date:** 2026-04-08
**Status:** Spec
**Repo:** frank
**Related:** `docs/superpowers/plans/2026-04-01--obs--work-lifecycle-health-monitoring.md` (M2 — established the API-provisioned baseline this spec replaces)

## Problem

Frank's Grafana alerting stack is currently API-provisioned: alert rules, contact points, notification policies, and the Feature Health dashboard were created via REST API calls and live in Grafana's PVC-backed SQLite database. They survive pod restarts but not PVC loss. Recovery requires re-running curl commands documented in blog posts — fragile, manual, and incompatible with Frank's "everything declarative, ArgoCD self-heals" philosophy.

The supporting infrastructure (Blackbox Exporter, Pushgateway, Health Bridge) is already declarative under `apps/`. Only the Grafana-internal configuration is the snowflake.

## Goal

Codify the existing Grafana alerting stack as Kubernetes manifests managed by ArgoCD. Make alert rules, contact points, notification policies, and the Feature Health dashboard reproducible from Git. Survive PVC loss as a non-event.

## Scope

**In scope:**
- 5 alert rules currently in the Feature Health folder
- 2 contact points (Telegram, Health Bridge webhook)
- Notification policy with severity-based routing
- Feature Health dashboard (with layout improvements)
- Migration from API-provisioned to file-provisioned
- Verification that the full alerting chain still works post-migration

**Out of scope (explicitly):**
- Expanding monitoring coverage to additional services (more probes, more pod namespaces, more heartbeat jobs). The Feature Health dashboard currently shows ~5 of each because that's all that exists in the metrics. Adding services is a follow-up effort.
- Cluster Health dashboard (separate effort, tracked in `willikins/context/current-priorities.md` backlog)
- Other Grafana dashboards beyond Feature Health
- Migrating other Grafana configuration (datasources are already file-provisioned; OIDC stays in Helm values)

## Approach

**Grafana file-based provisioning via ConfigMaps**, mounted into Grafana's standard provisioning directories using `extraConfigmapMounts` in the victoria-metrics Helm values. This is the same pattern already used for the VictoriaLogs datasource — proven, no new dependencies, integrates cleanly with ArgoCD.

Alternatives considered and rejected:
- **Terraform Grafana provider** — introduces Terraform into a stack that's purely ArgoCD + manifests. Overkill for 5 rules.
- **Pulumi** — same problem; doesn't integrate with ArgoCD's reconciliation loop. Better fit for infrastructure layer (Omni configs, DNS) than for in-cluster Grafana config.
- **API-provisioning Job** — fragile, requires idempotency logic, doesn't survive PVC loss without re-running. Defeats the purpose.

## Architecture

### New ArgoCD Application

`apps/grafana-alerting/` — raw manifests pattern, same as `blackbox-exporter`, `pushgateway`, and `health-bridge`. Application CR in `apps/root/templates/grafana-alerting.yaml`.

### File Layout

```
apps/grafana-alerting/
└── manifests/
    ├── alert-rules-cm.yaml          # ConfigMap: 5 alert rules in feature-health folder
    ├── contact-points-cm.yaml       # ConfigMap: Telegram + Health Bridge webhook
    ├── notification-policy-cm.yaml  # ConfigMap: routing tree
    └── dashboard-cm.yaml            # ConfigMap: dashboard provider config + Feature Health JSON

apps/root/templates/
└── grafana-alerting.yaml            # ArgoCD Application CR

apps/victoria-metrics/
└── values.yaml                      # Modified: extraConfigmapMounts + envFromSecret entries
```

**Why split into 4 ConfigMaps:**
- Rules / contact points / policy have different change frequencies and review burdens. Adding a rule shouldn't risk touching contact point YAML.
- Dashboard mounts to a different Grafana directory (`/etc/grafana/provisioning/dashboards/` vs `/etc/grafana/provisioning/alerting/`).
- Keeps each file under a sane size; the dashboard JSON alone will be the largest.

### Helm Values Changes

In `apps/victoria-metrics/values.yaml` under `grafana:`:

1. **`extraConfigmapMounts`** — append 4 entries, one per ConfigMap, mounting to the appropriate provisioning subdirectory.
2. **`envFromSecret`** — ensure the Grafana pod has these env vars available (referenced by contact points provisioning):
   - `FRANK_C2_TELEGRAM_BOT_TOKEN`
   - `FRANK_C2_TELEGRAM_CHAT_ID`
   - `HEALTH_BRIDGE_WEBHOOK_SECRET`

The OIDC `envFromSecret` pattern already exists in the values file. Reuse the same mechanism. Verify the ExternalSecret backing it includes these three keys (the work-lifecycle M2 plan noted the ExternalSecret was expanded to map 7 secrets including `GRAFANA_API_KEY` — confirm at plan time which secrets are already wired and which need adding).

## Alert Rules

Five rules, all in folder `feature-health`. Each uses Grafana 12.x SSE 3-step format (A: datasource query → B: reduce → C: threshold). Classic condition format will fail with `sse.parseError` — see `.claude/rules/frank-gotchas.md`.

| UID | Title | Query (A) | Threshold (C) | For | Evaluate Every | Severity | Labels |
|-----|-------|-----------|---------------|-----|----------------|----------|--------|
| `exercise-reminder-stale` | Exercise Reminder Stale | `time() - willikins_heartbeat_last_success_timestamp{job="exercise_reminder"}` | gt 10800 | 1m | 5m | critical | `github_issue=willikins#11` |
| `session-manager-stale` | Session Manager Stale | `time() - willikins_heartbeat_last_success_timestamp{job="session_manager"}` | gt 600 | 5m | 1m | critical | `github_issue=willikins#13` |
| `audit-digest-stale` | Audit Digest Stale | `time() - willikins_heartbeat_last_success_timestamp{job="audit_digest"}` | gt 93600 | 1h | 30m | warning | `github_issue=willikins#12` |
| `endpoint-down` | Endpoint Down | `probe_success{probe_group="feature_health"}` | lt 1 | 5m | 1m | critical | *(none — multi-target)* |
| `agent-pod-not-running` | Agent Pod Not Running | `kube_pod_status_phase{namespace="secure-agent-pod", phase="Running"}` | lt 1 | 5m | 1m | critical | `github_issue=frank#8` |

**VictoriaMetrics datasource UID:** `P4169E866C3094E38`

**Threshold note:** `exercise-reminder-stale` is set to 10800s (3 hours) in this spec. The current API-provisioned version is at 60s as a testing artifact — that gets restored to 10800s during migration, not codified as 60s.

**Reduce step (B) settings:** reducer `last`, mode `dropNN`, expression `A`.

**Threshold step (C) settings:** datasourceUid `__expr__`, type `threshold`, expression `B`.

### Extensibility

Rules grouped by pattern within `alert-rules-cm.yaml`:
- Heartbeat-stale group (3 rules)
- Endpoint-down group (1 rule)
- Pod-not-running group (1 rule)

Adding a new heartbeat alert means appending to the heartbeat group: change job name, threshold, severity, and `github_issue` label. Same YAML file, same pattern, no API calls.

## Contact Points

### Telegram - Willikins

- **UID:** `efi04e0201jb4f` (preserved from current API-provisioned version to keep notification policy refs stable)
- **Type:** `telegram`
- **Bot:** `@agent_zero_cc_bot` (id: 8378519865)
- **Settings:**
  - `bottoken: $FRANK_C2_TELEGRAM_BOT_TOKEN`
  - `chatid: $FRANK_C2_TELEGRAM_CHAT_ID`
  - `parse_mode: Markdown`

### Health Bridge Webhook

- **Name:** `Health Bridge Webhook`
- **Type:** `webhook`
- **Settings:**
  - `url: http://health-bridge.monitoring.svc.cluster.local:8080/webhook`
  - `httpMethod: POST`
  - `authorization_scheme: Bearer`
  - `authorization_credentials: $HEALTH_BRIDGE_WEBHOOK_SECRET`

Both env vars resolved by Grafana at startup from the pod env (injected via `envFromSecret`).

## Notification Policy

Single routing tree:

- **Root:** default receiver `Telegram - Willikins`, group_wait 30s, group_interval 3m, repeat_interval 3m
- **Routes:**
  1. `severity=critical` → `Telegram - Willikins` (continue: true)
  2. `severity=warning` → `Telegram - Willikins` (continue: true)
  3. `grafana_folder=Feature Health` → `Health Bridge Webhook` (continue: false)

`continue: true` on severity routes means alerts match both Telegram (human notification) and the Health Bridge route (GitHub lifecycle automation).

## Dashboard

### Folder

Move from root level to `feature-health` folder. Grafana's file-based dashboard provisioning supports `folder:` in the dashboard provider config — the folder is created on Grafana startup if absent.

### Layout

| Position | Panel | Type | Purpose |
|----------|-------|------|---------|
| Top-left | Feature Health Status | stat-style summary | Big-number count of firing alerts in the Feature Health folder, color-coded |
| Top-right (upper) | Cron Job Heartbeats — Sub-hourly | table | `(time() - willikins_heartbeat_last_success_timestamp{job=~"session_manager\|vk_issue_bridge"}) / 60`, columns: job, Minutes Since Last Success. Thresholds: green <60m, yellow <180m, red ≥180m |
| Top-right (lower) | Cron Job Heartbeats — Daily | table | `(time() - willikins_heartbeat_last_success_timestamp{job="audit_digest"}) / 60`, columns: job, Minutes Since Last Success. Thresholds: green <1500m, yellow <1560m, red ≥1560m (aligned with the `audit-digest-stale` rule threshold of 93600s = 26h) |

> **Retroactive update (2026-04-24):** Originally specified as one panel with uniform 60/180m thresholds. Split into two cadence-bucketed panels because `audit-digest` runs daily (rule threshold 26h = 1560m), so the original thresholds painted it RED for ~21h of every 24h cycle despite its alert being `Normal`. Sub-hourly heartbeats (`session_manager`, `vk_issue_bridge`) keep the original tight thresholds; daily heartbeats get thresholds aligned with the rule. When adding a new cron, place it in the panel that matches its cadence; if a third cadence bucket emerges, add a third panel rather than widening either threshold.
| Middle | Endpoint Probes | table | `probe_success{probe_group="feature_health"}`, columns: instance, Success (UP/DOWN). 1=UP green, 0=DOWN red |
| Bottom | Pod Status | table | `kube_pod_status_phase{namespace=~"secure-agent-pod\|n8n-01\|paperclip-system", phase="Running"}`, columns: namespace, pod, phase, Count |

### Top-left panel mechanism

The original API-provisioned dashboard used an `alertlist` panel that grew into a verbose dropdown that didn't fit the panel size. We need a compact summary instead.

The constraint: `ALERTS{}` doesn't exist in VictoriaMetrics for Grafana-managed alerts (gotcha documented in `.claude/rules/frank-gotchas.md`). Options to evaluate at plan time:

1. **Stat panel via Grafana datasource** — query `grafana` datasource for alert state count. Verify availability in Grafana 12.x.
2. **Compact alertlist** — use `alertlist` panel with view options (e.g., `viewMode: stat`, `showInstances: false`) tuned to display just a count.
3. **Stat panel scraping `/api/v1/alerts`** via a sidecar — rejected, too much complexity.

The implementation plan picks one based on what actually works in the running Grafana. Spec leaves the exact mechanism open; the requirement is "compact summary showing firing alert count, fits in a small panel cell."

### Table panels gotcha

Prometheus instant queries in table panels require `"format": "table"` on targets. Without it, Grafana returns time-series frames that don't render. Use `filterFieldsByName` transform, not `labelsToFields` with `mode: rows` (which doesn't work). Documented in `.claude/rules/frank-gotchas.md`.

### Editing workflow

The provisioned dashboard is read-only in the UI. To edit:
1. Open the provisioned dashboard, "Save as" to a scratch dashboard
2. Edit the scratch copy in the UI
3. Export JSON
4. Update the ConfigMap, commit, push
5. ArgoCD syncs; Grafana picks up changes after pod restart (provisioning files are read at boot, not watched)
6. Delete the scratch dashboard

This is the standard workflow for file-provisioned dashboards.

## Migration

The migration is destructive in a controlled sense: existing API-provisioned resources must be removed before file-provisioning takes over, otherwise we get duplicates. Grafana doesn't deduplicate file-provisioned vs API-provisioned resources with the same name — they're treated as separate objects.

### Steps

1. Build and commit the 4 ConfigMaps and the Application CR
2. ArgoCD syncs — Grafana now has both API-provisioned and file-provisioned versions side by side
3. Verify file-provisioned versions work: rules visible, marked as "provisioned" (read-only), notification policy routes correct, contact points present, dashboard appears in `feature-health` folder
4. Delete API-provisioned originals via API calls (the curl commands documented in `blog/content/operating/15-health-monitoring/`)
5. Restart Grafana pod to flush alertmanager dedup state (required after contact point changes, gotcha documented)
6. Final end-to-end verification (see Verification section)

### Rollback

1. Revert the ArgoCD Application sync (delete the Application or remove the manifests from Git)
2. Re-run the API calls from `blog/content/operating/15-health-monitoring/` to recreate the originals

The blog post commands remain the source of truth for the rollback path until this spec is fully deployed and verified, after which they can be marked as historical.

## Verification

End-to-end test after migration completes:

- [ ] All 5 rules visible in Grafana UI under `feature-health` folder, marked as "provisioned" (read-only)
- [ ] Notification policy shows the 3 routes
- [ ] Both contact points present, marked as "provisioned"
- [ ] Feature Health dashboard appears in `feature-health` folder, all 4 panels render with data
- [ ] Top-left summary panel shows correct firing alert count (test with a known-firing alert)
- [ ] Trigger test: temporarily lower `exercise-reminder-stale` threshold to 60s (in the ConfigMap, via a commit), wait for ArgoCD sync + Grafana reload, confirm:
  - Alert transitions Normal → Pending → Firing
  - Telegram notification arrives at `@agent_zero_cc_bot`
  - Health Bridge webhook fires; corresponding GitHub project item transitions to `dead`
- [ ] Restore threshold to 10800s, commit, sync
- [ ] Restart Grafana pod, confirm all rules/policies/dashboard reload from ConfigMaps and survive (PVC loss simulation)

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Grafana file-provisioning syntax differs from API JSON in subtle ways | Plan-time verification step: deploy one rule first, confirm it works, then port the rest |
| Contact point UID mismatch breaks notification policy refs | Preserve existing UIDs (`efi04e0201jb4f` for Telegram) |
| Env var resolution fails silently (missing secret) | Verify ExternalSecret keys at plan time before writing the contact points ConfigMap |
| Top-left panel mechanism doesn't have a clean solution | Spec accepts a compact alertlist as fallback; not a blocker |
| ArgoCD self-heal fights with manual UI edits | File-provisioned resources are read-only in UI by design; this is a feature |
| Dashboard JSON drift from in-UI edits | Document the scratch-dashboard editing workflow; enforce via convention |

## Open Questions

None blocking. The top-left panel mechanism is the only TBD, and it's bounded — three options listed, plan picks one based on what works.

## Decisions Captured

- **Tool choice:** Grafana file-based provisioning via ConfigMaps. Not Terraform, not Pulumi, not API-provisioning Job.
- **App split:** Separate `apps/grafana-alerting/` ArgoCD Application, not co-located with `apps/victoria-metrics/`. Different lifecycle, keeps the victoria-metrics app focused.
- **ConfigMap split:** 4 ConfigMaps (rules, contact points, policy, dashboard). Different change frequencies, different mount targets.
- **Secret handling:** Env var injection via `envFromSecret` (option B from brainstorming). Not inline secrets, not leaving contact points API-provisioned.
- **Scope:** Codify existing alerting + dashboard layout fixes only. Expanding monitoring coverage is a follow-up. Cluster Health dashboard is a separate backlog item.
- **Folder placement:** Feature Health dashboard moves to a `feature-health` folder.
- **Top-left panel:** replace the verbose alertlist with a compact summary. Exact mechanism deferred to plan time.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| Grafana Alerting as Code Implementation Plan | derio-net/superpowers-for-vk | `2026-04-08--obs--grafana-alerting-as-code` | — |
