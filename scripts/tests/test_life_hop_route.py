"""Frank reaches Hop over the tailnet to scan its images (spec: Reaching Hop, R8)."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HEADSCALE_CM = ROOT / "clusters/hop/apps/headscale/manifests/configmap.yaml"
MAN = ROOT / "apps/hop-scan/manifests"
TEMPLATE = ROOT / "apps/root/templates/hop-scan.yaml"

# The ACL as it was before this plan. The edit must leave every one of these untouched.
OLD_ACLS = [{"action": "accept", "src": ["default", "tag:subnet-router", "tag:hop-node"], "dst": ["*:*"]}]
OLD_DST = ["*:*"]
OLD_TAG_OWNERS = {"tag:subnet-router": ["default"]}
OLD_AUTO_APPROVERS = {
    "routes": {
        "192.168.10.0/24": ["tag:subnet-router"],
        "192.168.50.0/24": ["tag:subnet-router"],
        "192.168.55.0/24": ["tag:subnet-router"],
    },
    "exitNode": ["tag:subnet-router"],
}


def acl():
    cm = yaml.safe_load(HEADSCALE_CM.read_text())
    text = cm["data"]["acl.yaml"]
    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("//"))
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


def docs():
    out = []
    for f in sorted(MAN.glob("*.yaml")):
        if f.name == "kustomization.yaml":
            continue
        out += [d for d in yaml.safe_load_all(f.read_text()) if d]
    return out


def of(kind):
    return [d for d in docs() if d["kind"] == kind]


def test_old_acl_entries_are_unchanged():
    a = acl()
    assert a["acls"][: len(OLD_ACLS)] == OLD_ACLS
    for tag, owners in OLD_TAG_OWNERS.items():
        assert a["tagOwners"][tag] == owners
    assert a["autoApprovers"] == OLD_AUTO_APPROVERS


NEW_TAGS = {"tag:frank-updater", "tag:frank-session"}


def _grant(tag):
    (entry,) = [r for r in acl()["acls"][len(OLD_ACLS):] if r["src"] == [tag]]
    return entry


def test_the_edit_is_minimal_two_entries_and_three_owners():
    a = acl()
    new = a["acls"][len(OLD_ACLS):]
    assert len(new) == 2
    assert {tuple(r["src"]) for r in new} == {(t,) for t in NEW_TAGS}
    assert set(a["tagOwners"]) - set(OLD_TAG_OWNERS) == NEW_TAGS | {"tag:hop-node"}


def test_frank_updater_reaches_only_hop_kube_api():
    entry = _grant("tag:frank-updater")
    assert entry["action"] == "accept"
    assert entry["dst"] == ["tag:hop-node:6443"], "the scanner needs only the kube API"
    assert acl()["tagOwners"]["tag:frank-updater"], "the tag needs an owner"


def test_frank_session_reaches_only_hop_kube_and_talos_apis():
    # p5-r3: hop-os sessions upgrade Hop's Talos and Kubernetes; they join as their OWN tag so
    # the scanner's 6443-only grant stays narrow and a session never borrows it.
    entry = _grant("tag:frank-session")
    assert entry["action"] == "accept"
    assert entry["dst"] == ["tag:hop-node:6443,50000"]
    assert acl()["tagOwners"]["tag:frank-session"] == ["group:tag-admins"]


def test_application_is_a_frank_path_app_in_its_own_namespace():
    text = TEMPLATE.read_text()
    assert "path: apps/hop-scan/manifests" in text
    spec = yaml.safe_load(text.replace("{{ .Values.repoURL }}", "x").replace(
        "{{ .Values.targetRevision }}", "main").replace("{{ .Values.destination.server }}", "s"))["spec"]
    assert spec["destination"]["namespace"] == "hop-scan"
    assert "ServerSideApply=true" in spec["syncPolicy"]["syncOptions"]
    assert not spec["syncPolicy"]["automated"].get("prune", False)
    assert {d["kind"] for d in docs()} >= {"Namespace", "CronJob", "NetworkPolicy"}


def _cronjob():
    (cj,) = of("CronJob")
    return cj, cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]


def _all_containers(pod):
    return pod.get("initContainers", []) + pod["containers"]


def test_cronjob_is_daily_and_takes_no_service_account_token():
    cj, pod = _cronjob()
    sched = cj["spec"]["schedule"].split()
    assert sched[2:] == ["*", "*", "*"] and sched[0].isdigit() and sched[1].isdigit(), "daily"
    assert cj["spec"]["concurrencyPolicy"] == "Forbid"
    assert pod["automountServiceAccountToken"] is False, "RBAC none"
    assert not of("Role") and not of("ClusterRole") and not of("RoleBinding")
    assert pod["restartPolicy"] == "Never"


def test_userspace_tailscale_sidecar_degrades_before_phase_7():
    _, pod = _cronjob()
    (ts,) = [c for c in _all_containers(pod) if c["name"] == "tailscale"]
    assert ts.get("restartPolicy") == "Always", "native sidecar so the Job can finish"
    assert ts["image"].startswith("tailscale/tailscale:v") or "/tailscale:" in ts["image"]
    env = {e["name"]: e for e in ts["env"]}
    assert env["TS_USERSPACE"]["value"] == "true"
    key = env["TS_AUTHKEY"]["valueFrom"]["secretKeyRef"]
    assert (key["name"], key["key"], key["optional"]) == ("frank-updater-tailscale", "authkey", True)
    assert "--advertise-tags=tag:frank-updater" in env["TS_EXTRA_ARGS"]["value"]
    assert "--login-server=https://headscale.hop.derio.net" in env["TS_EXTRA_ARGS"]["value"]
    assert env["TS_SOCKS5_SERVER"]["value"].startswith("localhost:")
    assert env["TS_KUBE_SECRET"]["value"] == "", "no in-cluster Secret state: the pod has no RBAC"


def test_lists_hop_pods_with_an_optional_read_only_kubeconfig():
    _, pod = _cronjob()
    vols = {v["name"]: v for v in pod["volumes"]}
    sec = [v for v in vols.values() if v.get("secret", {}).get("secretName") == "hop-readonly-kubeconfig"]
    assert sec and sec[0]["secret"]["optional"] is True
    (lister,) = [c for c in _all_containers(pod) if c["name"] == "list-images"]
    script = "\n".join(lister["command"] + lister.get("args", []))
    assert "get pods" in script and "-A" in script
    assert not re.search(r"\b(apply|create|delete|patch|edit|exec)\b", script)
    env = {e["name"]: e.get("value") for e in lister["env"]}
    assert env["HTTPS_PROXY"].startswith("socks5")


def test_scans_each_distinct_image_against_the_shared_trivy_server():
    _, pod = _cronjob()
    (scan,) = [c for c in _all_containers(pod) if c["name"] == "scan"]
    script = "\n".join(scan["command"] + scan.get("args", []))
    assert "trivy image" in script
    assert "--server http://trivy-service.trivy-system:4954" in script
    assert "sort -u" in script or "uniq" in script, "distinct images"
    assert not any(e["name"].lower().endswith("_proxy") for e in scan.get("env", [])), \
        "the scanner must reach the in-cluster server directly, not via the tailnet proxy"


def test_results_are_prefixed_json_lines_on_stdout():
    _, pod = _cronjob()
    (rep,) = [c for c in pod["containers"] if c["name"] == "report"]
    cm = [d for d in of("ConfigMap")]
    kust = yaml.safe_load((MAN / "kustomization.yaml").read_text())
    files = [f for g in kust["configMapGenerator"] for f in g["files"]]
    src = (MAN / files[0].split("=")[-1]).read_text()
    assert 'print("hop-scan result " + json.dumps(' in src
    for field in ("cluster", "image", "scanned_at", "error"):
        assert f'"{field}"' in src
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"):
        assert f'"{sev}"' in src
    assert 'print("hop-scan heartbeat ' in src, "dead-man line even when nothing could be scanned"
    assert rep["image"].startswith("python:")
    assert not cm  # script ships via the generator, not a hand-written ConfigMap


def test_networkpolicy_limits_egress():
    (np,) = of("NetworkPolicy")
    assert np["spec"]["podSelector"] == {} or np["spec"]["podSelector"]["matchLabels"]
    assert "Egress" in np["spec"]["policyTypes"]
    assert "ingress" not in np["spec"] or np["spec"]["ingress"] == []
    rules = json.dumps(np["spec"]["egress"])
    assert "trivy-system" in rules and "4954" in rules
    assert "53" in rules  # DNS
    assert "3478" in rules  # DERP/STUN
    assert "443" in rules  # headscale, registries


def test_every_image_is_pinned_and_workloads_are_bounded():
    _, pod = _cronjob()
    for c in _all_containers(pod):
        tag = c["image"].rsplit(":", 1)[-1]
        assert ":" in c["image"].split("/")[-1] and "latest" not in tag, c["image"]
        assert c["resources"]["limits"]["memory"], c["name"]
        assert c["securityContext"]["allowPrivilegeEscalation"] is False


# ---- security review (p3-sec-1..4) ----------------------------------------------------------
import os  # noqa: E402
import subprocess  # noqa: E402


def test_p3_sec_1_tag_owners_are_an_admin_group_not_default():
    a = acl()
    admins = a["groups"]["group:tag-admins"]
    assert admins == ["tag-admin"], "a dedicated user that never registers nodes"
    other_users = {o for owners in a["tagOwners"].values() for o in owners if not o.startswith("group:")}
    other_users |= {m for g, ms in a["groups"].items() if g != "group:tag-admins" for m in ms}
    assert not set(admins) & other_users, "disjoint from every user that owns nodes/other tags"
    assert "default" not in admins
    for tag in ("tag:frank-updater", "tag:frank-session", "tag:hop-node"):
        assert a["tagOwners"][tag] == ["group:tag-admins"], tag
    # the old entry is still exactly as it was
    assert a["tagOwners"]["tag:subnet-router"] == ["default"]
    text = yaml.safe_load(HEADSCALE_CM.read_text())["data"]["acl.yaml"]
    assert "reusable" in text and "ephemeral" in text and "pre-tagged" in text
    assert "single-use" not in text.replace("NOT single-use", ""), "a daily CronJob registers a fresh node each run"
    assert "short expiry" in text and "rotat" in text


def _scan_script():
    _, pod = _cronjob()
    (scan,) = [c for c in _all_containers(pod) if c["name"] == "scan"]
    return "\n".join(scan["command"] + scan.get("args", []))


def test_p3_sec_2_image_lines_are_validated_and_trivy_gets_a_terminator():
    script = _scan_script()
    assert "grep -E" in script
    assert '-- "$image"' in script
    m = re.search(r"grep -E '([^']+)'", script)
    pat = re.compile(m.group(1))
    for ok in ("ghcr.io/x/y:1.2", "nginx", "r.io/a/b@sha256:" + "a" * 64, "a/b:c"):
        assert pat.match(ok), ok
    for bad in ("--config=/etc/x", "-x", "", " a", "a b", "a;b", "$(id)"):
        assert not pat.match(bad), bad
    # behavioural: run the filter pipeline on the fixture
    out = subprocess.run(["sh", "-c", f"grep -E '{m.group(1)}'"], input="--config=/etc/x\n\nok/img:1\n",
                         capture_output=True, text=True).stdout
    assert out == "ok/img:1\n"


def test_p3_sec_3_tailscale_state_is_not_visible_to_the_scanner():
    _, pod = _cronjob()
    byname = {c["name"]: c for c in _all_containers(pod)}
    ts, scan = byname["tailscale"], byname["scan"]
    mounts = lambda c: {m["name"]: m["mountPath"] for m in c.get("volumeMounts", [])}
    assert mounts(ts) == {"ts-state": "/ts-state"}
    assert "ts-state" not in mounts(scan)
    for name, c in byname.items():
        if name != "tailscale":
            assert "ts-state" not in mounts(c), name
    env = {e["name"]: e.get("value") for e in ts["env"]}
    assert env["TS_STATE_DIR"] == "/ts-state" and env["TS_SOCKET"].startswith("/ts-state/")
    # scan has its own cache dir, not a /tmp shared with tailscale
    senv = {e["name"]: e.get("value") for e in scan["env"]}
    assert senv["TRIVY_CACHE_DIR"].startswith("/scan-tmp")
    assert mounts(scan)["scan-tmp"] == "/scan-tmp"
    assert "/tmp" not in mounts(ts).values()
    vols = {v["name"] for v in pod["volumes"]}
    assert {"ts-state", "scan-tmp"} <= vols
    assert ts["securityContext"]["runAsUser"] != scan["securityContext"]["runAsUser"]


def test_p3_sec_4_trivy_token_reaches_the_scanner_from_an_optional_secret():
    _, pod = _cronjob()
    (scan,) = [c for c in _all_containers(pod) if c["name"] == "scan"]
    env = {e["name"]: e for e in scan["env"]}
    ref = env["TRIVY_TOKEN"]["valueFrom"]["secretKeyRef"]
    assert ref["name"] == "trivy-server-token" and ref["optional"] is True
    assert "--token" not in _scan_script(), "the token is read from TRIVY_TOKEN, not argv (visible in /proc)"


def test_p3_r6_trivy_cannot_eat_the_loop_input_and_the_scan_has_a_budget():
    script = _scan_script()
    assert re.search(r'trivy image[^\n]*\\?\n?[^\n]*</dev/null|</dev/null', script), "trivy must not read the loop's stdin"
    assert '-- "$image" </dev/null' in script
    cj, pod = _cronjob()
    (scan,) = [c for c in _all_containers(pod) if c["name"] == "scan"]
    env = {e["name"]: e.get("value") for e in scan["env"]}
    budget = int(env["SCAN_BUDGET_S"])
    assert "SCAN_BUDGET_S" in script and "date +%s" in script and "break" in script
    m = re.search(r"--timeout (\d+)m", script)
    per_image = int(m.group(1)) * 60
    deadline = cj["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"]
    waits = 12 * 10 + 60  # list-images retry loop + tailscale join slack
    assert budget + per_image + waits + 300 <= deadline, "margin so the report container always prints"
    # behavioural: run the real script body with a fake trivy that also drains stdin
    import tempfile

    def run(budget):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "results").mkdir()
            Path(d, "images.txt").write_text("a/one:1\n--evil\n\nb/two:2\n")
            body = script.replace("/work", d)
            fake = f'trivy(){{ cat >/dev/null; echo "$@" >> {d}/log; }}\n'
            subprocess.run(["sh", "-c", fake + body], env={"PATH": os.environ["PATH"], "SCAN_BUDGET_S": str(budget)},
                           capture_output=True, text=True, timeout=30)
            log = Path(d, "log")
            return log.read_text().splitlines() if log.exists() else []

    assert run(0) == []
    ran = run(3600)
    assert len(ran) == 2 and all("--evil" not in l.split("--")[-1] for l in ran), ran


def test_p3_r1_wildcard_is_narrowed_so_only_the_explicit_grant_reaches_frank_updater():
    a = acl()
    wildcard = a["acls"][0]
    assert wildcard["dst"] == OLD_DST, "destinations unchanged"
    assert "*" not in wildcard["src"]
    # everyone who has the access today: the one user that registers nodes plus every other tag,
    # minus the new tag. tag:hop-node is included because a tagged hop-1 stops matching its
    # user (Caddy on hop-1 reaches Frank LB IPs over the mesh); tag-admin registers no nodes.
    users = {"default"}
    tags = set(a["tagOwners"]) - NEW_TAGS
    assert set(wildcard["src"]) == users | tags
    assert "tag-admin" not in wildcard["src"] and "group:tag-admins" not in wildcard["src"]
    for tag in NEW_TAGS:
        grants = [r for r in a["acls"] if tag in r["src"]]
        assert grants == [_grant(tag)], f"{tag}: its explicit grant is its only access"
    for r in a["acls"]:
        assert "*" not in r["src"]
