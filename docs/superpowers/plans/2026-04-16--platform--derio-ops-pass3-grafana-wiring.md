# Derio Ops Pass 3 — Grafana Wiring — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-16--platform--derio-ops-layers-restoration-design.md`
**Status:** Not Started

> **Execution: subagent-driven-development throughout.** No VK dispatch.
>
> Rationale: vk-dispatch's dependency model is strictly sequential (Phase N → blocked by Phase N-1), which would serialize Phases 3–6 even though they're independent. subagent-driven-development can genuinely parallelise those four by spawning concurrent subagents. Ordering the controller should enforce:
> - **Phase 0 first** (sequential — repo creation → transfers → verify → deploy).
> - **Phases 1 and 2** next, sequentially or in parallel (both depend only on Phase 0; eyeballing the first one or two is useful as a smoke test of the multi-instance-rule pattern).
> - **Phases 3, 4, 5, 6 in parallel** — four concurrent subagents. Each writes independent Layer rules, commits to its own subfolder of `apps/grafana-alerting/manifests/alert-rules-cm.yaml`… wait — they ALL edit the same ConfigMap. Serialize the commits (not the rule-writing) by having each subagent return its rule YAML as a diff and the controller applies them in sequence, or serialize via a shared mutex on the file. Either works; the per-layer research and YAML authoring is what parallelises.
> - **Phase 7 and Phase 8** last, sequentially, with the operator in the loop.

**Goal:** Wire each of the 20 Layer trackers on the Derio Ops board to a Grafana alert rule whose `github_issue` label matches the tracker Issue. The Health Bridge (already deployed) then drives the Layer's Lifecycle field automatically — `firing+warning → degraded`, `firing+critical → dead`, `resolved → healthy`.

**Architecture:** One canonical alert rule per Layer, living as code in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`. Each rule uses the Grafana 12.x 3-step SSE format (A: data-source query → B: reduce → C: threshold) and carries `labels.github_issue: "frank-ops#<LAYER>"` plus `labels.severity`. Multi-component Layers use aggregation expressions to emit a single "any-component-down" signal, which prevents Lifecycle-field flapping when several sub-probes fire in quick succession.

**Tracker repo:** Layer trackers are relocated from the public `derio-net/frank` repo to a new **private** `derio-net/frank-ops` repo in Phase 0. The Derio Ops project v2 board is already org-private, but its Issues were backing on a public repo — so every Bridge comment and bug-Issue leaked cluster-state signal. Moving to a private repo closes that hole. Issue numbering is reset to match Layer numbering 1:1 (Layer 13 → `frank-ops#13`), with closed placeholder Issues filling the dropped slots (Layers 7, 20, 21, 22, 23 per the spec's "gaps preserved" editorial rule).

**Tech Stack:** Grafana 12.x managed alerting (file-provisioned), VictoriaMetrics data source (uid `P4169E866C3094E38`), kube-state-metrics, Blackbox Exporter, Pushgateway heartbeats, health-bridge (`ghcr.io/derio-net/health-bridge:v0.2.0`), GitHub Project v2 GraphQL.

---

## File Structure

```
apps/grafana-alerting/manifests/
  alert-rules-cm.yaml          # EXTENDED — new rule groups per Layer, organised into sections

docs/superpowers/plans/
  2026-04-16--platform--derio-ops-pass3-grafana-wiring.md   # THIS FILE

docs/superpowers/specs/
  2026-04-16--platform--derio-ops-layers-restoration-design.md   # Update status at the end
```

No new apps, no new CRDs. All 20 rules land in the existing ConfigMap.

---

## Reference — Per-Layer Rule Pattern

Every Layer rule follows this shape. Substitute `<LAYER>`, `<ISSUE>`, `<EXPR>`, `<THRESH>`, `<SEVERITY>`, `<SUMMARY>`:

```yaml
      - orgId: 1
        name: layer-<LAYER>-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-<LAYER>-down
            title: Layer <LAYER> <NAME> Down
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: '<EXPR>'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: <OP>, params: [<THRESH>] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: <SEVERITY>
              github_issue: "frank-ops#<LAYER>"
            annotations:
              summary: "<SUMMARY>"
```

**Severity policy for Layer rules:**
- `severity: warning` by default (degraded is the usual truthful state of a partially-failing Layer).
- `severity: critical` only where full Layer loss is operationally catastrophic (Layer 2 OS, Layer 6 GitOps, Layer 24 Ingress, Layer 8 Observability — losing those means you lose the feedback loop itself).

**Multi-instance pattern (required for all Layer rules).** Don't aggregate to a scalar — Telegram and the Bridge comment become useless ("Layer 3 is degraded" tells the operator nothing actionable). Instead: let `refId A` return a labelled series (one sample per pod/node/volume/etc.), `refId B` reduce preserves labels, `refId C` threshold fires one alert instance per failing resource. The annotation template references `{{ $labels.<dim> }}` so the notification names exactly what's broken. Example skeleton:
- `expr: kube_pod_status_ready{namespace="foo",condition="true"}` (preserves `pod` label)
- threshold: `lt 1` (fires on value 0, i.e. NotReady)
- annotation: `"LN Foo: pod {{ $labels.pod }} NotReady"`

The Bridge's `lastState` dedup collapses multiple simultaneous alerts into a single Lifecycle transition + one comment (the first one wins). Telegram groups them per `group_interval` into a single message listing every failing instance. Best of both worlds.

Where a rule aggregates disparate signals (e.g. Layer 8 covers both pod readiness AND probe health), use `label_replace` to inject a normalised `component` label so the annotation template has a single variable to reference. See Layer 8 for the canonical example.

**Label format reminder:** the Bridge's `ParseIssueRef` splits on `#` and treats the left half as the bare repo name. Use `frank-ops#<LAYER>`, not `derio-net/frank-ops#<LAYER>` — the long form breaks the GraphQL `findProjectItem` query. Post-Phase-0, `frank-ops#<LAYER>` == `Layer <LAYER>` for any non-gap Layer number.

---

## Phase 0: Framework Prep [agentic]

### Dependencies

None. This phase unblocks all subsequent phases.

### Task 1: Relocate Layer trackers to private `derio-net/frank-ops`

Pass 1 put the 20 Layer tracker Issues in `derio-net/frank` (public), which means Bridge comments + auto-created bug Issues leak cluster-state signal to the public web. Fix by moving the trackers to a new private repo, with Issue numbers aligned 1:1 to Layer numbers (placeholders in the gap slots per the spec's editorial rule).

**Files:**
- Modify: `apps/grafana-alerting/manifests/alert-rules-cm.yaml` (existing `agent-pod-not-running` rule label update)
- Modify: `docs/superpowers/specs/2026-04-16--platform--derio-ops-layers-restoration-design.md` (Issue column in the Layer table)

**Source→destination mapping** (this is the canonical reference — subsequent phases use the right column):

| Layer | Source (public, frank) | Destination (private, frank-ops) |
|-------|-----------------------:|-------------------------:|
| 1  | `frank` issue 87  | `frank-ops` issue 1  |
| 2  | `frank` issue 88  | `frank-ops` issue 2  |
| 3  | `frank` issue 89  | `frank-ops` issue 3  |
| 4  | `frank` issue 90  | `frank-ops` issue 4  |
| 5  | `frank` issue 91  | `frank-ops` issue 5  |
| 6  | `frank` issue 92  | `frank-ops` issue 6  |
| *(7 dropped)* | — | `frank-ops` issue 7 (closed placeholder) |
| 8  | `frank` issue 93  | `frank-ops` issue 8  |
| 9  | `frank` issue 94  | `frank-ops` issue 9  |
| 10 | `frank` issue 95  | `frank-ops` issue 10 |
| 11 | `frank` issue 96  | `frank-ops` issue 11 |
| 12 | `frank` issue 97  | `frank-ops` issue 12 |
| 13 | `frank` issue 98  | `frank-ops` issue 13 |
| 14 | `frank` issue 99  | `frank-ops` issue 14 |
| 15 | `frank` issue 11  | `frank-ops` issue 15 |
| 16 | `frank` issue 10  | `frank-ops` issue 16 |
| 17 | `frank` issue 100 | `frank-ops` issue 17 |
| 18 | `frank` issue 8   | `frank-ops` issue 18 |
| 19 | `frank` issue 101 | `frank-ops` issue 19 |
| *(20 absorbed)* | — | `frank-ops` issue 20 (closed placeholder) |
| *(21 merged into 18)* | — | `frank-ops` issue 21 (closed placeholder) |
| *(22 absorbed into 8)* | — | `frank-ops` issue 22 (closed placeholder) |
| *(23 absorbed into 8)* | — | `frank-ops` issue 23 (closed placeholder) |
| 24 | `frank` issue 102 | `frank-ops` issue 24 |
| 25 | `frank` issue 103 | `frank-ops` issue 25 |

- [x] **Step 1: Create the private repo**

```bash
gh repo create derio-net/frank-ops \
  --private \
  --description "Operational state of the Frank cluster — Layer trackers for the Derio Ops board. Code lives in derio-net/frank." \
  --disable-issues=false
```

Expected: `✓ Created repository derio-net/frank-ops on GitHub`.

- [x] **Step 1b: Clone `frank-ops` under `~/repos` so future sessions can work on it locally**

```bash
cd ~/repos
gh repo clone derio-net/frank-ops
ls -d ~/repos/frank-ops
```

Expected: `/home/claude/repos/frank-ops` exists. This sits alongside `~/repos/frank`, `~/repos/willikins`, etc. — same convention as the other derio-net repos. Future sessions that need to edit tracker Issue bodies or inspect board history can `cd ~/repos/frank-ops` directly instead of going through `gh`.

- [x] **Step 2: Transfer Layers 1–6 in order**

Transfers go sequentially because Issue numbers in the new repo increment in transfer order. Verify each transfer assigned the expected number before moving on.

```bash
SRC=derio-net/frank
DST=derio-net/frank-ops

# Layer 1 → frank-ops#1
gh issue transfer 87 --repo "$SRC" "$DST"
# Layer 2 → frank-ops#2
gh issue transfer 88 --repo "$SRC" "$DST"
# Layer 3 → frank-ops#3
gh issue transfer 89 --repo "$SRC" "$DST"
# Layer 4 → frank-ops#4
gh issue transfer 90 --repo "$SRC" "$DST"
# Layer 5 → frank-ops#5
gh issue transfer 91 --repo "$SRC" "$DST"
# Layer 6 → frank-ops#6
gh issue transfer 92 --repo "$SRC" "$DST"

# Sanity: numbers should be 1-6
gh issue list --repo "$DST" --state all --json number,title --jq '.[] | "\(.number)\t\(.title)"' | sort -n
```

Expected: six Issues numbered 1–6, titles `Layer 1 — Hardware` … `Layer 6 — GitOps`.

- [x] **Step 3: Burn gap placeholder #7 (Layer 7 dropped)**

```bash
NUM=$(gh issue create --repo "$DST" \
  --title "[gap] Layer 7 — Fun Stuff (dropped, not a board tracker)" \
  --body "This Issue exists solely to preserve the Layer-number → Issue-number 1:1 mapping. Layer 7 (OpenRGB / fun stuff) was dropped from the Derio Ops board per the editorial decision in the spec. See docs/superpowers/specs/2026-04-16--platform--derio-ops-layers-restoration-design.md." \
  --label gap 2>/dev/null || gh issue create --repo "$DST" \
  --title "[gap] Layer 7 — Fun Stuff (dropped, not a board tracker)" \
  --body "This Issue exists solely to preserve the Layer-number → Issue-number 1:1 mapping.")
# Extract issue number and close
gh issue close "$(echo "$NUM" | grep -oE '[0-9]+$')" --repo "$DST" --reason "not planned"
```

Expected: New Issue created as `frank-ops#7`, then closed with reason `not planned`.

Note: the `gap` label may not exist in a fresh repo. Either create it first (`gh label create gap --repo "$DST" --description "Placeholder for a dropped/absorbed Layer number"`) or drop the `--label gap` flag.

- [x] **Step 4: Transfer Layers 8–14 and 15–19 (with Layer-number/Issue-number alignment)**

```bash
# Layer 8 → frank-ops#8
gh issue transfer 93 --repo "$SRC" "$DST"
# Layers 9–14 → frank-ops#9-14
for N in 94 95 96 97 98 99; do
  gh issue transfer "$N" --repo "$SRC" "$DST"
done
# Layer 15 → frank-ops#15  (source is frank issue 11 — repurposed from Paperclip)
gh issue transfer 11 --repo "$SRC" "$DST"
# Layer 16 → frank-ops#16  (source is frank issue 10 — repurposed from Media)
gh issue transfer 10 --repo "$SRC" "$DST"
# Layer 17 → frank-ops#17
gh issue transfer 100 --repo "$SRC" "$DST"
# Layer 18 → frank-ops#18  (source is frank issue 8 — repurposed from Persistent Agent)
gh issue transfer 8 --repo "$SRC" "$DST"
# Layer 19 → frank-ops#19
gh issue transfer 101 --repo "$SRC" "$DST"

# Sanity
gh issue list --repo "$DST" --state all --json number,title --jq '.[] | "\(.number)\t\(.title)"' | sort -n | tail -20
```

Expected: Issues 8–19 populated with correct Layer titles. If any transfer produced the wrong number, STOP and re-sequence — downstream label wiring depends on this alignment.

- [x] **Step 5: Burn gap placeholders #20, #21, #22, #23**

```bash
for LAYER_NUM in 20 21 22 23; do
  case "$LAYER_NUM" in
    20) REASON="absorbed into adjacent Layers per editorial rule" ;;
    21) REASON="merged into Layer 18 (Persistent Agent) — same workstation" ;;
    22) REASON="absorbed into Layer 8 (Observability) — Health Monitoring" ;;
    23) REASON="absorbed into Layer 8 (Observability) — Health Bridge" ;;
  esac
  NUM=$(gh issue create --repo "$DST" \
    --title "[gap] Layer $LAYER_NUM — $REASON" \
    --body "Placeholder to preserve Layer-number → Issue-number 1:1 mapping. See spec." \
    --json number --jq .number 2>/dev/null)
  gh issue close "$NUM" --repo "$DST" --reason "not planned"
done
```

Expected: Issues #20, #21, #22, #23 created and closed.

- [x] **Step 6: Transfer Layers 24 and 25**

```bash
gh issue transfer 102 --repo "$SRC" "$DST"  # → frank-ops#24
gh issue transfer 103 --repo "$SRC" "$DST"  # → frank-ops#25
```

- [x] **Step 7: Verify the Derio Ops board auto-updated**

GitHub auto-updates project v2 item references when an Issue transfers. Confirm by querying the board:

```bash
gh api graphql -f query='
{
  organization(login:"derio-net") {
    projectV2(number:1) {
      items(first:50) {
        nodes {
          content {
            ... on Issue {
              number
              repository { nameWithOwner }
              title
            }
          }
        }
      }
    }
  }
}' --jq '.data.organization.projectV2.items.nodes[].content | "\(.repository.nameWithOwner)#\(.number)\t\(.title)"' | sort
```

Expected: 20 items, all on `derio-net/frank-ops`, numbered 1–6, 8–19, 24–25. No residual items on `derio-net/frank`.

If any Layer tracker still shows `derio-net/frank#N`, remove it from the board manually and re-add the corresponding `frank-ops` Issue:

```bash
# Example for one stuck item
gh project item-delete --owner derio-net --project 1 --id <item-id>
gh project item-add --owner derio-net --project 1 --url https://github.com/derio-net/frank-ops/issues/<LAYER>
```

- [x] **Step 8: Update the existing `agent-pod-not-running` rule label**

The pre-Pass-3 rule still carries `github_issue: "frank#8"` (the old public-repo reference). Repoint it at `frank-ops#18`.

Open `apps/grafana-alerting/manifests/alert-rules-cm.yaml` and change:
```yaml
            labels:
              severity: critical
              github_issue: "frank#8"
```
to:
```yaml
            labels:
              severity: critical
              github_issue: "frank-ops#18"
```

Commit, push, restart Grafana:
```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "chore(obs): repoint agent-pod-not-running rule at frank-ops#18"
git push origin main
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl rollout status -n monitoring deploy/grafana --timeout=120s
```

- [x] **Step 9: Update the spec's Layer table**

Edit `docs/superpowers/specs/2026-04-16--platform--derio-ops-layers-restoration-design.md` — replace every old-repo issue reference in the table's "Issue" column with the corresponding `frank-ops` number. Do longest-number substitutions first to avoid partial matches (e.g. `frank#103` before `frank#10`).

```bash
SPEC=docs/superpowers/specs/2026-04-16--platform--derio-ops-layers-restoration-design.md
sed -i \
  -e 's|frank#103|frank-ops#25|g' \
  -e 's|frank#102|frank-ops#24|g' \
  -e 's|frank#101|frank-ops#19|g' \
  -e 's|frank#100|frank-ops#17|g' \
  -e 's|frank#99|frank-ops#14|g' \
  -e 's|frank#98|frank-ops#13|g' \
  -e 's|frank#97|frank-ops#12|g' \
  -e 's|frank#96|frank-ops#11|g' \
  -e 's|frank#95|frank-ops#10|g' \
  -e 's|frank#94|frank-ops#9|g' \
  -e 's|frank#93|frank-ops#8|g' \
  -e 's|frank#92|frank-ops#6|g' \
  -e 's|frank#91|frank-ops#5|g' \
  -e 's|frank#90|frank-ops#4|g' \
  -e 's|frank#89|frank-ops#3|g' \
  -e 's|frank#88|frank-ops#2|g' \
  -e 's|frank#87|frank-ops#1|g' \
  -e 's|frank#11\b|frank-ops#15|g' \
  -e 's|frank#10\b|frank-ops#16|g' \
  -e 's|frank#8\b|frank-ops#18|g' \
  "$SPEC"
git add "$SPEC"
git commit -m "docs(spec): relocate Layer trackers to derio-net/frank-ops (private)"
git push origin main
```

Note: `frank#8`, `#10`, `#11` use word-boundary `\b` to avoid clobbering the longer numbers — but those longer numbers are also substituted earlier in the command (belt-and-braces).

### Task 2: Verify the pipeline end-to-end

Prove the updated `agent-pod-not-running` rule still fires through the Bridge and hits `frank-ops#18` correctly before adding 19 more Layer rules on top.

**Files:** none

- [x] **Step 1: Port-forward and send a synthetic firing alert targeting `frank-ops#18`**

```bash
source .env
export WEBHOOK_SECRET=$(kubectl get secret -n monitoring health-bridge-secrets -o jsonpath='{.data.WEBHOOK_SECRET}' | base64 -d)
kubectl port-forward -n monitoring svc/health-bridge 8080:8080 >/dev/null 2>&1 &
PF_PID=$!
sleep 2

curl -s -X POST http://localhost:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "status":"firing",
    "alerts":[{
      "status":"firing",
      "labels":{"alertname":"pass3-smoke","severity":"warning","github_issue":"frank-ops#18"},
      "annotations":{"summary":"Pass 3 pipeline smoke test"},
      "startsAt":"2026-04-16T00:00:00Z",
      "generatorURL":"https://grafana.frank.derio.net"
    }]
  }'
echo
```

Expected: `{"processed": 1, "total": 1}`.

- [x] **Step 2: Verify Lifecycle field on frank-ops#18 changed to `degraded`**

```bash
gh api graphql -f query='
{
  repository(owner:"derio-net", name:"frank-ops") {
    issue(number:18) {
      projectItems(first:5) {
        nodes {
          fieldValueByName(name:"Lifecycle") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
        }
      }
    }
  }
}' --jq '.data.repository.issue.projectItems.nodes[].fieldValueByName.name'
```

Expected: `degraded`.

- [x] **Step 3: Send a resolved alert, verify return to `healthy`**

```bash
curl -s -X POST http://localhost:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "status":"resolved",
    "alerts":[{
      "status":"resolved",
      "labels":{"alertname":"pass3-smoke","severity":"warning","github_issue":"frank-ops#18"},
      "annotations":{"summary":"Pass 3 pipeline smoke test resolved"},
      "startsAt":"2026-04-16T00:00:00Z",
      "endsAt":"2026-04-16T00:05:00Z"
    }]
  }'
echo
kill $PF_PID
```

Re-run the GraphQL query from Step 2. Expected: `healthy`.

- [-] **Step 4: If either transition failed, stop the plan and root-cause** *(skipped — both transitions succeeded on first try)*

If Lifecycle didn't transition: check Bridge logs (`kubectl logs -n monitoring -l app=health-bridge --tail=50`). Common failures:
- `issue X is not on project Y` — transfer didn't carry the Issue's board-item association (re-add manually via `gh project item-add`).
- `unknown lifecycle state` — project doesn't expose the expected option names.
- `401 unauthorized` — `HEALTH_BRIDGE_WEBHOOK_SECRET` mismatch between Grafana contact point and the ExternalSecret.
- `404` when querying frank-ops — Bridge's GitHub token needs `repo` scope on the new private repo. Verify the token's scope includes all private repos, not just specific ones.

Do not proceed to Phase 1 until this smoke test is green.

### Task 3: Section-organise the alert-rules ConfigMap

Group rules by consumer so future edits stay tidy. Existing rules (heartbeats, endpoint-down, pod-not-running) are feature-level; new Pass 3 rules are Layer-level.

**Files:**
- Modify: `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

- [x] **Step 1: Add section banner comments at the top of each group**

Open `apps/grafana-alerting/manifests/alert-rules-cm.yaml`. Insert a banner immediately after `groups:` and before the first `- orgId:`:

```yaml
    groups:
      # =====================================================================
      # FEATURE-LEVEL ALERTS (bugs in specific willikins crons / endpoints)
      # Labels: severity + github_issue=willikins#<N>
      # These fire independently of the Layer trackers below; the Layer
      # rules aggregate them into a single "is this Layer up" signal.
      # =====================================================================

      # --- Heartbeat-stale: exercise reminder (eval every 5m) ---
      - orgId: 1
        name: heartbeat-stale-5m
```

Add a second banner before Layer rules (which get inserted in later phases):

```yaml
      # =====================================================================
      # LAYER TRACKERS (Derio Ops board, derio-net/frank-ops — private)
      # Labels: severity + github_issue=frank-ops#<LAYER>
      # One rule per Layer. Use aggregation to keep the signal single.
      # Added in Pass 3 — see docs/superpowers/specs/2026-04-16--platform--derio-ops-layers-restoration-design.md
      # =====================================================================
      # (Layer rules appended below as each phase completes.)
```

- [x] **Step 2: Commit, push, restart Grafana to reload provisioning**

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "chore(obs): section-organise alert-rules ConfigMap (Pass 3 prep)"
git push origin main

kubectl rollout status -n argocd application/grafana-alerting --timeout=60s || true
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl rollout status -n monitoring deploy/grafana --timeout=120s
```

Expected: Grafana pod restarts cleanly. Alert rules reload without syntax errors (no "sse.parseError" in logs).

### Task 4: Confirm notification policy routes Feature Health folder to the Bridge

**Files:** none (read-only verification)

- [x] **Step 1: Check folder-name casing matches the route matcher**

The notification-policy matcher is `grafana_folder=Feature Health`, but the rule file writes `folder: feature-health`. Grafana internally uses the folder's display name ("Feature Health"), not the provisioning key. Verify by tailing Grafana logs when an alert fires:

```bash
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana --tail=200 | grep -i 'routed to\|health-bridge-webhook\|Health Bridge'
```

Expected: At least one `... routed to ... Health Bridge Webhook ...` line from the Task 2 smoke test. If absent, the matcher needs to be adjusted to `grafana_folder=feature-health` in `apps/grafana-alerting/manifests/notification-policy-cm.yaml`.

- [x] **Step 2: If the matcher was wrong, fix and redeploy**

```bash
# Edit apps/grafana-alerting/manifests/notification-policy-cm.yaml:
#   matchers: [ "grafana_folder=feature-health" ]
# Or alternatively:
#   object_matchers: [ ["grafana_folder","=","feature-health"] ]
git add apps/grafana-alerting/manifests/notification-policy-cm.yaml
git commit -m "fix(obs): match Feature Health folder casing in notification policy"
git push origin main
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
```

Re-run Task 2 smoke test to confirm.

---

## Phase 1: Priority Dogfood — Layer 8 Observability [agentic]

### Dependencies

Blocked by Phase 0.

### Context

Layer 8's components: VictoriaMetrics, Grafana, Pushgateway, Blackbox Exporter, Fluent Bit, Health Bridge. The clever bit is dogfooding — the Bridge must alert on its own absence, otherwise a dead Bridge goes unnoticed (and then nothing on the board updates).

**Signal source:** Blackbox probe on `http://health-bridge.monitoring.svc.cluster.local:8080/healthz` (already in `apps/blackbox-exporter/manifests/vmprobe.yaml`), plus VictoriaMetrics/Grafana up-state via kube-state-metrics.

### Task 1: Write the Layer 8 aggregate rule

**Files:**
- Modify: `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

- [x] **Step 1: Append the Layer 8 rule under the LAYER TRACKERS banner**

```yaml
      # --- Layer 8 — Observability (frank-ops#8) ---
      # Per-instance: one alert per failing monitoring pod, plus one if the
      # health-bridge self-probe fails. Uses label_replace to inject a
      # `component` label that normalises across both signals for templating.
      - orgId: 1
        name: layer-8-observability-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-8-observability-down
            title: Layer 8 Observability Degraded
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  # Raw readiness values (0=NotReady, 1=Ready) with a
                  # normalised `component` label for templating. Threshold lt 1
                  # fires on value==0, per-series.
                  expr: |
                    label_replace(
                      kube_pod_status_ready{namespace="monitoring",condition="true"},
                      "component", "pod/$1", "pod", "(.+)"
                    )
                    or
                    label_replace(
                      probe_success{instance="http://health-bridge.monitoring.svc.cluster.local:8080/healthz"},
                      "component", "probe/health-bridge-healthz", "", ""
                    )
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: critical
              github_issue: "frank-ops#8"
            annotations:
              summary: "L8 Observability: {{ $labels.component }} failing"
              runbook: "kubectl get pods -n monitoring; kubectl get probe -n monitoring feature-health-probes -o yaml"
```

- [x] **Step 2: Validate PromQL against live VictoriaMetrics before committing**

```bash
source .env
kubectl -n monitoring port-forward svc/vmselect-victoria-metrics-k8s-stack 8481:8481 >/dev/null 2>&1 &
sleep 2

# Component-readiness check:
curl -sG "http://localhost:8481/select/0/prometheus/api/v1/query" \
  --data-urlencode 'query=sum(kube_pod_status_ready{namespace="monitoring",condition="true"})' | jq '.data.result'
curl -sG "http://localhost:8481/select/0/prometheus/api/v1/query" \
  --data-urlencode 'query=sum(kube_pod_info{namespace="monitoring"})' | jq '.data.result'

# Probe check:
curl -sG "http://localhost:8481/select/0/prometheus/api/v1/query" \
  --data-urlencode 'query=probe_success{instance="http://health-bridge.monitoring.svc.cluster.local:8080/healthz"}' | jq '.data.result'

kill %1
```

Expected: Each query returns a non-empty `result` array with `value` `[timestamp, "<number>"]`. If `probe_success` is empty, the Bridge-healthz target wasn't scraped yet — wait 60s and retry; if still empty, the VMProbe needs Bridge-pod readiness verified.

- [x] **Step 3: Commit, push, restart Grafana**

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "feat(obs): add Layer 8 (Observability) alert rule → frank-ops#8"
git push origin main
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl rollout status -n monitoring deploy/grafana --timeout=120s
```

- [x] **Step 4: Verify the rule loads and evaluates to Normal**

```bash
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana --tail=50 | grep -i 'layer-8\|parse error\|provisioning' | head -20
```

Expected: `msg="Provisioning alert rules" ...layer-8-observability-down...` and no `parseError`. Query the Grafana API:

```bash
GRAFANA_URL="https://grafana.frank.derio.net"
curl -s -u admin:$GRAFANA_ADMIN_PASSWORD "$GRAFANA_URL/api/v1/provisioning/alert-rules/layer-8-observability-down" | jq '.title,.condition,.labels'
```

Expected: Rule exists with `condition: C`, `labels.github_issue: "frank-ops#8"`.

### Task 2: End-to-end transition test for Layer 8

- [x] **Step 1: Simulate a firing alert via webhook** (fast path — don't actually break the monitoring stack)

```bash
kubectl port-forward -n monitoring svc/health-bridge 8080:8080 >/dev/null 2>&1 &
sleep 2
curl -s -X POST http://localhost:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{"status":"firing","labels":{"alertname":"layer-8-smoke","severity":"critical","github_issue":"frank-ops#8"},"annotations":{"summary":"Layer 8 smoke"},"startsAt":"2026-04-16T00:00:00Z"}]}'
echo
```

- [x] **Step 2: Verify frank-ops#8 → `dead` on the board** (critical severity maps to dead)

```bash
gh api graphql -f query='{repository(owner:"derio-net",name:"frank-ops"){issue(number:8){projectItems(first:5){nodes{fieldValueByName(name:"Lifecycle"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}' \
  --jq '.data.repository.issue.projectItems.nodes[].fieldValueByName.name'
```

Expected: `dead`.

- [x] **Step 3: Resolve and verify return to `healthy`**

```bash
curl -s -X POST http://localhost:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" -H "Content-Type: application/json" \
  -d '{"status":"resolved","alerts":[{"status":"resolved","labels":{"alertname":"layer-8-smoke","severity":"critical","github_issue":"frank-ops#8"},"annotations":{"summary":"Layer 8 resolved"},"startsAt":"2026-04-16T00:00:00Z","endsAt":"2026-04-16T00:05:00Z"}]}'
echo
kill %1
# Re-run the gh api graphql query — expect "healthy"
```

---

## Phase 2: Priority — Layer 18 Persistent Agent [agentic]

### Dependencies

Blocked by Phase 0. Not blocked by Phase 1 — can run in parallel.

### Context

Layer 18 (frank-ops#18) hosts the willikins crons. The existing `agent-pod-not-running` rule already carries `github_issue: "frank-ops#18"` — so pod-level failure wiring is complete. What's missing: the three `willikins#N`-labelled heartbeat rules (exercise, session-manager, audit-digest) also indicate Layer 18 trouble, but they don't roll up to the Layer tracker.

**Decision:** Keep willikins#N rules for per-feature triage (they stay unchanged); add a **second set** of Layer-level rules that fire `warning/github_issue=frank-ops#18` when any heartbeat is stale. This gives the operator two channels: "Layer 18 is degraded" (for the board) and "exercise-reminder cron specifically is broken" (for the willikins Issue).

### Task 1: Add Layer-18 heartbeat-aggregation rule

**Files:**
- Modify: `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

- [x] **Step 1: Append the Layer 18 rule**

```yaml
      # --- Layer 18 — Persistent Agent (frank-ops#18) ---
      # Per-job heartbeat check — fires ONE alert instance per stale cron, all
      # labelled github_issue=frank-ops#18 so they roll up to the Layer tracker.
      # Bridge lastState-dedup ensures only one Lifecycle transition per fire-bundle;
      # the first instance's annotation (with specific job name) lands in the comment.
      # Pod-level critical failures are covered by agent-pod-not-running
      # (labels.github_issue=frank-ops#18, severity=critical) — leave that rule intact.
      - orgId: 1
        name: layer-18-persistent-agent-degraded
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-18-persistent-agent-degraded
            title: Layer 18 Persistent Agent Heartbeat Stale
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  # Each clause returns a 0/1 series WITH the source metric's labels
                  # (notably `job`). `or` stacks them into a multi-dimensional
                  # series — one element per currently-stale job.
                  expr: |
                    (time() - willikins_heartbeat_last_success_timestamp{job="exercise_reminder"} > bool 10800)
                    or (time() - willikins_heartbeat_last_success_timestamp{job="session_manager"} > bool 600)
                    or (time() - willikins_heartbeat_last_success_timestamp{job="audit_digest"} > bool 93600)
                    or (time() - willikins_heartbeat_last_success_timestamp{job="vk_issue_bridge"} > bool 600)
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: gt, params: [0] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: warning
              github_issue: "frank-ops#18"
            annotations:
              summary: "Layer 18 (Persistent Agent) — {{ $labels.job }} cron heartbeat stale. See willikins#11/#12/#13 for per-cron triage."
              runbook: "kubectl logs -n secure-agent-pod -l app=secure-agent-pod --tail=50 | grep -i {{ $labels.job }}"
```

- [x] **Step 2: Commit, push, reload Grafana**

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "feat(obs): add Layer 18 (Persistent Agent) heartbeat-aggregation rule → frank-ops#18"
git push origin main
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl rollout status -n monitoring deploy/grafana --timeout=120s
```

- [x] **Step 3: Smoke-test the Layer 18 rule via webhook** (same pattern as Phase 1 Task 2, with `github_issue=frank-ops#18` and `severity=warning` → expect `degraded`)

### Task 2: Confirm the Deployed pod rule still co-exists

The existing `agent-pod-not-running` rule also targets `frank-ops#18` with `severity=critical`. If both fire simultaneously (pod down AND heartbeat stale), the more-severe transition wins — i.e. Layer 18 → `dead` (correct).

- [x] **Step 1: Read both rules, confirm label overlap is intentional**

```bash
grep -A 40 'agent-pod-not-running\|layer-18-persistent-agent-degraded' apps/grafana-alerting/manifests/alert-rules-cm.yaml | grep -E 'severity:|github_issue:'
```

Expected:
```
              severity: critical
              github_issue: "frank-ops#18"
              severity: warning
              github_issue: "frank-ops#18"
```

This is the intended dual-signal: warning (heartbeat stale) → `degraded`, critical (pod down) → `dead`, resolution of either → `healthy`.

---

## Phase 3: Foundation Layers (1–6) [agentic]

### Dependencies

Blocked by Phase 0. Independent of Phases 1–2.

### Context

Foundation layers have strong coverage from kube-state-metrics and existing dashboards. One rule per layer, all `severity: warning` except Layer 2 (OS) and Layer 6 (GitOps) which are cluster-survival and rate `critical`.

### Task 1: Layer 1 — Hardware & Nodes (frank-ops#1)

**Files:** Modify `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

- [x] **Step 1: Append rule — any node NotReady**

```yaml
      # --- Layer 1 — Hardware & Nodes (frank-ops#1) ---
      # Per-node: one alert instance per NotReady node.
      - orgId: 1
        name: layer-1-hardware-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-1-hardware-down
            title: Layer 1 Hardware Node NotReady
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  # status="false" series are 1 when node is NotReady, 0 otherwise.
                  # Preserves `node` label for templating.
                  expr: 'kube_node_status_condition{condition="Ready",status="false"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: gt, params: [0] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: warning
              github_issue: "frank-ops#1"
            annotations:
              summary: "L1 Hardware: node {{ $labels.node }} NotReady"
              runbook: "kubectl describe node {{ $labels.node }}; talosctl -n {{ $labels.node }} health"
```

### Task 2: Layer 2 — OS & Bootstrap (frank-ops#2)

- [x] **Step 1: Append rule — control-plane node NotReady = critical**

```yaml
      # --- Layer 2 — OS & Bootstrap (frank-ops#2) ---
      # Per-control-plane-node: one alert per NotReady mini node.
      - orgId: 1
        name: layer-2-os-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-2-os-down
            title: Layer 2 OS Control-Plane NotReady
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  # Control-plane nodes only (filter by role)
                  expr: |
                    kube_node_status_condition{condition="Ready",status="false"}
                    * on(node) group_left kube_node_role{role="control-plane"}
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: gt, params: [0] }
            noDataState: OK
            execErrState: Error
            for: 2m
            labels:
              severity: critical
              github_issue: "frank-ops#2"
            annotations:
              summary: "L2 OS: control-plane node {{ $labels.node }} NotReady — HA at risk"
              runbook: "talosctl -n {{ $labels.node }} health; talosctl -n {{ $labels.node }} dmesg | tail -50"
```

### Task 3: Layer 3 — Networking / Cilium (frank-ops#3)

- [x] **Step 1: Append rule — Cilium agent down on any node**

```yaml
      # --- Layer 3 — Networking / Cilium (frank-ops#3) ---
      # Per-pod: one alert per NotReady cilium-agent (or cilium-operator) pod.
      - orgId: 1
        name: layer-3-networking-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-3-networking-down
            title: Layer 3 Cilium Agent Down
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace="kube-system",pod=~"cilium-.*",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: warning
              github_issue: "frank-ops#3"
            annotations:
              summary: "L3 Cilium: pod {{ $labels.pod }} NotReady"
              runbook: "kubectl -n kube-system describe pod {{ $labels.pod }}; kubectl -n kube-system logs {{ $labels.pod }} --tail=50"
```

### Task 4: Layer 4 — Storage / Longhorn (frank-ops#4)

- [x] **Step 1: Append rule — degraded Longhorn volumes**

```yaml
      # --- Layer 4 — Storage / Longhorn (frank-ops#4) ---
      # Per-volume: one alert per Degraded/Faulted volume.
      # robustness: 0=unknown 1=healthy 2=degraded 3=faulted
      - orgId: 1
        name: layer-4-storage-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-4-storage-down
            title: Layer 4 Longhorn Volume Degraded
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'longhorn_volume_robustness'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: gt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 10m
            labels:
              severity: warning
              github_issue: "frank-ops#4"
            annotations:
              summary: "L4 Longhorn: volume {{ $labels.volume }} robustness={{ $values.B.Value | printf \"%.0f\" }} (2=degraded, 3=faulted)"
              runbook: "kubectl -n longhorn-system get volume {{ $labels.volume }} -o yaml"
```

### Task 5: Layer 5 — GPU Compute (frank-ops#5)

- [x] **Step 1: Append rule — any GPU operator pod NotReady**

```yaml
      # --- Layer 5 — GPU Compute (frank-ops#5) ---
      # Per-pod: fires for each NotReady GPU-operator or Intel-DRA-driver pod,
      # carrying `namespace` + `pod` labels for templating.
      - orgId: 1
        name: layer-5-gpu-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-5-gpu-down
            title: Layer 5 GPU Operator NotReady
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace=~"gpu-operator|intel-gpu-resource-driver",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: warning
              github_issue: "frank-ops#5"
            annotations:
              summary: "L5 GPU: {{ $labels.namespace }}/{{ $labels.pod }} NotReady"
              runbook: "kubectl -n {{ $labels.namespace }} describe pod {{ $labels.pod }}"
```

Note: the `intel-gpu-resource-driver` namespace name may differ — verify with `kubectl get ns | grep -i gpu` and correct before committing.

### Task 6: Layer 6 — GitOps / ArgoCD (frank-ops#6)

- [x] **Step 1: Append rule — ArgoCD server unreachable OR apps OutOfSync**

```yaml
      # --- Layer 6 — GitOps / ArgoCD (frank-ops#6) ---
      # Two sub-rules in one group, both → frank-ops#6:
      #   - layer-6-app-unhealthy: per-app alert when health_status != Healthy
      #   - layer-6-server-down: argocd-server pod NotReady
      # The Bridge's lastState dedup ensures only one Lifecycle transition per
      # fire bundle; Telegram groups them into a single message.
      - orgId: 1
        name: layer-6-gitops-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-6-app-unhealthy
            title: Layer 6 ArgoCD App Unhealthy
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  # argocd_app_info is always 1 when the app exists; the
                  # label selector filters to non-Healthy states only.
                  expr: 'argocd_app_info{health_status!~"Healthy|Missing"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: gt, params: [0] }
            noDataState: OK
            execErrState: Error
            for: 10m
            labels:
              severity: critical
              github_issue: "frank-ops#6"
            annotations:
              summary: "L6 ArgoCD: app {{ $labels.name }} health={{ $labels.health_status }}"
              runbook: "argocd app get {{ $labels.name }} --port-forward --port-forward-namespace argocd"
          - uid: layer-6-server-down
            title: Layer 6 ArgoCD Server Down
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace="argocd",pod=~"argocd-server.*",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: critical
              github_issue: "frank-ops#6"
            annotations:
              summary: "L6 ArgoCD: server pod {{ $labels.pod }} NotReady"
              runbook: "kubectl -n argocd describe pod {{ $labels.pod }}"
```

### Task 7: Deploy + verify Phase 3 rules

- [x] **Step 1: Commit + push all six new rules together**

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "feat(obs): add Layer 1–6 foundation alert rules → frank-ops#1-92"
git push origin main
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl rollout status -n monitoring deploy/grafana --timeout=120s
```

- [x] **Step 2: Smoke-test each rule via webhook** (6 quick calls — use `severity=warning` for 1,3,4,5 and `severity=critical` for 2,6)

Script it (layer number = issue number in `frank-ops`):

```bash
for TUPLE in "1:warning" "2:critical" "3:warning" "4:warning" "5:warning" "6:critical"; do
  LAYER="${TUPLE%%:*}"; SEV="${TUPLE##*:}"
  curl -s -X POST http://localhost:8080/webhook \
    -H "Authorization: Bearer $WEBHOOK_SECRET" -H "Content-Type: application/json" \
    -d "{\"status\":\"firing\",\"alerts\":[{\"status\":\"firing\",\"labels\":{\"alertname\":\"layer-smoke\",\"severity\":\"$SEV\",\"github_issue\":\"frank-ops#$LAYER\"},\"annotations\":{\"summary\":\"Phase 3 smoke\"},\"startsAt\":\"2026-04-16T00:00:00Z\"}]}"
  echo " → frank-ops#$LAYER"
done
```

- [x] **Step 3: Verify all six Lifecycle transitions, then resolve** (loop)

```bash
for LAYER in 1 2 3 4 5 6; do
  STATE=$(gh api graphql -f query="{repository(owner:\"derio-net\",name:\"frank-ops\"){issue(number:$LAYER){projectItems(first:5){nodes{fieldValueByName(name:\"Lifecycle\"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}" --jq '.data.repository.issue.projectItems.nodes[].fieldValueByName.name')
  echo "frank-ops#$LAYER: $STATE"
done
# Expected: 1→degraded, 2→dead, 3→degraded, 4→degraded, 5→degraded, 6→dead

# Resolve:
for TUPLE in "1:warning" "2:critical" "3:warning" "4:warning" "5:warning" "6:critical"; do
  LAYER="${TUPLE%%:*}"; SEV="${TUPLE##*:}"
  curl -s -X POST http://localhost:8080/webhook \
    -H "Authorization: Bearer $WEBHOOK_SECRET" -H "Content-Type: application/json" \
    -d "{\"status\":\"resolved\",\"alerts\":[{\"status\":\"resolved\",\"labels\":{\"alertname\":\"layer-smoke\",\"severity\":\"$SEV\",\"github_issue\":\"frank-ops#$LAYER\"},\"annotations\":{\"summary\":\"Phase 3 resolve\"},\"startsAt\":\"2026-04-16T00:00:00Z\",\"endsAt\":\"2026-04-16T00:05:00Z\"}]}"
  echo " → resolved frank-ops#$LAYER"
done
# Expected: all six return to healthy.
```

---

## Phase 4: Core Services (9, 10, 11, 12, 13, 14) [agentic]

### Dependencies

Blocked by Phase 0. Independent of Phases 1–3.

### Task 1: Layer 9 — Backup & DR (frank-ops#9)

**Files:** Modify `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

- [x] **Step 1: Append rule — last successful Longhorn backup older than 48h**

```yaml
      # --- Layer 9 — Backup & DR (frank-ops#9) ---
      - orgId: 1
        name: layer-9-backup-stale
        folder: feature-health
        interval: 5m
        rules:
          - uid: layer-9-backup-stale
            title: Layer 9 Longhorn Backup Stale
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 3600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'time() - max(longhorn_backup_actual_size_bytes > 0) by (backup) * 0 + time() - longhorn_backup_target_last_available_time'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 3600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 3600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: gt, params: [172800] }
            noDataState: OK
            execErrState: Error
            for: 30m
            labels:
              severity: warning
              github_issue: "frank-ops#9"
            annotations:
              summary: "L9 Backup: last Longhorn backup {{ $values.B.Value | humanizeDuration }} ago (>48h threshold)"
              runbook: "kubectl -n longhorn-system get backups | tail; kubectl -n longhorn-system get backuptarget"
```

Note: `longhorn_backup_target_last_available_time` may not exist — if `curl` query returns empty, fall back to `longhorn_backup_state{state="Completed"}` age-of-last. Verify per Phase 1 Task 1 Step 2 pattern before committing.

### Task 2: Layer 10 — Secrets (frank-ops#10)

- [x] **Step 1: Append rule — Infisical pod down OR ESO reconciliation failures**

```yaml
      # --- Layer 10 — Secrets (frank-ops#10) ---
      # Per-pod: one alert per NotReady Infisical or ESO pod.
      - orgId: 1
        name: layer-10-secrets-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-10-secrets-down
            title: Layer 10 Secrets Degraded
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace=~"infisical|external-secrets",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: warning
              github_issue: "frank-ops#10"
            annotations:
              summary: "L10 Secrets: {{ $labels.namespace }}/{{ $labels.pod }} NotReady"
              runbook: "kubectl -n {{ $labels.namespace }} describe pod {{ $labels.pod }}"
```

### Task 3: Layer 11 — Local Inference (frank-ops#11)

- [x] **Step 1: Append rule — Ollama or LiteLLM down**

```yaml
      # --- Layer 11 — Local Inference (frank-ops#11) ---
      # Per-pod: one alert per NotReady Ollama or LiteLLM pod.
      - orgId: 1
        name: layer-11-inference-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-11-inference-down
            title: Layer 11 Local Inference Degraded
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace=~"ollama|litellm",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: warning
              github_issue: "frank-ops#11"
            annotations:
              summary: "L11 Inference: {{ $labels.namespace }}/{{ $labels.pod }} NotReady"
              runbook: "kubectl -n {{ $labels.namespace }} describe pod {{ $labels.pod }}"
```

### Task 4: Layer 12 — Agentic Control Plane / Sympozium (frank-ops#12)

- [x] **Step 1: Append rule — Sympozium pod NotReady**

```yaml
      # --- Layer 12 — Agentic Control Plane (frank-ops#12) ---
      # Per-pod: one alert per NotReady Sympozium pod.
      - orgId: 1
        name: layer-12-agents-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-12-agents-down
            title: Layer 12 Sympozium Down
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace="sympozium",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: warning
              github_issue: "frank-ops#12"
            annotations:
              summary: "L12 Sympozium: pod {{ $labels.pod }} NotReady"
              runbook: "kubectl -n sympozium describe pod {{ $labels.pod }}"
```

### Task 5: Layer 13 — Unified Auth / Authentik (frank-ops#13)

- [x] **Step 1: Append rule — Authentik server or worker NotReady**

```yaml
      # --- Layer 13 — Unified Auth / Authentik (frank-ops#13) ---
      # Per-pod: one alert per NotReady Authentik server/worker pod.
      - orgId: 1
        name: layer-13-auth-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-13-auth-down
            title: Layer 13 Authentik Degraded
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace="authentik",pod=~"authentik-(server|worker).*",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: critical
              github_issue: "frank-ops#13"
            annotations:
              summary: "L13 Authentik: pod {{ $labels.pod }} NotReady — SSO/forward-auth at risk"
              runbook: "kubectl -n authentik describe pod {{ $labels.pod }}; kubectl -n authentik logs {{ $labels.pod }} --tail=50"
```

Authentik is `critical` because losing it breaks forward-auth for every SSO-protected service.

### Task 6: Layer 14 — Multi-tenancy / vCluster (frank-ops#14)

- [x] **Step 1: Append rule — any vCluster pod NotReady**

```yaml
      # --- Layer 14 — Multi-tenancy / vCluster (frank-ops#14) ---
      # Per-vCluster-control-plane-pod: one alert per NotReady vcluster pod.
      - orgId: 1
        name: layer-14-vcluster-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-14-vcluster-down
            title: Layer 14 vCluster Degraded
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace=~"vcluster-.*",pod=~"vcluster-.*",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 10m
            labels:
              severity: warning
              github_issue: "frank-ops#14"
            annotations:
              summary: "L14 vCluster: {{ $labels.namespace }}/{{ $labels.pod }} NotReady"
              runbook: "kubectl -n {{ $labels.namespace }} describe pod {{ $labels.pod }}"
```

### Task 7: Deploy + verify Phase 4 rules

- [x] **Step 1: Commit + push**

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "feat(obs): add Layer 9–14 core-service alert rules → frank-ops#9-99"
git push origin main
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl rollout status -n monitoring deploy/grafana --timeout=120s
```

- [x] **Step 2: Smoke-test the six new rules** (same loop pattern as Phase 3 Task 7 with issues 94-99, severities warning/warning/warning/warning/critical/warning)

---

## Phase 5: User-facing (15, 16, 17) [agentic]

### Dependencies

Blocked by Phase 0. Independent of other Layer phases.

### Context

Three partially-baked Layers:
- **Layer 15 (frank-ops#15):** Initial state `in-progress`. n8n + VK deployed; Paperclip + Praison planned.
- **Layer 16 (frank-ops#16):** Initial state `blocked`. ComfyUI + GPU Switcher pending Traefik route + model downloads.
- **Layer 17 (frank-ops#17):** Initial state `healthy`. Extended basis — blog probe + mesh peer count + cert expiry + Hetzner API.

A rule that fires constantly because a Layer is legitimately blocked would make the Health Bridge flap the Lifecycle back to `dead` and mask the intentional state. Strategy:
- **Layer 15:** rule covers only the deployed components (n8n, VK). It's OK if this rule fires — `in-progress` will be overridden to `degraded`, which is honest.
- **Layer 16:** no rule yet. Write a `# DEFERRED` comment in the ConfigMap with the intended expression once Layer 16 is unblocked.
- **Layer 17:** rule covers blog blackbox probe + Headscale peer count. Hetzner API check deferred to Phase 7 (needs a new exporter).

### Task 1: Layer 15 — Agentic Workflows (frank-ops#15)

- [x] **Step 1: Append rule — n8n or VK pod NotReady**

```yaml
      # --- Layer 15 — Agentic Workflows (frank-ops#15) ---
      # Per-pod: one alert per NotReady n8n or VK pod.
      # Paperclip + Praison will be folded into the namespace regex when deployed.
      - orgId: 1
        name: layer-15-workflows-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-15-workflows-down
            title: Layer 15 Agentic Workflows Degraded
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace=~"n8n-01|vk-remote",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: warning
              github_issue: "frank-ops#15"
            annotations:
              summary: "L15 Workflows: {{ $labels.namespace }}/{{ $labels.pod }} NotReady"
              runbook: "kubectl -n {{ $labels.namespace }} describe pod {{ $labels.pod }}"
```

### Task 2: Layer 16 — Media Generation (frank-ops#16) — placeholder

- [x] **Step 1: Insert only a DEFERRED-work comment block** (no rule yet — Layer is blocked by design)

```yaml
      # --- Layer 16 — Media Generation (frank-ops#16) ---
      # DEFERRED (Pass 3+): Layer is currently `blocked` pending Traefik route +
      # model downloads. Once unblocked, add a rule that checks:
      #   - ComfyUI pod readiness (namespace=comfyui)
      #   - GPU Switcher pod readiness (namespace=gpu-switcher)
      # Label: github_issue=frank-ops#16, severity=warning.
      # Until that rule exists, frank-ops#16's Lifecycle field must be managed
      # manually (left at `blocked`).
```

- [x] **Step 2: Document the manual-management deviation**

Add a sub-heading in this plan's "Deployment Deviations" section after this phase executes, confirming that `frank-ops#16` is left at manual `blocked` state.

### Task 3: Layer 17 — Public Edge / Hop (frank-ops#17)

- [x] **Step 1: Append rule — blog blackbox probe failing OR Headscale peer count abnormal**

```yaml
      # --- Layer 17 — Public Edge / Hop (frank-ops#17) ---
      - orgId: 1
        name: layer-17-edge-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-17-edge-down
            title: Layer 17 Public Edge Degraded
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: |
                    (probe_success{instance="https://blog.derio.net"} < bool 1)
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: gt, params: [0] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: critical
              github_issue: "frank-ops#17"
            annotations:
              summary: "L17 Edge: probe {{ $labels.instance }} failing — Hop cluster or Caddy down"
              runbook: "source .env_hop; kubectl -n blog get pods; talosctl -n $HOP_IP health"
              # DEFERRED (Pass 3+): extend with Headscale peer count + cert expiry + Hetzner API.
              # Headscale: headscale_peer_count from a sidecar scrape (needs exporter).
              # Cert expiry: probe_ssl_earliest_cert_expiry - time() < 7*86400.
              # Hetzner API: needs hetzner_server_status exporter — file a follow-up.
```

Note: `probe_success{instance="https://blog.derio.net"}` relies on blog.derio.net being in the `feature-health` VMProbe target list — it already is (`apps/blackbox-exporter/manifests/vmprobe.yaml` line 13). No additional probe needed.

### Task 4: Deploy + verify Phase 5 rules

- [x] **Step 1: Commit + push**

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "feat(obs): add Layer 15 + 17 rules → frank-ops#15, frank-ops#17 (Layer 16 deferred pending unblock)"
git push origin main
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl rollout status -n monitoring deploy/grafana --timeout=120s
```

- [x] **Step 2: Smoke-test Layer 15 and 17** (webhook loop with frank-ops#15 warning, frank-ops#17 critical)

---

## Phase 6: Delivery, Ingress, CI (19, 24, 25) [agentic]

### Dependencies

Blocked by Phase 0. Independent of other Layer phases.

### Task 1: Layer 19 — Progressive Delivery / Argo Rollouts (frank-ops#19)

**Files:** Modify `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

- [x] **Step 1: Append rule — argo-rollouts controller pod NotReady**

```yaml
      # --- Layer 19 — Progressive Delivery / Argo Rollouts (frank-ops#19) ---
      # Per-pod: one alert per NotReady argo-rollouts controller pod.
      - orgId: 1
        name: layer-19-rollouts-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-19-rollouts-down
            title: Layer 19 Argo Rollouts Controller Down
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace="argo-rollouts",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 10m
            labels:
              severity: warning
              github_issue: "frank-ops#19"
            annotations:
              summary: "L19 Rollouts: controller pod {{ $labels.pod }} NotReady — canary analyses will stall"
              runbook: "kubectl -n argo-rollouts describe pod {{ $labels.pod }}"
```

### Task 2: Layer 24 — In-Cluster Ingress / Traefik (frank-ops#24)

- [x] **Step 1: Append rule — Traefik pod NotReady**

```yaml
      # --- Layer 24 — In-Cluster Ingress / Traefik (frank-ops#24) ---
      # Per-pod: one alert per NotReady Traefik pod.
      - orgId: 1
        name: layer-24-ingress-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-24-ingress-down
            title: Layer 24 Traefik Ingress Down
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace="traefik",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 5m
            labels:
              severity: critical
              github_issue: "frank-ops#24"
            annotations:
              summary: "L24 Traefik: pod {{ $labels.pod }} NotReady — *.cluster.derio.net hostnames at risk"
              runbook: "kubectl -n traefik describe pod {{ $labels.pod }}; kubectl -n traefik logs {{ $labels.pod }} --tail=50"
```

### Task 3: Layer 25 — CI/CD Platform (frank-ops#25)

- [x] **Step 1: Append rule — Gitea, Tekton controller, or Zot down**

```yaml
      # --- Layer 25 — CI/CD / Gitea + Tekton + Zot (frank-ops#25) ---
      # Per-pod: one alert per NotReady Gitea / Tekton / Zot pod.
      - orgId: 1
        name: layer-25-cicd-down
        folder: feature-health
        interval: 1m
        rules:
          - uid: layer-25-cicd-down
            title: Layer 25 CI/CD Platform Degraded
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  expr: 'kube_pod_status_ready{namespace=~"gitea|tekton-pipelines|zot",condition="true"}'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 600, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: lt, params: [1] }
            noDataState: OK
            execErrState: Error
            for: 10m
            labels:
              severity: warning
              github_issue: "frank-ops#25"
            annotations:
              summary: "L25 CI/CD: {{ $labels.namespace }}/{{ $labels.pod }} NotReady"
              runbook: "kubectl -n {{ $labels.namespace }} describe pod {{ $labels.pod }}"
```

### Task 4: Deploy + verify Phase 6 rules

- [x] **Step 1: Commit + push**

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "feat(obs): add Layer 19 + 24 + 25 delivery/ingress/CI rules → frank-ops#19-103"
git push origin main
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl rollout status -n monitoring deploy/grafana --timeout=120s
```

- [x] **Step 2: Smoke-test** (webhook loop frank-ops#19 warning, frank-ops#24 critical, frank-ops#25 warning)

---

## Phase 7: Alert UX + Finalization [agentic]

### Dependencies

Blocked by Phases 1–6.

### Context

Two jobs:
1. **Alert UX improvements.** Several existing alert summaries are generic ("VK Issue Bridge reported failures in the last 15 minutes"). Where a metric exposes actionable dimensions (failure kind, affected job, failure count), fold them into the summary via Grafana's `{{ $values }}` template. This makes Telegram pings and GitHub comments immediately actionable without needing to open the dashboard.
2. **Audit the board** and flag any Layer where the Grafana-driven Lifecycle state doesn't match reality.

### Task 1: Improve `VK Issue Bridge Failures` alert summary

**Files:** Modify `apps/grafana-alerting/manifests/alert-rules-cm.yaml`

- [ ] **Step 1: Inspect the `willikins_vk_bridge_failure_total` metric's labels**

```bash
source .env
kubectl -n monitoring port-forward svc/vmselect-victoria-metrics-k8s-stack 8481:8481 >/dev/null 2>&1 &
sleep 2
curl -sG "http://localhost:8481/select/0/prometheus/api/v1/series" \
  --data-urlencode 'match[]=willikins_vk_bridge_failure_total' | jq '.data'
kill %1
```

Expected: Series metadata with labels like `{__name__="willikins_vk_bridge_failure_total", failure_kind="...", issue_repo="...", ...}`. Record the label names.

If the metric has no useful breakdown labels, stop — file a follow-up task in the willikins repo to add `failure_kind` and `issue` labels to the counter, and mark Step 2 blocked.

- [ ] **Step 2: Rewrite the rule to expose the breakdown**

Edit the existing `vk-bridge-failures` group in `apps/grafana-alerting/manifests/alert-rules-cm.yaml`:

```yaml
      # --- VK Issue Bridge failures (eval every 5m) ---
      - orgId: 1
        name: vk-bridge-failures
        folder: feature-health
        interval: 5m
        rules:
          - uid: vk-bridge-failures
            title: VK Issue Bridge Failures
            condition: C
            data:
              - refId: A
                relativeTimeRange: { from: 900, to: 0 }
                datasourceUid: P4169E866C3094E38
                model:
                  refId: A
                  # Keep the failure_kind + issue_repo labels so they land in $labels
                  expr: 'sum by (failure_kind, issue_repo) (increase(willikins_vk_bridge_failure_total[15m])) > 0'
                  instant: true
                  intervalMs: 1000
                  maxDataPoints: 43200
              - refId: B
                relativeTimeRange: { from: 900, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: B
                  type: reduce
                  expression: A
                  reducer: last
                  settings: { mode: dropNN }
              - refId: C
                relativeTimeRange: { from: 900, to: 0 }
                datasourceUid: __expr__
                model:
                  refId: C
                  type: threshold
                  expression: B
                  conditions:
                    - evaluator: { type: gt, params: [0] }
            noDataState: OK
            execErrState: Error
            for: 0m
            labels:
              severity: warning
            annotations:
              summary: "VK Issue Bridge — {{ $values.B.Value | printf \"%.0f\" }} failure(s) of kind {{ $labels.failure_kind }} on {{ $labels.issue_repo }} in last 15m"
              description: "Check /home/claude/.willikins-agent/vk-bridge.log for the failing payload"
```

Substitute `failure_kind` / `issue_repo` for whatever the metric actually exposes (from Step 1).

- [ ] **Step 3: Audit pre-existing feature-level rules for the same enrichment**

The 20 Layer rules written in Phases 1–6 already use the multi-instance pattern. What remains are the pre-existing feature-level rules (written before Pass 3) that still collapse to scalars:

- `endpoint-down`: summary currently "HTTP endpoint probe failing" — add `{{ $labels.instance }}` so Telegram shows which endpoint. `probe_success` already carries `instance`; change the reduce to preserve labels (drop the outer `sum(...)`).
- `agent-pod-not-running`: add `{{ $labels.pod }}`. `kube_pod_status_phase` carries `pod`; remove the `sum()` wrapper in refId A so the reduce runs per-pod.

Both are quick fixes in the same vein as the Layer rules. Apply each, commit, push, reload Grafana, smoke-test by firing a synthetic alert and inspecting the rendered summary in Telegram + the GitHub comment.

Apply at least the `endpoint-down` fix — it's the cheapest and most impactful:

```yaml
            annotations:
              summary: "HTTP endpoint probe failing: {{ $labels.instance }}"
```

- [ ] **Step 4: Commit + push + reload Grafana**

```bash
git add apps/grafana-alerting/manifests/alert-rules-cm.yaml
git commit -m "feat(obs): enrich alert summaries with actionable labels (failure_kind, instance)"
git push origin main
kubectl delete pod -n monitoring -l app.kubernetes.io/name=grafana
kubectl rollout status -n monitoring deploy/grafana --timeout=120s
```

- [ ] **Step 5: Trigger a test firing and inspect the Telegram message + GitHub comment**

Use the webhook smoke-test pattern. Confirm the rendered summary contains the substituted label values.

### Task 2: Audit the Derio Ops board

- [ ] **Step 1: Query every Layer tracker's Lifecycle field and compare to reality**

```bash
for LAYER in 1 2 3 4 5 6 8 9 10 11 12 13 14 15 16 17 18 19 24 25; do
  STATE=$(gh api graphql -f query="{repository(owner:\"derio-net\",name:\"frank-ops\"){issue(number:$LAYER){title projectItems(first:5){nodes{fieldValueByName(name:\"Lifecycle\"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}" --jq '.data.repository.issue | "\(.title)\t\(.projectItems.nodes[].fieldValueByName.name)"')
  echo "frank-ops#$LAYER	$STATE"
done
```

Expected baseline: after Phase 0–6 smoke tests have all been resolved, all 20 trackers show `healthy` except the intentional holdouts:
- `frank-ops#16` — `blocked` (manual, Layer 16 not yet unblocked)
- `frank-ops#15` — `in-progress` (manual, Layer 15 has planned-but-undeployed components)

Any Layer showing `degraded` or `dead` without a known cause is a real issue — investigate via the rule's `runbook` annotation.

- [ ] **Step 2: Document deviations**

For any Layer whose state doesn't match expectations, append a bullet under "Deployment Deviations" at the bottom of this plan with: Layer number, actual state, root cause, follow-up action.

### Task 3: Flag layers where no probe could be defined

- [ ] **Step 1: Create follow-up comments for each deferred item**

```bash
# Layer 16 — probe-less because blocked
gh issue comment 16 --repo derio-net/frank-ops --body "Pass 3 Grafana wiring: Layer 16 has no alert rule yet because the Layer is currently \`blocked\`. Once Traefik route + model downloads are done, add a rule covering ComfyUI + GPU Switcher pod readiness with \`github_issue=frank-ops#16, severity=warning\`. Placeholder DEFERRED comment lives in \`apps/grafana-alerting/manifests/alert-rules-cm.yaml\`."

# Layer 17 — Headscale + Hetzner API pieces deferred
gh issue comment 17 --repo derio-net/frank-ops --body "Pass 3 Grafana wiring: Layer 17's rule currently only covers the blog blackbox probe. Extensions deferred: Headscale peer count (needs headscale metrics exporter), cert expiry (\`probe_ssl_earliest_cert_expiry - time() < 7*86400\`), Hetzner API status (needs new exporter). DEFERRED comments in \`alert-rules-cm.yaml\`."
```

### Task 4: Update spec status

- [ ] **Step 1: Edit spec to reflect Pass 3 completion**

Edit `docs/superpowers/specs/2026-04-16--platform--derio-ops-layers-restoration-design.md`:

```
-*Status: Pass 1 + Pass 2 complete. Pass 3 pending.*
+*Status: Pass 1 + Pass 2 + Pass 3 complete.*
```

```
-## Pass 3 — Grafana wiring (not yet executed)
+## Pass 3 — Grafana wiring (executed 2026-04-DD)
```

Commit:

```bash
git add docs/superpowers/specs/2026-04-16--platform--derio-ops-layers-restoration-design.md
git commit -m "docs(spec): mark Derio Ops Pass 3 complete"
git push origin main
```

---

## Phase 8: Post-Deploy Checklist [manual]

### Dependencies

Blocked by Phase 7.

This is an **extension** of the existing Observability layer (Layer 8), not a new layer — per `.claude/rules/plan-post-deploy-checklist.md`, fix/extension plans skip blog + README steps and instead update the existing Layer's posts.

- [-] **Step 1: Expose externally (if user-facing)** *(skipped — no new user-facing surface; the board itself is already accessible)*
- [ ] **Step 2: Update Building #23 Health Bridge blog post** — add a section "Pass 3: Wiring the Layer trackers" covering the per-Layer rule pattern, severity mapping, and Bridge label-format caveat. This replaces the otherwise-required new-post step.
- [ ] **Step 3: Update Operating #16 Health Bridge blog post** — add operational notes: how to smoke-test via webhook, how to check Lifecycle state via `gh api graphql`, how to reload alert rules after editing the ConfigMap.
- [-] **Step 4: Update README** *(skipped — no new service, no new IP, no structural change)*
- [ ] **Step 5: Sync runbook** — run `/sync-runbook` only if any new `# manual-operation` blocks were added. (This plan adds none — Grafana provisioning is code-driven end-to-end.)
- [ ] **Step 6: Update plan status** — edit this file's header to `**Status:** Deployed`.

---

## Deployment Deviations

Document any deviations from this plan here during execution:

*(To be filled during implementation)*
