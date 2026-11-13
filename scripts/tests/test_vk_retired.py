"""Guard: VibeKanban and the secure-agent-pod are retired from Frank's git state.

Spec: docs/superpowers/specs/2026-11-08--agents--retire-vk-design.md (R1-R8 in
Phase 1, R9-R15 in Phase 2). Phase 2 deleted the pod's directory, root templates
and secrets, so the scans below no longer exempt anything.
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
VK_RULE_UIDS = ("vk-bridge-stale", "vk-bridge-failures", "vk-executor-pool-wedged")


def _rules_doc():
    cm = yaml.safe_load(RULES_CM.read_text())
    return yaml.safe_load(cm["data"]["alert-rules.yaml"])


def _apps_files():
    for f in sorted(APPS.rglob("*")):
        if not f.is_file() or f.suffix not in {".yaml", ".yml", ".md", ".json", ".sh"}:
            continue
        yield f


# --- R2 / R3: the stack and its public surface ------------------------------

def test_vk_remote_stack_is_gone():
    assert not (APPS / "vk-remote").exists()
    assert not (APPS / "root/templates/vk-remote.yaml").exists()


def test_nothing_in_apps_advertises_vk_or_ships_its_image():
    offenders = []
    for f in _apps_files():
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
    # Read the baseline from a pin that keeps moving: a pin that stops moving makes the
    # old...new diff grow without bound and relists already-shipped PRs.
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


# --- R10-R15: the secure-agent-pod is gone ---------------------------------

POD_UIDS = (
    "exercise-reminder-stale",
    "session-manager-stale",
    "audit-digest-stale",
    "agent-pod-not-running",
    "layer-18-persistent-agent-degraded",
)


def test_pod_paths_are_gone():
    for rel in (
        "apps/secure-agent-pod",
        "apps/root/templates/secure-agent-pod.yaml",
        "apps/root/templates/ns-secure-agent-pod.yaml",
        "secrets/secure-agent-pod",
        "secrets/github-app/github-app-derio-key.yaml",
    ):
        assert not (REPO / rel).exists(), rel
    # Tekton's own copy of the App key is what stays.
    assert (REPO / "secrets/github-app/github-app-derio-key-tekton.yaml").exists()


def test_pod_alert_rules_are_deleted_and_tombstoned():
    doc = _rules_doc()
    defined = {r["uid"] for g in doc["groups"] for r in g["rules"]}
    tombstoned = {d["uid"] for d in doc["deleteRules"]}
    for uid in POD_UIDS:
        assert uid not in defined, f"{uid} is still defined"
        assert uid in tombstoned, f"{uid} needs a deleteRules tombstone"
    text = RULES_CM.read_text()
    for uid in POD_UIDS:
        assert f"{{orgId: 1, uid: {uid}}}" in text


def test_pod_dashboard_is_gone():
    assert not (APPS / "grafana-alerting/manifests/secure-agent-pod-dashboard-cm.yaml").exists()
    assert "grafana-secure-agent-pod-dashboard" not in (APPS / "victoria-metrics/values.yaml").read_text()


def test_bump_workflow_has_no_frozen_pod_images():
    text = BUMP.read_text()
    assert "secure-agent-kali" not in text
    assert "vk-local" not in text


_POD_TOKENS = (
    "secure-agent-kali",
    "vk-local",
    "192.168.55.215",
    "192.168.55.218",
    "192.168.55.219",
    "secure-agent-pod",
)


def test_nothing_names_the_pod_unless_it_says_retired():
    offenders = []
    for top in ("apps", "secrets", ".github"):
        for f in sorted((REPO / top).rglob("*")):
            if not f.is_file():
                continue
            try:
                lines = f.read_text().splitlines()
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(lines, 1):
                if not any(t in line for t in _POD_TOKENS):
                    continue
                low = line.lower()
                if "retired" in low or "historical" in low:
                    continue
                if re.search(r"\{orgId: 1, uid: [\w-]+\}", line):
                    continue  # a deleteRules tombstone
                offenders.append(f"{f.relative_to(REPO)}:{n}: {line.strip()[:100]}")
    assert not offenders, offenders


def test_pin_exceptions_fixture_names_neither_pod_image():
    fixture = REPO / "scripts/tests/fixtures/life/pin-exceptions.yaml"
    if not fixture.exists():
        return  # arrives with frank#913; vacuous until then
    text = fixture.read_text()
    assert "vk-local" not in text
    assert "secure-agent-kali" not in text


SUPERSEDED = (
    "blog/content/docs/building/21-secure-agent-pod",
    "blog/content/docs/building/25-vk-relay",
    "blog/content/docs/building/26-vk-remote-self-host",
    "blog/content/docs/building/18-persistent-agent",
    "blog/content/docs/building/28-agent-images-sidecar",
    "blog/content/docs/operating/14-secure-agent-pod",
    "blog/content/docs/operating/20-vk-relay",
    "blog/content/docs/operating/21-vk-remote",
    "blog/content/docs/operating/19-git-credentials-without-a-shell",
    "blog/content/docs/papers/17-agentic-orchestration",
)


def test_blog_bundles_carry_the_retirement_notice():
    missing = []
    for rel in SUPERSEDED:
        lines = (REPO / rel / "index.md").read_text().splitlines()
        if not any(l.startswith("> **Update 2026-11.**") for l in lines):
            missing.append(rel)
    assert not missing, missing
