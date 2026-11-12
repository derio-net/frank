"""Guard FR_ISOLATION_TARGET=worktree on Frank's agent pods (frank#686).

super-fr v3.15.0 shipped docker-less isolation host modes: with
`FR_ISOLATION_TARGET=worktree` in the process env, `fr isolation up/exec/down`
runs as a plain git worktree in the host env (no docker/devcontainer), making
fr-goal / fr-brainstorming / fr-debugging runnable inside Frank's unprivileged
agent pods. See docs/superpowers/specs/2026-07-24--agents--fr-isolation-target-env-design.md.

Two things must both hold, or an SSH agent silently falls back to devcontainer
mode and fails:

  1. every agent-bearing container declares FR_ISOLATION_TARGET=worktree in its
     `env:` (hermes, ssh — NOT hindsight, no agent processes);
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
HERMES_DEPLOY = REPO / "apps/hermes-agent-shell/manifests/deployment.yaml"
HERMES_SHIM_CM = REPO / "apps/hermes-agent-shell/manifests/configmap-byok-env.yaml"

# Containers that run agent processes and so MUST carry the var.
REQUIRED_CONTAINERS = {"hermes", "ssh"}
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
    """hermes and ssh each carry FR_ISOLATION_TARGET=worktree."""
    containers = _containers(HERMES_DEPLOY)

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
    # The ssh sidecar's PID 1 is sshd, which clobbers /proc/1/environ with its
    # proctitle — the loop is vacuous THERE, so the static fallback export is
    # what actually delivers the var to login shells. Its literal must stay in
    # lockstep with the Deployment env value.
    assert re.search(r"export FR_ISOLATION_TARGET=worktree\b", script), (
        "the hermes shim must carry the static fallback "
        "'export FR_ISOLATION_TARGET=worktree' — /proc/1/environ is proctitle "
        "junk when sshd is PID 1 (ssh sidecar), so the environ loop never fires"
    )
