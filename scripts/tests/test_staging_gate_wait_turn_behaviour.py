"""Execute resolve-contract's wait-turn step script for real (plan
2026-06-15-staging-vcluster-gate, phase 9), not just inspect its text.

Every other staging-gate guard for this step is structural (test_staging_gate_manifests.py:
step order, env var wiring, the RBAC Role). None of them runs the shell, so a loop that admits
cleanly could still spin forever, exit early on the wrong condition, or never notice a genuinely
older run. This stubs `kubectl` on PATH with a tiny script that returns canned, queued
PipelineRun listings (tab-separated name/creationTimestamp/conditionStatus, mirroring the real
jsonpath output) and executes the real script via `sh -c` -- same technique as
test_staging_gate_git_stepaction_behaviour.py for the git StepAction.

`WAIT_POLL_INTERVAL` is an (undocumented, non-Tekton-param) env override the script itself
supports via `${WAIT_POLL_INTERVAL:-10}` -- production always gets the 10s default; these tests
set it to 0 so a multi-iteration scenario doesn't cost the test 10s+ wall time.
"""

import os
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "apps/staging-gate/tekton/pipeline.yaml"


def _script() -> str:
    for doc in yaml.safe_load_all(PIPELINE.read_text()):
        if doc and doc.get("kind") == "Pipeline":
            resolve = next(t for t in doc["spec"]["tasks"] if t["name"] == "resolve-contract")
            wait = next(s for s in resolve["taskSpec"]["steps"] if s["name"] == "wait-turn")
            return wait["script"]
    raise AssertionError("resolve-contract's wait-turn step not found")


_STUB_KUBECTL = """#!/bin/sh
set -eu
if [ "$1" = "-n" ] && [ "$3" = "get" ] && [ "$4" = "pipelineruns" ]; then
  count=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
  count=$((count + 1))
  echo "$count" > "$COUNTER_FILE"
  max=$(wc -l < "$RESPONSES_LIST" | tr -d ' ')
  idx=$count
  if [ "$idx" -gt "$max" ]; then idx=$max; fi
  file=$(sed -n "${idx}p" "$RESPONSES_LIST")
  cat "$file"
  exit 0
fi
echo "stub kubectl: unhandled args: $*" >&2
exit 1
"""


def _setup_stub(tmp_path: Path, responses: list[str]) -> dict:
    """responses[i] is the raw TSV body kubectl returns on the (i+1)th call;
    calls beyond len(responses) reuse the last one."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "kubectl"
    stub.write_text(_STUB_KUBECTL)
    stub.chmod(0o755)

    responses_dir = tmp_path / "responses"
    responses_dir.mkdir()
    responses_list = tmp_path / "responses.txt"
    lines = []
    for i, body in enumerate(responses):
        f = responses_dir / f"call-{i}.tsv"
        f.write_text(body)
        lines.append(str(f))
    responses_list.write_text("\n".join(lines) + "\n")

    return {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RESPONSES_LIST": str(responses_list),
        "COUNTER_FILE": str(tmp_path / "counter"),
        "WAIT_POLL_INTERVAL": "0",
    }


def _run(env: dict, app: str, self_name: str, timeout: str) -> subprocess.CompletedProcess:
    run_env = dict(env, APP=app, SELF=self_name, WAIT_TIMEOUT=timeout)
    return subprocess.run(["sh", "-c", _script()], env=run_env, capture_output=True, text=True, timeout=30)


def _row(name: str, ts: str, status: str) -> str:
    return f"{name}\t{ts}\t{status}\n"


def test_proceeds_immediately_when_no_older_run_exists(tmp_path):
    env = _setup_stub(tmp_path, [_row("self-run", "2026-09-15T00:01:00Z", "Unknown")])

    result = _run(env, app="runs-fr", self_name="self-run", timeout="5")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "proceeding" in result.stdout


def test_waits_while_an_older_run_is_unfinished_then_proceeds(tmp_path):
    blocked = _row("older-run", "2026-09-15T00:00:00Z", "Unknown") + _row(
        "self-run", "2026-09-15T00:01:00Z", "Unknown"
    )
    done = _row("older-run", "2026-09-15T00:00:00Z", "True") + _row(
        "self-run", "2026-09-15T00:01:00Z", "Unknown"
    )
    env = _setup_stub(tmp_path, [blocked, blocked, done])

    result = _run(env, app="runs-fr", self_name="self-run", timeout="30")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "waiting on older run" in result.stdout
    assert "proceeding" in result.stdout
    calls = int((tmp_path / "counter").read_text())
    assert calls >= 3, f"expected the script to poll at least 3 times, got {calls}"


def test_does_not_wait_on_a_newer_run_or_a_different_app(tmp_path):
    # An OTHER run for the same app that is NEWER than self must not block; nor
    # should a run for a different app ever appear (the label selector already
    # scopes kubectl's own query -- this just proves the age comparison is
    # right when the stub still includes only same-app rows).
    rows = _row("self-run", "2026-09-15T00:01:00Z", "Unknown") + _row(
        "newer-run", "2026-09-15T00:02:00Z", "Unknown"
    )
    env = _setup_stub(tmp_path, [rows])

    result = _run(env, app="runs-fr", self_name="self-run", timeout="5")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "proceeding" in result.stdout


def test_times_out_when_an_older_run_never_finishes(tmp_path):
    blocked = _row("older-run", "2026-09-15T00:00:00Z", "Unknown") + _row(
        "self-run", "2026-09-15T00:01:00Z", "Unknown"
    )
    env = _setup_stub(tmp_path, [blocked])

    result = _run(env, app="runs-fr", self_name="self-run", timeout="1")

    assert result.returncode == 1, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "timed out" in result.stderr
