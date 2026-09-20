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


def test_proceeds_after_a_few_retries_when_self_is_never_labelled(tmp_path):
    """P9 review (I1): every manual run (`tkn pipeline start`, phase 11's own
    Test Plan) is NOT labelled staging-gate/app -- only the TriggerTemplate
    sets that label. Without a bail-out, self would never appear in `rows` and
    the step would spin for the full waitTurnTimeoutSeconds (default 30min)
    before failing with a misleading timeout message. It must instead give up
    after a few short retries and proceed."""
    other_app_only = _row("some-other-run", "2026-09-15T00:00:00Z", "Unknown")
    env = _setup_stub(tmp_path, [other_app_only])

    result = _run(env, app="runs-fr", self_name="self-run", timeout="600")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "not labelled staging-gate/app" in result.stderr
    assert "serialization not enforced" in result.stderr
    calls = int((tmp_path / "counter").read_text())
    assert calls <= 5, f"expected a bounded number of retries, not a full spin to timeout, got {calls}"


def test_does_not_bail_out_early_once_self_is_found(tmp_path):
    """The self-not-found bail-out must not fire once self actually appears,
    even if it took a couple of polls to show up (informer/API propagation
    lag) -- distinguishing this from I1's case is the whole point of counting
    consecutive self-missing polls rather than any single condition."""
    missing = _row("some-other-run", "2026-09-15T00:00:00Z", "Unknown")
    found = _row("self-run", "2026-09-15T00:01:00Z", "Unknown")
    env = _setup_stub(tmp_path, [missing, found])

    result = _run(env, app="runs-fr", self_name="self-run", timeout="30")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "not labelled staging-gate/app" not in result.stderr
    assert "proceeding" in result.stdout


def test_waits_on_an_older_run_with_the_same_creation_timestamp_when_its_name_sorts_earlier(tmp_path):
    """P9 review (I2): creationTimestamp has one-second granularity, so two
    PipelineRuns created in the same second compare equal on the strict `<`
    the original script used -- both would see no older run and proceed
    concurrently. The tiebreak on name (`$2<selfts || ($2==selfts && $1<self)`)
    must treat a same-timestamp, earlier-sorting name as blocking."""
    same_ts = "2026-09-15T00:01:00Z"
    blocked = _row("staging-gate-runs-fr-aaaaa", same_ts, "Unknown") + _row(
        "staging-gate-runs-fr-bbbbb", same_ts, "Unknown"
    )
    done = _row("staging-gate-runs-fr-aaaaa", same_ts, "True") + _row(
        "staging-gate-runs-fr-bbbbb", same_ts, "Unknown"
    )
    env = _setup_stub(tmp_path, [blocked, blocked, done])

    result = _run(env, app="runs-fr", self_name="staging-gate-runs-fr-bbbbb", timeout="30")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "waiting on older run" in result.stdout
    assert "proceeding" in result.stdout


def test_does_not_wait_on_a_same_timestamp_run_whose_name_sorts_later(tmp_path):
    """The mirror of the above: a same-timestamp OTHER run whose name sorts
    LATER than self must never block self (the tiebreak is a total order, not
    a mutual exclusion)."""
    same_ts = "2026-09-15T00:01:00Z"
    rows = _row("staging-gate-runs-fr-aaaaa", same_ts, "Unknown") + _row(
        "staging-gate-runs-fr-zzzzz", same_ts, "Unknown"
    )
    env = _setup_stub(tmp_path, [rows])

    result = _run(env, app="runs-fr", self_name="staging-gate-runs-fr-aaaaa", timeout="5")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "proceeding" in result.stdout


def test_an_older_run_with_an_empty_condition_status_still_blocks(tmp_path):
    """P9 review (M8b): kubectl's jsonpath `{.status.conditions[-1:].status}`
    returns an EMPTY string (allowMissingKeys), not the literal text
    'Unknown', for a freshly-created PipelineRun with no conditions yet. The
    blocking predicate (`$3!='True' && $3!='False'`) must still treat that as
    unfinished."""
    blocked = _row("older-run", "2026-09-15T00:00:00Z", "") + _row(
        "self-run", "2026-09-15T00:01:00Z", "Unknown"
    )
    done = _row("older-run", "2026-09-15T00:00:00Z", "True") + _row(
        "self-run", "2026-09-15T00:01:00Z", "Unknown"
    )
    env = _setup_stub(tmp_path, [blocked, done])

    result = _run(env, app="runs-fr", self_name="self-run", timeout="30")

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "waiting on older run" in result.stdout
    assert "proceeding" in result.stdout
