#!/usr/bin/env python3
"""ci-budget monthly tier review (spec 2026-10-18 section 5, R15).

Once a month, reads each org's previous-month GitHub Actions usage, proposes
tier changes, and upserts one issue in derio-net/frank titled
`CI tier review <YYYY-MM>` (label `ci-tiers`). Report only: the operator acts by
editing tiers.yaml. Reuses watcher.py's usage functions and forges.py's clients.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import ci_gate_coverage
import forges
import watcher

LABEL = "ci-tiers"
ISSUE_REPO = "derio-net/frank"
HALF = 0.5


def previous_month(now: datetime) -> tuple[int, int]:
    return (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)


def title(month_label: str) -> str:
    return f"CI tier review {month_label}"


def repo_minutes(usage_items, exclude_repos=()) -> dict:
    """{bare repo name: {minutes, macos}} in weighted included minutes."""
    out: dict[str, dict] = {}
    for item in usage_items:
        name = watcher._repo_name(item)
        if not watcher._is_actions(item) or not name or name in exclude_repos:
            continue
        wt = watcher._weighted(item)
        if wt is None:
            continue
        rec = out.setdefault(name, {"minutes": 0.0, "macos": 0.0})
        rec["minutes"] += wt
        if watcher._sku(item) == "actions macos":
            rec["macos"] += wt
    return out


def analyse_org(org, ocfg, usage_items, public_repos) -> dict:
    tiers = ocfg.get("repos") or {}
    included = float(ocfg.get("included_minutes") or 0)
    threshold = float(ocfg.get("threshold_pct", 85))
    per_repo = repo_minutes(usage_items, public_repos)
    used = sum(v["minutes"] for v in per_repo.values())
    pct = used / included * 100 if included else 0.0
    preferred = {n for n, c in tiers.items() if c.get("tier") == "github-preferred"}
    pinned = watcher.pinned_share(usage_items, preferred, public_repos)
    consumers = sorted(
        ({"repo": n, "minutes": v["minutes"], "macos": v["macos"],
          "tier": (tiers.get(n) or {}).get("tier", "unlisted")} for n, v in per_repo.items()),
        key=lambda c: (-c["minutes"], c["repo"]),
    )
    props: list[dict] = []
    for name, cfg in tiers.items():
        if name in public_repos:
            props.append({"repo": name, "action": "remove",
                          "reason": "the repo is now public, so its minutes are free and it needs no tier"})
        elif cfg.get("tier") == "github-preferred" and included and per_repo.get(name, {}).get("minutes", 0) >= HALF * included:
            props.append({"repo": name, "action": "gitea-only",
                          "reason": f"alone used {per_repo[name]['minutes']:.0f} of the org's {included:.0f} included minutes (>=50%)"})
    for c in consumers:
        if c["tier"] != "unlisted" or c["minutes"] <= 0:
            continue
        if c["macos"] >= c["minutes"]:
            props.append({"repo": c["repo"], "action": "github-only",
                          "reason": f"billed {c['minutes']:.0f} minutes, all macOS (cannot run on Gitea)"})
        else:
            props.append({"repo": c["repo"], "action": "github-preferred",
                          "reason": f"billed {c['minutes']:.0f} minutes but is absent from tiers.yaml"})
    return {"org": org, "used": used, "included": included, "pct": pct, "threshold": threshold,
            "over_threshold": pct >= threshold, "pinned_share": pinned, "eligible_share": 1 - pinned if used else 0.0,
            "consumers": consumers, "proposals": props}


def gate_gaps(ocfg, gh, labels, public) -> dict:
    out: dict[str, list[str]] = {}
    for name, cfg in (ocfg.get("repos") or {}).items():
        tier = cfg.get("tier")
        if tier not in ("github-preferred", "gitea-only") or name in public:
            continue
        try:
            findings = ci_gate_coverage.check_workflows(
                gh.workflow_files(name), tier, list(cfg.get("gitea_secrets") or []), labels)
        except Exception as e:  # noqa: BLE001 - one unreadable repo must not sink the report
            out[name] = [f"could not read workflow files: {e}"]
            continue
        lines = sorted(f.line() for f in findings if f.verdict != "ok")
        if lines:
            out[name] = lines
    return out


def render(month_label: str, orgs: dict) -> str:
    L = [f"Tier review for {month_label}. Report only: act by editing `apps/ci-budget/tiers.yaml`.", ""]
    for org, res in orgs.items():
        L.append(f"## {org}")
        if "error" in res:
            L += [f"Could not be analysed: {res['error']}", ""]
            continue
        a, gaps = res["analysis"], res["gaps"]
        L.append(f"{a['used']:.0f} of {a['included']:.0f} included minutes used ({a['pct']:.1f}%, "
                 f"threshold {a['threshold']:.0f}%). Fallback-eligible share {a['eligible_share']:.0%}, "
                 f"GitHub-pinned share {a['pinned_share']:.0%}.")
        if a["over_threshold"]:
            L += ["", "Threshold crossed. Ranked consumers (the pinned minutes kept billing GitHub after the flip):"]
            L += [f"{i}. {c['repo']} [{c['tier']}]: {c['minutes']:.0f} min ({c['macos']:.0f} macOS)"
                  for i, c in enumerate(a["consumers"], 1)]
        L += ["", "Proposals:"]
        L += [f"- {p['repo']} -> {p['action']}: {p['reason']}" for p in a["proposals"]] or ["- none"]
        L += ["", "Gate coverage:"]
        L += [f"- {n}: {line}" for n, lines in sorted(gaps.items()) for line in lines] or ["- no gaps"]
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def upsert_issue(issues, issue_title: str, body: str) -> int:
    """Edit the issue with this exact title (any state), else create it."""
    for i in issues.list(LABEL):
        if i.get("title") == issue_title and "pull_request" not in i:
            issues.edit(i["number"], body)
            return i["number"]
    return issues.create(issue_title, body, LABEL)


def main(env=None, http=None, now=None, out=print) -> int:
    import yaml

    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    http = http or forges.default_http
    cfg = yaml.safe_load(open(env.get("TIERS_FILE", "/config/tiers.yaml")))
    labels = ci_gate_coverage.runner_labels(open(env.get("RUNNER_CONFIG", "/config/runner-config.yaml")).read())
    year, month = previous_month(now)
    label = f"{year:04d}-{month:02d}"
    results, failed = {}, False
    for org, ocfg in (cfg.get("orgs") or {}).items():
        try:
            k = watcher._env_key(org)
            gh = forges.GitHubClient(org, env.get(f"GH_BILLING_TOKEN_{k}"), env.get(f"GH_AUTHORITY_TOKEN_{k}"), http)
            public = gh.public_repos(org)
            analysis = analyse_org(org, ocfg, gh.billing_usage(org, year, month), public)
            results[org] = {"analysis": analysis, "gaps": gate_gaps(ocfg, gh, labels, public)}
        except Exception as e:  # noqa: BLE001
            failed = True
            results[org] = {"error": str(e)}
            out(f"ci-budget-report error org={org}: {e}")
    issues = forges.GitHubIssues(env.get("GH_ISSUES_TOKEN"), ISSUE_REPO, http)
    number = upsert_issue(issues, title(label), render(label, results))
    out(f"ci-budget-report result month={label} issue={number} orgs={len(results)} failed={int(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
