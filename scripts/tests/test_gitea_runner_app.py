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
    cms = [d for d in _load("config.yaml") if d["kind"] == "ConfigMap"]
    config = yaml.safe_load(cms[0]["data"]["config.yaml"])
    assert config["runner"]["capacity"] == 2
    labels = config["runner"]["labels"]
    assert any(
        label.startswith("ubuntu-latest:docker://") for label in labels
    ), labels
    assert config["container"]["docker_host"] == "tcp://localhost:2375"


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
