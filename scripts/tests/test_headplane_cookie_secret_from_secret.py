"""Guard: Headplane's session-signing key comes from a SOPS-managed Secret, not git.

Headplane 0.5.5 has no `server.cookie_secret_path`. The only non-file route is
its env overrides (`HEADPLANE_LOAD_ENV_OVERRIDES=true` +
`HEADPLANE_SERVER__COOKIE_SECRET`), which apply AFTER the file is validated, so
`files/config.yaml` must still carry a 32-character value. That value is a fixed,
deliberately non-secret placeholder. Verified against the real image
(2026-11-12): with overrides on, a session signed with the env value is
accepted and one signed with the file value is rejected.

The Secret itself is SOPS-encrypted under `secrets/hop/` and applied
out-of-band (manual-op `edge-hop-headplane-cookie-secret-rotation`); it is not
ArgoCD-managed. Context: ice#5.
"""

import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "clusters/hop/apps/headplane/manifests"
SOPS_FILE = REPO / "secrets/hop/headplane-cookie-secret.yaml"

PLACEHOLDER = "env-override-placeholder-0000000"
SECRET_NAME = "headplane-cookie-secret"
SECRET_KEY = "cookie-secret"


def _container():
    deploy = yaml.safe_load((APP / "deployment.yaml").read_text())
    (container,) = [c for c in deploy["spec"]["template"]["spec"]["containers"] if c["name"] == "headplane"]
    return container


def _env():
    return {e["name"]: e for e in _container().get("env", [])}


def test_placeholder_is_exactly_32_characters():
    # Headplane's schema is `32 <= string <= 32`; any other length fails boot.
    assert len(PLACEHOLDER) == 32


def test_config_file_carries_only_the_placeholder_and_secure_cookies():
    config = yaml.safe_load((APP / "files/config.yaml").read_text())
    assert config["server"]["cookie_secret"] == PLACEHOLDER
    assert config["server"]["cookie_secure"] is True


def test_env_overrides_are_enabled_and_feed_the_key_from_the_secret():
    env = _env()
    assert env["HEADPLANE_LOAD_ENV_OVERRIDES"]["value"] == "true"
    ref = env["HEADPLANE_SERVER__COOKIE_SECRET"]["valueFrom"]["secretKeyRef"]
    assert ref["name"] == SECRET_NAME
    assert ref["key"] == SECRET_KEY
    # A missing Secret must block the rollout, never boot on the placeholder.
    assert ref.get("optional", False) is False


def test_no_other_headplane_env_var_could_override_the_key():
    overriding = [n for n in _env() if n.startswith("HEADPLANE_SERVER__")]
    assert overriding == ["HEADPLANE_SERVER__COOKIE_SECRET"]


def test_sops_file_matches_the_reference_and_is_encrypted():
    doc = yaml.safe_load(SOPS_FILE.read_text())
    assert doc["kind"] == "Secret"
    assert doc["metadata"]["name"] == SECRET_NAME
    assert doc["metadata"]["namespace"] == "headscale-system"
    assert set(doc["stringData"]) == {SECRET_KEY}
    assert doc["stringData"][SECRET_KEY].startswith("ENC[")
    assert doc["sops"]["age"], "must be encrypted to the repo's age recipient"


def test_no_tracked_file_carries_a_literal_cookie_secret_value():
    tracked = subprocess.run(
        ["git", "grep", "-n", "-I", "-E", r"cookie_secret:[[:space:]]*[^[:space:]]", "--", ":!scripts/tests/"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    offenders = []
    for line in tracked:
        value = line.split("cookie_secret:", 1)[1].strip().strip("\"'")
        # Prose mentions (`server.cookie_secret` exactly 32 chars) are not assignments.
        if not value or value.startswith(("<", "`")) or " " in value or value == PLACEHOLDER:
            continue
        offenders.append(line.split(":", 2)[0] + ":" + line.split(":", 2)[1])
    assert offenders == [], f"literal cookie_secret values in the tree: {offenders}"
