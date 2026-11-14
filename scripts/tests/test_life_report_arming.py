"""cluster-update-fr's ExternalSecrets stop degrading the app only while phase 7 has not run.

The switch is the placeholder App ids in clustergenerators.yaml: phase 7 (P7.T1.S3) replaces them,
and from then on a Secret that cannot sync must degrade the app again.
"""
from pathlib import Path

import yaml

MAN = Path(__file__).resolve().parents[2] / "apps/cluster-update-fr/manifests"


def _docs(name):
    return [d for d in yaml.safe_load_all((MAN / name).read_text()) if d]


def test_externalsecret_health_is_ignored_exactly_while_the_apps_are_placeholders():
    pending = "PENDING-MANUAL-PHASE" in (MAN / "clustergenerators.yaml").read_text()
    ess = [d for d in _docs("externalsecrets.yaml") if d["kind"] == "ExternalSecret"]
    assert {d["metadata"]["name"] for d in ess} == {
        "cluster-update-fr-github", "cluster-update-fr-session-github",
        "cluster-update-fr-gitea", "cluster-update-fr-telegram"}
    for d in ess:
        ann = d["metadata"].get("annotations", {})
        ignored = ann.get("argocd.argoproj.io/ignore-healthcheck") == "true"
        assert ignored == pending, (
            f"{d['metadata']['name']}: ignore-healthcheck must be present exactly while "
            "clustergenerators.yaml still holds PENDING-MANUAL-PHASE; phase 7 removes both together")
