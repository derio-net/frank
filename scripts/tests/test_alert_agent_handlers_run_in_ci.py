"""Guard: CI runs the alert-agent handler suite.

`apps/alert-agent/handlers/tests/` lives outside `scripts/tests/`, so the
`pytest scripts/tests/` tripwire run never collected it. Until frank#746 nothing
in CI exercised the cred-expiry warning de-dup — the logic that decides whether
an expiry warning is sent or skipped — and a regression there fails silently.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/repo-tripwires.yml"


def test_tripwires_job_runs_the_alert_agent_handler_suite():
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["tripwires"]["steps"]
    run = next(s["run"] for s in steps if s.get("name") == "Run tripwires")
    assert "set -o pipefail" in run, "without pipefail `pytest | tee` can never fail"
    assert "pytest apps/alert-agent/handlers/tests/" in run
    assert (REPO / "apps/alert-agent/handlers/tests").is_dir()
