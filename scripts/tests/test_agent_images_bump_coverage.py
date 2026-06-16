"""Guard: every agent-images image pinned in apps/ must be covered by the
agent-images bump workflow's allowlist.

The bump workflow (.github/workflows/agent-images-bump.yml) rewrites pinned
agent-image SHAs when agent-images publishes a new build. Coverage used to be a
hardcoded per-file `sed` list, so a NEW app pinning an agent-image was silently
skipped — alert-agent, n8n-01 and hermes-agent-shell all went stale this way.
This test fails if any 40-hex agent-image pin under apps/ names an image the
workflow does not bump, so the allowlist can never drift behind the manifests.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/agent-images-bump.yml"
APPS = REPO / "apps"

# ghcr.io/derio-net images NOT built by agent-images (so the bumper must NOT
# touch them) — exclude from the coverage requirement.
NON_AGENT_IMAGES = {"blog"}

PIN_RE = re.compile(r"ghcr\.io/derio-net/([a-z0-9-]+):[a-f0-9]{40}")


def _pinned_agent_images():
    names = set()
    for f in APPS.rglob("*.yaml"):
        names.update(PIN_RE.findall(f.read_text()))
    return names - NON_AGENT_IMAGES


def _workflow_covered_images():
    text = WORKFLOW.read_text()
    covered = set(re.findall(r"ghcr\.io/derio-net/([a-z0-9-]+):", text))  # literal sed targets
    m = re.search(r'AGENT_IMAGES="([^"]+)"', text)                        # the generalized allowlist
    if m:
        covered.update(m.group(1).split())
    return covered


def test_every_pinned_agent_image_is_bumped():
    pinned = _pinned_agent_images()
    covered = _workflow_covered_images()
    missing = pinned - covered
    assert not missing, (
        f"apps/ pins agent-image(s) the bump workflow does not cover: {sorted(missing)}. "
        f"Add them to AGENT_IMAGES in {WORKFLOW.relative_to(REPO)}."
    )


def test_multi_agent_shell_and_hermes_are_pinned_somewhere():
    # Sanity: the regression this guards is real — these apps exist and pin
    # agent-images, so the coverage assertion above is not vacuous.
    pinned = _pinned_agent_images()
    assert {"multi-agent-shell", "hermes-agent-shell"} <= pinned
