"""Guard: Paperclip runs as a pure upstream pod (fresh start, 2026-10-04 spec).

No shell sidecar, no hermes/opencode shims, no LiteLLM key, no Frank-built
images. The upstream image bundles the agent CLIs; operators connect Claude
through the UI. This test keeps the removed pieces from creeping back.
"""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
MANIFESTS = REPO / "apps/paperclip/manifests"
BANNED_NAME_PREFIXES = (
    "paperclip-shell", "paperclip-hermes", "paperclip-opencode", "paperclip-llm-key",
)


def _docs():
    out = []
    for f in sorted(MANIFESTS.glob("*.yaml")):
        for d in yaml.safe_load_all(f.read_text()):
            if d:
                out.append(d)
    return out


def _deployment():
    return next(d for d in _docs()
                if d["kind"] == "Deployment" and d["metadata"]["name"] == "paperclip")


def _pod():
    return _deployment()["spec"]["template"]["spec"]


def test_single_container_no_init_containers():
    pod = _pod()
    assert [c["name"] for c in pod["containers"]] == ["paperclip"]
    assert not pod.get("initContainers")


def test_image_is_upstream_sha_pin():
    img = _pod()["containers"][0]["image"]
    assert img.startswith("ghcr.io/paperclipai/paperclip:sha-"), img


def test_no_agent_shim_env():
    env = _pod()["containers"][0].get("env", [])
    names = {e["name"] for e in env}
    bad = {n for n in names if n.startswith("OLLAMA_")} | (
        names & {"HERMES_HOME", "XDG_CONFIG_HOME"})
    assert not bad, bad
    for e in env:
        if e["name"] == "PATH":
            assert "agent-bin" not in e.get("value", "")


def test_no_llm_key_reference():
    c = _pod()["containers"][0]
    for ef in c.get("envFrom", []):
        assert ef.get("secretRef", {}).get("name") != "paperclip-llm-key"
    for e in c.get("env", []):
        ref = e.get("valueFrom", {}).get("secretKeyRef", {})
        assert ref.get("name") != "paperclip-llm-key"


def test_no_shell_shim_objects():
    for d in _docs():
        name = d["metadata"]["name"]
        assert not name.startswith(BANNED_NAME_PREFIXES), f"{d['kind']}/{name}"


def test_config_trust_proxy_and_announcements():
    cm = next(d for d in _docs()
              if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "paperclip-config")
    data = cm["data"]
    assert "TRUST_PROXY" in data
    assert data["TRUST_PROXY"] != "true"
    assert "uniquelocal" not in data["TRUST_PROXY"]
    assert data["PAPERCLIP_ANNOUNCEMENTS_ENABLED"] == "false"


def test_shell_leftovers_gone():
    wf = (REPO / ".github/workflows/agent-images-bump.yml").read_text()
    assert "paperclip-shell" not in wf
    assert not (REPO / "apps/paperclip/client-setup").exists()
    assert not (REPO / "secrets/paperclip").exists()
