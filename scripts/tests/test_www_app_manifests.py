"""Tripwire: the Hop `www` app keeps the shape the edge assumes.

www.derio.net is served by a container on Hop behind the edge Caddy. Three
things about that deployment are load-bearing and easy to break by hand:

1. The image tag is CI-owned. `site-promotion` (apps/tekton/pipelines/) rewrites
   it after every build of agentic-stoa/site. A hand-pinned tag looks fine in
   git and then silently stops tracking reality — the same failure the blog
   deployment's marker comment exists to prevent.

2. The port is 8080 everywhere — container, Service and the edge reverse_proxy.
   The site image's runtime stage is caddy:2.9-alpine on :8080 (blog parity).
   A drift here presents as a networking fault, not a config error.

3. The app is wired into Hop's App-of-Apps. Manifests that no Application CR
   points at are inert, and nothing surfaces that.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WWW_DIR = REPO_ROOT / "clusters/hop/apps/www/manifests"
ROOT_TEMPLATES = REPO_ROOT / "clusters/hop/apps/root/templates"

IMAGE_REPO = "ghcr.io/agentic-stoa/site"
NAMESPACE = "www-system"
PORT = 8080


def _load(path: Path) -> dict:
    assert path.is_file(), f"missing manifest: {path.relative_to(REPO_ROOT)}"
    return yaml.safe_load(path.read_text())


def test_deployment_shape() -> None:
    dep = _load(WWW_DIR / "deployment.yaml")

    assert dep["kind"] == "Deployment"
    assert dep["metadata"]["namespace"] == NAMESPACE

    containers = dep["spec"]["template"]["spec"]["containers"]
    assert len(containers) == 1, "www is a single-container static server"
    c = containers[0]

    image = c["image"]
    assert image.startswith(f"{IMAGE_REPO}:"), f"unexpected image repo: {image}"
    tag = image.split(":", 1)[1]
    assert len(tag) == 40 and all(ch in "0123456789abcdef" for ch in tag), (
        f"image must be pinned to a 40-char commit sha, got {tag!r} — "
        "floating tags break GitOps determinism"
    )

    ports = c["ports"]
    assert [p["containerPort"] for p in ports] == [PORT]

    probe = c.get("readinessProbe")
    assert probe, "no readinessProbe — a broken build would take traffic"
    assert probe["httpGet"]["path"] == "/"


def test_image_pin_carries_the_ci_owned_marker() -> None:
    """The marker is the only signal to a human that CI owns this line.

    Asserted against raw text because YAML parsing discards comments.
    """
    raw = (WWW_DIR / "deployment.yaml").read_text()
    image_lines = [ln for ln in raw.splitlines() if IMAGE_REPO in ln]
    assert image_lines, "no image line found"
    assert any("updated by CI" in ln for ln in image_lines), (
        "the image line must carry the CI-ownership marker used by the blog "
        "deployment, or someone will hand-pin it"
    )


def test_service_targets_the_container_port() -> None:
    svc = _load(WWW_DIR / "service.yaml")
    assert svc["kind"] == "Service"
    assert svc["metadata"]["namespace"] == NAMESPACE
    port = svc["spec"]["ports"][0]
    assert port["port"] == PORT, "edge Caddy reverse_proxies to :8080"

    dep = _load(WWW_DIR / "deployment.yaml")
    assert svc["spec"]["selector"] == dep["spec"]["selector"]["matchLabels"], (
        "Service selector must match the Deployment's pod labels"
    )


def test_app_is_wired_into_hop_app_of_apps() -> None:
    """Manifests with no Application CR pointing at them never deploy.

    The root templates carry Helm placeholders ({{ .Values.repoURL }}), which
    are not valid YAML, so this asserts on raw text rather than parsing.
    """
    app = (ROOT_TEMPLATES / "www.yaml").read_text()
    assert "kind: Application" in app
    assert "path: clusters/hop/apps/www/manifests" in app
    assert f"namespace: {NAMESPACE}" in app
    # Same guarantees the rest of the Hop estate relies on.
    assert "selfHeal: true" in app
    assert "prune: false" in app
    assert "ServerSideApply=true" in app

    # The namespace is templated directly by the root chart (same as ns-blog),
    # not wrapped in its own Application.
    ns = _load(ROOT_TEMPLATES / "ns-www.yaml")
    assert ns["kind"] == "Namespace"
    assert ns["metadata"]["name"] == NAMESPACE
    assert ns["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "baseline"
