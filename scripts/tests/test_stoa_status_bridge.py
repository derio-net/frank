"""Guard: the Gitea→GitHub status bridge is wired and filtered correctly.

Gitea Actions writes commit statuses on the mirror; Gitea's `status` webhook
event carries them to the gitea-listener, and the stoa-status-bridge pipeline
forwards them to GitHub via the existing github-status Task. The sha is
identical on both sides by construction (mirror), so no mapping is needed.

The filters are the load-bearing part:
- only agentic-stoa mirrors are forwarded;
- Tekton's own dual-status writes (context tekton/*) are dropped — GitHub
  already receives those directly from github-status; forwarding them again
  would double-post every Tekton CI result.

Plan: docs/superpowers/plans/2026-07-19-cicd-stoa-mirror-gitea-actions
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
EL_GITEA = REPO_ROOT / "apps/tekton/triggers/eventlistener.yaml"
BRIDGE_PIPELINE = REPO_ROOT / "apps/tekton/pipelines/stoa-status-bridge.yaml"

BRIDGE_PARAMS = {
    "repo-full-name",
    "revision",
    "state",
    "context",
    "description",
    "target-url",
}


def _gitea_docs():
    return [d for d in yaml.safe_load_all(EL_GITEA.read_text()) if d]


def _bridge_trigger():
    for doc in _gitea_docs():
        if doc.get("kind") == "EventListener":
            for trig in doc["spec"]["triggers"]:
                if trig.get("name") == "gitea-status-bridge":
                    return trig
    return None


def test_bridge_trigger_filter():
    trig = _bridge_trigger()
    assert trig is not None, "gitea-status-bridge trigger missing"

    filters = []
    for interceptor in trig.get("interceptors", []):
        if interceptor.get("ref", {}).get("name") == "cel":
            for p in interceptor.get("params", []):
                if p["name"] == "filter":
                    filters.append(p["value"])
    filt = " && ".join(filters)

    assert "X-Gitea-Event" in filt and "'status'" in filt
    # Explicit repo list since the three-org widening (guarded against
    # mirror-reconcile MAIN_REPOS in test_ci_mirror_resilience.py).
    assert "body.repository.full_name in [" in filt and "'agentic-stoa/hum'" in filt
    assert "!body.context.startsWith('tekton')" in filt

    assert trig["template"]["ref"] == "stoa-status-bridge-template"


def test_bridge_template_and_bindings():
    trig = _bridge_trigger()
    assert trig is not None

    bindings = {b["name"]: b["value"] for b in trig.get("bindings", [])}
    assert bindings["repo-full-name"] == "$(body.repository.full_name)"
    assert bindings["revision"] == "$(body.sha)"
    # NOT $(body.state) — Gitea's vocabulary is a superset of GitHub's and
    # must be narrowed first (see test_bridge_maps_gitea_only_states)
    assert bindings["state"] == "$(extensions.gh_state)"
    assert bindings["context"] == "$(body.context)"

    # description/target_url are omitempty in Gitea's status payload — they
    # must come through has()-guarded overlays, not direct body bindings
    # (a missing field in a direct binding silently drops the event)
    assert bindings["description"] == "$(extensions.description)"
    assert bindings["target-url"] == "$(extensions.target_url)"
    overlays = {}
    for interceptor in trig.get("interceptors", []):
        for p in interceptor.get("params", []):
            if p["name"] == "overlays":
                overlays.update({o["key"]: o["expression"] for o in p["value"]})
    assert overlays["target_url"] == "has(body.target_url) ? body.target_url : ''"

    templates = [
        d
        for d in _gitea_docs()
        if d.get("kind") == "TriggerTemplate"
        and d["metadata"]["name"] == "stoa-status-bridge-template"
    ]
    assert templates, "stoa-status-bridge-template missing"
    tmpl = templates[0]
    assert {p["name"] for p in tmpl["spec"]["params"]} == BRIDGE_PARAMS

    run = tmpl["spec"]["resourcetemplates"][0]
    assert run["kind"] == "PipelineRun"
    assert run["spec"]["pipelineRef"]["name"] == "stoa-status-bridge"


def _bridge_overlays():
    overlays = {}
    for interceptor in _bridge_trigger().get("interceptors", []):
        for p in interceptor.get("params", []):
            if p["name"] == "overlays":
                overlays.update({o["key"]: o["expression"] for o in p["value"]})
    return overlays


def test_bridge_maps_gitea_only_states():
    """Gitea's CommitStatusState is a SUPERSET of GitHub's.

    GitHub's status API accepts exactly pending|success|error|failure. Gitea
    adds `skipped` and `warning`. Posting either verbatim returns 422
    ("State is not included in the list"), github-status exits non-zero, and
    — because a commit status has no lifecycle of its own — the GitHub status
    stays stuck on the `pending` written when the job was queued. Forever.

    Incident 2026-07-22: the CI_AUTHORITY guard PRs made every Gitea job skip
    (correct: CI_AUTHORITY=github during parallel running), 30 bridge
    PipelineRuns failed on `skipped`, and 4 PRs showed permanently pending
    gitea-actions/* checks that no rerun could clear.

    Both Gitea-only states mean "not a failure", so both map to `success`
    with the real state preserved in the description. Everything already in
    GitHub's vocabulary passes through untouched.
    """
    expr = _bridge_overlays().get("gh_state")
    assert expr, "gh_state overlay missing — raw Gitea states would 422"

    for gitea_only in ("skipped", "warning"):
        assert f"'{gitea_only}'" in expr, (
            f"Gitea-only state {gitea_only!r} not narrowed to GitHub's "
            f"vocabulary — it would 422 and strand the status: {expr}"
        )
    assert "'success'" in expr
    # non-Gitea-only states must still pass through unmapped
    assert "body.state" in expr.split("?", 1)[1]

    desc = _bridge_overlays().get("description")
    assert desc and "body.state" in desc, (
        "description must surface the real Gitea state, or a skipped job "
        f"reads as a genuine green check on GitHub: {desc}"
    )


def test_bridge_pipeline_forwards_via_github_status():
    docs = [d for d in yaml.safe_load_all(BRIDGE_PIPELINE.read_text()) if d]
    pipelines = [d for d in docs if d["kind"] == "Pipeline"]
    assert len(pipelines) == 1
    spec = pipelines[0]["spec"]

    assert {p["name"] for p in spec["params"]} == BRIDGE_PARAMS

    tasks = {t["name"]: t for t in spec["tasks"]}
    assert set(tasks) == {"current-state", "forward"}
    forward = tasks["forward"]
    assert forward["taskRef"]["name"] == "github-status"

    params = {p["name"]: p["value"] for p in forward["params"]}
    # gitea-actions/ prefix distinguishes Frank results from native GH checks
    assert params["context"] == "gitea-actions/$(params.context)"
    assert params["revision"] == "$(params.revision)"
    assert params["state"] == "$(params.state)"
    assert params["repo-full-name"] == "$(params.repo-full-name)"


# ── Ordering guard ────────────────────────────────────────────────────────
# One PipelineRun per Gitea status event, and nothing orders them. For a
# skipped job Gitea emits `pending` then the terminal state ~2s apart; on
# 2026-10-23 (derio-homelab/homelab PR #40, f227d20) the pending run was
# created at 20:18:45 and the skipped->success run at 20:18:47, both finished
# at 20:18:52, and the stale `pending` POSTed LAST. GitHub treats the newest
# status as current, so the check read pending forever and
# layer-25-delivery-overdue (kind=status) fired.


def _bridge_tasks():
    docs = [d for d in yaml.safe_load_all(BRIDGE_PIPELINE.read_text()) if d]
    return {t["name"]: t for t in docs[0]["spec"]["tasks"]}


def _guard():
    import types

    script = _bridge_tasks()["current-state"]["taskSpec"]["steps"][0]["script"]
    module = types.ModuleType("bridge_guard")
    exec(compile(script, str(BRIDGE_PIPELINE), "exec"), module.__dict__)
    return module


def _combined(*statuses):
    return lambda: {"statuses": [{"context": c, "status": s} for c, s in statuses]}


CTX = "acceptance-report / matrix (push)"


def test_forward_is_gated_on_the_guard():
    tasks = _bridge_tasks()
    forward = tasks["forward"]
    assert forward.get("runAfter") == ["current-state"]
    assert {"input": "$(tasks.current-state.results.superseded)",
            "operator": "notin", "values": ["true"]} in forward.get("when", [])
    # The guard must run for EVERY event: a task consuming a result of a
    # SKIPPED task is itself skipped, so a `when: state in [pending]` on the
    # guard would silently stop every terminal status from being forwarded.
    assert "when" not in tasks["current-state"]


def test_stale_pending_is_dropped_once_gitea_has_moved_on():
    # The 2026-10-23 incident: Gitea already holds the terminal state.
    assert _guard().superseded("pending", CTX, _combined((CTX, "skipped"))) is True
    assert _guard().superseded("pending", CTX, _combined((CTX, "success"))) is True


def test_current_pending_is_forwarded():
    # Normal queueing and re-runs: pending IS Gitea's current state.
    assert _guard().superseded("pending", CTX, _combined((CTX, "pending"))) is False
    # Another context's terminal state says nothing about this one.
    assert _guard().superseded("pending", CTX, _combined(("other (push)", "success"))) is False


def test_terminal_states_are_never_suppressed():
    def boom():
        raise AssertionError("terminal events must not read Gitea")

    for state in ("success", "failure", "error"):
        assert _guard().superseded(state, CTX, boom) is False


def test_guard_fails_open():
    # A Gitea read error must not swallow a status: forward as before.
    def unreachable():
        raise OSError("gitea down")

    assert _guard().superseded("pending", CTX, unreachable) is False
    assert _guard().superseded("pending", CTX, lambda: {"message": "not found"}) is False
