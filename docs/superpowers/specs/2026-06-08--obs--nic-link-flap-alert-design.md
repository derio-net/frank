# NIC Link-Flap Alert — Design

**Date:** 2026-06-08
**Status:** Spec
**Repo:** frank
**Layer:** obs
**Related:**
- `apps/grafana-alerting/manifests/alert-rules-cm.yaml` (Layer-1 hardware rule family this extends), `notification-policy-cm.yaml`
- `docs/runbooks/frank-gotchas/networking.md` (full incident write-up + monitoring-gap analysis)
- `agents/rules/frank-gotchas.md` → Networking section (one-liner index)
- Incident: 2026-06-08 — gpu-1's `enp3s0` (Realtek `r8169`) link-flapped after an overnight power outage; each link-down stripped the node IP off Cilium's direct-routing device, collapsing the gpu-1 datapath and dropping every SSH-via-LB session on the node at once. **No alert fired** for ~8h.

## Problem

A flapping physical NIC is invisible to Frank's current alerting. On 2026-06-08, gpu-1's `enp3s0` flapped from ~03:57 UTC (intermittent) into a continuous storm at ~12:01 UTC. node-exporter captured it perfectly — `node_network_carrier_changes_total{device="enp3s0"}` reached **76 on gpu-1, 0 on every other node** — yet zero alerts paged. The operator discovered it only when two SSH sessions dropped.

Two structural reasons none of the existing rules caught it:

1. **"Alive but flapping" ≠ "down".** Every host/network rule is a binary down-state threshold with `for: 5m`:
   - `Layer 1 Hardware Node NotReady` (`kube_node_status_condition{condition="Ready",status="false"}`, `for: 5m`) — the node never sustained NotReady; kubelet posted `Ready` during each up-window, so the 40s node-monitor grace never elapsed continuously.
   - `Layer 3 Cilium Agent Down` (`kube_pod_status_ready{pod=~"cilium-.*"}`, `for: 5m`) — the Cilium pod stayed `Running`/`Ready` the whole time; it was *alive and retrying* its datapath init, not down. Pod-readiness ≠ datapath-healthy.
   - `Endpoint Down` (`probe_success{feature_health}`, `for: 5m`) — intermittent up-windows let blackbox probes succeed within any 5m window.

   A fast flap is up-on-average and never sustains a 5-minute down-state, so binary `== false` + `for: 5m` rules are blind to it **by construction**. The correct signal is a **rate of change**, not a state threshold.

2. **Scrape aliasing.** `changes(node_network_up{device="enp3s0"}[12h])` registered only **1** — the ~30s scrape sampled "up" most times and missed the sub-10s flaps. The kernel **counter** `node_network_carrier_changes_total` recorded all 76. Alerting must key off the counter's rate, never the up/down gauge.

## Goal

Add a single declarative alert rule that pages Telegram when a node's physical NIC is flapping, with enough lead time to catch the sustained/storming phase well before connectivity is severed — without false-paging on reboots, cable replugs, or routine maintenance.

- **Declarative, ArgoCD-self-healing** — lives entirely in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`, file-provisioned exactly like the existing Layer-1 hardware rules. Zero API provisioning.
- **Consistent with the Layer-1 hardware family** — `feature-health` folder, `severity: warning`, `github_issue: "frank-ops#1"`, so it routes to Telegram (via the `severity=warning` route) and into the Health Bridge work-lifecycle (via the `feature-health` folder route) exactly like its siblings.
- **False-positive-safe** — robust to counter resets (a node-exporter restart on reboot zeroes the counter; `increase()` accounts for resets), so reboots (~1 change) and cable replugs (≤2 changes) never trip it.

## Scope

**In scope:**
- One new rule group + rule in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`.
- The incident + monitoring-gap documentation the rule's `runbook` annotation references — full prose in `docs/runbooks/frank-gotchas/networking.md` and a one-liner + gpu-1 cross-ref in `agents/rules/frank-gotchas.md` (drafted during the 2026-06-08 incident response; carried here so the annotation resolves and the rule ships self-contained, per the repo's Layer Fix/Extension workflow step 5).

**Out of scope (explicitly):**
- `execErrState`/`noDataState` semantics changes (the `Error → KeepLast` rework proposed in `2026-05-31--obs--feature-health-alert-resilience-design.md` is a separate, not-yet-deployed spec — this rule matches the **prevailing** file convention `execErrState: Error` / `noDataState: OK`).
- Any change to the notification policy, contact points, or routing — the existing `severity=warning` + `feature-health` routes already deliver this rule correctly; no new route needed.
- New VictoriaMetrics HA, datasource changes, or additional probes.
- The physical/driver remediation for the gpu-1 NIC itself (cable reseat done; `pcie_aspm=off` durable fix tracked in the networking runbook) — that is hardware ops, not alerting.
- Hop-cluster alerting (separate Falco/VictoriaLogs plane).

## Approach

Add one rule group `layer-1-nic-link-flap` to `alert-rules-cm.yaml`, mirroring the existing `layer-1-hardware-down` / `layer-1-node-memory-headroom` SSE A→B→C shape (query → reduce → threshold), against the same VictoriaMetrics datasource UID `P4169E866C3094E38`.

| Field | Value |
|-------|-------|
| Group / uid / title | `layer-1-nic-link-flap` / `Layer 1 Hardware NIC Link Flapping` |
| Query (A) | `increase(node_network_carrier_changes_total{device=~"en.*\|eth.*"}[30m])` — physical NICs only (`enp*`/`eth*`/`ens*`/`eno*`); excludes `cilium_*`, `lxc*`, `veth*`, `lo`. `instant: true`, `relativeTimeRange.from: 1800` (≥ the 30m rate window). |
| B | `reduce`, `last`, `dropNN` (matches family) |
| C | `threshold`, `gt`, params `[6]` |
| Condition | `C` |
| `for:` | `0m` — the 30m window itself provides the smoothing; fire as soon as ≥6 carrier changes accumulate in 30m |
| `noDataState` | `OK` (a scrape gap / node-down is covered by the NotReady rule — this rule must not page on missing data) |
| `execErrState` | `Error` (matches the prevailing file convention) |
| Severity | `warning` |
| Labels | `github_issue: "frank-ops#1"` (Layer-1 hardware work item) |
| Folder | `feature-health` (same as the L1 family → Telegram + Health Bridge routing) |
| `interval` | `1m` (group eval cadence, matches family) |

**Annotation templating note:** `node_network_carrier_changes_total` carries an **`instance`** label (`<ip>:9100`), **not** `node` (unlike `kube_node_status_condition`). Annotations therefore template `{{ $labels.instance }}` and `{{ $labels.device }}`, mirroring the memory-headroom rule's use of `{{ $labels.instance }}`.

- `summary`: `"L1 Hardware: NIC {{ $labels.device }} on {{ $labels.instance }} is link-flapping (>6 carrier changes/30m) — Cilium datapath risk (see 2026-06-08 enp3s0 incident)"`
- `runbook`: `"talosctl -n <node-ip> dmesg | grep 'Link is'; reseat cable / switch-end port; durable fix pcie_aspm=off — docs/runbooks/frank-gotchas/networking.md"`

**Threshold rationale (`>6 / 30m`):** chosen against the incident data (76 changes/12h; sparse early phase, dense storm). A 30m window catches *sustained* intermittent flapping hours before a full storm while staying reboot/replug-safe:
- Reboot → counter resets to 0, ~1 boot link-up → no fire.
- Cable replug → ≤2 changes → no fire.
- Sustained flapping (~6+ changes/30m) → fires.
- Storm (dozens/30m) → fires hard.

Honest limit: a *truly* sparse fault (one flap every ~10 min) stays under the threshold and won't page — no threshold can catch that without also flagging routine maintenance. The realistic, high-value win is catching the fault once it becomes sustained, which is strictly better than today's zero coverage.

## Architecture

```
 node-exporter (per node)
   node_network_carrier_changes_total{device=~"en.*|eth.*"}   ← kernel counter, reset-safe
        │  scraped by vmagent → vmsingle
        ▼
 Grafana provisioned rule  layer-1-nic-link-flap  (folder: feature-health)
   A: increase(...[30m])  →  B: reduce last  →  C: threshold gt 6   (for: 0m)
        │ severity=warning ───────────────▶ Telegram - Willikins   (continue: true)
        └ grafana_folder=feature-health ──▶ Health Bridge Webhook → frank-ops#1 lifecycle
```

No new datasource, route, or contact point — the rule plugs into the existing Layer-1 hardware delivery path.

## File Layout (changes)

```
apps/grafana-alerting/manifests/
  alert-rules-cm.yaml   # MODIFIED: + new rule group `layer-1-nic-link-flap` (one rule)
```

## Verification

In the isolation workspace (no cluster mutation):

- [ ] **YAML validity** — the ConfigMap parses; the new rule group is well-formed YAML and structurally identical (refIds, datasourceUid, model shapes) to `layer-1-hardware-down`.
- [ ] **PromQL sanity** — `increase(node_network_carrier_changes_total{device=~"en.*|eth.*"}[30m])` is a valid query against the live VM datasource and returns one series per physical NIC per node (confirmed: the metric exists, gpu-1 enp3s0 carried 76 over the incident).
- [ ] **Threshold arithmetic** — confirm against captured incident data that the storm window exceeds 6/30m (would have fired) and that an isolated reboot/replug stays ≤2 (would not).
- [ ] **Label templating** — confirm the metric exposes `instance` + `device` (not `node`), matching the annotation templates.

## Test Plan

*(post-merge — operator-driven; the rule must be deployed and Grafana restarted to load file-provisioned rules)*

1. **Deploy:** merge → ArgoCD syncs `grafana-alerting` → **restart the Grafana pod** (file-provisioned alert rules are read at boot, not watched): `kubectl rollout restart deploy/<grafana> -n monitoring`.
2. **Confirm the rule loaded:** in Grafana → Alerting → Alert rules, `Layer 1 Hardware NIC Link Flapping` is present under `feature-health`, state `Normal`.
3. **Synthetic metric import (non-disruptive, deterministic):** import a rising synthetic counter into `vmsingle` that breaches the threshold, spanning the eval window — e.g. via `POST <vmsingle>:8428/api/v1/import/prometheus` with a series `node_network_carrier_changes_total{device="en-test",instance="synthetic:9100",job="node-exporter"}` rising from a low value at `now-30m` to `+>6` at `now` (constructed so `increase[30m] > 6`).
4. **Confirm paging:** the rule transitions to `Firing` within one eval interval and a **Telegram message arrives** at `Telegram - Willikins` with the `device`/`instance` templated correctly. (The Health Bridge route also fires per `frank-ops#1`; confirm it does not create a spurious *new* tracker beyond the expected Layer-1 lifecycle.)
5. **Clean up:** delete the synthetic series (or let it age out of the 30m window so the rule auto-resolves); confirm the rule returns to `Normal` and a resolved notification is sent.

Verifies the full chain end-to-end — rule evaluation → notification policy routing → Telegram delivery — exactly what was missing on 2026-06-08.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Threshold too high → misses a genuinely sparse fault | Acknowledged in Approach; `>6/30m` is the proportionate balance vs. reboot/maintenance false-positives. Lower later if a sparse fault is observed slipping through. |
| `device=~"en.*\|eth.*"` misses a node whose NIC has a different name | All current Frank nodes use `enp*`/`eth*` (Talos predictable names). The regex covers `en*`/`eth*`; revisit if a node with `ens*`/`eno*`/other lands — those also match `en.*`. |
| Maintenance reboot false-paging | `increase()` is counter-reset-aware; a reboot yields ~1 change → below threshold. Verified by the threshold-arithmetic check. |
| Rule errors on a datasource blip (`execErrState: Error`) | Matches the prevailing file convention; the separate resilience spec owns any `KeepLast` rework. Out of scope here. |
| Annotation uses wrong label (`node` vs `instance`) | Confirmed the metric carries `instance`, not `node`; templates use `{{ $labels.instance }}`. Verification asserts label set. |

## Decisions Captured

- **Threshold:** `increase(node_network_carrier_changes_total{device=~"en.*|eth.*"}[30m]) > 6`, `for: 0m` — sustained-flap detection with reboot/replug safety and the best lead time for the "8h blind" pain (operator-chosen over a storm-only `[10m] > 5` and a dual warn/crit rule).
- **Scope:** all physical NICs, all nodes (the gap is generic).
- **Severity/routing:** `warning` + `github_issue: "frank-ops#1"`, folder `feature-health` — reuses the Layer-1 hardware delivery path (Telegram + Health Bridge); no notification-policy change.
- **execErrState/noDataState:** `Error` / `OK` — match the prevailing file convention; the `KeepLast` rework stays in its own spec.
- **Test Plan:** post-merge synthetic metric import into vmsingle to prove the Telegram chain, non-disruptively (operator-chosen over a real controlled flap or a temporary threshold drop).

## Open Questions

None blocking.

## Deployment Deviations

- **2026-06-08 — Telegram 400 (silent non-delivery), fixed post-merge.** The post-merge Test Plan caught the rule firing correctly on a *real* gpu-1 `enp3s0` flap (the reseat from the original incident had not fully held), but **every Telegram page failed with `400 Bad Request`**. Root cause: Grafana's Telegram contact point sends HTML `parse_mode`, and the annotations carried `talosctl -n <node-ip> dmesg` and `(>6 …)` — Telegram's HTML parser rejected `<node-ip>` as an invalid tag. The Health Bridge webhook (raw JSON) delivered fine, so `frank-ops#1` lifecycle worked; only Telegram was affected, and `grafana_alerting_notification_errors_total` did not surface it. Fix: strip `<`/`>`/`&` from the annotation values (`<node-ip>`→`NODE_IP`, `>6`→`6+`); gotcha recorded in `agents/rules/frank-gotchas.md` (Grafana) + `docs/runbooks/frank-gotchas/grafana.md`. This is the textbook payoff of the "not Deployed until the workflow is observed end-to-end" rule — static validation passed; only a live firing exposed it. (gpu-1 NIC durable fix — `pcie_aspm=off` Talos patch — tracked separately as hardware ops.)

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-06-08--obs--nic-link-flap-alert | `derio-net/frank` | `2026-06-08--obs--nic-link-flap-alert` | — |
