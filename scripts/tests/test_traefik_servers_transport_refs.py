"""Every IngressRoute `serversTransport` reference must resolve the way Traefik resolves it.

Traefik looks a bare `serversTransport: <name>` up in the BACKEND SERVICE's
namespace. A ServersTransport in another namespace must be written
`<namespace>-<name>@kubernetescrd`, and only works with the kubernetesCRD
provider's `allowCrossNamespace: true`. Otherwise Traefik DROPS THE WHOLE ROUTER
and the host answers "404 page not found", while ArgoCD reports Synced/Healthy.

Bit the speech route (#1006, 2026-11-22): `serversTransport: speech-long-requests`
for a Service in `speech`, with the ServersTransport in `traefik-system`.
Traefik logged `servers transport not found speech-speech-long-requests@kubernetescrd`.
"""
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
MANIFESTS = REPO / "apps/traefik/manifests"
VALUES = REPO / "apps/traefik/values.yaml"
CROSS = re.compile(r"^(?P<ns>[a-z0-9-]+?)-(?P<name>[a-z0-9.-]+)@kubernetescrd$")


def _docs():
    for f in sorted(MANIFESTS.glob("*.yaml")):
        for d in yaml.safe_load_all(f.read_text()):
            if d:
                yield f.name, d


def _transports():
    return {(d["metadata"].get("namespace", "default"), d["metadata"]["name"])
            for _, d in _docs() if d.get("kind") == "ServersTransport"}


def _cross_namespace_allowed():
    v = yaml.safe_load(VALUES.read_text())
    return bool(v.get("providers", {}).get("kubernetesCRD", {}).get("allowCrossNamespace"))


def _refs():
    for fname, d in _docs():
        if d.get("kind") != "IngressRoute":
            continue
        route_ns = d["metadata"].get("namespace", "default")
        for r in d["spec"].get("routes", []):
            for s in r.get("services", []):
                if "serversTransport" in s:
                    yield fname, d["metadata"]["name"], s.get("namespace", route_ns), s["serversTransport"]


def test_there_is_at_least_one_reference_to_check():
    assert list(_refs()), "no serversTransport references found; the guard would be vacuous"


def test_every_servers_transport_reference_resolves():
    transports = _transports()
    bad = []
    for fname, route, svc_ns, ref in _refs():
        if ref.endswith("@kubernetescrd"):
            names = {f"{ns}-{n}@kubernetescrd": (ns, n) for ns, n in transports}
            if ref not in names:
                bad.append(f"{fname}:{route}: {ref} names no ServersTransport")
            elif names[ref][0] != svc_ns and not _cross_namespace_allowed():
                bad.append(f"{fname}:{route}: {ref} is cross-namespace but allowCrossNamespace is off")
        elif (svc_ns, ref) not in transports:
            where = sorted(ns for ns, n in transports if n == ref)
            hint = f" (it exists in {where}; write '{where[0]}-{ref}@kubernetescrd')" if where else ""
            bad.append(f"{fname}:{route}: '{ref}' is looked up in the service namespace '{svc_ns}'{hint}")
    assert not bad, "\n".join(bad)
