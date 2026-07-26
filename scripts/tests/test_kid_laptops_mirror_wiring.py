"""Guard the GitHub -> Gitea mirror wiring for derio-homelab/kid-laptops.

kid-laptops is private and lives in a THIRD GitHub org — neither `derio-net`
nor `agentic-stoa` — so it cannot reuse either existing credential.

Three traps are locked down here, each of which fails silently:

  - **The ESO namespace trap.** ESO resolves `auth.privateKey.secretRef` in the
    CONSUMING ExternalSecret's namespace and *ignores* a `namespace:` field on
    the ref. Writing one looks correct, reads correct in review, and leaves the
    ExternalSecret in SecretSyncedError forever while ArgoCD reports green.
    That exact mistake hid for seven days on `frank-gitops-push`.

  - **Token TTL vs refresh.** A GitHub App installation token lives ~1h. A
    refreshInterval at or above that guarantees windows where Tekton reads an
    expired token.

  - **The frozen-array trap.** `github-pull-sync` hardcodes the `stoa-github-mirror`
    Secret inside `.spec.tasks[]`, and this repo's tekton-extras
    `ignoreDifferences` carries array-item jqPathExpressions on `.spec.tasks[]?`
    — which make ArgoCD carry the LIVE array into every apply, so edits to it
    are discarded while syncs report Succeeded. kid-laptops therefore gets its
    own Pipeline object rather than a new param on the shared one. This test
    asserts the shared pipeline was left alone.
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "apps/tekton/manifests/clustergenerator-derio-homelab-github-app.yaml"
MIRROR_ES = REPO / "apps/tekton/manifests/externalsecret-derio-homelab-github-mirror.yaml"
WEBHOOK_ES = REPO / "apps/tekton/manifests/externalsecret-derio-homelab-github-webhook-secret.yaml"
PULL_SYNC = REPO / "apps/tekton/pipelines/derio-homelab-pull-sync.yaml"
SHARED_PULL_SYNC = REPO / "apps/tekton/pipelines/github-pull-sync.yaml"
EL_GITHUB = REPO / "apps/tekton/triggers/eventlistener-github.yaml"

DERIO_FR_AUTOMATION_APP_ID = "3994132"
TRIGGER_NAME = "derio-homelab-kid-laptops-main-sync"
REPO_FULL_NAME = "derio-homelab/kid-laptops"


def _docs(path: Path) -> list[dict]:
    assert path.exists(), f"missing manifest: {path.relative_to(REPO)}"
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _one(path: Path, kind: str) -> dict:
    matches = [d for d in _docs(path) if d.get("kind") == kind]
    assert len(matches) == 1, f"expected one {kind} in {path.name}, got {len(matches)}"
    return matches[0]


def test_generator_uses_the_existing_derio_app() -> None:
    gen = _one(GENERATOR, "ClusterGenerator")
    assert gen["metadata"]["name"] == "github-app-derio-homelab"
    spec = gen["spec"]
    assert spec["kind"] == "GithubAccessToken"
    assert spec["generator"]["githubAccessTokenSpec"]["appID"] == DERIO_FR_AUTOMATION_APP_ID


def test_generator_private_key_ref_omits_namespace() -> None:
    gen = _one(GENERATOR, "ClusterGenerator")
    ref = gen["spec"]["generator"]["githubAccessTokenSpec"]["auth"]["privateKey"]["secretRef"]
    assert "namespace" not in ref, (
        "secretRef must NOT carry a namespace: ESO resolves it in the consuming "
        "ExternalSecret's namespace and ignores this field. Setting it produces "
        "a permanently unsynced secret with no error anywhere but the ES status."
    )
    assert ref["name"] and ref["key"]


def test_mirror_externalsecret_consumes_the_generator_and_refreshes_under_an_hour() -> None:
    es = _one(MIRROR_ES, "ExternalSecret")
    assert es["metadata"]["namespace"] == "tekton-pipelines"
    gen_ref = es["spec"]["dataFrom"][0]["sourceRef"]["generatorRef"]
    assert gen_ref["kind"] == "ClusterGenerator"
    assert gen_ref["name"] == "github-app-derio-homelab"

    interval = es["spec"]["refreshInterval"]
    assert interval.endswith("m"), f"expected minutes, got {interval!r}"
    assert int(interval[:-1]) < 60, (
        f"refreshInterval {interval} is not under the ~1h installation-token TTL"
    )


def test_webhook_hmac_secret_is_its_own_not_borrowed_from_stoa() -> None:
    es = _one(WEBHOOK_ES, "ExternalSecret")
    assert es["spec"]["target"]["name"] == "derio-homelab-github-webhook-secret"
    remote_key = es["spec"]["data"][0]["remoteRef"]["key"]
    assert not remote_key.startswith("/agentic-stoa/"), (
        "a derio-homelab webhook must not share the agentic-stoa HMAC secret"
    )


def test_kid_laptops_has_its_own_pull_sync_pipeline() -> None:
    pipeline = _one(PULL_SYNC, "Pipeline")
    assert pipeline["metadata"]["name"] == "derio-homelab-pull-sync"
    rendered = PULL_SYNC.read_text()
    assert "derio-homelab-github-mirror" in rendered, (
        "the pipeline must read the derio-homelab token, not the stoa one"
    )
    assert "stoa-github-mirror" not in rendered


def test_shared_pull_sync_pipeline_was_not_edited() -> None:
    rendered = SHARED_PULL_SYNC.read_text()
    assert "derio-homelab" not in rendered, (
        "github-pull-sync's .spec.tasks[] is inside a frozen array "
        "(tekton-extras ignoreDifferences uses array-item jqPathExpressions on "
        ".spec.tasks[]?). Edits there apply green and never go live. Add a new "
        "Pipeline object instead."
    )


def test_github_eventlistener_has_a_kid_laptops_main_sync_trigger() -> None:
    els = [d for d in _docs(EL_GITHUB) if d.get("kind") == "EventListener"]
    triggers = [t for el in els for t in el["spec"]["triggers"]]
    matching = [t for t in triggers if t.get("name") == TRIGGER_NAME]
    assert matching, f"no trigger named {TRIGGER_NAME}"
    trigger = matching[0]

    cel = [i for i in trigger["interceptors"] if i.get("ref", {}).get("name") == "cel"]
    assert cel, "expected a cel interceptor"
    cel_filter = cel[0]["params"][0]["value"]
    assert REPO_FULL_NAME in cel_filter
    assert "refs/heads/main" in cel_filter

    gh = [i for i in trigger["interceptors"] if i.get("ref", {}).get("name") == "github"]
    assert gh, "expected the github ClusterInterceptor for HMAC validation"
    secret_param = next(p for p in gh[0]["params"] if p["name"] == "secretRef")
    assert secret_param["value"]["secretName"] == "derio-homelab-github-webhook-secret"

    bound = {b["name"] for b in trigger["bindings"]}
    assert {"github-repo", "gitea-repo", "sha", "ref-to"} <= bound, bound
