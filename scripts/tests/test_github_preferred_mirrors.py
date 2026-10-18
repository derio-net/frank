"""Guard the GitHub -> Gitea mirror wiring for the nine github-preferred repos.

Spec 2026-10-18--cicd--github-preferred-gitea-fallback, section 2 and 3 (R4-R6).
The repo lists are DERIVED from apps/ci-budget/tiers.yaml, so a repo added to a
tier cannot silently miss its mirror triggers.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
TEKTON = REPO / "apps/tekton"
EL_GITHUB = TEKTON / "triggers/eventlistener-github.yaml"
EL_GITEA = TEKTON / "triggers/eventlistener.yaml"
TIERS = REPO / "apps/ci-budget/tiers.yaml"
GENERATOR = TEKTON / "manifests/clustergenerator-derio-net-mirror-github-app.yaml"
MIRROR_ES = TEKTON / "manifests/externalsecret-derio-net-github-mirror.yaml"
PULL_SYNC = TEKTON / "pipelines/derio-net-pull-sync.yaml"
BRIDGE = TEKTON / "pipelines/stoa-status-bridge.yaml"

SECRETS = {
    "derio-net": "derio-net-github-webhook-secret",
    "derio-homelab": "derio-homelab-github-webhook-secret",
}


def _docs(path: Path) -> list[dict]:
    assert path.exists(), f"missing manifest: {path.relative_to(REPO)}"
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _one(path: Path, kind: str, name: str | None = None) -> dict:
    hits = [
        d for d in _docs(path)
        if d.get("kind") == kind and (name is None or d["metadata"]["name"] == name)
    ]
    assert len(hits) == 1, f"expected one {kind} {name or ''} in {path.name}, got {len(hits)}"
    return hits[0]


def _triggers(path: Path, listener: str) -> dict[str, dict]:
    el = _one(path, "EventListener", listener)
    return {t["name"]: t for t in el["spec"]["triggers"]}


def _cel(trigger: dict) -> dict:
    for i in trigger["interceptors"]:
        if i.get("ref", {}).get("name") == "cel":
            return {p["name"]: p["value"] for p in i["params"]}
    raise AssertionError(f"{trigger['name']}: no cel interceptor")


def _github_secret(trigger: dict) -> str:
    for i in trigger["interceptors"]:
        if i.get("ref", {}).get("name") == "github":
            return next(p for p in i["params"] if p["name"] == "secretRef")["value"]["secretName"]
    raise AssertionError(f"{trigger['name']}: no github interceptor")


def _preferred(org: str) -> list[str]:
    repos = yaml.safe_load(TIERS.read_text())["orgs"][org]["repos"]
    return sorted(f"{org}/{n}" for n, c in repos.items() if c["tier"] == "github-preferred")


def _named_repos(trigger: dict) -> list[str]:
    import re

    return sorted(re.findall(r"'([\w.-]+/[\w.-]+)'", _cel(trigger)["filter"]))


def _template(name: str) -> dict:
    return _one(EL_GITHUB, "TriggerTemplate", name)


def test_main_sync_triggers_serve_exactly_the_tier_repos() -> None:
    trig = _triggers(EL_GITHUB, "github-listener")
    assert _named_repos(trig["derio-net-main-sync"]) == _preferred("derio-net")
    assert _named_repos(trig["derio-homelab-main-sync"]) == sorted(
        _preferred("derio-homelab") + ["derio-homelab/kid-laptops"]
    )
    assert "derio-homelab-kid-laptops-main-sync" not in trig, "renamed to derio-homelab-main-sync"
    for name in ("derio-net-main-sync", "derio-homelab-main-sync"):
        assert "refs/heads/main" in _cel(trig[name])["filter"]
        assert _github_secret(trig[name]) == SECRETS[name.rsplit("-main-sync", 1)[0]]


def test_pr_sync_triggers_serve_the_tier_repos_only_and_write_sync_pr_refs() -> None:
    trig = _triggers(EL_GITHUB, "github-listener")
    for org in ("derio-net", "derio-homelab"):
        t = trig[f"{org}-pr-sync"]
        assert _named_repos(t) == _preferred(org), "kid-laptops has no PR mirror (main-sync only)"
        cel = _cel(t)
        for action in ("opened", "synchronize", "reopened"):
            assert f"'{action}'" in cel["filter"]
        overlays = str(cel["overlays"])
        assert "refs/heads/sync-pr-" in overlays and "body.pull_request.head.sha" in overlays
        assert _github_secret(t) == SECRETS[org]
        events = next(
            p["value"] for i in t["interceptors"] if i.get("ref", {}).get("name") == "github"
            for p in i["params"] if p["name"] == "eventTypes"
        )
        assert events == ["pull_request"]


def test_derio_net_triggers_run_the_derio_net_pipeline_with_its_own_token() -> None:
    trig = _triggers(EL_GITHUB, "github-listener")
    for name in ("derio-net-main-sync", "derio-net-pr-sync"):
        tpl = _template(trig[name]["template"]["ref"])
        run = tpl["spec"]["resourcetemplates"][0]["spec"]
        assert run["pipelineRef"]["name"] == "derio-net-pull-sync"
    pipeline = _one(PULL_SYNC, "Pipeline")
    assert pipeline["metadata"]["name"] == "derio-net-pull-sync"
    text = PULL_SYNC.read_text()
    assert "derio-net-github-mirror" in text
    assert "stoa-github-mirror" not in text and "derio-homelab-github-mirror" not in text


def test_homelab_triggers_run_the_homelab_pipeline() -> None:
    trig = _triggers(EL_GITHUB, "github-listener")
    for name in ("derio-homelab-main-sync", "derio-homelab-pr-sync"):
        tpl = _template(trig[name]["template"]["ref"])
        assert tpl["spec"]["resourcetemplates"][0]["spec"]["pipelineRef"]["name"] == "derio-homelab-pull-sync"


def test_mirror_generator_is_scoped_to_the_five_repos_with_minimal_permissions() -> None:
    gen = _one(GENERATOR, "ClusterGenerator")
    assert gen["metadata"]["name"] == "github-app-derio-mirror"
    spec = gen["spec"]["generator"]["githubAccessTokenSpec"]
    assert spec["appID"] == "3994132"
    assert spec["installID"] == "138773908"
    ref = spec["auth"]["privateKey"]["secretRef"]
    assert ref["name"] == "github-app-derio-key" and "namespace" not in ref
    assert spec["permissions"] == {
        "contents": "read", "pull_requests": "read", "statuses": "write", "metadata": "read",
    }
    assert sorted(spec["repositories"]) == sorted(r.split("/")[1] for r in _preferred("derio-net"))


def test_mirror_externalsecret_refreshes_under_the_token_ttl() -> None:
    es = _one(MIRROR_ES, "ExternalSecret")
    assert es["metadata"]["name"] == "derio-net-github-mirror"
    assert es["metadata"]["namespace"] == "tekton-pipelines"
    assert es["spec"]["target"]["name"] == "derio-net-github-mirror"
    assert es["spec"]["refreshInterval"] == "45m"
    gen = es["spec"]["dataFrom"][0]["sourceRef"]["generatorRef"]
    assert (gen["kind"], gen["name"]) == ("ClusterGenerator", "github-app-derio-mirror")


def test_gitea_push_excludes_derio_net_and_status_bridge_admits_three_orgs() -> None:
    trig = _triggers(EL_GITEA, "gitea-listener")
    push = _cel(trig["gitea-push"])["filter"]
    for org in ("agentic-stoa", "derio-homelab", "derio-net"):
        assert f"!body.repository.full_name.startsWith('{org}/')" in push
    bridge = _cel(trig["gitea-status-bridge"])["filter"]
    for org in ("agentic-stoa", "derio-homelab", "derio-net"):
        assert f"body.repository.full_name.startsWith('{org}/')" in bridge
    assert "!body.context.startsWith('tekton')" in bridge


def test_status_bridge_pipeline_keeps_its_name_and_says_three_orgs() -> None:
    p = _one(BRIDGE, "Pipeline")
    assert p["metadata"]["name"] == "stoa-status-bridge"
    assert "three" in p["spec"]["description"].lower()
