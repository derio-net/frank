"""Tests for scripts/stale_field_managers.py (frank#827).

A hand `kubectl apply --server-side` on an object ArgoCD later manages leaves a
second Apply manager in `metadata.managedFields`. Server-side apply removes a
field only once NO manager owns it, so when git later DROPS a list item (a
container, an init container) that the hand manager co-owns, ArgoCD's apply
strips just the fields it alone owned. The item survives, now without an
`image`, and the API server rejects the whole object:

    spec.template.spec.containers[1].image: Required value

ArgoCD then reports the app Synced/Healthy against its LAST good revision
while every sync to the merge fails. The fixture is the live paperclip
Deployment on 2026-10-11, metadata only, which is exactly that shape: a
2026-05-17 `kubectl` Apply entry still owning `paperclip-shell` and
`hermes-init` after #823 deleted both from git.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/stale_field_managers.py"
FIXTURE = REPO / "scripts/tests/fixtures/argocd/paperclip-deploy-2026-10-11.json"


def _run(payload: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30,
    )


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_flags_the_hand_apply_manager_on_an_argocd_object():
    proc = _run(_fixture())
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "paperclip-system/Deployment/paperclip" in proc.stdout
    assert "manager=kubectl" in proc.stdout and "2026-05-17T13:04:15Z" in proc.stdout


def test_does_not_flag_argocd_or_controller_updates():
    """ArgoCD's own Apply entry and `Update` managers (rollout restarts, the
    controller-manager's status writes) are normal and must stay quiet."""
    obj = _fixture()
    obj["metadata"]["managedFields"] = [
        f for f in obj["metadata"]["managedFields"] if f["manager"] != "kubectl"
    ]
    proc = _run(obj)
    assert proc.returncode == 0, proc.stdout
    assert proc.stdout.strip() == ""


def test_ignores_objects_argocd_does_not_track():
    """A hand Apply manager on an object outside GitOps is the operator's own
    business (SOPS-applied Secrets are the common case) and nobody's sync."""
    obj = _fixture()
    obj["metadata"]["annotations"] = {}
    proc = _run(obj)
    assert proc.returncode == 0, proc.stdout


def test_accepts_a_kubectl_list():
    """`kubectl get <kind> -A -o json --show-managed-fields` returns a List."""
    proc = _run({"apiVersion": "v1", "kind": "List", "items": [_fixture(), _fixture()]})
    assert proc.returncode == 1
    assert proc.stdout.count("paperclip-system/Deployment/paperclip") == 2


def test_patch_removes_only_the_stale_entry_and_is_guarded():
    """A bare `remove /metadata/managedFields/0` would delete whatever sits at
    index 0 by the time it runs. Each remove is preceded by `test` ops on the
    entry's manager AND time, so the API server refuses the patch if the list
    moved, rather than deleting ArgoCD's own entry."""
    proc = _run(_fixture(), "--patch")
    assert proc.returncode == 1, proc.stderr
    ops = json.loads(proc.stdout)
    assert ops == [
        {"op": "test", "path": "/metadata/managedFields/0/manager", "value": "kubectl"},
        {"op": "test", "path": "/metadata/managedFields/0/time", "value": "2026-05-17T13:04:15Z"},
        {"op": "remove", "path": "/metadata/managedFields/0"},
    ]


def test_patch_removes_from_the_highest_index_down():
    """Two stale entries: removing index 0 first would shift the second one, so
    its guarded path would point at the wrong entry."""
    obj = _fixture()
    stale = dict(obj["metadata"]["managedFields"][0], time="2026-06-01T00:00:00Z")
    obj["metadata"]["managedFields"].append(stale)
    ops = json.loads(_run(obj, "--patch").stdout)
    removes = [o["path"] for o in ops if o["op"] == "remove"]
    assert removes == ["/metadata/managedFields/4", "/metadata/managedFields/0"]


def test_patch_mode_needs_exactly_one_object():
    proc = _run({"apiVersion": "v1", "kind": "List", "items": [_fixture(), _fixture()]}, "--patch")
    assert proc.returncode == 2
    assert "exactly one" in proc.stderr
