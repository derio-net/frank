"""Tests for ComfyUI VRAM flags + the (pre-existing) Authentik-gated route.

Component 1c/1d of the stoa Frank infra:
- 1c VRAM/offload flags on the Deployment (NEW — TDD red→green here).
- 1d The Traefik route, Authentik proxy provider, and homepage tile for
  comfyui.cluster.derio.net ALREADY EXIST in the repo; these are regression
  guards asserting they stay present + correctly shaped (the live SSO outpost
  assignment is the manual MO-3, not declarative).

Contract source of truth:
docs/superpowers/specs/2026-06-14-stoa-frank-infra-design.md
"""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DEPLOYMENT = REPO / "apps/comfyui/manifests/deployment.yaml"
INGRESSROUTES = REPO / "apps/traefik/manifests/ingressroutes.yaml"
BLUEPRINT = REPO / "apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml"
HOMEPAGE = REPO / "apps/homepage/manifests/files/services.yaml"

HOST = "comfyui.cluster.derio.net"

OFFLOAD_FLAGS = ("--reserve-vram", "--lowvram", "--novram", "--cache-none")


def _comfyui_container():
    for doc in yaml.safe_load_all(DEPLOYMENT.read_text()):
        if doc and doc.get("kind") == "Deployment":
            return doc["spec"]["template"]["spec"]["containers"][0]
    raise AssertionError("no Deployment found")


def test_deployment_has_vram_offload_flags():
    c = _comfyui_container()
    args = c.get("args") or c.get("command") or []
    argstr = " ".join(str(a) for a in args)
    assert any(f in argstr for f in OFFLOAD_FLAGS), (
        f"deployment must set a 16GB offload flag ({OFFLOAD_FLAGS}); got {args!r}"
    )
    # Must keep serving the API on 8188.
    assert "--listen" in argstr and "8188" in argstr, "must keep --listen / --port 8188"


def test_ingressroute_present_and_sso_gated():
    routes = [
        d
        for d in yaml.safe_load_all(INGRESSROUTES.read_text())
        if d and d.get("kind") == "IngressRoute"
    ]
    match = None
    for r in routes:
        for route in r["spec"].get("routes", []):
            if HOST in route.get("match", ""):
                match = route
    assert match is not None, f"no IngressRoute for {HOST}"
    mws = [m["name"] for m in match.get("middlewares", [])]
    assert "authentik-forwardauth" in mws, "route must be SSO-gated"
    svc = match["services"][0]
    assert svc["name"] == "comfyui" and svc["port"] == 8188


def test_authentik_proxy_provider_present():
    text = BLUEPRINT.read_text()
    assert f"https://{HOST}" in text, "Authentik blueprint must carry the comfyui provider"
    assert "forward_single" in text and "invalidation_flow" in text


def test_homepage_tile_present():
    assert f"https://{HOST}" in HOMEPAGE.read_text(), "homepage must carry a comfyui tile"
