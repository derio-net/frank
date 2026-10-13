#!/usr/bin/env python3
"""Say whether a PR's CI actually verified it — never read "no checks" as passed.

    python3 scripts/pr_ci_verdict.py <pr-number> [--repo owner/name]

Exit 0 only on PASSED. Every other verdict is non-zero and names why.

WHY (frank#800): PR #797 showed "no checks reported" for eleven hours and was
read as clean. It was suspected to be draft-suppression; it was not — open drafts
carry checks normally. The PR CONFLICTED with main from the moment it opened, and
GitHub runs `pull_request` workflows against `refs/pull/N/merge`, a ref that does
not exist while the PR conflicts. So: no event error, no queued run, no skipped
status — just nothing, which `gh pr checks` and the PR page both render as an
empty, red-X-free list. main has no required status checks, so nothing marks the
missing run as "Expected" either.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

EXIT_CODES = {
    "PASSED": 0,
    "FAILED": 1,
    "NO_CHECKS": 2,
    "CONFLICTING": 3,
    "PENDING": 4,
    "UNKNOWN": 5,
}

# Conclusions that do not fail a PR. Anything else completed is a failure.
_OK_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
_OK_STATES = {"SUCCESS"}
_PENDING_STATES = {"PENDING", "EXPECTED"}


def _check(entry: dict) -> tuple[str, str]:
    """Return (name, outcome) with outcome in ok | failed | pending."""
    if entry.get("__typename") == "StatusContext":
        name, state = entry.get("context", "?"), (entry.get("state") or "").upper()
        if state in _OK_STATES:
            return name, "ok"
        return name, "pending" if state in _PENDING_STATES else "failed"
    name = entry.get("name", "?")
    if (entry.get("status") or "").upper() != "COMPLETED":
        return name, "pending"
    return name, "ok" if (entry.get("conclusion") or "").upper() in _OK_CONCLUSIONS else "failed"


def classify(pr: dict) -> tuple[str, str]:
    """Classify `gh pr view --json mergeable,statusCheckRollup` output."""
    mergeable = (pr.get("mergeable") or "UNKNOWN").upper()
    checks = [_check(c) for c in pr.get("statusCheckRollup") or []]

    # Checked first: green runs from an earlier, mergeable head can linger on a
    # conflicting one, and they say nothing about the code that would merge.
    if mergeable == "CONFLICTING":
        return "CONFLICTING", (
            "PR conflicts with its base: GitHub cannot build refs/pull/N/merge, so NO "
            "pull_request workflow runs. Merge the base in and push; checks follow."
        )
    if not checks:
        if mergeable == "UNKNOWN":
            return "UNKNOWN", "mergeability not yet computed and no checks — re-query shortly."
        return "NO_CHECKS", "no checks reported — absence is not a pass. Is a workflow missing a trigger?"

    failed = [n for n, o in checks if o == "failed"]
    if failed:
        return "FAILED", "failing: " + ", ".join(failed)
    pending = [n for n, o in checks if o == "pending"]
    if pending:
        return "PENDING", "still running: " + ", ".join(pending)
    return "PASSED", f"{len(checks)} check(s) green"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pr")
    ap.add_argument("--repo", default=None)
    args = ap.parse_args(argv)
    cmd = ["gh", "pr", "view", args.pr, "--json", "mergeable,statusCheckRollup"]
    if args.repo:
        cmd += ["--repo", args.repo]
    pr = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
    verdict, message = classify(pr)
    print(f"{verdict}: {message}")
    return EXIT_CODES[verdict]


if __name__ == "__main__":
    sys.exit(main())
