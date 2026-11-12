"""Guard DISABLE_AUTOUPDATER=1 on every claude-running container.

The Claude Code native build ships a background auto-updater that buffers its
~250-335MB download many times over in anon memory (~4.2GiB peak — the
`claude install` gotcha in docs/runbooks/frank-gotchas/agent-shells.md). Inside
a pod that keeps PERSISTENT claude sessions (alert-agent's per-stream tmux
sessions, n8n-01's agent-session), that peak lands inside long-lived processes
whose RSS never shrinks back: on 2026-08-27 the alert-agent `agent` container
sat pinned at its 8Gi memory.max (memory.events max=2.35M reclaim hits) with
the surge and digest sessions at 4.35GB/3.9GB RSS — matching the updater peak,
not the ~400MB/session design budget — and was OOMKilled (exit 137) the moment
the 14:00Z surge-gate wake allocated on top. Five self-downloaded binaries in
~/.local/share/claude/versions/ (Aug 13→27) proved the updater active; the
update also swapped the binary under the running sessions, wedging all three
panes on the new version's interactive "Set up auto mode" onboarding dialog.
Debug journal: docs/superpowers/journals/debug/2026-08-27-alert-agent-oom-overload.md.

Updates must arrive via the agent-images pipeline (memory-safe curl install),
never via the in-pod updater. Every claude-running container must declare
DISABLE_AUTOUPDATER=1 in `env:`. (The secure-agent-pod's kali container and its
profile.d re-export shim were retired 2026-11, so only the manifests of the
remaining claude-running pods are checked.)
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

from .test_fr_isolation_target_env import (
    _containers,
    _env_value,
)

REPO = Path(__file__).resolve().parents[2]

# manifest → container names that run claude and MUST carry the var.
# (alert-agent's telegram-bridge/grafana-webhook sidecars are python-only;
# hermes-agent-shell runs hermes, not claude — both stay out on purpose.)
REQUIRED = {
    REPO / "apps/alert-agent/manifests/deployment.yaml": {"agent"},
    REPO / "apps/n8n-01/manifests/deployment.yaml": {"multi-agent-shell"},
    REPO / "apps/cnc-base/manifests/statefulset-node.yaml": {"node"},
}


def test_env_in_all_claude_containers():
    """Every claude-running container declares DISABLE_AUTOUPDATER=1."""
    for manifest, names in REQUIRED.items():
        containers = _containers(manifest)
        for name in names:
            assert name in containers, f"container {name!r} not found in {manifest.name}"
            assert _env_value(containers[name], "DISABLE_AUTOUPDATER") == "1", (
                f"{manifest.relative_to(REPO)} container {name!r} must declare "
                "env DISABLE_AUTOUPDATER=1 — the in-pod Claude Code auto-updater "
                "inflated alert-agent's persistent sessions to ~4GB each and "
                "OOMKilled the container (2026-08-27); updates ship via "
                "agent-images, never in-pod"
            )
