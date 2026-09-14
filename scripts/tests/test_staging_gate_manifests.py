"""Guard the staging-gate vCluster's ArgoCD wiring (plan
2026-06-15-staging-vcluster-gate, phase 7).

Two things must hold once the staging vCluster is registered out-of-band as an
ArgoCD cluster named `staging` (manual op, not this repo):

1. `runs-fr-staging` and the `infrastructure` AppProject address it BY NAME
   (`destination.name: staging`). Both `name` and `server` resolve against the
   registered cluster list; name is used for consistency with `cnc-staging`,
   so the registered Secret's `name` is the one identity to keep in sync.

2. ArgoCD can clone the PRIVATE github.com/derio-net/runs-fr chart repo. As of
   2026-09-14 the only ArgoCD repository Secret on the cluster was the
   in-cluster Gitea `repo-stoa-companies` (listed with
   `kubectl -n argocd get secret -l argocd.argoproj.io/secret-type=repository`).
   The credential is an ESO-minted installation token from a SCOPED
   ClusterGenerator on the existing derio-fr-automation App: same App and
   installation as `github-app-derio`, but restricted at mint time to the
   gated repos with `contents: read`. The App installation itself holds
   contents/pull_requests/issues/workflows write across every derio-net repo,
   which ArgoCD must never carry.

These run in CI (`.github/workflows/repo-tripwires.yml` runs scripts/tests/ on
every PR). The Application/AppProject assertions shell out to
`helm template apps/root` and fail closed. The ExternalSecret/ClusterGenerator
assertions read raw manifests, because apps/root renders only the App-of-Apps
CRs, not what each Application deploys.
"""

import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROOT_CHART = REPO / "apps/root"

STAGING_VCLUSTER_URL = "https://staging.vcluster-staging.svc:443"
RUNS_FR_REPO_URL = "https://github.com/derio-net/runs-fr.git"

# The shared, unscoped generator the scoped one mirrors (same App + install).
DERIO_GENERATOR = "github-app-derio"
# The scoped read-only generator ArgoCD repository credentials use.
ARGOCD_READ_GENERATOR = "github-app-derio-argocd-read"
# Every ClusterGenerator that existed before this plan. A new name outside
# BASELINE | {ARGOCD_READ_GENERATOR} is a generator this plan did not intend.
BASELINE_GENERATORS = {"github-app-derio", "github-app-derio-homelab", "github-app-stoa"}
MANUAL_OP_ID = "cicd-staging-gate-argocd-runs-fr-repo-key"


def _render() -> list:
    out = subprocess.run(
        ["helm", "template", str(ROOT_CHART)],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, f"helm template apps/root failed:\n{out.stderr}"
    docs = [d for d in yaml.safe_load_all(out.stdout) if d]
    assert docs, "helm template apps/root produced no documents"
    return docs


def _find(docs: list, kind: str, name: str) -> dict:
    for d in docs:
        if d.get("kind") == kind and d.get("metadata", {}).get("name") == name:
            return d
    raise AssertionError(f"no {kind}/{name} rendered by apps/root")


def _raw_manifests() -> list:
    """Raw manifests under apps/*/manifests/*.yaml, each tagged with `_path`."""
    docs = []
    for path in REPO.glob("apps/*/manifests/*.yaml"):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc:
                doc["_path"] = path
                docs.append(doc)
    return docs


def _generators() -> dict:
    return {
        d["metadata"]["name"]: d
        for d in _raw_manifests()
        if d.get("kind") == "ClusterGenerator"
    }


def _runs_fr_repo_es() -> dict:
    matches = [
        d
        for d in _raw_manifests()
        if d.get("kind") == "ExternalSecret"
        and d.get("metadata", {}).get("namespace") == "argocd"
        and ((d.get("spec", {}).get("target", {}).get("template", {}) or {}).get("data") or {}).get("url")
        == RUNS_FR_REPO_URL
    ]
    assert len(matches) == 1, (
        f"expected exactly one argocd ExternalSecret templating {RUNS_FR_REPO_URL}, "
        f"found {len(matches)}"
    )
    return matches[0]


def test_runs_fr_staging_addresses_the_vcluster_by_name():
    app = _find(_render(), "Application", "runs-fr-staging")
    dest = app["spec"]["destination"]
    assert dest.get("name") == "staging", (
        f"runs-fr-staging must target destination.name: staging (like "
        f"cnc-staging), got: {dest}"
    )
    assert "server" not in dest, (
        f"runs-fr-staging must not also set destination.server: {dest}"
    )


def test_infrastructure_project_has_the_staging_destination_by_name():
    project = _find(_render(), "AppProject", "infrastructure")
    destinations = project["spec"]["destinations"]
    names = {d.get("name") for d in destinations if d.get("name")}
    assert "staging" in names, (
        f"infrastructure AppProject must list a destination named 'staging': "
        f"{destinations}"
    )
    assert "cnc-staging" in names, (
        "the cnc-staging destination must survive the staging-gate addition: "
        f"{destinations}"
    )
    staging_entry = next(d for d in destinations if d.get("name") == "staging")
    assert staging_entry.get("namespace") == "*", (
        f"staging destination must allow any namespace: {staging_entry}"
    )
    assert "server" not in staging_entry, (
        f"the staging destination must be addressed by name only: {staging_entry}"
    )


def test_argocd_has_a_repository_credential_for_the_private_runs_fr_repo():
    spec = _runs_fr_repo_es()["spec"]
    template = spec["target"]["template"]
    labels = template.get("metadata", {}).get("labels", {})
    assert labels.get("argocd.argoproj.io/secret-type") == "repository", (
        f"the templated Secret must carry the repository label ArgoCD scans "
        f"for: {labels}"
    )
    data = template["data"]
    assert data.get("type") == "git"
    assert data.get("username") == "x-access-token"
    assert data.get("password") == "{{ .token }}"

    generator_names = {
        entry.get("sourceRef", {}).get("generatorRef", {}).get("name")
        for entry in (spec.get("dataFrom") or [])
    }
    assert generator_names == {ARGOCD_READ_GENERATOR}, (
        f"the ArgoCD credential must be minted by the scoped read-only generator "
        f"{ARGOCD_READ_GENERATOR}, never the unscoped {DERIO_GENERATOR}: "
        f"{generator_names}"
    )

    refresh = spec.get("refreshInterval", "")
    assert refresh.endswith("m") and int(refresh[:-1]) < 60, (
        f"refreshInterval must stay under the ~1h installation-token TTL, "
        f"got: {refresh!r}"
    )


def test_argocd_read_generator_is_scoped_to_read_only_on_the_gated_repos():
    generators = _generators()
    assert ARGOCD_READ_GENERATOR in generators, (
        f"missing ClusterGenerator {ARGOCD_READ_GENERATOR}"
    )
    scoped = generators[ARGOCD_READ_GENERATOR]["spec"]
    base = generators[DERIO_GENERATOR]["spec"]
    assert scoped["kind"] == "GithubAccessToken"

    s = scoped["generator"]["githubAccessTokenSpec"]
    b = base["generator"]["githubAccessTokenSpec"]
    assert (s["appID"], s["installID"]) == (b["appID"], b["installID"]), (
        "the scoped generator must mint from the same App installation as "
        f"{DERIO_GENERATOR} (no new App, no new PEM)"
    )
    assert s["auth"]["privateKey"]["secretRef"] == {"name": "github-app-derio-key", "key": "key"}, (
        "ESO ignores secretRef.namespace and resolves it in the CONSUMER "
        "namespace, so no namespace field may appear here"
    )
    assert s.get("repositories") == ["runs-fr"], (
        f"token must be restricted to the gated repos only: {s.get('repositories')}"
    )
    assert s.get("permissions") == {"contents": "read"}, (
        f"token must carry contents:read and nothing else: {s.get('permissions')}"
    )


def test_no_unintended_cluster_generator_is_added():
    names = set(_generators())
    unexpected = names - BASELINE_GENERATORS - {ARGOCD_READ_GENERATOR}
    assert not unexpected, f"unexpected ClusterGenerators added: {sorted(unexpected)}"
    missing = BASELINE_GENERATORS - names
    assert not missing, f"pre-existing ClusterGenerators removed: {sorted(missing)}"
    base = _generators()[DERIO_GENERATOR]["spec"]["generator"]["githubAccessTokenSpec"]
    assert "repositories" not in base and "permissions" not in base, (
        f"{DERIO_GENERATOR} is shared by secure-agent-pod and tekton; scoping it "
        "would break them"
    )


def test_repo_credential_manifests_are_wired_into_an_argocd_ns_application():
    """A manifest no Application sources is inert. The owning Application must
    already target namespace argocd rather than widening staging-gate."""
    es_path = _runs_fr_repo_es()["_path"]
    gen_path = _generators()[ARGOCD_READ_GENERATOR]["_path"]
    apps = [d for d in _render() if d.get("kind") == "Application"]
    for path in (es_path, gen_path):
        rel = str(path.parent.relative_to(REPO))
        owning = [
            a for a in apps
            if (a["spec"].get("source") or {}).get("path", "").rstrip("/") == rel
        ]
        assert owning, f"no Application sources {rel} — {path.name} would never be applied"
        assert all(a["spec"]["destination"].get("namespace") == "argocd" for a in owning), (
            f"the Application owning {rel} must target namespace argocd: "
            f"{[a['metadata']['name'] for a in owning]}"
        )


def test_repo_credential_comment_documents_the_consumer_namespace_pem():
    """ESO resolves privateKey.secretRef in the CONSUMING ExternalSecret's
    namespace, which hid frank-gitops-push for seven days. The COMMENT (not the
    YAML body, where `namespace: argocd` appears anyway) must name the PEM
    Secret, the argocd namespace, and the manual op that places it there."""
    path = _runs_fr_repo_es()["_path"]
    comments = "\n".join(
        line for line in path.read_text().splitlines() if line.lstrip().startswith("#")
    )
    for needle in ("github-app-derio-key", "argocd", MANUAL_OP_ID):
        assert needle in comments, (
            f"{path.relative_to(REPO)} comments must mention {needle!r}"
        )
