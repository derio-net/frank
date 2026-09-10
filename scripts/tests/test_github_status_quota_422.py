"""Tripwire: the github-status step must distinguish unactionable 422s from retryable errors.

Incident 2026-09-10. 292 of the cluster's 371 `Failed` pods were
`stoa-status-bridge-*-forward-pod`, minted at exactly 96/day (two every 30
minutes) and retained ~3 days by the TTL GC. Every one exited
`step-report exit=1`.

Root cause: GitHub caps commit statuses per (SHA, context). `agentic-stoa/cnc-fr`
main had been frozen at af90148b for 49 days while a Gitea Actions `pins-update`
workflow fired every 30 minutes against that same static SHA. The pair
(af90148b, `gitea-actions/pins-update / pins (push)`) accumulated ~900 statuses --
every other context on that commit had 16 -- until the cap was reached. GitHub
then answered every write:

    HTTP 422 {"errors": "Validation failed: This SHA and context has reached
              the maximum number of statuses."}

The step script ended with

    [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]

under `sh -e`, so ANY non-2xx failed the step. Correct for a transient error,
wrong for this one: the quota is spent permanently, so no retry can ever
succeed. One dead pod every 30 minutes, forever.

WHY THIS TEST EXECUTES THE SCRIPT INSTEAD OF GREPPING IT
--------------------------------------------------------
A textual assertion ("the file mentions 'maximum number of statuses'") passes on
an implementation that mentions the string and still exits 1 -- the exact
"reassurance of coverage without the fact of it" that
test_tekton_ignore_rules_no_arrays.py was widened to avoid. So this test pulls
the real step script out of the Task YAML and runs it under `sh` against a
stubbed `curl`, asserting on the exit status.

IT GUARDS BOTH DIRECTIONS, AND THE SECOND IS THE IMPORTANT ONE
--------------------------------------------------------------
Tolerating 422 wholesale would silently re-introduce the earlier
stoa-status-bridge incident, where Gitea's status vocabulary (`skipped`,
`warning`) is a superset of GitHub's and a `skipped` job 422'd -- a REAL bug that
stranded a `pending` status forever and was correctly fixed at the CEL layer by
mapping the state, not by swallowing the error. So `test_other_422_still_fails`
is not padding: it pins that only the quota message is forgiven.
"""

import os
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_PATH = REPO_ROOT / "apps/tekton/tasks/github-status.yaml"

# The exact body GitHub returns once (SHA, context) is saturated. Captured live
# from stoa-status-bridge-wjzjl-forward-pod on 2026-09-10.
QUOTA_BODY = (
    '{\n  "message": "Validation Failed",\n'
    '  "errors": "Validation failed: This SHA and context has reached the '
    'maximum number of statuses.",\n'
    '  "documentation_url": "https://docs.github.com/rest/commits/statuses",\n'
    '  "status": "422"\n}'
)

# A DIFFERENT 422 -- the shape of the skipped/warning vocabulary bug. Must stay fatal.
VOCAB_BODY = (
    '{\n  "message": "Validation Failed",\n'
    '  "errors": [{"resource": "Status", "code": "custom", '
    '"field": "state", "message": "state is not included in the list"}],\n'
    '  "status": "422"\n}'
)


def _step_script() -> str:
    """Extract the `report` step's shell script from the Task manifest."""
    doc = yaml.safe_load(TASK_PATH.read_text())
    assert doc["kind"] == "Task", f"{TASK_PATH} is not a Task"
    steps = doc["spec"]["steps"]
    report = next((s for s in steps if s["name"] == "report"), None)
    assert report is not None, "github-status Task has no step named 'report'"
    args = report["args"]
    assert len(args) == 1, f"expected a single script arg, got {len(args)}"
    return args[0]


def _run_step(tmp_path: Path, http_code: str, body: str) -> subprocess.CompletedProcess:
    """Run the real step script with `curl` stubbed to return (http_code, body)."""
    bindir = tmp_path / "bin"
    bindir.mkdir()

    # Hold the canned body in a real file so the stub reproduces it byte-for-byte
    # (embedding it in the shell source would mangle newlines into literal \n).
    body_file = tmp_path / "body.json"
    body_file.write_text(body)

    # Stub curl: honour `-o <path>` (copy the canned body there), print the code.
    stub = bindir / "curl"
    stub.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            out=""
            while [ $# -gt 0 ]; do
              case "$1" in
                -o) out="$2"; shift 2 ;;
                *)  shift ;;
              esac
            done
            [ -n "$out" ] && cat {str(body_file)!r} > "$out"
            printf '%s' {http_code!r}
            """
        )
    )
    stub.chmod(0o755)

    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bindir}:{env['PATH']}",
            "GITHUB_TOKEN": "stub-token",
            "REPO_FULL_NAME": "agentic-stoa/cnc-fr",
            "REVISION": "af90148b6c38abeadf2361fce2ca8bb86d4ad65a",
            "STATE": "success",
            "DESCRIPTION": "Successful in 8s",
            "CONTEXT": "gitea-actions/pins-update / pins (push)",
            "TARGET_URL": "http://192.168.55.209:3000/agentic-stoa/cnc-fr/actions/runs/2535",
            "GITHUB_API_URL": "https://api.github.com",
        }
    )
    return subprocess.run(
        ["/bin/sh", "-e", "-c", _step_script()],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_quota_exhausted_422_is_not_fatal(tmp_path):
    """The bug. A saturated (SHA, context) can never accept a retry -- don't fail."""
    result = _run_step(tmp_path, "422", QUOTA_BODY)
    assert result.returncode == 0, (
        "step failed on a permanently-unactionable 422 (status quota exhausted); "
        "this mints one dead pod per bridge invocation, forever.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_quota_exhausted_422_is_loud(tmp_path):
    """Tolerated must not mean silent -- the operator needs the reason in the log.

    The marker must be text the STEP emits, not text GitHub sent. An earlier
    draft of this assertion also accepted "maximum number of statuses", which
    appears in the response body the script already `cat`s -- so it passed while
    the bug was present and could never tell a loud implementation from a silent
    one. A green assertion inside a red suite is a bug in the assertion.
    """
    result = _run_step(tmp_path, "422", QUOTA_BODY)
    combined = (result.stdout + result.stderr).lower()
    assert "quota" in combined, (
        "the tolerated 422 produced no step-authored explanation; a swallowed "
        "error with no log line is how this goes unnoticed for another 39 days.\n"
        f"{result.stdout}"
    )


def test_other_422_still_fails(tmp_path):
    """Regression guard: the skipped/warning vocabulary 422 was a REAL bug."""
    result = _run_step(tmp_path, "422", VOCAB_BODY)
    assert result.returncode != 0, (
        "a non-quota 422 was swallowed. Gitea's status vocabulary is a superset "
        "of GitHub's, and that mismatch previously stranded a `pending` status "
        "forever; it must stay fatal so it surfaces."
    )


@pytest.mark.parametrize("code", ["401", "404", "500", "502"])
def test_other_errors_still_fail(tmp_path, code):
    """Every other non-2xx stays fatal."""
    result = _run_step(tmp_path, code, '{"message": "boom"}')
    assert result.returncode != 0, f"HTTP {code} was swallowed"


@pytest.mark.parametrize("code", ["200", "201"])
def test_success_still_passes(tmp_path, code):
    """The happy path is unchanged."""
    result = _run_step(tmp_path, code, '{"state": "success"}')
    assert result.returncode == 0, f"HTTP {code} failed the step"
