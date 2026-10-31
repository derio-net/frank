import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from render_all_images import find_unpinned, is_ignored, is_unpinned  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "life"


def _bad(name):
    return find_unpinned((FIX / name).read_text())


def test_tag_ok():
    assert _bad("tag-ok.yaml") == []


def test_digest_ok():
    assert _bad("digest-ok.yaml") == []


def test_latest_bad():
    assert _bad("latest-bad.yaml") == ["ghcr.io/x/y:latest"]


def test_no_tag_bad():
    assert _bad("notag-bad.yaml") == ["ghcr.io/x/y"]


def test_tekton_param_ignored():
    assert _bad("tekton-param.yaml") == []


def test_helm_split_repository_tag_ok_and_registry_port_not_a_tag():
    assert _bad("helm-split.yaml") == []
    assert is_unpinned("registry.local:5000/org/app")


def test_snapshot_lists_no_unpinned_images():
    lines = (FIX / "rendered-images.txt").read_text().splitlines()
    images = [line for line in lines if line and not line.startswith("#")]
    assert images, "snapshot is empty"
    assert [i for i in images if not is_ignored(i) and is_unpinned(i)] == []


def test_check_fails_when_any_source_is_skipped():
    from render_all_images import exit_code

    assert exit_code(check=True, unpinned=[], skipped=["x: boom"]) == 1
    assert exit_code(check=True, unpinned=["a:latest"], skipped=[]) == 1
    assert exit_code(check=True, unpinned=[], skipped=[]) == 0
    assert exit_code(check=False, unpinned=["a:latest"], skipped=["x"]) == 0


def test_kustomize_falls_back_to_kubectl(monkeypatch):
    import render_all_images as r

    monkeypatch.setattr(r.shutil, "which", lambda name: "/bin/x" if name == "kubectl" else None)
    assert r.kustomize_cmd() == ["kubectl", "kustomize"]
    monkeypatch.setattr(r.shutil, "which", lambda name: "/bin/x")
    assert r.kustomize_cmd() == ["kustomize", "build"]
