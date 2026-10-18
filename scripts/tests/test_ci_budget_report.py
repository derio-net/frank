"""Guard: the monthly CI tier-review report (spec 2026-10-18 section 5, R15)."""

import base64
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FILES = REPO_ROOT / "apps/ci-budget/files"


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


r = _load("report")

NOW = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)
LABELS = {"ubuntu-latest"}
UNGATED = "name: ci\non: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps: [{run: echo}]\n"


def it(repo, sku="Actions Linux", qty=100, org="derio-net"):
    return {"product": "actions", "sku": sku, "quantity": qty, "unitType": "Minutes",
            "organizationName": org, "repositoryName": repo}


def cfg(repos, included=1000, threshold=85):
    return {"included_minutes": included, "threshold_pct": threshold, "gitea_org": "o", "repos": repos}


# ---------------------------------------------------------------- minutes

def test_previous_month_wraps_the_year():
    assert r.previous_month(NOW) == (2026, 10)
    assert r.previous_month(datetime(2027, 1, 1, tzinfo=timezone.utc)) == (2026, 12)


def test_repo_minutes_weights_macos_normalises_names_and_skips_storage_and_public():
    items = [it("willikins", qty=30), it("derio-net/willikins", "Actions macOS", 5),
             it("pub", qty=500), {**it("willikins", "Actions storage", 9), "unitType": "GigabyteHours"}]
    got = r.repo_minutes(items, exclude_repos={"pub"})
    assert got == {"willikins": {"minutes": 80.0, "macos": 50.0}}


# ---------------------------------------------------------------- analysis

def analyse(items, repos, public=(), **kw):
    return r.analyse_org("derio-net", cfg(repos, **kw), items, set(public))


def props(a):
    return {(p["repo"], p["action"]) for p in a["proposals"]}


def test_shares_split_fallback_eligible_from_pinned():
    a = analyse([it("a", qty=60), it("a", "Actions macOS", 4), it("b", qty=100)],
                {"a": {"tier": "github-preferred"}, "b": {"tier": "github-only"}})
    assert a["used"] == 200.0
    assert a["pinned_share"] == pytest.approx(140 / 200)
    assert a["eligible_share"] == pytest.approx(60 / 200)


def test_preferred_repo_with_half_the_included_minutes_proposes_gitea_only():
    a = analyse([it("big", qty=500), it("small", qty=499)],
                {"big": {"tier": "github-preferred"}, "small": {"tier": "github-preferred"}})
    assert ("big", "gitea-only") in props(a)
    assert not any(p["repo"] == "small" for p in a["proposals"])
    assert all(p["reason"] for p in a["proposals"])


def test_billed_repo_absent_from_tiers_proposed_preferred_or_github_only_when_all_macos():
    a = analyse([it("new1", qty=10), it("new2", "Actions macOS", 3), it("new3", qty=1), it("new3", "Actions macOS", 1)],
                {"x": {"tier": "github-only"}})
    assert ("new1", "github-preferred") in props(a)
    assert ("new2", "github-only") in props(a)
    assert ("new3", "github-preferred") in props(a)


def test_unlisted_public_repo_is_not_proposed_and_listed_public_repo_is_removed():
    a = analyse([it("pub", qty=900), it("old", qty=1)],
                {"pub": {"tier": "github-preferred"}, "old": {"tier": "github-preferred"}}, public=["pub"])
    assert ("pub", "remove") in props(a)
    assert not any(p["repo"] == "pub" and p["action"] != "remove" for p in a["proposals"])
    assert a["used"] == 1.0


def test_unlisted_public_repo_never_billed_so_never_proposed():
    a = analyse([it("p2", qty=5)], {}, public=["p2"])
    assert a["proposals"] == []


def test_org_over_threshold_lists_ranked_consumers_and_pinned_share():
    a = analyse([it("a", qty=300), it("b", qty=600), it("c", qty=5)],
                {"a": {"tier": "github-preferred"}, "b": {"tier": "github-only"}}, included=1000, threshold=85)
    assert a["over_threshold"] is True
    assert [c["repo"] for c in a["consumers"]] == ["b", "a", "c"]
    assert a["pct"] == pytest.approx(90.5)
    below = analyse([it("a", qty=100)], {"a": {"tier": "github-preferred"}})
    assert below["over_threshold"] is False


# ---------------------------------------------------------------- gate coverage

class FakeGH:
    def __init__(self, files=None, public=(), boom=()):
        self.files, self.public, self.boom = files or {}, set(public), set(boom)

    def workflow_files(self, repo):
        if repo in self.boom:
            raise RuntimeError("403")
        return self.files.get(repo, {})


def test_gate_coverage_covers_preferred_and_gitea_only_but_not_github_only():
    repos = {"p": {"tier": "github-preferred"}, "g": {"tier": "gitea-only"}, "o": {"tier": "github-only"}}
    gh = FakeGH({k: {".github/workflows/ci.yml": UNGATED} for k in repos})
    gaps = r.gate_gaps(cfg(repos), gh, LABELS, public=set())
    assert set(gaps) == {"p", "g"}
    assert gaps["p"] == [".github/workflows/ci.yml:t: ungated"]


def test_gate_coverage_read_failure_is_reported_not_raised():
    gaps = r.gate_gaps(cfg({"p": {"tier": "github-preferred"}}), FakeGH(boom=["p"]), LABELS, public=set())
    assert "could not read" in gaps["p"][0]


# ---------------------------------------------------------------- rendering

def test_render_has_title_label_and_every_section():
    a = analyse([it("big", qty=900)], {"big": {"tier": "github-preferred"}})
    body = r.render("2026-10", {"derio-net": {"analysis": a, "gaps": {"big": ["w.yml:t: ungated"]}}})
    assert r.title("2026-10") == "CI tier review 2026-10"
    assert r.LABEL == "ci-tiers"
    for needle in ("derio-net", "big", "gitea-only", "ungated", "tiers.yaml", "Gate coverage"):
        assert needle in body


def test_render_notes_an_org_that_could_not_be_read():
    body = r.render("2026-10", {"derio-net": {"error": "HTTP 403"}})
    assert "HTTP 403" in body


# ---------------------------------------------------------------- issue upsert

class FakeIssues:
    def __init__(self, existing=()):
        self.issues = [dict(i) for i in existing]
        self.calls = []

    def list(self, label):
        self.calls.append(("list", label))
        return self.issues

    def create(self, title, body, label):
        self.calls.append(("create", title))
        self.issues.append({"number": 7, "title": title, "body": body})
        return 7

    def edit(self, number, body):
        self.calls.append(("edit", number))
        for i in self.issues:
            if i["number"] == number:
                i["body"] = body


def test_upsert_creates_when_absent_then_edits_not_duplicates():
    iss = FakeIssues()
    n1 = r.upsert_issue(iss, "CI tier review 2026-10", "v1")
    n2 = r.upsert_issue(iss, "CI tier review 2026-10", "v2")
    assert n1 == n2 == 7
    assert len(iss.issues) == 1 and iss.issues[0]["body"] == "v2"


def test_upsert_ignores_pull_requests_and_other_titles_and_matches_closed_issues():
    iss = FakeIssues([
        {"number": 1, "title": "CI tier review 2026-10", "pull_request": {}, "body": ""},
        {"number": 2, "title": "CI tier review 2026-09", "body": ""},
        {"number": 3, "title": "CI tier review 2026-10", "state": "closed", "body": ""},
    ])
    assert r.upsert_issue(iss, "CI tier review 2026-10", "x") == 3
    assert ("create", "CI tier review 2026-10") not in iss.calls


# ---------------------------------------------------------------- GitHubIssues client + main

def test_issues_client_lists_all_states_across_pages_and_patches_body():
    seen = []
    forges = sys.modules["forges"]

    def http(method, url, headers=None, body=None):
        seen.append((method, url, body))
        if method == "GET" and "page=1" in url:
            return 200, [{"number": i, "title": f"t{i}"} for i in range(100)]
        if method == "GET":
            return 200, [{"number": 100, "title": "last"}]
        return 200, {"number": 100}

    c = forges.GitHubIssues("tok", "derio-net/frank", http=http)
    assert len(c.list("ci-tiers")) == 101
    assert "state=all" in seen[0][1] and "labels=ci-tiers" in seen[0][1]
    c.edit(100, "b")
    assert seen[-1][0] == "PATCH" and seen[-1][1].endswith("/repos/derio-net/frank/issues/100")
    c.create("T", "B", "ci-tiers")
    assert seen[-1][2] == {"title": "T", "body": "B", "labels": ["ci-tiers"]}


def _b64(s):
    return base64.b64encode(s.encode()).decode()


def test_main_end_to_end_upserts_once_across_two_runs(tmp_path):
    tiers = tmp_path / "tiers.yaml"
    tiers.write_text("version: 1\norgs:\n  derio-net:\n    included_minutes: 1000\n    threshold_pct: 85\n"
                     "    gitea_org: derio-net\n    mode: dry-run\n    repos:\n      big: {tier: github-preferred}\n")
    runner = tmp_path / "runner.yaml"
    runner.write_text("runner:\n  labels:\n    - ubuntu-latest:docker://x\n")
    issues = []

    def http(method, url, headers=None, body=None):
        if "/settings/billing/usage" in url:
            return 200, {"usageItems": [it("derio-net/big", qty=800), it("stray", qty=3)]}
        if "/orgs/derio-net/repos" in url:
            return 200, []
        if url.endswith("/contents/.github/workflows"):
            return 200, [{"type": "file", "name": "ci.yml", "url": "http://f/ci"}]
        if "/contents/" in url and url.endswith(("/.gitea/workflows",)):
            return 404, {}
        if url == "http://f/ci":
            return 200, {"content": _b64(UNGATED)}
        if "/repos/derio-net/frank/issues" in url:
            if method == "GET":
                return 200, issues if "page=1" in url else []
            if method == "POST":
                issues.append({"number": 9, "title": body["title"], "body": body["body"]})
                return 201, {"number": 9}
            if method == "PATCH":
                issues[0]["body"] = body["body"]
                return 200, {"number": 9}
        raise AssertionError((method, url))

    env = {"TIERS_FILE": str(tiers), "RUNNER_CONFIG": str(runner), "GH_BILLING_TOKEN_DERIO_NET": "b",
           "GH_AUTHORITY_TOKEN_DERIO_NET": "a", "GH_ISSUES_TOKEN": "i"}
    out = []
    assert r.main(env=env, http=http, now=NOW, out=out.append) == 0
    assert r.main(env=env, http=http, now=NOW, out=out.append) == 0
    assert len(issues) == 1 and issues[0]["title"] == "CI tier review 2026-10"
    assert "big" in issues[0]["body"] and "stray" in issues[0]["body"] and "ungated" in issues[0]["body"]
    assert any("ci-budget-report" in line and "issue=9" in line for line in out)
