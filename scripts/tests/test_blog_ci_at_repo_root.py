"""Tripwire: the blog CI workflow must live where GitHub actually reads it.

THE FAILURE. GitHub Actions only ever loads workflows from `.github/workflows/`
at the REPOSITORY root. blog-craft materializes its CI under the Hugo site root,
which for frank is `blog/.github/workflows/blog-ci.yml` — so from the day it
arrived (#667) that file was inert. Its papers, mermaid and image gates never
ran a single time, while the repo carried a well-commented workflow that looked
for all the world like they did. Nothing reports this: there is no error, no
skipped run, no empty check. The file simply is not a workflow as far as GitHub
is concerned.

It could not have passed even if GitHub had run it, which is the tell that
nobody ever did: it invoked `--config .blog-craft.yaml` and
`docs/papers-dossiers/*` relative to the site root, and in frank both of those
live at the repo root.

WHY THIS EXISTED, AND WHAT IT IS NOW. Until blog-craft v0.17.0 every `/update`
re-added the inert copy — `plan_update` classifies an absent managed path as
`add`, and `.github/**` was mapped under `site_dir` — so each resync recreated a
file GitHub would never run, and this test was the only thing that made it loud.

blog-craft#61 fixed it upstream: the manifest now declares a path ROOT per file,
`.github/**` is repo-rooted, and `/update` RELOCATES a stale copy instead of
leaving two. Verified against v0.17.0 — the resync plan no longer mentions
`blog/.github/` at all.

So this is now a REGRESSION guard rather than a live tripwire. It stays because
the failure it catches is silent by construction: a workflow in the wrong
directory produces no error, no skipped run and no empty check, and nothing else
in this repo would notice.

WHAT THIS CHECKS. Offline, at PR time:

  1. the real workflow exists at the repo root
  2. no workflow directory has reappeared under blog/
  3. the root workflow still invokes every blog-craft gate — a gate silently
     vanishing from this file is exactly how the glossary step went missing
     (blog-craft#60: enabling a feature flag drops its contribution to a
     merged-class file, and `update applied` prints either way)
  4. the upstream `deploy` stub has not been carried in alongside them, which
     would give one site two deploy paths (frank deploys via deploy-blog.yml)

WHAT IT DOES NOT CHECK. Whether the workflow passes, or whether GitHub actually
scheduled it. This is a placement and coverage guard, not a substitute for the
run. The mermaid gate is currently opted out via `quality.mermaid_syntax: false`
in .blog-craft.yaml — the STEP is still required to be present here, so flipping
the config back on needs no workflow edit.
"""
from __future__ import annotations

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/blog-ci.yml"
INERT = REPO / "blog/.github"

# Each blog-craft gate, by the script the workflow must invoke.
REQUIRED_GATES = [
    "blog/scripts/sync_dossier_to_data.py",
    "blog/scripts/validate_dossier.py",
    "blog/scripts/validate_papers.py",
    "blog/scripts/validate_glossary.py",
    "blog/scripts/validate_mermaid.py",
    "blog/scripts/validate_images.py",
    # The width gate (blog-craft v0.19.0) measures the BUILT site, so unlike
    # every gate above it must run after the Hugo build. That ordering is the
    # reason it is easy to drop: a step appended below `hugo --minify` reads
    # like a build artifact rather than a gate.
    "blog/scripts/validate_mermaid_layout.mjs",
]


def test_blog_workflow_is_at_repo_root() -> None:
    assert WORKFLOW.is_file(), (
        f"{WORKFLOW.relative_to(REPO)} is missing. GitHub only reads workflows from "
        "the repo root; a copy under blog/ is inert and gates nothing."
    )


def test_no_inert_workflow_copy_under_blog() -> None:
    assert not INERT.exists(), (
        "blog/.github/ is back — almost certainly re-added by a blog-craft /update, "
        "which recreates any managed path that is missing. GitHub will never run it. "
        "Delete it; the live workflow is .github/workflows/blog-ci.yml."
    )


@pytest.mark.parametrize("script", REQUIRED_GATES)
def test_every_blog_gate_is_invoked(script: str) -> None:
    body = WORKFLOW.read_text(encoding="utf-8")
    assert script in body, (
        f"{script} is no longer invoked by .github/workflows/blog-ci.yml. "
        "A gate that silently leaves this file stops gating without any signal — "
        "the exact shape of blog-craft#60."
    )


def test_deploy_stub_not_carried_over() -> None:
    # Structural, not a substring match: the workflow's own comments explain why
    # the stub is excluded, and a text search for the stub's wording therefore
    # matches the documentation of its absence. Parse the jobs instead.
    yaml = pytest.importorskip("yaml")
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    assert "deploy" not in jobs, (
        "blog-craft's placeholder `deploy` job has been copied in. frank deploys "
        "the blog via .github/workflows/deploy-blog.yml; two deploy paths for one "
        "site is a race, not redundancy."
    )
