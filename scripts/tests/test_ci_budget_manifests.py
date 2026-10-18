"""Guard: the ci-budget-watcher manifests (spec 2026-10-18 section 4)."""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps/ci-budget"

APPS = {
    "derio-net": ("3994132", "138773908", "github-app-derio-key"),
    "derio-homelab": ("4403773", "149345112", "github-app-homelab-key"),
    "agentic-stoa": ("3994156", "138773982", "github-app-stoa-key"),
}
BILLING_PERMS = {"organization_administration": "read", "metadata": "read"}
AUTHORITY_PERMS = {
    "variables": "write", "actions": "read", "checks": "read",
    "contents": "read", "metadata": "read",
}


def _docs(name):
    return [d for d in yaml.safe_load_all((APP / name).read_text()) if d]


def _all_docs():
    out = []
    for p in sorted(APP.glob("*.yaml")):
        if p.name in ("kustomization.yaml", "tiers.yaml"):
            continue
        out += _docs(p.name)
    return out


def _kind(kind, name=None):
    hits = [d for d in _all_docs() if d["kind"] == kind and (name is None or d["metadata"]["name"] == name)]
    assert hits, f"no {kind} {name}"
    return hits


def _cronjob():
    return _kind("CronJob", "ci-budget-watcher")[0]


def _pod():
    return _cronjob()["spec"]["jobTemplate"]["spec"]["template"]["spec"]


def _tiers():
    return yaml.safe_load((APP / "tiers.yaml").read_text())


def test_cronjob_shape():
    cj = _cronjob()
    assert cj["spec"]["schedule"] == "*/10 * * * *"
    assert cj["spec"]["concurrencyPolicy"] == "Forbid"
    assert cj["metadata"]["namespace"] == "tekton-pipelines"


def test_images_pinned_by_digest_and_hardened():
    pod = _pod()
    assert pod["securityContext"]["runAsNonRoot"] is True
    for c in pod["initContainers"] + pod["containers"]:
        assert re.fullmatch(r"python:3[\w.\-]*@sha256:[0-9a-f]{64}", c["image"]), c["image"]
        sc = c["securityContext"]
        assert sc["readOnlyRootFilesystem"] is True
        assert sc["allowPrivilegeEscalation"] is False
        assert sc["capabilities"]["drop"] == ["ALL"]


def test_pyyaml_installed_by_init_container_from_hash_pinned_requirement():
    pod = _pod()
    (init,) = pod["initContainers"]
    cmd = " ".join(init["command"] + init.get("args", []))
    assert "--require-hashes" in cmd and "--target" in cmd and "--only-binary" in cmd
    assert "requirements.txt" in cmd
    req = (APP / "files/requirements.txt").read_text()
    assert re.search(r"^pyyaml==\d", req, re.M | re.I)
    assert re.search(r"--hash=sha256:[0-9a-f]{64}", req)
    # every requirement line is pinned with a hash
    for line in re.sub(r"\\\n", " ", req).splitlines():
        if line.strip() and not line.startswith("#"):
            assert "==" in line and "--hash=sha256:" in line, line
    main = pod["containers"][0]
    env = {e["name"]: e.get("value") for e in main["env"]}
    deps = [m["mountPath"] for m in main["volumeMounts"] if m["name"] == "deps"]
    assert deps and deps[0] in env["PYTHONPATH"].split(":")
    assert any(v["name"] == "deps" and "emptyDir" in v for v in pod["volumes"])


def test_secrets_are_optional_and_named():
    main = _pod()["containers"][0]
    refs = {
        e["valueFrom"]["secretKeyRef"]["name"]: e["valueFrom"]["secretKeyRef"]
        for e in main["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
    }
    for n in ("ci-budget-gitea", "ci-budget-gitea-probe", "ci-budget-telegram"):
        assert n in refs, n
    assert all(r.get("optional") is True for r in refs.values())


def test_every_generator_has_a_consumed_token_secret():
    main = _pod()["containers"][0]
    consumed = {
        (e["name"], e["valueFrom"]["secretKeyRef"]["name"])
        for e in main["env"] if e["name"].startswith("GH_")
    }
    es = {d["spec"]["target"]["name"]: d for d in _kind("ExternalSecret")}
    for kind in ("BILLING", "AUTHORITY"):
        for org in APPS:
            key = org.upper().replace("-", "_")
            if kind == "AUTHORITY" and org == "agentic-stoa":
                continue
            name = f"GH_{kind}_TOKEN_{key}"
            secrets = [s for n, s in consumed if n == name]
            assert len(secrets) == 1, name
            assert secrets[0] in es, secrets[0]


def test_script_ships_in_config_map_generator_and_matches_the_checker_byte_for_byte():
    k = yaml.safe_load((APP / "kustomization.yaml").read_text())
    files = {f for g in k["configMapGenerator"] for f in g["files"]}
    assert {"files/watcher.py", "files/ci_gate_coverage.py", "files/requirements.txt", "tiers.yaml"} <= files
    assert (APP / "files/ci_gate_coverage.py").read_bytes() == (REPO / "scripts/ci_gate_coverage.py").read_bytes()
    assert (APP / "files/runner-config.yaml").read_bytes() == (
        REPO / "apps/gitea-runner/manifests/files/config.yaml"
    ).read_bytes()
    assert "files/runner-config.yaml" in files


def _generators():
    return {d["metadata"]["name"]: d["spec"]["generator"]["githubAccessTokenSpec"] for d in _kind("ClusterGenerator")}


def test_billing_generators_have_no_repositories():
    gens = _generators()
    for org, (app_id, install_id, key) in APPS.items():
        g = gens[f"github-app-{org}-ci-billing"]
        assert g["permissions"] == BILLING_PERMS
        assert "repositories" not in g
        assert (g["appID"], g["installID"]) == (app_id, install_id)
        assert g["auth"]["privateKey"]["secretRef"] == {"name": key, "key": "key"}


def test_authority_generators_scoped_to_the_orgs_tier_repos():
    gens = _generators()
    tiers = _tiers()["orgs"]
    for org in ("derio-net", "derio-homelab"):
        g = gens[f"github-app-{org}-ci-authority"]
        assert g["permissions"] == AUTHORITY_PERMS
        assert sorted(g["repositories"]) == sorted(tiers[org]["repos"])
        assert (g["appID"], g["installID"]) == APPS[org][:2]
    assert "github-app-agentic-stoa-ci-authority" not in gens
    assert len(gens) == 5


def test_external_secrets_reference_their_generators():
    gens = _generators()
    for d in _kind("ExternalSecret"):
        assert d["metadata"]["namespace"] == "tekton-pipelines"
        ref = d["spec"]["dataFrom"][0]["sourceRef"]["generatorRef"]
        assert ref["kind"] == "ClusterGenerator" and ref["name"] in gens
        assert d["spec"]["refreshInterval"] in ("30m", "45m")
    assert len(_kind("ExternalSecret")) == 5


def test_role_limited_to_the_state_configmap():
    (role,) = _kind("Role", "ci-budget-watcher")
    named = [r for r in role["rules"] if r.get("resourceNames")]
    assert named == [{"apiGroups": [""], "resources": ["configmaps"],
                      "resourceNames": ["ci-budget-state"], "verbs": ["get", "patch", "update"]}]
    # RBAC cannot restrict `create` by name, so it is the one unnamed verb
    rest = [r for r in role["rules"] if not r.get("resourceNames")]
    assert rest == [{"apiGroups": [""], "resources": ["configmaps"], "verbs": ["create"]}]
    (rb,) = _kind("RoleBinding", "ci-budget-watcher")
    assert rb["subjects"][0]["name"] == "ci-budget-watcher"
    assert _pod()["serviceAccountName"] == "ci-budget-watcher"


def test_no_other_generator_grants_billing_or_variables():
    offenders = []
    for p in (REPO / "apps").rglob("*.yaml"):
        if APP in p.parents or "vendor" in p.parts:
            continue
        try:
            docs = list(yaml.safe_load_all(p.read_text()))
        except yaml.YAMLError:
            continue
        for d in docs:
            if not isinstance(d, dict) or d.get("kind") != "ClusterGenerator":
                continue
            perms = (d["spec"]["generator"].get("githubAccessTokenSpec") or {}).get("permissions") or {}
            if {"organization_administration", "variables"} & set(perms):
                offenders.append(str(p.relative_to(REPO)))
    assert offenders == []


CM = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
RULE_UID = "ci-budget-heartbeat-stale"


def _rule(uid=RULE_UID):
    cm = yaml.safe_load(CM.read_text())
    for blob in cm["data"].values():
        for grp in yaml.safe_load(blob).get("groups", []):
            for rule in grp.get("rules", []):
                if rule["uid"] == uid:
                    return grp, rule
    raise AssertionError(f"rule {uid} not found")


def _expr(rule):
    return next(d for d in rule["data"] if d["refId"] == "A")["model"]["expr"]


def _container():
    return _pod()["containers"][0]["name"]


def test_heartbeat_rule_is_a_scoped_frank_dead_mans_switch():
    grp, rule = _rule()
    assert len(RULE_UID) <= 40
    assert grp["folder"] == "feature-health"
    a, b, c = (next(d for d in rule["data"] if d["refId"] == r) for r in "ABC")
    assert a["model"]["queryType"] == "stats"
    expr = a["model"]["expr"]
    assert "stats count() as value" in expr and "by (" not in expr
    assert expr == (
        "kubernetes.namespace_name:tekton-pipelines AND "
        f"kubernetes.container_name:{_container()} AND "
        "kubernetes.pod_name:ci-budget-watcher* AND "
        '_msg:"ci-budget-watcher verdict" AND NOT _msg:"verdict=error" | stats count() as value'
    )
    assert a["relativeTimeRange"]["from"] == 2400
    assert c["model"]["conditions"][0]["evaluator"] == {"type": "lt", "params": [1]}
    assert rule["noDataState"] == "OK"
    assert rule["labels"]["telegram_direct"] == "true"
    assert rule["labels"]["severity"] == "critical"


def test_erroring_rule_pages_on_repeated_error_verdicts():
    uid = "ci-budget-watcher-erroring"
    grp, rule = _rule(uid)
    assert len(uid) <= 40
    assert grp["folder"] == "feature-health"
    assert _expr(rule) == (
        "kubernetes.namespace_name:tekton-pipelines AND "
        f"kubernetes.container_name:{_container()} AND "
        "kubernetes.pod_name:ci-budget-watcher* AND "
        '_msg:"ci-budget-watcher verdict=error" | stats count() as value'
    )
    c = next(d for d in rule["data"] if d["refId"] == "C")
    assert c["model"]["conditions"][0]["evaluator"] == {"type": "gt", "params": [3]}
    assert next(d for d in rule["data"] if d["refId"] == "A")["relativeTimeRange"]["from"] == 2400
    assert rule["noDataState"] == "OK"
    assert rule["labels"]["telegram_direct"] == "true"


def _terms(expr):
    """(required substrings, forbidden substrings) from the _msg terms."""
    import re as _re
    msg = [(m.group(1) == "NOT ", m.group(2)) for m in _re.finditer(r'(NOT )?_msg:"([^"]+)"', expr)]
    return [t for n, t in msg if not n], [t for n, t in msg if n]


def _watcher():
    import importlib.util, sys
    sys.path.insert(0, str(APP / "files"))
    try:
        spec = importlib.util.spec_from_file_location("watcher_for_rule", APP / "files/watcher.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        sys.path.remove(str(APP / "files"))
    return m


def test_lines_the_watcher_prints_satisfy_the_rule_terms():
    w = _watcher()

    class Boom:
        def billing_usage(self, *a):
            raise RuntimeError("403")

        public_repos = list_failed_runs = billing_usage

    class Gitea:
        def get_org_var(self, *a):
            return None

    from datetime import datetime, timezone
    cfg = {"included_minutes": 2000, "threshold_pct": 85, "gitea_org": "o", "mode": "dry-run", "repos": {}}
    ok, bad = [], []

    class Ok:
        def billing_usage(self, *a):
            return []

        def public_repos(self, *a):
            return set()

    now = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
    w.run_org("o", cfg, Ok(), Gitea(), {}, now, type("N", (), {"enabled": False})(), set(), log=ok.append)
    w.run_org("o", cfg, Boom(), Gitea(), {}, now, type("N", (), {"enabled": False})(), set(), log=bad.append)
    beat_req, beat_forbid = _terms(_expr(_rule()[1]))
    err_req, _ = _terms(_expr(_rule("ci-budget-watcher-erroring")[1]))
    healthy = [l for l in ok if "verdict=" in l]
    errors = [l for l in bad if "verdict=" in l]
    assert len(healthy) == 1 and len(errors) == 1
    assert all(t in healthy[0] for t in beat_req) and not any(t in healthy[0] for t in beat_forbid)
    # an erroring run is NOT a heartbeat, and is what the erroring rule counts
    assert any(t in errors[0] for t in beat_forbid)
    assert all(t in errors[0] for t in err_req)
