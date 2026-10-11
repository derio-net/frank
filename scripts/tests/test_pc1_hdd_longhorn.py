"""Guard: pc-1's HDD tier is declared consistently in git.

Spec: docs/superpowers/specs/2026-10-11--stor--pc1-hdd-longhorn-design.md
Plan: docs/superpowers/plans/2026-10-11--stor--pc1-hdd-longhorn

Pins the declarative half: Talos UserVolumeConfigs select drives by WWID, the
Longhorn node-disk patches match their mounts, the longhorn-hdd class exists,
allow-empty-disk-selector-volume is off, every CI workspace uses longhorn-hdd,
and the docs stopped claiming longhorn-cicd is pinned to pc-1.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
P03 = REPO_ROOT / "patches/phase03-longhorn"
KNOWN_PC1_HDD_WWIDS = {
    "naa.50014ee2ae0311c3",
    "naa.50014ee203581a1f",
    "naa.50014ee0556235e7",
}
PC1_UUID = "03de0294-0480-05ab-3106-410700080009"


def _volume_docs():
    res = yaml.safe_load((P03 / "402-pc1-hdd-volumes.yaml").read_text())
    docs = [d for d in yaml.safe_load_all(res["spec"]["data"]) if d]
    return res, docs


def test_402_metadata():
    res, _ = _volume_docs()
    md = res["metadata"]
    assert md["id"] == "402-pc1-hdd-volumes"
    assert md["type"] == "ConfigPatches.omni.sidero.dev"
    assert md["labels"]["omni.sidero.dev/cluster"] == "frank"
    assert md["labels"]["omni.sidero.dev/cluster-machine"] == PC1_UUID


def test_402_volumes_select_by_wwid():
    text = (P03 / "402-pc1-hdd-volumes.yaml").read_text()
    assert "/dev/sd" not in text
    _, docs = _volume_docs()
    assert docs
    for d in docs:
        assert d["kind"] == "UserVolumeConfig"
        assert d["filesystem"]["type"] == "xfs"
        m = re.fullmatch(
            r'disk\.wwid == "(naa\.[0-9a-f]{16})"',
            d["provisioning"]["diskSelector"]["match"],
        )
        assert m, d["provisioning"]["diskSelector"]["match"]
        assert m.group(1) in KNOWN_PC1_HDD_WWIDS
        assert d["name"] == "hdd-" + m.group(1)[-8:]


def _disks(name):
    return yaml.safe_load((P03 / name).read_text())["spec"]["disks"]


def test_pc1_node_disks_match_volumes():
    _, docs = _volume_docs()
    names = {d["name"] for d in docs}
    disks = _disks("longhorn-node-disks-pc-1.yaml")
    assert set(disks) == names
    for n, e in disks.items():
        assert e["path"] == f"/var/mnt/{n}/"
        assert e["diskType"] == "filesystem"
        assert e["tags"] == ["hdd"]
        assert e["storageReserved"] == 0
        assert e["allowScheduling"] is True
        assert e["evictionRequested"] is False
        assert not n.startswith("default-disk")


def test_gpu1_node_disks_match_401():
    disks = _disks("longhorn-node-disks-gpu-1.yaml")
    assert set(disks) == {"gpu-sda-4000000000000", "gpu-sdb-4000000000000"}
    res = yaml.safe_load((P03 / "401-gpu1-extra-disks.yaml").read_text())
    data = yaml.safe_load(res["spec"]["data"])
    mounts = {
        p["mountpoint"]
        for disk in data["machine"]["disks"]
        for p in disk["partitions"]
    }
    for e in disks.values():
        assert e["tags"] == ["gpu-local"]
        assert e["path"].rstrip("/") in mounts


def test_longhorn_hdd_storageclass():
    sc = yaml.safe_load(
        (REPO_ROOT / "apps/longhorn/manifests/storageclass-longhorn-hdd.yaml").read_text()
    )
    assert sc["kind"] == "StorageClass"
    assert sc["metadata"]["name"] == "longhorn-hdd"
    assert sc["provisioner"] == "driver.longhorn.io"
    p = sc["parameters"]
    assert p["numberOfReplicas"] == "1"
    assert p["diskSelector"] == "hdd"
    assert p["dataLocality"] == "disabled"
    assert sc["reclaimPolicy"] == "Delete"
    assert sc["allowVolumeExpansion"] is True


def test_empty_disk_selector_volumes_disallowed():
    v = yaml.safe_load((REPO_ROOT / "apps/longhorn/values.yaml").read_text())
    assert v["defaultSettings"]["allowEmptyDiskSelectorVolume"] is False


def _walk(node, found):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "volumeClaimTemplate" and isinstance(v, dict):
                found.append(v)
            _walk(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk(v, found)


def test_every_tekton_workspace_uses_longhorn_hdd():
    found = []
    for f in sorted((REPO_ROOT / "apps/tekton").rglob("*.y*ml")):
        for doc in yaml.safe_load_all(f.read_text()):
            _walk(doc, found)
    assert len(found) >= 11, len(found)
    for t in found:
        assert t["spec"]["storageClassName"] == "longhorn-hdd"


def test_long_lived_consumers_stay_on_cicd():
    gitea = yaml.safe_load((REPO_ROOT / "apps/gitea/values.yaml").read_text())
    assert gitea["persistence"]["storageClass"] == "longhorn-cicd"
    zot = yaml.safe_load((REPO_ROOT / "apps/zot/values.yaml").read_text())
    assert "storageClassName: longhorn-cicd" in (REPO_ROOT / "apps/zot/values.yaml").read_text()
    assert zot is not None
    pvc = yaml.safe_load((REPO_ROOT / "apps/gitea-runner/manifests/pvc.yaml").read_text())
    assert pvc["spec"]["storageClassName"] == "longhorn-cicd"


def test_docs_tell_the_truth():
    readme = (P03 / "README.md").read_text()
    for w in KNOWN_PC1_HDD_WWIDS:
        assert w in readme
    assert "phase3-longhorn" not in readme
    for rel in (
        "README.md",
        "blog/content/docs/building/27-cicd-platform/index.md",
        "blog/content/docs/operating/02-storage-backups/index.md",
    ):
        for line in (REPO_ROOT / rel).read_text().splitlines():
            low = line.lower()
            if "longhorn-cicd" in low and ("on pc-1" in low or "pins pvcs" in low):
                assert "correction" in low or "historical" in low, f"{rel}: {line}"
    gotchas = (REPO_ROOT / "agents/rules/frank-gotchas.md").read_text()
    assert "allow-empty-disk-selector-volume" in gotchas
