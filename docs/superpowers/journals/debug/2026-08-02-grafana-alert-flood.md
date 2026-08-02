# Journal: 2026-08-02-grafana-alert-flood

<!-- fr:journal kind=repro scope=debug id=8ac6d2fcd83c created=2026-08-02T20:33:01 -->
### 8ac6d2fcd83c · repro · 72 Grafana alerts firing on Frank; 48 escalate as unexplained

Fetched \`/api/prometheus/grafana/api/v1/alerts\` from the VictoriaMetrics Grafana (192.168.55.203, plain HTTP): 236 rules, **72 in state \`Alerting\`**.

Running the repo `frank-alert-triage` classifier over the firing set:

| verdict | count |
|---|---|
| unexplained (escalate) | 48 |
| false-positive (tombstone) | 21 |
| muted (canary) | 2 |
| by-design (gpu timeshare) | 1 |

All 48 `unexplained` are `Layer 3 Cilium Agent Down`, plus 1 `Layer 5 GPU Operator NotReady`.
Every one carries `__name__: kube_pod_status_ready` and names a distinct
`cilium-operator-76d44bb8d-*` pod in `kube-system`. `activeAt` clusters at
2026-08-02T16:32Z.

Repro (inside the cluster-admin isolation container):

    PW=$(kubectl -n monitoring get secret victoria-metrics-grafana -o jsonpath="{.data.admin-password}" | base64 -d)
    curl -s -u "admin:$PW" "http://192.168.55.203/api/prometheus/grafana/api/v1/alerts" -o /tmp/frank-alerts.json
    PYTHONPATH=agents/skills/frank-alert-triage python3 <driver from SKILL.md Step 3>

<!-- fr:journal kind=ruled-out scope=debug id=927bb243c991 created=2026-08-02T20:33:54 -->
### 927bb243c991 · ruled-out · Ruled out: a real Cilium outage

The alert name says "Cilium Agent Down" and 48 of them fired at once, which
reads as a datapath emergency. It is not.

Evidence against:

- `kubectl get nodes` — all 7 nodes `Ready`, no `NotReady`, no `DiskPressure`.
- `kubectl -n kube-system get deploy cilium-operator` — `2/2 READY, 2 AVAILABLE`.
- Cluster-wide sweep of every `Running` pod comparing ready-containers to
  total-containers: **zero** partially-ready pods. Every running pod on Frank is
  fully ready.
- The alerting pod names are 48 *distinct* ReplicaSet hashes from one
  ReplicaSet (`76d44bb8d`) — a live outage would re-alert on the same pod, not
  on 48 different ones.

Also note the alert name is itself misleading: the rule fires on
`cilium-operator-*` (a Deployment), not on the `cilium` agent DaemonSet.

<!-- fr:journal kind=ruled-out scope=debug id=99d12984099f created=2026-08-02T20:33:55 -->
### 99d12984099f · ruled-out · Ruled out: kube-state-metrics scrape-size blindness (the 2026-07-27 gotcha)

A prior incident (`frank-gotchas.md`, 2026-07-27) had kube-state-metrics exceed
`-promscrape.maxScrapeSize`, dropping the whole response and blinding all 25
`kube_*` alert rules. Superficially similar — a mass `kube_*` anomaly.

Refuted: that failure mode produces **NoData**, not **Alerting**. The firing set
here has only 4 rules in `Normal (NoData)`, and the 48 Cilium alerts carry fully
populated label sets scraped from a live kube-state-metrics instance
(`instance: 10.244.13.70:8080`). Series are arriving; they are just stale.

<!-- fr:journal kind=hypothesis scope=debug id=290d00fb406b created=2026-08-02T20:33:57 -->
### 290d00fb406b · hypothesis · Hypothesis: the alerting pods are graceful-node-shutdown tombstones in phase Failed

The 21 alerts the classifier *did* call `false-positive` are tombstones the
classifier recognised (`Succeeded`). The 48 it escalated might be the same class
of object in a phase the classifier does not recognise.

Prediction: `status.phase` on an alerting pod is a terminal phase that is not in
`_TERMINAL_POD_STATES`.

Test — resolve one alerting pod directly:

    kubectl -n kube-system get pod cilium-operator-76d44bb8d-rxzzp -o json

Result — **CONFIRMED**:

    phase:   Failed
    reason:  NodeShutdown
    message: Pod was rejected: Pod was rejected as the node is shutting down.
    node:    mini-1
    startTime: 2026-08-02T16:24:52Z

Across the whole set: 50 `cilium-operator` pods exist — **47 `Failed`, 2
`Running`, 1 `Succeeded`**. Cluster-wide there are 194 `Failed` pods, 47 of them
`reason: NodeShutdown` in `kube-system`.

<!-- fr:journal kind=root-cause scope=debug id=d2f1c80bd6a4 created=2026-08-02T20:33:58 -->
### d2f1c80bd6a4 · root-cause · classify.py omits Failed from _TERMINAL_POD_STATES, so node-shutdown tombstones escalate

**48 alerts escalate as `unexplained` because
`agents/skills/frank-alert-triage/classify.py` treats only `Succeeded`,
`Completed` and absent as terminal — it omits `Failed`.**

    _TERMINAL_POD_STATES = frozenset({"Succeeded", "Completed", None})

Kubernetes has **two** terminal pod phases: `Succeeded` and `Failed`. A pod in
either can never become Ready again, so its `kube_pod_status_ready` series is
stale by definition. The classifier recognises one and escalates the other.

Why it fired tonight: the Phase 6 `frank.derio.net` retirement ConfigPatch
(PR #745/#747 line of work) rolled the three control planes at ~16:2x UTC. As
each node drained, the scheduler kept placing `cilium-operator` replicas onto it
and the shutting-down kubelet **rejected** each one — `phase: Failed`,
`reason: NodeShutdown`. That rejection loop minted 47 tombstones in minutes.
Kubernetes does not garbage-collect them (`--terminated-pod-gc-threshold`
defaults to 12500), so kube-state-metrics keeps exporting a NotReady readiness
series for every one, forever.

The repo already documents this exact object in `frank-gotchas.md`
("graceful-node-shutdown TOMBSTONES ... phase `Failed`") — the gotcha file knows
about `Failed` tombstones and the classifier does not. The triage tool and the
runbook disagree, and the tool is the one that pages.

Secondary observation (NOT fixed here): `reason` also distinguishes safe-to-
delete tombstones (`NodeShutdown`, `Terminated`) from genuine failures
(`DeadlineExceeded`, 10 in `kid-laptops-ci`; 68 reasonless in
`tekton-pipelines`). The verdict is the same — a terminal pod is never Ready —
but the recommended *action* differs, so the fix carries the reason through into
the operator-facing text.

<!-- fr:journal kind=finding scope=debug id=1375797c226f created=2026-08-02T20:44:56 state=fixed -->
### 1375797c226f · finding [fixed] · Failed added to _TERMINAL_POD_STATES; pod_reason separates verdict from advice

**Source change** — `agents/skills/frank-alert-triage/classify.py`:

- `_TERMINAL_POD_STATES` gains `"Failed"`. Kubernetes has two terminal phases;
  the set now matches the API rather than half of it.
- new `_SHUTDOWN_REASONS = {"NodeShutdown", "Terminated"}`.
- `classify()` gains an optional `pod_reason` kwarg (backward compatible). It
  **never** changes the verdict — a terminal pod is stale regardless — only the
  operator one-liner: shutdown artifacts keep the "delete the terminal pod"
  advice, any other `Failed` reason instead says to KEEP the object because it is
  the failure evidence.

**Failing tests written first** (`test_classify.py`, red before / green after):

- `test_readiness_with_terminal_pod_is_false_positive` — extended to `Failed`;
  this is the pure root-cause test.
- `test_node_shutdown_tombstone_is_false_positive_not_escalated` — the 2026-08-02
  regression, pinned with the live label set.
- `test_shutdown_tombstone_recommends_deletion`
- `test_non_shutdown_failure_does_not_recommend_deletion` — guards the advice
  split (a `DeadlineExceeded` pod must not be recommended for deletion).
- `test_pod_reason_is_optional_and_backward_compatible`

Red: 4 failed / 8 passed. Green: **12 passed**.

**Live proof against the same firing set** (fixed classifier, re-resolved pods):

    before: {unexplained: 48, false-positive: 21, muted: 2, by-design: 1}
    after:  {false-positive: 69, muted: 2, by-design: 1}   # 0 unexplained

The 48 Cilium alerts now read `pod is Failed (NodeShutdown tombstone)` and the
GPU-operator one `pod is Failed (Terminated tombstone)` — matching the
independently-verified cluster state (all deploys fully available, zero
partially-ready Running pods).

**Docs** — playbook (`SKILL.md`) updated: resolve `status.reason` alongside
phase, do not read the phase off kubectl column output
(`ContainerStatusUnknown` ≠ a phase), decision-tree table split by reason, and a
note on telling a tombstone flood from an outage. Gotcha one-liner added to
`agents/rules/frank-gotchas.md` with full prose in
`docs/runbooks/frank-gotchas/grafana.md`.

Also corrected a **stale claim** in SKILL.md that `apps/alert-agent` mirrors this
decision tree and must be kept in sync: its SKILL.md is a 60-line operating brief
with no tree, and it explicitly has no kubernetes credential, so it cannot
resolve a pod phase at all.

**Regression suite**: 10 pre-existing failures (`test_cnc_staging_*`), identical
on a clean `git archive origin/main` baseline — untouched by this change. A
collected-count difference (533 vs 536) traced to PR #751 merging mid-session;
rebased onto `origin/main`, now 0 behind.

**NOT fixed (deliberately out of scope, recorded for follow-up):** the tombstones
themselves still accumulate on every node reboot. Durable options are lowering
`--terminated-pod-gc-threshold` via a Talos ConfigPatch, or moving the
feature-health rules from per-pod `kube_pod_status_ready` to
`kube_deployment_status_replicas_unavailable` — which `frank-gotchas.md` already
recommends for this false-positive class. Either is a larger change than a
triage-classifier fix and should be decided on its own merits.
