"""Guard: apps/ci-budget/tiers.yaml (spec 2026-10-18 section 1)."""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TIERS = REPO_ROOT / "apps/ci-budget/tiers.yaml"
RECONCILE = REPO_ROOT / "apps/tekton/manifests/mirror-reconcile.yaml"

PREFERRED = {
    "derio-net": {
        "willikins", "herdr-vertical-tabs", "presentation-craft",
        "vibe-kanban", "runs-fr",
    },
    "derio-homelab": {
        "proxmox-cluster", "omada-controller", "homelab", "ansible-pihole",
    },
}


def _cfg():
    return yaml.safe_load(TIERS.read_text())


def _main_repos():
    for doc in yaml.safe_load_all(RECONCILE.read_text()):
        if not doc:
            continue
        text = yaml.dump(doc)
        if "MAIN_REPOS" not in text:
            continue
        def walk(o):
            if isinstance(o, dict):
                if o.get("name") == "MAIN_REPOS" and "value" in o:
                    yield o["value"]
                for v in o.values():
                    yield from walk(v)
            elif isinstance(o, list):
                for v in o:
                    yield from walk(v)
        for v in walk(doc):
            return v.split()
    raise AssertionError("MAIN_REPOS not found")


def test_orgs_and_budget_fields():
    cfg = _cfg()
    assert cfg["version"] == 1
    assert set(cfg["orgs"]) == {"derio-net", "derio-homelab", "agentic-stoa"}
    for name, org in cfg["orgs"].items():
        assert org["included_minutes"] == 2000, name
        assert org["threshold_pct"] == 85, name
        assert org["gitea_org"], name
        assert org["mode"] in {"dry-run", "live"}, name
        assert org["mode"] == "dry-run", f"{name} must ship as dry-run"


def test_repo_entries_are_valid():
    for org in _cfg()["orgs"].values():
        for repo, e in org["repos"].items():
            assert e["tier"] in {"github-only", "gitea-only", "github-preferred"}, repo
            assert e.get("pin_authority", "github") in {"github", "gitea"}, repo
            assert isinstance(e.get("gitea_secrets", []), list), repo


def test_github_preferred_sets():
    orgs = _cfg()["orgs"]
    for org, expected in PREFERRED.items():
        got = {r for r, e in orgs[org]["repos"].items() if e["tier"] == "github-preferred"}
        assert got == expected, org


def test_kid_laptops_is_gitea_only():
    assert _cfg()["orgs"]["derio-homelab"]["repos"]["kid-laptops"]["tier"] == "gitea-only"


def test_every_mirrored_stoa_repo_is_gitea_only():
    repos = _cfg()["orgs"]["agentic-stoa"]["repos"]
    stoa = {r.split("/", 1)[1] for r in _main_repos() if r.startswith("agentic-stoa/")}
    assert stoa
    assert set(repos) == stoa  # exact: no stale and no missing repo
    for r in stoa:
        assert repos[r]["tier"] == "gitea-only", r


def test_every_gitea_only_repo_is_mirrored():
    main = set(_main_repos())
    for org, o in _cfg()["orgs"].items():
        for repo, e in o["repos"].items():
            if e["tier"] == "gitea-only":
                assert f"{org}/{repo}" in main, f"{org}/{repo} not in MAIN_REPOS"


def test_no_unknown_keys():
    cfg = _cfg()
    assert set(cfg) <= {"version", "orgs", "readonly_secrets"}
    for name, org in cfg["orgs"].items():
        extra = set(org) - {"included_minutes", "threshold_pct", "gitea_org", "mode", "repos"}
        assert not extra, (name, extra)
        for repo, e in org["repos"].items():
            extra = set(e) - {"tier", "pin_authority", "gitea_secrets"}
            assert not extra, (name, repo, extra)


FORBIDDEN_SECRET = re.compile(r"PAT|WRITE|ADMIN|PUSH", re.I)


def test_gitea_secrets_are_declared_readonly():
    cfg = _cfg()
    allow = cfg["readonly_secrets"]
    for a in allow:
        assert set(a) == {"name", "repo", "kind", "note"}, a
        assert a["kind"] in {"deploy-key", "read-token"}, a
        assert a["note"], a
        assert not FORBIDDEN_SECRET.search(a["name"]), a
    declared = {(a["repo"], a["name"]) for a in allow}
    used = set()
    for org, o in cfg["orgs"].items():
        for repo, e in o["repos"].items():
            for n in e.get("gitea_secrets", []):
                assert not FORBIDDEN_SECRET.search(n), n
                used.add((f"{org}/{repo}", n))
    assert used == declared


def test_header_says_secrets_are_repo_level():
    head = TIERS.read_text().split("version:")[0].lower()
    assert "repository secret" in head and "that repo only" in head
