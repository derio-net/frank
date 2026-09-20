"""Execute staging-gate-notify's message-builder script for real (plan
2026-06-15-staging-vcluster-gate, phase 9), not just inspect its text.

Structural tests already assert `parse_mode` never appears in the curl invocation and that a
`tr -d '<>&'` call exists somewhere in the script. Neither proves the SANITIZED value is what
actually reaches curl's `text=` field, nor that the "which task failed" logic picks the right
task. This stubs `curl` on PATH to record its own argv instead of making a network call, and
feeds app/sha containing `<`, `>`, `&` (the raw, unvalidated trigger-payload shape notify must
tolerate per its own header comment) plus a mixed set of task statuses.
"""

import os
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
TASKS = REPO / "apps/staging-gate/tekton/tasks.yaml"

_STUB_CURL = """#!/bin/sh
for a in "$@"; do
  printf '%s\\n' "$a" >> "$CURL_CALL_FILE"
done
exit 0
"""


def _script() -> str:
    for doc in yaml.safe_load_all(TASKS.read_text()):
        if doc and doc.get("kind") == "Task" and doc["metadata"]["name"] == "staging-gate-notify":
            return doc["spec"]["steps"][0]["script"]
    raise AssertionError("staging-gate-notify step not found")


def _run(tmp_path: Path, **status_overrides: str) -> tuple[subprocess.CompletedProcess, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "curl"
    stub.write_text(_STUB_CURL)
    stub.chmod(0o755)
    call_file = tmp_path / "curl-calls"

    statuses = {
        "RESOLVE_STATUS": "Succeeded",
        "BUMP_STATUS": "Succeeded",
        "AWAIT_STATUS": "Succeeded",
        "SMOKE_STATUS": "Failed",
        "PROMOTE_STATUS": "None",
    }
    statuses.update(status_overrides)

    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "CURL_CALL_FILE": str(call_file),
        "APP": "runs-fr",
        "SHA": "deadbee",
        "PIPELINE_RUN": "staging-gate-runs-fr-abc12",
        "TELEGRAM_TOKEN": "tok",
        "TELEGRAM_CHAT_ID": "12345",
        **statuses,
    }
    result = subprocess.run(["sh", "-c", _script()], env=env, capture_output=True, text=True, timeout=30)
    calls = call_file.read_text() if call_file.exists() else ""
    return result, calls


def test_names_app_sha_failing_task_and_pipelinerun():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        result, calls = _run(Path(d))

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    text_arg = next(line for line in calls.splitlines() if line.startswith("text="))
    assert "app=runs-fr" in text_arg
    assert "sha=deadbee" in text_arg
    assert "failing_task=run-smoke" in text_arg
    assert "pipelineRun=staging-gate-runs-fr-abc12" in text_arg


def test_identifies_the_first_failed_task_in_pipeline_order():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        result, calls = _run(
            Path(d),
            RESOLVE_STATUS="Succeeded",
            BUMP_STATUS="Failed",
            AWAIT_STATUS="None",
            SMOKE_STATUS="None",
            PROMOTE_STATUS="None",
        )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    text_arg = next(line for line in calls.splitlines() if line.startswith("text="))
    assert "failing_task=bump-staging" in text_arg


def test_reports_unknown_when_no_task_status_is_literally_failed():
    """Belt-and-braces case: $(tasks.status) said the run was red, but every
    individual task status handed to this script reads Succeeded/None (e.g. a
    future task added to the pipeline but not yet wired into notify's params).
    The script must not crash or fabricate a task name."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        result, calls = _run(
            Path(d),
            RESOLVE_STATUS="Succeeded",
            BUMP_STATUS="Succeeded",
            AWAIT_STATUS="Succeeded",
            SMOKE_STATUS="Succeeded",
            PROMOTE_STATUS="Succeeded",
        )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    text_arg = next(line for line in calls.splitlines() if line.startswith("text="))
    assert "failing_task=unknown" in text_arg


def test_strips_html_special_characters_from_app_and_sha():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        bin_dir = Path(d) / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "curl"
        stub.write_text(_STUB_CURL)
        stub.chmod(0o755)
        call_file = Path(d) / "curl-calls"

        env = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "HOME": str(d),
            "CURL_CALL_FILE": str(call_file),
            "APP": "runs<fr>&evil",
            "SHA": "dead&bee<f>",
            "PIPELINE_RUN": "pr-1",
            "TELEGRAM_TOKEN": "tok",
            "TELEGRAM_CHAT_ID": "12345",
            "RESOLVE_STATUS": "Failed",
            "BUMP_STATUS": "None",
            "AWAIT_STATUS": "None",
            "SMOKE_STATUS": "None",
            "PROMOTE_STATUS": "None",
        }
        result = subprocess.run(["sh", "-c", _script()], env=env, capture_output=True, text=True, timeout=30)
        calls = call_file.read_text() if call_file.exists() else ""

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    text_arg = next(line for line in calls.splitlines() if line.startswith("text="))
    for needle in ("<", ">", "&"):
        assert needle not in text_arg, f"unsanitized {needle!r} leaked into the message: {text_arg}"
    assert "app=runsfrevil" in text_arg
    assert "sha=deadbeef" in text_arg


def test_never_sets_parse_mode():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        result, calls = _run(Path(d))

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "parse_mode" not in calls, f"curl must never be invoked with parse_mode: {calls}"


def test_posts_to_the_telegram_sendmessage_endpoint_with_the_token_and_chat_id():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        result, calls = _run(Path(d))

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "https://api.telegram.org/bottok/sendMessage" in calls
    assert "chat_id=12345" in calls


def test_fails_loudly_when_the_telegram_credential_is_empty():
    """P9 review (I4, Important): staging-gate-telegram's ExternalSecret keys are
    `optional: true` in the notify Task's env now, so a not-yet-synced
    ExternalSecret leaves TELEGRAM_TOKEN/TELEGRAM_CHAT_ID empty rather than
    making the whole container un-startable (CreateContainerConfigError). The
    script itself must then fail loudly and clearly instead of POSTing to
    Telegram with an empty token/chat_id or crashing on an unbound variable."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        bin_dir = Path(d) / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "curl"
        stub.write_text(_STUB_CURL)
        stub.chmod(0o755)
        call_file = Path(d) / "curl-calls"

        env = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "HOME": str(d),
            "CURL_CALL_FILE": str(call_file),
            "APP": "runs-fr",
            "SHA": "deadbee",
            "PIPELINE_RUN": "pr-1",
            "TELEGRAM_TOKEN": "",
            "TELEGRAM_CHAT_ID": "",
            "RESOLVE_STATUS": "Succeeded",
            "BUMP_STATUS": "Succeeded",
            "AWAIT_STATUS": "Succeeded",
            "SMOKE_STATUS": "Failed",
            "PROMOTE_STATUS": "None",
        }
        result = subprocess.run(["sh", "-c", _script()], env=env, capture_output=True, text=True, timeout=30)

    assert result.returncode != 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert not call_file.exists(), (
        f"curl must never be invoked with an empty token/chat_id: {call_file.read_text() if call_file.exists() else ''}"
    )
    assert result.stderr.strip(), "must print a clear message when the credential is empty"
