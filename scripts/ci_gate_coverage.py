#!/usr/bin/env python3
"""Gate-coverage checker for GitHub/Gitea dual-forge workflows.

Spec: docs/superpowers/specs/2026-10-18--cicd--github-preferred-gitea-fallback-design.md
section 6. Reports, per job, whether it carries one of the two job-level gates
(authority gate or GitHub pin) and whether an authority-gated job can actually
run on Frank's Gitea runner.

Usage:
    ci_gate_coverage.py <checkout-dir> --tier <t> [--gitea-secret NAME ...]
                        [--runner-config <path>]
Prints one line per non-ok finding; exits 1 if there is any.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

AUTHORITY_GATE = (
    "(vars.CI_AUTHORITY || 'github') == "
    "(github.server_url == 'https://github.com' && 'github' || 'gitea')"
)
GITHUB_PIN = "github.server_url == 'https://github.com'"
RERUN_BRANCHES = ("sync-pr-**", "sync-rerun-**")
DEFAULT_RUNNER_CONFIG = (
    Path(__file__).resolve().parents[1] / "apps/gitea-runner/manifests/files/config.yaml"
)


@dataclass(frozen=True)
class Finding:
    workflow: str
    job: str  # "" for a workflow-level finding
    verdict: str
    detail: str = ""

    def line(self) -> str:
        where = f"{self.workflow}:{self.job}" if self.job else self.workflow
        return f"{where}: {self.verdict}" + (f" ({self.detail})" if self.detail else "")


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _strip_expr(s: str) -> str:
    s = s.strip()
    m = re.fullmatch(r"\$\{\{(.*)\}\}", s, re.S)
    return m.group(1) if m else s


def gates(job_if) -> tuple[bool, bool]:
    """(authority_gated, github_pinned) for a job-level `if:` value."""
    if job_if is None:
        return False, False
    text = _squash(_strip_expr(str(job_if)))
    gate = _squash(AUTHORITY_GATE)
    authority = gate in text
    rest = text.replace(gate, "")
    return authority, _squash(GITHUB_PIN) in rest


def runner_labels(config_yaml: str) -> set[str]:
    labels = yaml.safe_load(config_yaml)["runner"]["labels"]
    return {str(label).split(":", 1)[0] for label in labels}


def _runs_on_labels(job: dict) -> list[str] | None:
    ro = job.get("runs-on")
    if ro is None:
        return None
    if isinstance(ro, dict):
        ro = ro.get("labels", [])
    return [str(x) for x in (ro if isinstance(ro, list) else [ro])]


def _verdict_runs_on(job: dict, labels: set[str]) -> tuple[str, str] | None:
    ro = _runs_on_labels(job)
    if ro is None:
        return None
    if any("${{" in x for x in ro):
        return "fallback-runs-on-expression", ", ".join(ro)
    unserved = [x for x in ro if x not in labels]
    if unserved:
        return "fallback-on-unserved-label", ", ".join(unserved)
    return None


def _job_text(job: dict) -> str:
    return yaml.dump(job)


def _verdict_secrets(job: dict, gitea_secrets: list[str]) -> tuple[str, str] | None:
    used = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", _job_text(job)))
    missing = sorted(used - {"GITHUB_TOKEN"} - set(gitea_secrets))
    if missing:
        return "fallback-secret-not-mirrored", ", ".join(missing)
    return None


def _verdict_github_token(job: dict) -> tuple[str, str] | None:
    text = _job_text(job)
    if not re.search(r"secrets\.GITHUB_TOKEN|github\.token", text):
        return None
    for step in job.get("steps") or []:
        run = str(step.get("run", ""))
        if re.search(r"(^|[\s;&|(])gh\s", run) or "api.github.com" in run:
            return "fallback-github-token-to-github", "gh/api.github.com with GITHUB_TOKEN"
        uses = str(step.get("uses", ""))
        repo = str((step.get("with") or {}).get("repository", ""))
        if uses.startswith("actions/checkout") and repo and "github.repository" not in repo:
            return "fallback-github-token-to-github", f"checkout of {repo}"
    return None


def _has_rerun_triggers(wf: dict) -> bool:
    """True when the workflow also fires on the sync-pr/sync-rerun branches."""
    on = wf.get("on", wf.get(True))
    if not isinstance(on, dict) or "push" not in on:
        return False
    push = on["push"]
    if not isinstance(push, dict) or "branches" not in push:
        return True  # no branch filter: every branch, including the sync ones
    return all(b in (push["branches"] or []) for b in RERUN_BRANCHES)


def _triggers_need_rerun(wf: dict) -> bool:
    on = wf.get("on", wf.get(True))
    if isinstance(on, str):
        on = [on]
    names = set(on) if isinstance(on, (list, dict)) else set()
    return bool(names & {"pull_request", "push"})


def _check_job(wfname, name, job, gitea_secrets, labels) -> tuple[list[Finding], bool]:
    authority, pinned = gates(job.get("if"))
    if not authority and not pinned:
        return [Finding(wfname, name, "ungated")], False
    if pinned:
        return [Finding(wfname, name, "ok")], False
    problems = [
        v
        for v in (
            _verdict_runs_on(job, labels),
            _verdict_secrets(job, gitea_secrets),
            _verdict_github_token(job),
        )
        if v
    ]
    if not problems:
        return [Finding(wfname, name, "ok")], True
    return [Finding(wfname, name, v, d) for v, d in problems], True


def check_workflows(
    files: dict[str, str], tier: str, gitea_secrets: list[str], labels: set[str]
) -> list[Finding]:
    if tier == "github-only":
        return []
    out: list[Finding] = []
    for wfname, text in sorted(files.items()):
        wf = yaml.safe_load(text) or {}
        any_authority = False
        for name, job in (wf.get("jobs") or {}).items():
            found, authority = _check_job(wfname, name, job or {}, gitea_secrets, labels)
            out += found
            any_authority |= authority
        if any_authority and _triggers_need_rerun(wf) and not _has_rerun_triggers(wf):
            out.append(Finding(wfname, "", "missing-rerun-triggers"))
    return out


def load_checkout(root: Path) -> dict[str, str]:
    wfdir = root / ".github/workflows"
    files = {}
    for p in sorted(list(wfdir.glob("*.yml")) + list(wfdir.glob("*.yaml"))):
        files[p.name] = p.read_text()
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("checkout")
    ap.add_argument("--tier", required=True, choices=["github-only", "gitea-only", "github-preferred"])
    ap.add_argument("--gitea-secret", action="append", default=[])
    ap.add_argument("--runner-config", default=str(DEFAULT_RUNNER_CONFIG))
    args = ap.parse_args(argv)
    labels = runner_labels(Path(args.runner_config).read_text())
    findings = check_workflows(
        load_checkout(Path(args.checkout)), args.tier, args.gitea_secret, labels
    )
    bad = [f for f in findings if f.verdict != "ok"]
    for f in bad:
        print(f.line())
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
