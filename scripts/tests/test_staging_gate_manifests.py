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
    smoke_step = run_smoke["spec"]["steps"][0]
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
