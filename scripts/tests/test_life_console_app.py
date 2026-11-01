"""The update console on Frank (plan 2026-10-31--life--update-security-lifecycle, phase 4).

Single writer, read-mostly RBAC with one namespaced write Role, an ingress lockdown that
holds even if the console's own checks fail, SSO restricted to the operator group, and a
CI path for the console's own repo. Contract: derio-net/cluster-update-fr README.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/cluster-update-fr"
MAN = APP / "manifests"
TEMPLATE = ROOT / "apps/root/templates/cluster-update-fr.yaml"
NS = "cluster-update-fr"
SESSIONS = "upgrade-sessions"
SA = "cluster-update-fr"
READ_VERBS = {"get", "list"}


def application():
    text = TEMPLATE.read_text()
    for k, v in (("{{ .Values.repoURL }}", "x"), ("{{ .Values.targetRevision }}", "main"),
                 ("{{ .Values.destination.server }}", "s")):
        text = text.replace(k, v)
    return yaml.safe_load(text)


def docs(*names):
    out = []
    for n in names:
        out += [d for d in yaml.safe_load_all((MAN / n).read_text()) if d]
    return out


def all_manifests():
    out = []
    for f in sorted(MAN.glob("*.yaml")):
        if f.name == "kustomization.yaml":
            continue
        out += [d for d in yaml.safe_load_all(f.read_text()) if d]
    return out


def of_kind(kind):
    return [d for d in all_manifests() if d["kind"] == kind]


def deployment():
    (d,) = of_kind("Deployment")
    return d


def pod():
    return deployment()["spec"]["template"]["spec"]


def container(name="console"):
    return next(c for c in pod()["containers"] if c["name"] == name)


def env_file():
    out = {}
    for line in (MAN / "files/console.env").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


# ------------------------------------------------------------------ Application


def test_application_is_a_single_source_with_pruning_for_the_config_hash():
    spec = application()["spec"]
    assert spec["source"]["path"] == "apps/cluster-update-fr/manifests"
    assert spec["destination"]["namespace"] == NS
    pol = spec["syncPolicy"]
    assert pol["automated"]["prune"] is True, "the hashed ConfigMap name changes; old one must go"
    assert pol["automated"]["selfHeal"] is True
    assert "ServerSideApply=true" in pol["syncOptions"]
    assert any(i["kind"] == "Secret" and "/data" in i["jsonPointers"] for i in spec["ignoreDifferences"])


def test_state_pvc_and_namespace_survive_a_prune():
    (pvc,) = of_kind("PersistentVolumeClaim")
    assert pvc["metadata"]["annotations"]["argocd.argoproj.io/sync-options"] == "Prune=false,Delete=false"
    (ns,) = [n for n in of_kind("Namespace") if n["metadata"]["name"] == NS]
    assert ns["metadata"]["annotations"]["argocd.argoproj.io/sync-options"] == "Prune=false,Delete=false"
    assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]


# ------------------------------------------------------------------ the pod


def test_single_writer_recreate():
    d = deployment()["spec"]
    assert d["replicas"] == 1
    assert d["strategy"] == {"type": "Recreate"}


def test_image_is_the_console_pinned_exactly():
    img = container()["image"]
    assert img.startswith("ghcr.io/derio-net/cluster-update-fr:") or img.startswith(
        "ghcr.io/derio-net/cluster-update-fr@sha256:"), img
    tag = img.split(":", 1)[1].split("@")[0] if ":" in img.split("/")[-1] else ""
    assert "@sha256:" in img or re.fullmatch(r"v\d+\.\d+\.\d+", tag), "exact version or digest"


def test_hardened_non_root_read_only():
    sc = pod()["securityContext"]
    assert sc["runAsNonRoot"] is True and sc["seccompProfile"]["type"] == "RuntimeDefault"
    for c in pod()["containers"] + pod().get("initContainers", []):
        s = c["securityContext"]
        assert s["allowPrivilegeEscalation"] is False, c["name"]
        assert s["capabilities"]["drop"] == ["ALL"], c["name"]
    assert container()["securityContext"]["readOnlyRootFilesystem"] is True
    assert pod()["serviceAccountName"] == SA


def test_state_lives_on_the_pvc_at_state_dir():
    mounts = {m["mountPath"]: m["name"] for m in container()["volumeMounts"]}
    state = env_file()["STATE_DIR"]
    vol = next(v for v in pod()["volumes"] if v["name"] == mounts[state])
    assert vol["persistentVolumeClaim"]["claimName"] == of_kind("PersistentVolumeClaim")[0]["metadata"]["name"]


def test_every_secret_reference_is_optional():
    for c in pod()["containers"] + pod().get("initContainers", []):
        for e in c.get("env", []):
            ref = e.get("valueFrom", {}).get("secretKeyRef")
            if ref:
                assert ref.get("optional") is True, (c["name"], e["name"])
        for ef in c.get("envFrom", []):
            if "secretRef" in ef:
                assert ef["secretRef"].get("optional") is True, c["name"]
    for v in pod()["volumes"]:
        if "secret" in v:
            assert v["secret"].get("optional") is True, v["name"]
        for src in v.get("projected", {}).get("sources", []):
            if "secret" in src:
                assert src["secret"].get("optional") is True, v["name"]


def test_credentials_reach_the_console_as_files():
    env = env_file()
    for key in ("GITHUB_TOKEN_FILE", "GITEA_TOKEN_FILE", "FRANK_UPDATER_TELEGRAM_BOT_TOKEN_FILE",
                "SESSION_SECRET_DIR", "HOP_KUBECONFIG"):
        assert env[key].startswith("/"), key
    mounted = {m["mountPath"] for m in container()["volumeMounts"]}
    for key in ("SESSION_SECRET_DIR",):
        assert env[key] in mounted
    for key in ("GITHUB_TOKEN_FILE", "GITEA_TOKEN_FILE", "FRANK_UPDATER_TELEGRAM_BOT_TOKEN_FILE",
                "HOP_KUBECONFIG"):
        assert any(env[key].startswith(m.rstrip("/") + "/") for m in mounted), key
    sessions_dir = next(v for v in pod()["volumes"]
                        if v["name"] == next(m["name"] for m in container()["volumeMounts"]
                                             if m["mountPath"] == env["SESSION_SECRET_DIR"]))
    files = {i["path"] for s in sessions_dir["projected"]["sources"] for i in s["secret"]["items"]}
    assert files == {"github-token", "omni-sa-key", "talosconfig", "hop-talosconfig", "hop-kubeconfig"}


def test_telegram_chat_and_thread_come_from_a_secret_not_from_git():
    env = {e["name"]: e for e in container().get("env", [])}
    for name in ("FRANK_UPDATER_TELEGRAM_CHAT_ID", "FRANK_UPDATER_TELEGRAM_SECURITY_THREAD_ID"):
        assert "secretKeyRef" in env[name]["valueFrom"], name


def test_tailscale_sidecar_has_its_own_state_and_user():
    ts = next(c for c in pod().get("initContainers", []) if c["name"] == "tailscale")
    assert ts["restartPolicy"] == "Always"
    assert ts["image"].startswith("tailscale/tailscale:v")
    env = {e["name"]: e for e in ts["env"]}
    assert env["TS_USERSPACE"]["value"] == "true"
    assert env["TS_SOCKS5_SERVER"]["value"] == "localhost:1055"
    assert env["TS_AUTHKEY"]["valueFrom"]["secretKeyRef"]["optional"] is True
    assert "--advertise-tags=tag:frank-updater" in env["TS_EXTRA_ARGS"]["value"]
    assert ts["securityContext"]["runAsUser"] not in (None, 0)
    state = next(m["name"] for m in ts["volumeMounts"] if m["mountPath"] == env["TS_STATE_DIR"]["value"])
    assert state not in {m["name"] for m in container()["volumeMounts"]}, "console must not read the node key"
    assert container()["securityContext"].get("runAsUser") != ts["securityContext"]["runAsUser"]


def test_probes_use_the_ops_port_only():
    c = container()
    ports = {p["name"]: p["containerPort"] for p in c["ports"]}
    assert ports == {"ui": 8080, "ops": 9090, "session": 8081}
    for probe in ("livenessProbe", "readinessProbe"):
        assert c[probe]["httpGet"]["port"] == "ops" and c[probe]["httpGet"]["path"] == "/healthz"


def test_services_are_cluster_ip_and_split_by_audience():
    svcs = {s["metadata"]["name"]: s for s in of_kind("Service")}
    assert all(s["spec"].get("type", "ClusterIP") == "ClusterIP" for s in svcs.values())
    ui = svcs["cluster-update-fr"]
    assert [p["port"] for p in ui["spec"]["ports"]] == [8080]
    sess = svcs["cluster-update-fr-session"]
    assert [p["port"] for p in sess["spec"]["ports"]] == [8081]
    assert env_file()["SESSION_API_URL"] == f"http://cluster-update-fr-session.{NS}.svc.cluster.local:8081"
    exposed = {p["port"] for s in svcs.values() for p in s["spec"]["ports"]}
    assert 9090 not in exposed, "metrics are scraped by pod, never through a Service others can reach"


# ------------------------------------------------------------------ config


def test_config_is_generated_with_a_hash_so_a_change_rolls_the_pod():
    k = yaml.safe_load((MAN / "kustomization.yaml").read_text())
    (gen,) = [g for g in k["configMapGenerator"] if g["name"] == "cluster-update-fr-config"]
    assert gen.get("namespace") == NS
    assert not k.get("generatorOptions", {}).get("disableNameSuffixHash", False)
    assert "files/console.env" in "".join(gen.get("envs", []))
    refs = [ef["configMapRef"]["name"] for ef in container().get("envFrom", []) if "configMapRef" in ef]
    assert refs == ["cluster-update-fr-config"]


def test_trust_config_is_declared_and_trusts_nothing_until_phase_7():
    env = env_file()
    for key in ("RENOVATE_BOT_LOGIN", "CONSOLE_BOT_LOGIN", "SESSION_BOT_LOGIN", "STATUS_CREATOR_LOGINS"):
        assert key in env, key
        assert env[key] == "", f"{key}: a placeholder login would be TRUSTED; empty means trust nothing"
    assert env["TRUSTED_COMMITTERS"] == "web-flow"
    assert env["FRANK_REF"] == "main" and env["FRANK_REPO"] == "derio-net/frank"


def test_ci_contexts_are_required_by_the_policy_file():
    policy = yaml.safe_load((ROOT / "update-policy.yaml").read_text())
    assert policy["required_ci_contexts"] == ["gitea-actions/*"]


def test_identity_is_the_authentik_jwt_for_the_operator_group():
    env = env_file()
    assert env["OPERATOR_GROUP"] == "root-admins"
    assert env["AUTHENTIK_ISSUER"] == "https://auth.cluster.derio.net/application/o/updates-cluster/"
    assert env["AUTHENTIK_JWKS_URL"] == env["AUTHENTIK_ISSUER"] + "jwks/"
    assert env["AUTHENTIK_AUDIENCE"] == "cluster-update-console"
    assert "PROXY_SECRET_FILE" not in env, "JWT mode only; a shared secret would be a second way in"


def test_links_and_sources_point_at_real_places():
    env = env_file()
    assert env["RUNS_FR_URL"] == "https://sessions.cluster.derio.net"
    assert env["CONSOLE_URL"] == "https://updates.cluster.derio.net"
    assert env["VICTORIALOGS_URL"] == "http://victoria-logs-victoria-logs-single-server.monitoring.svc.cluster.local:9428"
    assert env["LISTEN"] == ":8080" and env["OPS_LISTEN"] == ":9090" and env["SESSION_API_LISTEN"] == ":8081"
    assert env["OMNI_STATUS_FILE"].startswith("/")


# ------------------------------------------------------------------ RBAC


def _bindings_for_sa():
    out = []
    for kind in ("ClusterRoleBinding", "RoleBinding"):
        for b in of_kind(kind):
            if any(s["kind"] == "ServiceAccount" and s["name"] == SA and s["namespace"] == NS
                   for s in b["subjects"]):
                out.append(b)
    return out


def test_cluster_wide_access_is_read_only():
    roles = {r["metadata"]["name"]: r for r in of_kind("ClusterRole")}
    bound = [b for b in _bindings_for_sa() if b["kind"] == "ClusterRoleBinding"]
    assert bound
    seen = set()
    for b in bound:
        assert b["roleRef"]["kind"] == "ClusterRole" and b["roleRef"]["name"] in roles, b["roleRef"]
        for rule in roles[b["roleRef"]["name"]]["rules"]:
            assert set(rule["verbs"]) <= READ_VERBS, rule
            assert "*" not in rule["resources"] + rule["apiGroups"], rule
            seen |= {(g, r) for g in rule["apiGroups"] for r in rule["resources"]}
    assert seen == {
        ("", "pods"), ("", "nodes"), ("argoproj.io", "applications"), ("argoproj.io", "rollouts"),
        ("aquasecurity.github.io", "vulnerabilityreports"),
    }  # exactly what internal/live/live.go lists; workloads and watch are not used (p4-r6)


def test_writes_are_a_namespaced_role_in_upgrade_sessions_on_pods_and_secrets_only():
    bound = [b for b in _bindings_for_sa() if b["kind"] == "RoleBinding"]
    assert len(bound) == 1 and bound[0]["metadata"]["namespace"] == SESSIONS
    roles = {r["metadata"]["name"]: r for r in of_kind("Role") if r["metadata"]["namespace"] == SESSIONS}
    assert bound[0]["roleRef"] == {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role",
                                   "name": bound[0]["roleRef"]["name"]}
    rules = roles[bound[0]["roleRef"]["name"]]["rules"]
    assert len(rules) == 1
    (rule,) = rules
    assert rule["apiGroups"] == [""] and sorted(rule["resources"]) == ["pods", "secrets"]
    assert sorted(rule["verbs"]) == ["create", "delete", "get", "list"]


def test_no_way_to_widen_its_own_access_or_reach_a_shell():
    for r in of_kind("Role") + of_kind("ClusterRole"):
        for rule in r["rules"]:
            joined = " ".join(rule["resources"])
            for banned in ("rolebindings", "roles", "clusterroles", "clusterrolebindings",
                           "pods/exec", "pods/ephemeralcontainers", "pods/attach", "serviceaccounts/token",
                           "*"):
                assert banned not in rule["resources"], (r["metadata"]["name"], joined)
            assert not {"escalate", "bind", "impersonate", "patch", "update", "*"} & set(rule["verbs"]), rule
    names = {b["roleRef"]["name"] for b in _bindings_for_sa()}
    assert not names & {"cluster-admin", "admin", "edit"}, names


# ------------------------------------------------------------------ network lockdown


def _cnp():
    (p,) = [d for d in of_kind("CiliumNetworkPolicy") if d["metadata"]["name"] == "cluster-update-fr"]
    return p


def _ingress_by_port():
    out = {}
    for rule in _cnp()["spec"]["ingress"]:
        assert "fromEntities" not in rule and "fromCIDR" not in rule and "fromCIDRSet" not in rule, rule
        for pp in rule["toPorts"]:
            for p in pp["ports"]:
                out.setdefault(p["port"], []).extend(rule["fromEndpoints"])
    return out


def test_only_traefik_reaches_the_ui_only_vmagent_the_metrics_only_sessions_the_api():
    assert _cnp()["spec"]["endpointSelector"]["matchLabels"] == container_pod_labels()
    by_port = _ingress_by_port()
    assert set(by_port) == {"8080", "9090", "8081"}
    assert by_port["8080"] == [{"matchLabels": {"k8s:io.kubernetes.pod.namespace": "traefik-system",
                                                "app.kubernetes.io/name": "traefik"}}]
    assert by_port["9090"] == [{"matchLabels": {"k8s:io.kubernetes.pod.namespace": "monitoring",
                                                "app.kubernetes.io/name": "vmagent"}}]
    assert by_port["8081"] == [{"matchLabels": {"k8s:io.kubernetes.pod.namespace": SESSIONS}}]


def container_pod_labels():
    labels = deployment()["spec"]["template"]["metadata"]["labels"]
    return {"app.kubernetes.io/name": labels["app.kubernetes.io/name"]}


def test_metrics_are_scraped_from_the_ops_port():
    (scrape,) = of_kind("VMPodScrape")
    ep = scrape["spec"]["podMetricsEndpoints"][0]
    assert ep["port"] == "ops" and ep["path"] == "/metrics"
    assert scrape["spec"]["selector"]["matchLabels"] == container_pod_labels()


# ------------------------------------------------------------------ secrets plumbing


def test_external_secrets_cover_github_gitea_and_telegram():
    names = {e["metadata"]["name"] for e in of_kind("ExternalSecret")}
    assert {"cluster-update-fr-github", "cluster-update-fr-session-github",
            "cluster-update-fr-gitea", "cluster-update-fr-telegram"} <= names
    for e in of_kind("ExternalSecret"):
        assert e["metadata"]["namespace"] == NS
    for g in of_kind("ClusterGenerator"):
        spec = g["spec"]["generator"]["githubAccessTokenSpec"]
        assert spec["appID"].startswith("PENDING") and spec["installID"].startswith("PENDING")
        assert spec["permissions"].get("administration") is None


def test_the_session_app_is_separate_from_the_console_app_and_scoped_to_frank():
    gens = {g["metadata"]["name"]: g["spec"]["generator"]["githubAccessTokenSpec"] for g in of_kind("ClusterGenerator")}
    assert set(gens) == {"github-app-cluster-update-console", "github-app-cluster-update-session"}
    for spec in gens.values():
        assert spec["repositories"] == ["frank"]
    assert set(gens["github-app-cluster-update-session"]["permissions"]) == {"contents", "pull_requests", "metadata"}
    assert gens["github-app-cluster-update-session"]["auth"]["privateKey"]["secretRef"]["name"] \
        != gens["github-app-cluster-update-console"]["auth"]["privateKey"]["secretRef"]["name"]


# ------------------------------------------------------------------ exposure


def _ingress_routes():
    path = ROOT / "apps/traefik/manifests/ingressroutes.yaml"
    return {d["metadata"]["name"]: d for d in yaml.safe_load_all(path.read_text()) if d}


def test_both_hosts_sit_behind_forward_auth_to_clusterip_services():
    routes = _ingress_routes()
    for name, host, svc, ns, port in (
        ("cluster-update-fr", "updates.cluster.derio.net", "cluster-update-fr", NS, 8080),
        ("runs-fr", "sessions.cluster.derio.net", "runs-fr", "runs-fr", 80),
    ):
        (route,) = routes[name]["spec"]["routes"]
        assert route["match"] == f"Host(`{host}`)"
        mids = [m["name"] for m in route["middlewares"]]
        assert "authentik-forwardauth" in mids and "security-headers" in mids
        assert [(s["name"], s["namespace"], s["port"]) for s in route["services"]] == [(svc, ns, port)]
    # the UI route must never reach the session API or metrics
    assert env_file()["LISTEN"] == ":8080"


def _blueprint():
    cm = yaml.safe_load((ROOT / "apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml").read_text())
    return cm["data"]["cluster-proxy-providers.yaml"]


def test_authentik_providers_forward_single_and_restricted_to_the_operator_group():
    text = _blueprint()
    for name, host, slug in (("Cluster Update Console (cluster)", "updates.cluster.derio.net", "updates-cluster"),
                             ("Upgrade Sessions (cluster)", "sessions.cluster.derio.net", "sessions-cluster")):
        block = text.split(f"name: {name}\n", 1)[1].split("- model: authentik_providers_proxy", 1)[0]
        assert "mode: forward_single" in block and f"external_host: https://{host}" in block
        assert "invalidation_flow" in block
        assert f"slug: {slug}" in text
    assert "client_id: cluster-update-console" in text, "the audience the console verifies"
    assert text.count("model: authentik_policies.policybinding") >= 2
    bindings = text.split("model: authentik_policies.policybinding")[1:]
    for slug_id in ("app-updates-cluster", "app-sessions-cluster"):
        assert any(f"!KeyOf {slug_id}" in b.split("- model:")[0] and "root-admins" in b.split("- model:")[0]
                   for b in bindings), slug_id
    updates = text.split("name: Cluster Update Console (cluster)\n", 1)[1].split("- model: authentik_core.application", 1)[0]
    assert "signing_key" in updates, "the console verifies an asymmetric JWT"


def test_the_jwt_header_is_forwarded_by_the_middleware():
    docs_ = list(yaml.safe_load_all((ROOT / "apps/traefik/manifests/middlewares.yaml").read_text()))
    fwd = next(d for d in docs_ if d and d["metadata"]["name"] == "authentik-forwardauth")
    headers = fwd["spec"]["forwardAuth"]["authResponseHeaders"]
    assert "X-authentik-jwt" in headers and "X-authentik-username" in headers


def test_homepage_has_both_tiles():
    text = (ROOT / "apps/homepage/manifests/files/services.yaml").read_text()
    for host in ("updates.cluster.derio.net", "sessions.cluster.derio.net"):
        assert f"href: https://{host}" in text


# ------------------------------------------------------------------ update path and CI for the console repo


def test_console_and_runs_fr_take_the_session_path():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import life_policy

    policy = life_policy.load_policy()
    for app in ("frank/cluster-update-fr", "frank/runs-fr"):
        for update in ("patch", "minor", "major"):
            assert life_policy.resolve({"app": app}, update, policy) == "session", (app, update)
    rule = next(r for r in policy["rules"] if r["match"].get("image") == "ghcr.io/derio-net/upgrade-session")
    assert rule["path"] == "session"


def test_the_console_repo_is_mirrored_bridged_and_declared_trigger_first():
    repo = "derio-net/cluster-update-fr"
    listener = (ROOT / "apps/tekton/triggers/eventlistener.yaml").read_text()
    github = (ROOT / "apps/tekton/triggers/eventlistener-github.yaml").read_text()
    assert listener.count(f"'{repo}'") == 1, "status bridge allowlist"
    assert github.count(f"'{repo}'") == 2, "derio-net main-sync + pr-sync"
    decl = yaml.safe_load((ROOT / "apps/tekton/webhooks.yaml").read_text())["webhooks"]
    (entry,) = [w for w in decl if w["target"] == repo]
    assert entry["forge"] == "github" and set(entry["events"]) == {"push", "pull_request"}
    assert "TRIGGER-FIRST" in entry["note"]
    tiers = yaml.safe_load((ROOT / "apps/ci-budget/tiers.yaml").read_text())
    assert tiers["orgs"]["derio-net"]["repos"]["cluster-update-fr"]["tier"] == "github-preferred"


# ------------------------------------------------------------------ p4-sec-1: what protects main


PLAN = ROOT / "docs/superpowers/plans/2026-10-31--life--update-security-lifecycle"


def test_session_app_comment_does_not_claim_a_control_that_is_not_in_git():
    text = (MAN / "clustergenerators.yaml").read_text()
    assert "cannot merge, so" not in text
    assert "ruleset" in text and "cluster-update/approved" in text, "name the control that actually protects main"
    assert "phase 7" in text.lower(), "and say it is a manual step, not code in this repo"


def test_phase_7_creates_the_main_ruleset_with_the_console_only_check():
    plan = yaml.safe_load((PLAN / "07.yaml").read_text())
    steps = {s["id"]: s["text"] for t in plan["tasks"] for s in t["steps"]}
    text = steps["P7.T1.S5"]
    for needle in ("main", "cluster-update/approved", "console App", "force", "deletion", "session App"):
        assert needle in text, needle
    assert "P7.T1.S5" in plan["state"]["steps"]
    prose = (PLAN / "_prose.md").read_text()
    assert "id: life-main-ruleset" in prose


# ------------------------------------------------------------------ p4-sec-2: what the console may launch

CONSOLE_USER = "system:serviceaccount:cluster-update-fr:cluster-update-fr"


def vap(name):
    (p,) = [d for d in of_kind("ValidatingAdmissionPolicy") if d["metadata"]["name"] == name]
    (b,) = [d for d in of_kind("ValidatingAdmissionPolicyBinding") if d["spec"]["policyName"] == name]
    return p, b


def _all_expressions(p):
    return " ".join(v["expression"] for v in p["spec"]["validations"])


def test_pods_the_console_creates_are_confined_by_an_admission_policy():
    p, b = vap("upgrade-session-pods")
    assert b["spec"]["validationActions"] == ["Deny"]
    assert b["spec"]["matchResources"]["namespaceSelector"]["matchLabels"] == {
        "kubernetes.io/metadata.name": SESSIONS}
    (rule,) = p["spec"]["matchConstraints"]["resourceRules"]
    assert rule["resources"] == ["pods"] and set(rule["operations"]) == {"CREATE", "UPDATE"}
    assert p["spec"]["failurePolicy"] == "Fail"
    conds = " ".join(c["expression"] for c in p["spec"]["matchConditions"])
    assert CONSOLE_USER in conds
    expr = _all_expressions(p) + " " + " ".join(v["expression"] for v in p["spec"]["variables"])
    for needle in (
        "upgrade-session-", "'hop-os'", "serviceAccountName", "automountServiceAccountToken",
        "ghcr.io/derio-net/upgrade-session:", "ghcr.io/derio-net/upgrade-session@sha256:",
        "app.kubernetes.io/managed-by", "cluster-update-fr", "cluster-update.fr/type",
        "hostPath", "hostNetwork", "hostPID", "hostIPC", "privileged", "capabilities", "ephemeralContainers",
        "initContainers",
    ):
        assert needle in expr, needle
    for t in ("chart-major", "stateful", "rollouts", "frank-os", "hop-os"):
        assert f"'{t}'" in expr, t


def test_the_session_image_prefix_cannot_be_spoofed_by_a_longer_name():
    p, _ = vap("upgrade-session-pods")
    expr = _all_expressions(p)
    assert "startsWith('ghcr.io/derio-net/upgrade-session')" not in expr, "needs the : or @ delimiter"


def test_nobody_but_cluster_admin_may_add_ephemeral_containers_to_session_pods():
    p, b = vap("upgrade-session-no-ephemeral-containers")
    assert b["spec"]["validationActions"] == ["Deny"]
    assert b["spec"]["matchResources"]["namespaceSelector"]["matchLabels"] == {
        "kubernetes.io/metadata.name": SESSIONS}
    (rule,) = p["spec"]["matchConstraints"]["resourceRules"]
    assert rule["resources"] == ["pods/ephemeralcontainers"]
    conds = " ".join(c["expression"] for c in p["spec"]["matchConditions"])
    assert "system:masters" in conds and "root-admins" in conds
    assert [v["expression"] for v in p["spec"]["validations"]] == ["false"]


def test_secrets_list_stays_only_for_orphan_reconciliation_and_says_so():
    text = (MAN / "rbac.yaml").read_text()
    assert "orphan" in text and "list" in text.split("orphan", 1)[0][-600:] + text.split("orphan", 1)[1][:600]


# ------------------------------------------------------------------ p4-r9: the API token only reaches the console


def test_the_service_account_token_is_mounted_only_in_the_console_container():
    assert pod()["automountServiceAccountToken"] is False
    vol = next(v for v in pod()["volumes"] if "projected" in v and any(
        "serviceAccountToken" in s for s in v["projected"]["sources"]))
    mounts = {c["name"]: [m for m in c.get("volumeMounts", []) if m["name"] == vol["name"]]
              for c in pod()["containers"] + pod().get("initContainers", [])}
    assert [m["mountPath"] for m in mounts["console"]] == ["/var/run/secrets/kubernetes.io/serviceaccount"]
    assert mounts["console"][0]["readOnly"] is True
    assert all(not m for name, m in mounts.items() if name != "console"), mounts


def test_session_secrets_are_confined_by_an_admission_policy():
    p, b = vap("upgrade-session-secrets")
    assert b["spec"]["validationActions"] == ["Deny"]
    assert b["spec"]["matchResources"]["namespaceSelector"]["matchLabels"] == {
        "kubernetes.io/metadata.name": SESSIONS}
    (rule,) = p["spec"]["matchConstraints"]["resourceRules"]
    assert rule["resources"] == ["secrets"] and set(rule["operations"]) == {"CREATE", "UPDATE"}
    assert CONSOLE_USER in p["spec"]["matchConditions"][0]["expression"]
    expr = _all_expressions(p)
    for needle in ("'Opaque'", "startsWith('us-')", "app.kubernetes.io/managed-by", "kubernetes.io/service-account.name"):
        assert needle in expr, needle


# ------------------------------------------------------------------ p4-r4: Omni's running version


def test_an_omni_status_sidecar_writes_the_file_the_console_reads():
    side = next(c for c in pod()["containers"] if c["name"] == "omni-status")
    assert side["image"].startswith("ghcr.io/derio-net/upgrade-session:"), "the image that ships omnictl"
    assert side["command"][:2] == ["/bin/sh", "-c"]
    body = " ".join(side["command"][1:] + side.get("args", []))
    assert "omnictl get sysversion -o json" in body
    assert "mv " in body, "atomic replace, so the console never reads a half-written file"
    status = env_file()["OMNI_STATUS_FILE"]
    assert status in body, "writes exactly the path the console is told to read"
    env = {e["name"]: e for e in side["env"]}
    assert env["OMNICONFIG"]["value"].startswith("/var/run/omni/")
    s = side["securityContext"]
    assert s["readOnlyRootFilesystem"] is True and s["allowPrivilegeEscalation"] is False
    assert s["capabilities"]["drop"] == ["ALL"]
    # its own scratch, the shared status dir read-write here and READ-ONLY in the console
    mounts = {m["name"]: m for m in side["volumeMounts"]}
    cmounts = {m["name"]: m for m in container()["volumeMounts"]}
    assert mounts["omni-status"].get("readOnly") is not True
    assert cmounts["omni-status"]["readOnly"] is True
    assert cmounts["omni-status"]["mountPath"] == status.rsplit("/", 1)[0]
    assert "tmp" not in mounts or mounts["tmp"]["name"] != "tmp", "must not share the console's /tmp"
    cred = next(v for v in pod()["volumes"] if v["name"] == mounts["omni-reader"]["name"])
    assert cred["secret"]["optional"] is True
    assert "omni-reader" not in cmounts, "the Reader credential belongs to the sidecar alone"
