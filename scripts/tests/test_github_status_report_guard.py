"""github-status-report: the shared POST step, and its optional ordering guard.

The StepAction is the ONE place the GitHub commit-status POST lives. Two
callers:

- the `github-status` Task (every CI pipeline's status post) — no guard, so
  its behaviour is exactly what it was before the step moved;
- the stoa-status-bridge's `forward` task, which runs the Gitea current-state
  check as the step immediately before this one and passes `guard-file`. A
  file reading `true` means "this pending is stale, Gitea has moved past it":
  skip the POST. Anything else — missing file, `false`, unreadable — posts,
  because a guard that fails closed would swallow real statuses (frank#1029).

Runs the StepAction's real shell script with curl stubbed on PATH.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
STEPACTION = REPO / "apps/tekton/tasks/github-status-report.yaml"
TASK = REPO / "apps/tekton/tasks/github-status.yaml"


def _script() -> str:
    doc = yaml.safe_load(STEPACTION.read_text())
    assert doc["kind"] == "StepAction"
    assert doc["metadata"]["name"] == "github-status-report"
    return doc["spec"]["args"][0]


def _run(tmp_path: Path, guard: str | None):
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    calls = tmp_path / "curl.calls"
    stub = stub_dir / "curl"
    stub.write_text(
        "#!/bin/sh\n"
        f'echo called >> {calls}\n'
        'out=""\n'
        'while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; *) shift;; esac; done\n'
        '[ -n "$out" ] && echo "{}" > "$out"\n'
        "printf 201\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    guard_file = ""
    if guard is not None:
        guard_file = str(tmp_path / "superseded")
        if guard != "<missing>":
            Path(guard_file).write_text(guard)
    env = {
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "REPO_FULL_NAME": "derio-net/runs-fr",
        "REVISION": "a" * 40,
        "STATE": "pending",
        "DESCRIPTION": "d",
        "CONTEXT": "gitea-actions/x",
        "TARGET_URL": "",
        "GITHUB_API_URL": "https://api.github.com",
        "BEST_EFFORT": "false",
        "GUARD_FILE": guard_file,
        "GITHUB_TOKEN_DERIO_NET": "tok-net",
    }
    script = _script().replace("/tmp/resp", str(tmp_path / "resp"))
    proc = subprocess.run(
        ["/bin/sh", "-e", "-c", script], env=env, capture_output=True, text=True, cwd=tmp_path
    )
    return proc, calls.exists()


def test_superseded_pending_is_not_posted(tmp_path: Path) -> None:
    proc, posted = _run(tmp_path, "true")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not posted, "a stale pending reached GitHub after Gitea moved past it"
    assert "stale" in proc.stdout


@pytest.mark.parametrize("guard", ["false", "", "<missing>", None])
def test_anything_but_true_posts(tmp_path: Path, guard: str | None) -> None:
    # Fail-open: missing/empty/false guard, or no guard configured at all.
    proc, posted = _run(tmp_path, guard)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert posted


def test_github_status_task_delegates_without_a_guard() -> None:
    """Every CI pipeline posts through the Task; moving the step must not
    change what they do, so the Task passes no guard-file."""
    task = yaml.safe_load(TASK.read_text())
    (step,) = task["spec"]["steps"]
    assert step["ref"]["name"] == "github-status-report"
    names = {p["name"] for p in step.get("params", [])}
    assert "guard-file" not in names
    task_params = {p["name"] for p in task["spec"]["params"]}
    stepaction = yaml.safe_load(STEPACTION.read_text())
    # Every Task param is forwarded to the StepAction param of the same name.
    forwarded = {p["name"]: p["value"] for p in step["params"]}
    assert forwarded == {n: f"$(params.{n})" for n in task_params}
    assert task_params | {"guard-file"} == {p["name"] for p in stepaction["spec"]["params"]}
