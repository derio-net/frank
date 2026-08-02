"""Pure, stdlib-only classifier for Frank Grafana alerts.

`classify(labels, pod_state)` maps one firing alert's label set (+ the caller-
resolved pod phase, when the alert is readiness-based) to a `Verdict`. It never
touches the cluster or the network — the SKILL.md playbook does the Grafana-API
fetch and the `kubectl` pod-state resolution, then calls this. That keeps the
decision tree deterministically unit-testable.

The tree, in priority order (first match wins):

1. `canary: true`          → **muted**          — a deliberately-firing canary
   (e.g. the expired-cert canary, issue #251); never paged.
2. `gpu_timeshare: true`   → **by-design**      — gpu-1 hosts one of Ollama/
   ComfyUI at a time, so one feature-health probe is always down by design; the
   only real pager is `gpu-node-both-down`.
3. readiness rule (`__name__ == kube_pod_status_ready`) AND the referenced pod
   is terminal/absent (`Succeeded`/`Completed`/`Failed`/None) → **false-positive**
   — a stale kube-state-metrics series held by a terminated pod. The pod's
   `status.reason` does not change the verdict, only the recommended action.
4. otherwise                → **unexplained**    — no known-benign pattern; escalate.

`github_issue` is captured into `Verdict.tracker` as an ORTHOGONAL annotation,
never a verdict: the label only says "this alert type has a tracker", not that
the current firing is benign (a genuinely Running-but-NotReady pod carries the
same label and must still escalate).
"""
from __future__ import annotations

from dataclasses import dataclass

# A pod that is gone, or reported terminal, cannot be "NotReady" in any
# meaningful sense — the readiness alert is holding a stale metric series.
# `None` here means the caller RESOLVED the pod as absent (a genuine tombstone),
# never "pod resolution failed" — the driver must map a kubectl error to a
# non-terminal sentinel so a real NotReady pod is not suppressed as benign.
#
# Kubernetes has TWO terminal phases, `Succeeded` and `Failed`; a pod in either
# will never transition back to Ready, so its readiness series is stale in both
# cases. `Failed` was originally missing here, so graceful-node-shutdown
# tombstones escalated as `unexplained` — 48 of them during the 2026-08-02
# control-plane roll, against a completely healthy cluster. `Completed` is not an
# API phase but kubectl's *display* string; it is kept so a caller that scraped
# column output rather than `status.phase` still classifies correctly.
_TERMINAL_POD_STATES = frozenset({"Succeeded", "Completed", "Failed", None})

# `status.reason` values meaning the pod was killed by node lifecycle rather than
# by anything it did: `NodeShutdown` (rejected before it ever started, because the
# kubelet was already draining) and `Terminated` (killed mid-run by the same
# shutdown). These objects hold no diagnostic value, so deleting them is the safe
# cleanup. Any OTHER Failed reason — a timed-out CI job, an application crash —
# is still terminal, so the readiness series is still stale and the verdict is
# unchanged; but that pod object IS the failure evidence, and telling the operator
# to delete it would destroy the only record of why it failed.
_SHUTDOWN_REASONS = frozenset({"NodeShutdown", "Terminated"})

_READINESS_METRIC = "kube_pod_status_ready"


@dataclass(frozen=True)
class Verdict:
    """One alert's classification. `kind` drives the triage; `reason` is the
    operator one-liner; `tracker` is the linked issue when the alert carries one."""

    kind: str            # muted | by-design | false-positive | unexplained
    reason: str
    tracker: str | None = None


def _is_readiness_rule(labels: dict) -> bool:
    return labels.get("__name__") == _READINESS_METRIC


def classify(
    labels: dict,
    pod_state: str | None = None,
    pod_reason: str | None = None,
) -> Verdict:
    """Classify one firing alert. `pod_state` is the live pod phase the caller
    resolved for readiness-based alerts (None when absent / not applicable).
    `pod_reason` is that pod's `status.reason`; it never changes the verdict, only
    whether the operator one-liner recommends deleting the pod. Optional, so
    callers predating it keep working."""
    tracker = labels.get("github_issue")

    if labels.get("canary") == "true":
        return Verdict("muted", "canary — expected, never paged (e.g. cert-expiry #251)", tracker)

    if labels.get("gpu_timeshare") == "true":
        return Verdict(
            "by-design",
            "GPU timeshared — one workload is down by design; the real pager is "
            "gpu-node-both-down only",
            tracker,
        )

    if _is_readiness_rule(labels) and pod_state in _TERMINAL_POD_STATES:
        where = pod_state or "absent"
        # Absent and Succeeded/Completed pods are shutdown artifacts by nature; a
        # Failed pod only is when its reason says node lifecycle killed it.
        is_shutdown_artifact = (
            pod_state != "Failed" or pod_reason in _SHUTDOWN_REASONS
        )
        if is_shutdown_artifact:
            detail = (
                f"({pod_reason} tombstone); delete the terminal pod to clear it"
                if pod_reason
                else "(graceful-shutdown tombstone); delete the terminal pod to clear it"
            )
        else:
            detail = (
                f"(terminated: {pod_reason or 'unknown reason'}) — pod is terminal so "
                "the series is stale, but KEEP the object: it is the failure evidence"
            )
        return Verdict(
            "false-positive",
            f"stale kube-state-metrics readiness series — pod is {where} {detail}",
            tracker,
        )

    esc = "no known-benign pattern matched — escalate"
    if tracker:
        esc += f" (tracked at {tracker})"
    return Verdict("unexplained", esc, tracker)
