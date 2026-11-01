"""Disposable upgrade-session infrastructure on Frank (plan 2026-10-31--life--update-security-lifecycle, phase 5).

The upgrade-sessions namespace is the security boundary for pods that hold cluster-upgrade
credentials (spec R20, R21, R23). The console (derio-net/cluster-update-fr) creates the pods and
their Secrets; frank owns everything that bounds them:

  - the namespace, PodSecurity restricted;
  - default-deny plus one egress policy per upgrade type: egress is the exfiltration boundary
    (p5-session-merge-and-exfil-boundary), so no general internet, no gist/raw/upload hosts, and
    DNS answers only for the names a type may reach (a DNS proxy that answers everything is a
    tunnel);
  - one ServiceAccount per in-cluster type, and STATIC per-app-namespace Roles generated from the
    policy facts (p5-session-rbac-static) -- the console creates no RoleBindings;
  - nobody but cluster-admins may exec into or add ephemeral containers to a session pod, except
    runs-fr's exec, which is how the operator attaches (p5-no-ephemeral-containers).

Generated objects come from scripts/life_sessions.py; a drift test keeps the files equal to it.
"""
import functools
import ipaddress
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

APP = ROOT / "apps/upgrade-sessions"
MAN = APP / "manifests"
TEMPLATE = ROOT / "apps/root/templates/upgrade-sessions.yaml"
CONSOLE_MAN = ROOT / "apps/cluster-update-fr/manifests"
NS = "upgrade-sessions"
TYPES = ("chart-major", "stateful", "rollouts", "frank-os", "hop-os")
IN_CLUSTER = ("chart-major", "stateful", "rollouts", "frank-os")
TYPE_LABEL = "cluster-update.fr/type"
READ_VERBS = {"get", "list", "watch"}
FRANK_NODES = {"192.168.55.21", "192.168.55.22", "192.168.55.23", "192.168.55.31",
               "192.168.55.71", "192.168.55.41", "192.168.55.42"}

GITHUB = {"api.github.com", "github.com"}
MODELS = {"api.anthropic.com", "console.anthropic.com", "claude.ai", "platform.claude.com",
          "api.openai.com", "auth.openai.com", "chatgpt.com"}
OMNI = "omni.frank.derio.net"
TAILNET = {"headscale.hop.derio.net"}
# Hosts that would let a steered session upload data somewhere readable, or fetch arbitrary code.
FORBIDDEN_HOSTS = {"gist.github.com", "uploads.github.com", "raw.githubusercontent.com",
                   "objects.githubusercontent.com", "gist.githubusercontent.com", "codeload.github.com",
                   "pastebin.com", "registry.npmjs.org", "pypi.org"}


def application():
    text = TEMPLATE.read_text()
    for k, v in (("{{ .Values.repoURL }}", "x"), ("{{ .Values.targetRevision }}", "main"),
                 ("{{ .Values.destination.server }}", "s")):
        text = text.replace(k, v)
    return yaml.safe_load(text)


@functools.lru_cache(maxsize=None)
def _manifests():
    out = []
    for f in sorted(MAN.glob("*.yaml")):
        if f.name == "kustomization.yaml":
            continue
        out += [d for d in yaml.safe_load_all(f.read_text()) if d]
    return tuple(out)


def manifests():
    return list(_manifests())


def of_kind(kind, docs=None):
    return [d for d in (docs if docs is not None else manifests()) if d["kind"] == kind]


def cnp(name):
    return next(d for d in of_kind("CiliumNetworkPolicy") if d["metadata"]["name"] == name)


def type_policy(typ):
    return cnp(f"upgrade-session-{typ}")


def fqdns(policy):
    names = set()
    for rule in policy["spec"].get("egress", []):
        for f in rule.get("toFQDNs", []):
            names.add(f.get("matchName") or f.get("matchPattern"))
    return names


def ports(rule):
    return {(p["port"], p.get("protocol", "TCP")) for tp in rule.get("toPorts", []) for p in tp.get("ports", [])}


# ------------------------------------------------------------------ app + namespace
def test_root_template_deploys_the_manifests_with_prune_and_no_namespace_creation():
    spec = application()["spec"]
    assert spec["source"]["path"] == "apps/upgrade-sessions/manifests"
    assert spec["destination"]["namespace"] == NS
    # Generated Roles disappear from git when an app stops being stateful; prune must remove the
    # stale grant from the cluster, or a revoked permission keeps working.
    assert spec["syncPolicy"]["automated"] == {"prune": True, "selfHeal": True}
    assert "ServerSideApply=true" in spec["syncPolicy"]["syncOptions"]
    assert "CreateNamespace=false" in spec["syncPolicy"]["syncOptions"]


def test_kustomization_lists_every_manifest():
    kust = yaml.safe_load((MAN / "kustomization.yaml").read_text())
    files = {f.name for f in MAN.glob("*.yaml")} - {"kustomization.yaml"}
    assert set(kust["resources"]) == files


def test_namespace_is_podsecurity_restricted_and_survives_app_deletion():
    ns = of_kind("Namespace")
    assert [n["metadata"]["name"] for n in ns] == [NS]
    labels = ns[0]["metadata"]["labels"]
    assert labels["pod-security.kubernetes.io/enforce"] == "restricted"
    assert labels["pod-security.kubernetes.io/audit"] == "restricted"
    # Deleting the namespace would delete live session pods mid-upgrade.
    assert ns[0]["metadata"]["annotations"]["argocd.argoproj.io/sync-options"] == "Prune=false,Delete=false"


def test_smoke_declaration_exists_for_the_app():
    decl = yaml.safe_load((ROOT / "smoke/frank/upgrade-sessions.yaml").read_text())
    assert decl["app"] == "upgrade-sessions" and decl["cluster"] == "frank"
    assert decl["checks"][0]["target"] == "application/upgrade-sessions"


# ------------------------------------------------------------------ network policy
def test_default_deny_selects_every_pod_in_both_directions():
    d = cnp("upgrade-sessions-default-deny")
    assert d["metadata"]["namespace"] == NS
    assert d["spec"]["endpointSelector"] == {}
    # An empty rule enables enforcement and allows nothing.
    assert d["spec"]["ingress"] == [{}] and d["spec"]["egress"] == [{}]
    # Deny outranks allow in Cilium: SSH is shut for every session whatever the type allows.
    assert d["spec"]["egressDeny"] == [{"toEntities": ["all"], "toPorts": [{"ports": [{"port": "22", "protocol": "TCP"}]}]}]


def test_one_egress_policy_per_type_selecting_its_label_and_nothing_else():
    names = {d["metadata"]["name"] for d in of_kind("CiliumNetworkPolicy")}
    assert names == {"upgrade-sessions-default-deny"} | {f"upgrade-session-{t}" for t in TYPES}
    for t in TYPES:
        p = type_policy(t)
        assert p["metadata"]["namespace"] == NS
        assert p["spec"]["endpointSelector"] == {"matchLabels": {TYPE_LABEL: t}}
        assert "ingress" not in p["spec"], f"{t}: session pods take no inbound traffic"
        assert of_kind("CiliumClusterwideNetworkPolicy") == []


@pytest.mark.parametrize("typ", TYPES)
def test_every_type_reaches_github_api_and_git_and_the_model_providers(typ):
    names = fqdns(type_policy(typ))
    assert GITHUB | MODELS <= names


@pytest.mark.parametrize("typ", TYPES)
def test_no_type_reaches_an_upload_host_or_a_wildcard(typ):
    names = fqdns(type_policy(typ))
    assert not names & FORBIDDEN_HOSTS
    for n in names:
        assert n != "*" and not n.startswith("*."), f"{typ}: wildcard {n} widens the exfiltration boundary"
        assert "github" not in n or n in GITHUB, f"{typ}: {n}"


@pytest.mark.parametrize("typ", TYPES)
def test_every_egress_rule_names_ports_and_no_rule_opens_ssh(typ):
    for rule in type_policy(typ)["spec"]["egress"]:
        assert ("22", "TCP") not in ports(rule), f"{typ}: no session gets SSH anywhere (no Omni host access)"


@pytest.mark.parametrize("typ", TYPES)
def test_only_entity_is_the_kube_apiserver(typ):
    for rule in type_policy(typ)["spec"]["egress"]:
        if "toEntities" in rule:
            assert rule["toEntities"] == ["kube-apiserver"], rule
            assert ports(rule) == {("6443", "TCP")}
    assert any("toEntities" in r for r in type_policy(typ)["spec"]["egress"])


@pytest.mark.parametrize("typ", TYPES)
def test_every_type_reaches_the_console_session_api_and_gitea(typ):
    eps = [(r["toEndpoints"], ports(r)) for r in type_policy(typ)["spec"]["egress"] if "toEndpoints" in r]
    console = [{"matchLabels": {"k8s:io.kubernetes.pod.namespace": "cluster-update-fr",
                                "app.kubernetes.io/name": "cluster-update-fr"}}]
    assert (console, {("8081", "TCP")}) in eps
    assert ([{"matchLabels": {"k8s:io.kubernetes.pod.namespace": "gitea"}}], {("3000", "TCP")}) in eps


def test_omni_and_talos_api_only_for_frank_os():
    for t in TYPES:
        names = fqdns(type_policy(t))
        cidrs = [c for r in type_policy(t)["spec"]["egress"] for c in r.get("toCIDR", [])]
        if t == "frank-os":
            assert OMNI in names
            rule = next(r for r in type_policy(t)["spec"]["egress"]
                        if any(f.get("matchName") == OMNI for f in r.get("toFQDNs", [])))
            assert ports(rule) == {("443", "TCP")}, "Omni API only; never the Omni host itself"
            assert {str(ipaddress.ip_network(c).network_address) for c in cidrs} == FRANK_NODES
            assert all(c.endswith("/32") for c in cidrs)
            talos = [r for r in type_policy(t)["spec"]["egress"] if "toCIDR" in r]
            assert all(ports(r) == {("50000", "TCP")} for r in talos)
        else:
            assert not any("omni" in n for n in names), t
            assert cidrs == [], f"{t}: no CIDR egress"


def test_tailnet_only_for_hop_os():
    for t in TYPES:
        names = fqdns(type_policy(t))
        has = bool(names & TAILNET) or any("tailscale.com" in n for n in names)
        assert has == (t == "hop-os"), t
    rules = type_policy("hop-os")["spec"]["egress"]
    stun = [r for r in rules if ("3478", "UDP") in ports(r)]
    assert stun, "DERP/STUN needs UDP 3478"


def _ns_targets(t):
    out = {}
    for r in type_policy(t)["spec"]["egress"]:
        for e in r.get("toEndpoints", []):
            n = e["matchLabels"].get("k8s:io.kubernetes.pod.namespace")
            if n not in ("cluster-update-fr", "gitea", "kube-system"):
                out[n] = sorted(int(p) for p, _ in ports(r))
    return out


def test_target_app_services_only_for_stateful_and_rollouts_on_their_service_ports():
    import life_policy
    import life_sessions as ls

    facts = life_policy.load_facts()
    for t, flag in (("stateful", "stateful"), ("rollouts", "rollout")):
        got = _ns_targets(t)
        namespaces = set(ls.app_namespaces(flag)) - ls.UNREACHABLE
        want = {}
        for k, f in facts.items():
            for s in f["services"] if k.startswith("frank/") else []:
                if s["namespace"] in namespaces:
                    want.setdefault(s["namespace"], set()).update(p for p in s["ports"] if p != 22)
        assert got == {ns: sorted(p) for ns, p in want.items()}, t
    assert "paperclip-system" in _ns_targets("stateful")
    assert "litellm" in _ns_targets("rollouts"), "the Rollout's Services live in the sibling app"
    for t in ("chart-major", "frank-os", "hop-os"):
        assert _ns_targets(t) == {}, t


def test_infrastructure_with_unauthenticated_admin_apis_is_never_a_network_target():
    # Longhorn's manager API deletes volumes without auth; VictoriaMetrics/Logs serve delete APIs.
    for t in TYPES:
        for ns in ("longhorn-system", "monitoring", NS, "argocd"):
            assert ns not in _ns_targets(t), (t, ns)


@pytest.mark.parametrize("typ", TYPES)
def test_dns_answers_only_the_names_the_type_may_reach(typ):
    rules = type_policy(typ)["spec"]["egress"]
    dns = [r for r in rules if any(e["matchLabels"].get("k8s-app") == "kube-dns" for e in r.get("toEndpoints", []))]
    assert len(dns) == 1
    assert ports(dns[0]) == {("53", "UDP"), ("53", "TCP")}
    allowed = set()
    for tp in dns[0]["toPorts"]:
        for d in tp["rules"]["dns"]:
            allowed.add(d.get("matchName") or d.get("matchPattern"))
    assert "*" not in allowed, "a DNS proxy that answers everything is a tunnel out"
    for name in fqdns(type_policy(typ)):
        assert name in allowed, f"{typ}: {name} is allowed but cannot be resolved"
        # resolv.conf search domains (ndots:5) are tried first; their names must be answerable too
        assert f"{name}.{NS}.svc.cluster.local" in allowed
    for name in allowed:
        base = re.sub(r"\.(upgrade-sessions\.svc\.cluster\.local|svc\.cluster\.local|cluster\.local)$", "", name)
        assert base in fqdns(type_policy(typ)) or name.endswith(".svc.cluster.local"), f"{typ}: stray DNS name {name}"


def test_network_policies_equal_the_generator():
    import life_sessions as ls

    assert (MAN / "networkpolicies.yaml").read_text() == ls.render(ls.network_policies())


# ------------------------------------------------------------------ service accounts + RBAC
def test_one_service_account_per_in_cluster_type_and_none_for_hop_os():
    sas = of_kind("ServiceAccount")
    assert {s["metadata"]["name"] for s in sas} == {f"upgrade-session-{t}" for t in IN_CLUSTER}
    for s in sas:
        assert s["metadata"]["namespace"] == NS
        # The pod opts in explicitly (the admission policy requires it); nothing else in the
        # namespace gets these tokens by accident.
        assert s["automountServiceAccountToken"] is False


def rbac_docs():
    return [d for d in manifests() if d["kind"] in ("Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding")]


def test_read_clusterrole_is_read_only_and_never_reads_secrets_or_logs():
    cr = of_kind("ClusterRole")
    assert [c["metadata"]["name"] for c in cr] == ["upgrade-session-read"]
    for rule in cr[0]["rules"]:
        assert set(rule["verbs"]) <= READ_VERBS, rule
        assert not {"secrets", "configmaps", "pods/log", "pods/exec", "pods/attach", "pods/portforward",
                    "*"} & set(rule["resources"]), rule
    crb = of_kind("ClusterRoleBinding")
    assert len(crb) == 1 and crb[0]["roleRef"]["name"] == "upgrade-session-read"
    assert {(s["name"], s["namespace"]) for s in crb[0]["subjects"]} == {
        (f"upgrade-session-{t}", NS) for t in IN_CLUSTER}


def test_no_session_rbac_grants_writes_beyond_the_two_scoped_ones():
    for d in of_kind("Role"):
        for rule in d["rules"]:
            assert "*" not in rule["verbs"] and "*" not in rule["resources"], d["metadata"]
            assert not {"delete", "deletecollection", "update", "escalate", "bind", "impersonate"} & set(rule["verbs"])
            writes = set(rule["verbs"]) - READ_VERBS
            if writes:
                assert (rule["resources"], writes) in (
                    (["volumesnapshots"], {"create"}), (["snapshots"], {"create"}),
                    (["rollouts/status"], {"patch"})), (d["metadata"], rule)


def _bindings_to(sa):
    out = {}
    for b in of_kind("RoleBinding"):
        if any(s["name"] == sa and s["namespace"] == NS for s in b["subjects"]):
            out[b["metadata"]["namespace"]] = b["roleRef"]["name"]
    return out


def test_stateful_role_exists_in_exactly_the_stateful_app_namespaces():
    import life_sessions as ls

    bound = _bindings_to("upgrade-session-stateful")
    expected = set(ls.app_namespaces("stateful")) | {"longhorn-system"}
    assert set(bound) == expected
    roles = {(r["metadata"]["namespace"], r["metadata"]["name"]): r for r in of_kind("Role")}
    for ns, role in bound.items():
        rules = roles[(ns, role)]["rules"]
        if ns == "longhorn-system":
            # Longhorn's Snapshot CRs live in longhorn-system, whatever namespace owns the volume.
            assert {"apiGroups": ["longhorn.io"], "resources": ["snapshots"], "verbs": ["create", "get", "list"]} in rules
        if ns in ls.app_namespaces("stateful"):
            assert {"apiGroups": [""], "resources": ["persistentvolumeclaims"], "verbs": ["get", "list"]} in rules
            assert {"apiGroups": ["snapshot.storage.k8s.io"], "resources": ["volumesnapshots"],
                    "verbs": ["create", "get", "list"]} in rules


def test_rollouts_role_exists_in_exactly_the_rollout_app_namespaces():
    import life_sessions as ls

    bound = _bindings_to("upgrade-session-rollouts")
    assert set(bound) == set(ls.app_namespaces("rollout")) and bound
    roles = {(r["metadata"]["namespace"], r["metadata"]["name"]): r for r in of_kind("Role")}
    for ns, role in bound.items():
        assert roles[(ns, role)]["rules"] == [
            {"apiGroups": ["argoproj.io"], "resources": ["rollouts"], "verbs": ["get", "list"]},
            {"apiGroups": ["argoproj.io"], "resources": ["rollouts/status"], "verbs": ["patch"]}]


def test_chart_major_and_frank_os_have_no_namespaced_writes():
    assert _bindings_to("upgrade-session-chart-major") == {}
    assert _bindings_to("upgrade-session-frank-os") == {}


def test_app_namespaces_come_from_the_policy_facts_frank_only():
    import life_policy
    import life_sessions as ls

    facts = life_policy.load_facts()
    stateful_frank = {k for k, f in facts.items() if f["stateful"] and k.startswith("frank/")}
    assert stateful_frank, "facts lost the stateful apps"
    # Hop's stateful apps (static Hetzner PVs, no Longhorn) get no Frank-side snapshot grant.
    assert not any(n in ls.app_namespaces("stateful") for n in ("caddy-system", "headscale-system"))
    assert "paperclip-system" in ls.app_namespaces("stateful")
    assert ls.app_namespaces("rollout") == ["litellm"]


def test_app_roles_equal_the_generator():
    import life_sessions as ls

    assert (MAN / "app-roles.yaml").read_text() == ls.render(ls.app_roles())


# ------------------------------------------------------------------ exec / ephemeral containers
def _local_rbac_everywhere():
    out = []
    for f in list((ROOT / "apps").rglob("*.yaml")) + list((ROOT / "clusters/hop/apps").rglob("*.yaml")):
        if "/vendor/" in str(f) or "/chart/" in str(f) or "/root/templates/" in str(f):
            continue
        try:
            docs = list(yaml.safe_load_all(f.read_text()))
        except yaml.YAMLError:
            continue
        for d in docs:
            if isinstance(d, dict) and d.get("kind") in ("Role", "ClusterRole"):
                out.append((f, d))
    return out


def _grants(rule, resource):
    res = set(rule.get("resources", []))
    return resource in res or "*" in res or (resource.startswith("pods/") and "pods/*" in res)


def test_nothing_outside_cluster_admin_may_add_ephemeral_containers_or_exec_into_sessions():
    for f, d in _local_rbac_everywhere():
        ns = d["metadata"].get("namespace")
        for rule in d.get("rules", []):
            if d["kind"] == "ClusterRole" or ns == NS:
                assert not _grants(rule, "pods/ephemeralcontainers"), (f, d["metadata"]["name"])
                assert not _grants(rule, "pods/exec"), (f, d["metadata"]["name"], "only runs-fr may exec into sessions")


def test_runs_fr_is_the_one_exec_into_sessions_and_has_no_ephemeral_containers():
    values = (ROOT / "apps/runs-fr/values.yaml").read_text()
    assert yaml.safe_load(values)["namespace"] == NS
    assert "ephemeralcontainers" not in values


def test_console_role_in_sessions_is_unchanged_and_has_no_exec():
    docs = [d for d in yaml.safe_load_all((CONSOLE_MAN / "rbac.yaml").read_text()) if d]
    role = next(d for d in docs if d["kind"] == "Role")
    assert role["metadata"]["namespace"] == NS
    assert role["rules"] == [{"apiGroups": [""], "resources": ["pods", "secrets"],
                              "verbs": ["get", "list", "create", "delete"]}]


# ------------------------------------------------------------------ credentials
def test_session_github_token_comes_from_the_scoped_session_app_only():
    gens = {d["metadata"]["name"]: d for d in yaml.safe_load_all((CONSOLE_MAN / "clustergenerators.yaml").read_text()) if d}
    spec = gens["github-app-cluster-update-session"]["spec"]["generator"]["githubAccessTokenSpec"]
    assert spec["repositories"] == ["frank"]
    assert spec["permissions"] == {"contents": "write", "pull_requests": "write", "metadata": "read"}
    es = [d for d in yaml.safe_load_all((CONSOLE_MAN / "externalsecrets.yaml").read_text()) if d]
    session = next(e for e in es if e["metadata"]["name"] == "cluster-update-fr-session-github")
    assert session["metadata"]["namespace"] == "cluster-update-fr"
    assert session["spec"]["dataFrom"][0]["sourceRef"]["generatorRef"]["name"] == "github-app-cluster-update-session"


def test_upgrade_sessions_holds_no_standing_secret():
    # Every credential reaches a session through the console-created us-<id>-creds Secret, which
    # dies with the session (R23). Nothing in git puts a standing Secret in the namespace.
    for kind in ("Secret", "ExternalSecret", "SecretStore", "ClusterSecretStore"):
        assert of_kind(kind) == [], kind


def test_no_credential_carries_the_omni_host():
    # operator decision omni-runbook: no session ever receives access to the Omni host.
    text = "\n".join(f.read_text() for f in MAN.glob("*.yaml"))
    assert "ssh" not in text.lower()
    dep = (CONSOLE_MAN / "deployment.yaml").read_text()
    projected = re.findall(r"path: ([\w-]+)", dep.split("name: session-credentials", 2)[-1])
    assert set(projected) <= {"github-token", "omni-sa-key", "talosconfig", "hop-talosconfig", "hop-kubeconfig"}, projected


# ------------------------------------------------------------------ console pod admission
def test_console_pod_policy_forbids_overriding_the_entrypoint():
    # p5-session-selection-explicit: a pod `command:` replaces the image entrypoint, which is what
    # selects the pinned talosctl/kubectl; with it, neither is on PATH and the env is ignored.
    docs = [d for d in yaml.safe_load_all((CONSOLE_MAN / "admission-policy.yaml").read_text()) if d]
    pol = next(d for d in docs if d["metadata"]["name"] == "upgrade-session-pods")
    exprs = [v["expression"] for v in pol["spec"]["validations"]]
    assert "variables.containers.all(c, !has(c.command))" in exprs


# ------------------------------------------------------------------ image bumps
def test_agent_images_bump_covers_the_session_image():
    wf = (ROOT / ".github/workflows/agent-images-bump.yml").read_text()
    line = next(l for l in wf.splitlines() if l.strip().startswith("AGENT_IMAGES="))
    assert "upgrade-session" in line.split('"')[1].split()
