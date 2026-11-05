import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from render_all_images import find_unpinned, image_repo, is_ignored, is_unpinned  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "life"


def _bad(name):
    return find_unpinned((FIX / name).read_text())


def test_image_repo_strips_tag_and_digest_but_keeps_a_registry_port():
    assert image_repo("ghcr.io/derio-net/blog:bb12c2922c03") == "ghcr.io/derio-net/blog"
    assert image_repo("postgres:16-alpine@sha256:" + "a" * 64) == "postgres"
    assert image_repo("zot.local:5000/x/y:1.2.3") == "zot.local:5000/x/y"
    assert image_repo("zot.local:5000/x/y") == "zot.local:5000/x/y"


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
    assert find_unpinned(doc) == ["ghcr.io/team/app", "ghcr.io/x/tool:latest"]


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


# --- p1-r2: EXACT versions, not floating major/minor tags -----------------------------


def test_floating_tags_are_unpinned():
    for image in (
        "postgres:16", "postgres:16-alpine", "python:3.13-slim", "node:22-alpine",
        "caddy:2.9-alpine", "alpine:3.20", "busybox:1.37", "ghcr.io/x/y:2", "x:latest",
    ):
        assert is_unpinned(image), image


def test_exact_tags_are_pinned():
    for image in (
        "busybox:1.37.0", "python:3.13.18-slim", "node:22.23.3-alpine", "x:20260527",
        "ghcr.io/x/y:sha-d554c47", "ghcr.io/x/y:7cebcbb", "a/b:main-v1.83.14-stable.patch.1",
        "a@sha256:" + "0" * 64, "a:1.37@sha256:" + "0" * 64,
    ):
        assert not is_unpinned(image), image


def test_pin_exceptions_are_justified_and_live():
    import yaml

    data = yaml.safe_load((FIX / "pin-exceptions.yaml").read_text())
    entries = data["exceptions"]
    assert entries
    snapshot = (FIX / "rendered-images.txt").read_text().splitlines()
    for entry in entries:
        assert len(entry["reason"].strip()) > 20, entry
        assert entry["image"] in snapshot, f"stale exception {entry['image']}"


# --- p1-r1: R2 is enforced offline against git, not only against the snapshot ----------


def _snapshot_images():
    lines = (FIX / "rendered-images.txt").read_text().splitlines()
    return {line for line in lines if line and not line.startswith("#")}


@pytest.mark.slow
def test_git_resident_sources_render_pinned_offline():
    import render_all_images as r

    images, skipped, _ = r.collect_offline()
    assert skipped == [], skipped
    assert images, "no git-resident images rendered"
    assert sorted(i for i in images if r.is_unpinned(i)) == []


@pytest.mark.slow
def test_offline_images_are_in_the_snapshot_so_a_stale_snapshot_fails():
    import render_all_images as r

    images, _, _ = r.collect_offline()
    # Repositories, not refs: a tag moved by automation (blog deploys) is not drift.
    snapshot = {image_repo(i) for i in _snapshot_images()}
    assert sorted({image_repo(i) for i in images} - snapshot) == [], "regenerate: scripts/render_all_images.py"


@pytest.mark.slow
def test_offline_audit_goes_red_on_a_floating_image(tmp_path, monkeypatch):
    """Scratch copy of a manifest dir with `image: foo:latest` must be caught."""
    import render_all_images as r

    scratch = tmp_path / "m"
    scratch.mkdir()
    (scratch / "d.yaml").write_text(
        "kind: Deployment\nspec:\n  template:\n    spec:\n      containers:\n"
        "        - {name: a, image: 'foo:latest'}\n"
    )
    monkeypatch.setattr(r, "ROOT", tmp_path)
    app = {"metadata": {"name": "x"}, "spec": {"destination": {"namespace": "x"}}}
    out = r.render_source(app, {"path": "m"}, tmp_path)
    assert r.find_unpinned(out) == ["foo:latest"]


# --- stateful workloads never change bytes in this phase -------------------------------

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}


def _pod_spec(doc):
    spec = doc.get("spec") or {}
    if doc.get("kind") == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec")) or {}
    return (spec.get("template") or {}).get("spec") or (spec if doc.get("kind") == "Pod" else {})


def stateful_images(rendered_yaml):
    import yaml

    out = set()
    for doc in yaml.safe_load_all(rendered_yaml):
        if not isinstance(doc, dict) or doc.get("kind") not in WORKLOAD_KINDS:
            continue
        pod = _pod_spec(doc)
        spec = doc.get("spec") or {}
        stateful = bool(spec.get("volumeClaimTemplates")) or any(
            "persistentVolumeClaim" in v for v in pod.get("volumes") or []
        )
        if stateful:
            for c in (pod.get("containers") or []) + (pod.get("initContainers") or []):
                if isinstance(c.get("image"), str):
                    out.add(c["image"])
    return out


def test_stateful_workload_images_are_digest_pinned_or_excepted():
    import render_all_images as r

    images = set()
    for app in r.applications():
        for source in app["spec"].get("sources") or [app["spec"]["source"]]:
            if "path" not in source:
                continue
            import tempfile

            with tempfile.TemporaryDirectory() as td:
                images |= stateful_images(r.render_source(app, source, Path(td)))
    assert images, "no stateful git-resident workloads found"
    bad = sorted(i for i in images if "@sha256:" not in i and i not in r._pin_exceptions())
    assert bad == [], "stateful images must be digest-pinned (or justified in pin-exceptions.yaml)"
