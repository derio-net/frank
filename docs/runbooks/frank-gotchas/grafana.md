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

## Verifying a `mute_time_intervals` mute actually suppressed delivery

A time-interval mute on a notification-policy route does NOT surface the way silences do, so the obvious checks mislead:

- The alert's v2 `/api/alertmanager/grafana/api/v2/alerts` status stays `state: active` — only **silences** (`silencedBy`) and **inhibitions** (`inhibitedBy`) flip an alert to `suppressed`. A time-interval mute is applied at the *notify* stage, leaving `state: active`.
- Grafana 12's v2 alert `status` object has **no `mutedBy` field at all** (`{state, silencedBy, inhibitedBy}` only) — querying `.status.mutedBy` yields `null` whether or not the mute is active. It proves nothing.

Verify the mute by the **dispatcher-vs-notification metric gap** on the Grafana `/metrics` endpoint (`kubectl exec deploy/victoria-metrics-grafana -c grafana -- wget -qO- http://127.0.0.1:3000/metrics`):

- `grafana_alerting_dispatcher_alert_processing_duration_seconds_count` increments — the alert reached the dispatcher and matched a route.
- `grafana_alerting_notification_latency_seconds_count` stays **0** — the notify stage sent nothing.
- `grafana_alerting_silences{state="active"} 0` — rules out a silence, leaving the mute timing as the only suppression mechanism.

Two corroborating signals from the v2 `/alerts` API:

- `receivers[]` reflects ROUTING, not delivery. A canary route whose receiver is set to a real contact point (e.g. `Telegram - Willikins`) still lists that name even when fully muted — the mute, not the receiver, stops delivery.
- A **single** entry in `receivers[]` confirms `continue: false` stopped route evaluation at that route. If the alert had continued, downstream matching routes (e.g. `grafana_folder="feature-health"` → `Health Bridge Webhook`) would appear as additional receivers. For the cert-expiry canary this is the proof that health-bridge never sees the canary (no never-closing bug issue).

Established 2026-06-07 proving the cert-expiry canary's perma-mute (issue #251, `apps/grafana-alerting/manifests/notification-policy-cm.yaml`). The canary's two instances (warning 14d + critical 7d) fired, dispatcher count = 2, notification latency count = 0, single receiver — Telegram and health-bridge both silent, operator confirmed no Telegram message.

## Telegram contact point uses HTML parse_mode — `<>&` in annotations → 400 Bad Request, silent non-delivery

The `Telegram - Willikins` contact point sends messages with Telegram's **HTML `parse_mode`**. Grafana renders the alert's `summary`/`runbook` annotations into the message body **without HTML-escaping**, so any of these in an annotation value breaks Telegram's HTML parser:

- `<…>` that looks like a tag — e.g. a `<node-ip>` placeholder, `<pod>`, `<name>`
- a bare `<` or `>` (including `>6`, `<1GiB` written literally)
- a bare `&`

Telegram's Bot API rejects the malformed message with **`400 Bad Request`**, and Grafana's notifier aborts the send. The failure is **silent end-to-end**:

- The rule still evaluates, fires, and dispatches (`ngalert ... "Sending alerts to local notifier" count=1`).
- **Other receivers on the same alert deliver fine** — e.g. a `feature-health` alert still reaches the Health Bridge webhook (which sends raw JSON, no HTML), so `frank-ops#N` lifecycle works. Only Telegram is affected.
- `grafana_alerting_notification_latency_seconds_count` keeps incrementing (other alerts/receivers), and in practice `grafana_alerting_notification_errors_total` did **not** surface this — so the metrics look healthy.

The only reliable signal is the notifier log:

```
kubectl logs -n monitoring deploy/victoria-metrics-grafana -c grafana \
  | grep -iE 'ngalert.notifier.*level=error.*telegram'
# ... err="Telegram - Willikins/telegram[0]: ... failed to send telegram message:
#         webhook response status 400 Bad Request"
```

**Rule:** keep `<`, `>`, `&` out of `summary`/`runbook` annotation *values*. Use `6+` not `>6`, a bracket-free placeholder like `NODE_IP` not `<node-ip>`, and `{{ $labels.* }}` templates for real values. YAML **comments** (`#`) in the rule are safe — Grafana strips them at provisioning, so they never reach the message.

**Why static checks miss it:** the YAML is valid, the rule provisions cleanly, routing/labels are correct — the rule looks perfect until it actually tries to *deliver*. Only an end-to-end firing (real or synthetic-metric-import) exercises the Telegram send path. Caught 2026-06-08 on the `layer-1-nic-link-flap` rule: it fired correctly on a real gpu-1 `enp3s0` flap but its annotations carried `talosctl -n <node-ip> dmesg` and `(>6 carrier changes/30m)`, so every page 400'd and the operator got nothing — discovered only by driving the post-merge Test Plan. This is the concrete proof of the repo rule "a layer is not Deployed until its workflow has been triggered + observed end-to-end."

## GPU-time-shared layers: probe end-to-end, not pod existence (2026-06-15)

**Symptom.** The Derio Ops board was **all green** while local inference was **down
cluster-wide**: `ai-alert-helper` was the only App showing trouble (Degraded — its `digest`/
`surge-check` CronJobs `curl -f`'d the helper → the helper's LiteLLM call 500'd → `curl` exit 22).
Every Ollama-backed LiteLLM model was returning **500**.

**Root cause (two layers).**
1. **The outage.** gpu-1 holds the cluster's only GPU; the `gpu-switcher` hands it to **one**
   workload at a time — Ollama (Layer 11 inference) **or** ComfyUI (Layer 16 media). When the GPU
   went to ComfyUI, the `ollama` Deployment scaled to `replicas:0` (its App has
   `ignoreDifferences` on `/spec/replicas`, so it stays **Synced/Healthy with 0 pods**). LiteLLM
   completions to `ollama.ollama.svc:11434` then failed with `APIConnectionError ... [Operation
   not permitted]` — **EPERM is Cilium socket-LB's response to a ClusterIP with no endpoints**, NOT
   a dead backend (a dead backend gives ECONNREFUSED). This is a *red herring* that points at a
   network policy; it's actually "zero pods behind the Service."
2. **The blind dashboard.** The `Layer 11 Local Inference Degraded` rule queried the **per-pod**
   `kube_pod_status_ready{namespace=~"ollama|litellm"}` and fired if `< 1`. With 0 Ollama pods
   there are **0 series** — nothing `< 1` to fire on. The rule can only catch "a pod that exists
   but is NotReady," never "the pod was scaled away." `kube_deployment_status_replicas_unavailable`
   is **also** 0 (0 desired → 0 unavailable). LiteLLM emits **no** Prometheus metrics (OSS —
   Enterprise-only). So inference was un-monitored end-to-end, and the alerter that should have
   reported it (`ai-alert-helper`) was itself a victim of the same outage.

**Fix — synthetic end-to-end probes (plan `2026-06-15--obs--gpu-timeshare-health-probes`).**
Two blackbox-exporter modules + VMProbes produce `probe_success{layer="11"|"16"}`:
- `litellm_chat` — a real `POST /v1/chat/completions` (fast `gemma-12b-nothin` alias), auth via a
  dedicated least-privilege virtual key (`bearer_token_file`, mounted `optional:true` so the pod —
  and the blog uptime probe — start before the key is minted).
- `comfyui_object_info` — `GET /object_info` asserting a core node (`KSampler`) is loaded, so it
  catches custom-node import failures, not just liveness.

**Honest-but-quiet routing.** Exactly one of inference/media is **always down by design** (whoever
lacks the GPU), so paging on either is pure noise → it'd get muted → silent again. The per-layer
rules carry `gpu_timeshare: "true"` and an **early `continue:false` route to Health Bridge only**
(degraded tile, **no Telegram**; ORDER IS LOAD-BEARING — it must precede the `severity=*` →
Telegram routes, same reason as the cert-canary watchdog). `noDataState: Alerting` so a vanished
probe reads as down, not the old silent `OK`. The **only** pager is `gpu-node-both-down`:
`sum(probe_success{probe_group="gpu_timeshare"}) < 1` (both down → gpu-1/driver dead, both scaled
to 0, or switcher stuck), `severity:critical`, **no** `gpu_timeshare` label (routes normally →
Telegram + health-bridge bug), `for:10m` to ride out the switch-over gap, `noDataState: OK` (both
series absent = scrape gap = monitoring blindness, not a confirmed GPU death).

**Truth table.** Ollama owns GPU → L11 green, L16 degraded(quiet). ComfyUI owns GPU → L11
degraded(quiet), L16 green. Neither → both degraded **+ PAGE**.

**Verify (VMUI, datasource VictoriaMetrics):** `probe_success{probe_group="gpu_timeshare"}` — one
series 1, one series 0 in steady state. Which workload holds the GPU: `kubectl -n ollama get deploy
ollama` vs `kubectl -n comfyui get deploy comfyui` (the `0/0` one yielded the GPU).
