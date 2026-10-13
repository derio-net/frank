"""Guard scripts/pr_ci_verdict.py — a PR with no checks must never read as passed.

frank#800: PR #797 showed "no checks reported" for eleven hours and was read as
clean. The cause was NOT that it was a draft (open drafts #839/#840 carry a
tripwires check) — it CONFLICTED with main from creation, and GitHub fires no
`pull_request` workflow while there is no `refs/pull/N/merge` to run against.
These fixtures are shaped like `gh pr view --json isDraft,mergeable,statusCheckRollup`.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _mod():
    spec = spec_from_file_location("pr_ci_verdict", REPO / "scripts/pr_ci_verdict.py")
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run(name, status="COMPLETED", conclusion="SUCCESS"):
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}


def _pr(mergeable="MERGEABLE", checks=(), draft=False):
    return {"isDraft": draft, "mergeable": mergeable, "statusCheckRollup": list(checks)}


def test_the_797_shape_is_conflicting_not_passed():
    verdict, _ = _mod().classify(_pr(mergeable="CONFLICTING", draft=True))
    assert verdict == "CONFLICTING"


def test_conflicting_wins_even_over_stale_green_checks():
    # Checks from an earlier, mergeable head can linger on a later conflicting
    # one; they verify nothing about the code that would merge.
    verdict, _ = _mod().classify(_pr(mergeable="CONFLICTING", checks=[_run("tripwires")]))
    assert verdict == "CONFLICTING"


def test_no_checks_on_a_mergeable_pr_is_its_own_verdict():
    verdict, _ = _mod().classify(_pr(checks=[]))
    assert verdict == "NO_CHECKS"


def test_unknown_mergeability_with_no_checks_is_not_passed():
    verdict, _ = _mod().classify(_pr(mergeable="UNKNOWN"))
    assert verdict == "UNKNOWN"


def test_a_draft_with_green_checks_passes():
    # Draft state is irrelevant — the #800 premise this test pins as false.
    verdict, _ = _mod().classify(_pr(draft=True, checks=[_run("tripwires")]))
    assert verdict == "PASSED"


def test_any_failure_fails():
    checks = [_run("tripwires"), _run("validate", conclusion="FAILURE")]
    verdict, msg = _mod().classify(_pr(checks=checks))
    assert verdict == "FAILED"
    assert "validate" in msg


def test_in_flight_checks_are_pending():
    checks = [_run("tripwires"), _run("validate", status="IN_PROGRESS", conclusion="")]
    verdict, _ = _mod().classify(_pr(checks=checks))
    assert verdict == "PENDING"


def test_skipped_and_neutral_count_as_non_failing():
    checks = [_run("tripwires"), _run("deploy-pages", conclusion="SKIPPED"), _run("x", conclusion="NEUTRAL")]
    verdict, _ = _mod().classify(_pr(checks=checks))
    assert verdict == "PASSED"


def test_commit_status_contexts_are_read_too():
    checks = [{"__typename": "StatusContext", "context": "gitea-actions/ci", "state": "FAILURE"}]
    verdict, msg = _mod().classify(_pr(checks=checks))
    assert verdict == "FAILED"
    assert "gitea-actions/ci" in msg


@pytest.mark.parametrize("verdict", ["CONFLICTING", "NO_CHECKS", "UNKNOWN", "PENDING", "FAILED"])
def test_only_passed_exits_zero(verdict):
    m = _mod()
    assert m.EXIT_CODES["PASSED"] == 0
    assert m.EXIT_CODES[verdict] != 0
