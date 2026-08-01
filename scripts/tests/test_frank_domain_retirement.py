"""Guards for the staged retirement of non-Omni frank.derio.net names."""

from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]
OMNI_PATCH = REPO / "patches/phase13-auth/omni-configpatch.yaml"
LEGACY_PATCH = REPO / "patches/phase13-auth/oidc-apiserver.yaml"
AUTHN_CONFIG = REPO / "patches/phase13-auth/authn-config.yaml"

OLD_ISSUER = "https://auth.frank.derio.net/application/o/k8s-agent/"
NEW_ISSUER = "https://auth.cluster.derio.net/application/o/k8s-agent/"
AUTHN_PATH = "/etc/kubernetes/authn-config.yaml"
AUTHN_HOST_PATH = "/var/lib/kubernetes/authn-config.yaml"
CLUSTER_AUTH_HOST = "https://auth.cluster.derio.net"

BLUEPRINT_CALLBACKS = {
    "blueprints-provider-argocd.yaml": {
        "https://argocd.frank.derio.net/auth/callback",
        "https://argocd.frank.derio.net/api/dex/callback",
        "https://argocd.cluster.derio.net/auth/callback",
        "https://argocd.cluster.derio.net/api/dex/callback",
    },
    "blueprints-provider-grafana.yaml": {
        "https://grafana.frank.derio.net/login/generic_oauth",
        "https://grafana.cluster.derio.net/login/generic_oauth",
    },
    "blueprints-provider-infisical.yaml": {
        "https://infisical.frank.derio.net/api/v1/sso/oidc/callback",
        "https://infisical.cluster.derio.net/api/v1/sso/oidc/callback",
    },
}


class _AuthentikLoader(yaml.SafeLoader):
    """Load blueprint object references as ordinary YAML values."""


def _construct_authentik_tag(loader, _tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_AuthentikLoader.add_multi_constructor("!", _construct_authentik_tag)


def _blueprint_entries(filename):
    path = REPO / "apps/authentik-extras/manifests" / filename
    configmap = yaml.safe_load(path.read_text())
    blueprint = yaml.load(next(iter(configmap["data"].values())), Loader=_AuthentikLoader)
    return blueprint["entries"]


def _oauth_provider(entries):
    return next(
        entry
        for entry in entries
        if entry.get("model") == "authentik_providers_oauth2.oauth2provider"
    )


def _env_value(container, name):
    return next(item["value"] for item in container["env"] if item["name"] == name)


def test_omni_patch_delivers_dual_issuer_authentication_config():
    assert not LEGACY_PATCH.exists(), (
        "the raw OIDC patch duplicates the authoritative Omni ConfigPatch"
    )
    assert AUTHN_CONFIG.exists(), "standalone AuthenticationConfiguration is missing"

    wrapper = yaml.safe_load(OMNI_PATCH.read_text())
    assert wrapper["metadata"]["labels"] == {
        "omni.sidero.dev/cluster": "frank",
        "omni.sidero.dev/machine-set": "frank-control-planes",
    }
    machine_config = yaml.safe_load(wrapper["spec"]["data"])
    api_server = machine_config["cluster"]["apiServer"]
    extra_args = api_server["extraArgs"]

    assert extra_args == {"authentication-config": AUTHN_PATH}
    assert not any(key.startswith("oidc-") for key in extra_args)
    assert api_server["extraVolumes"] == [
        {
            "hostPath": AUTHN_HOST_PATH,
            "mountPath": AUTHN_PATH,
            "readonly": True,
        }
    ]

    authn_file = next(
        item
        for item in machine_config["machine"]["files"]
        if item["path"] == AUTHN_HOST_PATH
    )
    assert authn_file["op"] == "create"
    assert str(authn_file["permissions"]) in {"0o644", "420"}

    standalone = yaml.safe_load(AUTHN_CONFIG.read_text())
    assert yaml.safe_load(authn_file["content"]) == standalone
    assert standalone["apiVersion"] == "apiserver.config.k8s.io/v1"
    assert standalone["kind"] == "AuthenticationConfiguration"

    authenticators = standalone["jwt"]
    assert {item["issuer"]["url"] for item in authenticators} == {
        OLD_ISSUER,
        NEW_ISSUER,
    }
    expected_mappings = {
        "username": {"claim": "preferred_username", "prefix": "authentik:"},
        "groups": {"claim": "groups", "prefix": ""},
    }
    for authenticator in authenticators:
        assert authenticator["issuer"]["audiences"] == ["k8s-agent"]
        assert authenticator["claimMappings"] == expected_mappings


def test_oidc_blueprints_accept_old_and_cluster_callbacks():
    for filename, expected_urls in BLUEPRINT_CALLBACKS.items():
        provider = _oauth_provider(_blueprint_entries(filename))
        actual_urls = {item["url"] for item in provider["attrs"]["redirect_uris"]}
        assert expected_urls <= actual_urls, (
            f"{filename}: missing callbacks {sorted(expected_urls - actual_urls)}"
        )


def test_k8s_agent_contract_stays_callback_free_with_eight_hour_tokens():
    provider = _oauth_provider(_blueprint_entries("blueprints-agent-auth.yaml"))
    attrs = provider["attrs"]
    assert attrs["redirect_uris"] == []
    assert attrs["access_token_validity"] == "hours=8"


def test_overlap_consumers_use_cluster_domain():
    authentik = yaml.safe_load((REPO / "apps/authentik/values.yaml").read_text())
    authentik_env = authentik["global"]["env"]
    authentik_host = next(
        item["value"] for item in authentik_env if item["name"] == "AUTHENTIK_HOST"
    )
    assert authentik_host == CLUSTER_AUTH_HOST

    argocd = yaml.safe_load((REPO / "apps/argocd/values.yaml").read_text())
    argocd_config = argocd["configs"]["cm"]
    assert argocd_config["url"] == "https://argocd.cluster.derio.net"
    assert (
        f"issuer: {CLUSTER_AUTH_HOST}/application/o/argocd/"
        in argocd_config["oidc.config"]
    )

    victoria_metrics = yaml.safe_load(
        (REPO / "apps/victoria-metrics/values.yaml").read_text()
    )
    grafana = victoria_metrics["grafana"]["grafana.ini"]
    assert grafana["server"]["root_url"] == "https://grafana.cluster.derio.net"
    oauth = grafana["auth.generic_oauth"]
    assert oauth["auth_url"] == f"{CLUSTER_AUTH_HOST}/application/o/authorize/"
    assert oauth["token_url"] == f"{CLUSTER_AUTH_HOST}/application/o/token/"
    assert oauth["api_url"] == f"{CLUSTER_AUTH_HOST}/application/o/userinfo/"

    n8n = yaml.safe_load((REPO / "apps/n8n-01/manifests/deployment.yaml").read_text())
    n8n_container = n8n["spec"]["template"]["spec"]["containers"][0]
    assert _env_value(n8n_container, "WEBHOOK_URL") == "https://n8n.cluster.derio.net/"

    paperclip = yaml.safe_load(
        (REPO / "apps/paperclip/manifests/configmap.yaml").read_text()
    )
    assert (
        paperclip["data"]["PAPERCLIP_PUBLIC_URL"]
        == "https://paperclip.cluster.derio.net"
    )
    allowed_hosts = paperclip["data"]["PAPERCLIP_ALLOWED_HOSTNAMES"].split(",")
    assert "paperclip.frank.derio.net" in allowed_hosts

    launch_urls = {
        "blueprints-provider-argocd.yaml": "https://argocd.cluster.derio.net",
        "blueprints-provider-grafana.yaml": "https://grafana.cluster.derio.net",
        "blueprints-provider-infisical.yaml": "https://infisical.cluster.derio.net",
    }
    for filename, expected_url in launch_urls.items():
        application = next(
            entry
            for entry in _blueprint_entries(filename)
            if entry.get("model") == "authentik_core.application"
        )
        assert application["attrs"]["meta_launch_url"] == expected_url

    probes = list(
        yaml.safe_load_all(
            (REPO / "apps/blackbox-exporter/manifests/vmprobe.yaml").read_text()
        )
    )
    feature_targets = probes[0]["spec"]["targets"]["staticConfig"]["targets"]
    assert "https://paperclip.cluster.derio.net" in feature_targets
    assert "https://grafana.cluster.derio.net" in feature_targets
    assert not any(".frank.derio.net" in target for target in feature_targets)

    landing = (
        REPO / "clusters/hop/apps/landing/manifests/files/index.html"
    ).read_text()
    for host in ("argocd", "grafana", "longhorn"):
        assert f'https://{host}.cluster.derio.net' in landing
        assert f'https://{host}.frank.derio.net' not in landing

    access_reference = (REPO / "references/access.md").read_text()
    assert "https://infisical.cluster.derio.net" in access_reference
    assert "https://infisical.frank.derio.net" not in access_reference


def test_cluster_proxy_blueprint_owns_cluster_hosts_during_overlap():
    cluster_entries = _blueprint_entries("blueprints-cluster-proxy-providers.yaml")
    legacy_entries = _blueprint_entries("blueprints-proxy-providers.yaml")

    cluster_hosts = {
        entry["attrs"]["external_host"]
        for entry in cluster_entries
        if entry.get("model") == "authentik_providers_proxy.proxyprovider"
    }
    legacy_hosts = {
        entry["attrs"]["external_host"]
        for entry in legacy_entries
        if entry.get("model") == "authentik_providers_proxy.proxyprovider"
    }

    assert cluster_hosts
    assert all(host.endswith(".cluster.derio.net") for host in cluster_hosts)
    assert legacy_hosts == {
        "https://longhorn.frank.derio.net",
        "https://hubble.frank.derio.net",
        "https://sympozium.frank.derio.net",
        "https://n8n-01.frank.derio.net",
    }
    assert cluster_hosts.isdisjoint(legacy_hosts)


def test_embedded_outpost_uses_cluster_host_without_managing_provider_assignments():
    entries = _blueprint_entries("blueprints-cluster-proxy-providers.yaml")
    outpost = next(
        entry
        for entry in entries
        if entry.get("model") == "authentik_outposts.outpost"
    )

    assert outpost["state"] == "present"
    assert outpost["identifiers"] == {"name": "authentik Embedded Outpost"}
    assert outpost["attrs"]["config"] == {
        "authentik_host": CLUSTER_AUTH_HOST,
        "authentik_host_browser": CLUSTER_AUTH_HOST,
    }
    assert "providers" not in outpost["attrs"]
