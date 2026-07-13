"""Decision-tree coverage for classify() — one case per branch, using the real
Grafana alert label shapes captured during a live Frank triage (2026-07-13)."""
from classify import classify, Verdict


# Real labels from the live firing set this session.
_CANARY = {
    "alertname": "TLS cert expiring within 7 days",
    "canary": "true",
    "instance": "https://expired.badssl.com/",
    "severity": "critical",
}
_GPU_TIMESHARE = {
    "__name__": "probe_success",
    "alertname": "Layer 11 Local Inference Degraded",
    "gpu_timeshare": "true",
    "github_issue": "frank-ops#11",
    "layer": "11",
    "severity": "warning",
}
_READINESS = {
    "__name__": "kube_pod_status_ready",
    "condition": "true",
    "alertname": "Layer 3 Cilium Agent Down",
    "github_issue": "frank-ops#3",
    "namespace": "kube-system",
    "pod": "cilium-operator-76d44bb8d-87tmm",
    "severity": "warning",
}


def test_canary_is_muted():
    v = classify(_CANARY, pod_state=None)
    assert v.kind == "muted"


def test_gpu_timeshare_is_by_design():
    v = classify(_GPU_TIMESHARE, pod_state=None)
    assert v.kind == "by-design"
    assert "gpu-node-both-down" in v.reason   # names the real pager


def test_readiness_with_terminal_pod_is_false_positive():
    # A Succeeded/Completed/absent pod behind a readiness rule = stale KSM series.
    for state in ("Succeeded", "Completed", None):
        v = classify(_READINESS, pod_state=state)
        assert v.kind == "false-positive", f"pod_state={state!r}"


def test_readiness_with_live_pod_is_not_false_positive():
    # A genuinely Running-but-NotReady pod is a REAL degradation → escalate,
    # AND the tracker is still captured (orthogonality holds on the escalate path).
    v = classify(_READINESS, pod_state="Running")
    assert v.kind == "unexplained"
    assert v.tracker == "frank-ops#3"


def test_readiness_with_unresolved_pod_escalates_not_false_positive():
    # The driver passes a non-terminal sentinel when kubectl fails to resolve —
    # it must NOT be swallowed as a benign tombstone (fail-safe = escalate).
    v = classify(_READINESS, pod_state="unresolved")
    assert v.kind == "unexplained"


def test_github_issue_is_captured_as_tracker_annotation():
    # tracker is orthogonal to kind — captured whenever the label is present,
    # even on a false-positive.
    v = classify(_READINESS, pod_state="Succeeded")
    assert v.kind == "false-positive"
    assert v.tracker == "frank-ops#3"


def test_unexplained_when_no_pattern_matches():
    v = classify({"alertname": "Something New", "severity": "warning"}, pod_state=None)
    assert v.kind == "unexplained"
    assert v.tracker is None


def test_verdict_is_immutable_shape():
    v = classify(_CANARY, pod_state=None)
    assert isinstance(v, Verdict)
    assert v.reason  # every verdict carries a human one-liner
