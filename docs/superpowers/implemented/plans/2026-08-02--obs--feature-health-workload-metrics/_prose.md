# Feature-health alerts on workload availability, not per-pod readiness

**Status:** In Progress
**Layer:** obs
**Spec:** `docs/superpowers/specs/2026-08-02--obs--feature-health-workload-metrics-design.md`

## Why

On 2026-08-02 a control-plane rolling reboot produced 48 firing Grafana alerts
against a completely healthy cluster. The draining kubelet rejected
`cilium-operator` replicas the scheduler was still placing on it, leaving 47
pods in `phase: Failed, reason: NodeShutdown`. Kubernetes does not garbage
collect terminal pods below a threshold of 12500, so kube-state-metrics kept
exporting a NotReady `kube_pod_status_ready` series for every one of them —
forever.

PR #752 fixed the *triage* of that class. This plan fixes the *source*: eleven
feature-health rules ask "is this pod ready?" when they mean "is this capability
being served?" Those questions diverge precisely when pods are cattle.

A further 21 `Succeeded` tombstones from earlier reboots had been firing
unnoticed underneath, so the standing baseline was 25 permanently-firing alerts
rather than the true 3. The noise had become the background.

## Approach

Rewrite each rule onto workload-level availability, keeping every routing-
relevant field untouched. `agents/rules/frank-gotchas.md` already recommends
this, and **Layer 25 was migrated the same way on 2026-05-14** — this finishes a
job the repo started.

Three workload kinds appear across the eleven namespaces, so there is no single
drop-in metric:

| kind | metric |
|---|---|
| Deployment | `kube_deployment_status_replicas_unavailable` |
| DaemonSet | `kube_daemonset_status_number_unavailable` |
| StatefulSet | `kube_statefulset_status_replicas` − `kube_statefulset_status_replicas_ready` |

Nested `label_replace` folds `deployment`/`daemonset`/`statefulset` into a
common `workload` label plus a lowercase `kind`, so summaries and runbooks stay
specific and interpolate directly into a kubectl resource path.

## Phase shape

Phases 2 and 3 both edit the same 2000-line ConfigMap, so they are strictly
serial — parallelising them would guarantee a conflict for no wall-clock gain.

1. **Tripwire harness** — assert the defect exists, lock the properties the
   rewrite must not break. The regression test is marked `xfail(strict=True)`
   so the suite stays green now and **fails on xpass** the moment phase 3
   completes, forcing its removal rather than leaving a dead guard behind.
2. **8 non-DaemonSet rules**, `for: 5m`.
3. **3 DaemonSet-bearing rules**, `for: 15m`, then retire the xfail.
4. **New scale-to-0 rule**, exclusion set derived in CI.
5. **Docs** — gotcha one-liner, runbook prose.
6. **[manual]** Grafana pod restart and live verification, post-merge.

## The two traps this plan is built around

**The threshold inverts.** `lt 1` on a readiness gauge becomes `gt 0` on an
unavailability counter. Backwards, the rule fires constantly or never — and
both failure modes look plausible in review. Phase 2 asserts the evaluator
shape explicitly for exactly this reason.

**A Deployment at 0 replicas is usually healthy.** Two independent mechanisms
put Frank Deployments at 0 by design: the gpu-switcher timeshare
(`ollama`, `comfyui`) and Argo Rollouts with `workloadRef.scaleDown: onsuccess`
(`litellm`, currently serving 5/5 through its Rollout). An earlier draft of the
spec got this wrong in both directions — it cited a ClusterRole that carries no
namespaces, and assumed `litellm` was GPU-timeshared. A naive
`spec_replicas == 0` rule would have paged for the healthy LiteLLM gateway on
day one.

Phase 4's guard therefore **derives** the exclusion set from both declarative
sources rather than restating it, so adding a third timeshared workload or a
second `scaleDown: onsuccess` Rollout fails CI instead of paging at 03:00.

## Verification posture

Offline tripwires are blocking (CI runs `scripts/tests/` via
`.github/workflows/repo-tripwires.yml`). Every rewritten expression is
additionally checked against live VictoriaMetrics during implementation,
because **a rule that parses is not a rule that returns data** — a typo'd metric
name yields NoData, which reads exactly like "nothing is wrong".

The final live verification is post-merge and operator-driven: Grafana reads
file-provisioned rules at boot and does not watch them, so ArgoCD showing
`Synced/Healthy` proves the ConfigMap changed and says nothing about what
Grafana is evaluating.
