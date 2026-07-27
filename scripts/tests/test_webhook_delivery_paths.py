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

WHAT IT DOES NOT CHECK. Whether the declared webhook actually exists in the
forge right now. A hook deleted by hand in Gitea still passes here. Closing that
needs a verifier CronJob comparing this file to the forge APIs — the follow-up.
The declaration was snapshotted while live reality matched (verified 2026-07-26).
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


def _declarations() -> list[dict]:
    return yaml.safe_load(DECL.read_text())["webhooks"]


def _triggers() -> dict[str, dict]:
    """{trigger-name: {listener, repos}} across every EventListener in git."""
    out: dict[str, dict] = {}
    for f in TRIGGER_FILES:
        for doc in yaml.safe_load_all(f.read_text()):
            if not doc or doc.get("kind") != "EventListener":
                continue
            listener = doc["metadata"]["name"]
            for t in doc["spec"]["triggers"]:
                blob = ""
                for ic in t.get("interceptors") or []:
                    for p in ic.get("params") or []:
                        if p.get("name") == "filter":
                            blob += " " + str(p.get("value"))
                # Repos appear as quoted 'owner/name' literals inside the CEL.
                repos = sorted({
                    m for m in re.findall(r"'([\w.-]+/[\w.-]+)'", blob)
                    if not m.startswith("refs/")
                })
                out[t["name"]] = {"listener": listener, "repos": repos}
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
