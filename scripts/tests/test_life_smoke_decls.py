"""Every Application declares a smoke test in git that exercises the real service (spec R17)."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import life_policy  # noqa: E402

SMOKE = ROOT / "smoke"
KINDS = {"http", "tcp", "exec-probe", "functional"}


def _apps():
    return [tuple(k.split("/")) for k in life_policy.app_keys()]


def load(cluster, app):
    path = SMOKE / cluster / f"{app}.yaml"
    assert path.exists(), f"missing smoke declaration {path.relative_to(ROOT)}"
    return yaml.safe_load(path.read_text())


def test_every_application_has_a_valid_declaration():
    for cluster, app in _apps():
        decl = load(cluster, app)
        assert decl["app"] == app and decl["cluster"] == cluster, (cluster, app)
        assert decl["checks"], (cluster, app)
        for check in decl["checks"]:
            assert check["kind"] in KINDS, (app, check)
            assert check["target"] and check["expect"], (app, check)
            if check["kind"] == "http":
                assert "status" in check["expect"], (app, check)
            if check["kind"] == "exec-probe":
                assert check.get("reason", "").strip(), f"{app}: exec-probe needs a reason"


def test_no_declaration_is_orphaned():
    wanted = {f"{c}/{a}.yaml" for c, a in _apps()}
    have = {str(p.relative_to(SMOKE)) for p in SMOKE.glob("*/*.yaml")}
    assert have == wanted, sorted(have ^ wanted)


def _kinds(cluster, app):
    return [c["kind"] for c in load(cluster, app)["checks"]]


def test_functional_checks_where_it_matters():
    def functional(app):
        return [c for c in load("frank", app)["checks"] if c["kind"] == "functional"]

    (chat,) = functional("litellm")
    assert "chat/completions" in chat["target"] and chat["request"]["model"].startswith("gemma")
    (objinfo,) = functional("comfyui")
    assert objinfo["target"].endswith("/object_info")
    ovms = {c["target"].rsplit("/", 2)[-2] for c in functional("ovms-retrieval")}
    assert ovms == {"bge-m3", "bge-reranker-v2-m3"}
    for c in functional("ovms-retrieval"):
        assert "/v2/models/" in c["target"] and c["target"].endswith("/ready")
    dash = [c for c in functional("victoria-metrics") if "dashboards" in c["name"]]
    assert dash and dash[0]["expect"]["json_min_length"] >= 1
    (apps,) = functional("argocd")
    assert "applications.argoproj.io" in apps["target"]


def test_ovms_functional_checks_name_every_servable():
    text = (ROOT / "apps/ovms-retrieval/manifests/deployment.yaml").read_text()
    for c in yaml.safe_load((SMOKE / "frank/ovms-retrieval.yaml").read_text())["checks"]:
        assert c["target"].rsplit("/", 2)[-2] in text


def test_hop_public_services_check_their_public_url():
    for app in ("blog", "www", "headscale", "caddy", "landing", "headplane"):
        urls = [c["target"] for c in load("hop", app)["checks"] if c["kind"] == "http"]
        assert any(u.startswith("https://") and u.split("/")[2].endswith("derio.net") for u in urls), app
    for app in ("blog", "www", "headscale"):
        assert any(c.get("public") for c in load("hop", app)["checks"]), app


def test_in_cluster_targets_are_well_formed_and_name_a_rendered_service():
    import re

    facts = life_policy.load_facts()
    services = {(s["name"], s["namespace"]) for f in facts.values() for s in f["services"]}
    for cluster, app in _apps():
        for c in load(cluster, app)["checks"]:
            t = c["target"]
            assert not re.search(r"None|\{\{|\$", t), t
            m = re.search(r"(?:https?://)?([\w.-]+)\.([\w-]+)\.svc\.cluster\.local", t)
            if m:
                assert (m.group(1), m.group(2)) in services, f"{app}: {t} names no rendered Service"


def test_http_checks_expect_one_status_and_never_accept_auth_walls():
    seen = {}
    for cluster, app in _apps():
        for c in load(cluster, app)["checks"]:
            if c["kind"] != "http":
                continue
            status = c["expect"]["status"]
            statuses = status if isinstance(status, list) else [status]
            assert 1 <= len(statuses) <= 2, (app, status)
            assert not set(statuses) & {401, 403, 404}, f"{app}: {status} proves reachability, not health"
            for h in c["expect"].get("headers", {}):
                assert h == h.lower()
            seen[app] = c["target"]
    assert seen["argocd"].startswith("http://argocd-server."), "not the applicationset-controller"
    assert seen["authentik"].endswith("/-/health/ready/")
