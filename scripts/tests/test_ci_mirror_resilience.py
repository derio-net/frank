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
PVC_PENDING_UID = "layer-25-ci-workspace-pvc-pending"  # shipped by #855
TIMEOUT_UID = "layer-25-pipelinerun-timeout"  # shipped by #855
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


MIRRORED_ORGS = ("agentic-stoa", "derio-homelab", "derio-net")


def _main_sync_repos() -> list[str]:
    """The repos every push-to-main mirror trigger actually serves, in listener order.

    Not just `agentic-stoa-main-sync`: derio-homelab/kid-laptops has its own
    `derio-homelab-kid-laptops-main-sync` trigger (a different GitHub App and
    webhook secret). The reconciler was written against the first trigger only,
    so for its first day a dropped kid-laptops webhook was a lost commit with
    no repair path — and the guard passed, because it only looked there too.
    """
    repos: list[str] = []
    for trig in _github_listener()["spec"]["triggers"]:
        if trig["name"].endswith("-main-sync"):
            repos += re.findall(rf"'((?:{'|'.join(MIRRORED_ORGS)})/[\w.-]+)'", _cel(trig)["filter"])
    return repos


def _token_var(org: str) -> str:
    """Env var carrying an org's GitHub App token: agentic-stoa keeps the original name."""
    return "GITHUB_TOKEN" if org == "agentic-stoa" else f"GITHUB_TOKEN_{org.upper().replace('-', '_')}"


def _pr_sync_repos() -> list[str]:
    """Repos with a PR trigger that writes sync-pr-<N> to the Gitea mirror.

    Every such trigger mirrors the PR head first (github-pull-sync, cnc-ci's
    `mirror` task, the hum/content-factory/stoa-blog `pull-and-push` task), so
    sync-pr-<N> == PR head is the mirror's intended state for all of them. The
    reconciler restores that ref. It re-fires Gitea Actions but cannot re-run a
    Tekton CI body, which the docs say explicitly.
    """
    repos = []
    for trig in _github_listener()["spec"]["triggers"]:
        cel = _cel(trig)
        if "sync-pr-" not in str(cel.get("overlays")):
            continue
        repos += re.findall(rf"'((?:{'|'.join(MIRRORED_ORGS)})/[\w.-]+)'", cel["filter"])
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
            f"{c['name']}: MAIN_REPOS drifted from the *-main-sync CEL filters"
            " — a repo added there would never be repaired"
        )
        assert env["PR_REPOS"].split() == _pr_sync_repos(), c["name"]
    assert declaring == 2, "both the heads and plan stages must carry the repo lists"
    assert "derio-homelab/kid-laptops" in _main_sync_repos(), (
        "the derivation must see the second org's trigger, not only agentic-stoa's"
    )
    # The derivation must not silently collapse: these write sync-pr-N today.
    assert _pr_sync_repos() == sorted(
        [f"agentic-stoa/{r}" for r in ("cnc-fr", "cnc-frd", "cnc-fru", "content-factory",
                                       "hermes-brain", "hum", "second-brain", "stoa-blog")]
        + [f"derio-homelab/{r}" for r in ("proxmox-cluster", "omada-controller", "homelab",
                                          "ansible-pihole")]
        + [f"derio-net/{r}" for r in ("willikins", "herdr-vertical-tabs", "presentation-craft",
                                      "vibe-kanban", "runs-fr")]
    )


def test_every_mirrored_org_has_its_own_github_token_wired_to_the_right_secret() -> None:
    """Each org is a separate GitHub App installation: one App's token cannot read
    another org's private repo (GitHub answers 404). So a repo from a second org
    in MAIN_REPOS with only the first org's token wired is a reconciler that
    looks covered and fails every run — loudly, but only after the first drift.
    """
    secrets = {
        "agentic-stoa": "stoa-github-mirror",
        "derio-homelab": "derio-homelab-github-mirror",
        "derio-net": "derio-net-github-mirror",
    }
    pod = _cronjob()["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    stages = {c["name"]: c for c in pod["initContainers"] + pod["containers"]}
    orgs = {repo.split("/")[0] for repo in _main_sync_repos()}
    assert orgs == set(secrets), f"mirrored orgs {sorted(orgs)} changed; wire a token for each"
    for stage in ("plan", "push"):  # the two stages that talk to GitHub
        env = {e["name"]: e for e in stages[stage]["env"]}
        for org, secret in secrets.items():
            ref = env[_token_var(org)]["valueFrom"]["secretKeyRef"]
            assert (ref["name"], ref["key"]) == (secret, "token"), (stage, org, ref)


def test_plan_reads_each_repo_with_its_own_orgs_token() -> None:
    token_for = _plan_module().token_for
    env = {"GITHUB_TOKEN": "stoa", "GITHUB_TOKEN_DERIO_HOMELAB": "homelab", "GITHUB_TOKEN_DERIO_NET": "net"}
    assert token_for("agentic-stoa/hum", env) == "stoa"
    assert token_for("derio-homelab/kid-laptops", env) == "homelab"
    assert token_for("derio-net/willikins", env) == "net"
    # An org with no token of its own falls back to the original one: the
    # request then fails loudly (404) into errors.txt and fails the Job, which
    # is better than a KeyError that takes the other org's repairs down too.
    assert token_for("someone-else/x", env) == "stoa"


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
    push = next(c for c in cj["jobTemplate"]["spec"]["template"]["spec"]["containers"] if c["name"] == "push")
    assert {"name": "DRY_RUN", "value": "0"} in push["env"], "ship live, with the switch visible"
    assert "mirror-reconcile result dry_run=" in _script_cm()["data"]["push.sh"]


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
        commit_time=lambda r, s: pytest.fail("main heads carry their own time"),
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
        github_open_prs=lambda r: [(124, "ab45e07")],
        commit_time=lambda r, s: OLD,
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
        github_open_prs=lambda r: [(7, "prsha"), (8, "insync")],
        commit_time=lambda r, s: FRESH if s == "prsha" else pytest.fail("in-sync PR needs no lookup"),
        gitea_head=lambda r, branch: {"main": "same", "sync-pr-8": "insync"}.get(branch, "older"),
        now=NOW,
        grace=timedelta(minutes=10),
    )
    # a/main matches; b/main and a's PR are younger than the grace period,
    # so the webhook sync still owns them.
    assert plan == []


def test_pr_grace_is_the_head_commit_time_not_pr_activity() -> None:
    # A PR with constant review chatter must still be repaired: its updated_at
    # would never age past the grace period, its head commit does.
    plan = _plan_module().plan(
        main_repos=[],
        pr_repos=["agentic-stoa/second-brain"],
        github_head=lambda r: None,
        github_open_prs=lambda r: [(124, "ab45e07")],
        commit_time=lambda r, s: OLD,
        gitea_head=lambda r, branch: None,
        now=NOW,
        grace=timedelta(minutes=10),
    )
    assert len(plan) == 1


def test_plan_skips_a_pr_whose_commit_time_is_unreadable() -> None:
    plan = _plan_module().plan(
        main_repos=[],
        pr_repos=["agentic-stoa/x"],
        github_head=lambda r: None,
        github_open_prs=lambda r: [(1, "abc")],
        commit_time=lambda r, s: None,
        gitea_head=lambda r, branch: None,
        now=NOW,
        grace=timedelta(minutes=10),
    )
    assert plan == []


def test_plan_output_is_grouped_by_repo() -> None:
    mod = _plan_module()
    out = mod.format_plan([
        mod.Drift("agentic-stoa/b", "refs/heads/main", "refs/heads/main", "1", None),
        mod.Drift("agentic-stoa/a", "refs/heads/main", "refs/heads/main", "2", None),
        mod.Drift("agentic-stoa/b", "refs/pull/1/head", "refs/heads/sync-pr-1", "3", None),
    ])
    assert [line.split()[0] for line in out.splitlines()] == [
        "agentic-stoa/a", "agentic-stoa/b", "agentic-stoa/b"
    ]


def test_main_wires_github_and_gitea_into_the_plan(tmp_path, monkeypatch) -> None:
    """Run plan.py's main() with a stubbed GitHub API and a real heads file.

    Pins the I/O the pure planner tests cannot see: the GitHub JSON paths,
    the heads-file parsing, the __listed__ filter, and errors.txt.
    """
    mod = _plan_module()
    (tmp_path / "gitea-heads.txt").write_text(
        "agentic-stoa/a __listed__ -\n"
        "agentic-stoa/a refs/heads/main oldmain\n"
        "agentic-stoa/a refs/heads/sync-pr-5 prsha\n"
    )  # agentic-stoa/b has no marker: its ls-remote failed
    old = "2026-10-11T21:59:10Z"
    responses = {
        "/repos/agentic-stoa/a/branches/main": {"commit": {"sha": "newmain", "commit": {"committer": {"date": old}}}},
        "/repos/agentic-stoa/a/pulls?state=open&per_page=100": [
            {"number": 5, "head": {"sha": "prsha"}},
            {"number": 6, "head": {"sha": "pr6sha"}},
        ],
        "/repos/agentic-stoa/a/commits/pr6sha": {"commit": {"committer": {"date": old}}},
    }
    monkeypatch.setattr(mod, "_github", lambda path, token: responses[path])
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("PLAN_DIR", str(tmp_path))
    monkeypatch.setenv("MAIN_REPOS", "agentic-stoa/a agentic-stoa/b")
    monkeypatch.setenv("PR_REPOS", "agentic-stoa/a")
    mod.main()
    assert (tmp_path / "plan.txt").read_text().splitlines() == [
        "agentic-stoa/a refs/heads/main refs/heads/main newmain oldmain",
        "agentic-stoa/a refs/pull/6/head refs/heads/sync-pr-6 pr6sha -",
    ]
    assert (tmp_path / "errors.txt").read_text() == "agentic-stoa/b: Gitea heads unreadable\n"


def test_main_records_a_github_failure_and_carries_on(tmp_path, monkeypatch) -> None:
    mod = _plan_module()
    (tmp_path / "gitea-heads.txt").write_text("agentic-stoa/a __listed__ -\nagentic-stoa/b __listed__ -\n")

    def fake(path, token):
        if "/a/" in path:
            raise OSError("HTTP 502")
        return {"commit": {"sha": "s", "commit": {"committer": {"date": "2026-10-11T00:00:00Z"}}}}

    monkeypatch.setattr(mod, "_github", fake)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("PLAN_DIR", str(tmp_path))
    monkeypatch.setenv("MAIN_REPOS", "agentic-stoa/a agentic-stoa/b")
    monkeypatch.setenv("PR_REPOS", "")
    mod.main()
    assert (tmp_path / "plan.txt").read_text() == "agentic-stoa/b refs/heads/main refs/heads/main s -\n"
    assert "agentic-stoa/a: GitHub main unreadable" in (tmp_path / "errors.txt").read_text()


def test_plan_output_round_trips_through_the_push_script_format() -> None:
    mod = _plan_module()
    line = mod.format_plan([mod.Drift("agentic-stoa/x", "refs/pull/1/head", "refs/heads/sync-pr-1", "abc", None)])
    assert line == "agentic-stoa/x refs/pull/1/head refs/heads/sync-pr-1 abc -\n"


# --------------------------------------------------------------------------
# 3. the next outage pages


def test_sync_failing_rule_covers_only_fast_failures() -> None:
    """The complement of #855's timeout rule, so a failure class pages once.

    layer-25-pipelinerun-timeout counts failures OUTSIDE le="1800" (> 30m);
    this rule counts failures INSIDE it. Both reading the same bucket edge is
    what makes them a partition rather than an overlap.
    """
    rule = _rules()[SYNC_FAILING_UID]
    expr = _expr(rule)
    assert 'pipeline=~".+-pull-sync"' in expr
    assert expr.count('status="failed", le="1800"') == 2, "both failure terms read the fast bucket"
    assert ">= 3" in expr and ">= 0.5" in expr and "[2h]" in expr
    assert "unless" not in expr
    assert rule["for"] == "30m"
    assert rule["labels"]["severity"] == "warning"
    timeout = _expr(_rules()[TIMEOUT_UID])
    assert 'le="1800"' in timeout, "the partition edge moved: re-check both rules together"


def test_the_outage_mechanism_is_watched_once_not_twice() -> None:
    # #855 shipped the Pending-PVC rule; this branch's own copy was dropped on
    # merge. Exactly one rule may watch tekton-pipelines PVC phase.
    watchers = [uid for uid, r in _rules().items()
                if "kube_persistentvolumeclaim_status_phase" in _expr(r)
                and 'namespace="tekton-pipelines"' in _expr(r)]
    assert watchers == [PVC_PENDING_UID]


def test_the_repair_path_has_its_own_dead_man() -> None:
    rule = _rules()[RECONCILE_STALE_UID]
    expr = _expr(rule)
    assert 'cronjob="mirror-reconcile"' in expr and 'namespace="tekton-pipelines"' in expr
    assert "kube_cronjob_status_last_successful_time" in expr
    assert rule["noDataState"] == "OK"  # never succeeded yet -> quiet, not paging
    assert "> bool 1800" in expr and rule["for"] == "30m"  # ~1h total, as documented


@pytest.mark.parametrize("uid", [SYNC_FAILING_UID, RECONCILE_STALE_UID])
def test_new_rules_fit_grafanas_uid_limit(uid: str) -> None:
    assert len(uid) <= 40
