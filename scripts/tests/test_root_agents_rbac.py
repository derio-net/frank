"""Guard for the scoped `root-agents` RBAC (derio-net/frank#912, spec 2026-11-14--auth--root-agents-least-privilege R7).

Static over every Role / ClusterRole / RoleBinding / ClusterRoleBinding under apps/. The live proof is
the SubjectAccessReview matrix (scripts/root-agents-cutover.sh), not CI.
"""
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROTECTED = {"upgrade-sessions", "cluster-update-fr", "runs-fr"}
# Namespaces whose Secrets are the credential store of the update pipeline or of the platform.
SECRET_NAMESPACES = PROTECTED | {"argocd", "infisical", "authentik", "kube-system", "longhorn-system"}
SECRET_GROUPS_OK = {"root-admins", "root-devops", "system:masters"}
# ServiceAccounts that may read Secrets in a protected namespace, each with its reason.
SA_ALLOWLIST = {
    ("cluster-update-fr", "cluster-update-fr"): "the console launches sessions and holds their credentials",
    ("upgrade-sessions", "upgrade-session-chart-major"): "session type; acts inside its own namespace",
    ("upgrade-sessions", "upgrade-session-stateful"): "session type; acts inside its own namespace",
    ("upgrade-sessions", "upgrade-session-rollouts"): "session type; acts inside its own namespace",
    ("upgrade-sessions", "upgrade-session-frank-os"): "session type; acts inside its own namespace",
    # Vendored Tekton controllers: upstream grants them cluster-wide Secret access (git credentials,
    # webhook TLS); they are platform controllers, not agent identities. Narrowing them means forking vendor/.
    ("tekton-pipelines", "tekton-pipelines-controller"): "vendored controller; resolves PipelineRun secrets",
    ("tekton-pipelines-resolvers", "tekton-pipelines-resolvers"): "vendored remote resolvers; reads git credentials",
    ("tekton-pipelines", "tekton-triggers-sa"): "EventListener SA; reads trigger secrets for the CI pipelines",
    ("tekton-pipelines", "tekton-triggers-controller"): "vendored controller",
    ("tekton-pipelines", "tekton-triggers-webhook"): "vendored webhook; owns its TLS Secret",
    ("tekton-pipelines", "tekton-triggers-core-interceptors"): "vendored interceptors; read webhook secrets",
}
# `get` on pods/exec, pods/attach, pods/portforward opens a websocket stream, so the connect
# subresources are forbidden even for a read-only verb set.
FORBIDDEN_RESOURCES = {"secrets", "serviceaccounts", "serviceaccounts/token", "*", "pods/exec", "pods/attach",
                       "pods/portforward", "pods/proxy", "nodes/proxy", "services/proxy"}
# What a root-agents ClusterRoleBinding may name: cluster-scoped kinds only. A namespaced kind bound
# cluster-wide would reach the protected namespaces, which only per-namespace RoleBindings can exclude.
CLUSTER_SCOPED = {"nodes", "namespaces", "persistentvolumes", "storageclasses", "customresourcedefinitions"}
FORBIDDEN_VERBS = {"impersonate", "bind", "escalate", "*", "create", "update", "patch", "delete",
                   "deletecollection"}
READ = {"get", "list", "watch", "*"}
BUILTIN = {  # ClusterRoles shipped by Kubernetes: name -> reads Secrets?
    "cluster-admin": True, "admin": True, "edit": True, "view": False,
}


def _docs():
    for f in sorted((ROOT / "apps").rglob("*.yaml")):
        try:
            for d in yaml.safe_load_all(f.read_text()):
                if isinstance(d, dict) and d.get("kind"):
                    yield f, d
        except yaml.YAMLError:
            continue  # Helm-templated


DOCS = list(_docs())
ROLES = {}
AGGREGATED = set()  # roles that aggregate, or are aggregated into view/edit/admin
BINDINGS = []
for _f, _d in DOCS:
    if _d["kind"] in ("Role", "ClusterRole"):
        ROLES[(_d["kind"], _d["metadata"].get("namespace"), _d["metadata"]["name"])] = _d.get("rules") or []
        if _d.get("aggregationRule") or any(k.startswith("rbac.authorization.k8s.io/aggregate-to-")
                                            for k in (_d["metadata"].get("labels") or {})):
            AGGREGATED.add(_d["metadata"]["name"])
    elif _d["kind"] in ("RoleBinding", "ClusterRoleBinding"):
        BINDINGS.append((_f, _d))


def _rules_of(binding):
    ref, ns = binding["roleRef"], binding["metadata"].get("namespace")
    key = (ref["kind"], ns if ref["kind"] == "Role" else None, ref["name"])
    return ROLES.get(key)


def _reads_secrets(rules):
    return any(("secrets" in (r.get("resources") or []) or "*" in (r.get("resources") or []))
               and (READ & set(r.get("verbs") or [])) for r in rules)


def _binding_reads_secrets(binding):
    ref = binding["roleRef"]
    if ref["kind"] == "ClusterRole" and ref["name"] in BUILTIN and _rules_of(binding) is None:
        return BUILTIN[ref["name"]]
    return _reads_secrets(_rules_of(binding) or [])


def _reaches_protected(binding):
    if binding["kind"] == "ClusterRoleBinding":
        return True
    return binding["metadata"].get("namespace") in SECRET_NAMESPACES


def _sa_ok(ns, name):
    return (ns, name) in SA_ALLOWLIST or (ns, "*") in SA_ALLOWLIST


def test_generated_file_is_fresh():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/root_agents_rbac.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_generated_binding_in_protected_or_hop_namespaces():
    gen = [d for f, d in DOCS if f.name == "root-agents-rbac.yaml" and d["kind"] == "RoleBinding"]
    assert gen, "the generated RoleBindings are missing"
    for d in gen:
        ns = d["metadata"]["namespace"]
        assert ns not in PROTECTED, ns
    got = {d["metadata"]["namespace"] for d in gen}
    # Namespaces that exist only on Hop (its root chart is a different cluster) must never leak in through
    # life_sessions._destinations(), which yields hop/* keys too.
    assert not got & {"caddy-system", "headscale-system", "crowdsec-system", "falco-system"}, got
    # An independent pin, so a generator regression that drops namespaces cannot regenerate itself green.
    assert {"argocd", "monitoring", "authentik", "infisical", "kube-system", "longhorn-system"} <= got, got
    assert len(got) >= 30, len(got)
    for d in gen:
        assert d["roleRef"] == {"kind": "ClusterRole", "name": "root-agents-ns-read",
                                "apiGroup": "rbac.authorization.k8s.io"}, d["metadata"]["namespace"]
        assert d["subjects"] == [{"kind": "Group", "name": "root-agents", "apiGroup": "rbac.authorization.k8s.io"}]


def test_protected_set_is_the_same_everywhere():
    sys.path.insert(0, str(ROOT / "scripts"))
    import root_agents_rbac
    assert set(root_agents_rbac.PROTECTED) == PROTECTED
    script = (ROOT / "scripts/root-agents-cutover.sh").read_text()
    assert f'PROTECTED="{" ".join(sorted(PROTECTED, key=script.index))}"' in script


def test_the_cluster_scoped_read_binding_exists_and_names_the_cluster_role():
    crb = [b for _, b in BINDINGS if b["kind"] == "ClusterRoleBinding"
           and any(sub.get("name") == "root-agents" for sub in b.get("subjects") or [])]
    assert [b["metadata"]["name"] for b in crb] == ["authentik-root-agents-read"]
    assert crb[0]["roleRef"]["name"] == "root-agents-cluster-read"


def test_every_root_agents_subject_is_read_only_and_secretless():
    seen = 0
    for f, b in BINDINGS:
        if not any(s.get("kind") == "Group" and s["name"] == "root-agents" for s in b.get("subjects") or []):
            continue
        seen += 1
        assert b["roleRef"]["name"] not in BUILTIN, f"{f}: root-agents bound to built-in {b['roleRef']['name']}"
        rules = _rules_of(b)
        assert rules, f"{f}: {b['metadata']['name']} resolves to no rules"
        assert b["roleRef"]["name"] not in AGGREGATED, f"{f}: {b['roleRef']['name']} uses aggregation"
        for r in rules:
            if b["kind"] == "ClusterRoleBinding":
                assert set(r.get("resources") or []) <= CLUSTER_SCOPED, (f, r)
            assert not (FORBIDDEN_RESOURCES & set(r.get("resources") or [])), (f, r)
            assert not (FORBIDDEN_VERBS & set(r.get("verbs") or [])), (f, r)
        if b["kind"] == "RoleBinding":
            assert b["metadata"]["namespace"] not in PROTECTED
    assert seen >= 31, f"root-agents bindings found: {seen} (1 cluster-read + one per namespace expected)"


def test_root_agents_has_no_cluster_admin_binding():
    for f, b in BINDINGS:
        if any(s.get("name") == "root-agents" for s in b.get("subjects") or []):
            assert b["roleRef"]["name"] not in BUILTIN, f


def test_no_unlisted_subject_reads_protected_secrets():
    bad = []
    for f, b in BINDINGS:
        if not _reaches_protected(b) or not _binding_reads_secrets(b):
            continue
        for s in b.get("subjects") or []:
            if s["kind"] == "Group" and s["name"] in SECRET_GROUPS_OK:
                continue
            if s["kind"] == "ServiceAccount" and _sa_ok(s.get("namespace"), s["name"]):
                continue
            bad.append((str(f.relative_to(ROOT)), b["metadata"]["name"], s["kind"], s["name"]))
    assert not bad, "\n".join(map(str, bad))


def test_the_allowlist_is_reasoned():
    assert all(reason for reason in SA_ALLOWLIST.values())
