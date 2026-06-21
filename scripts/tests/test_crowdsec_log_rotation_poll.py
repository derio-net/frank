"""Guard CrowdSec against going blind on Kubernetes log rotation.

The agent tails `/var/log/containers/caddy-*_caddy-system_*.log`, which are
SYMLINKS to the kubelet's per-container log (`/var/log/pods/.../0.log`). The
crowdsec chart hardcodes `force_inotify: true` and defaults
`poll_without_inotify: false`, so the per-file tailer uses inotify on the
resolved inode. When the kubelet rotates that log by SIZE (`containerLogMaxSize`,
NOT a pod restart), the inotify tailer cannot follow the rotation — it logs
"Re-opening moved/deleted file" then hangs forever in "Waiting for ... to
appear", parsing zero lines. Caddy keeps serving, scanners keep probing, and
NOTHING is banned (ArgoCD green, agent Running 1/1 — silent).

This bit on 2026-06-20T11:37Z: the agent went blind ~19h, last ban 09:55Z.
The agent emits an explicit startup WARNING naming the exact fix:
  "File ... is a symlink, but inotify polling is enabled. Crowdsec will not be
   able to detect rotation. Consider setting poll_without_inotify to true ..."

`poll_without_inotify: true` is the only chart-overridable lever
(`acquis-configmap.yaml` line 15: `{{ .poll_without_inotify | default "false" }}`;
`force_inotify` is hardcoded but orthogonal — it governs directory-watch for
NEW files, not the per-file tailer). Polling is stat-based and detects
rotation/truncation, so the tailer re-attaches to the fresh inode.
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
VALUES = REPO / "clusters/hop/apps/crowdsec/values.yaml"


def _values():
    return yaml.safe_load(VALUES.read_text())


def test_caddy_acquisition_enables_poll_without_inotify():
    # Every container-log acquisition tails a symlink subject to kubelet
    # size-rotation; inotify (the chart default) hangs on rotation. Polling is
    # the documented fix and the only chart-exposed override.
    acqs = _values()["agent"]["acquisition"]
    assert acqs, "agent.acquisition must define at least one source"
    for a in acqs:
        assert a.get("poll_without_inotify") is True, (
            f"acquisition {a!r} must set poll_without_inotify: true — inotify cannot "
            "follow a symlinked container-log rotation and the tailer hangs blind"
        )
