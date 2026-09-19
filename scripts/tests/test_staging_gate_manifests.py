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

# The ArgoCD cluster registration (P11, out-of-band) keeps the `.svc` form --
# tlsClientConfig.insecure: true (cnc-staging precedent) skips hostname
# verification entirely, so the SAN mismatch below does not apply to it.
STAGING_VCLUSTER_URL = "https://staging.vcluster-staging.svc:443"
# P9 review (C2, Critical): the gate's OWN kubeconfig (exportKubeConfig.
# additionalSecrets, consumed with full TLS verification -- no insecure flag)
# must use a hostname that is an actual SAN on the syncer certificate. A live
# TLS handshake against the cnc-staging vCluster (same chart, same version)
# proved `<name>.<namespace>` IS a SAN (e.g. `cnc-staging.cnc-staging-vcluster`)
# but `<name>.<namespace>.svc` is NOT -- so the gate kubeconfig's server must
# be the `.svc`-LESS form, the opposite of the ArgoCD registration above.
STAGING_GATE_KUBECONFIG_URL = "https://staging.vcluster-staging:443"
EXTRA_SANS = ["staging.vcluster-staging.svc", "staging.vcluster-staging.svc.cluster.local"]
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


TEKTON_DIR = REPO / "apps/staging-gate/tekton"
RETIRED_SSH_NEEDLES = ("staging-gate-ssh-creds", "id_rsa", "git@github.com")
PUSH_SECRET_NAME = "frank-gitops-push"
PUSH_SECRET_KEY = "token"


def _tekton_docs() -> list[dict]:
    """Every YAML doc under apps/staging-gate/tekton/, tagged with `_path` (raw
    manifests — this dir is applied directly by ArgoCD's directory recurse, not
    templated through apps/root)."""
    docs = []
    for path in sorted(TEKTON_DIR.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc:
                doc["_path"] = path
                docs.append(doc)
    return docs


def _iter_steps(docs: list[dict]):
    """Yield (doc, step) for every step in every Task/Pipeline (incl. finally and
    inline taskSpecs), so a git-plumbing assertion catches the step wherever it
    currently lives."""
    for doc in docs:
        kind = doc.get("kind")
        task_specs: list[dict] = []
        if kind == "Task":
            task_specs.append(doc.get("spec", {}))
        elif kind == "Pipeline":
            for entry in doc.get("spec", {}).get("tasks", []) + doc.get("spec", {}).get("finally", []):
                if entry.get("taskSpec"):
                    task_specs.append(entry["taskSpec"])
        for spec in task_specs:
            for step in spec.get("steps", []):
                yield doc, step


def _find_task(docs: list[dict], name: str) -> dict:
    for doc in docs:
        if doc.get("kind") == "Task" and doc.get("metadata", {}).get("name") == name:
            return doc
    raise AssertionError(f"no Task/{name} found under {TEKTON_DIR}")


def _find_pipeline(docs: list[dict]) -> dict:
    for doc in docs:
        if doc.get("kind") == "Pipeline":
            return doc
    raise AssertionError(f"no Pipeline found under {TEKTON_DIR}")


def _pipeline_task(pipeline: dict, name: str) -> dict:
    for t in pipeline["spec"]["tasks"]:
        if t["name"] == name:
            return t
    raise AssertionError(f"no pipeline task {name!r} in {pipeline['metadata']['name']}")


def test_no_manifest_references_the_retired_ssh_credential():
    for path in sorted(TEKTON_DIR.glob("*.yaml")):
        text = path.read_text()
        for needle in RETIRED_SSH_NEEDLES:
            assert needle not in text, (
                f"{path.relative_to(REPO)} still references retired SSH plumbing: {needle!r}"
            )


def test_git_pushing_steps_read_the_github_app_token():
    """Behaviour-level, not shape-level: whether the git-push plumbing lives inline
    per step (pre-refactor) or in the shared `staging-gate-git` StepAction
    (P8.T2.S3 REFACTOR), the actual `git push` must read GITHUB_TOKEN from
    frank-gitops-push/token, and every push-mode caller must route through it.

    P8 review (p8-m4): this used to `return` as soon as the StepAction was
    found, so the inline-step scan below never ran — a stray inline `git push`
    step missing GITHUB_TOKEN would have gone unnoticed. Both checks always run
    now."""
    docs = _tekton_docs()
    step_action = next(
        (
            d for d in docs
            if d.get("kind") == "StepAction" and d.get("metadata", {}).get("name") == "staging-gate-git"
        ),
        None,
    )
    if step_action is not None:
        spec = step_action["spec"]
        assert "git push" in spec.get("script", ""), (
            "staging-gate-git StepAction must contain the git push plumbing"
        )
        env = {e["name"]: e for e in spec.get("env", [])}
        assert "GITHUB_TOKEN" in env, "staging-gate-git StepAction has no GITHUB_TOKEN env"
        ref = env["GITHUB_TOKEN"].get("valueFrom", {}).get("secretKeyRef", {})
        assert ref == {"name": PUSH_SECRET_NAME, "key": PUSH_SECRET_KEY}, (
            f"staging-gate-git GITHUB_TOKEN must come from {PUSH_SECRET_NAME}/{PUSH_SECRET_KEY}, "
            f"got: {ref}"
        )
        push_callers = [
            (doc, step)
            for doc, step in _iter_steps(docs)
            if step.get("ref", {}).get("name") == "staging-gate-git"
            and any(p.get("name") == "mode" and p.get("value") == "push" for p in step.get("params", []))
        ]
        assert push_callers, (
            "expected at least one step calling staging-gate-git in push mode"
        )

    found_push = False
    for doc, step in _iter_steps(docs):
        if "git push" not in step.get("script", ""):
            continue
        found_push = True
        env = {e["name"]: e for e in step.get("env", [])}
        assert "GITHUB_TOKEN" in env, (
            f"{doc['_path'].name}/{step.get('name')}: git-pushing step has no GITHUB_TOKEN env"
        )
        ref = env["GITHUB_TOKEN"].get("valueFrom", {}).get("secretKeyRef", {})
        assert ref == {"name": PUSH_SECRET_NAME, "key": PUSH_SECRET_KEY}, (
            f"{doc['_path'].name}/{step.get('name')}: GITHUB_TOKEN must come from "
            f"{PUSH_SECRET_NAME}/{PUSH_SECRET_KEY}, got: {ref}"
        )
    if step_action is None:
        assert found_push, "expected at least one git-pushing step under apps/staging-gate/tekton"


def test_stepaction_scripts_never_splice_params_directly():
    """P8 review (p8-c1, Critical): Tekton v1beta1 rejects `$(params.*)` inside a
    StepAction `script` ("param substitution in scripts is not allowed"), and
    splicing untrusted trigger-payload-derived values (app/sha/message) straight
    into a shell script would also be a command-injection path. Every StepAction
    must pass params through env and read only "$VAR"."""
    for doc in _tekton_docs():
        if doc.get("kind") != "StepAction":
            continue
        script = doc.get("spec", {}).get("script", "")
        assert "$(params." not in script, (
            f"{doc['_path'].name}/{doc['metadata']['name']}: StepAction script must not "
            f"splice $(params.*) — read via env instead:\n{script}"
        )


def test_stepaction_has_no_computeresources_field():
    """P8 review (p8-i2, Important): computeResources is not a v1beta1
    StepActionSpec field — kubectl apply --dry-run=server --validate=strict
    fails with 'unknown field spec.computeResources'. It must live on each
    calling ref step instead."""
    step_action = next(
        d for d in _tekton_docs()
        if d.get("kind") == "StepAction" and d.get("metadata", {}).get("name") == "staging-gate-git"
    )
    assert "computeResources" not in step_action["spec"], (
        f"StepAction spec must not set computeResources: {step_action['spec'].keys()}"
    )


FORBIDDEN_REF_STEP_FIELDS = {"image", "command", "args", "script", "workingDir", "env", "volumeMounts"}


def test_ref_steps_calling_the_stepaction_carry_their_own_computeresources():
    """P8 review (p8-i2): each `ref:` step must set its own computeResources
    (moved off the StepAction) but must not override a field the StepAction
    itself owns."""
    docs = _tekton_docs()
    callers = [
        (doc, step)
        for doc, step in _iter_steps(docs)
        if step.get("ref", {}).get("name") == "staging-gate-git"
    ]
    assert callers, "expected at least one step to ref: staging-gate-git"
    for doc, step in callers:
        assert "computeResources" in step, (
            f"{doc['_path'].name}/{step.get('name')}: ref step must set its own "
            f"computeResources now that the StepAction cannot"
        )
        overridden = FORBIDDEN_REF_STEP_FIELDS & step.keys()
        assert not overridden, (
            f"{doc['_path'].name}/{step.get('name')}: ref step must not set "
            f"{sorted(overridden)} — those belong to the StepAction"
        )


def test_no_pipeline_task_reads_another_tasks_status_outside_finally():
    """P8 review (p8-c2, Critical): confirmed by kubectl apply --dry-run=server —
    'pipeline tasks can not refer to execution status ... of any other pipeline
    task'. $(tasks.<x>.status)/.reason or $(tasks.status) are legal only in
    finally."""
    import re

    pattern = re.compile(r"\$\(tasks\.[\w-]+\.(status|reason)\)|\$\(tasks\.status\)")
    pipeline = _find_pipeline(_tekton_docs())
    for task in pipeline["spec"]["tasks"]:
        text = yaml.safe_dump(task)
        assert not pattern.search(text), (
            f"pipeline task {task['name']!r} references task status/reason outside "
            f"finally, which Tekton rejects: {text}"
        )


TEKTON_TOKEN_NEEDLES = ("x-access-token:", "${GITHUB_TOKEN}@")


def test_no_clone_or_push_url_embeds_the_token():
    """P8 review (p8-m1, Moderate): the token must never be embedded in a clone
    or push URL (it would land in .git/config in the scratch clone). Auth goes
    through a credential.helper that names the env var, not the value."""
    for path in sorted(TEKTON_DIR.glob("*.yaml")):
        text = path.read_text()
        for needle in TEKTON_TOKEN_NEEDLES:
            assert needle not in text, (
                f"{path.relative_to(REPO)} embeds a token directly in a URL: {needle!r}"
            )


def test_stepaction_push_mode_is_a_noop_on_an_unchanged_file_and_retries_the_push():
    """P8 review (p8-i1 + p8-m2): re-gating the same sha must not fail on an
    empty commit (git add; git diff --cached --quiet => exit 0, as
    cnc-promotion does), and a non-fast-forward push must retry (bounded) by
    rebasing onto origin/main, as apps/tekton/pipelines/site-promotion.yaml
    does, rather than failing the whole run on a race."""
    step_action = next(
        d for d in _tekton_docs()
        if d.get("kind") == "StepAction" and d.get("metadata", {}).get("name") == "staging-gate-git"
    )
    script = step_action["spec"]["script"]
    assert "git diff --cached --quiet" in script, (
        "push mode must no-op on an unchanged target file"
    )
    assert "git push" in script and "while" in script, (
        "push mode must retry the push in a bounded loop"
    )
    assert "rebase" in script, (
        "push mode's retry must rebase onto origin/main before retrying"
    )


def test_resolve_contract_validates_app_and_sha_before_use():
    """P8 review (p8-rec, Recommendation): defence in depth — a manual
    PipelineRun bypasses phase 10's CEL trigger validation, and app/sha reach a
    filesystem path (registry lookup) and shell scripts respectively."""
    pipeline = _find_pipeline(_tekton_docs())
    resolve = _pipeline_task(pipeline, "resolve-contract")
    task_params = {p["name"] for p in resolve["taskSpec"]["params"]}
    assert "sha" in task_params, "resolve-contract must take a sha param to validate it"
    pipeline_params = {p["name"] for p in resolve["params"]}
    assert "sha" in pipeline_params, "the pipeline must pass sha into resolve-contract"

    steps = resolve["taskSpec"]["steps"]
    assert steps[0]["name"] == "validate-inputs", (
        f"resolve-contract's first step must validate inputs, got: {[s['name'] for s in steps]}"
    )
    validate_script = steps[0].get("script", "")
    assert "$(params." not in validate_script, (
        "validate-inputs must read app/sha via env, not $(params.*) splicing"
    )
    assert "a-f0-9" in validate_script, "validate-inputs must regex-check sha"
    assert "a-z0-9" in validate_script, "validate-inputs must regex-check app"


def test_resolve_contract_read_step_reads_app_via_env():
    """Scope check (P8 review): app derives from the GHA repository_dispatch
    payload and is used to build a filesystem path — read via env, not spliced
    with $(params.app) directly into the script."""
    pipeline = _find_pipeline(_tekton_docs())
    resolve = _pipeline_task(pipeline, "resolve-contract")
    read_step = next(s for s in resolve["taskSpec"]["steps"] if s["name"] == "read")
    assert "$(params.app)" not in read_step.get("script", ""), (
        "resolve-contract's read step must read app via env, not $(params.app)"
    )
    env_names = {e["name"] for e in read_step.get("env", [])}
    assert "APP" in env_names, "resolve-contract's read step must set an APP env var"


def test_run_smoke_reads_app_and_sha_via_env():
    """Scope check (P8 review): app/sha derive from the trigger payload; run-smoke
    builds a Job name and image tag from them — read via env, not $(params.*)."""
    run_smoke = _find_task(_tekton_docs(), "staging-gate-run-smoke")
    smoke_step = next(s for s in run_smoke["spec"]["steps"] if s["name"] == "smoke")
    script = smoke_step.get("script", "")
    assert "$(params.app)" not in script and "$(params.sha)" not in script, (
        f"staging-gate-run-smoke must read app/sha via env, not $(params.*): {script}"
    )
    env_names = {e["name"] for e in smoke_step.get("env", [])}
    assert {"APP", "SHA"} <= env_names, (
        f"staging-gate-run-smoke's smoke step must set APP and SHA env vars: {env_names}"
    )


def test_promote_task_writes_the_last_green_record():
    promote = _find_task(_tekton_docs(), "staging-gate-promote")
    params = {p["name"] for p in promote["spec"]["params"]}
    assert "prodValuesKey" not in params, (
        f"staging-gate-promote must not carry the retired prodValuesKey param: {params}"
    )
    assert "promotedRecordPath" in params, (
        f"staging-gate-promote must take promotedRecordPath: {params}"
    )
    scripts = "\n".join(s.get("script", "") for s in promote["spec"]["steps"])
    # P8 review (p8-m4): ".sha" alone is satisfied by the substring inside
    # "$(params.sha)" even with the actual yq write deleted. Assert on the real
    # write form instead.
    for field in (".sha = strenv(", ".image = strenv(", ".pipelineRun = strenv("):
        assert field in scripts, (
            f"staging-gate-promote steps must write {field!r} into the record: {scripts}"
        )
    assert ".promotedAt = strenv(" in scripts, (
        f"staging-gate-promote steps must write .promotedAt into the record: {scripts}"
    )
    assert "$(params.promotedRecordPath)" in scripts, (
        "staging-gate-promote steps must reference $(params.promotedRecordPath)"
    )


def test_resolve_contract_exposes_the_v2_results():
    pipeline = _find_pipeline(_tekton_docs())
    resolve = _pipeline_task(pipeline, "resolve-contract")
    results = {r["name"] for r in resolve["taskSpec"]["results"]}
    for name in ("promotedRecordPath", "smokeRbacUrl"):
        assert name in results, (
            f"resolve-contract must expose a {name!r} result, got: {sorted(results)}"
        )


def test_no_secrets_read_role_exists():
    """P8 review (p8-m3): secretKeyRef env is resolved by the kubelet, not the pod
    ServiceAccount, so staging-gate-secrets-read only widened who could read
    frank-gitops-push via the automounted SA token in third-party step images.
    The vcluster kubeconfig is likewise injected as a workspace Secret volume,
    never read via the API. Neither needs RBAC — the Role must be gone."""
    names = {
        d.get("metadata", {}).get("name")
        for d in _tekton_docs()
        if d.get("kind") in ("Role", "RoleBinding")
    }
    assert "staging-gate-secrets-read" not in names, (
        f"staging-gate-secrets-read must be removed (unneeded privilege): {names}"
    )


VCLUSTER_TEMPLATE_VALUES = REPO / "apps/vclusters/template/values.yaml"
VCLUSTER_STAGING_VALUES = REPO / "apps/vclusters/staging/values.yaml"
VCLUSTER_CHART_VERSION = "0.32.1"
VCLUSTER_GATE_SECRET = "vc-staging-gate"


def _render_vcluster_staging() -> list[dict]:
    """Render the loft `vcluster` chart with template+staging values — fail closed:
    a chart schema violation (P9 lesson: kubeconform/pytest can both pass a shape
    the chart itself, or Tekton's webhook, rejects) must fail this test, not be
    silently skipped."""
    out = subprocess.run(
        [
            "helm", "template", "staging", "vcluster",
            "--repo", "https://charts.loft.sh",
            "--version", VCLUSTER_CHART_VERSION,
            "-n", "vcluster-staging",
            "-f", str(VCLUSTER_TEMPLATE_VALUES),
            "-f", str(VCLUSTER_STAGING_VALUES),
        ],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, f"helm template of the vcluster chart failed:\n{out.stderr}"
    docs = [d for d in yaml.safe_load_all(out.stdout) if d]
    assert docs, "vcluster chart render produced no documents"
    return docs


def test_vcluster_staging_chart_renders_with_the_gate_kubeconfig_export():
    _render_vcluster_staging()
    doc = yaml.safe_load(VCLUSTER_STAGING_VALUES.read_text())
    additional = (doc.get("exportKubeConfig") or {}).get("additionalSecrets")
    assert additional == [{"name": VCLUSTER_GATE_SECRET, "server": STAGING_GATE_KUBECONFIG_URL}], (
        f"exportKubeConfig.additionalSecrets must declare exactly one entry "
        f"{{name: {VCLUSTER_GATE_SECRET}, server: {STAGING_GATE_KUBECONFIG_URL}}} "
        f"(no namespace override -- defaults to the vCluster's own host ns): {additional}"
    )


def test_vcluster_staging_never_sets_the_singular_exportkubeconfig_secret():
    """P9 review (M6): exportKubeConfig.secret and exportKubeConfig.additionalSecrets
    are MUTUALLY EXCLUSIVE -- confirmed live: rendering the chart with both set
    fails outright (`exportKubeConfig.secret and exportKubeConfig.additionalSecrets
    cannot be set at the same time`, vcluster/templates/statefulset.yaml). Setting
    `secret` here would not silently coexist with `additionalSecrets`; it would
    break the whole chart render."""
    doc = yaml.safe_load(VCLUSTER_STAGING_VALUES.read_text())
    assert "secret" not in (doc.get("exportKubeConfig") or {}), (
        "exportKubeConfig.secret must stay unset -- it is mutually exclusive "
        "with additionalSecrets, not merely 'ignored'"
    )


def test_vcluster_staging_declares_extra_sans_for_the_svc_form_hostnames():
    """P9 review (C2): the ArgoCD cluster registration (P11, out-of-band) keeps
    the `.svc` hostname form with tlsClientConfig.insecure: true, but registering
    it WITHOUT insecure some day (or any other future `.svc` consumer) needs the
    syncer cert to actually carry that SAN. controlPlane.proxy.extraSANs is the
    chart's real config key (verified live: helm template with it set decodes,
    inside the rendered vc-config-staging Secret's config.yaml, to
    controlPlane.proxy.extraSANs -- exactly where the chart's own values.schema
    documents it: 'extra hostnames to sign the vCluster proxy certificate for')."""
    docs = _render_vcluster_staging()
    doc = yaml.safe_load(VCLUSTER_STAGING_VALUES.read_text())
    extra_sans = ((doc.get("controlPlane") or {}).get("proxy") or {}).get("extraSANs")
    assert extra_sans == EXTRA_SANS, (
        f"controlPlane.proxy.extraSANs must declare {EXTRA_SANS}: {extra_sans}"
    )

    import base64
    import re

    config_secret = next(
        d for d in docs
        if d.get("kind") == "Secret" and d.get("metadata", {}).get("name") == "vc-config-staging"
    )
    rendered_cfg = yaml.safe_load(base64.b64decode(config_secret["data"]["config.yaml"]))
    assert rendered_cfg["controlPlane"]["proxy"]["extraSANs"] == EXTRA_SANS, (
        "the chart must actually read controlPlane.proxy.extraSANs into the "
        f"syncer's config.yaml: {rendered_cfg['controlPlane']['proxy']}"
    )


def _rbac_docs() -> list[dict]:
    docs = []
    for doc in yaml.safe_load_all((TEKTON_DIR / "serviceaccount-rbac.yaml").read_text()):
        if doc:
            docs.append(doc)
    return docs


def test_vcluster_kubeconfig_role_is_scoped_to_the_gate_secret_only():
    docs = _rbac_docs()
    role = next(
        (
            d for d in docs
            if d.get("kind") == "Role" and d.get("metadata", {}).get("namespace") == "vcluster-staging"
        ),
        None,
    )
    assert role is not None, "expected a Role in namespace vcluster-staging for the gate kubeconfig"
    rules = role["rules"]
    assert len(rules) == 1, f"expected exactly one rule: {rules}"
    rule = rules[0]
    assert rule.get("resources") == ["secrets"]
    assert rule.get("verbs") == ["get"]
    assert rule.get("resourceNames") == [VCLUSTER_GATE_SECRET], (
        f"the Role must be restricted to {VCLUSTER_GATE_SECRET} only: {rule}"
    )

    binding = next(
        (
            d for d in docs
            if d.get("kind") == "RoleBinding" and d.get("metadata", {}).get("namespace") == "vcluster-staging"
        ),
        None,
    )
    assert binding is not None, "expected a RoleBinding alongside the vcluster-staging Role"
    assert binding["roleRef"]["name"] == role["metadata"]["name"]
    assert binding["subjects"] == [
        {"kind": "ServiceAccount", "name": "staging-gate", "namespace": "tekton-pipelines"}
    ]


def test_no_manifest_references_the_retired_vcluster_kubeconfig_workspace():
    """The retired June design: a `vcluster-kubeconfig` WORKSPACE fed by a
    `vcluster-staging-kubeconfig` manual Secret. P9.T1 replaces both with an
    RBAC-gated `kubectl get secret` fetch (whose Role is legitimately named
    `staging-gate-vcluster-kubeconfig-read` — that name is fine; only the
    retired workspace/secret NAMES are checked for)."""
    for doc in _tekton_docs():
        if doc.get("kind") in ("Pipeline", "Task"):
            for spec in (
                [doc.get("spec", {})]
                if doc["kind"] == "Task"
                else [
                    doc.get("spec", {}),
                    *[
                        t.get("taskSpec", {})
                        for t in doc.get("spec", {}).get("tasks", []) + doc.get("spec", {}).get("finally", [])
                        if t.get("taskSpec")
                    ],
                ]
            ):
                names = {w.get("name") for w in spec.get("workspaces", [])}
                assert "vcluster-kubeconfig" not in names, (
                    f"{doc['_path'].name}/{doc['metadata']['name']}: still declares the "
                    f"retired vcluster-kubeconfig workspace: {names}"
                )
        if doc.get("kind") == "TriggerTemplate":
            for rt in doc["spec"].get("resourcetemplates", []):
                for w in rt.get("spec", {}).get("workspaces", []):
                    assert w.get("name") != "vcluster-kubeconfig", (
                        f"TriggerTemplate still binds the retired vcluster-kubeconfig workspace: {w}"
                    )
                    secret_name = (w.get("secret") or {}).get("secretName")
                    assert secret_name != "vcluster-staging-kubeconfig", (
                        f"TriggerTemplate still references the retired manual Secret: {w}"
                    )


NO_SHELL_IMAGES = ("rancher/kubectl",)


def test_no_step_with_a_script_uses_a_shell_less_image():
    """P9 finding: `rancher/kubectl:v1.31.4` is "kubectl from scratch" -- a single
    static binary with NO shell at all. Confirmed 2026-09-15 with a direct docker
    run negative control: executing a `#!/bin/sh` script against it fails
    `exec ...: no such file or directory` (the OS can't find the shebang
    interpreter). Tekton's `script:` mechanism requires a shell in the image, so
    every existing rancher/kubectl step (await-sync, the old run-smoke/reset
    steps) would fail at pod runtime -- invisible to `kubectl apply --dry-run`
    and to structural pytest, exactly the class of bug this phase's admission
    gate and behaviour tests exist to catch. Fixed by switching to
    bitnamilegacy/kubectl:1.33.4 (Debian-based, has bash/date/base64/awk),
    already used elsewhere in the repo (apps/tekton/manifests/pipelinerun-ttl-gc.yaml)."""
    for doc, step in _iter_steps(_tekton_docs()):
        if "script" not in step:
            continue
        image = step.get("image", "")
        for needle in NO_SHELL_IMAGES:
            assert needle not in image, (
                f"{doc['_path'].name}/{step.get('name')}: step has a script but uses "
                f"the shell-less image {image!r}"
            )


def test_run_smoke_and_reset_fetch_kubeconfig_via_the_host_api_not_a_workspace():
    for task_name in ("staging-gate-run-smoke", "staging-gate-reset"):
        task = _find_task(_tekton_docs(), task_name)
        assert "workspaces" not in task["spec"], (
            f"{task_name} must no longer declare a workspaces list: {task['spec'].get('workspaces')}"
        )
        fetch = next(s for s in task["spec"]["steps"] if s["name"] == "fetch-kubeconfig")
        script = fetch.get("script", "")
        assert "get secret vc-staging-gate" in script and "-n vcluster-staging" in script, (
            f"{task_name}/fetch-kubeconfig must fetch vc-staging-gate from vcluster-staging: {script}"
        )
        assert "umask 077" in script, f"{task_name}/fetch-kubeconfig must umask 077: {script}"
        assert "cat" not in [line.strip().split(" ", 1)[0] for line in script.splitlines() if line.strip()], (
            f"{task_name}/fetch-kubeconfig must never `cat` the fetched kubeconfig: {script}"
        )


def test_run_smoke_fetches_the_gated_smoke_rbac_with_the_app_token():
    run_smoke = _find_task(_tekton_docs(), "staging-gate-run-smoke")
    params = {p["name"] for p in run_smoke["spec"]["params"]}
    assert {"smokeRbacUrl", "smokeServiceAccount"} <= params, (
        f"staging-gate-run-smoke must take smokeRbacUrl and smokeServiceAccount: {params}"
    )
    fetch = next(s for s in run_smoke["spec"]["steps"] if s["name"] == "fetch-smoke-rbac")
    assert fetch["image"].startswith("curlimages/curl"), fetch["image"]
    assert fetch["securityContext"]["runAsUser"] == 100, (
        "curlimages/curl needs a non-numeric-user-safe runAsUser (P8/repo gotcha)"
    )
    script = fetch.get("script", "")
    assert "curl -fsS" in script, "the fetch must fail closed (curl -fsS)"
    assert "Accept: application/vnd.github.raw" in script
    assert "{sha}" in script, "the sha placeholder must be substituted in the script"
    env = {e["name"]: e for e in fetch.get("env", [])}
    assert env.get("SMOKE_RBAC_URL", {}).get("value") == "$(params.smokeRbacUrl)"
    assert env.get("SHA", {}).get("value") == "$(params.sha)"
    ref = env.get("GITHUB_TOKEN", {}).get("valueFrom", {}).get("secretKeyRef", {})
    assert ref == {"name": PUSH_SECRET_NAME, "key": PUSH_SECRET_KEY}, (
        f"fetch-smoke-rbac must authenticate with {PUSH_SECRET_NAME}/{PUSH_SECRET_KEY}: {ref}"
    )


def test_run_smoke_creates_namespace_applies_rbac_and_sets_the_contract_service_account():
    run_smoke = _find_task(_tekton_docs(), "staging-gate-run-smoke")
    smoke_step = next(s for s in run_smoke["spec"]["steps"] if s["name"] == "smoke")
    script = smoke_step.get("script", "")
    assert "create namespace" in script and "--dry-run=client" in script, (
        "run-smoke must create smokeNamespace idempotently"
    )
    assert "smoke-rbac.yaml" in script, "run-smoke must apply the fetched smoke RBAC manifest"
    assert "serviceAccountName: $SMOKE_SA" in script
    assert "GATEWAY_URL" in script and "SMOKE_NAMESPACE" in script
    env = {e["name"]: e for e in smoke_step.get("env", [])}
    assert env.get("SMOKE_SA", {}).get("value") == "$(params.smokeServiceAccount)"
    assert env.get("KUBECONFIG", {}).get("value") == "/tekton/home/vc.kubeconfig"

    # P9 review (M5, Minor): reset deletes the namespace with --wait=false
    # (staging-gate-reset's script, below), so a re-gate of the same app run
    # back-to-back can hit "the system is terminating" on the next `create
    # namespace`/`apply`. Wait for the delete to actually finish first.
    wait_idx = next(
        i for i, line in enumerate(script.splitlines())
        if "kubectl wait" in line and "--for=delete" in line and 'ns/"$ns"' in line
    )
    create_idx = next(i for i, line in enumerate(script.splitlines()) if "create namespace" in line)
    assert wait_idx < create_idx, (
        f"must wait for a prior delete of $ns before (re)creating it: {script}"
    )
    wait_line = script.splitlines()[wait_idx]
    assert "|| true" in wait_line, (
        f"the wait must not fail the step on a first-ever run (namespace never "
        f"existed, so there is nothing to wait for): {wait_line}"
    )


def test_pipeline_run_smoke_task_passes_smoke_rbac_and_service_account():
    pipeline = _find_pipeline(_tekton_docs())
    run_smoke = _pipeline_task(pipeline, "run-smoke")
    values = {p["name"]: p["value"] for p in run_smoke["params"]}
    assert values.get("smokeRbacUrl") == "$(tasks.resolve-contract.results.smokeRbacUrl)"
    assert values.get("smokeServiceAccount") == "$(tasks.resolve-contract.results.smokeServiceAccount)"


def test_resolve_contract_exposes_the_smoke_service_account_result():
    pipeline = _find_pipeline(_tekton_docs())
    resolve = _pipeline_task(pipeline, "resolve-contract")
    results = {r["name"] for r in resolve["taskSpec"]["results"]}
    assert "smokeServiceAccount" in results, sorted(results)
    read_step = next(s for s in resolve["taskSpec"]["steps"] if s["name"] == "read")
    assert "$(results.smokeServiceAccount.path)" in read_step.get("script", "")


def test_triggertemplate_labels_pipelineruns_by_app():
    tt = next(d for d in _tekton_docs() if d.get("kind") == "TriggerTemplate")
    pr_template = tt["spec"]["resourcetemplates"][0]
    labels = pr_template["metadata"].get("labels", {})
    assert labels.get("staging-gate/app") == "$(tt.params.app)", labels


def test_triggertemplate_pipelinerun_sets_explicit_timeouts_so_finally_survives_a_timeout():
    """P9 review (I3, Important): Tekton v1.6.0 CANCELS running `finally` TaskRuns
    (reset, notify) when timeouts.pipeline elapses, UNLESS timeouts.tasks is set
    strictly lower -- losing both the vCluster namespace cleanup and the red-path
    Telegram alert on exactly the run most likely to need them. The default
    pipeline timeout is 60m and wait-turn alone can consume up to 30m of it
    (waitTurnTimeoutSeconds default 1800), so an unset timeouts block is a real
    exposure, not a theoretical one."""
    tt = next(d for d in _tekton_docs() if d.get("kind") == "TriggerTemplate")
    pr_spec = tt["spec"]["resourcetemplates"][0]["spec"]
    timeouts = pr_spec.get("timeouts")
    assert timeouts == {"pipeline": "1h30m", "tasks": "1h20m", "finally": "10m"}, timeouts

    def _minutes(duration: str) -> int:
        import re
        h = re.search(r"(\d+)h", duration)
        m = re.search(r"(\d+)m", duration)
        return (int(h.group(1)) if h else 0) * 60 + (int(m.group(1)) if m else 0)

    assert _minutes(timeouts["tasks"]) < _minutes(timeouts["pipeline"]), (
        "timeouts.tasks must be strictly LESS than timeouts.pipeline, or Tekton "
        f"still cancels running finally TaskRuns on a pipeline timeout: {timeouts}"
    )


def test_resolve_contract_waits_its_turn_before_cloning():
    pipeline = _find_pipeline(_tekton_docs())
    resolve = _pipeline_task(pipeline, "resolve-contract")
    steps = resolve["taskSpec"]["steps"]
    names = [s["name"] for s in steps]
    assert names.index("validate-inputs") < names.index("wait-turn") < names.index("clone"), names

    wait = next(s for s in steps if s["name"] == "wait-turn")
    script = wait.get("script", "")
    assert "pipelineruns" in script and "staging-gate/app=" in script
    env = {e["name"]: e for e in wait.get("env", [])}
    assert env.get("SELF", {}).get("value") == "$(context.pipelineRun.name)"
    assert env.get("APP", {}).get("value") == "$(params.app)"
    task_params = {p["name"]: p for p in resolve["taskSpec"]["params"]}
    assert task_params.get("waitTurnTimeoutSeconds", {}).get("default") == "1800"


def test_wait_turn_timeout_is_a_real_pipeline_level_knob():
    """P9 review (M1, Minor): waitTurnTimeoutSeconds was declared on the embedded
    taskSpec's own params (with a default) but never surfaced as a Pipeline
    param and never passed into resolve-contract's task node -- so it was a
    default with no way to actually override it, not a knob. Plumb it through:
    a Pipeline-level param (same default, so nothing changes if unset) whose
    value resolve-contract's task node passes explicitly."""
    pipeline = _find_pipeline(_tekton_docs())
    pipeline_params = {p["name"]: p for p in pipeline["spec"]["params"]}
    assert pipeline_params.get("waitTurnTimeoutSeconds", {}).get("default") == "1800", (
        f"expected a Pipeline-level waitTurnTimeoutSeconds param with default 1800: {pipeline_params}"
    )
    resolve = _pipeline_task(pipeline, "resolve-contract")
    task_values = {p["name"]: p["value"] for p in resolve["params"]}
    assert task_values.get("waitTurnTimeoutSeconds") == "$(params.waitTurnTimeoutSeconds)", (
        f"resolve-contract's task node must pass the Pipeline param through: {task_values}"
    )


def test_pipelinerun_read_rbac_exists():
    docs = _rbac_docs()
    role = next(
        (
            d for d in docs
            if d.get("kind") == "Role" and d.get("metadata", {}).get("namespace") == "tekton-pipelines"
            and "pipelinerun" in d.get("metadata", {}).get("name", "")
        ),
        None,
    )
    assert role is not None, "expected a Role granting pipelinerun read in tekton-pipelines"
    rule = role["rules"][0]
    assert "pipelineruns" in rule.get("resources", [])
    assert set(rule.get("verbs", [])) >= {"get", "list"}
    assert "tekton.dev" in rule.get("apiGroups", [])

    binding = next(
        d for d in docs
        if d.get("kind") == "RoleBinding" and d.get("metadata", {}).get("name") == role["metadata"]["name"]
    )
    assert binding["subjects"] == [
        {"kind": "ServiceAccount", "name": "staging-gate", "namespace": "tekton-pipelines"}
    ]


def test_notify_runs_on_a_red_pipeline_using_only_raw_params_and_status():
    pipeline = _find_pipeline(_tekton_docs())
    finally_tasks = pipeline["spec"]["finally"]
    notify = next(t for t in finally_tasks if t["name"] == "notify")
    when = notify.get("when", [])
    assert any(
        w.get("input") == "$(tasks.status)"
        and w.get("operator") == "notin"
        and set(w.get("values", [])) == {"Succeeded", "Completed"}
        for w in when
    ), f"notify must gate on $(tasks.status) not in [Succeeded, Completed]: {when}"

    param_values = " ".join(str(p.get("value", "")) for p in notify.get("params", []))
    assert "resolve-contract.results" not in param_values, (
        "notify must never read resolve-contract RESULTS -- a failed/skipped "
        "resolve-contract would silently skip notify too"
    )
    assert "$(params.app)" in param_values
    assert "$(params.sha)" in param_values
    assert "$(context.pipelineRun.name)" in param_values
    for status_var in (
        "$(tasks.resolve-contract.status)",
        "$(tasks.bump-staging.status)",
        "$(tasks.await-sync.status)",
        "$(tasks.run-smoke.status)",
        "$(tasks.promote.status)",
    ):
        assert status_var in param_values, f"notify must read {status_var}: {param_values}"


def test_reset_documents_and_accepts_being_skipped_on_a_failed_resolve_contract():
    pipeline = _find_pipeline(_tekton_docs())
    reset = next(t for t in pipeline["spec"]["finally"] if t["name"] == "reset")
    param_values = " ".join(str(p.get("value", "")) for p in reset.get("params", []))
    assert "resolve-contract.results.smokeNamespace" in param_values
    text = (TEKTON_DIR / "pipeline.yaml").read_text()
    assert "reset is skipped" in text.lower() or "skips reset too" in text.lower(), (
        "pipeline.yaml must document why reset may be skipped when resolve-contract fails"
    )


def test_staging_gate_telegram_externalsecret_maps_the_c2_bot():
    doc = next(
        d for d in _tekton_docs()
        if d.get("kind") == "ExternalSecret" and d.get("metadata", {}).get("name") == "staging-gate-telegram"
    )
    assert doc["metadata"]["namespace"] == "tekton-pipelines"
    assert doc["spec"]["secretStoreRef"] == {"name": "infisical", "kind": "ClusterSecretStore"}
    keys = {d["secretKey"]: d["remoteRef"]["key"] for d in doc["spec"]["data"]}
    assert keys == {"token": "FRANK_C2_TELEGRAM_BOT_TOKEN", "chat-id": "FRANK_C2_TELEGRAM_CHAT_ID"}


def test_notify_task_reads_the_telegram_credential_and_sets_no_parse_mode():
    notify_task = _find_task(_tekton_docs(), "staging-gate-notify")
    step = notify_task["spec"]["steps"][0]
    env = {e["name"]: e for e in step.get("env", [])}
    assert env["TELEGRAM_TOKEN"]["valueFrom"]["secretKeyRef"] == {
        "name": "staging-gate-telegram", "key": "token", "optional": True
    }, (
        "P9 review (I4): optional: true, so an un-synced ExternalSecret leaves "
        "the env var empty instead of making the whole container un-startable "
        "(CreateContainerConfigError)"
    )
    assert env["TELEGRAM_CHAT_ID"]["valueFrom"]["secretKeyRef"] == {
        "name": "staging-gate-telegram", "key": "chat-id", "optional": True
    }
    script = step.get("script", "")
    non_comment = "\n".join(
        line for line in script.splitlines() if not line.strip().startswith("#")
    )
    assert "parse_mode" not in non_comment, (
        "the curl invocation itself must never set parse_mode (the HTML-400 trap), "
        f"even though the comment above it may mention the word: {non_comment}"
    )
    assert "tr -d '<>&'" in script
    assert "sendMessage" in script


def test_notify_step_sets_home_like_every_other_step():
    """P9 review (M9, Minor): every other step in this dir sets HOME=/tekton/home
    (several actually need it -- kubectl/git writes under it); notify was the
    only one that didn't. No functional need today (curlimages/curl writes
    nothing under HOME), but keep the step consistent with its siblings so a
    future edit that DOES need a writable HOME doesn't have to discover this."""
    notify_task = _find_task(_tekton_docs(), "staging-gate-notify")
    step = notify_task["spec"]["steps"][0]
    env = {e["name"]: e for e in step.get("env", [])}
    assert env.get("HOME", {}).get("value") == "/tekton/home", env.get("HOME")


def test_notify_step_has_a_short_explicit_timeout():
    """P9 review (I4): the un-synced-ExternalSecret failure mode is bounded by
    optional: true above, but an actual Telegram outage/hang should not consume
    the whole `finally` window either -- a short explicit step timeout."""
    notify_task = _find_task(_tekton_docs(), "staging-gate-notify")
    step = notify_task["spec"]["steps"][0]
    assert step.get("timeout") == "2m", step.get("timeout")


def test_notify_script_fails_closed_on_an_empty_telegram_credential():
    """P9 review (I4): with the secretKeyRefs now optional: true, the script
    itself is the only thing standing between an un-synced ExternalSecret and
    either an unbound-variable crash or a silent no-op POST with an empty
    token/chat_id. It must check and fail loudly BEFORE ever invoking curl."""
    notify_task = _find_task(_tekton_docs(), "staging-gate-notify")
    script = notify_task["spec"]["steps"][0].get("script", "")
    lines = script.splitlines()
    check_idx = next(
        i for i, line in enumerate(lines)
        if "TELEGRAM_TOKEN" in line and ("-z" in line or ":-" in line)
    )
    curl_idx = next(i for i, line in enumerate(lines) if "curl -fsS" in line)
    assert check_idx < curl_idx, (
        f"the empty-credential check must run before curl is ever invoked: {script}"
    )


README = REPO / "apps/staging-gate/README.md"


def test_readme_documents_the_smoke_rbac_namespace_constraint():
    """P9 review (M3): staging-gate-run-smoke's rbac.yaml is applied with a bare
    `kubectl -n "$ns" apply -f -` -- the manifest must be namespace-free or
    match the contract's smokeNamespace, or the SA the Job runs as resolves
    against the wrong namespace with no apply-time error."""
    text = README.read_text()
    assert "smokeNamespace" in text and "namespace-free" in text.lower(), text


def test_readme_documents_the_smoke_rbac_blast_radius():
    """P9 review (M4): that apply is kind-unfiltered, so write access to the
    app's smoke RBAC manifest is write access to arbitrary objects in the
    staging vCluster's smoke namespace. Document that the pinned ?ref={sha}
    is what bounds it."""
    text = README.read_text()
    assert "kind-unfiltered" in text.lower() or "unfiltered" in text.lower(), text
    assert "?ref={sha}" in text or "ref={sha}" in text


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


VCLUSTER_API_PORT = 8443


def _staging_netpols() -> list[dict]:
    return [d for d in _tekton_docs() if d.get("kind") == "NetworkPolicy"]


def _staging_cp_policies() -> list[dict]:
    """Policies that select the staging vCluster control-plane pod (release=staging)."""
    hits = [
        np for np in _staging_netpols()
        if (np["spec"].get("podSelector") or {}).get("matchLabels", {}).get("release") == "staging"
    ]
    assert hits, "no NetworkPolicy under apps/staging-gate/tekton selects the staging vCluster control-plane pod"
    return hits


def _rules_allowing_staging(np: dict, predicate) -> bool:
    for rule in np["spec"].get("ingress") or []:
        ports = [p.get("port") for p in (rule.get("ports") or [])]
        if VCLUSTER_API_PORT not in ports:
            continue
        for src in rule.get("from") or []:
            if predicate(src):
                return True
    return False


def test_gate_can_reach_the_staging_vcluster_api():
    """P9 review (C1, Critical): the chart's own vc-cp-staging NetworkPolicy
    (policies.networkPolicy.enabled: true, apps/vclusters/template/values.yaml)
    selects the control-plane pod and allows ingress only from same-namespace
    release: staging / vcluster.loft.sh/managed-by: staging and app: loft --
    nothing from tekton-pipelines. Without an additive rule the gate's
    run-smoke/reset/await-sync Tasks (using the vc-staging-gate kubeconfig,
    C2) can never reach the vCluster API."""
    ok = any(
        _rules_allowing_staging(
            np,
            lambda s: (s.get("namespaceSelector") or {})
            .get("matchLabels", {})
            .get("kubernetes.io/metadata.name") == "tekton-pipelines",
        )
        for np in _staging_cp_policies()
    )
    assert ok, f"no ingress rule admits the tekton-pipelines namespace on {VCLUSTER_API_PORT}"


def test_argocd_can_reach_the_staging_vcluster_api():
    """P9 review (C1): the <app>-staging ArgoCD Applications (e.g. runs-fr-staging)
    sync workloads INTO the vCluster -- same requirement as the cnc-staging
    precedent (apps/cnc-staging-host/manifests/networkpolicy-argocd.yaml)."""
    ok = any(
        _rules_allowing_staging(
            np,
            lambda s: (s.get("namespaceSelector") or {})
            .get("matchLabels", {})
            .get("kubernetes.io/metadata.name") == "argocd",
        )
        for np in _staging_cp_policies()
    )
    assert ok, f"no ingress rule admits the argocd namespace on {VCLUSTER_API_PORT}"


def test_staging_vcluster_own_pods_can_reach_the_vcluster_api():
    """P9 review (C1). THE REGRESSION GUARD from the cnc-staging incident
    (apps/cnc-staging-host/manifests/networkpolicy-argocd.yaml HISTORY block):
    an empty podSelector in `from` means every pod in the policy's own
    namespace -- where the vCluster's synced pods (CoreDNS!) run. Without it,
    CoreDNS cannot watch Services/EndpointSlices and every in-vCluster name
    NXDOMAINs. Restated here even though the chart's OWN vc-cp-staging policy
    already grants this, per the cnc incident's lesson: a future edit that
    "simplifies" this file into replacing rather than adding to the chart's
    policy must not silently lose this clause."""
    ok = any(
        _rules_allowing_staging(np, lambda s: s.get("podSelector") == {})
        for np in _staging_cp_policies()
    )
    assert ok, (
        f"no ingress rule admits the staging vCluster's own namespace on "
        f"{VCLUSTER_API_PORT} -- CoreDNS will lose API access"
    )


def test_staging_vcluster_api_netpol_is_ingress_only():
    """These policies must not add an egress policyType -- doing so would flip
    the control-plane pod to default-deny EGRESS too (see the #657 incident
    referenced by the cnc-staging-host HISTORY block)."""
    for np in _staging_cp_policies():
        types = np["spec"].get("policyTypes") or []
        assert "Egress" not in types, (
            f"{np['metadata']['name']} adds an Egress policyType"
        )
