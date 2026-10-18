"""Behaviour test: run the shipped heads.sh + push.sh against local bare repos.

test_ci_mirror_resilience.py unit-tests the planner. This file runs the two
shell stages for real, because their git semantics are the part a regression
would hide in: the --force-with-lease expectation (including the empty
"must not exist yet" form), and the moved-since-planning skip. Both remotes
are file:// bare repos standing in for GitHub and Gitea. The scripts'
absolute mount paths are rewritten into a temp dir.

Each test runs twice: once with the host's sh and git, and once inside the
production image (alpine/git:2.47.2, busybox ash) when Docker answers, so
a busybox-only incompatibility cannot ship green. CI has no Docker, so CI
runs the host variant only. What neither variant covers is the ssh and
https transports (file:// stands in for both).
"""
from __future__ import annotations

import functools
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
RECONCILE = REPO / "apps" / "tekton" / "manifests" / "mirror-reconcile.yaml"
NAME = "agentic-stoa/r"
IMAGE = "alpine/git:2.47.2"
SCRIPT_ENV = ("HOME", "GITHUB_TOKEN", "GITEA_SSH", "GITHUB_GIT", "MAIN_REPOS",
              "PR_REPOS", "GIT_CONFIG_NOSYSTEM", "DRY_RUN")

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


@functools.cache
def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        if subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode:
            return False
        return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True,
                              timeout=15).returncode == 0 or subprocess.run(
            ["docker", "pull", "-q", IMAGE], capture_output=True, timeout=300).returncode == 0
    except subprocess.TimeoutExpired:
        return False


@pytest.fixture(params=["host", "alpine"])
def runner(request) -> str:
    if request.param == "alpine" and not _docker_ok():
        pytest.skip("docker unavailable: the busybox variant runs where docker does")
    return request.param


def _git(*args: str, cwd: pathlib.Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    ).stdout.strip()


@pytest.fixture()
def world(tmp_path: pathlib.Path, runner: str) -> dict:
    tmp_path = tmp_path.resolve()  # docker bind mounts need the real path (/private/var on macOS)
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
    return {"dirs": dirs, "env": env, "c": commits, "gitea": gitea, "src": src,
            "runner": runner, "root": tmp_path}


def _run(world: dict, script: str, **extra: str) -> subprocess.CompletedProcess:
    env = {**world["env"], **extra}
    path = str(world["dirs"]["scripts"] / script)
    if world["runner"] == "host":
        return subprocess.run(["sh", path], env=env, capture_output=True, text=True)
    root = str(world["root"])
    cmd = ["docker", "run", "--rm", "-v", f"{root}:{root}", "--user", f"{os.getuid()}:{os.getgid()}",
           "--entrypoint", "sh"]
    for k in SCRIPT_ENV:
        if k in env:
            cmd += ["-e", f"{k}={env[k]}"]
    return subprocess.run(cmd + [IMAGE, path], capture_output=True, text=True, timeout=120)


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
    assert "drift=2 repaired=2 skipped=0 failed=0 plan_errors=0" in res.stdout
    assert list(world["dirs"]["work"].iterdir()) == [], "each repo's clone must be freed"


def test_dry_run_reports_the_plan_and_pushes_nothing(world: dict) -> None:
    c = world["c"]
    _plan(world, f"{NAME} refs/heads/main refs/heads/main {c['c2']} {c['c1']}")
    res = _run(world, "push.sh", DRY_RUN="1")
    assert res.returncode == 0, res.stdout + res.stderr
    assert _head(world, "refs/heads/main") == c["c1"]
    assert f"would-repair {NAME} refs/heads/main {c['c1']} -> {c['c2']}" in res.stdout
    assert "dry_run=1 drift=1 repaired=0" in res.stdout


def test_heads_leaves_an_unreadable_repo_unmarked(world: dict) -> None:
    res = _run(world, "heads.sh", MAIN_REPOS=f"{NAME} agentic-stoa/missing", PR_REPOS="")
    assert res.returncode == 0, res.stderr
    text = (world["dirs"]["plan"] / "gitea-heads.txt").read_text()
    assert f"{NAME} __listed__ -" in text
    assert "agentic-stoa/missing" not in text, "a failed listing must not read as 'no branches'"
    assert "heads-error agentic-stoa/missing" in res.stderr


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


def test_push_fetches_each_org_with_that_orgs_own_token(world: dict) -> None:
    """derio-homelab/kid-laptops is a different GitHub App installation from
    agentic-stoa: its token is the only one that can read it. Fetching it with
    the agentic-stoa token is a 404 on every drift, so the repo would be listed
    as covered and never actually repaired.

    A `git` shim on PATH records the credential each fetch carried, then runs the
    real git, so this checks what the shipped script sends, not what a config says.
    """
    if world["runner"] != "host":
        pytest.skip("the git shim is host-side; the alpine variant covers busybox sh, not auth")
    import base64

    c, root = world["c"], world["root"]
    for side in ("github", "gitea"):
        twin = root / side / "derio-homelab" / "k.git"
        twin.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root / side / "agentic-stoa" / "r.git", twin)
    shim = root / "shim"
    shim.mkdir()
    log = root / "fetch-auth.log"
    (shim / "git").write_text(
        f"#!/bin/sh\ncase \"$*\" in *http.extraHeader=*) printf '%s\\n' \"$*\" >> {log};; esac\n"
        f"exec {shutil.which('git')} \"$@\"\n"
    )
    (shim / "git").chmod(0o755)
    _plan(world,
          f"{NAME} refs/heads/main refs/heads/main {c['c2']} {c['c1']}",
          f"derio-homelab/k refs/heads/main refs/heads/main {c['c2']} {c['c1']}")

    res = _run(world, "push.sh", PATH=f"{shim}:{os.environ['PATH']}",
               GITHUB_TOKEN="stoa-tok", GITHUB_TOKEN_DERIO_HOMELAB="homelab-tok")
    assert res.returncode == 0, res.stdout + res.stderr

    def header(token: str) -> str:
        return "Authorization: Basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode()

    fetches = log.read_text().splitlines()
    stoa = next(l for l in fetches if "/agentic-stoa/r.git" in l)
    homelab = next(l for l in fetches if "/derio-homelab/k.git" in l)
    assert header("stoa-tok") in stoa and header("homelab-tok") not in stoa
    assert header("homelab-tok") in homelab and header("stoa-tok") not in homelab


def test_push_never_falls_back_to_another_orgs_token(world: dict) -> None:
    """An org whose own token is missing must fail ITS repos (no-token, failed=1),
    never be fetched with the agentic-stoa token: that is a guaranteed 404 and
    sends one org's credential to a repo it was not minted for."""
    if world["runner"] != "host":
        pytest.skip("the git shim is host-side")
    c, root = world["c"], world["root"]
    shim = root / "shim2"
    shim.mkdir()
    log = root / "fetch2.log"
    (shim / "git").write_text(
        f"#!/bin/sh\ncase \"$*\" in *http.extraHeader=*) printf '%s\\n' \"$*\" >> {log};; esac\n"
        f"exec {shutil.which('git')} \"$@\"\n"
    )
    (shim / "git").chmod(0o755)
    _plan(world, f"derio-net/k refs/heads/main refs/heads/main {c['c2']} {c['c1']}")
    res = _run(world, "push.sh", PATH=f"{shim}:{os.environ['PATH']}", GITHUB_TOKEN="stoa-tok")
    assert res.returncode != 0
    assert "no-token derio-net/k" in res.stdout
    assert "failed=1" in res.stdout
    assert not log.exists(), "nothing may be fetched with another org's token"
