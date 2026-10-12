"""Guards for the GitHub->Gitea CI mirror's resilience (2026-10-12 outage).

Three independent failures stacked into one ~15h CI blackout for agentic-stoa:

1. #836 moved every Tekton workspace onto ``longhorn-hdd`` before any Longhorn
   disk carried the ``hdd`` tag. Each ``github-pull-sync`` PipelineRun sat
   Pending for its full 1h timeout (21:22Z -> 04:21Z): the commits never
   reached Gitea, so no Gitea Actions run, so no commit status.
2. At 06:49-06:51Z GitHub got HTTP 502 for three pushes because both
   EventListeners were single replicas pinned to pc-1, which was draining.
   GitHub never retries a failed delivery.
3. Nothing noticed. ``layer-25-pipeline-failing`` only fires on a pipeline
   with ZERO successes in 24h, so a run of timeouts after a successful
   afternoon is invisible to it by construction; and the mirror has no repair
   path at all — a lost webhook is a lost commit, forever.

These tests pin one fix per failure: listeners that survive a node drain, a
reconciler that repairs drift the webhook path dropped, and alerts that see a
sync outage and the Pending-PVC mechanism that caused this one.
"""
from __future__ import annotations

import pathlib
import re
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
TRIGGERS = REPO / "apps" / "tekton" / "triggers"
EL_GITHUB = TRIGGERS / "eventlistener-github.yaml"
EL_GITEA = TRIGGERS / "eventlistener.yaml"
LISTENER_PDB = REPO / "apps" / "tekton" / "manifests" / "eventlistener-pdb.yaml"
RECONCILE = REPO / "apps" / "tekton" / "manifests" / "mirror-reconcile.yaml"
ALERT_RULES_CM = REPO / "apps" / "grafana-alerting" / "manifests" / "alert-rules-cm.yaml"

LISTENERS = {"github-listener": EL_GITHUB, "gitea-listener": EL_GITEA}
SYNC_FAILING_UID = "layer-25-mirror-sync-failing"
PVC_PENDING_UID = "layer-25-ci-pvc-pending"
RECONCILE_STALE_UID = "layer-25-mirror-reconcile-stale"


# --------------------------------------------------------------------------
# helpers


def _docs(path: pathlib.Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _one(path: pathlib.Path, kind: str, name: str | None = None) -> dict:
    hits = [
        d
        for d in _docs(path)
        if d.get("kind") == kind and (name is None or d["metadata"]["name"] == name)
    ]
    assert len(hits) == 1, f"expected one {kind} {name or ''} in {path.name}, got {len(hits)}"
    return hits[0]


def _cel(trigger: dict) -> dict:
    for interceptor in trigger.get("interceptors", []):
        if interceptor.get("ref", {}).get("name") == "cel":
            return {p["name"]: p["value"] for p in interceptor.get("params", [])}
    return {}


def _github_listener() -> dict:
    return _one(EL_GITHUB, "EventListener", "github-listener")


def _main_sync_repos() -> list[str]:
    """The repo list the push-to-main mirror trigger actually serves."""
    trig = next(t for t in _github_listener()["spec"]["triggers"] if t["name"] == "agentic-stoa-main-sync")
    return re.findall(r"'(agentic-stoa/[\w.-]+)'", _cel(trig)["filter"])


def _mirror_only_pr_repos() -> list[str]:
    """Repos whose PR trigger ONLY mirrors to sync-pr-N (CI runs in Gitea Actions).

    The Phase-4-era repos (hum, content-factory, stoa-blog) run bespoke Tekton
    CI from the PR webhook; mirroring their sync-pr branch would not restore
    that CI, so the reconciler deliberately does not claim to cover them.
    """
    repos = []
    for trig in _github_listener()["spec"]["triggers"]:
        if trig.get("template", {}).get("ref") != "agentic-stoa-main-sync-template":
            continue
        cel = _cel(trig)
        if "pull_request" not in str(trig) or "sync-pr-" not in str(cel.get("overlays")):
            continue
        repos += re.findall(r"'(agentic-stoa/[\w.-]+)'", cel["filter"])
    return sorted(set(repos))


def _cronjob() -> dict:
    return _one(RECONCILE, "CronJob", "mirror-reconcile")


def _script_cm() -> dict:
    return _one(RECONCILE, "ConfigMap", "mirror-reconcile-scripts")


def _plan_module() -> types.ModuleType:
    """Load the plan script out of the ConfigMap so the tests run what ships."""
    mod = types.ModuleType("mirror_reconcile_plan")
    # @dataclass resolves annotations through sys.modules[cls.__module__].
    sys.modules[mod.__name__] = mod
    exec(compile(_script_cm()["data"]["plan.py"], "plan.py", "exec"), mod.__dict__)
    return mod


def _rules() -> dict[str, dict]:
    cm = yaml.safe_load(ALERT_RULES_CM.read_text())
    doc = yaml.safe_load(cm["data"]["alert-rules.yaml"])
    return {r["uid"]: r for g in doc["groups"] for r in g["rules"]}


def _expr(rule: dict) -> str:
    return " ".join(rule["data"][0]["model"]["expr"].split())


# --------------------------------------------------------------------------
# 1. the listeners survive a node drain


@pytest.mark.parametrize("name", sorted(LISTENERS))
def test_listener_is_not_pinned_to_a_single_node(name: str) -> None:
    el = _one(LISTENERS[name], "EventListener", name)
    spec = el["spec"]["resources"]["kubernetesResource"]["spec"]["template"]["spec"]
    assert "kubernetes.io/hostname" not in (spec.get("nodeSelector") or {}), (
        f"{name} is pinned to one node: draining it 502s every webhook, and GitHub never retries"
    )


@pytest.mark.parametrize("name", sorted(LISTENERS))
def test_listener_runs_two_replicas_on_different_nodes(name: str) -> None:
    res = _one(LISTENERS[name], "EventListener", name)["spec"]["resources"]["kubernetesResource"]
    assert res.get("replicas", 1) >= 2, f"{name}: one replica means one drain = lost webhooks"
    spread = res["spec"]["template"]["spec"].get("topologySpreadConstraints") or []
    assert any(
        c.get("topologyKey") == "kubernetes.io/hostname"
        and c.get("labelSelector", {}).get("matchLabels", {}).get("eventlistener") == name
        for c in spread
    ), f"{name}: replicas must be spread across hosts, or both can land on the node being drained"


@pytest.mark.parametrize("name", sorted(LISTENERS))
def test_listener_has_a_disruption_budget(name: str) -> None:
    pdbs = [d for d in _docs(LISTENER_PDB) if d.get("kind") == "PodDisruptionBudget"]
    match = [p for p in pdbs if p["spec"]["selector"]["matchLabels"].get("eventlistener") == name]
    assert len(match) == 1, f"{name}: no PodDisruptionBudget — a drain may evict both replicas at once"
    assert match[0]["spec"].get("minAvailable") == 1
    assert match[0]["metadata"]["namespace"] == "tekton-pipelines"


# --------------------------------------------------------------------------
# 2. a reconciler repairs drift the webhook path dropped


def test_reconciler_covers_exactly_the_repos_the_triggers_serve() -> None:
    pod = _cronjob()["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    declaring = 0
    for c in pod["initContainers"] + pod["containers"]:
        env = {e["name"]: e.get("value") for e in c.get("env", [])}
        if "MAIN_REPOS" not in env:
            continue
        declaring += 1
        assert env["MAIN_REPOS"].split() == _main_sync_repos(), (
            f"{c['name']}: MAIN_REPOS drifted from the agentic-stoa-main-sync CEL filter"
            " — a repo added there would never be repaired"
        )
        assert env["PR_REPOS"].split() == _mirror_only_pr_repos(), c["name"]
    assert declaring == 2, "both the heads and plan stages must carry the repo lists"
    assert _mirror_only_pr_repos() == ["agentic-stoa/hermes-brain", "agentic-stoa/second-brain"]


def test_reconciler_cannot_regress_a_newer_gitea_head() -> None:
    push = _script_cm()["data"]["push.sh"]
    assert "--force-with-lease=" in push, (
        "a plain --force lets a stale plan overwrite a head a webhook sync pushed meanwhile"
    )
    assert not re.search(r"git[^\n]*push[^\n]*\s--force(\s|$)", push)


def test_reconciler_never_overlaps_itself_and_reports_a_result() -> None:
    cj = _cronjob()["spec"]
    assert cj["concurrencyPolicy"] == "Forbid"
    assert cj["jobTemplate"]["spec"]["activeDeadlineSeconds"] <= 900
    assert "mirror-reconcile result drift=" in _script_cm()["data"]["push.sh"]


def test_reconciler_does_not_depend_on_the_storage_that_broke() -> None:
    pod = _cronjob()["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    for vol in pod["volumes"]:
        assert "persistentVolumeClaim" not in vol and "ephemeral" not in vol, (
            "the reconciler is the repair path for a broken PVC path; it must not need a PVC itself"
        )
    assert "nodeSelector" not in pod


def _gh(heads=None, prs=None):
    heads = heads or {}
    prs = prs or {}
    return types.SimpleNamespace(
        github_head=lambda repo: heads.get(repo),
        github_open_prs=lambda repo: prs.get(repo, []),
    )


NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
OLD = NOW - timedelta(minutes=30)
FRESH = NOW - timedelta(minutes=2)


def test_plan_repairs_a_main_head_the_mirror_missed() -> None:
    plan = _plan_module().plan(
        main_repos=["agentic-stoa/second-brain"],
        pr_repos=[],
        github_head=lambda r: ("6673521", OLD),
        github_open_prs=lambda r: [],
        gitea_head=lambda r, branch: "e296c27",
        now=NOW,
        grace=timedelta(minutes=10),
    )
    assert [(d.repo, d.src_ref, d.dst_ref, d.want, d.have) for d in plan] == [
        ("agentic-stoa/second-brain", "refs/heads/main", "refs/heads/main", "6673521", "e296c27")
    ]


def test_plan_creates_a_missing_sync_pr_branch() -> None:
    # PR #124's shape: the opened+synchronize syncs both timed out, so the
    # sync-pr branch never existed on Gitea at all.
    plan = _plan_module().plan(
        main_repos=[],
        pr_repos=["agentic-stoa/second-brain"],
        github_head=lambda r: None,
        github_open_prs=lambda r: [(124, "ab45e07", OLD)],
        gitea_head=lambda r, branch: None,
        now=NOW,
        grace=timedelta(minutes=10),
    )
    assert [(d.src_ref, d.dst_ref, d.want, d.have) for d in plan] == [
        ("refs/pull/124/head", "refs/heads/sync-pr-124", "ab45e07", None)
    ]


def test_plan_leaves_in_sync_and_in_flight_refs_alone() -> None:
    plan = _plan_module().plan(
        main_repos=["agentic-stoa/a", "agentic-stoa/b"],
        pr_repos=["agentic-stoa/a"],
        github_head=lambda r: ("same", OLD) if r.endswith("/a") else ("new", FRESH),
        github_open_prs=lambda r: [(7, "prsha", FRESH)],
        gitea_head=lambda r, branch: "same" if branch == "main" else "older",
        now=NOW,
        grace=timedelta(minutes=10),
    )
    # a/main matches; b/main and a's PR are younger than the grace period,
    # so the webhook sync still owns them.
    assert plan == []


def test_plan_output_round_trips_through_the_push_script_format() -> None:
    mod = _plan_module()
    line = mod.format_plan([mod.Drift("agentic-stoa/x", "refs/pull/1/head", "refs/heads/sync-pr-1", "abc", None)])
    assert line == "agentic-stoa/x refs/pull/1/head refs/heads/sync-pr-1 abc -\n"


# --------------------------------------------------------------------------
# 3. the next outage pages


def test_sync_failing_rule_sees_a_partial_day_outage() -> None:
    rule = _rules()[SYNC_FAILING_UID]
    expr = _expr(rule)
    assert 'pipeline=~".+-pull-sync"' in expr
    assert 'status="failed"' in expr
    # A ratio, not "zero successes in 24h" — the latter is what stayed silent
    # through seven hours of timeouts after a successful afternoon.
    assert ">= 3" in expr and ">= 0.5" in expr and "[2h]" in expr
    assert "unless" not in expr
    assert rule["for"] == "30m"
    assert rule["labels"]["severity"] == "warning"


def test_pending_ci_pvc_rule_watches_the_mechanism_itself() -> None:
    rule = _rules()[PVC_PENDING_UID]
    expr = _expr(rule)
    assert 'namespace="tekton-pipelines"' in expr and 'phase="Pending"' in expr
    assert "kube_persistentvolumeclaim_status_phase" in expr
    assert rule["for"] == "10m"


def test_the_repair_path_has_its_own_dead_man() -> None:
    rule = _rules()[RECONCILE_STALE_UID]
    expr = _expr(rule)
    assert 'cronjob="mirror-reconcile"' in expr and 'namespace="tekton-pipelines"' in expr
    assert "kube_cronjob_status_last_successful_time" in expr
    assert rule["noDataState"] == "OK"  # never succeeded yet -> quiet, not paging


@pytest.mark.parametrize("uid", [SYNC_FAILING_UID, PVC_PENDING_UID, RECONCILE_STALE_UID])
def test_new_rules_fit_grafanas_uid_limit(uid: str) -> None:
    assert len(uid) <= 40
