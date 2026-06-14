"""Tests for the stoa ComfyUI image + model-download Job.

Component 1 of the stoa Frank infra: the ComfyUI image bakes the stoa
custom nodes (pinned), the build workflow embeds a stoa node-set dimension
in the image tag, the Deployment pins the SAME tag (tag-drift guard), and a
declarative Job hydrates the models PVC.

Contract source of truth:
docs/superpowers/specs/2026-06-14-stoa-frank-infra-design.md

These assert SHAPE only (no network, no cluster). Generative quality is
measured at the live [manual] gates, not here.
"""
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "apps/comfyui/docker/Dockerfile"
WORKFLOW = REPO / ".github/workflows/build-comfyui.yml"
DEPLOYMENT = REPO / "apps/comfyui/manifests/deployment.yaml"
ENTRYPOINT = REPO / "apps/comfyui/docker/entrypoint.sh"
JOB = REPO / "apps/comfyui/manifests/job-model-download.yaml"

# Nodes are baked into a staging dir (NOT /app/custom_nodes, which the PVC
# shadows at runtime) and seeded into the PVC at boot by the entrypoint.
NODE_STAGE = "/opt/stoa-custom-nodes"

# The stoa custom-node upstreams that must be baked + pinned.
NODE_REPOS = [
    "Lightricks/ComfyUI-LTXVideo",
    "city96/ComfyUI-GGUF",
    "kijai/ComfyUI-WanVideoWrapper",
]
# At least one Kokoro node and one Fish-Speech node (repo name varies).
TTS_MARKERS = ["kokoro", "fish"]


def _workflow_env() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text())
    return doc["env"]


def _deployment_image_tag() -> str:
    for doc in yaml.safe_load_all(DEPLOYMENT.read_text()):
        if doc and doc.get("kind") == "Deployment":
            img = doc["spec"]["template"]["spec"]["containers"][0]["image"]
            return img.rsplit(":", 1)[1]
    raise AssertionError("no Deployment found in deployment.yaml")


def test_workflow_exposes_stoa_node_dimension():
    env = _workflow_env()
    assert "STOA_NODES" in env, "build-comfyui.yml env must pin a STOA_NODES rev"


def test_image_tag_embeds_stoa_dimension_and_matches_deployment():
    env = _workflow_env()
    expected = (
        f"comfyui-{env['COMFYUI_REF']}-pt{env['PYTORCH_VERSION']}"
        f"-{env['CUDA_VERSION_PIP']}-stoa{env['STOA_NODES']}"
    )
    # The workflow's pushed tag template must embed the stoa dimension.
    assert "stoa" in WORKFLOW.read_text(), "workflow tag must embed -stoa<N>"
    # The Deployment must pin the exact same tag the workflow renders (no drift).
    assert _deployment_image_tag() == expected, (
        f"deployment image tag {_deployment_image_tag()!r} != workflow tag {expected!r}"
    )


NODE_REF_KEYS = ["LTXVIDEO_REF", "GGUF_REF", "WANVIDEO_REF", "KOKORO_REF", "FISHSPEECH_REF"]
# A real pin: a 40-hex commit SHA or a version tag (vN.N / N.N). NOT a branch.
PINNED_RE = re.compile(r"^([0-9a-f]{40}|v?\d+\.\d+(\.\d+)?)$")
FLOATING = {"main", "master", "HEAD", "latest", "trunk", "develop"}


def test_dockerfile_bakes_pinned_video_nodes():
    text = DOCKERFILE.read_text()
    for repo in NODE_REPOS:
        assert repo in text, f"Dockerfile must clone {repo}"
    assert re.search(r"git .*checkout|--branch", text), "nodes must be checked out at a ref"
    assert "requirements.txt" in text, "node requirements.txt must be installed"


def test_node_refs_are_pinned_not_floating():
    """The 'never a floating default branch' guarantee, actually enforced."""
    env = _workflow_env()
    for key in NODE_REF_KEYS:
        ref = str(env[key])
        assert ref not in FLOATING, f"{key}={ref!r} is a floating branch — pin it"
        assert PINNED_RE.match(ref), f"{key}={ref!r} must be a 40-hex SHA or a version tag"
    # The Dockerfile ARG defaults must match the workflow pins (build determinism).
    dtext = DOCKERFILE.read_text()
    for key in NODE_REF_KEYS:
        assert f"ARG {key}={env[key]}" in dtext, f"Dockerfile ARG {key} must match the workflow pin"


def test_dockerfile_bakes_both_tts_engines():
    text = DOCKERFILE.read_text().lower()
    for marker in TTS_MARKERS:
        assert marker in text, f"Dockerfile must bake a {marker} TTS node"


def test_dockerfile_stages_nodes_outside_pvc_mount():
    text = DOCKERFILE.read_text()
    # Nodes must be cloned into the staging dir, not /app/custom_nodes (the PVC
    # mount shadows that path at runtime).
    assert NODE_STAGE in text, f"nodes must be baked into {NODE_STAGE} (PVC-shadow guard)"


def test_entrypoint_seeds_custom_nodes_from_stage():
    body = ENTRYPOINT.read_text()
    assert NODE_STAGE in body, "entrypoint must seed nodes from the staging dir"
    assert "custom_nodes" in body, "entrypoint must seed into /app/custom_nodes (the PVC)"
    # Idempotent seed: only copy a node when it's absent in the PVC.
    assert re.search(r"\[ -d|\[ ! -d|test -d", body), "node seed must be idempotent"


def test_model_download_job_shape():
    assert JOB.exists(), "apps/comfyui/manifests/job-model-download.yaml must exist"
    doc = next(
        d for d in yaml.safe_load_all(JOB.read_text()) if d and d.get("kind") == "Job"
    )
    spec = doc["spec"]["template"]["spec"]
    assert (
        spec["nodeSelector"]["kubernetes.io/hostname"] == "gpu-1"
    ), "model download must run on gpu-1"
    assert spec.get("restartPolicy") in ("OnFailure", "Never")
    # Mounts the comfyui-models PVC.
    claims = [
        v.get("persistentVolumeClaim", {}).get("claimName")
        for v in spec.get("volumes", [])
    ]
    assert "comfyui-models" in claims, "Job must mount the comfyui-models PVC"
    # Idempotent: the download script skips artefacts already present.
    body = JOB.read_text()
    assert re.search(r"\[ -f|\[ ! -f|test -f", body), "download must be skip-if-present"
    # All five stoa artefacts referenced.
    low = body.lower()
    for marker in ["ltx", "wan", "kokoro", "fish"]:
        assert marker in low, f"Job must download the {marker} artefact"
