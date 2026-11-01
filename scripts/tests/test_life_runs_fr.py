"""Production runs-fr, scoped to the upgrade sessions (plan 2026-10-31--life--update-security-lifecycle, phase 4).

runs-fr trusts a header and has no auth of its own, so its network policy is the primary guard.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "apps/root/templates/runs-fr.yaml"
VALUES = ROOT / "apps/runs-fr/values.yaml"
MAN = ROOT / "apps/runs-fr/manifests"
SESSIONS = "upgrade-sessions"


def app(template=TEMPLATE):
    text = template.read_text()
    for k, v in (("{{ .Values.repoURL }}", "x"), ("{{ .Values.targetRevision }}", "main"),
                 ("{{ .Values.destination.server }}", "s")):
        text = text.replace(k, v)
    return yaml.safe_load(text)


def values():
    return yaml.safe_load(VALUES.read_text())


def manifests():
    out = []
    for f in sorted(MAN.glob("*.yaml")):
        out += [d for d in yaml.safe_load_all(f.read_text()) if d]
    return out


def test_installs_the_runs_fr_chart_like_staging_with_a_pinned_ref():
    spec = app()["spec"]
    chart = next(s for s in spec["sources"] if s.get("path") == "charts/runs-fr")
    staging = app(ROOT / "apps/root/templates/runs-fr-staging.yaml")
    assert chart["repoURL"] == next(s for s in staging["spec"]["sources"] if s.get("path"))["repoURL"]
    assert re.fullmatch(r"v\d+\.\d+\.\d+", chart["targetRevision"]), "production must not track main"
    assert "$values/apps/runs-fr/values.yaml" in chart["helm"]["valueFiles"]
    assert any(s.get("ref") == "values" for s in spec["sources"])
    assert any(s.get("path") == "apps/runs-fr/manifests" for s in spec["sources"])
    assert spec["destination"]["namespace"] == "runs-fr"
    assert "name" not in spec["destination"] or spec["destination"]["name"] != "staging"
    assert "ServerSideApply=true" in spec["syncPolicy"]["syncOptions"]


def test_scoped_to_the_session_namespace_and_label_with_the_authentik_header():
    v = values()
    assert v["namespace"] == SESSIONS
    assert v["labelSelector"] == "fr.run/id"
    assert v["authHeader"] == "X-authentik-username"


def test_the_role_header_is_one_the_proxy_overwrites_and_can_never_say_owner():
    v = values()
    mw = next(d for d in yaml.safe_load_all((ROOT / "apps/traefik/manifests/middlewares.yaml").read_text())
              if d and d["metadata"]["name"] == "authentik-forwardauth")
    assert v["authRoleHeader"] in mw["spec"]["forwardAuth"]["authResponseHeaders"], \
        "a client-supplied role header would pass through Traefik untouched"
    assert v["authRoleHeader"] != "X-Forwarded-Role"
    assert v["authRoleHeader"] in ("X-authentik-meta-provider", "X-authentik-meta-app", "X-authentik-meta-outpost")


def test_image_is_pinned_exactly():
    img = values()["image"]
    assert img["repository"] == "ghcr.io/derio-net/runs-fr"
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(img["tag"])), img


def test_service_is_cluster_ip_and_no_chart_ingress():
    v = values()
    assert v["service"]["type"] == "ClusterIP"
    assert not v.get("ingress", {}).get("enabled", False)
    assert v["replicaCount"] == 1


def test_chart_network_policy_is_off_because_a_cilium_policy_names_the_proxy():
    # The chart's own policy would be a second, weaker statement of the same rule.
    assert not values().get("networkPolicy", {}).get("enabled", False)


def test_only_traefik_reaches_the_ui_port():
    (cnp,) = [d for d in manifests() if d["kind"] == "CiliumNetworkPolicy"]
    assert cnp["metadata"]["namespace"] == "runs-fr"
    assert cnp["spec"]["endpointSelector"]["matchLabels"] == {"app.kubernetes.io/name": "runs-fr"}
    (rule,) = cnp["spec"]["ingress"]
    assert "fromEntities" not in rule and "fromCIDR" not in rule
    assert rule["fromEndpoints"] == [{"matchLabels": {"k8s:io.kubernetes.pod.namespace": "traefik-system",
                                                      "app.kubernetes.io/name": "traefik"}}]
    assert rule["toPorts"] == [{"ports": [{"port": "8080", "protocol": "TCP"}]}]


def test_namespace_is_restricted_and_survives_a_prune():
    (ns,) = [d for d in manifests() if d["kind"] == "Namespace"]
    assert ns["metadata"]["name"] == "runs-fr"
    assert ns["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "restricted"


def test_helm_rendered_role_is_a_namespaced_pods_and_exec_role_only():
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("helm"):
        import pytest
        pytest.skip("helm not installed")
    chart_tag = next(s for s in app()["spec"]["sources"] if s.get("path") == "charts/runs-fr")["targetRevision"]
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(["git", "clone", "--depth", "1", "--branch", chart_tag,
                            "https://github.com/derio-net/runs-fr.git", d],
                           capture_output=True, text=True)
        if r.returncode != 0:
            import pytest
            pytest.skip("cannot clone the runs-fr chart offline")
        out = subprocess.run(["helm", "template", "runs-fr", f"{d}/charts/runs-fr", "-n", "runs-fr",
                              "-f", str(VALUES)], capture_output=True, text=True, check=True).stdout
    docs = [x for x in yaml.safe_load_all(out) if x]
    assert not [x for x in docs if x["kind"] in ("ClusterRole", "ClusterRoleBinding")]
    (role,) = [x for x in docs if x["kind"] == "Role"]
    assert role["metadata"]["namespace"] == SESSIONS
    flat = {(g, r, v) for rule in role["rules"] for g in rule["apiGroups"] for r in rule["resources"] for v in rule["verbs"]}
    assert flat == {("", "pods", "get"), ("", "pods", "list"), ("", "pods", "watch"), ("", "pods/exec", "create")}
    assert "pods/ephemeralcontainers" not in str(role)
    # The names the IngressRoute and the Cilium policy rely on come from the chart, not from us.
    (svc,) = [x for x in docs if x["kind"] == "Service"]
    assert svc["metadata"]["name"] == "runs-fr" and svc["spec"]["ports"][0]["port"] == 80
    (dep,) = [x for x in docs if x["kind"] == "Deployment"]
    assert dep["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/name"] == "runs-fr"
    env = {e["name"]: e["value"] for e in dep["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["NAMESPACE"] == SESSIONS and env["AUTH_HEADER"] == "X-authentik-username"
    assert dep["spec"]["template"]["spec"]["containers"][0]["image"] == "ghcr.io/derio-net/runs-fr:0.3.0"
    assert not [x for x in docs if x["kind"] == "NetworkPolicy"]
