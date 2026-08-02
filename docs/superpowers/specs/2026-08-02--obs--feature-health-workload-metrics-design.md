# Feature-health alerts on workload availability, not per-pod readiness

**Status:** Draft
**Layer:** obs
**Date:** 2026-08-02
**Supersedes nothing.** Follow-up to PR #752, which fixed the *triage* of this
false-positive class. This fixes the *source*.

## Problem

Twelve feature-health rules in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`
alert on `kube_pod_status_ready{condition="true"} < 1`. (Eleven at the time this
spec was written; phase 1's folder-wide tripwire found a twelfth,
`layer-8-observability-down`, treated separately below.) That metric carries one
series per **pod**, and a terminal pod's series never goes away:

- Kubernetes has two terminal phases, `Succeeded` and `Failed`. A pod in either
  can never become Ready, so its readiness series reads NotReady forever.
- Kubernetes does not garbage-collect terminal pods —
  `--terminated-pod-gc-threshold` defaults to **12500**.
- kube-state-metrics keeps exporting the stale series until someone deletes the
  pod by hand.

On 2026-08-02 the Phase 6 `frank.derio.net` retirement ConfigPatch rolled the
three control planes. As each node drained, the scheduler kept placing
`cilium-operator` replicas onto it and the shutting-down kubelet rejected each
one (`phase: Failed`, `reason: NodeShutdown`). 47 tombstones from a single
ReplicaSet produced **48 firing alerts against a completely healthy cluster** —
every Deployment fully available, zero partially-ready Running pods anywhere.

A further 21 `Succeeded` tombstones from earlier reboots had been firing
unnoticed underneath, so the standing baseline was 25 permanently-firing alerts
rather than the true 3.

`agents/rules/frank-gotchas.md` already recommends
`kube_deployment_status_replicas_unavailable` for exactly this class, and
**Layer 25 was already migrated** on 2026-05-14 (see the rationale comment above
`layer-25-cicd-down`) for the same reason — Tekton task pods accumulating in
Completed state. This spec finishes the job for the other eleven layers.

## Why per-pod readiness is the wrong question

`kube_pod_status_ready` answers "is this pod ready?" The alert wants to answer
"is this capability being served?" Those differ whenever pods are cattle:

| | per-pod readiness | workload availability |
|---|---|---|
| terminal pod left behind | **fires forever** | invisible (not a replica) |
| rolling update in progress | fires per old pod | fires only if capacity drops |
| genuine outage (0 replicas up) | fires | fires |
| workload scaled to 0 | silent (no series) | silent (0 unavailable) |

Only the last row is a shared blind spot, and it is addressed separately below.

## Decisions (operator, 2026-08-02)

1. **Normalized `workload` label.** Fold `deployment` / `daemonset` /
   `statefulset` into a common `workload` label via `label_replace`, plus a
   `kind` label. Keeps summaries and runbooks specific, at the cost of more
   PromQL per rule. (Rejected: `sum()` scalar as used by Layer 25 — simpler and
   precedented, but the alert cannot say which workload is degraded. Rejected:
   one rule per workload kind — grows 11 rules to ~25 and double-pages a
   multi-kind outage.)
2. **`for: 15m` on any rule that queries a DaemonSet metric; every other rule
   keeps the `for:` it already had.** A DaemonSet reports replicas unavailable
   during any node drain, so leaving those at their old window would make every
   planned Talos reboot produce an alert burst — trading one noise source for
   another. The 2026-08-02 control-plane roll took ~7 minutes and would not have
   alerted at 15m. (Rejected: PromQL `unless` join against node-Ready —
   Grafana-managed rules have no native inhibition and the hand-rolled version is
   fragile.)

   **Correction (phase 2).** This decision was first written as "5m elsewhere",
   and phase 2 implemented it faithfully — normalising `layer-6-gitops-down`,
   `layer-14-vcluster-down` and `layer-19-rollouts-down` down from **10m to 5m**.
   That was wrong and has been reverted. This change swaps the *metric* a rule
   watches; it is not licence to re-tune sensitivity. Tightening ArgoCD's
   `critical` alert from 10m to 5m raises the chance of firing during a slow
   rollout — precisely the false-positive class this work exists to remove. The
   in-repo precedent agrees: `layer-25-cicd-down`, migrated to workload metrics
   in 2026-05, sits at 10m. The guard is now a per-uid expected-`for:` map
   (`PHASE_2_EXPECTED_FOR`), not a blanket constant, so any future window change
   has to be written down deliberately.
3. **Alert on unexpected scale-to-0**, with the intentionally-scalable set
   excluded. See the implementation note below — this is delivered differently
   from how it was drawn in the decision preview, for a measured reason.
4. **Test Plan = blocking CI tripwires + a post-merge live spot-check**, no
   deliberate failure injection.

### Implementation note on decision 3 — and why it diverges from the preview

The decision was presented with a label-based allowlist
(`kube_deployment_labels{label_frank_scalable="true"}`). **That is not
implementable as drawn.** Measured on the live cluster:

```
query: kube_deployment_labels   ->   0 series
```

kube-state-metrics does not export object labels unless
`--metric-labels-allowlist` is configured, which it is not. Enabling it would
mean a `apps/victoria-metrics/values.yaml` change that **increases KSM
cardinality** — on a cluster where KSM reached 21.6 MiB on 2026-07-27, exceeded
vmagent's 16 MiB `-promscrape.maxScrapeSize`, and had its **entire** response
dropped, silently blinding all 25 `kube_*` rules including the two that watch
for CronJobs failing. Re-approaching that ceiling to encode a three-element list
is a bad trade.

The by-design scale-to-0 set comes from **two independent mechanisms**, both
declared in-repo. Verified live rather than assumed — an earlier draft of this
spec got it wrong in a way that would have paged on day one.

**(a) GPU timeshare.** `gpu-switcher` scales exactly two workloads, listed in its
`WORKLOADS` env var (`apps/gpu-switcher/manifests/deployment.yaml`):

```
WORKLOADS = "ollama:ollama:ollama,comfyui:comfyui:comfyui"
```

Two, not three. (`apps/gpu-switcher/manifests/clusterrole.yaml` is *not* the
source of truth — a ClusterRole has no namespace scoping at all, despite its
leading comment saying "in GPU workload namespaces".)

**(b) Argo Rollouts `workloadRef`.** A Rollout with
`workloadRef.scaleDown: onsuccess` scales its underlying Deployment to **0** the
moment the Rollout goes Healthy, and serves traffic from the Rollout's own
ReplicaSet — the behaviour documented under Argo Rollouts in
`frank-gotchas.md`. Two Rollouts exist:

| Rollout | workloadRef | scaleDown | Deployment replicas |
|---|---|---|---|
| `litellm/litellm` | `Deployment/litellm` | `onsuccess` | **0** (Rollout: 5/5 ready) |
| `sympozium-system/sympozium-apiserver` | `Deployment/sympozium-apiserver` | default (`never`) | non-zero |

So the live `spec_replicas == 0` set is `comfyui` (timeshare) and `litellm`
(Rollout scale-down) — and **`litellm` is a fully healthy service**. A naive
`spec_replicas == 0` rule would have fired on the LiteLLM gateway immediately.

**Delivered as** an explicit exclusion in the rule's PromQL, with a tripwire that
derives the expected exclusion set from both sources — gpu-switcher's `WORKLOADS`
env var and every `workloadRef` target under `apps/**/rollout.yaml` — so adding a
third timeshared workload or a second `scaleDown: onsuccess` Rollout fails CI
instead of paging.

Coverage is not lost: `ollama`/`comfyui` are probed end-to-end by L11
`litellm_chat` and L16 `comfyui_object_info` with `gpu-node-both-down` as the
real pager, and `litellm`'s actual health is the Rollout's, which
`layer-11-inference-down` already probes.

## Design

### Rewrite pattern

Each of the eleven rules keeps its `uid`, `title`, `folder: feature-health`,
`severity`, `github_issue` label, and its A→B→C SSE structure. Only the `A`
expression, the `C` threshold direction, `for:`, and the annotations change.

Before:

```yaml
expr: 'kube_pod_status_ready{namespace="kube-system",pod=~"cilium-.*",condition="true"}'
# ...
conditions:
  - evaluator: { type: lt, params: [1] }
for: 5m
annotations:
  summary: "L3 Cilium: pod {{ $labels.pod }} NotReady"
```

After:

```yaml
expr: |
  label_replace(
    label_replace(
      kube_deployment_status_replicas_unavailable{namespace="kube-system",deployment=~"cilium-.*"},
      "workload", "$1", "deployment", "(.*)"),
    "kind", "deployment", "", "")
  or
  label_replace(
    label_replace(
      kube_daemonset_status_number_unavailable{namespace="kube-system",daemonset=~"cilium-.*"},
      "workload", "$1", "daemonset", "(.*)"),
    "kind", "daemonset", "", "")
# ...
conditions:
  - evaluator: { type: gt, params: [0] }
for: 15m          # namespace contains DaemonSets
annotations:
  summary: "L3 Cilium: {{ $labels.kind }}/{{ $labels.workload }} has {{ $value }} replica(s) unavailable"
  runbook: "kubectl -n kube-system rollout status {{ $labels.kind }}/{{ $labels.workload }}; kubectl -n kube-system describe {{ $labels.kind }}/{{ $labels.workload }}"
```

`kind` is written **lowercase** (`deployment`, not `Deployment`) so it
interpolates straight into a `kubectl` resource path. Grafana's alert templating
is Go `text/template` with a restricted function set; relying on a `lower`
filter would be an avoidable bet, and lowercase is what the runbook needs
anyway.

Note the threshold **inverts**: `lt 1` on a readiness gauge becomes `gt 0` on an
unavailability counter. Getting this backwards yields a rule that fires
constantly or never — it is the highest-risk mechanical error in the change and
gets a dedicated tripwire.

**One rule is deliberately exempt, and it is not a mistake.** The scale-to-0 rule
(below) thresholds at `lt 1`. In PromQL, `metric == 0` is a **filter, not a
comparison**: it drops non-matching series and returns the *original sample
value* for those that match — which here is always `0`. So
`kube_deployment_spec_replicas{...} == 0` paired with `gt 0` produces a rule that
can **never fire**, while reading as perfectly conventional beside its eleven
siblings. Measured live in phase 4 before the rule was written. The guard asserts
the `== 0` / `lt 1` **pairing**, so neither half can be tidied into consistency
on its own. Any documentation that says "every feature-health rule thresholds at
`gt 0`" is wrong.

### StatefulSets have no `_unavailable` metric

kube-state-metrics exports `kube_statefulset_status_replicas` and
`kube_statefulset_status_replicas_ready` but no unavailability counter. Derive
it:

```promql
kube_statefulset_status_replicas{namespace="argocd"}
  - kube_statefulset_status_replicas_ready{namespace="argocd"}
```

Both metrics confirmed present (13 series each).

### Per-rule mapping

Workload kinds counted live per namespace. `for:` is 15m where a DaemonSet
contributes, else 5m.

| Rule | Namespaces | Kinds present | `for:` |
|---|---|---|---|
| `layer-3-networking-down` | kube-system (`cilium-.*`) | Deploy + DS | 15m |
| `layer-4-storage-down` | longhorn-system (`longhorn-manager-.*`) | DS | 15m |
| `layer-5-gpu-down` | gpu-operator, intel-gpu-resource-driver | Deploy + DS | 15m |
| `layer-6-gitops-down` | argocd | Deploy + STS | 5m |
| `layer-10-secrets-down` | infisical, external-secrets | Deploy + STS | 5m |
| `layer-12-agents-down` | sympozium-system | Deploy | 5m |
| `layer-13-auth-down` | authentik | Deploy + STS | 5m |
| `layer-14-vcluster-down` | `vcluster-.*` | STS | 5m |
| `layer-15-workflows-down` | n8n-01, agents, paperclip-system | Deploy + STS | 5m |
| `layer-19-rollouts-down` | argo-rollouts | Deploy | 5m |
| `layer-24-ingress-down` | traefik-system | Deploy | 5m |
| `layer-8-observability-down` | monitoring | Deploy + STS (**DS excluded**) | 5m |

### The twelfth rule — `layer-8-observability-down`

Found during phase 1, not during the brainstorm: a **twelfth** rule also queries
`kube_pod_status_ready`. It is the least-broken of the set and needs different
treatment, so it is called out separately rather than folded into the table
above without comment.

It already mitigates the tombstone problem *inside the query*:

```promql
kube_pod_status_ready{namespace="monitoring",condition="true"}
  unless on(namespace,pod)
kube_pod_status_phase{namespace="monitoring",phase=~"Succeeded|Failed"} == 1
```

That is exactly the approach this spec lists under **Rejected alternatives**, and
it works — which is why layer-8 was *not* among the 72 alerts firing on
2026-08-02. It is nonetheless migrated, for three reasons:

1. It is a second pattern for the same question in the same folder — the way the
   next person gets confused.
2. The `unless` join doubles the series joined on every evaluation.
3. Leaving it means the `strict=True` xfail can never xpass, so phase 3 would
   have to weaken the guard to finish — the precise anti-pattern that marker
   exists to prevent.

**It does not follow the DaemonSet rule.** `monitoring` contains two DaemonSets,
`fluent-bit` and `victoria-metrics-prometheus-node-exporter` — node-level
collectors whose unavailability during a node drain is exactly the noise this
work removes, and whose real coverage is the Layer 1/2 node alerts. The
observability control plane proper is Deployments (`victoria-metrics-grafana`,
`vmagent-*`, `vmsingle-*`, `victoria-metrics-kube-state-metrics`,
`health-bridge`, `blackbox-exporter`, `pushgateway`) plus one StatefulSet
(`victoria-logs-*`).

So layer-8 queries **Deployments and StatefulSets only, and keeps `for: 5m`** —
it is `severity: critical`, and blunting it to 15m would slow detection of the
alerting stack's own failure for no benefit, since excluding DaemonSets already
removes the reboot noise that motivated the 15m window elsewhere.

**Correction (phase 3): the compensating control claimed above did not exist.**
This spec originally justified dropping the two DaemonSets by asserting "their
real coverage is the Layer 1/2 node alerts". That is false. Both
`layer-1-hardware-down` and `layer-2-os-down` key on
`kube_node_status_condition{condition="Ready",status="false"}` — they fire when a
**node** goes NotReady and are completely blind to a collector dying on a healthy
node. The old per-pod layer-8 query *did* cover `fluent-bit` and
`victoria-metrics-prometheus-node-exporter` pods, so excluding them was a genuine
coverage regression introduced by this migration, not a neutral scoping choice.

Rather than ship the gap, a **separate rule** restores the coverage without
blunting layer-8:

```yaml
- uid: layer-8-observability-collectors-down
  title: Layer 8 Observability Collectors Degraded
  folder: feature-health
  expr: |
    label_replace(
      label_replace(
        kube_daemonset_status_number_unavailable{namespace="monitoring"},
        "workload", "$1", "daemonset", "(.*)"),
      "kind", "daemonset", "", "")
  for: 15m
  labels:
    severity: warning
    github_issue: "frank-ops#8"
```

`for: 15m` because these ARE DaemonSets — the node-drain tolerance is exactly
what they need, and it satisfies the folder-wide policy guard without an
exemption. `severity: warning` rather than `critical`: losing `fluent-bit` stops
log shipping and losing `node-exporter` stops node metrics, both real
degradations, but `vmagent`/`vmsingle`/`grafana` are Deployments still covered at
`critical`/5m by layer-8 proper, so the alerting stack itself is not blind.

Its `probe_success` clause for `health-bridge/healthz` is preserved **verbatim**
— that is an end-to-end probe, the sharpest signal in the folder, and entirely
unaffected by this migration. Its `component` label convention
(`pod/<name>` → now `<kind>/<name>`) carries over so the summary still reads
naturally.

The `unless ... kube_pod_status_phase` join is **deleted**, not ported: workload
availability metrics have no tombstones to filter.

The existing pod-name regexes (`cilium-.*`, `longhorn-manager-.*`,
`authentik-(server|worker).*`, …) carry over as workload-name regexes. They get
*simpler*: a pod regex has to tolerate the ReplicaSet-hash suffix, a workload
regex matches the workload name exactly.

`layer-14-vcluster-down`'s `pod=~".*-[0-9]+$"` was a hand-rolled "match
StatefulSet pods only" filter. It disappears entirely — querying
`kube_statefulset_*` selects StatefulSets by construction.

### New rule: unexpected scale-to-0

One new rule, not eleven — the condition is workload-shaped, not layer-shaped.

```yaml
- uid: workload-unexpectedly-scaled-to-zero
  title: Workload Unexpectedly Scaled To Zero
  folder: feature-health
  expr: |
    kube_deployment_spec_replicas{
      namespace!~"ollama|comfyui",
      deployment!~"litellm"
    } == 0
  for: 15m
  labels:
    severity: warning
    github_issue: "frank-ops#8"
  annotations:
    summary: "{{ $labels.namespace }}/{{ $labels.deployment }} is scaled to 0 replicas and is not a known scale-to-0 workload"
    runbook: "kubectl -n {{ $labels.namespace }} get deploy {{ $labels.deployment }} -o yaml; check for an Argo Rollout owning it: kubectl -n {{ $labels.namespace }} get rollouts.argoproj.io"
```

Exclusions, each traceable to a declarative source:

- `namespace!~"ollama|comfyui"` — gpu-switcher's `WORKLOADS` env var.
- `deployment!~"litellm"` — the `scaleDown: onsuccess` Rollout in
  `apps/litellm/manifests/rollout.yaml`. Excluded by *deployment name* rather
  than namespace, so an unrelated Deployment appearing in the `litellm`
  namespace is still covered.

`for: 15m` because a legitimate `Recreate`-strategy rollout passes through 0
replicas — several Frank apps use `Recreate` for RWO PVC reasons
(`storage-secrets-ssa.md`), so a short window would false-positive on ordinary
deploys.

**This collides with phase 3's policy guard**, which asserts the 15m window is
reserved for rules querying a DaemonSet metric. The guard is right to exist —
without it, 15m becomes the place tuning goes to hide. Resolve by widening it to
"15m requires **either** a DaemonSet metric **or** membership in an explicit
allowlist carrying a written reason", and add this rule with the `Recreate`
rationale above. Do not delete the guard, and do not silently exempt the rule:
the allowlist entry is the written decision.

Scoped to Deployments only. StatefulSets and DaemonSets are not scaled to 0 as
an operational pattern on Frank, and including them would mean chasing every
vCluster's lifecycle.

`github_issue: frank-ops#8` — layer 8 is `obs` per `docs/layers.yaml`; this rule
is observability's own, not any single feature layer's.

## Guards (blocking CI)

New `scripts/tests/test_feature_health_workload_metrics.py`:

1. **No `kube_pod_status_ready` anywhere in the `feature-health` folder.** The
   regression tripwire — this is the defect class being removed.
2. **Every migrated rule keeps `folder: feature-health`, its `uid`, its
   `github_issue` label, and its `severity`.** Routing in
   `notification-policy-cm.yaml` keys on `grafana_folder="feature-health"`, so a
   folder typo would silently reroute a layer to Telegram.
3. **Every unavailability-based rule uses `evaluator: gt` with `params: [0]`.**
   Catches the inverted-threshold error described above.
4. **Every rule whose namespace selector can match a DaemonSet has `for: 15m`.**
   Encodes decision 2 so a later edit cannot quietly reintroduce reboot noise.
5. **The scale-to-0 exclusion set is derived from its two declarative sources
   and must match the rule.** The test parses gpu-switcher's `WORKLOADS` env var
   from `apps/gpu-switcher/manifests/deployment.yaml` and every `workloadRef`
   target under `apps/**/rollout.yaml` whose `scaleDown` is `onsuccess`, then
   asserts the rule's exclusion regexes cover exactly that set — no more, no
   less. Adding a third timeshared workload, or flipping
   `sympozium-apiserver`'s Rollout to `scaleDown: onsuccess`, fails CI instead
   of paging at 03:00.
6. **Every `expr` parses as PromQL** and every rule body parses as YAML.

Guard 5 is the one that earns its keep. The first draft of this spec asserted
against `clusterrole.yaml` — which carries no namespaces at all — and listed
`litellm` as GPU-timeshared, which it is not. Both errors were caught by
checking live state, and neither would have been caught by review of the YAML
alone. Encoding the derivation in a test is what stops the next person
(including a future me) from re-deriving it wrong.

## Test Plan

Post-merge, operator-driven. Claims map to the acceptance rows below.

1. **ArgoCD picks up the ConfigMap and Grafana reloads it.**
   `kubectl -n argocd get app grafana-alerting -o custom-columns=SYNC:.status.sync.status,HEALTH:.status.health.status`
   → `Synced/Healthy`. Grafana provisioning files are read **at boot, not
   watched** (`grafana.md`), so this needs
   `kubectl -n monitoring rollout restart deploy/victoria-metrics-grafana`
   and is a manual-operation step, not an automatic consequence of the merge.
2. **No feature-health rule is in `NoData`.** Fetch
   `/api/prometheus/grafana/api/v1/alerts` and assert zero rules in
   `Normal (NoData)` within the `feature-health` folder. A typo'd metric name
   produces NoData, not an error — this is the check that catches it.
3. **Every rewritten rule returns series in VMUI.** For each of the 11
   expressions, a non-empty instant query result. Distinguishes "correctly
   quiet" from "silently broken".
4. **The firing set falls to the 3-alert baseline** — 2 TLS cert canaries
   (`canary: true`) + 1 GPU-timeshare probe (`gpu_timeshare: true`) — with the
   22 remaining tombstones deleted.
5. **A tombstone no longer fires anything.** After the next node reboot (or by
   inspecting any remaining terminal pod), confirm no feature-health rule
   references it.
6. **The scale-to-0 rule stays quiet** while `comfyui` and `litellm` sit at 0
   replicas, proving the exclusion works against live state rather than in
   theory.

## Acceptance rows

| id | claim |
|---|---|
| `feature-health-survives-node-reboot` | A control-plane rolling reboot completes without any feature-health alert firing for a terminated pod. |
| `feature-health-detects-real-outage` | A workload losing all available replicas still raises its layer's feature-health alert. |
| `feature-health-routing-preserved` | Every migrated rule continues to route to Health Bridge only, never Telegram. |
| `feature-health-scale-to-zero-guarded` | An unexpected scale-to-0 alerts, while the GPU-timeshared workloads scaling to 0 do not. |

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|-----------|
| 2026-08-02--obs--feature-health-workload-metrics | `derio-net/frank` | `2026-08-02--obs--feature-health-workload-metrics` | — |

## Rejected alternatives

- **Lower `--terminated-pod-gc-threshold`.** Treats the symptom cluster-wide and
  is a Talos ConfigPatch touching kube-controller-manager on all three control
  planes — higher blast radius than an alert-rule change, and it would still
  leave the rules asking the wrong question. Worth doing separately on its own
  merits.
- **A CronJob that reaps terminal pods.** Same objection, plus a new moving part
  that itself needs a dead-man's switch (see the `pipelinerun-ttl-gc` OOM in
  `frank-gotchas.md` for how that goes).
- **Filter tombstones inside the existing query** (`kube_pod_status_ready unless
  on(pod) kube_pod_status_phase{phase=~"Succeeded|Failed"}`). Keeps the wrong
  question and doubles the series joined per evaluation.
- **Blackbox probes for all eleven layers.** The right answer for user-facing
  capabilities and already used for L11/L16, but writing eleven end-to-end
  probes is a much larger project. Workload availability is the correct
  infrastructure-level signal and a strict improvement on per-pod readiness.
