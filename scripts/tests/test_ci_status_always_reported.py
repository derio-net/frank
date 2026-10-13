"""Tripwires: a CI PipelineRun must ALWAYS leave a commit status behind.

Incident 2026-10-11 21:22Z .. 2026-10-12 07:19Z. Every CI PipelineRun's
workspace PVC (`longhorn-hdd`) failed to provision (`specified disk tag hdd
does not exist`). The `mirror` / `pull-and-push` pod sat Pending until the
PipelineRun hit Tekton's default `timeouts.pipeline: 1h`. With ONLY a pipeline
timeout, Tekton v1.6 skips `finally` once it elapses ("PipelineRun timeout has
been reached") -- so the `github-status-failure` / `gitea-status-failure`
tasks never ran and GitHub received NO `tekton/ci` status at all. 23 runs
across cnc-frd, cnc-fr, second-brain and hermes-brain were affected; PRs with
no status looked green and merged untested.

Three guards, one per layer of the fix:

1. finally gets its own budget -- every CI TriggerTemplate sets
   `timeouts.tasks` + `timeouts.finally` within `timeouts.pipeline`, so a
   tasks-timeout cancels the DAG and the failure status still posts.
2. pending first -- every CI Pipeline posts a `pending` status from a DAG
   task that binds no workspace and depends on nothing, so a run that is
   created but never reports is visibly *pending*, not absent. The post is
   best-effort (a GitHub flake must not turn a green run red).
3. alerting -- Grafana rules over signals that exist live: kube-state-metrics'
   PVC phase, and the Tekton duration histogram (its metrics carry only
   `status=success|failed`, no reason label, so a timeout is identified by a
   failed run's duration).

The CI set is DISCOVERED (TriggerTemplate -> pipelineRef -> Pipeline whose
`finally` posts a status) and pinned against an expected floor, so a new CI
pipeline inherits the guards and a broken discovery cannot pass vacuously.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import textwrap
from typing import Any

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
TRIGGER_FILES = sorted((REPO / "apps" / "tekton" / "triggers").glob("*.yaml"))
PIPELINES_DIR = REPO / "apps" / "tekton" / "pipelines"
TASKS_DIR = REPO / "apps" / "tekton" / "tasks"
ALERT_RULES_CM = REPO / "apps" / "grafana-alerting" / "manifests" / "alert-rules-cm.yaml"

STATUS_TASKS = {"github-status", "gitea-status"}

# Floor for discovery: these MUST be found. More is fine (new CI pipelines
# inherit every guard below); fewer means discovery broke.
EXPECTED_CI_PIPELINES = {"cnc-ci", "hum-ci", "content-factory-ci", "stoa-blog-ci", "gitea-ci"}

MIN_FINALLY_SECONDS = 5 * 60

PVC_PENDING_UID = "layer-25-ci-workspace-pvc-pending"
LONG_FAILURE_UID = "layer-25-pipelinerun-timeout"
OUTCOMES_GROUP = "layer-25-pipeline-outcomes"


# --------------------------------------------------------------------------- helpers


def _docs(path: pathlib.Path) -> list[dict[str, Any]]:
    return [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]


def _pipelines() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(PIPELINES_DIR.glob("*.yaml")):
        for doc in _docs(path):
            if doc.get("kind") == "Pipeline":
                out[doc["metadata"]["name"]] = doc
    return out


def _task_ref_name(pt: dict[str, Any]) -> str | None:
    return (pt.get("taskRef") or {}).get("name")


def _status_finally(pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in pipeline["spec"].get("finally", []) if _task_ref_name(t) in STATUS_TASKS]


def _ci_runs() -> list[tuple[str, str, dict[str, Any]]]:
    """(template name, pipeline name, PipelineRun spec) for every TriggerTemplate
    resourcetemplate whose in-repo Pipeline posts a commit status in `finally`."""
    pipelines = _pipelines()
    runs = []
    for path in TRIGGER_FILES:
        for doc in _docs(path):
            if doc.get("kind") != "TriggerTemplate":
                continue
            for rt in doc["spec"].get("resourcetemplates", []):
                if rt.get("kind") != "PipelineRun":
                    continue
                name = (rt["spec"].get("pipelineRef") or {}).get("name")
                if name in pipelines and _status_finally(pipelines[name]):
                    runs.append((doc["metadata"]["name"], name, rt["spec"]))
    return runs


def _seconds(duration: str) -> int:
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", str(duration))
    assert m and any(m.groups()), f"unparseable Tekton duration {duration!r}"
    h, mi, s = (int(g or 0) for g in m.groups())
    return h * 3600 + mi * 60 + s


def _params(pt: dict[str, Any]) -> dict[str, Any]:
    return {p["name"]: p.get("value") for p in pt.get("params", [])}


# --------------------------------------------------------------------------- discovery


def test_discovery_finds_every_ci_pipeline():
    found = {pipeline for _, pipeline, _ in _ci_runs()}
    missing = EXPECTED_CI_PIPELINES - found
    assert not missing, (
        f"CI discovery lost {sorted(missing)} -- every guard below would pass "
        f"vacuously for it. Found: {sorted(found)}"
    )


# --------------------------------------------------------------------------- 1. finally budget


@pytest.mark.parametrize("template,pipeline,spec", _ci_runs(), ids=lambda v: v if isinstance(v, str) else "")
def test_ci_runs_give_finally_its_own_budget(template, pipeline, spec):
    """With only `timeouts.pipeline`, Tekton skips `finally` when it elapses --
    the 2026-10-11 silent-CI incident. `tasks` must leave `finally` a window."""
    timeouts = spec.get("timeouts") or {}
    for key in ("pipeline", "tasks", "finally"):
        assert key in timeouts, (
            f"{template} (pipeline {pipeline}) sets no timeouts.{key}: {timeouts!r}. "
            "Without tasks < pipeline, a pipeline timeout cancels finally and the "
            "failure status is never posted."
        )
    total, tasks, fin = (_seconds(timeouts[k]) for k in ("pipeline", "tasks", "finally"))
    assert tasks + fin <= total, f"{template}: tasks+finally ({tasks + fin}s) exceeds pipeline ({total}s)"
    assert tasks < total, f"{template}: timeouts.tasks must be strictly below timeouts.pipeline"
    assert fin >= MIN_FINALLY_SECONDS, f"{template}: finally budget {fin}s < {MIN_FINALLY_SECONDS}s"


# --------------------------------------------------------------------------- status tasks


@pytest.mark.parametrize("task", sorted(STATUS_TASKS))
def test_status_tasks_bind_no_workspace(task):
    """The status posts must schedule even when the workspace PVC cannot."""
    doc = _docs(TASKS_DIR / f"{task}.yaml")[0]
    assert not doc["spec"].get("workspaces"), f"{task} declares workspaces; it must not need the PVC"
    for name, pipeline in _pipelines().items():
        for pt in pipeline["spec"].get("tasks", []) + pipeline["spec"].get("finally", []):
            if _task_ref_name(pt) == task:
                assert not pt.get("workspaces"), f"{name}/{pt['name']} binds a workspace to {task}"


# --------------------------------------------------------------------------- 2. pending first


def _pending_tasks(pipeline: dict[str, Any], task: str) -> list[dict[str, Any]]:
    return [
        pt
        for pt in pipeline["spec"].get("tasks", [])
        if _task_ref_name(pt) == task and _params(pt).get("state") == "pending"
    ]


@pytest.mark.parametrize("pipeline_name", sorted({p for _, p, _ in _ci_runs()}))
def test_ci_pipelines_post_pending_first(pipeline_name):
    pipeline = _pipelines()[pipeline_name]
    finally_tasks = _status_finally(pipeline)
    primary = "github-status" if any(_task_ref_name(t) == "github-status" for t in finally_tasks) else "gitea-status"

    pending = _pending_tasks(pipeline, primary)
    assert len(pending) == 1, (
        f"{pipeline_name} must post exactly one `pending` {primary} from a DAG task "
        f"before anything else, found {len(pending)}"
    )
    pt = pending[0]
    assert not pt.get("runAfter"), f"{pipeline_name}/{pt['name']} must not wait on any task (runAfter)"
    assert not pt.get("workspaces"), f"{pipeline_name}/{pt['name']} must not bind the workspace PVC"
    assert _params(pt).get("best-effort") == "true", (
        f"{pipeline_name}/{pt['name']} must pass best-effort: \"true\" -- a failed "
        "pending post must not fail an otherwise green run"
    )
    final_ctx = {_params(t).get("context") for t in finally_tasks if _task_ref_name(t) == primary}
    assert _params(pt).get("context") in final_ctx, (
        f"{pipeline_name}/{pt['name']} context {_params(pt).get('context')!r} must match "
        f"the finally context(s) {final_ctx!r}, or the pending status is never superseded"
    )

    # Dual-status pipelines mirror the pending to Gitea too (best-effort).
    if primary == "github-status" and any(_task_ref_name(t) == "gitea-status" for t in finally_tasks):
        gp = _pending_tasks(pipeline, "gitea-status")
        assert len(gp) == 1, f"{pipeline_name} must also post a best-effort pending gitea-status"
        assert _params(gp[0]).get("best-effort") == "true"
        assert not gp[0].get("workspaces")


# --------------------------------------------------------------------------- best-effort executes


def _script(task: str) -> str:
    doc = _docs(TASKS_DIR / f"{task}.yaml")[0]
    report = next(s for s in doc["spec"]["steps"] if s["name"] == "report")
    return report["args"][0]


def _run(tmp_path: pathlib.Path, task: str, code: str, best_effort: str | None) -> subprocess.CompletedProcess:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "curl"
    stub.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            out=""
            while [ $# -gt 0 ]; do
              case "$1" in -o) out="$2"; shift 2 ;; *) shift ;; esac
            done
            [ -n "$out" ] && [ "$out" != /dev/null ] && echo '{{"message":"boom"}}' > "$out"
            printf '%s' {code!r}
            """
        )
    )
    stub.chmod(0o755)
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bindir}:{env['PATH']}",
            "GITHUB_TOKEN": "stub",
            "GITEA_TOKEN": "stub",
            "REPO_FULL_NAME": "agentic-stoa/cnc-frd",
            "REVISION": "0" * 40,
            "STATE": "pending",
            "DESCRIPTION": "CI running",
            "CONTEXT": "tekton/ci",
            "TARGET_URL": "",
            "GITHUB_API_URL": "https://api.github.com",
            "GITEA_URL": "http://gitea",
        }
    )
    if best_effort is not None:
        env["BEST_EFFORT"] = best_effort
    return subprocess.run(["/bin/sh", "-e", "-c", _script(task)], env=env, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("task", sorted(STATUS_TASKS))
def test_best_effort_post_tolerates_api_errors_loudly(tmp_path, task):
    result = _run(tmp_path, task, "500", "true")
    assert result.returncode == 0, f"{task} best-effort post failed the step:\n{result.stdout}{result.stderr}"
    assert "best-effort" in (result.stdout + result.stderr).lower(), f"{task} swallowed the error silently"


@pytest.mark.parametrize("task", sorted(STATUS_TASKS))
@pytest.mark.parametrize("best_effort", [None, "false"])
def test_mandatory_post_still_fails_on_api_errors(tmp_path, task, best_effort):
    result = _run(tmp_path, task, "500", best_effort)
    assert result.returncode != 0, f"{task} swallowed HTTP 500 without best-effort"


# --------------------------------------------------------------------------- 3. alerting


def _rules() -> dict[str, dict[str, Any]]:
    cm = yaml.safe_load(ALERT_RULES_CM.read_text(encoding="utf-8"))
    doc = yaml.safe_load(cm["data"]["alert-rules.yaml"])
    out = {}
    for group in doc.get("groups", []):
        for rule in group.get("rules", []):
            out[rule["uid"]] = dict(rule, _group=group.get("name"))
    return out


def _expr(rule: dict[str, Any]) -> str:
    return next(d["model"]["expr"] for d in rule["data"] if d["refId"] == "A")


@pytest.mark.parametrize("uid", [PVC_PENDING_UID, LONG_FAILURE_UID])
def test_ci_silence_alerts_exist_and_route(uid):
    rules = _rules()
    assert uid in rules, f"alert rule {uid!r} missing from {ALERT_RULES_CM}"
    rule = rules[uid]
    assert rule["_group"] == OUTCOMES_GROUP
    assert rule["labels"]["severity"] == "warning"
    assert rule["labels"]["github_issue"] == "frank-ops#25"
    assert rule.get("noDataState") == "OK" and rule.get("execErrState")


def test_pvc_pending_alert_watches_ci_workspaces_by_age():
    expr = _expr(_rules()[PVC_PENDING_UID])
    for needle in (
        "kube_persistentvolumeclaim_status_phase",
        'phase="Pending"',
        'namespace="tekton-pipelines"',
        "kube_persistentvolumeclaim_created",
    ):
        assert needle in expr, f"{PVC_PENDING_UID} expr lacks {needle!r}: {expr!r}"


def test_long_failure_alert_catches_a_tasks_timeout():
    """A run cancelled at timeouts.tasks has duration ~= timeouts.tasks, so the
    `le` bucket the rule subtracts must sit BELOW the shortest tasks budget, or
    the post-fix timeout would land inside the bucket and never count."""
    expr = _expr(_rules()[LONG_FAILURE_UID])
    assert 'status="failed"' in expr and "_bucket{" in expr, expr
    m = re.search(r'le="(\d+)"', expr)
    assert m, f"{LONG_FAILURE_UID} must subtract a fixed le bucket: {expr!r}"
    le = int(m.group(1))
    shortest = min(_seconds(spec["timeouts"]["tasks"]) for _, _, spec in _ci_runs() if spec.get("timeouts"))
    assert le < shortest, f"le={le}s must be below the shortest timeouts.tasks ({shortest}s)"
