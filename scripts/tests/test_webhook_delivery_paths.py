"""Tripwire: every EventListener trigger must have a declared delivery path.

THE FAILURE. An EventListener trigger is only half a delivery path. The other
half is a webhook in Gitea or GitHub, which is forge state with no IaC anywhere
in this repo — so a correct, live trigger can ship with nothing able to reach it.

That happened on 2026-07-26. `agentic-stoa-site-promotion` went live with no
Gitea push webhook behind it, and every surface reported healthy: ArgoCD Synced,
mirror sync Succeeded, Gitea Actions green, the image published. The listener
log was SILENT, because the request never arrived — so it read as a broken
pipeline rather than a missing webhook.

WHAT THIS CHECKS. Offline, at PR time, against apps/tekton/webhooks.yaml:

  1. every trigger that names repositories is `serves:`-ed by some declaration
  2. every repo a trigger names has a declaration pointing at that trigger's
     listener
  3. no declaration references a trigger that no longer exists
  4. every declaration's `events:` covers the `eventTypes` its served triggers'
     `github` interceptors actually require
  5. no `scope: repo`/`scope: org` (forge-webhook) declaration claims an event
     GitHub restricts to App webhooks (at minimum `repository_dispatch` —
     see the class-2 failure below)

A SECOND, CLASS-2 FAILURE (found 2026-09-20, P10 review Critical #1). Checks
1-3 above assume "a declared delivery path" is sufficient — they never asked
whether the declared path can exist AT ALL. `staging-gate-runs-fr` shipped
with `forge: github, scope: repo, events: [repository_dispatch]`, which reads
as covered by every check above and is still impossible: GitHub's webhook
availability matrix (docs.github.com/en/webhooks/webhook-events-and-payloads)
restricts `repository_dispatch` to **App** webhooks — a plain repository
webhook cannot subscribe to it, full stop. Fixed by check 5, and by a new
declaration shape: `scope: direct-post` records a delivery path that is NOT a
forge webhook at all — the sender (here, `runs-fr`'s own GHA workflow) POSTs a
signed request directly to the listener, so GitHub's per-scope event
restriction does not apply to it. See the `derio-net/runs-fr` entry below and
journal decision `d-delivery-gha-direct-post`.

WHAT IT DOES NOT CHECK. Whether the declared webhook actually exists in the
forge right now. A hook deleted by hand in Gitea still passes here. Closing that
needs a verifier CronJob comparing this file to the forge APIs — the follow-up.
Most of the declarations were snapshotted while live reality matched (verified
2026-07-26); the `derio-net/runs-fr` entry is desired state ahead of the
runs-fr-side change that will make it real (see webhooks.yaml's header).
"""
from __future__ import annotations

import pathlib
import re

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
DECL = REPO / "apps/tekton/webhooks.yaml"
TRIGGER_FILES = [
    REPO / "apps/tekton/triggers/eventlistener.yaml",
    REPO / "apps/tekton/triggers/eventlistener-github.yaml",
]

# Triggers that legitimately name no repository, so there is nothing to cover:
# they match on event shape alone and are served by a broader (org//status) hook.
REPOLESS_OK = {"gitea-status-bridge"}

# Triggers whose EventListener is NOT defined in this repo, so it cannot be
# parsed here. The stoa-live-mirror-sync Application sources its manifests from
# `stoa/ci/tekton/live-mirror-sync` in another repository. Their delivery paths
# are still declared in webhooks.yaml — that is the point — but the
# stale-declaration check must not treat them as fictitious.
EXTERNAL_TRIGGERS = {
    "companies-main-push": "EventListener ships from stoa/ci/tekton/live-mirror-sync (other repo)",
}

# GitHub's webhook availability matrix restricts these event types to GitHub
# **App** webhooks (docs.github.com/en/webhooks/webhook-events-and-payloads,
# checked 2026-09-20) — a `scope: repo` or `scope: org` declaration can never
# be delivered one of these by a real forge webhook. `staging-gate-runs-fr`
# shipped exactly this impossible shape (P10 review Critical #1); the fix is
# `scope: direct-post` (see webhooks.yaml), never adding the event here.
GITHUB_APP_ONLY_EVENTS = {"repository_dispatch"}

# Pre-existing (P5/P8-era) declaration whose `events:` do not cover one of its
# `serves:` triggers' interceptor eventTypes -- discovered, not introduced, by
# the P10 review that added the coverage check below. agentic-stoa/cnc-frd is
# declared `scope: repo, events: [push, pull_request]` but also `serves:
# cnc-image-promotion`, whose `github` interceptor requires
# `eventTypes: [repository_dispatch]` -- the SAME GitHub App-only restriction
# as GITHUB_APP_ONLY_EVENTS above, so a repo webhook could not cover it even
# if the declaration listed it. Live corroboration (2026-09-20): the
# agentic-stoa/cnc-frd hook carries only `[pull_request, push]`, and no
# cnc-image-promotion PipelineRun exists in the retained window -- the path
# looks pre-existing and dead, not a live regression. Left as a discovery
# (journal:plans/2026-06-15-staging-vcluster-gate.md,
# id=p10-discovery-cnc-image-promotion-unreachable) with a follow-up note on
# the declaration itself, rather than silently "fixed" by this unrelated plan.
KNOWN_EVENT_COVERAGE_GAPS = {
    ("agentic-stoa/cnc-frd", "cnc-image-promotion"),
}

# Repo literals only count beside a `full_name` comparison (==, !=,
# .startsWith(, or list membership) -- never beside `.matches(`, where the
# quoted string is a CEL REGEX, not a repository name. Without this
# restriction a future clause like `client_payload.app.matches('^[a-z]+/
# [a-z]+$')` would be misread as declaring a phantom `[a-z]+/[a-z]+` delivery
# path (P10 review, finding #12 — latent, no live trigger has hit it yet).
_REPO_TOKEN_RE = re.compile(r"(?:==|!=|in|\.startsWith\(|,|\[)\s*'([\w.-]+/[\w.-]+)'")


def _declarations() -> list[dict]:
    return yaml.safe_load(DECL.read_text())["webhooks"]


def _triggers() -> dict[str, dict]:
    """{trigger-name: {listener, repos, event_types}} across every EventListener in git."""
    out: dict[str, dict] = {}
    for f in TRIGGER_FILES:
        for doc in yaml.safe_load_all(f.read_text()):
            if not doc or doc.get("kind") != "EventListener":
                continue
            listener = doc["metadata"]["name"]
            for t in doc["spec"]["triggers"]:
                blob = ""
                event_types: list[str] | None = None
                for ic in t.get("interceptors") or []:
                    for p in ic.get("params") or []:
                        if p.get("name") == "filter":
                            blob += " " + str(p.get("value"))
                        if ic.get("name") == "github" and p.get("name") == "eventTypes":
                            event_types = list(p.get("value") or [])
                repos = sorted({
                    m for m in _REPO_TOKEN_RE.findall(blob)
                    if not m.startswith("refs/")
                })
                out[t["name"]] = {
                    "listener": listener,
                    "repos": repos,
                    "event_types": event_types,
                }
    assert out, "no EventListener triggers parsed — did the manifests move?"
    return out


def test_every_repo_naming_trigger_has_a_declared_delivery_path():
    triggers, decls = _triggers(), _declarations()
    missing = []
    for name, t in sorted(triggers.items()):
        if not t["repos"] or name in REPOLESS_OK:
            continue
        for repo in t["repos"]:
            covered = any(
                d["target"] == repo
                and d["listener"] == t["listener"]
                and name in (d.get("serves") or [])
                for d in decls
            )
            if not covered:
                missing.append(f"{name} (listener {t['listener']}) needs a webhook for {repo}")
    assert not missing, (
        "EventListener triggers with no declared way to reach them — they will be "
        "live, correct and unreachable, and the failure looks like a broken "
        "pipeline rather than a missing webhook:\n"
        + "\n".join(f"  - {m}" for m in missing)
        + f"\n\nAdd the delivery path to {DECL.relative_to(REPO)} AND create it in "
          "the forge (see the manual-op cicd-stoa-site-gitea-push-webhook for the "
          "Gitea call)."
    )


def test_no_declaration_serves_a_trigger_that_no_longer_exists():
    """A stale entry makes the coverage check above pass on a fiction."""
    triggers, decls = _triggers(), _declarations()
    stale = sorted({
        s for d in decls for s in (d.get("serves") or [])
        if s not in triggers and s not in EXTERNAL_TRIGGERS
    })
    assert not stale, (
        "webhooks.yaml claims to serve triggers that do not exist in any "
        "EventListener — delete the entries, fix the names, or (if the listener "
        "genuinely lives in another repo) add an EXTERNAL_TRIGGERS entry:\n"
        + "\n".join(f"  - {s}" for s in stale)
    )


def test_every_repoless_exemption_is_still_repoless():
    """If a REPOLESS_OK trigger gains repos, it must be covered like the rest."""
    triggers = _triggers()
    wrong = [n for n in REPOLESS_OK if triggers.get(n, {}).get("repos")]
    assert not wrong, (
        "these triggers now name repositories, so they need declared delivery "
        "paths and must come out of REPOLESS_OK: " + ", ".join(wrong)
    )


@pytest.mark.parametrize("field", ["forge", "scope", "target", "listener", "events"])
def test_declaration_entries_are_well_formed(field):
    for d in _declarations():
        assert field in d, f"webhook declaration missing '{field}': {d}"
        assert d[field], f"webhook declaration has empty '{field}': {d}"


def test_declared_listeners_actually_exist():
    """Guards a typo'd listener name, which would silently satisfy nothing."""
    listeners = {t["listener"] for t in _triggers().values()}
    # live-mirror-sync's EventListener ships from its own app, not the two files
    # parsed above, so allow it explicitly rather than widening the parse.
    listeners.add("live-mirror-sync")
    bad = sorted({d["listener"] for d in _declarations()} - listeners)
    assert not bad, (
        f"webhooks.yaml points at listeners with no EventListener in git: {bad}"
    )


def test_forge_webhook_declarations_never_claim_a_github_app_only_event():
    """P10 review Critical #1: this is the check that would have caught it.

    `staging-gate-runs-fr` originally declared `scope: repo, events:
    [repository_dispatch]` -- a shape checks 1-3 above accept, because they
    only ask "is there a declaration", never "could this declaration's kind
    of webhook ever be delivered this event". GitHub's App-only events (at
    minimum `repository_dispatch`) can never reach a repo/org webhook, so a
    `scope: repo`/`scope: org` declaration naming one is unreachable BY
    CONSTRUCTION, independent of whether the forge side was ever created.
    """
    decls = _declarations()
    bad = []
    for d in decls:
        if d.get("forge") != "github" or d.get("scope") not in ("repo", "org"):
            continue
        claimed = set(d.get("events") or []) & GITHUB_APP_ONLY_EVENTS
        if claimed:
            bad.append(f"{d['target']} (scope {d['scope']}) claims {sorted(claimed)}")
    assert not bad, (
        "GitHub restricts these events to App webhooks -- a repo/org webhook "
        "cannot subscribe (docs.github.com/en/webhooks/webhook-events-and-payloads). "
        "Use `scope: direct-post` for a sender that POSTs straight to the "
        "listener instead of registering a forge webhook:\n"
        + "\n".join(f"  - {b}" for b in bad)
    )


def test_declared_events_cover_the_served_triggers_interceptor_event_types():
    """A declaration whose `events:` don't cover its trigger's real
    `eventTypes` is declaring a delivery path that, even if it exists in the
    forge, sends the wrong event and is filtered out at the interceptor.
    """
    triggers, decls = _triggers(), _declarations()
    missing = []
    for d in decls:
        declared = set(d.get("events") or [])
        for name in d.get("serves") or []:
            required = (triggers.get(name) or {}).get("event_types")
            if not required:
                continue  # trigger has no github interceptor eventTypes (e.g. cel-only)
            gap = set(required) - declared
            if gap and (d.get("target"), name) not in KNOWN_EVENT_COVERAGE_GAPS:
                missing.append(
                    f"{d.get('target')} serves {name} (requires eventTypes "
                    f"{sorted(required)}) but declares events {sorted(declared)}"
                )
    assert not missing, (
        "a declaration's events: must cover every eventType its served "
        "trigger's github interceptor actually requires, or a real delivery "
        "still gets filtered out at the interceptor:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )
