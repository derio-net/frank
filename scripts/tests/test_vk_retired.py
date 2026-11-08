"""Guard: VibeKanban is retired from Frank's git state (Phase 1 of retire-vk).

Spec: docs/superpowers/specs/2026-11-08--agents--retire-vk-design.md (R1-R8).

Phase 1 removes everything VK-shaped EXCEPT the live secure-agent-pod, whose
Deployment is `Recreate`: editing it ends the operator's running session. So
the pod's own directory is exempt from the "no references" scans below, and one
assertion pins the Deployment as untouched. Phase 2 deletes the pod, the exempt
paths and that pin together.
"""

import os
import re
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
APPS = REPO / "apps"
RULES_CM = APPS / "grafana-alerting/manifests/alert-rules-cm.yaml"
PROVIDERS = APPS / "authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml"
BUMP = REPO / ".github/workflows/agent-images-bump.yml"
POD_DEPLOYMENT = APPS / "secure-agent-pod/manifests/deployment.yaml"

POD_PIN = "dbb1b7fadf6594cdc659d964a4f1a527a7ca7a91"
VK_RULE_UIDS = ("vk-bridge-stale", "vk-bridge-failures", "vk-executor-pool-wedged")


def _rules_doc():
    cm = yaml.safe_load(RULES_CM.read_text())
    return yaml.safe_load(cm["data"]["alert-rules.yaml"])


def _apps_files(skip_pod=True):
    for f in sorted(APPS.rglob("*")):
        if not f.is_file() or f.suffix not in {".yaml", ".yml", ".md", ".json", ".sh"}:
            continue
        if skip_pod and "secure-agent-pod" in f.relative_to(APPS).parts[:1]:
            continue
        yield f


# --- R2 / R3: the stack and its public surface ------------------------------

def test_vk_remote_stack_is_gone():
    assert not (APPS / "vk-remote").exists()
    assert not (APPS / "root/templates/vk-remote.yaml").exists()


def test_nothing_in_apps_advertises_vk_or_ships_its_image():
    # Only the pod's Deployment is exempt until Phase 2 (live Recreate workload).
    offenders = []
    for f in _apps_files(skip_pod=False):
        if f == POD_DEPLOYMENT:
            continue
        text = f.read_text(errors="replace")
        if "vk.cluster.derio.net" in text:
            offenders.append(f"{f.relative_to(REPO)}: vk.cluster.derio.net")
        if "ghcr.io/derio-net/vk-remote" in text:
            offenders.append(f"{f.relative_to(REPO)}: vk-remote image")
    assert not offenders, offenders


def test_vk_authentik_entries_are_absent_tombstones():
    cm = yaml.safe_load(PROVIDERS.read_text())
    # BaseLoader: all scalars as strings, tolerates the blueprint's !Find/!KeyOf tags.
    doc = yaml.load(cm["data"]["cluster-proxy-providers.yaml"], Loader=yaml.BaseLoader)
    entries = doc["entries"]
    vk = [
        e for e in entries
        if e.get("identifiers", {}).get("slug") == "vk-remote-cluster"
        or e.get("identifiers", {}).get("name") == "VK Remote (cluster)"
    ]
    assert len(vk) == 2, "expect one application and one provider tombstone"
    assert all(e["state"] == "absent" for e in vk), vk
    assert "vk.cluster.derio.net" not in PROVIDERS.read_text()


def test_no_vk_ingressroute_or_homepage_tile():
    assert "vk-remote" not in (APPS / "traefik/manifests/ingressroutes.yaml").read_text()
    assert "VK Remote" not in (APPS / "homepage/manifests/files/services.yaml").read_text()


# --- R1: the alarms ---------------------------------------------------------

def test_vk_rules_are_deleted_and_tombstoned():
    doc = _rules_doc()
    defined = {r["uid"] for g in doc["groups"] for r in g["rules"]}
    tombstoned = {d["uid"] for d in doc["deleteRules"]}
    for uid in VK_RULE_UIDS:
        assert uid not in defined, f"{uid} is still defined"
        assert uid in tombstoned, f"{uid} needs a deleteRules tombstone (a removed file rule stays stored)"


def test_no_alert_expression_selects_the_vk_bridge_heartbeat():
    doc = _rules_doc()
    offenders = []
    for g in doc["groups"]:
        for r in g["rules"]:
            for d in r["data"]:
                expr = d.get("model", {}).get("expr", "")
                if "vk_issue_bridge" in expr or "vibekanban_" in expr:
                    offenders.append(r["uid"])
    assert not offenders, offenders
    assert "vk_issue_bridge" not in (APPS / "grafana-alerting/manifests/dashboard-cm.yaml").read_text()


# --- R4: the fork -----------------------------------------------------------

def test_vibe_kanban_is_not_mirrored_or_budgeted():
    offenders = []
    for sub in ("tekton", "ci-budget"):
        for f in (APPS / sub).rglob("*.y*ml"):
            if "vibe-kanban" in f.read_text():
                offenders.append(str(f.relative_to(REPO)))
    assert not offenders, offenders


# --- R5: the bump workflow --------------------------------------------------

def test_bump_workflow_has_no_vk_remote():
    text = BUMP.read_text()
    assert "VKR_SHA" not in text
    assert "vk-remote" not in text


def _bump_step_script():
    wf = yaml.safe_load(BUMP.read_text())
    for job in wf["jobs"].values():
        for step in job["steps"]:
            if step.get("id") == "bump":
                return step["run"]
    raise AssertionError("no step with id: bump")


def test_bump_step_exits_zero_when_nothing_is_skipped(tmp_path):
    # Runs the step for real, the way Actions does (bash -e): text guards cannot
    # see an exit status. A trailing `[ -n "$SKIPPED" ] && echo` exits 1 on every
    # normal bump, and "Verify coverage" and "Open PR" then never run.
    script = re.sub(r'AGENT_IMAGES="[^"]*"', 'AGENT_IMAGES=""', _bump_step_script())
    assert 'AGENT_IMAGES=""' in script
    env = {
        **os.environ,
        "AI_SHA": "a" * 40,
        "GITHUB_OUTPUT": str(tmp_path / "out"),
        "GH_TOKEN": "unused",
    }
    run = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr


def test_bump_baseline_reads_a_pin_that_keeps_moving():
    # The kali pin is frozen by R5, so a baseline read from it grows without bound.
    text = BUMP.read_text()
    match = re.search(r"OLD_AI_SHA=\$\(grep -oE '([^']+)'\s*\\?\s*(\S+)", text)
    assert match, "OLD_AI_SHA assignment not found"
    assert match.group(1).startswith("multi-agent-shell:")
    assert match.group(2) == "apps/alert-agent/manifests/deployment.yaml"


# --- R6: the shared token generator ----------------------------------------

def _generator_files(sub):
    out = []
    for f in (APPS / sub).rglob("*.y*ml"):
        for d in yaml.safe_load_all(f.read_text()):
            if (
                isinstance(d, dict)
                and d.get("kind") == "ClusterGenerator"
                and d.get("metadata", {}).get("name") == "github-app-derio"
            ):
                out.append(f)
    return out


def test_github_app_derio_generator_is_owned_by_tekton():
    assert len(_generator_files("tekton/manifests")) == 1
    assert _generator_files("secure-agent-pod") == []


# --- R7: the live pod is untouched until Phase 2 ----------------------------

def test_pod_deployment_still_pins_both_containers():
    # PHASE 1 INVARIANT. Phase 2 removes the pod and deletes this assertion.
    text = POD_DEPLOYMENT.read_text()
    # Pinned to the exact SHA: an accidental bump here rolls the pod.
    for image in ("secure-agent-kali", "vk-local"):
        assert f"ghcr.io/derio-net/{image}:{POD_PIN}" in text


