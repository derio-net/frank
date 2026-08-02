"""Guards for the staged retirement of non-Omni frank.derio.net names.

Phase 5 flips these from the dual-issuer OVERLAP contract to the FINAL state:
exactly one JWT issuer, no legacy callbacks, no legacy compatibility routes,
and legacy proxy entries surviving only as URL-free `state: absent` tombstones.

Two references are deliberately retained and asserted positively, because a
blanket "no frank.derio.net" rule would delete them:
  * omni.frank.derio.net — Omni keeps its own name
  * the Headscale frank.derio.net split-DNS SUFFIX (a bare zone key)
"""

import re
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]
OMNI_PATCH = REPO / "patches/phase13-auth/omni-configpatch.yaml"
LEGACY_PATCH = REPO / "patches/phase13-auth/oidc-apiserver.yaml"
AUTHN_CONFIG = REPO / "patches/phase13-auth/authn-config.yaml"
INGRESSROUTES = REPO / "apps/traefik/manifests/ingressroutes.yaml"
HEADSCALE_CONFIG = REPO / "clusters/hop/apps/headscale/manifests/configmap.yaml"

OLD_ISSUER = "https://auth.frank.derio.net/application/o/k8s-agent/"
NEW_ISSUER = "https://auth.cluster.derio.net/application/o/k8s-agent/"
AUTHN_PATH = "/etc/kubernetes/authn-config.yaml"
AUTHN_HOST_PATH = "/var/lib/kubernetes/authn-config.yaml"
CLUSTER_AUTH_HOST = "https://auth.cluster.derio.net"

# Any <label>.frank.derio.net name. The bare zone (Headscale's split-DNS
# suffix) deliberately does NOT match — it has no leading label.
FRANK_HOST = re.compile(r"[a-z0-9-]+\.frank\.derio\.net")
ALLOWED_FRANK_HOSTS = {"omni.frank.derio.net"}
SCANNED_DIRS = ("apps", "patches", "clusters", "references", "secrets")

# Final state: cluster callbacks only.
BLUEPRINT_CALLBACKS = {
    "blueprints-provider-argocd.yaml": {
        "https://argocd.cluster.derio.net/auth/callback",
        "https://argocd.cluster.derio.net/api/dex/callback",
    },
    "blueprints-provider-grafana.yaml": {
        "https://grafana.cluster.derio.net/login/generic_oauth",
    },
    "blueprints-provider-infisical.yaml": {
        "https://infisical.cluster.derio.net/api/v1/sso/oidc/callback",
    },
}

# Legacy forward-auth entries that must survive only as tombstones, so that
# removing the ConfigMap can never leave live Authentik objects behind.
LEGACY_PROVIDER_NAMES = {"Longhorn UI", "Hubble UI", "Sympozium", "n8n-01"}
LEGACY_APPLICATION_SLUGS = {"longhorn", "hubble", "sympozium", "n8n-01"}


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


def _offending_frank_hosts(text):
    """Every <label>.frank.derio.net occurrence that is not explicitly allowed."""
    return {m for m in FRANK_HOST.findall(text) if m not in ALLOWED_FRANK_HOSTS}


def _safe_read(path):
    """Read a file as text, treating binaries and unreadable paths as empty."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def test_omni_patch_delivers_cluster_only_authentication_config():
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
    # The embedded copy and the standalone file must stay byte-identical in
    # meaning, so reducing one without the other is a test failure, not drift.
    assert yaml.safe_load(authn_file["content"]) == standalone
    assert standalone["apiVersion"] == "apiserver.config.k8s.io/v1"
    assert standalone["kind"] == "AuthenticationConfiguration"

    authenticators = standalone["jwt"]
    assert {item["issuer"]["url"] for item in authenticators} == {NEW_ISSUER}, (
        "exactly one JWT issuer must remain after the overlap closes"
    )
    assert OLD_ISSUER not in {item["issuer"]["url"] for item in authenticators}

    expected_mappings = {
        "username": {"claim": "preferred_username", "prefix": "authentik:"},
        "groups": {"claim": "groups", "prefix": ""},
    }
    for authenticator in authenticators:
        assert authenticator["issuer"]["audiences"] == ["k8s-agent"]
        assert authenticator["claimMappings"] == expected_mappings


def test_oidc_blueprints_expose_only_cluster_callbacks():
    for filename, expected_urls in BLUEPRINT_CALLBACKS.items():
        provider = _oauth_provider(_blueprint_entries(filename))
        actual_urls = {item["url"] for item in provider["attrs"]["redirect_uris"]}
        assert actual_urls == expected_urls, (
            f"{filename}: expected exactly {sorted(expected_urls)}, "
            f"got {sorted(actual_urls)}"
        )


def test_k8s_agent_contract_stays_callback_free_with_eight_hour_tokens():
    provider = _oauth_provider(_blueprint_entries("blueprints-agent-auth.yaml"))
    attrs = provider["attrs"]
    assert attrs["redirect_uris"] == []
    assert attrs["access_token_validity"] == "hours=8"


def test_consumers_use_cluster_domain():
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
    assert "paperclip.frank.derio.net" not in allowed_hosts, (
        "the legacy Paperclip hostname must be dropped once the overlap closes"
    )
    assert "paperclip.cluster.derio.net" in allowed_hosts

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


def test_legacy_proxy_entries_are_url_free_absent_tombstones():
    """Deletion must be declarative.

    Dropping the ConfigMap outright would orphan live Authentik objects, so
    every legacy provider and application stays listed as `state: absent`
    with no external or launch URL to reconcile.
    """
    entries = _blueprint_entries("blueprints-proxy-providers.yaml")

    providers = [
        e for e in entries
        if e.get("model") == "authentik_providers_proxy.proxyprovider"
    ]
    applications = [
        e for e in entries if e.get("model") == "authentik_core.application"
    ]

    assert {p["identifiers"]["name"] for p in providers} == LEGACY_PROVIDER_NAMES
    assert {a["identifiers"]["slug"] for a in applications} == LEGACY_APPLICATION_SLUGS

    for entry in providers + applications:
        label = entry["identifiers"]
        assert entry["state"] == "absent", f"{label} must be a tombstone"
        attrs = entry.get("attrs", {})
        assert "external_host" not in attrs, f"{label} still carries external_host"
        assert "meta_launch_url" not in attrs, f"{label} still carries meta_launch_url"

    # Applications hold a FK to their provider, so they must be deleted first.
    last_application = max(i for i, e in enumerate(entries) if e in applications)
    first_provider = min(i for i, e in enumerate(entries) if e in providers)
    assert last_application < first_provider, (
        "application tombstones must precede provider tombstones so Authentik "
        "removes the dependent objects first"
    )


def test_no_legacy_frank_ingressroutes_or_certificates():
    """Structural check: no route match or TLS domain names a legacy host."""
    docs = [d for d in yaml.safe_load_all(INGRESSROUTES.read_text()) if d]
    assert docs, "ingressroutes.yaml parsed to nothing"

    for doc in docs:
        name = doc.get("metadata", {}).get("name", "<unnamed>")
        rendered = yaml.safe_dump(doc)
        offenders = _offending_frank_hosts(rendered)
        assert not offenders, (
            f"{doc.get('kind')}/{name} still references {sorted(offenders)}"
        )


def test_repo_has_no_non_omni_frank_references():
    """Raw-text sweep — catches comments and prose the YAML parse would drop."""
    offenders = {}
    for directory in SCANNED_DIRS:
        root = REPO / directory
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            found = _offending_frank_hosts(text)
            if found:
                offenders[str(path.relative_to(REPO))] = sorted(found)

    assert not offenders, (
        "non-Omni frank.derio.net references remain:\n"
        + "\n".join(f"  {p}: {hosts}" for p, hosts in sorted(offenders.items()))
    )


def test_omni_and_headscale_suffix_are_preserved():
    """The two deliberate survivors — a blanket sweep must not eat them."""
    omni_hits = sorted(
        str(path.relative_to(REPO))
        for directory in SCANNED_DIRS
        if (REPO / directory).exists()
        for path in (REPO / directory).rglob("*")
        if path.is_file() and "omni.frank.derio.net" in _safe_read(path)
    )
    assert omni_hits, "omni.frank.derio.net must survive the retirement"

    assert re.search(r"^\s+frank\.derio\.net:", HEADSCALE_CONFIG.read_text(), re.M), (
        "the Headscale frank.derio.net split-DNS suffix must be retained"
    )


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
