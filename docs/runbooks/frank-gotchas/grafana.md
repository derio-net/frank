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

Fix (a) was generalised to the whole `feature-health` folder on 2026-08-02 and is
now enforced by a tripwire — see [The feature-health folder alerts on workload
availability, not pod
readiness](#the-feature-health-folder-alerts-on-workload-availability-not-pod-readiness-2026-08-02),
which also documents the four traps in performing that rewrite.

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
- `litellm_chat` — a real `POST /v1/chat/completions` (fast `gemma-12b-nothin` alias), auth via the
  LiteLLM master key (`bearer_token_file`, ESO-synced from the existing Infisical
  `LITELLM_MASTER_KEY` to the `monitoring` ns; mounted `optional:true` so the pod — and the blog
  uptime probe — survive a brief unsynced window).
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

---

## Node-shutdown tombstones flood the feature-health alerts (2026-08-02)

**Symptom.** 72 of 236 Grafana rules in state `Alerting`, 48 of them
`Layer 3 Cilium Agent Down`. Telegram lit up. The cluster was entirely healthy.

**What was actually true at the time:**

| Check | Result |
|---|---|
| `kubectl get nodes` | all 7 `Ready` |
| `kubectl -n kube-system get deploy cilium-operator` | `2/2 READY, 2 AVAILABLE` |
| every `Running` pod, ready-containers vs total | **zero** partially-ready pods cluster-wide |
| `cilium-operator` pods | 50 total — 47 `Failed`, 2 `Running`, 1 `Succeeded` |

**Cause.** The Phase 6 `frank.derio.net` retirement ConfigPatch rolled the three
control planes at ~16:2x UTC. As each node drained, the scheduler kept placing
`cilium-operator` replicas onto it and the shutting-down kubelet **rejected**
every one:

```
phase:   Failed
reason:  NodeShutdown
message: Pod was rejected: Pod was rejected as the node is shutting down.
```

That rejection loop minted 47 tombstones in minutes. Kubernetes does **not**
garbage-collect them — `--terminated-pod-gc-threshold` defaults to 12500 — so
kube-state-metrics keeps exporting a NotReady `kube_pod_status_ready` series for
each one indefinitely, and each series keeps its layer's feature-health rule
firing.

This is the same object family as the graceful-shutdown tombstones documented in
`storage-secrets-ssa.md`, but a **different `reason`**: those pods were killed
mid-run (`reason: Terminated`); these were rejected before they ever started
(`reason: NodeShutdown`).

### The tooling bug this exposed

`agents/skills/frank-alert-triage/classify.py` declared:

```python
_TERMINAL_POD_STATES = frozenset({"Succeeded", "Completed", None})
```

Kubernetes has **two** terminal phases, `Succeeded` **and `Failed`**. A pod in
either can never transition back to Ready, so its readiness series is stale in
both cases. Because `Failed` was missing, the classifier muted `Succeeded`
tombstones correctly and escalated `Failed` ones as `unexplained` — 48 false
escalations, i.e. the triage tool pointed at a non-existent Cilium outage.

The runbook already knew about `Failed` tombstones; the classifier did not. When
a gotcha file and the tool that pages disagree, the tool wins in practice.

**Fixed** by adding `Failed` to the terminal set, plus an optional `pod_reason`
kwarg. The reason never changes the verdict — a terminal pod is stale regardless
— but it changes the recommended action:

- `NodeShutdown` / `Terminated` → node-lifecycle artifact, no diagnostic value,
  **safe to delete**.
- any other reason (`DeadlineExceeded` on a timed-out CI job, an app crash) →
  still a false-positive alert, but the pod object **is** the failure evidence.
  Report the reason; do **not** advise deleting it.

### Two traps when diagnosing this

1. **Never read the phase off `kubectl get pods` column output.** A node-shutdown
   tombstone renders as `0/1 ContainerStatusUnknown` — that column is a *display*
   string, not `status.phase` (which is `Failed`). Tooling that greps columns
   sees a vocabulary the API never emits.
2. **Distinguish a tombstone flood from a real outage by the pod names.** Many
   *distinct* pod names from a single ReplicaSet ⇒ tombstones; a genuine outage
   re-alerts on the same pod. Corroborate with the owning workload: a Deployment
   reading fully `AVAILABLE` beside dozens of NotReady pod alerts is the
   signature of stale series.

### Operator cleanup (recommended, not run by the triage skill)

```bash
# Node-shutdown tombstones only — leaves DeadlineExceeded/app failures intact.
kubectl get pods -A --field-selector=status.phase=Failed \
  -o jsonpath='{range .items[?(@.status.reason=="NodeShutdown")]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' \
  | while read -r ns name; do kubectl -n "$ns" delete pod "$name"; done
```

The alerts resolve on a short delay, not instantly: the deleted pod's readiness
series ages out of VictoriaMetrics on its ~5-minute staleness window.

### Standing exposure — CLOSED, see the next section

Every node reboot regenerates these tombstones, and it still does: nothing
lowers `--terminated-pod-gc-threshold` (a kube-controller-manager flag, i.e. a
Talos ConfigPatch). What changed is that **no feature-health rule reads pod
readiness any more**, so the tombstones no longer have an alert to fire. The
whole folder was moved onto workload availability the same day — see
[The feature-health folder alerts on workload availability, not pod
readiness](#the-feature-health-folder-alerts-on-workload-availability-not-pod-readiness-2026-08-02)
below, which is the durable fix this paragraph originally described as not done.

The triage-tool fix above is still load-bearing: `Failed` pods remain terminal,
they remain uncollected, and any *future* rule written against
`kube_pod_status_ready` would flood again. A tripwire now forbids exactly that
inside the `feature-health` folder.

---

## The feature-health folder alerts on workload availability, not pod readiness (2026-08-02)

The durable fix for the tombstone flood above. **14 rules** in
`apps/grafana-alerting/manifests/alert-rules-cm.yaml` were touched: 12 migrated
off `kube_pod_status_ready` (`layer-3`, `-4`, `-5`, `-6`, `-8`, `-10`, `-12`,
`-13`, `-14`, `-15`, `-19`, `-24`) plus 2 new rules
(`workload-unexpectedly-scaled-to-zero`, `layer-8-observability-collectors-down`).
`layer-25-cicd-down` was already on workload metrics from 2026-05 and is the
in-repo precedent the rest now follow.

**Why the metric had to change, not just the query.** `kube_pod_status_ready`
answers "is this *pod* ready?" The alert wants to answer "is this *workload*
serving?" A terminal pod — `Succeeded` or `Failed` — keeps exporting a NotReady
series forever, because Kubernetes does not garbage-collect terminal pods until
`--terminated-pod-gc-threshold` (default **12500**). Filtering the tombstones out
inside the existing query was considered and rejected: it keeps the wrong
question and doubles the series joined on every evaluation. The workload
counters have no pod dimension at all, so the failure mode is gone by
construction rather than suppressed.

The five metrics now in use:

| Kind | Metric | Notes |
|---|---|---|
| Deployment | `kube_deployment_status_replicas_unavailable` | direct counter |
| DaemonSet | `kube_daemonset_status_number_unavailable` | direct counter |
| StatefulSet | `kube_statefulset_status_replicas - kube_statefulset_status_replicas_ready` | **no `_unavailable` metric exists** |
| desired replicas | `kube_deployment_spec_replicas` | scale-to-0 rule only |
| end-to-end | `probe_success` | layer-8's health-bridge self-probe |

### The threshold inverts — and two polarity traps inside that inversion

Readiness rules fired on `lt 1` ("fewer than one ready"). Unavailability
counters fire on `gt 0` ("more than zero unavailable"). **All 12 migrated rules
flipped `lt 1` → `gt 0`.** Getting this backwards yields a rule that fires
constantly or never, and both look completely plausible in a diff. If a
feature-health rule seems stuck firing or suspiciously silent, check the
threshold polarity against the metric's meaning *first*.

Two things inside that inversion do **not** follow from it — one a *clause*
within a migrated rule, one a *whole rule's* threshold. Both were found by
measuring against the live cluster, and neither is visible by reading:

**1. `probe_success` is 1 on SUCCESS.** It is inverted relative to every
unavailability counter around it. `layer-8-observability-down` unions a
health-bridge `/healthz` probe into its workload branches; carried over verbatim
under the new `gt 0` threshold it would have **fired continuously while
health-bridge was healthy and gone silent the moment it died** — on the sharpest
signal in the folder, at `severity: critical`, produced by the careful obedient
diff. Shipped as `probe_success{instance="…"} == bool 0`, which maps
success→0 / failure→1 and so matches the polarity of the counts it is unioned
with. `== bool` keeps every label except `__name__`, so the surrounding
`label_replace` and `or` are unaffected.

**2. `metric == 0` is a PromQL *filter*, not a comparison.** Without `bool`, it
returns the matching series carrying their **original** value — which for this
filter is always `0`. So `workload-unexpectedly-scaled-to-zero`
(`kube_deployment_spec_replicas{…} == 0`) hands the reduce node a `0` on exactly
the series that should alert, and `gt 0` can **never** fire. Measured:
`kube_deployment_spec_replicas == 0` returned 2 series with value `0`, not `1`.
That rule therefore ships `== 0` + `evaluator: {type: lt, params: [1]}`, which
reads exactly like the pre-migration readiness threshold this
whole change removed. **Do not "tidy" it to `gt 0`: that silently deletes the
rule.** The guard
`test_the_scale_to_zero_rule_fires_on_the_series_its_filter_returns` asserts the
`== 0` / `lt 1` **pairing**, so moving to `== bool 0` requires inverting to
`gt 0` in the same edit. (`== bool 0` + `gt 0` is equally correct and was
rejected on cost only — `bool` drops the filter, pushing all 73 non-excluded
Deployments through the reduce node every minute for a normally-empty signal.)

> So: **"every feature-health rule thresholds at `gt 0`" is false**, and so is
> the narrower "every *workload-availability* rule does". Of the 39 rules in the
> folder, 27 threshold at `gt` and **12 at `lt`** — probes, heartbeat dead-man
> switches, cert-expiry countdowns and the GPU-timeshare rules all legitimately
> ask "is this below a floor?". `gt 0` is the convention for **unavailability
> counters specifically**, not for the folder. Among the workload-availability
> rules, `workload-unexpectedly-scaled-to-zero` is the single `lt 1`, and it is
> documented in-file so nobody mistakes it for a leftover.

### A pod regex is not a workload regex

The old selectors matched pod names, which carry the suffix Kubernetes appends
(`cilium-8x4kt`, `longhorn-manager-p2wjq`). A workload selector matches the
workload **name**. Carrying the regex over literally broke two rules, silently:

```
daemonset=~"cilium-.*"            -> 1 series   [cilium-envoy]           <- TRAP
daemonset=~"cilium.*"             -> 2 series   [cilium, cilium-envoy]
deployment=~"cilium.*"            -> 1 series   [cilium-operator]

daemonset=~"longhorn-manager-.*"  -> 0 series                            <- TRAP
daemonset="longhorn-manager"      -> 1 series   [longhorn-manager]
```

`cilium-.*` drops the **`cilium` DaemonSet** — the agent, the single most
important workload in Layer 3 — while still returning series for cilium-envoy
and cilium-operator, so the rule passes every structural assertion and verifies
"non-empty" against live data while never watching the agent again.
`longhorn-manager-.*` matches nothing at all: zero series, and under
`noDataState: OK` that is perfectly quiet — a rule deleted in all but name.

**Neither is catchable by diff review or by any assertion about rule structure.**
After rewriting a selector from pod-shaped to workload-shaped, assert the
**returned workload names** against `kubectl get deploy,ds,sts` — not merely that
the result is non-empty. Non-empty was true for the broken Layer 3.

### StatefulSets: the subtraction is a default vector match

There is no `kube_statefulset_status_replicas_unavailable`. The rules use
`kube_statefulset_status_replicas - kube_statefulset_status_replicas_ready`,
which is a **default (all-labels) vector match** — a single divergent label
between the two metrics silently drops the series and produces a rule that can
never fire. Verify by counting, not by eyeballing:

```
count(kube_statefulset_status_replicas - kube_statefulset_status_replicas_ready)  -> 13
count(kube_statefulset_status_replicas)                                           -> 13
```

13 in, 13 out, nothing dropped. Both metrics come from the same
kube-state-metrics target so their label sets are identical, which is why
`on(namespace,statefulset)` is unnecessary here. **Re-run that count if a query
ever spans two scrape targets.**

### A Deployment at 0 replicas is usually HEALTHY on Frank

This is the most confusing thing in the area, and `workload-unexpectedly-scaled-to-zero`
exists only because of it. Two independent mechanisms park a Deployment at 0
by design:

1. **The gpu-switcher timeshare.** gpu-1 holds the cluster's only GPU and the
   switcher hands it to one workload at a time, scaling the loser to 0. The set
   is declared in the `WORKLOADS` env var in
   `apps/gpu-switcher/manifests/deployment.yaml`
   (`ollama:ollama:ollama,comfyui:comfyui:comfyui`). Whichever one currently
   holds the GPU is at 1 and the other at 0 — **re-measure at a different moment
   and they swap; neither reading contradicts the other.**
2. **Argo Rollouts with `workloadRef.scaleDown: onsuccess`.** The controller
   scales the Helm chart's Deployment to 0 the moment the Rollout goes Healthy,
   and the Rollout's own ReplicaSets serve the traffic. Live right now:

   ```
   deploy/litellm   spec.replicas=0   available=<none>
   rollout/litellm  desired=5  ready=5  available=5
   ```

   **A `litellm` Deployment reading 0 while LiteLLM serves 5/5 is correct.** A
   naive scale-to-0 rule would have paged on a completely healthy LLM gateway on
   day one.

The rule's exclusions — `namespace!~"ollama|comfyui"`, `deployment!~"litellm"` —
are **CI-derived from those two declarative sources**, not hand-maintained: a
guard parses the `WORKLOADS` env var and every `apps/**/rollout.yaml` for
`workloadRef.scaleDown: onsuccess`, and fails if the rule's alternation literals
do not set-equal the derived sets. The split is not arbitrary either: the GPU
namespaces exist to be timeshared so excluding them wholesale is honest, whereas
`litellm` is an ordinary namespace that merely contains one Rollout-managed
Deployment — a separate guard fails if any namespace holding an `onsuccess`
Rollout is excluded wholesale.

> **Derive the exclusion set from `workloadRef.scaleDown`, never from a
> manifest's prose.** `apps/sympozium-extras/manifests/rollout.yaml` carried a
> leading comment claiming its Deployment was scaled to 0. It was not — the
> `workloadRef` sets no `scaleDown`, so the Argo Rollouts default `never`
> applies and `sympozium-apiserver` runs at 1/1. Anyone reading that comment
> would have excluded a Deployment that is supposed to be up and stopped
> watching it. The comment was corrected on 2026-08-02; the field is the fact,
> the comment is the trap.

### `for:` windows were preserved, not normalised

The design spec said "5m everywhere except DaemonSet rules"; that was wrong and
was reverted. **Swapping the metric a rule watches is not licence to re-tune its
sensitivity** — tightening `layer-6-gitops-down` (ArgoCD, critical) from 10m to
5m raises the chance of firing during a slow rollout, which is the exact
false-positive class this work removes. `layer-25-cicd-down`, the precedent, had
already been left at 10m for the same reason.

What is policy:

- **A rule whose expr queries a DaemonSet metric carries `for: 15m`**, to ride
  out a node drain. Two folder-wide guards enforce both directions (15m ⇒
  DaemonSet metric, DaemonSet metric ⇒ 15m). Today that is `layer-3`, `layer-4`,
  `layer-5` and `layer-8-observability-collectors-down`.
- **`workload-unexpectedly-scaled-to-zero` is the one 15m exemption**, recorded
  in `FIFTEEN_MINUTE_EXEMPTIONS` where the dict *value* is the written
  justification — an entry cannot be added without saying why. Its reason: a
  `Recreate`-strategy Deployment passes through 0 replicas on **every** ordinary
  rollout, and several Frank apps are on `Recreate` precisely because their PVC
  is RWO, so a short window would page on routine hand-deploys of exactly those
  apps. A second guard fails a stale exemption (rule moved off 15m or deleted)
  and a reason under 80 characters.
- **Everything else kept its pre-migration window.** Do not assume the folder is
  uniform — it currently holds `for:` values of `0s`, `0m`, `1m`, `2m`, `5m`,
  `10m`, `15m`, `30m`, `1h`, `2h` and `3h`, with five rules at 10m on purpose.

### Annotations: `$values.B.Value`, not `$value`

In Grafana unified alerting `{{ $value }}` renders the verbose multi-ref form
(`[ var='B' labels={…} value=1 ]`), unreadable in a Telegram message or a
Health Bridge tile. Every migrated rule uses
`{{ $values.B.Value | printf "%.0f" }}` (B is the reduce node in all of them),
matching the pre-existing `vk-bridge-failures` precedent.

Summaries name the **workload**, not the pod: each expr `label_replace`s the
kind-specific label into a common `workload` label plus a lowercase `kind`, so
one template renders `deployment/argocd-server` or `daemonset/cilium` across
branches. `layer-8-observability-down` is the exception — it normalises onto
`component` instead, because its third branch is a `probe_success` series with
no workload to name, and it renders `probe/health-bridge-healthz` alongside
`deployment/…` and `statefulset/…`. Its runbook annotation deliberately
interpolates **nothing**: `rollout status {{ $labels.component }}` would emit
`rollout status probe/health-bridge-healthz`, a paste-able command that is
garbage at 03:00 on a critical alert.

### Verifying a rule change — ArgoCD tells you nothing

**Grafana reads file-provisioned rules at boot and never watches them** (see the
section above on file-provisioned alerting). So ArgoCD `Synced/Healthy` proves
the ConfigMap changed and says **nothing** about what Grafana is evaluating; the
pod must be restarted. Both halves need checking separately:

```bash
# 1. Does the query mean what you think? Read the expr OUT OF the ConfigMap
#    (double YAML load — the CM has ONE data key holding a whole provisioning
#    document) and POST it through Grafana's datasource proxy. Never retype the
#    query: retyping is how "what was verified" and "what ships" diverge.
#    Grafana: PLAIN HTTP on 192.168.55.203 (https gets a TLS reset), basic auth
#    admin / secret victoria-metrics-grafana .data.admin-password in ns
#    monitoring; datasource proxy uid P4169E866C3094E38.
#
#    Query each top-level `or` branch SEPARATELY — a whole-expr result hides a
#    branch that returns nothing.

# 2. Is Grafana actually running it?
kubectl -n monitoring rollout restart deploy/victoria-metrics-grafana
```

What to assert on the result: the **workload names returned** (not just
non-empty), that every series carries the labels the annotations interpolate (an
empty `{{ $labels.workload }}` renders a broken resource path), and the
**values** — every migrated rule should read `0` on a healthy cluster, which is
the quiet state under `gt 0` and would have fired permanently under the old
`lt 1`. That last check is the polarity proof.

### Known coverage limits, deliberately not widened here

Recorded so they are not mistaken for oversights, and not folded into a query
rewrite:

- `layer-13-auth-down` stays **Deployment-only**. The `authentik-postgresql`
  StatefulSet was outside the rule before the migration, and Authentik's
  Postgres going down absolutely breaks SSO — worth its own change, not smuggled
  in under a rewrite.
- `layer-14-vcluster-down`'s namespace regex `vcluster-.*` does **not** match
  `cnc-staging-vcluster` (that namespace is suffixed, not prefixed), so that
  vCluster has never been covered — before or after this migration.
- `layer-8-observability-down` watches Deployments and StatefulSets only. That
  is a **routing** decision, not a hole: folding the `monitoring` DaemonSets back
  in would drag a critical 5m rule to 15m, so they get their own warning-level
  `layer-8-observability-collectors-down` at 15m instead, scoped to the whole
  namespace with no name selector so a third collector is covered automatically.

All of the above is guarded by
`scripts/tests/test_feature_health_workload_metrics.py`, which runs on every PR
via `.github/workflows/repo-tripwires.yml`. The durable parts are the
no-pod-readiness tripwire, the two `for: 15m` policy guards, the exemption-rot
guard and the exclusion-set derivation; the per-uid expectation maps are
migration scaffolding.
