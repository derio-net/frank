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
    return m.group(1).strip() if m else s


def _split_top(expr: str, op: str) -> list[str]:
    """Split on a two-char operator at paren depth 0, outside quotes."""
    parts, depth, quote, cur, i = [], 0, None, "", 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            cur += ch
        elif ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif depth == 0 and expr.startswith(op, i):
            parts.append(cur)
            cur = ""
            i += len(op)
            continue
        else:
            cur += ch
        i += 1
    parts.append(cur)
    return [p.strip() for p in parts]


def _unwrap(expr: str) -> str:
    """Strip parens that wrap the WHOLE expression."""
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth, quote = 0, None
        for i, ch in enumerate(expr):
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(expr) - 1:
                    return expr
        expr = expr[1:-1].strip()
    return expr


def conjuncts(job_if) -> list[str]:
    """Top-level `&&` conjuncts of an `if:`; an expression with a top-level
    `||` is not a conjunction, so it comes back as a single conjunct."""
    if job_if is None:
        return []
    expr = _unwrap(_strip_expr(str(job_if)))
    if len(_split_top(expr, "||")) > 1:
        return [expr]
    return [_unwrap(c) for c in _split_top(expr, "&&")]


_GATE = _squash(AUTHORITY_GATE)
_PIN = _squash(GITHUB_PIN)


def gates(job_if) -> tuple[bool, bool, bool]:
    """(authority_gated, github_pinned, malformed) for a job-level `if:`.

    A gate counts only as an exact top-level conjunct. Any conjunct that
    mentions CI_AUTHORITY without being the exact gate is malformed.
    """
    authority = pinned = malformed = False
    for c in conjuncts(job_if):
        sq = _squash(c)
        if sq == _GATE:
            authority = True
        elif sq == _PIN:
            pinned = True
        elif "ci_authority" in c.lower():
            malformed = True
    return authority, pinned, malformed


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


def _text(*objs) -> str:
    return "\n".join(yaml.dump(o) for o in objs if o)


_SECRET_RE = re.compile(r"secrets\.([A-Za-z0-9_]+)|secrets\[\s*['\"]([A-Za-z0-9_]+)['\"]\s*\]")
_TOKEN_RE = re.compile(
    r"secrets\.GITHUB_TOKEN|secrets\[\s*['\"]GITHUB_TOKEN['\"]\s*\]|github\.token"
)
_GH_CMD_RE = re.compile(r"(^|[\s;&|(`])gh\s")


def _verdict_secrets(job: dict, wf: dict, gitea_secrets: list[str]) -> tuple[str, str] | None:
    text = _text(job, wf.get("env"), wf.get("defaults"))
    used = {a or b for a, b in _SECRET_RE.findall(text)}
    missing = sorted(used - {"GITHUB_TOKEN"} - set(gitea_secrets))
    if "uses" in job and job.get("secrets") == "inherit":
        missing.append("inherit")
    if missing:
        return "fallback-secret-not-mirrored", ", ".join(missing)
    return None


def _verdict_github_token(job: dict, wf: dict) -> tuple[str, str] | None:
    ambient = _text(job.get("env"), wf.get("env"), wf.get("defaults"))
    job_token = bool(_TOKEN_RE.search(_text(job)) or _TOKEN_RE.search(ambient))
    if not job_token:
        return None
    for step in job.get("steps") or []:
        if _TOKEN_RE.search(_text(step.get("with"))):
            return "fallback-github-token-to-github", f"step with: {step.get('uses', '')}"
        run = str(step.get("run", ""))
        if _GH_CMD_RE.search(run) or "api.github.com" in run:
            return "fallback-github-token-to-github", "gh/api.github.com with GITHUB_TOKEN"
        uses = str(step.get("uses", ""))
        repo = str((step.get("with") or {}).get("repository", ""))
        if uses.startswith("actions/checkout") and repo and "github.repository" not in repo:
            return "fallback-github-token-to-github", f"checkout of {repo}"
    return None


def _glob_re(pat: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        elif pat[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pat[i])
            i += 1
    return re.compile(out + r"\Z")


def _branch_matches(patterns, branch: str) -> bool:
    matched = False
    for pat in patterns or []:
        neg = str(pat).startswith("!")
        if _glob_re(str(pat)[1:] if neg else str(pat)).match(branch):
            matched = not neg
    return matched


SYNC_SAMPLES = ("sync-pr-1", "sync-rerun-abc")


def _has_rerun_triggers(wf: dict) -> bool:
    """True when pushes to the sync-pr/sync-rerun branches fire the workflow."""
    on = wf.get("on", wf.get(True))
    if isinstance(on, str):
        return on == "push"
    if isinstance(on, list):
        return "push" in on
    if not isinstance(on, dict) or "push" not in on:
        return False
    push = on["push"]
    if not isinstance(push, dict) or not push:
        return True
    if "branches" in push:
        return all(_branch_matches(push["branches"], b) for b in SYNC_SAMPLES)
    if "branches-ignore" in push:
        return not any(_branch_matches(push["branches-ignore"], b) for b in SYNC_SAMPLES)
    # tag-only filters never fire on a branch push
    return not ({"tags", "tags-ignore"} & set(push))


def _triggers_need_rerun(wf: dict) -> bool:
    on = wf.get("on", wf.get(True))
    if isinstance(on, str):
        on = [on]
    names = set(on) if isinstance(on, (list, dict)) else set()
    return bool(names & {"pull_request", "push"})


def _callee_problem(job: dict, labels: set[str], files: dict[str, str]) -> tuple[str, str] | None:
    uses = str(job.get("uses", ""))
    if not uses.startswith("./.github/workflows/"):
        return None
    want = Path(uses).name
    for key, text in files.items():
        if Path(key).name == want:
            for name, cj in ((yaml.safe_load(text) or {}).get("jobs") or {}).items():
                v = _verdict_runs_on(cj or {}, labels)
                if v:
                    return v[0], f"{want}:{name}: {v[1]}"
    return None


def _check_job(wfname, name, job, wf, gitea_secrets, labels, files) -> tuple[list[Finding], bool]:
    authority, pinned, malformed = gates(job.get("if"))
    if malformed:
        return [Finding(wfname, name, "malformed-gate", str(job.get("if")))], False
    if not authority and not pinned:
        return [Finding(wfname, name, "ungated")], False
    if pinned:
        return [Finding(wfname, name, "ok")], False
    problems = [
        v
        for v in (
            _verdict_runs_on(job, labels),
            _callee_problem(job, labels, files),
            _verdict_secrets(job, wf, gitea_secrets),
            _verdict_github_token(job, wf),
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
            found, authority = _check_job(
                wfname, name, job or {}, wf, gitea_secrets, labels, files
            )
            out += found
            any_authority |= authority
        if any_authority and _triggers_need_rerun(wf) and not _has_rerun_triggers(wf):
            out.append(Finding(wfname, "", "missing-rerun-triggers"))
    return out


def load_checkout(root: Path) -> dict[str, str]:
    files = {}
    for d in (".github/workflows", ".gitea/workflows"):
        wfdir = root / d
        for p in sorted(list(wfdir.glob("*.yml")) + list(wfdir.glob("*.yaml"))):
            files[f"{d}/{p.name}"] = p.read_text()
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
