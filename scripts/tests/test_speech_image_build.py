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
    assert "ctranslate2" in text and "pip install" in text


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
