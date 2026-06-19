import re
from pathlib import Path

import pytest
import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip the guard

REPO = Path(__file__).resolve().parents[2]
STORAGE = REPO / "clusters/hop/apps/storage/manifests"
VALUES = REPO / "clusters/hop/apps/crowdsec/values.yaml"
APP_CR = REPO / "clusters/hop/apps/root/templates/crowdsec.yaml"

PV_DATA = STORAGE / "pv-crowdsec-data.yaml"
PV_CONFIG = STORAGE / "pv-crowdsec-config.yaml"

_UNITS = {"Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40}


def _load(p):
    return yaml.safe_load(p.read_text())


def _release_name():
    # The Application CR contains Helm `{{ .Values... }}` templating and is NOT valid
    # YAML, so we regex out releaseName — the value that drives the chart's PVC names
    # the claimRefs must match.
    m = re.search(r"releaseName:\s*(\S+)", APP_CR.read_text())
    assert m, "releaseName not found in crowdsec Application CR"
    return m.group(1).strip()


def _bytes(s):
    s = str(s).strip()
    for u, mult in _UNITS.items():
        if s.endswith(u):
            return int(float(s[: -len(u)]) * mult)
    return int(s)


@pytest.mark.parametrize("path", [PV_DATA, PV_CONFIG])
def test_pv_file_exists(path):
    assert path.is_file(), f"missing PV manifest {path}"


@pytest.mark.parametrize("path", [PV_DATA, PV_CONFIG])
def test_pv_shape(path):
    pv = _load(path)
    assert pv["kind"] == "PersistentVolume"
    spec = pv["spec"]
    assert spec["storageClassName"] == "hetzner-volume"
    assert spec["persistentVolumeReclaimPolicy"] == "Retain"
    assert spec["accessModes"] == ["ReadWriteOnce"]
    hp = spec["hostPath"]
    assert hp["type"] == "DirectoryOrCreate", "auto-create the dir (zero manual step)"
    assert hp["path"].startswith("/var/mnt/hop-data/crowdsec/")


def test_claimref_matches_chart_pvc_names():
    release = _release_name()
    expected = {
        PV_DATA: f"{release}-db-pvc",
        PV_CONFIG: f"{release}-config-pvc",
    }
    for path, pvc_name in expected.items():
        spec = _load(path)["spec"]
        assert "claimRef" in spec, f"{path.name} must pin its chart PVC via claimRef"
        cr = spec["claimRef"]
        assert cr["namespace"] == "crowdsec-system"
        assert cr["name"] == pvc_name, (
            f"{path.name} claimRef.name={cr['name']!r} != chart PVC {pvc_name!r}; "
            "binding hangs Pending → LAPI down → no bans"
        )


def test_values_enable_persistence():
    pvc = _load(VALUES)["lapi"]["persistentVolume"]
    for key in ("data", "config"):
        assert pvc[key]["enabled"] is True, f"lapi.persistentVolume.{key} not enabled"
        assert pvc[key]["storageClassName"] == "hetzner-volume", (
            f"{key} needs explicit StorageClass (Hop has no default SC → PVC Pending)"
        )


def test_requested_sizes_fit_pv_capacity():
    pvc = _load(VALUES)["lapi"]["persistentVolume"]
    assert _bytes(pvc["data"]["size"]) <= _bytes(
        _load(PV_DATA)["spec"]["capacity"]["storage"]
    )
    assert _bytes(pvc["config"]["size"]) <= _bytes(
        _load(PV_CONFIG)["spec"]["capacity"]["storage"]
    )
