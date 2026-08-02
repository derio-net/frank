"""Guards for the Headscale MagicDNS record that lets mesh peers reach LiteLLM.

The kid laptops can already *route* to Frank's LAN (argonath subnet routers) and
LiteLLM's own Bearer auth already answers them — the only missing piece is a
mesh-resolvable name. Phase 1 adds `litellm-lb.cluster.derio.net` pointing
straight at LiteLLM's Cilium LoadBalancer (192.168.55.206:4000), bypassing
Traefik and therefore the Authentik forward-auth outpost. Phase 2 adds the
canonical HTTPS path: `litellm-api.cluster.derio.net` → 192.168.55.220 (Traefik)
plus an IngressRoute for that host that deliberately does NOT carry
`authentik-forwardauth`.

Contract source of truth:
docs/superpowers/specs/2026-08-02--edge--litellm-mesh-dns-design.md

Note the file shape: `data["config.yaml"]` is a YAML *document embedded as a
string*, so every assertion here loads the ConfigMap and then loads that string
again. A clumsy hand-edit that drops a sibling record or re-nests the list would
still be valid YAML — hence the explicit shape assertions.

`data["acl.yaml"]` is deliberately never parsed here: despite the key name it is
Headscale *policy* in HuJSON (JSON with `//` comments), which loads with neither
`yaml.safe_load` nor `json.loads` on unmodified HEAD. A stock-loader guard on it
would report a pre-existing condition as though this edit had broken the file.
"""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIGMAP = REPO / "clusters/hop/apps/headscale/manifests/configmap.yaml"
INGRESSROUTES = REPO / "apps/traefik/manifests/ingressroutes.yaml"

LITELLM_RECORD = {
    "name": "litellm-lb.cluster.derio.net",
    "type": "A",
    "value": "192.168.55.206",
}
LITELLM_API_RECORD = {
    "name": "litellm-api.cluster.derio.net",
    "type": "A",
    "value": "192.168.55.220",
}
GITEA_SSH_RECORD = {
    "name": "gitea-ssh.cluster.derio.net",
    "type": "A",
    "value": "192.168.55.209",
}

API_HOST = "litellm-api.cluster.derio.net"
PUBLIC_HOST = "litellm.cluster.derio.net"
FORWARD_AUTH = "authentik-forwardauth"


def _headscale_config():
    cm = yaml.safe_load(CONFIGMAP.read_text())
    assert cm["kind"] == "ConfigMap", f"expected a ConfigMap, got {cm.get('kind')!r}"
    return yaml.safe_load(cm["data"]["config.yaml"])


def _extra_records():
    records = _headscale_config()["dns"]["extra_records"]
    assert isinstance(records, list), (
        "dns.extra_records must stay a LIST of mappings — an indentation slip in "
        f"the embedded document turned it into {type(records).__name__}"
    )
    for rec in records:
        assert isinstance(rec, dict), f"extra_records entry must be a mapping; got {rec!r}"
    return records


def test_litellm_lb_record_present():
    records = _extra_records()
    assert LITELLM_RECORD in records, (
        "dns.extra_records must carry the LiteLLM LoadBalancer record "
        f"{LITELLM_RECORD} — without it a mesh client has no name to resolve for "
        f"LiteLLM. Present records: {records!r}"
    )


def test_gitea_ssh_record_still_present():
    records = _extra_records()
    assert GITEA_SSH_RECORD in records, (
        "the pre-existing gitea-ssh record must survive any edit to this "
        f"hand-maintained embedded YAML — {GITEA_SSH_RECORD} is what makes "
        "git-over-ssh work for every mesh peer, and nothing else reports its loss. "
        f"Present records: {records!r}"
    )


def test_litellm_api_record_present():
    records = _extra_records()
    assert LITELLM_API_RECORD in records, (
        "dns.extra_records must carry the Traefik-fronted LiteLLM record "
        f"{LITELLM_API_RECORD} — this is the canonical HTTPS endpoint the kid "
        "laptops settle on, and without it the name resolves nowhere on the "
        f"mesh. Present records: {records!r}"
    )


def test_magic_dns_enabled():
    dns = _headscale_config()["dns"]
    assert dns.get("magic_dns") is True, (
        "dns.magic_dns must be true — extra_records are inert without MagicDNS, "
        f"so the record would resolve nowhere. Got {dns.get('magic_dns')!r}"
    )


# --- Traefik IngressRoute: the SSO invariant, asserted in both directions ---


def _ingressroutes():
    docs = [
        d
        for d in yaml.safe_load_all(INGRESSROUTES.read_text())
        if d and d.get("kind") == "IngressRoute"
    ]
    assert docs, f"no IngressRoute documents found in {INGRESSROUTES}"
    return docs


def _route_for_host(host):
    """Return the (IngressRoute, route) pair whose match rule names `host`."""
    needle = f"Host(`{host}`)"
    hits = [
        (doc, route)
        for doc in _ingressroutes()
        for route in doc["spec"].get("routes", [])
        if needle in route.get("match", "")
    ]
    assert len(hits) == 1, (
        f"expected exactly one route matching {needle}; found {len(hits)}. "
        "apps/traefik/manifests/ has no kustomization.yaml, so ArgoCD applies "
        "this file in directory mode — two routes for one host is a live "
        "conflict, not a build error."
    )
    return hits[0]


def _middlewares(route):
    return [m["name"] for m in route.get("middlewares", [])]


def test_litellm_api_route_has_no_forward_auth():
    _, route = _route_for_host(API_HOST)
    names = _middlewares(route)
    assert FORWARD_AUTH not in names, (
        f"the {API_HOST} route must NOT carry {FORWARD_AUTH!r}. LiteLLM "
        "authenticates by Bearer virtual key; the Authentik outpost intercepts "
        "before LiteLLM ever sees the header, so every API-key client would get "
        "a 302 to auth.cluster.derio.net instead of an API response. That is "
        "precisely the bug this plan exists to route around — reintroducing it "
        f"is silent from the cluster's side. Middlewares: {names!r}"
    )


def test_litellm_api_route_keeps_network_middlewares():
    _, route = _route_for_host(API_HOST)
    names = _middlewares(route)
    for required in ("ip-allowlist", "security-headers"):
        assert required in names, (
            f"the {API_HOST} route must keep {required!r} — dropping forward-auth "
            "is deliberate, dropping the network/header guards with it is not. "
            f"Middlewares: {names!r}"
        )


def test_litellm_public_route_still_has_forward_auth():
    _, route = _route_for_host(PUBLIC_HOST)
    names = _middlewares(route)
    assert FORWARD_AUTH in names, (
        f"the PUBLIC {PUBLIC_HOST} route must STILL carry {FORWARD_AUTH!r}. It "
        "fronts the LiteLLM admin UI and SSO is its only gate; someone tidying "
        "the two near-identical litellm routes could strip it, and nothing else "
        f"would report the loss. Middlewares: {names!r}"
    )


def test_litellm_api_route_targets_litellm_service():
    _, route = _route_for_host(API_HOST)
    services = route.get("services", [])
    assert len(services) == 1, f"expected one backend service; got {services!r}"
    svc = services[0]
    assert (svc.get("name"), svc.get("namespace"), svc.get("port")) == (
        "litellm",
        "litellm",
        4000,
    ), (
        f"the {API_HOST} route must target service litellm/litellm:4000 "
        f"(cross-namespace from traefik-system, as the public route already "
        f"does). Got {svc!r}"
    )


def test_litellm_api_route_reuses_wildcard_certificate():
    doc, _ = _route_for_host(API_HOST)
    tls = doc["spec"].get("tls", {})
    assert tls.get("certResolver") == "cloudflare", (
        f"the {API_HOST} route must use the cloudflare cert resolver; got "
        f"{tls.get('certResolver')!r}"
    )
    domains = tls.get("domains", [])
    assert domains and domains[0].get("main") == "*.cluster.derio.net", (
        "tls.domains[0].main must be '*.cluster.derio.net' so Traefik reuses the "
        "already-issued wildcard rather than placing a fresh ACME order for a "
        f"per-host cert. Got {domains!r}"
    )


def test_litellm_api_route_is_in_traefik_system():
    doc, _ = _route_for_host(API_HOST)
    meta = doc["metadata"]
    assert meta.get("namespace") == "traefik-system", (
        "the IngressRoute must live in traefik-system alongside its siblings; "
        f"got namespace {meta.get('namespace')!r}"
    )


def test_litellm_api_route_serves_on_websecure():
    """The tls block is inert unless the router listens on the TLS entrypoint.

    Without this, setting `entryPoints: [web]` — a plausible copy-paste from a
    non-TLS route — passes every other test in this module: the tls block still
    reads as correct, the middlewares are right, the backend is right. Live,
    Traefik has no :443 router for the host, so an https:// request falls
    through to the default certificate and 404s. Green CI, dead endpoint.
    """
    doc, route = _route_for_host(API_HOST)
    entrypoints = doc["spec"].get("entryPoints", [])
    assert entrypoints == ["websecure"], (
        f"the {API_HOST} route must serve on the websecure (:443) entrypoint, "
        "like every sibling in this file. A tls block on a non-TLS entrypoint "
        f"is silently inert. Got entryPoints={entrypoints!r}"
    )
    assert route.get("kind") == "Rule", (
        f"route kind must be 'Rule'; got {route.get('kind')!r}"
    )


def test_extra_record_names_are_unique():
    """Two records for one name is a coin-flip, not a configuration.

    `extra_records` is a list, so nothing stops a rebase or a careless edit from
    landing the same name twice with different values. Headscale would serve one
    of them; which one is not a property anybody should be relying on.
    """
    names = [r["name"] for r in _extra_records()]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, (
        f"duplicate name(s) in dns.extra_records: {dupes}. Each name must map "
        "to exactly one address."
    )


def test_ingressroute_names_are_unique():
    # Keyed on (namespace, name): that is the actual uniqueness scope of a
    # namespaced Kubernetes object, so a same-named route legitimately added in
    # another namespace does not read as a collision.
    keys = [
        (d["metadata"].get("namespace"), d["metadata"]["name"])
        for d in _ingressroutes()
    ]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, (
        f"duplicate IngressRoute (namespace, name) in {INGRESSROUTES.name}: "
        f"{dupes}. This directory has no kustomization.yaml, so ArgoCD applies "
        "every document as-is — a duplicate is a live resource collision (the "
        "second apply overwrites the first), not a build-time error."
    )
