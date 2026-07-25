"""Tripwire: the www delivery path stays wired end to end.

An image built from agentic-stoa/site only reaches www.derio.net if three
separate pieces agree, and each fails quietly on its own:

1. **The mirror trigger** — GitHub push must reach Frank's Gitea, or CI never
   runs and nothing is ever built.
2. **The promotion trigger** — a Gitea push must fire `site-promotion`, or the
   image is built and then never deployed. ArgoCD stays green on the old tag.
3. **The promotion pipeline itself** — it must use the derio-net credential
   (the stoa App token cannot push to derio-net/frank) and it must be
   race-safe, because a naive `pull --rebase` leaves a conflicted tree when two
   builds land together.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE = REPO_ROOT / "apps/tekton/pipelines/site-promotion.yaml"
EL_GITHUB = REPO_ROOT / "apps/tekton/triggers/eventlistener-github.yaml"
EL_GITEA = REPO_ROOT / "apps/tekton/triggers/eventlistener.yaml"

MANIFEST = "clusters/hop/apps/www/manifests/deployment.yaml"
REPO = "agentic-stoa/site"


def _docs(path: Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _code(path: Path) -> str:
    """File text with comment lines stripped.

    The negative assertions below are about what the pipeline *does*, not what
    its comments discuss — and the comments deliberately name both the wrong
    credential and the wrong git strategy in order to explain why they are
    wrong. Asserting over raw text would make documenting a hazard fail the
    test that guards it.
    """
    return "\n".join(
        ln for ln in path.read_text().splitlines() if not ln.lstrip().startswith("#")
    )


def test_pipeline_uses_the_derio_net_credential() -> None:
    """The stoa App token can read agentic-stoa but cannot push to frank.

    frank-gitops-push is minted from the derio-net installation for exactly
    this. Using the wrong secret produces a 403 at push time, after a green
    build.
    """
    code = _code(PIPELINE)
    assert "frank-gitops-push" in code, "promotion must use the derio-net token"
    assert "stoa-github-mirror" not in code, (
        "stoa-github-mirror is scoped to agentic-stoa and cannot push to "
        "derio-net/frank"
    )


def test_pipeline_targets_the_www_manifest() -> None:
    raw = PIPELINE.read_text()
    assert MANIFEST in raw, f"promotion must rewrite {MANIFEST}"
    assert "ghcr.io/agentic-stoa/site" in raw


def test_promotion_is_idempotent_and_race_safe() -> None:
    """Two builds landing together must not corrupt the tree.

    The blog workflow learned this the hard way: `git pull --rebase` in a
    retry loop leaves a conflicted working tree when two workflows touch the
    same image line. The fix is reset-to-origin per attempt plus explicit
    already-done / lost-the-race exits.
    """
    code = _code(PIPELINE)
    assert "pull --rebase" not in code, (
        "use reset-to-origin per attempt, not pull --rebase — the latter "
        "leaves a conflicted tree on concurrent builds"
    )
    assert "reset --hard origin/main" in code, "each attempt must start clean"
    assert "merge-base --is-ancestor" in code, (
        "must yield when a newer build already won the race"
    )


def test_pipeline_is_deployed_by_argocd() -> None:
    """A pipeline file nothing points at is inert."""
    docs = _docs(PIPELINE)
    kinds = {d.get("kind") for d in docs}
    assert "Pipeline" in kinds, f"expected a Pipeline, got {kinds}"
    pipeline = next(d for d in docs if d.get("kind") == "Pipeline")
    assert pipeline["metadata"]["namespace"] == "tekton-pipelines"


def test_site_is_mirrored_from_github() -> None:
    """Without this the repo never reaches Gitea and CI never runs."""
    raw = EL_GITHUB.read_text()
    assert REPO in raw, (
        f"{REPO} is absent from the GitHub EventListener — pushes would never "
        "reach the Gitea mirror"
    )


def test_gitea_push_fires_site_promotion() -> None:
    raw = EL_GITEA.read_text()
    assert "site-promotion" in raw, (
        "no Gitea trigger fires site-promotion — images would build and never "
        "deploy"
    )
    assert REPO in raw, "the promotion trigger must be filtered to this repo"


def test_promotion_trigger_is_filtered_to_main() -> None:
    """A sync-pr-** push must not promote an unreviewed branch to production."""
    raw = EL_GITEA.read_text()
    idx = raw.index("site-promotion")
    window = raw[max(0, idx - 3000) : idx + 3000]
    assert "refs/heads/main" in window, (
        "the site-promotion trigger must match refs/heads/main only — "
        "sync-pr-** branches must never reach www.derio.net"
    )
