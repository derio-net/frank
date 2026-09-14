"""Execute the staging-gate-git StepAction's real script, not just inspect it.

Every other staging-gate guard is structural: YAML shape, string patterns, and
(out of band) a server-side admission dry-run. None of them runs the shell, so a
script that admits cleanly can still fail on the path it exists for. That is
what happened after the phase-8 review: push mode's retry rebased onto
origin/main, but the StepAction passed committer identity only as `-c user.*`
flags on `add`/`commit`. `git rebase` rewrites the commit and needs an identity
too. In the pod (alpine/git as uid 65532, no passwd entry, no gitconfig) that
rebase dies with `unable to auto-detect email address`, so a gate that loses a
push race fails instead of retrying. Reproduced in alpine/git:2.45.2 as uid
65532 on 2026-09-15.

Hermeticity: on a developer laptop or CI runner git may auto-detect an identity
from the host account, which would mask the bug. `user.useConfigOnly=true`
(injected through GIT_CONFIG_COUNT env, so no file is touched) makes git refuse
to guess on every host, exactly as the pod does.

Needs only `git` and `sh` on PATH, both present on the CI runner.
"""

import os
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
STEPACTIONS = REPO / "apps/staging-gate/tekton/stepactions.yaml"
SEED_ID = ["-c", "user.email=seed@example.invalid", "-c", "user.name=seed"]


def _script() -> str:
    for doc in yaml.safe_load_all(STEPACTIONS.read_text()):
        if doc and doc.get("kind") == "StepAction" and doc["metadata"]["name"] == "staging-gate-git":
            return doc["spec"]["script"]
    raise AssertionError("StepAction staging-gate-git not found")


def _pod_like_env(home: Path) -> dict:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        # Refuse to guess an identity, like uid 65532 with no passwd entry.
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "user.useConfigOnly",
        "GIT_CONFIG_VALUE_0": "true",
        "GITHUB_TOKEN": "not-a-real-token",
    }
    return env


def _git(*args: str, cwd: Path, env: dict) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
    assert out.returncode == 0, f"git {' '.join(args)} failed:\n{out.stderr}"
    return out.stdout.strip()


def _setup(tmp_path: Path, race: bool) -> tuple[Path, Path, dict]:
    """A bare 'origin', the gate's --depth 1 clone at $SCRATCH/frank, and
    optionally a racing commit pushed to main after the gate cloned."""
    home = tmp_path / "home"
    home.mkdir()
    env = _pod_like_env(home)
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    _git("init", "-q", "--bare", str(remote), cwd=tmp_path, env=env)
    _git("clone", "-q", str(remote), str(seed), cwd=tmp_path, env=env)
    (seed / "promoted.yaml").write_text("sha: null\n")
    (seed / "other.txt").write_text("b\n")
    _git(*SEED_ID, "add", ".", cwd=seed, env=env)
    _git(*SEED_ID, "commit", "-qm", "init", cwd=seed, env=env)
    _git("push", "-q", "origin", "HEAD:main", cwd=seed, env=env)

    frank = scratch / "frank"
    _git("clone", "-q", "--depth", "1", "--branch", "main", f"file://{remote}", str(frank),
         cwd=tmp_path, env=env)

    if race:
        (seed / "other.txt").write_text("b\nc\n")
        _git(*SEED_ID, "commit", "-qam", "racer", cwd=seed, env=env)
        _git("push", "-q", "origin", "HEAD:main", cwd=seed, env=env)

    return remote, scratch, env


def _run_push(scratch: Path, env: dict, message: str) -> subprocess.CompletedProcess:
    run_env = dict(env, MODE="push", SCRATCH=str(scratch), MSG=message, TARGET="promoted.yaml")
    return subprocess.run(["sh", "-c", _script()], env=run_env, capture_output=True, text=True,
                          timeout=120)


def _remote_log(remote: Path, env: dict) -> list[str]:
    return _git("--git-dir", str(remote), "log", "--format=%s", "main", cwd=remote.parent,
                env=env).splitlines()


def test_push_mode_retries_through_a_race_with_no_host_identity(tmp_path):
    remote, scratch, env = _setup(tmp_path, race=True)
    (scratch / "frank" / "promoted.yaml").write_text("sha: abc1234\n")

    result = _run_push(scratch, env, "gate: last-green runs-fr sha-abc1234 [skip ci]")

    assert result.returncode == 0, (
        "push mode must survive a non-fast-forward race by rebasing and retrying; "
        f"exit {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    log = _remote_log(remote, env)
    assert log[0] == "gate: last-green runs-fr sha-abc1234 [skip ci]", log
    assert "racer" in log, f"the racing commit must be preserved, not overwritten: {log}"
    shown = _git("--git-dir", str(remote), "show", "main:promoted.yaml", cwd=tmp_path, env=env)
    assert shown == "sha: abc1234", shown


def test_push_mode_is_a_no_op_when_the_target_is_unchanged(tmp_path):
    remote, scratch, env = _setup(tmp_path, race=False)
    before = _remote_log(remote, env)

    result = _run_push(scratch, env, "gate: should not appear")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert _remote_log(remote, env) == before, "an unchanged target must not create a commit"


def test_push_mode_never_writes_the_token_to_git_config(tmp_path):
    _, scratch, env = _setup(tmp_path, race=False)
    (scratch / "frank" / "promoted.yaml").write_text("sha: def5678\n")

    result = _run_push(scratch, env, "gate: token hygiene")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    config = (scratch / "frank" / ".git" / "config").read_text()
    assert env["GITHUB_TOKEN"] not in config, ".git/config must never contain the token value"
