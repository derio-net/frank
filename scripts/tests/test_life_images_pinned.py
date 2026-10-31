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


# --- p1-r4: exemptions are explicit, visible, and narrow -------------------------------


def test_disabled_skip_only_for_known_operator_components():
    from render_all_images import rendered_images

    doc = (
        "spec:\n"
        "  vgpuManager: {enabled: false, image: vgpu-manager}\n"
        "  somethingElse: {enabled: false, image: 'ghcr.io/x/y:latest'}\n"
    )
    exempt: list[str] = []
    images = rendered_images(doc, exempt)
    assert "ghcr.io/x/y:latest" in images and "vgpu-manager" not in images
    assert any(e.startswith("disabled-component vgpuManager") for e in exempt)


def test_images_embedded_in_strings_are_audited():
    doc = (
        "kind: ConfigMap\n"
        "data:\n"
        "  script: |\n"
        "    docker run --rm ghcr.io/x/tool:latest --help\n"
        "    curl https://github.com/org/repo:foo\n"
        "  env: ghcr.io/team/app\n"
    )
    assert find_unpinned(doc) == ["ghcr.io/x/tool:latest", "ghcr.io/team/app"]


def test_unresolved_and_hook_exemptions_are_recorded():
    from render_all_images import rendered_images

    doc = (
        "kind: Pod\nmetadata: {name: t, annotations: {helm.sh/hook: test}}\n"
        "spec: {containers: [{image: busybox}]}\n---\n"
        "kind: Pod\nspec: {containers: [{image: '$(params.x)'}]}\n"
    )
    exempt: list[str] = []
    rendered_images(doc, exempt)
    assert "helm-test-hook Pod/t" in exempt
    assert "unresolved $(params.x)" in exempt


def test_committed_exemptions_file_is_non_silent():
    lines = (FIX / "audit-exemptions.txt").read_text().splitlines()
    kinds = {line.split(" ", 1)[0] for line in lines if line and not line.startswith("#")}
    assert {"helm-test-hook", "disabled-component"} <= kinds
