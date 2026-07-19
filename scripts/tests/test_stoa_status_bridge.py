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
    assert "body.repository.full_name.startsWith('agentic-stoa/')" in filt
    assert "!body.context.startsWith('tekton')" in filt

    assert trig["template"]["ref"] == "stoa-status-bridge-template"


def test_bridge_template_and_bindings():
    trig = _bridge_trigger()
    assert trig is not None

    bindings = {b["name"]: b["value"] for b in trig.get("bindings", [])}
    assert bindings["repo-full-name"] == "$(body.repository.full_name)"
    assert bindings["revision"] == "$(body.sha)"
    assert bindings["state"] == "$(body.state)"
    assert bindings["context"] == "$(body.context)"

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


def test_bridge_pipeline_forwards_via_github_status():
    docs = [d for d in yaml.safe_load_all(BRIDGE_PIPELINE.read_text()) if d]
    pipelines = [d for d in docs if d["kind"] == "Pipeline"]
    assert len(pipelines) == 1
    spec = pipelines[0]["spec"]

    assert {p["name"] for p in spec["params"]} == BRIDGE_PARAMS

    tasks = spec["tasks"]
    assert len(tasks) == 1
    forward = tasks[0]
    assert forward["taskRef"]["name"] == "github-status"

    params = {p["name"]: p["value"] for p in forward["params"]}
    # gitea-actions/ prefix distinguishes Frank results from native GH checks
    assert params["context"] == "gitea-actions/$(params.context)"
    assert params["revision"] == "$(params.revision)"
    assert params["state"] == "$(params.state)"
    assert params["repo-full-name"] == "$(params.repo-full-name)"
