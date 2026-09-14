"""Guard the staging-gate vCluster's ArgoCD wiring (Phase 7, plan
2026-06-15-staging-vcluster-gate).

Two things must hold once the staging vCluster is registered out-of-band as an
ArgoCD cluster named `staging` (manual op, not this repo):

1. `runs-fr-staging` and the `infrastructure` AppProject must address it BY
   NAME (`destination.name: staging`), the same pattern already used for
   `cnc-staging` — never `destination.server`, which requires ArgoCD to
   resolve a server URL against the registered cluster list at apply time and
   is more brittle than a name lookup once a cluster is registered.

2. ArgoCD needs a repository credential to clone the PRIVATE
   github.com/derio-net/runs-fr chart repo — every other Application in this
   repo sources the public derio-net/frank repo, so no such credential exists
   yet (verified live 2026-09-14: `argocd repo list` has no entry for
   runs-fr). The credential is minted by the existing `github-app-derio`
   ClusterGenerator (apps/secure-agent-pod/manifests/clustergenerator-github-
   app.yaml) — no new generator — following the repo-stoa-companies precedent
   (apps/argocd-extras/manifests/externalsecret-repo-stoa-companies.yaml).

LOCAL guards (frank does not run scripts/tests/ in CI). The Application/
AppProject assertions shell out to `helm template apps/root` (fail-closed:
non-zero return / missing render -> assertion error, never a false-green).
The ExternalSecret/ClusterGenerator assertions read the raw manifests
directly — apps/root only renders the App-of-Apps CRs, not what each
Application deploys.
"""

import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROOT_CHART = REPO / "apps/root"

STAGING_VCLUSTER_URL = "https://staging.vcluster-staging.svc:443"
RUNS_FR_REPO_URL = "https://github.com/derio-net/runs-fr.git"


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
    """Raw (non-Helm-templated) manifests under apps/*/manifests/*.yaml.

    apps/root only renders the App-of-Apps Application/AppProject/Namespace
    CRs — everything each Application deploys (ExternalSecrets,
    ClusterGenerators, ...) lives as plain YAML that ArgoCD applies straight
    from git, so it must be read directly rather than via `helm template
    apps/root`.
    """
    docs = []
    for path in REPO.glob("apps/*/manifests/*.yaml"):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc:
                doc["_path"] = path
                docs.append(doc)
    return docs


def test_runs_fr_staging_addresses_the_vcluster_by_name():
    app = _find(_render(), "Application", "runs-fr-staging")
    dest = app["spec"]["destination"]
    assert dest.get("name") == "staging", (
        f"runs-fr-staging must target destination.name: staging (like "
        f"cnc-staging), got: {dest}"
    )
    assert "server" not in dest, (
        f"runs-fr-staging must not use destination.server once the vCluster "
        f"is registered by name: {dest}"
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
    docs = _raw_manifests()
    secrets_es = [
        d
        for d in docs
        if d.get("kind") == "ExternalSecret"
        and d.get("metadata", {}).get("namespace") == "argocd"
    ]
    assert secrets_es, "no ExternalSecret found in namespace argocd"

    matches = []
    for es in secrets_es:
        template = es.get("spec", {}).get("target", {}).get("template", {})
        data = template.get("data", {}) or {}
        if data.get("url") == RUNS_FR_REPO_URL:
            matches.append(es)
    assert matches, (
        f"no ArgoCD repository ExternalSecret templates a Secret for "
        f"{RUNS_FR_REPO_URL}"
    )
    es = matches[0]
    spec = es["spec"]
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

    data_from = spec.get("dataFrom") or []
    assert data_from, f"ExternalSecret must mint the token via dataFrom: {spec}"
    generator_names = {
        entry.get("sourceRef", {}).get("generatorRef", {}).get("name")
        for entry in data_from
    }
    assert generator_names == {"github-app-derio"}, (
        f"must reuse the existing github-app-derio ClusterGenerator, not a "
        f"new one: {generator_names}"
    )

    refresh = spec.get("refreshInterval", "")
    assert refresh.endswith("m") and int(refresh[:-1]) < 60, (
        f"refreshInterval must stay under the ~1h installation-token TTL, "
        f"got: {refresh!r}"
    )


def test_repo_credential_manifest_is_wired_into_an_argocd_ns_application():
    """A manifest with no Application CR pointing at its directory is inert.

    Must NOT widen `staging-gate` (which targets tekton-pipelines) — the
    owning Application must already target namespace argocd.
    """
    docs = _raw_manifests()
    es = next(
        (
            d
            for d in docs
            if d.get("kind") == "ExternalSecret"
            and d.get("metadata", {}).get("namespace") == "argocd"
            and (d.get("spec", {}).get("target", {}).get("template", {}).get("data", {}) or {}).get("url")
            == RUNS_FR_REPO_URL
        ),
        None,
    )
    assert es, "runs-fr repository ExternalSecret not found among raw manifests"
    manifests_dir = es["_path"].parent

    apps = [d for d in _render() if d.get("kind") == "Application"]
    owning = [
        a
        for a in apps
        if a["spec"].get("source", {}).get("path", "").rstrip("/")
        == str(manifests_dir.relative_to(REPO))
    ]
    assert owning, (
        f"no Application sources {manifests_dir.relative_to(REPO)} — the "
        "ExternalSecret would never be applied"
    )
    assert all(a["spec"]["destination"].get("namespace") == "argocd" for a in owning), (
        f"the owning Application must target namespace argocd, not widen "
        f"staging-gate's tekton-pipelines scope: {owning}"
    )


def test_no_second_github_app_cluster_generator_is_added():
    """Phase 7 must reuse `github-app-derio` (the derio-net App installation
    that already covers runs-fr — it installs across ALL derio-net repos) —
    not mint a runs-fr-specific ClusterGenerator. The other two pre-existing
    generators (github-app-derio-homelab, github-app-stoa) are untouched
    baseline, not something this phase adds or removes."""
    docs = _raw_manifests()
    generators = [d for d in docs if d.get("kind") == "ClusterGenerator"]
    names = {g["metadata"]["name"] for g in generators}
    assert "github-app-derio" in names, "github-app-derio must still exist"
    assert not any("runs-fr" in n for n in names), (
        f"no runs-fr-specific ClusterGenerator should be added: {names}"
    )


def test_repo_credential_manifest_documents_the_consumer_namespace_key():
    """ESO resolves privateKey.secretRef in the CONSUMING ExternalSecret's
    namespace (argocd), not the generator's original namespace
    (secure-agent-pod) — this bit frank-gitops-push once already (see
    frank-gotchas.md). The manifest comment must say so, and must name the
    manual op that copies the PEM into argocd."""
    candidates = list(REPO.glob("apps/*/manifests/*.yaml"))
    for path in candidates:
        raw = path.read_text()
        if RUNS_FR_REPO_URL not in raw or "ExternalSecret" not in raw:
            continue
        assert "argocd" in raw and "cicd-staging-gate-argocd-runs-fr-repo-key" in raw, (
            f"{path.relative_to(REPO)} must document the consumer-namespace "
            "PEM requirement and name the manual op "
            "cicd-staging-gate-argocd-runs-fr-repo-key"
        )
        return
    raise AssertionError(
        f"no manifest under apps/*/manifests found for {RUNS_FR_REPO_URL}"
    )
