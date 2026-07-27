"""Guard the Hermes tool-home PVC against the worktree-exhaustion regression."""

from pathlib import Path
import re

import yaml  # hard dependency declared in pyproject


REPO = Path(__file__).resolve().parents[2]
PVC = REPO / "apps/hermes-agent-shell/manifests/pvc-home.yaml"


def test_hermes_tool_home_pvc_has_worktree_headroom() -> None:
    manifest = yaml.safe_load(PVC.read_text())
    storage = manifest["spec"]["resources"]["requests"]["storage"]
    match = re.fullmatch(r"(\d+)Gi", storage)

    assert match, "Hermes tool-home PVC must declare a GiB storage request"
    assert int(match.group(1)) >= 40, (
        "Hermes tool-home must request at least 40Gi: the previous 20Gi PVC "
        "filled during fr worktree creation and blocked scheduled bookmark drains"
    )
