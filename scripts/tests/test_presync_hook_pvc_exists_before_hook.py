"""A PreSync hook cannot mount a PVC that only the Sync phase creates.

ArgoCD runs PreSync hooks before the Sync phase applies anything, so a hook Job
whose volume claims a PVC from the SAME Application's plain resources schedules
against a claim that does not exist yet and sits Pending until its deadline,
then retries forever. cnc-prod hit this (`cnc-prod-snapshots`, never deployed,
2026-07-18 -> 2026-11-13). The PVC lives in cnc-prod-db instead (wave 0); a hook
must not own it either (hook resources are deleted before recreation).
"""

import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def _build(path: Path) -> list:
    out = subprocess.run(["kustomize", "build", str(path)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def _is_hook(doc: dict, phase: str) -> bool:
    ann = doc.get("metadata", {}).get("annotations", {}) or {}
    return phase in ann.get("argocd.argoproj.io/hook", "").split(",")


def test_cnc_prod_presync_jobs_only_mount_pvcs_that_already_exist():
    docs = _build(REPO / "apps/cnc-prod/manifests")
    owned = {d["metadata"]["name"] for d in docs if d["kind"] == "PersistentVolumeClaim"}
    for d in docs:
        if d["kind"] != "Job" or not _is_hook(d, "PreSync"):
            continue
        for v in d["spec"]["template"]["spec"].get("volumes", []):
            claim = (v.get("persistentVolumeClaim") or {}).get("claimName")
            assert claim not in owned, (
                f"PreSync hook {d['metadata']['name']} mounts PVC {claim}, which this "
                "Application only creates in the Sync phase: the hook can never schedule"
            )


def test_snapshot_pvc_is_owned_by_an_earlier_application_and_is_not_a_hook():
    pvc = list(yaml.safe_load_all((REPO / "apps/cnc-prod-db/manifests/snapshot-pvc.yaml").read_text()))
    pvc = [d for d in pvc if d][0]
    assert pvc["metadata"]["name"] == "cnc-prod-snapshots"
    assert not pvc["metadata"].get("annotations", {}).get("argocd.argoproj.io/hook"), (
        "a hook PVC is deleted before recreation, wiping the dumps"
    )
    job = yaml.safe_load((REPO / "apps/cnc-prod/manifests/snapshot-job.yaml").read_text().split("\n---")[0])
    claims = [v["persistentVolumeClaim"]["claimName"] for v in job["spec"]["template"]["spec"]["volumes"]]
    assert claims == ["cnc-prod-snapshots"]
