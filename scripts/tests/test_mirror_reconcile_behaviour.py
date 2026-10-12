"""Behaviour test: run the shipped heads.sh + push.sh against local bare repos.

test_ci_mirror_resilience.py unit-tests the planner. This file runs the two
shell stages for real, because their git semantics are the part a regression
would hide in: the --force-with-lease expectation (including the empty
"must not exist yet" form), and the moved-since-planning skip. Both remotes
are file:// bare repos standing in for GitHub and Gitea. The scripts'
absolute mount paths are rewritten into a temp dir.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
RECONCILE = REPO / "apps" / "tekton" / "manifests" / "mirror-reconcile.yaml"
NAME = "agentic-stoa/r"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(*args: str, cwd: pathlib.Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    ).stdout.strip()


@pytest.fixture()
def world(tmp_path: pathlib.Path) -> dict:
    scripts = next(d for d in yaml.safe_load_all(RECONCILE.read_text())
                   if d and d["kind"] == "ConfigMap")["data"]
    dirs = {k: tmp_path / k for k in ("scripts", "plan", "work", "ssh-creds", "home")}
    for d in dirs.values():
        d.mkdir()
    (dirs["ssh-creds"] / "id_rsa").write_text("dummy\n")
    for name, body in scripts.items():
        for mount in ("scripts", "plan", "work", "ssh-creds"):
            body = body.replace(f"/{mount}/", f"{dirs[mount]}/")
        (dirs["scripts"] / name).write_text(body)

    # "GitHub": one repo with main at c2 and an open PR head at p1.
    src = tmp_path / "src"
    _git("init", "-q", "-b", "main", str(src))
    commits = {}
    for n in ("c1", "c2"):
        (src / "f").write_text(n)
        _git("add", "f", cwd=src)
        _git("commit", "-qm", n, cwd=src)
        commits[n] = _git("rev-parse", "HEAD", cwd=src)
    _git("checkout", "-qb", "pr", cwd=src)
    (src / "f").write_text("p1")
    _git("commit", "-qam", "p1", cwd=src)
    commits["p1"] = _git("rev-parse", "HEAD", cwd=src)
    github = tmp_path / "github" / f"{NAME}.git"
    gitea = tmp_path / "gitea" / f"{NAME}.git"
    for bare in (github, gitea):
        bare.parent.mkdir(parents=True, exist_ok=True)
        _git("init", "-q", "--bare", str(bare))
    _git("push", "-q", str(github), f"{commits['c2']}:refs/heads/main",
         f"{commits['p1']}:refs/pull/1/head", cwd=src)
    # "Gitea" is behind: main at c1, no sync-pr branch.
    _git("push", "-q", str(gitea), f"{commits['c1']}:refs/heads/main", cwd=src)

    env = {**os.environ, "HOME": str(dirs["home"]), "GITHUB_TOKEN": "x",
           "GITEA_SSH": f"file://{tmp_path / 'gitea'}", "GITHUB_GIT": f"file://{tmp_path / 'github'}",
           "MAIN_REPOS": NAME, "PR_REPOS": NAME, "GIT_CONFIG_NOSYSTEM": "1"}
    return {"dirs": dirs, "env": env, "c": commits, "gitea": gitea, "src": src}


def _run(world: dict, script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["sh", str(world["dirs"]["scripts"] / script)],
                          env=world["env"], capture_output=True, text=True)


def _plan(world: dict, *lines: str, errors: str = "") -> None:
    (world["dirs"]["plan"] / "plan.txt").write_text("".join(f"{l}\n" for l in lines))
    (world["dirs"]["plan"] / "errors.txt").write_text(errors)


def _head(world: dict, ref: str) -> str:
    return _git("--git-dir", str(world["gitea"]), "rev-parse", "--verify", "-q", ref)


def test_heads_records_gitea_branches_and_the_listed_marker(world: dict) -> None:
    res = _run(world, "heads.sh")
    assert res.returncode == 0, res.stderr
    lines = (world["dirs"]["plan"] / "gitea-heads.txt").read_text().splitlines()
    assert f"{NAME} __listed__ -" in lines
    assert f"{NAME} refs/heads/main {world['c']['c1']}" in lines


def test_push_repairs_main_and_creates_the_missing_sync_pr_branch(world: dict) -> None:
    c = world["c"]
    _plan(world,
          f"{NAME} refs/heads/main refs/heads/main {c['c2']} {c['c1']}",
          f"{NAME} refs/pull/1/head refs/heads/sync-pr-1 {c['p1']} -")
    res = _run(world, "push.sh")
    assert res.returncode == 0, res.stdout + res.stderr
    assert _head(world, "refs/heads/main") == c["c2"]
    assert _head(world, "refs/heads/sync-pr-1") == c["p1"]
    assert "result drift=2 repaired=2 skipped=0 failed=0 plan_errors=0" in res.stdout


def test_lease_refuses_to_overwrite_a_head_that_moved_after_planning(world: dict) -> None:
    c = world["c"]
    # A webhook sync pushed p1 to Gitea main after the plan observed c1.
    _git("push", "-q", "--force", str(world["gitea"]), f"{c['p1']}:refs/heads/main", cwd=world["src"])
    _plan(world, f"{NAME} refs/heads/main refs/heads/main {c['c2']} {c['c1']}")
    res = _run(world, "push.sh")
    assert res.returncode != 0
    assert _head(world, "refs/heads/main") == c["p1"], "the lease must protect the newer head"
    assert "push-failed" in res.stdout


def test_create_lease_refuses_when_the_branch_appeared_meanwhile(world: dict) -> None:
    c = world["c"]
    _git("push", "-q", str(world["gitea"]), f"{c['c2']}:refs/heads/sync-pr-1", cwd=world["src"])
    _plan(world, f"{NAME} refs/pull/1/head refs/heads/sync-pr-1 {c['p1']} -")
    res = _run(world, "push.sh")
    assert res.returncode != 0
    assert _head(world, "refs/heads/sync-pr-1") == c["c2"]


def test_a_github_head_that_moved_since_planning_is_skipped_not_pushed(world: dict) -> None:
    c = world["c"]
    _plan(world, f"{NAME} refs/heads/main refs/heads/main {c['p1']} {c['c1']}")  # GitHub main is c2
    res = _run(world, "push.sh")
    assert res.returncode == 0, res.stdout + res.stderr
    assert _head(world, "refs/heads/main") == c["c1"]
    assert "skipped=1" in res.stdout


def test_plan_errors_fail_the_job_after_repairs_run(world: dict) -> None:
    c = world["c"]
    _plan(world, f"{NAME} refs/heads/main refs/heads/main {c['c2']} {c['c1']}",
          errors="agentic-stoa/other: GitHub main unreadable\n")
    res = _run(world, "push.sh")
    assert res.returncode != 0
    assert _head(world, "refs/heads/main") == c["c2"], "one broken repo must not block the others"
    assert "plan_errors=1" in res.stdout
