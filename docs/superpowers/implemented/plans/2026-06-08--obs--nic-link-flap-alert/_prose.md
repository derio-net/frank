# NIC Link-Flap Alert — Plan

Close the alerting blind spot exposed by the 2026-06-08 gpu-1 `enp3s0`
link-flap incident: a flapping physical NIC stripped the node IP off Cilium's
direct-routing device, collapsed the gpu-1 datapath, and dropped every
SSH-via-LB session on the node — and **no alert fired for ~8h** because every
host/network rule is a binary down-state threshold with `for: 5m`, blind to an
"alive but flapping" link by construction.

Design: `docs/superpowers/specs/2026-06-08--obs--nic-link-flap-alert-design.md`.
Full incident + monitoring-gap analysis:
`docs/runbooks/frank-gotchas/networking.md`.

## Phase 1 — Add NIC link-flap alert rule + validate (agentic, TDD)

One new rule group `layer-1-nic-link-flap` in
`apps/grafana-alerting/manifests/alert-rules-cm.yaml`, mirroring the existing
`layer-1-hardware-down` / `layer-1-node-memory-headroom` SSE A→B→C shape
against VM datasource `P4169E866C3094E38`.

- **Query:** `increase(node_network_carrier_changes_total{device=~"en.*|eth.*"}[30m])`
  — kernel carrier-change counter, physical NICs only, all nodes.
- **Threshold:** `> 6`, `for: 0m`. The 30m window provides smoothing and the
  lead time to catch sustained flapping before a full storm; counter-reset-aware
  so reboots (~1 change) and replugs (≤2) never false-page.
- **Routing (no policy change):** `severity: warning` → Telegram, folder
  `feature-health` → Health Bridge, `github_issue: "frank-ops#1"` — identical
  to the other Layer-1 hardware rules.
- **Annotation labels:** the metric carries `instance` + `device` (NOT `node`),
  so templates use `{{ $labels.instance }}` / `{{ $labels.device }}`.

TDD shape for a config change: assert the rule is absent + the file parses
(RED) → add the group → assert YAML validity, presence, structural parity with
the sibling, and threshold/label correctness (GREEN).

## Phase 2 — Post-merge deploy + synthetic-import Telegram test (manual)

Back-loaded manual phase (operator-driven; needs the live cluster + real
Telegram + a Grafana pod restart to load the file-provisioned rule). After
merge: sync + restart Grafana, confirm the rule loads, then import a rising
synthetic carrier-changes counter into vmsingle that breaches `>6/30m` and
confirm a Telegram message is delivered with the labels templated correctly —
proving the full chain (rule eval → routing → Telegram) that was missing on
2026-06-08. Clean up the synthetic series and confirm auto-resolve.

This phase ships **unimplemented** in the PR, marked for the operator to
execute and record evidence (`fr plan edit --complete-phase 2 --note`).
