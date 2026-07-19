"""Guard the CNC staging host-side ExternalSecrets app + fromHost secret sync.

The three CNC staging secrets (cnc-secrets / cnc-ghcr-pull / cnc-runner-auth)
cannot resolve INSIDE the OSS cnc-staging vCluster — there is no ESO controller
or `infisical` ClusterSecretStore in there (and the vCluster External-Secrets
INTEGRATION is a Pro feature that crashes OSS; frank #651 reverted by #652).

Approach A: resolve the ExternalSecrets host-side in ns `cnc-staging-vcluster`
(host ESO works), then sync the resolved Secrets INTO the vCluster ns
`cnc-staging` via OSS-native `sync.fromHost.secrets`.

These guards lock the STATIC invariants product code depends on. The
`dockerconfigjson` TYPE preservation through the runtime host->vCluster sync and
the vCluster RBAC read are RUNTIME facts — proven by the manual Phase-3
on-cluster spike, NOT here (helm/kustomize prove schema only; trusting that over
runtime is exactly the #651 trap).
"""

import subprocess
from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not skip

REPO = Path(__file__).resolve().parents[2]
HOST_APP = REPO / "apps/cnc-staging-host/manifests"
ROOT_APP = REPO / "apps/root"

NAMES = {"cnc-secrets", "cnc-ghcr-pull", "cnc-runner-auth"}


def _helm_template(path: Path):
    out = subprocess.run(
        ["helm", "template", "root", str(path)], capture_output=True, text=True
    )
    assert out.returncode == 0, f"helm template {path} failed:\n{out.stderr}"
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def _application(docs, name):
    for d in docs:
        if d.get("kind") == "Application" and d["metadata"]["name"] == name:
            return d
    raise AssertionError(f"Application {name} not rendered by the root app")


def _kustomize(path: Path):
    out = subprocess.run(
        ["kustomize", "build", str(path)], capture_output=True, text=True
    )
    assert out.returncode == 0, f"kustomize build {path} failed:\n{out.stderr}"
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def _externalsecrets(docs):
    return {
        d["metadata"]["name"]: d for d in docs if d.get("kind") == "ExternalSecret"
    }


def test_host_app_renders_the_three_externalsecrets():
    es = _externalsecrets(_kustomize(HOST_APP))
    assert set(es) == NAMES


def test_host_externalsecrets_live_in_the_vcluster_host_namespace():
    for name, d in _externalsecrets(_kustomize(HOST_APP)).items():
        assert (
            d["metadata"]["namespace"] == "cnc-staging-vcluster"
        ), f"{name} must be in the vcluster host ns cnc-staging-vcluster"


def test_secret_keys_are_preserved():
    es = _externalsecrets(_kustomize(HOST_APP))
    assert es["cnc-secrets"]["spec"]["data"][0]["secretKey"] == "CNCD_SECRETS_MASTER_KEY"
    assert es["cnc-runner-auth"]["spec"]["data"][0]["secretKey"] == "token"
    assert (
        ".dockerconfigjson"
        in es["cnc-ghcr-pull"]["spec"]["target"]["template"]["data"]
    )


def test_ghcr_pull_keeps_dockerconfigjson_type():
    es = _externalsecrets(_kustomize(HOST_APP))
    assert (
        es["cnc-ghcr-pull"]["spec"]["target"]["template"]["type"]
        == "kubernetes.io/dockerconfigjson"
    )


def test_root_renders_host_app_with_host_destination_and_early_wave():
    app = _application(_helm_template(ROOT_APP), "cnc-staging-host")
    dest = app["spec"]["destination"]
    # HOST destination (server), NOT a vCluster (which would use `name:`)
    assert dest.get("server") == "https://kubernetes.default.svc"
    assert dest["namespace"] == "cnc-staging-vcluster"
    assert app["spec"]["source"]["path"] == "apps/cnc-staging-host/manifests"
    # syncs before the in-vCluster staging workloads
    assert app["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "-1"
