"""ci-budget-watcher: GitHub-minutes budget watcher (spec 2026-10-18 section 4).

Runs as a CronJob (*/10) on stock python:3-alpine with PyYAML. All dates and
months are UTC. This module is split in three layers:

  1. pure decision functions (usage -> minutes, desired authority, backstop);
  2. an ordered two-forge apply driven through small client objects;
  3. state, notifications, heartbeat and the in-cluster clients.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone

import ci_gate_coverage
from forges import GiteaClient, GitHubClient, HttpError, default_http  # noqa: F401 - re-exported

# ---------------------------------------------------------------- layer 1

SKU_MULTIPLIER = {"actions linux": 1, "actions windows": 2, "actions macos": 10}
BACKSTOP_WINDOW = timedelta(minutes=30)
BACKSTOP_NEEDLE = "spending limit"
BACKSTOP_PREFIX = "the job was not started because"


def _sku(item: dict) -> str:
    return " ".join(str(item.get("sku", "")).lower().replace("_", " ").split())


def _is_actions(item: dict) -> bool:
    return str(item.get("product", "")).lower() == "actions"


def _weighted(item: dict) -> float | None:
    """Included-minute weight of one usage item; None when it is not minutes."""
    sku = _sku(item)
    if sku in SKU_MULTIPLIER:
        return float(item.get("quantity", 0)) * SKU_MULTIPLIER[sku]
    if "storage" in sku:
        return None
    raise ValueError(f"unknown Actions SKU {item.get('sku')!r}: refusing to guess a multiplier")


def _repo_name(item: dict) -> str:
    """repositoryName may arrive as 'owner/name'; tiers and exclusions use bare names."""
    return str(item.get("repositoryName", "")).rsplit("/", 1)[-1]


def included_minutes_used(usage_items, exclude_repos=()) -> float:
    """Included-minute consumption: Linux x1, Windows x2, macOS x10.

    Only Actions SKUs count; an unknown Actions SKU raises. `exclude_repos`
    removes public repos (their minutes are free and never draw on the quota).
    """
    total = 0.0
    for it in usage_items:
        if not _is_actions(it) or _repo_name(it) in exclude_repos:
            continue
        wt = _weighted(it)
        if wt is not None:
            total += wt
    return total


def pinned_share(usage_items, preferred_repos, exclude_repos=()) -> float:
    """Share of the weighted minutes that can never fall back to Gitea.

    Pinned = every minute of a repo that is not github-preferred, plus macOS
    minutes of a github-preferred repo.
    """
    total = pinned = 0.0
    for it in usage_items:
        if not _is_actions(it) or _repo_name(it) in exclude_repos:
            continue
        wt = _weighted(it)
        if wt is None:
            continue
        total += wt
        if _repo_name(it) not in preferred_repos or _sku(it) == "actions macos":
            pinned += wt
    return pinned / total if total else 0.0


def desired_authority(pct, threshold, backstop_hit, month_stamp, now_month, pin):
    """Return (authority, stamp). `stamp` = write CI_BUDGET_MONTH=now_month.

    A pin wins over everything and never stamps.
    """
    if pin:
        return pin, False
    if pct >= threshold or backstop_hit:
        return "gitea", month_stamp != now_month
    if month_stamp == now_month:
        return "gitea", False
    return "github", False


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _billing_block(job, anns) -> bool:
    if job.get("runner_name") or job.get("steps"):
        return False
    for a in anns:
        msg = str(a.get("message", "")).strip().lower()
        if (a.get("annotation_level") == "failure" and msg.startswith(BACKSTOP_PREFIX)
                and BACKSTOP_NEEDLE in msg):
            return True
    return False


def backstop_hits(runs, annotations, now, handled_ids):
    """Failed runs from the last 30 min, this UTC month, not yet handled, whose
    annotations say 'spending limit' (case-insensitive).

    `annotations` maps run id -> list of (job, [annotation]) pairs. GitHub's own
    annotation is a failure-level message "The job was not started because ...
    spending limit ..." on a job that never ran: no runner and no steps. A step
    can print the same words (`::error::`, `::warning::`, an echo), so all of
    level, sentence and the never-started job are required.
    """
    start = month_start(now)
    out = []
    for r in runs:
        if r.get("conclusion") != "failure" or r["id"] in handled_ids:
            continue
        created = parse_ts(r["created_at"])
        if created < start or now - created > BACKSTOP_WINDOW:
            continue
        if any(_billing_block(job, anns) for job, anns in annotations.get(r["id"], [])):
            out.append(r)
    return out


# ---------------------------------------------------------------- layer 2

AUTHORITY_VAR = "CI_AUTHORITY"
MONTH_VAR = "CI_BUDGET_MONTH"
BILLING_MAX_AGE = timedelta(minutes=55)
RERUN_MAX_AGE = timedelta(hours=24)
RERUN_PREFIX = "sync-rerun-"
SENT_KEEP = 300


class ReadbackError(RuntimeError):
    pass


def _iso(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def apply_authority(repo, desired, gh, gitea, gitea_org, gh_val, gitea_val):
    """Ordered two-forge write (R9): toward gitea the Gitea side first, toward
    github the GitHub side first; each write is read back before the next."""
    order = ("gitea", "github") if desired == "gitea" else ("github", "gitea")
    for forge in order:
        if (gitea_val if forge == "gitea" else gh_val) == desired:
            continue
        if forge == "gitea":
            gitea.set_repo_var(gitea_org, repo, AUTHORITY_VAR, desired)
            got = gitea.get_repo_var(gitea_org, repo, AUTHORITY_VAR)
        else:
            gh.set_variable(repo, AUTHORITY_VAR, desired)
            got = gh.get_variable(repo, AUTHORITY_VAR)
        if got != desired:
            raise ReadbackError(f"{repo}: {forge} {AUTHORITY_VAR} reads {got!r} after writing {desired!r}")


def coverage_gaps(repo, tier_cfg, gh, labels):
    findings = ci_gate_coverage.check_workflows(
        gh.workflow_files(repo), "github-preferred", list(tier_cfg.get("gitea_secrets") or []), labels
    )
    return sorted(f.line() for f in findings if f.verdict != "ok")


def _send(st, notifier, key, text):
    """Send once per key; unconfigured or failed sends are not recorded."""
    sent = st.setdefault("sent", [])
    if key in sent or not getattr(notifier, "enabled", False):
        return
    try:
        notifier.send(text)
    except Exception as e:  # noqa: BLE001 - a notification must never fail the run
        print(f"ci-budget-watcher notify-failed key={key} err={e}")
        return
    sent.append(key)
    del sent[:-SENT_KEEP]


def _need_billing(st, hits, now):
    last = st.get("last_read")
    if hits or not last or "pct" not in st:
        return True
    t = parse_ts(last)
    return now - t >= BILLING_MAX_AGE or (t.year, t.month) != (now.year, now.month)


def run_org(org, cfg, gh, gitea, st, now, notifier, labels, log=print):
    """One watcher pass over one org. Returns {verdict, pct, mode, failed}."""
    mode = cfg.get("mode", "dry-run")
    gitea_org = cfg["gitea_org"]
    threshold = cfg["threshold_pct"]
    now_month = now.strftime("%Y-%m")
    repos = cfg.get("repos") or {}
    preferred = {r: c for r, c in repos.items() if c.get("tier") == "github-preferred"}
    errors: list[str] = []
    refused: list[str] = []
    wanted: list[str] = []
    flipped: list[str] = []
    pct = float(st.get("pct", 0.0))
    try:
        # backstop candidates: cheap prefilter, then annotations for the few left
        handled = set(st.get("handled", []))
        candidates, ann = [], {}
        start = month_start(now)
        for repo in preferred:
            for r in gh.list_failed_runs(repo, now - BACKSTOP_WINDOW):
                created = parse_ts(r["created_at"])
                if (r.get("conclusion") != "failure" or r["id"] in handled
                        or created < start or now - created > BACKSTOP_WINDOW):
                    continue
                r = dict(r, _repo=repo)
                candidates.append(r)
                ann[r["id"]] = gh.run_annotations(repo, r["id"])
        hits = backstop_hits(candidates, ann, now, handled)

        share = float(st.get("pinned_share", 0.0))
        if _need_billing(st, hits, now):
            items = gh.billing_usage(org, now.year, now.month)
            public = gh.public_repos(org)
            pct = included_minutes_used(items, public) / cfg["included_minutes"] * 100
            share = pinned_share(items, set(preferred), public)
            st.update(last_read=_iso(now), pct=pct, pinned_share=share)

        # An org with no github-preferred repo has nothing to write and the
        # Gitea bot holds no rights there: skip every Gitea call.
        stamp = gitea.get_org_var(gitea_org, MONTH_VAR) if preferred else None
        computed, do_stamp = desired_authority(pct, threshold, bool(hits), stamp, now_month, None)
        tag = f"pct={pct:.1f} pinned_share={share:.2f}"
        if do_stamp and mode == "live" and preferred:
            gitea.set_org_var(gitea_org, MONTH_VAR, now_month)
            if gitea.get_org_var(gitea_org, MONTH_VAR) != now_month:
                raise ReadbackError(f"{org}: {MONTH_VAR} did not read back as {now_month}")

        desired_by_repo = {}
        at_gitea: set[str] = set()   # gitea on BOTH sides after this pass
        apply_failed: set[str] = set()
        for repo, tcfg in preferred.items():
            desired = tcfg.get("pin_authority") or computed
            desired_by_repo[repo] = desired
            gh_val = gh.get_variable(repo, AUTHORITY_VAR)
            gitea_val = gitea.get_repo_var(gitea_org, repo, AUTHORITY_VAR)
            if gh_val == desired and gitea_val == desired:
                if desired == "gitea":
                    at_gitea.add(repo)
                continue
            try:
                # Only a move TOWARD gitea can run an ungated job on a runner that
                # cannot serve it; returning to github is never refused.
                gaps = coverage_gaps(repo, tcfg, gh, labels) if desired == "gitea" else []
                if gaps:
                    refused.append(repo)
                    digest = hashlib.sha1("\n".join(gaps).encode()).hexdigest()[:8]
                    _send(st, notifier, f"refuse:{org}/{repo}:{digest}",
                          f"ci-budget: refusing to move {org}/{repo} to {desired} ({tag}); "
                          f"gate-coverage gaps:\n" + "\n".join(gaps[:10]))
                    continue
                if mode != "live":
                    wanted.append(repo)
                    _send(st, notifier, f"would-flip:{org}/{repo}:{desired}:{now_month}",
                          f"ci-budget (dry-run): would move {org}/{repo} to {desired} ({tag})")
                    continue
                apply_authority(repo, desired, gh, gitea, gitea_org, gh_val, gitea_val)
                flipped.append(repo)
                if desired == "gitea":
                    at_gitea.add(repo)
                _send(st, notifier, f"flip:{org}/{repo}:{desired}:{now_month}",
                      f"ci-budget: moved {org}/{repo} to {desired} ({tag})")
            except Exception as e:  # noqa: BLE001 - one repo's failure must not hide the rest
                errors.append(f"{repo}: {e}")
                apply_failed.add(repo)

        # backstop notification + Gitea re-run, worded from the actual outcome
        rerun = st.setdefault("rerun", {})
        for hit in hits:
            repo = hit["_repo"]
            if repo in apply_failed:
                outcome = "apply failed; will retry next run"
            elif repo in refused:
                outcome = "refused (gate-coverage gaps), no re-run"
            elif desired_by_repo.get(repo) != "gitea":
                outcome = "repo is pinned to github, no re-run"
            elif mode != "live":
                outcome = "dry-run, no re-run"
            elif repo in at_gitea:
                outcome = "re-running on Gitea"
            else:
                outcome = "not on gitea on both sides, no re-run"
            _send(st, notifier, f"backstop:{hit['id']}",
                  f"ci-budget: spending-limit failure in {org}/{repo} (run {hit['id']}); {outcome}")
            if outcome == "re-running on Gitea":
                name = RERUN_PREFIX + hit["head_sha"][:12]
                try:
                    gitea.create_branch(gitea_org, repo, name, hit["head_sha"])
                    rerun[f"{repo}/{name}"] = _iso(now)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{repo}: re-run {name}: {e}")
                    continue
            elif repo in apply_failed:
                continue  # leave unhandled: the next tick retries
            st.setdefault("handled", []).append(hit["id"])
        del st.get("handled", [])[:-SENT_KEEP]

        if mode == "live":
            for repo in preferred:
                for b in gitea.list_branches(gitea_org, repo):
                    name = b["name"]
                    if not name.startswith(RERUN_PREFIX):
                        continue
                    key = f"{repo}/{name}"
                    made = rerun.get(key)
                    if not made:
                        # unknown branch: first seen now; the commit time says
                        # nothing about when the branch was created
                        rerun[key] = _iso(now)
                    elif now - parse_ts(made) > RERUN_MAX_AGE:
                        gitea.delete_branch(gitea_org, repo, name)
                        rerun.pop(key, None)
    except Exception as e:  # noqa: BLE001
        errors.append(str(e))

    if errors:
        verdict = "error"
        for e in errors:
            log(f"ci-budget-watcher error org={org}: {e}")
    elif flipped:
        verdict = "flipped"
    elif wanted:
        verdict = "would-flip"
    elif refused:
        verdict = "refused"
    else:
        verdict = "ok"
    log(f"ci-budget-watcher verdict={verdict} org={org} pct={pct:.1f} mode={mode}")
    return {"verdict": verdict, "pct": pct, "mode": mode, "failed": bool(errors)}


# ---------------------------------------------------------------- layer 3

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"


class ConfigMapState:
    """The watcher's state: one JSON blob in the ci-budget-state ConfigMap."""

    def __init__(self, namespace, name, token, http=default_http, host="https://kubernetes.default.svc"):
        self.ns, self.name, self.token, self.http, self.host = namespace, name, token, http, host
        self.version = None

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def _url(self, named=True):
        base = f"{self.host}/api/v1/namespaces/{self.ns}/configmaps"
        return f"{base}/{self.name}" if named else base

    def load(self):
        status, cm = self.http("GET", self._url(), self._headers(), None)
        if status == 404:
            self.version = None
            return {}
        if status != 200:
            raise HttpError(status, cm, "GET", self._url())
        self.version = cm["metadata"].get("resourceVersion")
        return json.loads((cm.get("data") or {}).get("state.json", "{}"))

    def save(self, state):
        body = {"apiVersion": "v1", "kind": "ConfigMap",
                "metadata": {"name": self.name, "namespace": self.ns},
                "data": {"state.json": json.dumps(state, sort_keys=True)}}
        if self.version is None:
            status, resp = self.http("POST", self._url(False), self._headers(), body)
        else:
            body["metadata"]["resourceVersion"] = self.version
            status, resp = self.http("PUT", self._url(), self._headers(), body)
        if status not in (200, 201):
            raise HttpError(status, resp, "save", self._url())
        self.version = resp["metadata"].get("resourceVersion")


class TelegramNotifier:
    def __init__(self, token, chat_id, http=default_http):
        self.token, self.chat_id, self.http = token, chat_id, http

    @property
    def enabled(self):
        return bool(self.token and self.chat_id)

    def send(self, text):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        status, resp = self.http("POST", url, {}, {"chat_id": self.chat_id, "text": text})
        if status != 200:
            raise HttpError(status, resp, "POST", "telegram sendMessage")


def _env_key(org):
    return org.upper().replace("-", "_")


def main(env=None, http=None, now=None, out=print):
    import yaml

    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    cfg = yaml.safe_load(open(env.get("TIERS_FILE", "/config/tiers.yaml")))
    labels = ci_gate_coverage.runner_labels(open(env.get("RUNNER_CONFIG", "/config/runner-config.yaml")).read())
    k8s_http = http
    if http is None:
        ca = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")
        k8s_http = lambda m, u, h=None, b=None: default_http(m, u, h, b, context=ca)  # noqa: E731
        http = default_http
    sa_token = env.get("SA_TOKEN") or open(f"{SA_DIR}/token").read().strip()
    store = ConfigMapState(env.get("NAMESPACE", "tekton-pipelines"), "ci-budget-state", sa_token, http=k8s_http)
    state = store.load()
    gitea = GiteaClient(env.get("GITEA_API", "http://gitea-http.gitea.svc:3000/api/v1"), env.get("GITEA_TOKEN"), http)
    notifier = TelegramNotifier(env.get("TELEGRAM_TOKEN"), env.get("TELEGRAM_CHATID"), http)
    failed = False
    for org, ocfg in (cfg.get("orgs") or {}).items():
        try:
            k = _env_key(org)
            gh = GitHubClient(org, env.get(f"GH_BILLING_TOKEN_{k}"), env.get(f"GH_AUTHORITY_TOKEN_{k}"), http)
            st = state.setdefault(org, {})
            res = run_org(org, ocfg, gh, gitea, st, now, notifier, labels, log=out)
            failed |= res["failed"]
        except Exception as e:  # noqa: BLE001
            failed = True
            out(f"ci-budget-watcher error org={org}: {e}")
            out(f"ci-budget-watcher verdict=error org={org} pct=0.0 mode={ocfg.get('mode', 'dry-run')}")
    store.save(state)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
