"""Guard: the agentic-stoa mirror trigger set is complete.

All 10 private agentic-stoa repos must be in the main-sync CEL filter, and the
two workflow-bearing repos added by the 2026-07-19 Gitea Actions plan
(second-brain, hermes-brain) must have PR-time mirror-sync triggers so Gitea
Actions can fire on sync-pr-N branches. flexible-health has no workflows and
deliberately gets main-sync only.

Plan: docs/superpowers/plans/2026-07-19-cicd-stoa-mirror-gitea-actions
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
EL_GITHUB = REPO_ROOT / "apps/tekton/triggers/eventlistener-github.yaml"

ALL_PRIVATE_REPOS = [
    "hum",
    "content-factory",
    "stoa-blog",
    "companies",
    "cnc-fr",
    "cnc-frd",
    "cnc-fru",
    "second-brain",
    "hermes-brain",
    "flexible-health",
]

# repos whose PR CI runs as Gitea Actions on the mirror (mirror-sync trigger
# only — no bespoke Tekton CI template, unlike the Phase-4-era repos)
GITEA_ACTIONS_PR_REPOS = ["second-brain", "hermes-brain"]


def _docs():
    return list(yaml.safe_load_all(EL_GITHUB.read_text()))


def _github_listener():
    for doc in _docs():
        if (
            doc
            and doc.get("kind") == "EventListener"
            and doc["metadata"]["name"] == "github-listener"
        ):
            return doc
    raise AssertionError("github-listener EventListener not found")


def _trigger(name):
    for trig in _github_listener()["spec"]["triggers"]:
        if trig.get("name") == name:
            return trig
    return None


def _cel_params(trig):
    params = {}
    for interceptor in trig.get("interceptors", []):
        if interceptor.get("ref", {}).get("name") == "cel":
            for p in interceptor.get("params", []):
                params[p["name"]] = p["value"]
    return params


def test_main_sync_covers_all_private_repos():
    trig = _trigger("agentic-stoa-main-sync")
    assert trig is not None, "agentic-stoa-main-sync trigger missing"
    filt = _cel_params(trig)["filter"]
    for repo in ALL_PRIVATE_REPOS:
        assert f"agentic-stoa/{repo}" in filt, (
            f"main-sync filter missing agentic-stoa/{repo}"
        )


def test_pr_mirror_sync_triggers_for_gitea_actions_repos():
    for repo in GITEA_ACTIONS_PR_REPOS:
        trig = _trigger(f"agentic-stoa-{repo}-pr")
        assert trig is not None, f"PR trigger for {repo} missing"

        # fires on pull_request events, filtered to the repo + PR lifecycle
        cel = _cel_params(trig)
        assert f"agentic-stoa/{repo}" in cel["filter"]
        assert "'opened', 'synchronize', 'reopened'" in cel["filter"]

        # overlays produce the synthetic sync-pr-N destination branch
        overlays = {o["key"]: o["expression"] for o in cel["overlays"]}
        assert overlays["sha"] == "body.pull_request.head.sha"
        assert "'refs/heads/sync-pr-' + string(body.pull_request.number)" in (
            overlays["ref_to"]
        )

        # mirror-only sync: bound to the shared main-sync template (which runs
        # github-pull-sync), NOT a bespoke <repo>-ci template — Gitea Actions
        # provides the CI body for these repos.
        assert trig["template"]["ref"] == "agentic-stoa-main-sync-template"

        # no Tekton test body params
        binding_names = {b["name"] for b in trig.get("bindings", [])}
        assert "test-image" not in binding_names
        assert "test-command" not in binding_names


def test_flexible_health_has_no_pr_trigger():
    assert _trigger("agentic-stoa-flexible-health-pr") is None, (
        "flexible-health has no workflows — main-sync only by design"
    )
