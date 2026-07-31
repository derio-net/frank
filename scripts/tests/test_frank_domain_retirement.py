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


def test_omni_patch_delivers_dual_issuer_authentication_config():
    assert not LEGACY_PATCH.exists(), (
        "the raw OIDC patch duplicates the authoritative Omni ConfigPatch"
    )
    assert AUTHN_CONFIG.exists(), "standalone AuthenticationConfiguration is missing"

    wrapper = yaml.safe_load(OMNI_PATCH.read_text())
    machine_config = yaml.safe_load(wrapper["spec"]["data"])
    api_server = machine_config["cluster"]["apiServer"]
    extra_args = api_server["extraArgs"]

    assert extra_args == {"authentication-config": AUTHN_PATH}
    assert not any(key.startswith("oidc-") for key in extra_args)
    assert api_server["extraVolumes"] == [
        {"hostPath": AUTHN_PATH, "mountPath": AUTHN_PATH, "readonly": True}
    ]

    authn_file = next(
        item
        for item in machine_config["machine"]["files"]
        if item["path"] == AUTHN_PATH
    )
    assert authn_file["op"] == "create"
    assert str(authn_file["permissions"]) in {"0o600", "384"}

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
