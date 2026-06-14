"""Tests for the n8n-01 multi-agent-shell sidecar + persistent claude session.

Component 2 of the stoa Frank infra: a multi-agent-shell sidecar on the n8n-01
pod hosts a persistent, operator-attachable `claude` tmux session (never
`claude -p`), with PV-resident OAuth creds and no API keys in the manifest.

Contract source of truth:
docs/superpowers/specs/2026-06-14-stoa-frank-infra-design.md
"""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DEPLOYMENT = REPO / "apps/n8n-01/manifests/deployment.yaml"
PVC_AGENT_HOME = REPO / "apps/n8n-01/manifests/pvc-agent-home.yaml"
BOOTSTRAP = REPO / "apps/n8n-01/manifests/agent-session-bootstrap.yaml"
DRIVER_CM = REPO / "apps/n8n-01/manifests/agent-session-driver.yaml"

SIDECAR = "multi-agent-shell"
API_KEY_ENVS = {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"}


def _deploy():
    for doc in yaml.safe_load_all(DEPLOYMENT.read_text()):
        if doc and doc.get("kind") == "Deployment":
            return doc
    raise AssertionError("no Deployment found")


def _sidecar():
    pod = _deploy()["spec"]["template"]["spec"]
    for c in pod["containers"]:
        if c["name"] == SIDECAR:
            return c, pod
    raise AssertionError(f"no {SIDECAR} container in n8n-01 Deployment")


def test_sidecar_container_present_and_pinned():
    c, _ = _sidecar()
    assert c["image"].startswith("ghcr.io/derio-net/multi-agent-shell:")
    assert not c["image"].endswith(":latest"), "pin the sidecar image, never :latest"


def test_sidecar_has_no_api_keys():
    c, _ = _sidecar()
    names = {e["name"] for e in c.get("env", [])}
    assert not (names & API_KEY_ENVS), (
        f"sidecar must use subscription OAuth, not API keys; found {names & API_KEY_ENVS}"
    )


def test_sidecar_has_explicit_home_on_agent_pvc():
    c, _ = _sidecar()
    env = {e["name"]: e.get("value") for e in c.get("env", [])}
    assert "HOME" in env, "sidecar needs an explicit HOME"
    home = env["HOME"]
    mounts = {m["name"]: m["mountPath"] for m in c.get("volumeMounts", [])}
    assert "agent-home" in mounts, "sidecar must mount the agent-home volume"
    assert mounts["agent-home"] == home, "agent-home must mount at HOME (PV-resident creds)"


def test_no_share_process_namespace():
    pod = _deploy()["spec"]["template"]["spec"]
    assert not pod.get("shareProcessNamespace"), (
        "shareProcessNamespace is incompatible with the image's s6-overlay v3"
    )


def test_agent_home_pvc_manifest():
    assert PVC_AGENT_HOME.exists(), "apps/n8n-01/manifests/pvc-agent-home.yaml must exist"
    doc = next(
        d for d in yaml.safe_load_all(PVC_AGENT_HOME.read_text())
        if d and d.get("kind") == "PersistentVolumeClaim"
    )
    assert doc["spec"]["storageClassName"] == "longhorn"
    assert "ReadWriteOnce" in doc["spec"]["accessModes"]


# --- Task 2: persistent session bootstrap ------------------------------------

def _bootstrap_cm():
    doc = next(
        d for d in yaml.safe_load_all(BOOTSTRAP.read_text())
        if d and d.get("kind") == "ConfigMap"
    )
    return doc


def test_bootstrap_starts_interactive_claude_in_named_tmux():
    assert BOOTSTRAP.exists(), "agent-session-bootstrap.yaml must exist"
    script = "\n".join(_bootstrap_cm()["data"].values())
    assert "tmux" in script and "new-session" in script, "bootstrap must start a tmux session"
    assert "stoa-script-claude" in script, "session name must be stoa-script-claude"
    # Interactive claude — NEVER print mode.
    assert "claude" in script
    assert "-p " not in script and "--print" not in script, "never `claude -p`"
    # Must be able to write its per-turn output file without a permission prompt
    # (auto-approve safe ops — not a full permissions bypass).
    assert "--permission-mode auto" in script
    # Idempotent: don't double-create the session.
    assert "has-session" in script, "bootstrap must be idempotent (has-session guard)"


def test_sidecar_references_bootstrap():
    c, _ = _sidecar()
    vol_mounts = {m["name"] for m in c.get("volumeMounts", [])}
    pod = _deploy()["spec"]["template"]["spec"]
    vols = {v["name"]: v for v in pod["volumes"]}
    # A volume sourced from the bootstrap ConfigMap is mounted into the sidecar.
    cm_vols = {
        name for name, v in vols.items()
        if v.get("configMap", {}).get("name", "").startswith("agent-session-bootstrap")
    }
    assert cm_vols, "a bootstrap ConfigMap volume must exist"
    assert cm_vols & vol_mounts, "sidecar must mount the bootstrap ConfigMap"
    # And it actually runs the bootstrap (postStart hook or command references it).
    blob = yaml.safe_dump(c)
    assert "lifecycle" in blob or "command" in blob, "sidecar must invoke the bootstrap"


# --- Task 2: driver mount + pod-local transport ------------------------------

def _driver_cm():
    return next(
        d for d in yaml.safe_load_all(DRIVER_CM.read_text())
        if d and d.get("kind") == "ConfigMap"
    )


def test_driver_mounted_into_sidecar():
    assert DRIVER_CM.exists(), "agent-session-driver.yaml must exist"
    c, pod = _sidecar()
    vols = {v["name"]: v for v in pod["volumes"]}
    cm_vols = {
        name for name, v in vols.items()
        if v.get("configMap", {}).get("name", "") == "agent-session-driver"
    }
    mounts = {m["name"] for m in c.get("volumeMounts", [])}
    assert cm_vols & mounts, "sidecar must mount the agent-session-driver ConfigMap"


def test_session_server_is_pod_local():
    # The HTTP server binds 127.0.0.1 (n8n is in the same pod) — never 0.0.0.0,
    # and no Service/containerPort exposes it beyond the pod.
    driver = _driver_cm()["data"]["agent-session"]
    assert '"127.0.0.1"' in driver, "session HTTP server must bind 127.0.0.1 (pod-local)"
    assert "0.0.0.0" not in driver, "session HTTP server must not bind 0.0.0.0"
    c, _ = _sidecar()
    assert not c.get("ports"), "no containerPort — the server is localhost-only, not a Service"


def test_transport_documented_as_http():
    doc = "\n".join(_driver_cm()["data"].values())
    # content-factory's n8n httpRequest node posts to /session/send on localhost.
    assert "/session/send" in doc, "must document the POST /session/send endpoint"
    assert "127.0.0.1" in doc or "localhost" in doc, "must document the pod-local host"
    assert "AGENT_SIDECAR_URL" in doc, "must document the n8n env var it satisfies"


def test_bootstrap_starts_http_server():
    script = "\n".join(_bootstrap_cm()["data"].values())
    assert "agent-session serve" in script, "bootstrap must start the HTTP session server"


def test_n8n_container_points_at_sidecar_url():
    # The n8n container must expose AGENT_SIDECAR_URL so the workflow's
    # httpRequest node resolves it to the sidecar's pod-local endpoint.
    pod = _deploy()["spec"]["template"]["spec"]
    n8n = next(c for c in pod["containers"] if c["name"] == "n8n")
    env = {e["name"]: e.get("value") for e in n8n.get("env", [])}
    assert "AGENT_SIDECAR_URL" in env, "n8n must set AGENT_SIDECAR_URL"
    assert "localhost" in env["AGENT_SIDECAR_URL"] or "127.0.0.1" in env["AGENT_SIDECAR_URL"]
