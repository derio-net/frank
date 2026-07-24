"""Guard FR_ISOLATION_TARGET=worktree on Frank's agent pods (frank#686).

super-fr v3.15.0 shipped docker-less isolation host modes: with
`FR_ISOLATION_TARGET=worktree` in the process env, `fr isolation up/exec/down`
runs as a plain git worktree in the host env (no docker/devcontainer), making
fr-goal / fr-brainstorming / fr-debugging runnable inside Frank's unprivileged
agent pods. See docs/superpowers/specs/2026-07-24--agents--fr-isolation-target-env-design.md.

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

import re
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


def _reexport_loop_covers(script: str, var: str) -> bool:
    """True when the shim's `for … in <list>; do` loop line itself names var.

    A bare substring check would also match a comment mentioning the var while
    the loop line no longer carries it — assert on the loop line.
    """
    return bool(re.search(rf"for _\w+ in [^\n]*\b{re.escape(var)}\b[^\n]*; do", script))


def test_env_in_all_agent_containers():
    """kali, vk-local, hermes, ssh each carry FR_ISOLATION_TARGET=worktree."""
    secure = _containers(SECURE_AGENT_DEPLOY)
    hermes = _containers(HERMES_DEPLOY)
    # Keep the namespaces separate: a future name collision across the two
    # deployments must fail loudly, not silently shadow one entry.
    overlap = secure.keys() & hermes.keys()
    assert not overlap, f"container names collide across deployments: {overlap}"
    containers = {**secure, **hermes}

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
    assert _reexport_loop_covers(script, "FR_ISOLATION_TARGET"), (
        "the hermes 35-…-byok-env.sh re-export loop line must include "
        "FR_ISOLATION_TARGET so it survives sshd's env scrub into the login shell"
    )


def test_kali_shim_configmap_and_mount():
    """secure-agent-pod ships a fr-env shim ConfigMap the kali container mounts."""
    cm = _load(KALI_SHIM_CM)
    assert cm["kind"] == "ConfigMap"
    assert cm["metadata"]["name"] == "secure-agent-pod-env"
    assert cm["metadata"]["namespace"] == "secure-agent-pod"
    script = cm["data"]["35-secure-agent-pod-fr-env.sh"]
    assert _reexport_loop_covers(script, "FR_ISOLATION_TARGET"), (
        "the kali 35-secure-agent-pod-fr-env.sh re-export loop line must include "
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

    # Pin the volume→ConfigMap linkage: a typo'd configMap.name leaves the pod
    # stuck ContainerCreating — and with strategy Recreate the old pod is
    # already gone, i.e. a full agent-shell outage that syncs "forever".
    pod_spec = _load(SECURE_AGENT_DEPLOY)["spec"]["template"]["spec"]
    volumes = {v["name"]: v for v in pod_spec.get("volumes", [])}
    vol_name = m.get("name")
    assert vol_name in volumes, f"kali shim mount references undefined volume {vol_name!r}"
    assert volumes[vol_name].get("configMap", {}).get("name") == cm["metadata"]["name"], (
        f"volume {vol_name!r} must reference the shim ConfigMap "
        f"{cm['metadata']['name']!r} — a mismatch strands the pod in ContainerCreating"
    )
