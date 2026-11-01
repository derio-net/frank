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
OLD_ACLS = [{"action": "accept", "src": ["*"], "dst": ["*:*"]}]
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


def test_the_edit_is_minimal_one_entry_and_two_owners():
    a = acl()
    new = a["acls"][len(OLD_ACLS):]
    assert len(new) == 1
    assert set(a["tagOwners"]) - set(OLD_TAG_OWNERS) == {"tag:frank-updater", "tag:hop-node"}


def test_frank_updater_reaches_only_hop_kube_and_talos_apis():
    (entry,) = acl()["acls"][len(OLD_ACLS):]
    assert entry["action"] == "accept"
    assert entry["src"] == ["tag:frank-updater"]
    assert entry["dst"] == ["tag:hop-node:6443,50000"]
    assert acl()["tagOwners"]["tag:frank-updater"], "the tag needs an owner"


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
