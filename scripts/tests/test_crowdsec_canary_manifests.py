"""Static guards for the CrowdSec ban-pipeline canary manifests.

Locks the load-bearing fields so a careless edit can't silently re-break the
deploy (unpinned image, overlapping runs, a wrong/non-optional secret ref, a PVC
that hangs Pending for want of a StorageClass on Hop).
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — missing yaml must ERROR, not skip

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "clusters/hop/apps/crowdsec-canary"
MANIFESTS = APP / "manifests"
PV = REPO / "clusters/hop/apps/storage/manifests/pv-crowdsec-canary-state.yaml"
APP_TMPL = REPO / "clusters/hop/apps/root/templates/crowdsec-canary.yaml"


def _load(p):
    return yaml.safe_load(p.read_text())


def test_cronjob_schedule_and_no_overlap():
    cj = _load(MANIFESTS / "cronjob.yaml")
    assert cj["spec"]["schedule"] == "*/5 * * * *"
    assert cj["spec"]["concurrencyPolicy"] == "Forbid"
    job = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    assert job["restartPolicy"] == "Never"


def test_cronjob_image_is_digest_pinned():
    cj = _load(MANIFESTS / "cronjob.yaml")
    img = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["image"]
    assert "@sha256:" in img, "canary image must be digest-pinned"
    assert not img.endswith(":latest") and ":latest@" not in img


def test_telegram_secret_ref_is_optional():
    cj = _load(MANIFESTS / "cronjob.yaml")
    env = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["env"]
    tg = [e for e in env if e["name"] in ("TELEGRAM_TOKEN", "TELEGRAM_CHATID")]
    assert len(tg) == 2, "both Telegram env vars must be present"
    for e in tg:
        ref = e["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "crowdsec-canary-telegram"
        # optional => CronJob is healthy before the manual secret phase (heartbeat-only)
        assert ref.get("optional") is True


def test_cronjob_chowns_state_dir_via_init_container():
    # The hostPath state PV mounts root-owned and kubelet ignores fsGroup for
    # hostPath, so the non-root canary can't write /state without a root chown.
    cj = _load(MANIFESTS / "cronjob.yaml")
    spec = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    inits = spec.get("initContainers", [])
    chown = [c for c in inits if "chown" in " ".join(c.get("command", []))]
    assert chown, "a root init container must chown the hostPath state dir (fsGroup is ignored for hostPath)"
    c = chown[0]
    assert c["securityContext"]["runAsUser"] == 0
    assert any(m["mountPath"] == "/state" for m in c["volumeMounts"])


def test_cronjob_mounts_state_and_script():
    cj = _load(MANIFESTS / "cronjob.yaml")
    spec = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    vols = {v["name"] for v in spec["volumes"]}
    assert {"script", "state"} <= vols
    pvc = next(v for v in spec["volumes"] if v["name"] == "state")
    assert pvc["persistentVolumeClaim"]["claimName"] == "crowdsec-canary-state-pvc"


def test_pvc_has_storageclass_and_volumename():
    pvc = _load(MANIFESTS / "pvc-state.yaml")
    assert pvc["spec"]["storageClassName"] == "hetzner-volume"
    assert pvc["spec"]["volumeName"] == "crowdsec-canary-state"


def test_pv_pinned_to_hop1_and_bound():
    pv = _load(PV)
    assert pv["spec"]["storageClassName"] == "hetzner-volume"
    assert pv["spec"]["claimRef"]["name"] == "crowdsec-canary-state-pvc"
    terms = pv["spec"]["nodeAffinity"]["required"]["nodeSelectorTerms"][0]["matchExpressions"][0]
    assert terms["key"] == "kubernetes.io/hostname"
    assert terms["operator"] == "In" and terms["values"] == ["hop-1"]


def test_kustomization_generates_script_from_canary_py():
    kz = _load(MANIFESTS / "kustomization.yaml")
    gens = kz["configMapGenerator"]
    assert any("canary.py" in g.get("files", []) for g in gens)
    assert (MANIFESTS / "canary.py").exists()


def test_application_prunes_for_hashed_configmaps():
    # text assert — the template carries Helm {{ }} so it isn't plain YAML
    txt = APP_TMPL.read_text()
    assert "prune: true" in txt
    assert "path: clusters/hop/apps/crowdsec-canary/manifests" in txt
