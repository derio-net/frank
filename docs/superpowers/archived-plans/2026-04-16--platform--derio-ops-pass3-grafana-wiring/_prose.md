# Derio Ops Pass 3 — Grafana Wiring — Implementation Plan

## Phase 0: Framework Prep

### Task 1: Relocate Layer trackers to private `derio-net/frank-ops`

- P0.T1.S1: Create the private repo

- P0.T1.S2: Transfer Layers 1–6 in order

- P0.T1.S3: Burn gap placeholder #7 (Layer 7 dropped)

- P0.T1.S4: Transfer Layers 8–14 and 15–19 (with Layer-number/Issue-number alignment)

- P0.T1.S5: Burn gap placeholders #20, #21, #22, #23

- P0.T1.S6: Transfer Layers 24 and 25

- P0.T1.S7: Verify the Derio Ops board auto-updated

- P0.T1.S8: Update the existing `agent-pod-not-running` rule label

- P0.T1.S9: Update the spec's Layer table

### Task 2: Verify the pipeline end-to-end

- P0.T2.S1: Port-forward and send a synthetic firing alert targeting `frank-ops#18`

- P0.T2.S2: Verify Lifecycle field on frank-ops#18 changed to `degraded`

- P0.T2.S3: Send a resolved alert, verify return to `healthy`

- P0.T2.S4: If either transition failed, stop the plan and root-cause *(skipped — both transitions succeeded on first try)*

### Task 3: Section-organise the alert-rules ConfigMap

- P0.T3.S1: Add section banner comments at the top of each group

- P0.T3.S2: Commit, push, restart Grafana to reload provisioning

### Task 4: Confirm notification policy routes Feature Health folder to the Bridge

- P0.T4.S1: Check folder-name casing matches the route matcher

- P0.T4.S2: If the matcher was wrong, fix and redeploy

## Phase 1: Priority Dogfood — Layer 8 Observability

### Task 1: Write the Layer 8 aggregate rule

- P1.T1.S1: Append the Layer 8 rule under the LAYER TRACKERS banner

- P1.T1.S2: Validate PromQL against live VictoriaMetrics before committing

- P1.T1.S3: Commit, push, restart Grafana

- P1.T1.S4: Verify the rule loads and evaluates to Normal

### Task 2: End-to-end transition test for Layer 8

- P1.T2.S1: Simulate a firing alert via webhook (fast path — don't actually break the monitoring stack)

- P1.T2.S2: Verify frank-ops#8 → `dead` on the board (critical severity maps to dead)

- P1.T2.S3: Resolve and verify return to `healthy`

## Phase 2: Priority — Layer 18 Persistent Agent

### Task 1: Add Layer-18 heartbeat-aggregation rule

- P2.T1.S1: Append the Layer 18 rule

- P2.T1.S2: Commit, push, reload Grafana

- P2.T1.S3: Smoke-test the Layer 18 rule via webhook (same pattern as Phase 1 Task 2, with `github_issue=frank-ops#18` and `severity=warning` → expect `degraded`)

### Task 2: Confirm the Deployed pod rule still co-exists

- P2.T2.S1: Read both rules, confirm label overlap is intentional

## Phase 3: Foundation Layers (1–6)

### Task 1: Layer 1 — Hardware & Nodes (frank-ops#1)

- P3.T1.S1: Append rule — any node NotReady

### Task 2: Layer 2 — OS & Bootstrap (frank-ops#2)

- P3.T2.S1: Append rule — control-plane node NotReady = critical

### Task 3: Layer 3 — Networking / Cilium (frank-ops#3)

- P3.T3.S1: Append rule — Cilium agent down on any node

### Task 4: Layer 4 — Storage / Longhorn (frank-ops#4)

- P3.T4.S1: Append rule — degraded Longhorn volumes

### Task 5: Layer 5 — GPU Compute (frank-ops#5)

- P3.T5.S1: Append rule — any GPU operator pod NotReady

### Task 6: Layer 6 — GitOps / ArgoCD (frank-ops#6)

- P3.T6.S1: Append rule — ArgoCD server unreachable OR apps OutOfSync

### Task 7: Deploy + verify Phase 3 rules

- P3.T7.S1: Commit + push all six new rules together

- P3.T7.S2: Smoke-test each rule via webhook (6 quick calls — use `severity=warning` for 1,3,4,5 and `severity=critical` for 2,6)

- P3.T7.S3: Verify all six Lifecycle transitions, then resolve (loop)

## Phase 4: Core Services (9, 10, 11, 12, 13, 14)

### Task 1: Layer 9 — Backup & DR (frank-ops#9)

- P4.T1.S1: Append rule — last successful Longhorn backup older than 48h

### Task 2: Layer 10 — Secrets (frank-ops#10)

- P4.T2.S1: Append rule — Infisical pod down OR ESO reconciliation failures

### Task 3: Layer 11 — Local Inference (frank-ops#11)

- P4.T3.S1: Append rule — Ollama or LiteLLM down

### Task 4: Layer 12 — Agentic Control Plane / Sympozium (frank-ops#12)

- P4.T4.S1: Append rule — Sympozium pod NotReady

### Task 5: Layer 13 — Unified Auth / Authentik (frank-ops#13)

- P4.T5.S1: Append rule — Authentik server or worker NotReady

### Task 6: Layer 14 — Multi-tenancy / vCluster (frank-ops#14)

- P4.T6.S1: Append rule — any vCluster pod NotReady

### Task 7: Deploy + verify Phase 4 rules

- P4.T7.S1: Commit + push

- P4.T7.S2: Smoke-test the six new rules (same loop pattern as Phase 3 Task 7 with issues 94-99, severities warning/warning/warning/warning/critical/warning)

## Phase 5: User-facing (15, 16, 17)

### Task 1: Layer 15 — Agentic Workflows (frank-ops#15)

- P5.T1.S1: Append rule — n8n or VK pod NotReady

### Task 2: Layer 16 — Media Generation (frank-ops#16) — placeholder

- P5.T2.S1: Insert only a DEFERRED-work comment block (no rule yet — Layer is blocked by design)

- P5.T2.S2: Document the manual-management deviation

### Task 3: Layer 17 — Public Edge / Hop (frank-ops#17)

- P5.T3.S1: Append rule — blog blackbox probe failing OR Headscale peer count abnormal

### Task 4: Deploy + verify Phase 5 rules

- P5.T4.S1: Commit + push

- P5.T4.S2: Smoke-test Layer 15 and 17 (webhook loop with frank-ops#15 warning, frank-ops#17 critical)

## Phase 6: Delivery, Ingress, CI (19, 24, 25)

### Task 1: Layer 19 — Progressive Delivery / Argo Rollouts (frank-ops#19)

- P6.T1.S1: Append rule — argo-rollouts controller pod NotReady

### Task 2: Layer 24 — In-Cluster Ingress / Traefik (frank-ops#24)

- P6.T2.S1: Append rule — Traefik pod NotReady

### Task 3: Layer 25 — CI/CD Platform (frank-ops#25)

- P6.T3.S1: Append rule — Gitea, Tekton controller, or Zot down

### Task 4: Deploy + verify Phase 6 rules

- P6.T4.S1: Commit + push

- P6.T4.S2: Smoke-test (webhook loop frank-ops#19 warning, frank-ops#24 critical, frank-ops#25 warning)

## Phase 7: Alert UX + Finalization

### Task 1: Improve `VK Issue Bridge Failures` alert summary

- P7.T1.S1: Inspect the `willikins_vk_bridge_failure_total` metric's labels

- P7.T1.S2: Rewrite the rule to expose the breakdown

- P7.T1.S3: Audit pre-existing feature-level rules for the same enrichment

- P7.T1.S4: Commit + push + reload Grafana

- P7.T1.S5: Trigger a test firing and inspect the Telegram message + GitHub comment *(skipped — template strings verified via Grafana API read-back; full render requires a real Grafana alert eval, which is out of scope for this audit step)*

### Task 2: Audit the Derio Ops board

- P7.T2.S1: Query every Layer tracker's Lifecycle field and compare to reality

- P7.T2.S2: Document deviations

### Task 3: Flag layers where no probe could be defined

- P7.T3.S1: Create follow-up comments for each deferred item

### Task 4: Update spec status

- P7.T4.S1: Edit spec to reflect Pass 3 completion

## Phase 8: Post-Deploy Checklist

## Deployment Deviations

### 2026-05-14 — `layer-25-cicd-down` alert query rewrite

The Layer 25 alert rule shipped in Phase 6 used `kube_pod_status_ready{namespace=~"gitea|tekton-pipelines|zot",condition="true"}` + `reduce.last` + `threshold lt 1`. This false-positive-fired on 2026-05-13 during the `stoa-gitea-primary-rework-1` execution when ~38 leftover Tekton task pods (Completed/Error post-completion, Ready=False by design) accumulated in `tekton-pipelines`. The reduce-last picked one of them and tripped the threshold; the operator received 24+ hours of Telegram alerts with nothing actually wrong on the cluster.

Query rewritten in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`:

```diff
- expr: 'kube_pod_status_ready{namespace=~"gitea|tekton-pipelines|zot",condition="true"}'
+ expr: 'sum(kube_deployment_status_replicas_unavailable{namespace=~"gitea|tekton-pipelines|zot"})'
- evaluator: { type: lt, params: [1] }
+ evaluator: { type: gt, params: [0] }
```

Deployments are the long-running things; task pods aren't owned by Deployments and are naturally excluded. The complementary hygiene piece (TTL GC for old PipelineRuns) ships in the cicd-platform plan's deployment-deviations entry of the same date.

Gotcha entry added to `.claude/rules/frank-gotchas.md` so the pattern doesn't recur.
