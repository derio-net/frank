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
    stoa = [r.split("/", 1)[1] for r in _main_repos() if r.startswith("agentic-stoa/")]
    assert stoa
    for r in stoa:
        assert repos.get(r, {}).get("tier") == "gitea-only", r
