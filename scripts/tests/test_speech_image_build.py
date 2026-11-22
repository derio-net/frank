"""Guards for the derived speech image (Blackwell-capable CTranslate2).

No upstream speaches image ships CTranslate2 >= 4.6.3 (sm_120 / RTX 5070 Ti), so
CI builds a derived image from apps/speech/docker/ on a digest-pinned base. The
Deployment pins the result by version tag, which must equal the workflow's
SPEECH_REV so a rebuild and a redeploy move together.
"""
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "apps/speech/docker/Dockerfile"
WORKFLOW = REPO / ".github/workflows/build-speech.yml"
DEPLOYMENT = REPO / "apps/speech/manifests/deployment.yaml"

MIN_CT2 = (4, 6, 3)


def _version(text):
    return tuple(int(p) for p in text.split(".")[:3])


def test_dockerfile_base_is_digest_pinned():
    froms = re.findall(r"^FROM\s+(\S+)", DOCKERFILE.read_text(), re.M)
    assert froms, "Dockerfile has no FROM"
    for ref in froms:
        assert re.search(r"@sha256:[0-9a-f]{64}$", ref), f"FROM {ref} is not pinned by digest"
    assert froms[0].startswith("ghcr.io/speaches-ai/speaches:")


def test_dockerfile_installs_blackwell_capable_ctranslate2():
    text = DOCKERFILE.read_text()
    pins = re.findall(r"ctranslate2(?:==|>=)\$?\{?([0-9][0-9.]*)", text)
    args = re.findall(r"^ARG\s+CTRANSLATE2_VERSION=([0-9.]+)", text, re.M)
    versions = pins + args
    assert versions, "Dockerfile does not pin ctranslate2"
    for v in versions:
        assert _version(v) >= MIN_CT2, f"ctranslate2 {v} predates sm_120 support (>= 4.6.3 needed)"
    # the RUN install must use the build arg (not a stale literal)
    assert re.search(r'"ctranslate2==\$\{CTRANSLATE2_VERSION\}"', text)


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def test_workflow_builds_on_docker_dir_and_pushes_speech_image():
    wf = _workflow()
    on = wf.get("on", wf.get(True))
    assert "apps/speech/docker/**" in on["push"]["paths"]
    assert "workflow_dispatch" in on
    text = WORKFLOW.read_text()
    assert re.search(r"IMAGE_NAME:\s*\$\{\{\s*github\.repository_owner\s*\}\}/speech\b", text)
    assert "context: apps/speech/docker" in text
    assert "${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ env.SPEECH_REV }}" in text
    assert "packages: write" in text


def _rev():
    rev = _workflow()["env"]["SPEECH_REV"]
    assert rev and ":" not in rev
    return str(rev)


def test_deployment_pin_equals_workflow_revision():
    dep = yaml.safe_load(DEPLOYMENT.read_text())
    image = dep["spec"]["template"]["spec"]["containers"][0]["image"]
    assert image == f"ghcr.io/derio-net/speech:{_rev()}"


def test_workflow_build_arg_matches_dockerfile_default_and_minimum():
    wf_ver = str(_workflow()["env"]["CTRANSLATE2_VERSION"])
    arg = re.search(r"^ARG\s+CTRANSLATE2_VERSION=([0-9.]+)", DOCKERFILE.read_text(), re.M).group(1)
    assert wf_ver == arg
    assert _version(wf_ver) >= MIN_CT2
    assert "CTRANSLATE2_VERSION=${{ env.CTRANSLATE2_VERSION }}" in WORKFLOW.read_text()


def test_workflow_rebuilds_when_it_changes():
    # a SPEECH_REV bump lives in the workflow file itself
    on = _workflow().get("on", _workflow().get(True))
    assert ".github/workflows/build-speech.yml" in on["push"]["paths"]


def test_dockerfile_blocks_reresync_and_checks_ctranslate2_at_build():
    text = DOCKERFILE.read_text()
    assert "UV_NO_SYNC=1" in text
    assert "import ctranslate2" in text


def test_workflow_actions_are_pinned_to_commit_shas():
    uses = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", WORKFLOW.read_text(), re.M)
    assert uses
    for ref in uses:
        assert re.search(r"@[0-9a-f]{40}$", ref), f"{ref} is not pinned to a commit SHA"


def test_image_ships_no_cuda_forward_compat_libcuda():
    """The CUDA 12.9 base ships cuda-compat-12-9 (libcuda 575.x) and the NVIDIA
    container toolkit registers /usr/local/cuda-12.9/compat in the linker cache
    at container start, ahead of the host driver (570.211.01, CUDA 12.8). Forward
    compatibility is datacenter-only, so on the RTX 5070 Ti every CUDA call
    failed with error 804 "forward compatibility was attempted on non supported
    HW" (2026-11-22, Test Plan step 2: all transcriptions 500). With the host
    libcuda the same CUDA 12.9 build runs (minor-version compatibility), measured
    in the pod: Whisper large-v3-turbo float16 loads and transcribes on sm_120.
    The image must therefore not carry a compat libcuda at all."""
    text = DOCKERFILE.read_text()
    root_block = text.split("USER root", 1)
    assert len(root_block) == 2, "the compat removal needs root"
    after_root = root_block[1].split("USER ubuntu", 1)[0]
    assert "rm -rf /usr/local/cuda-*/compat" in after_root
    assert "! ls /usr/local/cuda-*/compat/libcuda.so*" in after_root, "the build must fail if a compat libcuda survives"
    assert text.index("USER root") < text.index("USER ubuntu"), "drop back to the unprivileged user"


def test_compat_fix_moves_the_image_tag():
    assert _workflow()["env"]["SPEECH_REV"].endswith("-r2"), "the compat fix must redeploy: bump SPEECH_REV"
