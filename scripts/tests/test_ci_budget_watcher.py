"""Guard: the ci-budget watcher (spec 2026-10-18 section 4).

Part 1: the pure decision core.
Part 2: the ordered two-forge apply, against fake clients.
Part 3: state, notifications and the heartbeat line.
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FILES = REPO_ROOT / "apps/ci-budget/files"
FIX = Path(__file__).parent / "fixtures/ci_budget"


def _load(name):
    sys.path.insert(0, str(FILES))
    try:
        spec = importlib.util.spec_from_file_location(name, FILES / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(FILES))
    return mod


w = _load("watcher")


def _fx(name):
    return json.loads((FIX / name).read_text())


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


# ---------------------------------------------------------------- part 1


def test_included_minutes_weights_skus():
    items = _fx("usage.json")["usageItems"]
    # Linux 100*1 + Windows 50*2 + macOS 20*10 + Linux 40*1 (storage and
    # copilot are not minutes)
    assert w.included_minutes_used(items) == 440


def test_included_minutes_excludes_public_repos():
    items = _fx("usage.json")["usageItems"]
    assert w.included_minutes_used(items, exclude_repos={"frank-public-thing"}) == 400


def test_included_minutes_unknown_actions_sku_raises():
    items = _fx("usage_unknown_sku.json")["usageItems"]
    with pytest.raises(ValueError, match="ARM Linux"):
        w.included_minutes_used(items)


def test_included_minutes_sku_case_and_separator_insensitive():
    items = [
        {"product": "Actions", "sku": "actions_macos", "quantity": 2, "repositoryName": "r"},
        {"product": "actions", "sku": "ACTIONS WINDOWS", "quantity": 1, "repositoryName": "r"},
    ]
    assert w.included_minutes_used(items) == 22


def test_pinned_share_counts_non_preferred_repos_and_macos():
    items = _fx("usage.json")["usageItems"]
    ex = {"frank-public-thing"}
    # preferred = all three: only herdr's macOS (200 of 400) is pinned
    assert w.pinned_share(items, {"willikins", "vibe-kanban", "herdr-vertical-tabs"}, ex) == 0.5
    # only willikins preferred: vibe 100 + herdr 200 pinned of 400
    assert w.pinned_share(items, {"willikins"}, ex) == 0.75
    assert w.pinned_share([], {"willikins"}) == 0.0


@pytest.mark.parametrize(
    "kw,expect",
    [
        (dict(pct=10), ("github", False)),
        (dict(pct=84.9), ("github", False)),
        (dict(pct=85), ("gitea", True)),
        (dict(pct=99), ("gitea", True)),
        (dict(pct=10, month_stamp="2026-10"), ("gitea", False)),
        (dict(pct=10, month_stamp="2026-09"), ("github", False)),
        (dict(pct=90, month_stamp="2026-10"), ("gitea", False)),
        (dict(pct=90, month_stamp="2026-09"), ("gitea", True)),
        (dict(pct=10, backstop_hit=True), ("gitea", True)),
        (dict(pct=95, pin="github"), ("github", False)),
        (dict(pct=5, pin="gitea"), ("gitea", False)),
        (dict(pct=5, month_stamp="2026-10", pin="github"), ("github", False)),
        (dict(pct=5, backstop_hit=True, pin="github"), ("github", False)),
    ],
)
def test_desired_authority(kw, expect):
    base = dict(pct=0, threshold=85, backstop_hit=False, month_stamp=None, now_month="2026-10", pin=None)
    base.update(kw)
    assert tuple(w.desired_authority(**base)) == expect


NOW = utc(2026, 10, 18, 12, 0)


def _runs():
    return _fx("runs.json")["workflow_runs"]


def _ann():
    a = _fx("annotations.json")
    return {9001: a["spend"], 9002: a["ordinary"], 9003: a["spend"], 9004: a["spend"]}


def test_backstop_hits_selects_recent_spending_limit_failures():
    hits = w.backstop_hits(_runs(), _ann(), NOW, set())
    # 9001: recent + matches (case-insensitive 'Spending Limit').
    # 9002: older than 30 min and not a spending message.
    # 9003: before the UTC month start. 9004: not a failure.
    assert [r["id"] for r in hits] == [9001]


def test_backstop_hits_skips_handled_ids():
    assert w.backstop_hits(_runs(), _ann(), NOW, {9001}) == []


def test_backstop_hits_ignores_runs_older_than_30_minutes():
    assert w.backstop_hits(_runs(), _ann(), utc(2026, 10, 18, 12, 40), set()) == []


def test_backstop_hits_month_start_guard():
    # one minute into the new month: the last-month failure never counts
    runs = [dict(_runs()[2], created_at="2026-09-30T23:59:00Z")]
    assert w.backstop_hits(runs, _ann(), utc(2026, 10, 1, 0, 1), set()) == []
    # a run created at/after the month start does
    runs = [dict(_runs()[2], created_at="2026-10-01T00:00:00Z")]
    assert [r["id"] for r in w.backstop_hits(runs, _ann(), utc(2026, 10, 1, 0, 10), set())] == [9003]


# ---------------------------------------------------------------- part 2
# Fake clients record every call in one shared list, so ordering across the
# two forges is observable.

LABELS = {"ubuntu-latest", "ubuntu-24.04"}
GATED_WF = (FIX.parent / "ci_gate_coverage/ok-gated.yml").read_text()
UNGATED_WF = (
    "name: bad\non:\n  pull_request:\njobs:\n  check:\n"
    "    runs-on: ubuntu-latest\n    steps:\n      - run: make test\n"
)


class FakeGH:
    def __init__(self, calls, gh_vars=None, usage=None, public=(), runs=None, ann=None, files=None, drop=()):
        self.calls = calls
        self.vars = dict(gh_vars or {})
        self.usage = usage if usage is not None else []
        self.public = set(public)
        self.runs = runs or {}
        self.ann = ann or {}
        self.files = files if files is not None else {}
        self.drop = set(drop)

    def billing_usage(self, org, year, month):
        self.calls.append(("gh", "billing", org, year, month))
        return self.usage

    def public_repos(self, org):
        self.calls.append(("gh", "public_repos", org))
        return self.public

    def list_failed_runs(self, repo, since):
        self.calls.append(("gh", "runs", repo))
        return list(self.runs.get(repo, []))

    def run_annotations(self, repo, run_id):
        self.calls.append(("gh", "annotations", repo, run_id))
        return self.ann.get(run_id, [])

    def workflow_files(self, repo):
        self.calls.append(("gh", "files", repo))
        return dict(self.files.get(repo, {}))

    def get_variable(self, repo, name):
        self.calls.append(("gh", "get", repo, name))
        return self.vars.get((repo, name))

    def set_variable(self, repo, name, value):
        self.calls.append(("gh", "set", repo, name, value))
        if ("gh", repo) not in self.drop:
            self.vars[(repo, name)] = value


class FakeGitea:
    def __init__(self, calls, repo_vars=None, org_vars=None, branches=None, drop=()):
        self.calls = calls
        self.repo_vars = dict(repo_vars or {})
        self.org_vars = dict(org_vars or {})
        self.branches = branches if branches is not None else {}
        self.drop = set(drop)

    def get_repo_var(self, org, repo, name):
        self.calls.append(("gitea", "get", repo, name))
        return self.repo_vars.get((repo, name))

    def set_repo_var(self, org, repo, name, value):
        self.calls.append(("gitea", "set", repo, name, value))
        if ("gitea", repo) not in self.drop:
            self.repo_vars[(repo, name)] = value

    def get_org_var(self, org, name):
        self.calls.append(("gitea", "org-get", name))
        return self.org_vars.get(name)

    def set_org_var(self, org, name, value):
        self.calls.append(("gitea", "org-set", name, value))
        self.org_vars[name] = value

    def create_branch(self, org, repo, name, sha):
        self.calls.append(("gitea", "branch-create", repo, name, sha))
        self.branches.setdefault(repo, {})[name] = {"name": name, "commit": {"timestamp": "2026-10-18T12:00:00Z"}}

    def list_branches(self, org, repo):
        self.calls.append(("gitea", "branch-list", repo))
        return list(self.branches.get(repo, {}).values())

    def delete_branch(self, org, repo, name):
        self.calls.append(("gitea", "branch-delete", repo, name))
        self.branches.get(repo, {}).pop(name, None)


class FakeNotifier:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.sent = []

    def send(self, text):
        self.sent.append(text)


def org_cfg(mode="live", repos=None, **kw):
    cfg = {
        "included_minutes": 2000,
        "threshold_pct": 85,
        "gitea_org": "derio-net",
        "mode": mode,
        "repos": repos
        or {
            "willikins": {"tier": "github-preferred"},
            "keepme": {"tier": "gitea-only"},
        },
    }
    cfg.update(kw)
    return cfg


def over_threshold_usage():
    # 1800 Linux minutes of 2000 = 90%
    return [{"product": "actions", "sku": "Actions Linux", "quantity": 1800, "repositoryName": "willikins"}]


def run(cfg=None, gh=None, gitea=None, st=None, notifier=None, now=NOW, org="derio-net"):
    calls = []
    gh = gh or FakeGH(calls)
    gitea = gitea or FakeGitea(calls)
    gh.calls = gitea.calls = calls
    out = []
    res = w.run_org(
        org, cfg or org_cfg(), gh, gitea, st if st is not None else {}, now,
        notifier or FakeNotifier(), LABELS, log=out.append,
    )
    return res, calls, out


def writes(calls):
    return [c for c in calls if c[1] in ("set", "org-set", "branch-create", "branch-delete")]


def test_toward_gitea_order_gitea_first_with_readbacks():
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    res, calls, _ = run(gh=gh, gitea=gitea)
    seq = [(c[0], c[1]) for c in calls if len(c) > 3 and c[2] == "willikins" and c[3] == "CI_AUTHORITY"]
    # gitea set, gitea read-back, github set, github read-back
    set_i = [i for i, c in enumerate(seq) if c[1] == "set"]
    assert [seq[i] for i in set_i] == [("gitea", "set"), ("gh", "set")]
    assert seq[set_i[0] + 1] == ("gitea", "get")
    assert seq[set_i[1] + 1] == ("gh", "get")
    assert gh.vars[("willikins", "CI_AUTHORITY")] == "gitea"
    assert gitea.repo_vars[("willikins", "CI_AUTHORITY")] == "gitea"
    assert res["verdict"] == "flipped"


def test_toward_github_order_github_first():
    # last month's stamp, below threshold: desired is github
    gh = FakeGH([], usage=[], files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "gitea"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "gitea"},
                      org_vars={"CI_BUDGET_MONTH": "2026-09"})
    res, calls, _ = run(gh=gh, gitea=gitea)
    sets = [(c[0], c[3]) for c in calls if c[1] == "set"]
    assert sets == [("gh", "CI_AUTHORITY"), ("gitea", "CI_AUTHORITY")]
    assert calls.index(("gh", "set", "willikins", "CI_AUTHORITY", "github")) < calls.index(
        ("gitea", "set", "willikins", "CI_AUTHORITY", "github"))
    assert gh.vars[("willikins", "CI_AUTHORITY")] == "github"


def test_failed_readback_stops_that_repos_sequence_and_errors():
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"},
                      drop={("gitea", "willikins")})
    res, calls, out = run(gh=gh, gitea=gitea)
    assert res["verdict"] == "error"
    assert res["failed"] is True
    # the GitHub side must never be written after the Gitea read-back failed
    assert not [c for c in calls if c[:2] == ("gh", "set")]


def test_matching_sides_write_nothing():
    gh = FakeGH([], usage=[], gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    res, calls, _ = run(gh=gh, gitea=gitea)
    assert writes(calls) == []
    assert res["verdict"] == "ok"


def test_coverage_findings_block_both_sides():
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": UNGATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    note = FakeNotifier()
    res, calls, _ = run(gh=gh, gitea=gitea, notifier=note)
    assert not [c for c in writes(calls) if c[1] == "set"]
    assert res["verdict"] == "refused"
    assert len(note.sent) == 1 and "willikins" in note.sent[0]


def test_org_variables_only_get_budget_month():
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    run(gh=gh, gitea=gitea)
    assert gitea.org_vars == {"CI_BUDGET_MONTH": "2026-10"}
    assert [c for c in gitea.calls if c[1] == "org-set"] == [("gitea", "org-set", "CI_BUDGET_MONTH", "2026-10")]


def test_unset_github_variable_is_written_explicitly():
    gh = FakeGH([], usage=[], files={"willikins": {"w.yml": GATED_WF}})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    run(gh=gh, gitea=gitea)
    assert gh.vars[("willikins", "CI_AUTHORITY")] == "github"
    # the Gitea side already matched and is not rewritten
    assert not [c for c in gitea.calls if c[:2] == ("gitea", "set")]


def test_dry_run_writes_nothing():
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    res, calls, _ = run(cfg=org_cfg(mode="dry-run"), gh=gh, gitea=gitea)
    assert writes(calls) == []
    assert res["verdict"] == "would-flip"


def test_gitea_only_repos_are_never_touched():
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    _, calls, _ = run(gh=gh, gitea=gitea)
    assert not [c for c in calls if "keepme" in c]


def test_pin_wins_over_the_computed_authority():
    cfg = org_cfg(repos={"willikins": {"tier": "github-preferred", "pin_authority": "github"}})
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    run(cfg=cfg, gh=gh, gitea=gitea)
    assert gh.vars[("willikins", "CI_AUTHORITY")] == "github"
    assert gitea.repo_vars[("willikins", "CI_AUTHORITY")] == "github"


def test_backstop_flips_and_reruns_on_gitea():
    runs = {"willikins": [dict(_runs()[0])]}
    gh = FakeGH([], usage=[], runs=runs, ann={9001: _fx("annotations.json")["spend"]},
                files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    st = {}
    res, calls, _ = run(gh=gh, gitea=gitea, st=st)
    assert gitea.repo_vars[("willikins", "CI_AUTHORITY")] == "gitea"
    assert ("gitea", "branch-create", "willikins", "sync-rerun-aaaaaaaaaaaa", _runs()[0]["head_sha"]) in calls
    assert 9001 in st["handled"]
    # handled: the next run sees no backstop hit
    gh.calls = gitea.calls = []
    w.run_org("derio-net", org_cfg(), gh, gitea, st, NOW, FakeNotifier(), LABELS, log=lambda s: None)
    assert not [c for c in gitea.calls if c[1] == "branch-create"]


def test_old_rerun_branches_are_deleted():
    gh = FakeGH([], usage=[], gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    st = {"rerun": {"willikins/sync-rerun-old": "2026-10-17T11:00:00Z",
                    "willikins/sync-rerun-new": "2026-10-18T11:00:00Z"}}
    gitea.branches = {"willikins": {
        "sync-rerun-old": {"name": "sync-rerun-old", "commit": {"timestamp": "2026-10-17T11:00:00Z"}},
        "sync-rerun-new": {"name": "sync-rerun-new", "commit": {"timestamp": "2026-10-18T11:00:00Z"}},
        "main": {"name": "main", "commit": {"timestamp": "2026-01-01T00:00:00Z"}},
    }}
    run(gh=gh, gitea=gitea, st=st)
    assert [c[3] for c in gitea.calls if c[1] == "branch-delete"] == ["sync-rerun-old"]


class Transport:
    """Scripted HTTP: maps (method, url-substring) -> (status, body)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers=None, body=None):
        self.calls.append((method, url, dict(headers or {}), body))
        for (m, frag), resp in self.routes.items():
            if m == method and frag in url:
                return resp(body) if callable(resp) else resp
        return 404, {"message": "Not Found"}


def test_github_client_headers_and_variable_upsert():
    t = Transport({
        ("PATCH", "/actions/variables/CI_AUTHORITY"): (404, {}),
        ("POST", "/actions/variables"): (201, {}),
    })
    c = w.GitHubClient("derio-net", "bill-tok", "auth-tok", http=t)
    c.set_variable("willikins", "CI_AUTHORITY", "github")
    assert [x[0] for x in t.calls] == ["PATCH", "POST"]
    method, url, headers, body = t.calls[0]
    assert url == "https://api.github.com/repos/derio-net/willikins/actions/variables/CI_AUTHORITY"
    assert headers["Authorization"] == "Bearer auth-tok"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert t.calls[1][3] == {"name": "CI_AUTHORITY", "value": "github"}


def test_github_client_patch_when_variable_exists():
    t = Transport({("PATCH", "/actions/variables/CI_AUTHORITY"): (204, None)})
    w.GitHubClient("derio-net", "b", "a", http=t).set_variable("willikins", "CI_AUTHORITY", "gitea")
    assert [x[0] for x in t.calls] == ["PATCH"]


def test_github_client_uses_billing_token_for_usage():
    t = Transport({("GET", "/settings/billing/usage"): (200, _fx("usage.json"))})
    c = w.GitHubClient("derio-net", "bill-tok", "auth-tok", http=t)
    items = c.billing_usage("derio-net", 2026, 10)
    assert len(items) == 6
    assert t.calls[0][1].startswith("https://api.github.com/organizations/derio-net/settings/billing/usage?")
    assert "year=2026" in t.calls[0][1] and "month=10" in t.calls[0][1]
    assert t.calls[0][2]["Authorization"] == "Bearer bill-tok"


def test_github_client_get_variable_404_is_none():
    t = Transport({})
    assert w.GitHubClient("o", "b", "a", http=t).get_variable("r", "X") is None


def test_github_client_workflow_files_reads_both_dirs():
    import base64
    wf = base64.b64encode(b"name: x\n").decode()
    t = Transport({
        ("GET", "/contents/.github/workflows/ci.yml"): (200, {"content": wf, "encoding": "base64"}),
        ("GET", "/contents/.github/workflows"): (200, [
            {"name": "ci.yml", "type": "file", "url": "https://api.github.com/repos/o/r/contents/.github/workflows/ci.yml"},
            {"name": "README.md", "type": "file", "url": "https://x/README.md"},
        ]),
    })
    files = w.GitHubClient("o", "b", "a", http=t).workflow_files("r")
    assert files == {".github/workflows/ci.yml": "name: x\n"}


def test_gitea_client_repo_variable_put_then_post():
    t = Transport({
        ("PUT", "/repos/derio-net/willikins/actions/variables/CI_AUTHORITY"): (404, {}),
        ("POST", "/repos/derio-net/willikins/actions/variables/CI_AUTHORITY"): (201, {}),
    })
    c = w.GiteaClient("http://g/api/v1", "gtok", http=t)
    c.set_repo_var("derio-net", "willikins", "CI_AUTHORITY", "gitea")
    assert [x[0] for x in t.calls] == ["PUT", "POST"]
    assert t.calls[0][2]["Authorization"] == "token gtok"
    assert t.calls[1][3] == {"value": "gitea"}


def test_gitea_client_reads_variable_data_and_org_variable():
    t = Transport({
        ("GET", "/repos/o/r/actions/variables/CI_AUTHORITY"): (200, {"name": "CI_AUTHORITY", "data": "gitea"}),
        ("GET", "/orgs/o/actions/variables/CI_BUDGET_MONTH"): (200, {"data": "2026-10"}),
    })
    c = w.GiteaClient("http://g/api/v1", "t", http=t)
    assert c.get_repo_var("o", "r", "CI_AUTHORITY") == "gitea"
    assert c.get_org_var("o", "CI_BUDGET_MONTH") == "2026-10"
    assert c.get_org_var("o", "NOPE") is None


def test_gitea_client_branch_create_tolerates_existing():
    t = Transport({("POST", "/repos/o/r/branches"): (409, {})})
    w.GiteaClient("http://g/api/v1", "t", http=t).create_branch("o", "r", "sync-rerun-abc", "deadbeef")
    assert t.calls[0][3] == {"new_branch_name": "sync-rerun-abc", "old_ref_name": "deadbeef"}


def test_http_error_other_than_404_raises():
    t = Transport({("GET", "/repos/o/r/actions/variables/X"): (500, {"message": "boom"})})
    with pytest.raises(w.HttpError):
        w.GitHubClient("o", "b", "a", http=t).get_variable("r", "X")
