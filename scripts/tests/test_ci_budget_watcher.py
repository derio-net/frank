"""Guard: the ci-budget watcher (spec 2026-10-18 section 4).

Part 1: the pure decision core.
Part 2: the ordered two-forge apply, against fake clients.
Part 3: state, notifications and the heartbeat line.
"""

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
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
    assert w.included_minutes_used(items) == 450


def test_included_minutes_excludes_public_repos():
    items = _fx("usage.json")["usageItems"]
    assert w.included_minutes_used(items, exclude_repos={"frank-public-thing"}) == 410


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
    # preferred = all three: only herdr's macOS (200 of 410) is pinned
    # (the owner/name row 'derio-net/willikins' counts as willikins)
    assert w.pinned_share(items, {"willikins", "vibe-kanban", "herdr-vertical-tabs"}, ex) == 200 / 410
    # only willikins preferred: vibe 100 + herdr 200 pinned of 400
    assert w.pinned_share(items, {"willikins"}, ex) == 300 / 410
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


def _jobs():
    return _fx("annotations.json")["jobs"]


def _pairs(kind, job="never_started"):
    return [(_jobs()[job], _fx("annotations.json")[kind])]


def _ann():
    return {9001: _pairs("spend"), 9002: _pairs("ordinary"), 9003: _pairs("spend"), 9004: _pairs("spend")}


def test_backstop_hits_selects_recent_spending_limit_failures():
    hits = w.backstop_hits(_runs(), _ann(), NOW, set())
    # 9001: recent + matches (case-insensitive 'Spending Limit').
    # 9002: older than 30 min and not a spending message.
    # 9003: before the UTC month start. 9004: not a failure.
    assert [r["id"] for r in hits] == [9001]


@pytest.mark.parametrize(
    "kind,job",
    [
        ("spend", "started"),                    # ::error:: spoof on a job that ran steps
        ("spoof_warning", "never_started"),      # log echo / ::warning:: level
        ("spoof_text", "never_started"),         # wrong sentence shape
        ("ordinary", "never_started"),
    ],
)
def test_backstop_rejects_spoofs(kind, job):
    runs = [_runs()[0]]
    assert w.backstop_hits(runs, {9001: _pairs(kind, job)}, NOW, set()) == []


def test_backstop_accepts_empty_runner_name_and_case_insensitive_text():
    runs = [_runs()[0]]
    assert [r["id"] for r in w.backstop_hits(runs, {9001: _pairs("spend", "never_started_empty_runner")}, NOW, set())] == [9001]


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
        return self.ann.get(run_id, [])  # [(job, annotations)] pairs

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
    gh = FakeGH([], usage=[], runs=runs, ann={9001: _pairs("spend")},
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
    assert len(items) == 7
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


# ---------------------------------------------------------------- part 3


def _state_run(st, now, mode="dry-run", notifier=None, gh=None, gitea=None):
    calls = []
    gh = gh or FakeGH(calls, usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                      gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = gitea or FakeGitea(calls, repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    gh.calls = gitea.calls = calls
    out = []
    w.run_org("derio-net", org_cfg(mode=mode), gh, gitea, st, now, notifier or FakeNotifier(), LABELS, log=out.append)
    return calls, out


def test_three_dry_run_passes_over_threshold_send_one_message():
    note = FakeNotifier()
    st = {}
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    for i in range(3):
        _state_run(st, NOW + timedelta(minutes=10 * i), notifier=note, gh=gh, gitea=gitea)
    assert len(note.sent) == 1
    assert "would move" in note.sent[0] and "pct=90.0" in note.sent[0]


def test_billing_read_hourly_not_every_run():
    st = {}
    gh = FakeGH([], usage=[], gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    reads = lambda: len([c for c in gh.calls if c[1] == "billing"])  # noqa: E731
    total = 0
    for minutes, expected in [(0, 1), (10, 1), (50, 1), (54, 1), (55, 2), (65, 2), (120, 3)]:
        gh.calls = gitea.calls = []
        _state_run(st, NOW + timedelta(minutes=minutes), gh=gh, gitea=gitea)
        total += reads()
        assert total == expected, minutes


def test_billing_reread_on_month_rollover():
    st = {"last_read": "2026-09-30T23:50:00Z", "pct": 99.0, "pinned_share": 0.0}
    gh = FakeGH([], usage=[], gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    calls, out = _state_run(st, utc(2026, 10, 1, 0, 5), gh=gh, gitea=gitea)
    assert [c for c in calls if c[1] == "billing"]
    assert st["pct"] == 0.0


def test_pending_backstop_forces_billing_read():
    st = {"last_read": "2026-10-18T11:59:00Z", "pct": 1.0, "pinned_share": 0.0}
    gh = FakeGH([], usage=[], runs={"willikins": [dict(_runs()[0])]},
                ann={9001: _pairs("spend")},
                files={"willikins": {"w.yml": GATED_WF}}, gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    calls, _ = _state_run(st, NOW, gh=gh, gitea=gitea)
    assert [c for c in calls if c[1] == "billing"]


def test_missing_telegram_secret_means_no_send_and_no_error():
    st = {}
    note = FakeNotifier(enabled=False)
    calls, out = _state_run(st, NOW, notifier=note)
    assert note.sent == []
    assert st.get("sent", []) == []  # nothing recorded: a later-configured bot still tells
    assert [l for l in out if "verdict=would-flip" in l]


def test_failed_send_is_retried_next_run():
    class Flaky(FakeNotifier):
        n = 0

        def send(self, text):
            Flaky.n += 1
            if Flaky.n == 1:
                raise OSError("telegram down")
            self.sent.append(text)

    st, note = {}, Flaky()
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    _state_run(st, NOW, notifier=note, gh=gh, gitea=gitea)
    _state_run(st, NOW + timedelta(minutes=10), notifier=note, gh=gh, gitea=gitea)
    assert len(note.sent) == 1


def test_exactly_one_heartbeat_line_per_org():
    import re
    for mode in ("dry-run", "live"):
        _, out = _state_run({}, NOW, mode=mode)
        beats = [l for l in out if "verdict=" in l]
        assert len(beats) == 1
        assert re.fullmatch(
            r"ci-budget-watcher verdict=(ok|flipped|would-flip|refused|error) org=derio-net pct=\d+\.\d mode=(dry-run|live)",
            beats[0],
        ), beats[0]


def test_error_run_still_emits_one_heartbeat():
    class Boom(FakeGH):
        def billing_usage(self, *a):
            raise RuntimeError("403")

    calls = []
    gh, gitea = Boom(calls), FakeGitea(calls)
    out = []
    res = w.run_org("derio-net", org_cfg(), gh, gitea, {}, NOW, FakeNotifier(), LABELS, log=out.append)
    assert res["failed"] and len([l for l in out if "verdict=" in l]) == 1
    assert "verdict=error" in [l for l in out if "verdict=" in l][0]


class FakeK8s:
    def __init__(self):
        self.cm = None
        self.calls = []

    def __call__(self, method, url, headers=None, body=None):
        self.calls.append((method, url, dict(headers or {}), body))
        assert url.endswith("/api/v1/namespaces/tekton-pipelines/configmaps" + ("" if method == "POST" else "/ci-budget-state"))
        if method == "GET":
            return (200, self.cm) if self.cm else (404, {})
        if method == "POST":
            self.cm = dict(body, metadata=dict(body["metadata"], resourceVersion="1"))
            return 201, self.cm
        if method == "PUT":
            assert body["metadata"]["resourceVersion"] == self.cm["metadata"]["resourceVersion"]
            self.cm = dict(body, metadata=dict(body["metadata"], resourceVersion="2"))
            return 200, self.cm
        raise AssertionError(method)


def test_state_round_trips_through_configmap():
    k = FakeK8s()
    s = w.ConfigMapState("tekton-pipelines", "ci-budget-state", "tok", http=k)
    assert s.load() == {}
    s.save({"derio-net": {"sent": ["a"], "pct": 3.5}})
    assert k.cm["kind"] == "ConfigMap" and k.cm["metadata"]["name"] == "ci-budget-state"
    s2 = w.ConfigMapState("tekton-pipelines", "ci-budget-state", "tok", http=k)
    assert s2.load() == {"derio-net": {"sent": ["a"], "pct": 3.5}}
    s2.save({"derio-net": {"sent": ["a", "b"]}})  # update path, resourceVersion carried
    assert json.loads(k.cm["data"]["state.json"]) == {"derio-net": {"sent": ["a", "b"]}}
    assert k.calls[0][2]["Authorization"] == "Bearer tok"


def test_telegram_notifier_enabled_only_with_both_secrets():
    assert not w.TelegramNotifier(None, "1").enabled
    assert not w.TelegramNotifier("t", "").enabled
    t = Transport({("POST", "/bott/sendMessage"): (200, {"ok": True})})
    n = w.TelegramNotifier("t", "42", http=t)
    assert n.enabled
    n.send("hi")
    assert t.calls[0][3] == {"chat_id": "42", "text": "hi"}


def test_main_runs_every_org_and_exits_nonzero_on_error(tmp_path, capsys):
    tiers = tmp_path / "tiers.yaml"
    tiers.write_text(
        "version: 1\norgs:\n"
        "  derio-net: {included_minutes: 2000, threshold_pct: 85, gitea_org: derio-net, mode: dry-run, repos: {}}\n"
        "  agentic-stoa: {included_minutes: 2000, threshold_pct: 85, gitea_org: agentic-stoa, mode: dry-run, repos: {}}\n"
    )
    runner = tmp_path / "runner.yaml"
    runner.write_text("runner:\n  labels: ['ubuntu-latest:docker://x']\n")
    k = FakeK8s()
    t = Transport({
        ("GET", "/organizations/derio-net/settings/billing/usage"): (200, {"usageItems": []}),
        ("GET", "/orgs/derio-net/repos"): (200, []),
    })

    def http(method, url, headers=None, body=None):
        return (k if "/api/v1/namespaces" in url else t)(method, url, headers, body)

    env = {"TIERS_FILE": str(tiers), "RUNNER_CONFIG": str(runner), "NAMESPACE": "tekton-pipelines",
           "SA_TOKEN": "sa", "GH_BILLING_TOKEN_DERIO_NET": "b"}
    rc = w.main(env=env, http=http, now=NOW)
    beats = [l for l in capsys.readouterr().out.splitlines() if "verdict=" in l]
    assert rc == 1
    assert len(beats) == 2
    assert "verdict=ok org=derio-net" in beats[0]
    assert "verdict=error org=agentic-stoa" in beats[1]  # no billing token for that org
    assert "derio-net" in json.loads(k.cm["data"]["state.json"])


# ------------------------------------------------ phase-3 review fixes


def _backstop_world(files=None, gh_val="github", gitea_val="github", cfg=None, mode="live", drop=()):
    runs = {"willikins": [dict(_runs()[0])]}
    gh = FakeGH([], usage=[], runs=runs, ann={9001: _pairs("spend")},
                files={"willikins": files or {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): gh_val}, drop=drop)
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): gitea_val}, drop=drop)
    st, note = {}, FakeNotifier()
    out = []
    res = w.run_org("derio-net", cfg or org_cfg(mode=mode), gh, gitea, st, NOW, note, LABELS, log=out.append)
    return res, gh, gitea, st, note


def test_rerun_created_when_already_at_gitea_on_both_sides():
    _, gh, gitea, st, note = _backstop_world(gh_val="gitea", gitea_val="gitea")
    assert [c for c in gitea.calls if c[1] == "branch-create"]
    assert "re-running on Gitea" in note.sent[0]


def test_failed_apply_leaves_backstop_unhandled_and_no_rerun():
    res, gh, gitea, st, note = _backstop_world(drop={("gitea", "willikins")})
    assert res["verdict"] == "error"
    assert 9001 not in st.get("handled", [])
    assert not [c for c in gitea.calls if c[1] == "branch-create"]
    assert "apply failed" in note.sent[0]


def test_refused_repo_gets_no_rerun_and_honest_text():
    res, gh, gitea, st, note = _backstop_world(files={"w.yml": UNGATED_WF})
    assert not [c for c in gitea.calls if c[1] == "branch-create"]
    assert any("refused" in m for m in note.sent)
    assert not any("re-running on Gitea" in m for m in note.sent)


def test_pinned_github_repo_gets_no_rerun_and_honest_text():
    cfg = org_cfg(repos={"willikins": {"tier": "github-preferred", "pin_authority": "github"}})
    res, gh, gitea, st, note = _backstop_world(cfg=cfg)
    assert not [c for c in gitea.calls if c[1] == "branch-create"]
    assert "pinned" in note.sent[0]


def test_dry_run_backstop_text_says_no_rerun():
    _, _, _, _, note = _backstop_world(mode="dry-run")
    assert "dry-run" in note.sent[0]


def test_move_to_github_is_never_refused_by_the_coverage_gate():
    gh = FakeGH([], usage=[], files={"willikins": {"w.yml": UNGATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "gitea"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "gitea"},
                      org_vars={"CI_BUDGET_MONTH": "2026-09"})
    res, calls, _ = run(gh=gh, gitea=gitea)
    assert res["verdict"] == "flipped"
    assert gh.vars[("willikins", "CI_AUTHORITY")] == "github"
    assert not [c for c in calls if c[1] == "files"]


def test_move_to_gitea_is_still_refused_by_the_coverage_gate():
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": UNGATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    res, calls, _ = run(gh=gh, gitea=gitea)
    assert res["verdict"] == "refused"


def test_unknown_rerun_branch_is_first_seen_now_never_aged_by_commit_time():
    gh = FakeGH([], usage=[], gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea.branches = {"willikins": {
        "sync-rerun-abc": {"name": "sync-rerun-abc", "commit": {"timestamp": "2020-01-01T00:00:00Z"}}}}
    st = {}
    run(gh=gh, gitea=gitea, st=st)
    assert not [c for c in gitea.calls if c[1] == "branch-delete"]
    assert st["rerun"]["willikins/sync-rerun-abc"] == "2026-10-18T12:00:00Z"
    # 24h+ later it is reaped
    gh.calls = gitea.calls = []
    w.run_org("derio-net", org_cfg(), gh, gitea, st, NOW + timedelta(hours=25), FakeNotifier(), LABELS, log=lambda s: None)
    assert [c[3] for c in gitea.calls if c[1] == "branch-delete"] == ["sync-rerun-abc"]


def test_three_tick_month_sequence():
    st, note = {}, FakeNotifier()
    gh = FakeGH([], usage=over_threshold_usage(), files={"willikins": {"w.yml": GATED_WF}},
                gh_vars={("willikins", "CI_AUTHORITY"): "github"})
    gitea = FakeGitea([], repo_vars={("willikins", "CI_AUTHORITY"): "github"})
    shared = []
    gh.calls = gitea.calls = shared

    def tick(now):
        del shared[:]
        return w.run_org("derio-net", org_cfg(), gh, gitea, st, now, note, LABELS, log=lambda s: None)

    # tick 1: over threshold -> stamp + flip
    assert tick(NOW)["verdict"] == "flipped"
    assert gitea.org_vars == {"CI_BUDGET_MONTH": "2026-10"}
    assert gh.vars[("willikins", "CI_AUTHORITY")] == "gitea"
    # tick 2: usage now low, same month -> stays gitea, no writes at all
    gh.usage = []
    assert tick(NOW + timedelta(hours=2))["verdict"] == "ok"
    assert w_writes(shared) == []
    assert gh.vars[("willikins", "CI_AUTHORITY")] == "gitea"
    # tick 3: next month -> back to github, GitHub written before Gitea
    assert tick(utc(2026, 11, 1, 0, 10))["verdict"] == "flipped"
    order = [c[0] for c in shared if c[1] == "set"]
    assert order == ["gh", "gitea"]
    assert gh.vars[("willikins", "CI_AUTHORITY")] == "github"
    assert gitea.repo_vars[("willikins", "CI_AUTHORITY")] == "github"


def w_writes(calls):
    return [c for c in calls if c[1] in ("set", "org-set", "branch-create", "branch-delete")]


def test_github_client_run_annotations_returns_job_annotation_pairs():
    jobs = _jobs()
    t = Transport({
        ("GET", "/check-runs/71/annotations"): (200, _fx("annotations.json")["spend"]),
        ("GET", "/check-runs/73/annotations"): (200, _fx("annotations.json")["ordinary"]),
        ("GET", "/actions/runs/9001/jobs"): (200, {"jobs": [jobs["never_started"], jobs["started"]]}),
    })
    pairs = w.GitHubClient("derio-net", "b", "a", http=t).run_annotations("willikins", 9001)
    assert [(j["id"], len(a)) for j, a in pairs] == [(71, 1), (73, 1)]
    assert pairs[0][0]["runner_name"] is None and pairs[1][0]["steps"]


# ------------------------------------------------ phase 5: runner probe
# Fixtures are captures from the live Gitea 1.25.4 admin Actions API
# (journal discovery gitea-runner-admin-api). The queue was empty at capture
# time, so the waiting-job tests re-status the one captured job object.

JOBS_URL = "http://g/api/v1/admin/actions/jobs?status=waiting&limit=50&page=%d"
RUNNERS_URL = "http://g/api/v1/admin/actions/runners?limit=50&page=%d"


def _waiting_job(created_at, labels=("ubuntu-latest",), attempt=1):
    job = _fx("gitea_admin_jobs_one.json")["jobs"][0]
    return dict(job, status="waiting", conclusion="", created_at=created_at, started_at=None,
                labels=list(labels), run_attempt=attempt)


def _runners():
    return _fx("gitea_admin_runners.json")["runners"]


def test_runner_probe_counts_online_runners_and_oldest_wait():
    jobs = [_waiting_job("2026-10-18T11:30:00Z"), _waiting_job("2026-10-18T11:55:00Z")]
    assert w.runner_probe(_runners(), jobs, NOW, LABELS) == {
        "runners_online": 1, "oldest_waiting_s": 1800, "waiting": 2, "unservable": 0}


def test_runner_probe_offline_runner_does_not_count_and_empty_queue_is_zero():
    runners = [dict(_runners()[0], status="offline")]
    assert w.runner_probe(runners, [], NOW, LABELS) == {
        "runners_online": 0, "oldest_waiting_s": 0, "waiting": 0, "unservable": 0}


def test_unservable_jobs_are_counted_apart_and_never_age_the_queue():
    jobs = [_waiting_job("2026-10-18T08:00:00Z", labels=("macos-latest",)),
            _waiting_job("2026-10-18T11:50:00Z", labels=("ubuntu-latest", "gpu"))]
    p = w.runner_probe(_runners(), jobs, NOW, LABELS)
    assert (p["waiting"], p["unservable"], p["oldest_waiting_s"]) == (0, 2, 0)


def test_reruns_do_not_age_the_queue_because_gitea_keeps_the_original_created():
    # Gitea 1.25.4 rerun resets only task_id/status/started/stopped on the job,
    # so created_at is the first attempt's.
    jobs = [_waiting_job("2026-10-18T06:00:00Z", attempt=2), _waiting_job("2026-10-18T11:50:00Z")]
    p = w.runner_probe(_runners(), jobs, NOW, LABELS)
    assert (p["waiting"], p["oldest_waiting_s"]) == (2, 600)


def test_created_at_with_a_non_utc_offset_is_aged_correctly():
    p = w.runner_probe(_runners(), [_waiting_job("2026-10-18T13:30:00+02:00")], NOW, LABELS)
    assert p["oldest_waiting_s"] == 1800


def test_runner_probe_line_omits_runners_online_when_version_lists_no_runners():
    base = {"oldest_waiting_s": 5, "waiting": 1, "unservable": 2}
    assert w.runner_probe_line(dict(base, runners_online=1)) == \
        "ci-runner-probe runners_online=1 oldest_waiting_s=5 waiting=1 unservable=2"
    assert w.runner_probe_line(dict(base, runners_online=None)) == \
        "ci-runner-probe oldest_waiting_s=5 waiting=1 unservable=2"


def test_gitea_client_reads_admin_actions_with_the_probe_token_and_exact_urls():
    t = Transport({
        ("GET", "/admin/actions/runners"): (200, _fx("gitea_admin_runners.json")),
        ("GET", "/admin/actions/jobs"): (200, _fx("gitea_admin_jobs_waiting_empty.json")),
    })
    c = w.GiteaClient("http://g/api/v1", "probe", t)
    assert c.list_admin_runners()[0]["status"] == "online"
    assert c.list_admin_waiting_jobs() == []
    assert [x[:2] for x in t.calls] == [("GET", RUNNERS_URL % 1), ("GET", JOBS_URL % 1)]
    assert all(call[2]["Authorization"] == "token probe" for call in t.calls)


def test_admin_listing_paginates_until_a_short_page():
    page1 = {"jobs": [_waiting_job("2026-10-18T11:00:00Z") for _ in range(50)]}
    page2 = {"jobs": [_waiting_job("2026-10-18T11:00:00Z") for _ in range(7)]}
    t = Transport({("GET", "page=1"): (200, page1), ("GET", "page=2"): (200, page2)})
    c = w.GiteaClient("http://g/api/v1", "probe", t)
    assert len(c.list_admin_waiting_jobs()) == 57
    assert [x[1] for x in t.calls] == [JOBS_URL % 1, JOBS_URL % 2]


def test_a_404_on_page_two_keeps_what_was_read_but_on_page_one_means_unsupported():
    page1 = {"runners": [_runners()[0] for _ in range(50)]}
    t = Transport({("GET", "page=1"): (200, page1)})  # page 2 -> 404
    assert len(w.GiteaClient("http://g/api/v1", "probe", t).list_admin_runners()) == 50
    assert w.GiteaClient("http://g/api/v1", "probe", Transport({})).list_admin_runners() is None


def test_runner_endpoint_missing_yields_no_runners_online():
    t = Transport({("GET", "/admin/actions/jobs"): (200, _fx("gitea_admin_jobs_waiting_empty.json"))})
    out = []
    w.log_runner_probe(w.GiteaClient("http://g/api/v1", "probe", t), NOW, LABELS, out.append)
    assert out == ["ci-runner-probe oldest_waiting_s=0 waiting=0 unservable=0"]


def test_runners_failure_still_logs_the_queue_line():
    t = Transport({
        ("GET", "/admin/actions/runners"): (500, {}),
        ("GET", "/admin/actions/jobs"): (200, {"jobs": [_waiting_job("2026-10-18T11:50:00Z")]}),
    })
    out = []
    w.log_runner_probe(w.GiteaClient("http://g/api/v1", "probe", t), NOW, LABELS, out.append)
    assert len(out) == 2
    assert out[0].startswith("ci-runner-probe-error runners: ") and "verdict" not in out[0]
    assert out[1] == "ci-runner-probe oldest_waiting_s=600 waiting=1 unservable=0"


def test_jobs_failure_still_logs_runners_online_with_a_trailing_field():
    t = Transport({
        ("GET", "/admin/actions/runners"): (200, _fx("gitea_admin_runners.json")),
        ("GET", "/admin/actions/jobs"): (500, {}),
    })
    out = []
    w.log_runner_probe(w.GiteaClient("http://g/api/v1", "probe", t), NOW, LABELS, out.append)
    assert out[0].startswith("ci-runner-probe-error jobs: ")
    assert out[1] == "ci-runner-probe runners_online=1 jobs=unavailable"


def _main_env(tmp_path, extra):
    tiers = tmp_path / "tiers.yaml"
    tiers.write_text("version: 1\norgs: {}\n")
    runner = tmp_path / "runner.yaml"
    runner.write_text("runner:\n  labels: ['ubuntu-latest:docker://x']\n")
    return {"TIERS_FILE": str(tiers), "RUNNER_CONFIG": str(runner), "SA_TOKEN": "sa", **extra}


def _main_http(t):
    k = FakeK8s()
    return lambda method, url, headers=None, body=None: (k if "/api/v1/namespaces" in url else t)(method, url, headers, body)


def test_main_logs_one_probe_line_when_the_probe_token_is_set(tmp_path, capsys):
    t = Transport({
        ("GET", "/admin/actions/runners"): (200, _fx("gitea_admin_runners.json")),
        ("GET", "/admin/actions/jobs?status=waiting"): (200, _fx("gitea_admin_jobs_waiting_empty.json")),
    })
    env = _main_env(tmp_path, {"GITEA_PROBE_TOKEN": "p"})
    assert w.main(env=env, http=_main_http(t), now=NOW) == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("ci-runner-probe")]
    assert lines == ["ci-runner-probe runners_online=1 oldest_waiting_s=0 waiting=0 unservable=0"]


def test_main_logs_a_probe_error_when_the_probe_token_is_absent(tmp_path, capsys):
    assert w.main(env=_main_env(tmp_path, {}), http=_main_http(Transport({})), now=NOW) == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("ci-runner-probe")]
    assert lines == ["ci-runner-probe-error no probe token"]
