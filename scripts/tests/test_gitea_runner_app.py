"""Guard: the Gitea Actions runner app (apps/gitea-runner) is shaped safely.

The act_runner + DinD pair is the only privileged workload we ship for CI —
these assertions pin the containment decisions: dedicated privileged-labeled
namespace (Gitea itself stays unprivileged), pc-1 pinning, Recreate strategy
(RWO PVC gotcha), pinned images, memory limits on both containers, and the
ESO-delivered registration token.

Plan: docs/superpowers/plans/2026-07-19-cicd-stoa-mirror-gitea-actions
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / "apps/gitea-runner/manifests"


def _runner_config():
    """The act_runner config, now a configMapGenerator SOURCE file.

    It is no longer a ConfigMap manifest — see kustomization.yaml and
    test_config_edit_rolls_the_pod for why that move is load-bearing.
    """
    return yaml.safe_load((RUNNER_DIR / "files/config.yaml").read_text())


def _load(name):
    docs = [
        d
        for d in yaml.safe_load_all((RUNNER_DIR / name).read_text())
        if d is not None
    ]
    assert docs, f"{name} is empty"
    return docs


def test_gitea_actions_enabled():
    values = yaml.safe_load(
        (REPO_ROOT / "apps/gitea/values.yaml").read_text()
    )
    assert values["gitea"]["config"]["actions"]["ENABLED"] is True


def test_namespace_is_privileged_and_dedicated():
    ns = _load("namespace.yaml")[0]
    assert ns["kind"] == "Namespace"
    assert ns["metadata"]["name"] == "gitea-runner"
    labels = ns["metadata"]["labels"]
    assert labels["pod-security.kubernetes.io/enforce"] == "privileged"


def test_deployment_shape():
    deploys = [d for d in _load("deployment.yaml") if d["kind"] == "Deployment"]
    assert len(deploys) == 1
    spec = deploys[0]["spec"]

    # RWO PVC + RollingUpdate deadlocks (frank gotcha) — must be Recreate
    assert spec["strategy"]["type"] == "Recreate"
    assert spec["replicas"] == 1

    pod = spec["template"]["spec"]
    assert pod["nodeSelector"]["kubernetes.io/hostname"] == "pc-1"
    # privileged DinD + arbitrary workflow code: the SA token must not be
    # reachable (a job can bind-mount host paths through the docker daemon)
    assert pod["automountServiceAccountToken"] is False

    containers = {c["name"]: c for c in pod["containers"]}
    assert set(containers) == {"runner", "dind"}

    runner, dind = containers["runner"], containers["dind"]

    # pinned images, never :latest
    for c in (runner, dind):
        image = c["image"]
        assert ":" in image and not image.endswith(":latest"), image
        assert c["resources"]["limits"]["memory"], f"{c['name']} needs a memory limit"

    assert "act_runner" in runner["image"]
    assert dind["image"].startswith("docker:") and "dind" in dind["image"]
    assert dind["securityContext"]["privileged"] is True

    env = {e["name"]: e for e in runner["env"]}
    assert (
        env["GITEA_INSTANCE_URL"]["value"]
        == "http://gitea-http.gitea.svc.cluster.local:3000"
    )
    assert (
        env["GITEA_RUNNER_REGISTRATION_TOKEN"]["valueFrom"]["secretKeyRef"]["name"]
        == "gitea-runner-token"
    )
    assert env["DOCKER_HOST"]["value"] == "tcp://localhost:2375"

    dind_env = {e["name"]: e.get("value") for e in dind["env"]}
    # empty TLS certdir = plain-TCP daemon on localhost; without this dind
    # silently generates certs and listens on 2376, and the runner hangs
    assert dind_env["DOCKER_TLS_CERTDIR"] == ""


def test_runner_config():
    config = _runner_config()
    assert config["runner"]["capacity"] == 2
    labels = config["runner"]["labels"]
    assert any(
        label.startswith("ubuntu-latest:docker://") for label in labels
    ), labels
    assert config["container"]["docker_host"] == "tcp://localhost:2375"


def test_job_containers_can_reach_the_docker_daemon():
    """Job containers must see the daemon AND published ports on localhost.

    Workflows written for GitHub-hosted runners assume the job and the Docker
    daemon share one host: `docker build` finds /var/run/docker.sock, and a
    `docker run -p 8088:80` is then reachable at http://localhost:8088.

    Here the job is a CONTAINER, a sibling of the DinD daemon, so neither
    holds. act_runner only mounts the docker host into job containers when it
    is a unix socket (its `docker_host` doc: "-" means "won't be mounted to
    the job containers"), and ours is TCP — so a job gets no DOCKER_HOST at
    all and the CLI falls back to the missing socket:

        ERROR: failed to connect to the docker API at unix:///var/run/docker.sock
               dial unix /var/run/docker.sock: connect: no such file or directory

    Measured against the live daemon 2026-07-22, container on a bridge
    network vs one on the host network:

        bridge  daemon localhost:2375 FAIL   published port FAIL
        host    daemon localhost:2375 OK     published port OK

    So `network: host` is load-bearing for BOTH halves, and DOCKER_HOST must
    be injected explicitly because act_runner will not do it for a TCP host.
    """
    container = _runner_config()["container"]

    assert container.get("network") == "host", (
        "job containers on a bridge network can reach neither the DinD "
        "daemon nor any port published by the containers they start"
    )

    options = container.get("options") or ""
    assert "DOCKER_HOST" in options and "2375" in options, (
        "act_runner does not propagate a TCP docker_host into job containers "
        f"— inject it via container.options: {options!r}"
    )


def test_registration_token_externalsecret():
    es = _load("externalsecret-runner-token.yaml")[0]
    assert es["kind"] == "ExternalSecret"
    assert es["metadata"]["namespace"] == "gitea-runner"

    # same store as the existing gitea secrets — read it, don't hardcode
    gitea_es = yaml.safe_load(
        (REPO_ROOT / "apps/gitea/manifests/externalsecret-gitea.yaml").read_text()
    )
    assert es["spec"]["secretStoreRef"] == gitea_es["spec"]["secretStoreRef"]

    assert es["spec"]["target"]["name"] == "gitea-runner-token"
    remote_keys = {d["remoteRef"]["key"] for d in es["spec"]["data"]}
    assert remote_keys == {"STOA_GITEA_RUNNER_TOKEN"}


def test_cache_pvc():
    pvc = _load("pvc.yaml")[0]
    assert pvc["kind"] == "PersistentVolumeClaim"
    assert pvc["spec"]["storageClassName"] == "longhorn-cicd"
    assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]


def test_root_application():
    app = yaml.safe_load(
        (REPO_ROOT / "apps/root/templates/gitea-runner.yaml")
        .read_text()
        .replace("{{ .Values.repoURL }}", "REPO")
        .replace("{{ .Values.targetRevision }}", "REV")
        .replace("{{ .Values.destination.server }}", "SERVER")
    )
    assert app["spec"]["source"]["path"] == "apps/gitea-runner/manifests"
    assert app["spec"]["destination"]["namespace"] == "gitea-runner"
    opts = app["spec"]["syncPolicy"]["syncOptions"]
    assert "ServerSideApply=true" in opts
    # namespace ships as a manifest (it carries the PSS labels)
    assert "CreateNamespace=false" in opts


def test_config_edit_rolls_the_pod():
    """A config edit must change the pod spec, or the runner never reloads it.

    act_runner reads /config/config.yaml exactly ONCE, at boot. Shipped as a
    plain ConfigMap the name never changes, so ArgoCD applies new content to a
    ConfigMap the running pod has already read: the app reports Synced, the
    live ConfigMap holds the new config, and the runner keeps serving the old
    one indefinitely. That is precisely what happened deploying frank#674 on
    2026-07-23 — the fix reached the cluster but not the runner until a manual
    `kubectl rollout restart`. Same shape as the gitea `gitea-inline-config`
    gotcha.

    kustomize's configMapGenerator hash-suffixes the name and rewrites the
    Deployment's volume reference, so an edit changes the POD SPEC and ArgoCD
    rolls it. This pins the three parts that make that work.
    """
    kustomization = yaml.safe_load((RUNNER_DIR / "kustomization.yaml").read_text())

    gens = kustomization.get("configMapGenerator") or []
    assert any(g.get("name") == "act-runner-config" for g in gens), (
        "act-runner-config must be GENERATED (hash-suffixed), not a literal "
        f"ConfigMap manifest, or config edits never reach the runner: {gens}"
    )

    # the literal manifest must be gone, or both would be applied
    assert not (RUNNER_DIR / "config.yaml").exists(), (
        "a literal config.yaml ConfigMap manifest still exists alongside the "
        "generator — the unhashed one would win and never roll the pod"
    )

    # generator source must be in resources' sibling dir and non-empty
    assert (RUNNER_DIR / "files/config.yaml").read_text().strip()

    # the Deployment must reference the generator's name so kustomize rewrites it
    deploy = [d for d in _load("deployment.yaml") if d["kind"] == "Deployment"][0]
    vols = deploy["spec"]["template"]["spec"]["volumes"]
    cm_vols = [v["configMap"]["name"] for v in vols if "configMap" in v]
    assert "act-runner-config" in cm_vols, cm_vols


def test_prune_is_enabled_but_stateful_resources_opt_out():
    """prune: true is required by the generator — and must not reach state.

    Hash-suffixed ConfigMaps orphan the previous one on every edit, so without
    prune the app sits OutOfSync forever. But unlike homepage (the repo's other
    prune: true app, which holds only a Deployment/Service/ConfigMaps) this app
    owns the two things the repo-wide `prune: false` rule exists to protect:
    the PVC holding the runner's registration identity (/data/.runner), and the
    registration-token ExternalSecret. Both opt out individually.
    """
    app = yaml.safe_load(
        (REPO_ROOT / "apps/root/templates/gitea-runner.yaml")
        .read_text()
        .replace("{{ .Values.repoURL }}", "REPO")
        .replace("{{ .Values.targetRevision }}", "REV")
        .replace("{{ .Values.destination.server }}", "SERVER")
    )
    automated = app["spec"]["syncPolicy"]["automated"]
    assert automated.get("prune") is True, (
        "configMapGenerator orphans a ConfigMap on every config edit; without "
        f"prune the app sits OutOfSync forever: {automated}"
    )

    for fname, kind in (
        ("pvc.yaml", "PersistentVolumeClaim"),
        ("externalsecret-runner-token.yaml", "ExternalSecret"),
    ):
        doc = [d for d in _load(fname) if d["kind"] == kind][0]
        opts = (doc["metadata"].get("annotations") or {}).get(
            "argocd.argoproj.io/sync-options", ""
        )
        assert "Prune=false" in opts, (
            f"{kind} is prunable while the app runs prune: true — this is the "
            "runner's persistent identity / credential"
        )
