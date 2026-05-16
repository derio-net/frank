# Frank Gotchas — Grafana

Long-form companion to the **Grafana** section in `agents/rules/frank-gotchas.md`. The hot file has the one-liner index; this file has the full prose, recovery commands, and dated incident notes.

## OIDC secret key naming

Grafana OIDC: secret key must be `GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET` for `envFromSecret` to work.

## 12.x SSE alert rules require 3-step A→B→C format

A (datasource query), B (reduce `__expr__`, reducer: last), C (threshold `__expr__`, expression: B). Classic condition format (`datasourceUid: "-100"`) fails with `sse.parseError`.

## `ALERTS{}` does NOT exist in VictoriaMetrics for Grafana-managed alerts

Use `alertlist` panel type, not a stat panel querying `ALERTS{}`.

## Table panels need explicit `format: table`

Grafana table panels with Prometheus instant queries require `"format": "table"` on targets — without it, data returns as time-series frames that don't render in tables. Use `filterFieldsByName` transform, not `labelsToFields` with `mode: "rows"`.

## Alertmanager dedup window is 4h after re-provisioning a contact point

After re-provisioning a contact point, the alertmanager treats previously-fired alerts as "already notified" for the default 4h `repeat_interval`. Fix: restart the Grafana pod to reset internal notification state.

## File-provisioned alerting is read at boot, not watched

Grafana alerting (rules, contact points, notification policy) and the Feature Health dashboard are file-provisioned via ConfigMaps in `apps/grafana-alerting/manifests/`. They are read-only in the UI. Edit the ConfigMap YAML, commit, push, then restart the Grafana pod (`kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana`) — provisioning files are read at boot, not watched.

## Provisioning env-var coercion turns numbers into ints

Grafana provisioning env var substitution coerces numeric values to integers during YAML-to-JSON transformation — even double-quoted `"$VAR"` doesn't help. Workaround: use YAML block scalar `chatid: |\n  $VAR` to force string type. See [grafana/grafana#69950](https://github.com/grafana/grafana/issues/69950).

## "Cannot change provenance from 'api' to 'file'"

If API-provisioned resources exist with matching UIDs, they must be deleted from the database first (scale down Grafana, use sqlite3 to `DELETE FROM provenance_type` and `DELETE FROM alert_rule`, scale back up).

## Helm chart regenerates admin password Secret on re-render

PVC-backed database retains old password. Fix: `grafana cli admin reset-admin-password "$NEW_PASS"` inside the pod after re-deployment.

## VictoriaMetrics chart `genCA` regenerates webhook caBundle

VictoriaMetrics Helm chart `genCA` regenerates webhook caBundle on every render — must add `ignoreDifferences` on `ValidatingWebhookConfiguration` `.webhooks[].clientConfig.caBundle` in the ArgoCD Application to prevent ArgoCD from overwriting the operator-managed cert.

## `kube_pod_status_ready` false-positives in batch namespaces

`kube_pod_status_ready{condition="true"}` false-positives in namespaces with batch workloads (Tekton, Argo Workflows, Jobs) — task pods stay around in Completed / Error state after their PipelineRun/Workflow finishes (Tekton leaves them for log inspection). Their Ready condition is False post-exit, so a Grafana alert that uses `kube_pod_status_ready{namespace=~"...",condition="true"}` + `reduce.last` + `threshold lt 1` will fire whenever any task pod is in the "last" position of the returned vector. The alert title looks ominous (`Layer 25 CI/CD Platform Degraded`) but cluster is fine.

Discovered 2026-05-14 in `layer-25-cicd-down`. Two fixes:
- (a) rewrite the query to use `sum(kube_deployment_status_replicas_unavailable{namespace=~"..."}) > 0` — Deployments are the long-running things; task pods aren't owned by Deployments and are naturally excluded
- (b) add a TTL GC for old PipelineRuns/Jobs (we shipped `apps/tekton/manifests/pipelinerun-ttl-gc.yaml` — daily 04:30 UTC, 7-day TTL)

Both fixes belong together — the query rewrite stops the false positive, the TTL keeps the namespace from accumulating clutter.
