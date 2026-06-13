# Feature-Health Alert Resilience — Design

**Date:** 2026-05-31
**Status:** Spec
**Repo:** frank
**Layer:** obs
**Related:**
- `docs/superpowers/specs/2026-04-08--obs--grafana-alerting-as-code-design.md` (established the declarative, file-provisioned feature-health alerting + Health Bridge work-lifecycle coupling this spec extends)
- `apps/grafana-alerting/manifests/alert-rules-cm.yaml`, `notification-policy-cm.yaml`
- `apps/victoria-metrics/values.yaml`
- Incident: 2026-05-31 ~15:31 UTC — Longhorn instance-manager on mini-2 died, detaching the single `vmsingle` PVC; ~30 feature-health rules error-stormed Telegram as `DatasourceError` with `[no value]` templating.

## Problem

On 2026-05-31 a Longhorn `instance-manager` pod on mini-2 died (transient CNI/gRPC reset, **no** kernel OOM) and was recreated. That detached every Longhorn volume it served for ~2 minutes, including the **single-replica `vmsingle`** PVC. While `vmsingle` was unavailable:

1. **Every feature-health rule's query execution errored.** All ~30 rules are configured `execErrState: Error`, so each transitioned to `Error` state and fired a critical `DatasourceError` alert. Result: a ~30-way Telegram storm. Each alert rendered `[no value]` for templated fields (pod name, etc.) because the query that fills them never returned.
2. **The errors crossed into the GitHub work-lifecycle plane.** Per the 2026-04-08 spec, the notification policy routes `grafana_folder=feature-health` → **Health Bridge Webhook** (`continue: true`), which transitions the rule's `github_issue` work-item to `dead`/`alive`. An `Error`-state alert carries the rule's `severity=critical` label *and* matches the folder route, so a transient datasource blip can **falsely mark GitHub work-items `dead`**.

Two independent root weaknesses:

- **Rule semantics:** rules answer "is monitoring reachable?" individually and incorrectly. A datasource outage is reported as a *feature* outage.
- **Datasource fragility:** `vmsingle` is a single replica on Longhorn, so any instance-manager blip on its node takes the whole metrics-read plane down.

## Goal

Make a transient datasource/storage disruption a **non-event** for feature-health alerting, while keeping the original spec's spirit intact:

- **Declarative, PVC-loss-safe, ArgoCD-self-healing** — every change lives in ConfigMaps (`apps/grafana-alerting/`) or Helm values (`apps/victoria-metrics/`). Zero API provisioning.
- **Preserve the Health Bridge / GitHub work-lifecycle coupling** — the `github_issue` labels, dual-route `continue: true`, and folder-based Health Bridge routing are untouched. The change *protects* the correctness of that automation (no false `dead` transitions), it does not alter it.

Concretely:
- A transient datasource exec-error never pages and never drives a GitHub lifecycle transition.
- A *genuine* VictoriaMetrics outage still pages — exactly **once** (a single deadman watchdog), human-only, with no GitHub side-effects.
- The underlying `vmsingle` SPOF is removed so the blip stops happening in the first place.

## Scope

**In scope:**
- Change `execErrState` semantics on the existing feature-health rules.
- Add one deadman watchdog rule in a new, non-feature folder.
- Notification-policy route for the watchdog folder.
- VictoriaMetrics HA: two `VMSingle` instances + `vmagent` dual-write + `vmauth` read failover.
- Repoint the Grafana VictoriaMetrics datasource URL to `vmauth` (UID preserved).

**Out of scope (explicitly):**
- Reworking individual rule thresholds or `for:` durations beyond the single `for: 0` testing-artifact review. The per-rule tuning from the 2026-04-08 spec is deliberate and stays.
- Migrating to **VMCluster** (vminsert/vmselect/vmstorage). Noted as the future horizontal scale-out path; the two-`VMSingle` HA pair is the proportionate step now.
- `noDataState` changes on feature rules (`OK` is correct and stays).
- Expanding monitoring coverage (more probes/rules) — unrelated follow-up.
- Hop-cluster alerting (Falco/VictoriaLogs path) — separate plane.

## Approach

Three independent pillars, layered so each is useful on its own and they compose:

### Pillar 1 — Rules stop self-reporting datasource errors

In `apps/grafana-alerting/manifests/alert-rules-cm.yaml`, change every feature-health rule's `execErrState: Error` → **`KeepLast`** (~30 occurrences). `noDataState: OK` is unchanged.

- `KeepLast` holds each rule's *last evaluated state* across a transient exec error: a healthy feature stays `Normal`, a genuinely-firing feature stays `Firing`. A datasource blip fabricates neither a critical page nor a Health Bridge transition.
- `for:` durations are **left as the 2026-04-08 spec tuned them** (e.g. `session-manager` 5m, `audit-digest` 1h). The only review item: the single rule at `for: 0m`/`0s`, a likely testing artifact — raise to a sane floor only if confirmed, preserving all deliberately-tuned values.

Rationale: this is the smallest change that kills the storm *and* protects the GitHub-lifecycle plane. It is valuable even before pillars 2–3 land.

### Pillar 2 — One deadman watchdog owns datasource health

Add a new rule group in a **new folder `monitoring-meta`** (sibling group in `alert-rules-cm.yaml`, or a small dedicated CM — plan-time choice, both are file-provisioned identically).

The watchdog is the inverse of pillar 1: it is the **only** rule allowed to fire on missing/errored data.

| Field | Value |
|-------|-------|
| Query (A) | always-present VM health metric, e.g. `vm_app_uptime_seconds{job=~"vmsingle.*"}` (count of live singles). Plan-time: confirm exact series name the operator exposes. |
| Condition | live single count `< 1` (no healthy backend) |
| `noDataState` | **`Alerting`** |
| `execErrState` | **`Alerting`** |
| `for:` | `2m` |
| Severity | `critical` |
| Labels | **no `github_issue`** |
| Folder | `monitoring-meta` (≠ `feature-health`) |

Because it lives outside `feature-health`, it never matches the Health Bridge route → no GitHub work-lifecycle side-effect. Because `execErrState: Alerting`, when the datasource is truly unreachable (vmauth down, both singles down) it is the single rule that pages — converting the former 30-way storm into one human Telegram page. When only one single is down but `vmauth` fails over, the watchdog still gets data and stays `Normal` (HA worked → no page, correct).

### Pillar 3 — VictoriaMetrics HA pair

In `apps/victoria-metrics/`:

- **Two independent `VMSingle` instances** (operator `VMSingle` CRs), with hard `podAntiAffinity` (`requiredDuringSchedulingIgnoredDuringExecution` on `kubernetes.io/hostname`) so they never co-locate on one mini node. Each keeps its own Longhorn PVC. A single node's instance-manager blip can take down at most one.
  - Plan-time: the `victoria-metrics-k8s-stack` chart models one `vmsingle`. Implement the second as a sibling `VMSingle` CR under `apps/victoria-metrics/manifests/` (operator-managed), keeping the chart's `vmsingle` as instance A. Confirm the operator/chart wiring at plan time.
- **`vmagent` dual-write** — add a second `remoteWrite` URL so vmagent writes identical data to both singles. The existing Longhorn-backed persistent queue (1Gi) buffers scrapes across the brief gap, so no write-side data loss.
  - Dedup note: with `vmauth` `first_available` routing, each query is served by exactly one backend, so cross-source merge/dedup is **not** required. (Dedup would only matter under a merging read layer like vmselect/promxy.)
- **`vmauth`** — stateless Deployment, **2 replicas, no PVC**, fronts the read path. One route listing both `VMSingle` backends, `load_balancing_policy: first_available` (sticky to A, fail over to B — avoids recent-data flicker), with retry on connection failure / 5xx. Anti-affinity across nodes.
- **Grafana datasource** — keep UID `P4169E866C3094E38`; repoint its URL (datasource provisioning in the victoria-metrics Helm values / provisioning CM) from the `vmsingle` service to the `vmauth` service DNS. No rule, dashboard, or notification-policy ref changes — they all key off the stable UID.

### Notification policy

In `apps/grafana-alerting/manifests/notification-policy-cm.yaml`, add a route:

- `grafana_folder=monitoring-meta` → `Telegram - Willikins`, `continue: false` (Telegram only — never Health Bridge), with its own `group_by` (e.g. `[alertname]`) and a longer `repeat_interval` than the 3m feature-health default so a sustained VM outage doesn't re-page aggressively.

Existing feature-health routes (`severity=critical`/`warning` → Telegram with `continue: true`; `grafana_folder=feature-health` → Health Bridge) are unchanged.

## Architecture

```
        ┌─────────── scrape ───────────┐
   [ targets ]                         │
        │                              ▼
   [ vmagent ] ──remoteWrite(BOTH)──▶ [ VMSingle-A ]  (mini-X, Longhorn, anti-affinity)
        │  persistent queue (1Gi)      [ VMSingle-B ]  (mini-Y, Longhorn, anti-affinity)
        │                                   ▲
        │                                   │ first_available + retry
        └────────────────────────────▶ [ vmauth ] (2 replicas, stateless)
                                            ▲
                                            │ Grafana datasource UID P4169E866C3094E38 (URL repointed)
                       ┌────────────────────┴───────────────────┐
              [ 30 feature-health rules ]            [ deadman watchdog ]
              execErrState: KeepLast                 folder: monitoring-meta
              noDataState: OK                         execErrState/noDataState: Alerting
              folder: feature-health                  Telegram only (no github_issue)
                  │ severity → Telegram (continue)         │
                  │ folder   → Health Bridge → GitHub       └── one page on real VM outage
                  └── feature state drives work-lifecycle
```

## File Layout (changes)

```
apps/grafana-alerting/manifests/
  alert-rules-cm.yaml          # MODIFIED: execErrState Error→KeepLast (×30); + watchdog rule group (monitoring-meta folder)
  notification-policy-cm.yaml  # MODIFIED: add monitoring-meta → Telegram-only route

apps/victoria-metrics/
  values.yaml                  # MODIFIED: vmagent 2nd remoteWrite; datasource URL → vmauth; (vmauth config if chart-managed)
  manifests/                   # NEW (if needed): second VMSingle CR + vmauth Deployment/Service/Config + anti-affinity
```

(Whether the second `VMSingle` and `vmauth` are expressed through the `victoria-metrics-k8s-stack` chart values or as sibling operator CRs in `apps/victoria-metrics/manifests/` is a plan-time decision based on chart capability; both remain file-provisioned + ArgoCD-managed.)

## Verification

End-to-end, in order:

- [ ] **Pillar 1:** Temporarily make a feature-health datasource query error (e.g. point one rule at vmauth then scale vmauth to 0 briefly, or use a deliberately bad query in a scratch commit). Confirm the rule transitions to `KeepLast` (state held), **no** Telegram page, **no** Health Bridge `dead` transition on its `github_issue`. Restore.
- [ ] **Pillar 2:** Scale **both** VMSingle replicas (or vmauth) to 0. Confirm: exactly **one** Telegram page from the watchdog within ~2m; feature-health rules stay silent. Confirm the watchdog carries no `github_issue` and triggers no Health Bridge call. Restore → watchdog auto-resolves.
- [ ] **Pillar 3 — failover:** With both singles healthy, `kubectl delete pod` the VMSingle that `vmauth` is currently sticky to. Confirm Grafana queries keep returning data (vmauth fails over to B) with no `DatasourceError` and no watchdog page. Confirm vmagent backfilled the deleted single on return (no permanent gap).
- [ ] **Pillar 3 — anti-affinity:** Confirm the two VMSingle pods are scheduled on different nodes; confirm a single node drain takes down at most one.
- [ ] **Datasource UID stability:** Confirm Grafana datasource UID is still `P4169E866C3094E38` after repoint; all rules/dashboards render unchanged.
- [ ] **Declarative/self-heal:** Restart the Grafana pod and delete one VMSingle PVC; confirm ArgoCD + operator reconcile everything back with no manual API calls (PVC-loss-as-non-event, per original spec).

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| `KeepLast` masks a *genuine* sustained datasource outage on feature rules | That is exactly what the deadman watchdog (pillar 2) covers — one authoritative page. The two pillars are co-dependent by design. |
| Watchdog accidentally lands in `feature-health` folder → drives Health Bridge | Explicit folder `monitoring-meta` + `continue: false` route; verification step asserts no Health Bridge call and no `github_issue`. |
| Operator/chart does not cleanly express a 2nd VMSingle | Plan-time spike: stand up the 2nd VMSingle as a sibling operator CR first, confirm vmagent dual-write, before touching the read path. |
| `vmauth` becomes a new SPOF | Stateless, 2 replicas, anti-affinity, no PVC — failure domain is far smaller than a Longhorn-backed single. |
| Recent-data flicker if vmauth round-robins between slightly-lagged singles | `load_balancing_policy: first_available` (sticky), not round-robin. |
| Datasource URL repoint breaks rules/dashboards | UID is preserved; only the URL changes. Verification asserts UID stability. |
| Doubled metrics storage cost | Accepted — 2×20Gi Longhorn at 1-month retention; the learning/HA value is the point (Frank ethos). VMCluster deferred as the scale-out path if retention grows. |

## Decisions Captured

- **Goal:** full hardening — all three pillars, not just the rule-config quick fix.
- **Pillar 1:** `execErrState: Error → KeepLast` across feature rules; `noDataState: OK` unchanged; `for:` left as tuned except the lone `for: 0` testing artifact.
- **Pillar 2:** single deadman watchdog, folder `monitoring-meta`, `execErrState`/`noDataState: Alerting`, `for: 2m`, Telegram-only, no `github_issue` — fenced out of the Health Bridge / GitHub work-lifecycle plane.
- **Pillar 3:** **two-`VMSingle` HA pair** (not VMCluster), anti-affinity, vmagent dual-write, **`vmauth`** read failover with `first_available`.
- **Datasource:** preserve UID `P4169E866C3094E38`, repoint URL to vmauth.
- **Spirit preserved:** fully declarative ConfigMaps/Helm values, PVC-loss-safe, Health Bridge coupling and `github_issue`/`continue: true` conventions untouched — the change *protects* lifecycle correctness rather than altering it.

## Open Questions

None blocking. Plan-time confirmations: exact VM health-metric series name for the watchdog query; whether the 2nd VMSingle + vmauth are chart-values or sibling CRs.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-05-31--obs--feature-health-alert-resilience | `derio-net/frank` | `2026-05-31--obs--feature-health-alert-resilience` | — |
