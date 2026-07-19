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

These are LOCAL guards (frank does not run scripts/tests/ in CI). They shell out
to `kustomize build` and `helm template --repo https://charts.loft.sh` and are
fail-closed (non-zero return / missing render -> assertion error, never a
false-green). In a runner without helm/kustomize or without egress they go red
on infra, not logic — run them where those tools + network are available.
"""

import base64
import subprocess
from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not skip

REPO = Path(__file__).resolve().parents[2]
HOST_APP = REPO / "apps/cnc-staging-host/manifests"
ROOT_APP = REPO / "apps/root"
CNC_STAGING = REPO / "apps/cnc-staging/manifests"
CNC_PROD = REPO / "apps/cnc-prod/manifests"
VC_TEMPLATE_VALUES = REPO / "apps/vclusters/template/values.yaml"
VC_STAGING_VALUES = REPO / "apps/vclusters/cnc-staging/values.yaml"
VCLUSTER_VERSION = "0.32.1"

NAMES = {"cnc-secrets", "cnc-ghcr-pull", "cnc-runner-auth"}


def _vcluster_config():
    """Render the cnc-staging vCluster and decode its effective config.yaml."""
    out = subprocess.run(
        [
            "helm", "template", "cnc-staging", "vcluster",
            "--repo", "https://charts.loft.sh", "--version", VCLUSTER_VERSION,
            "-f", str(VC_TEMPLATE_VALUES), "-f", str(VC_STAGING_VALUES),
        ],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, f"helm template vcluster failed:\n{out.stderr}"
    for d in yaml.safe_load_all(out.stdout):
        if d and d.get("kind") == "Secret" and "config.yaml" in d.get("data", {}):
            return yaml.safe_load(base64.b64decode(d["data"]["config.yaml"]))
    raise AssertionError("vc-config Secret not rendered")


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


def test_host_declares_ghcr_pull_dockerconfigjson_type():
    # NOTE: this asserts the host-side ExternalSecret's DECLARED template type.
    # Whether the SYNCED copy inside the vCluster retains the type is a RUNTIME
    # fact proven by the manual Phase-3 spike (the primary risk), not here.
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


# --- Phase 2: staging in-vCluster exclusion + vCluster fromHost sync ---------


def test_staging_overlay_creates_no_externalsecrets_at_all():
    """The OSS cnc-staging vCluster has NO ESO controller, so the overlay must
    create ZERO ExternalSecrets — not just the 3 store-backed ones. This also
    catches cnc-source-token (ClusterGenerator-backed), which would otherwise sit
    SecretSyncError forever and drag the app to Degraded. The 3 app secrets arrive
    via fromHost sync; source-token/reseed are excluded until reseed is enabled."""
    es = _externalsecrets(_kustomize(CNC_STAGING))
    assert es == {}, f"staging overlay must create NO ExternalSecrets in-vcluster, found: {sorted(es)}"


def test_staging_overlay_excludes_reseed_job():
    """reseed-job consumes cnc-source-token (unresolvable in-vcluster) and reseed
    is skipped for the first rollout — the Job must not be created."""
    jobs = {
        d["metadata"]["name"]
        for d in _kustomize(CNC_STAGING)
        if d.get("kind") == "Job"
    }
    assert "cnc-staging-reseed" not in jobs, "reseed Job must be excluded until reseed is enabled"


def test_prod_overlay_still_includes_the_three_externalsecrets():
    """Prod resolves them directly in host ns cnc — unaffected by the staging
    change (pins cnc-prod-secret-delivery-unaffected)."""
    es = _externalsecrets(_kustomize(CNC_PROD))
    missing = NAMES - set(es)
    assert not missing, f"prod overlay lost ExternalSecrets: {missing}"


def test_vcluster_fromhost_secret_mappings_present():
    fh = _vcluster_config()["sync"]["fromHost"]["secrets"]
    assert fh["enabled"] is True
    mappings = fh["mappings"]["byName"]
    for n in NAMES:
        assert (
            mappings.get(f"cnc-staging-vcluster/{n}") == f"cnc-staging/{n}"
        ), f"missing/incorrect fromHost mapping for {n}: {mappings}"


def test_vcluster_externalsecrets_integration_stays_disabled():
    """Never re-enable the Pro-only integration that crashed OSS (#651)."""
    cfg = _vcluster_config()
    assert cfg["integrations"]["externalSecrets"]["enabled"] is False
