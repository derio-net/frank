"""Guard FR_ISOLATION_TARGET=worktree on Frank's agent pods (frank#686).

super-fr v3.15.0 shipped docker-less isolation host modes: with
`FR_ISOLATION_TARGET=worktree` in the process env, `fr isolation up/exec/down`
runs as a plain git worktree in the host env (no docker/devcontainer), making
fr-goal / fr-brainstorming / fr-debugging runnable inside Frank's unprivileged
agent pods. See docs/superpowers/specs/2026-07-24-fr-isolation-target-worktree-design.md.

Two things must both hold, or an SSH agent silently falls back to devcontainer
mode and fails:

  1. every agent-bearing container declares FR_ISOLATION_TARGET=worktree in its
     `env:` (kali, vk-local, hermes, ssh — NOT hindsight, no agent processes);
  2. the profile.d re-export shims carry FR_ISOLATION_TARGET into SSH login
     shells, since sshd (`UsePAM no`, no `PermitUserEnvironment`) scrubs the
     container env from login shells — the "sshd scrubs container env on login"
     gotcha (docs/runbooks/frank-gotchas/agent-shells.md).

Both are load-bearing, so this test locks both.
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
SECURE_AGENT_DEPLOY = REPO / "apps/secure-agent-pod/manifests/deployment.yaml"
HERMES_DEPLOY = REPO / "apps/hermes-agent-shell/manifests/deployment.yaml"
HERMES_SHIM_CM = REPO / "apps/hermes-agent-shell/manifests/configmap-byok-env.yaml"
KALI_SHIM_CM = REPO / "apps/secure-agent-pod/manifests/configmap-fr-env.yaml"

# Containers that run agent processes and so MUST carry the var.
REQUIRED_CONTAINERS = {"kali", "vk-local", "hermes", "ssh"}
# Excluded on purpose — the Postgres/embedder sidecar runs no agent processes.
EXCLUDED_CONTAINER = "hindsight"


def _load(path: Path):
    return yaml.safe_load(path.read_text())


def _containers(deploy_path: Path) -> dict:
    spec = _load(deploy_path)["spec"]["template"]["spec"]
    return {c["name"]: c for c in spec["containers"]}


def _env_value(container: dict, name: str):
    for e in container.get("env", []) or []:
        if e.get("name") == name:
            return e.get("value")
    return None


def test_env_in_all_agent_containers():
    """kali, vk-local, hermes, ssh each carry FR_ISOLATION_TARGET=worktree."""
    containers = {}
    containers.update(_containers(SECURE_AGENT_DEPLOY))
    containers.update(_containers(HERMES_DEPLOY))

    for name in REQUIRED_CONTAINERS:
        assert name in containers, f"container {name!r} not found in the deployments"
        assert _env_value(containers[name], "FR_ISOLATION_TARGET") == "worktree", (
            f"container {name!r} must declare env FR_ISOLATION_TARGET=worktree "
            "(super-fr host-worktree isolation, frank#686)"
        )

    # hindsight runs no agent processes — it must NOT be swept in.
    assert EXCLUDED_CONTAINER in containers, "hindsight sidecar expected in hermes deployment"
    assert _env_value(containers[EXCLUDED_CONTAINER], "FR_ISOLATION_TARGET") is None, (
        "hindsight (Postgres/embedder sidecar) must NOT declare FR_ISOLATION_TARGET — "
        "no agent processes run there"
    )


def test_hermes_shim_reexports_var():
    """The hermes byok-env profile.d shim re-exports FR_ISOLATION_TARGET."""
    cm = _load(HERMES_SHIM_CM)
    assert cm["kind"] == "ConfigMap"
    assert cm["metadata"]["name"] == "hermes-agent-shell-env"
    script = cm["data"]["35-hermes-agent-shell-byok-env.sh"]
    assert "FR_ISOLATION_TARGET" in script, (
        "the hermes 35-…-byok-env.sh re-export loop must include FR_ISOLATION_TARGET "
        "so it survives sshd's env scrub into the login shell"
    )


def test_kali_shim_configmap_and_mount():
    """secure-agent-pod ships a fr-env shim ConfigMap the kali container mounts."""
    cm = _load(KALI_SHIM_CM)
    assert cm["kind"] == "ConfigMap"
    assert cm["metadata"]["name"] == "secure-agent-pod-env"
    assert cm["metadata"]["namespace"] == "secure-agent-pod"
    script = cm["data"]["35-secure-agent-pod-fr-env.sh"]
    assert "FR_ISOLATION_TARGET" in script, (
        "the kali 35-secure-agent-pod-fr-env.sh re-export loop must include "
        "FR_ISOLATION_TARGET"
    )

    kali = _containers(SECURE_AGENT_DEPLOY)["kali"]
    mount_path = "/etc/profile.d/35-secure-agent-pod-fr-env.sh"
    mounts = [m for m in kali.get("volumeMounts", []) if m.get("mountPath") == mount_path]
    assert mounts, f"kali must mount the shim at {mount_path}"
    m = mounts[0]
    assert m.get("subPath") == "35-secure-agent-pod-fr-env.sh", (
        "the shim must be a single-file subPath mount"
    )
    assert m.get("readOnly") is True, "the shim mount must be readOnly"
