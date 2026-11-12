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


def test_every_headplane_env_var_is_a_known_override():
    # With overrides on, EVERY HEADPLANE_* var is merged into the config, and an
    # unexpected one can fail validation and stop the pod booting. Adding one
    # must be a deliberate, boot-tested change to this set.
    names = {n for n in _env() if n.startswith("HEADPLANE_")}
    assert names == {
        "HEADPLANE_LOAD_ENV_OVERRIDES",
        "HEADPLANE_SERVER__COOKIE_SECRET",
        # Boot-tested with overrides on (2026-11-12); read by the API-key
        # runbook's in-pod probe.
        "HEADPLANE_HEADSCALE_API_KEY",
    }


def test_sops_file_matches_the_reference_and_is_encrypted():
    doc = yaml.safe_load(SOPS_FILE.read_text())
    assert doc["kind"] == "Secret"
    assert doc["metadata"]["name"] == SECRET_NAME
    assert doc["metadata"]["namespace"] == "headscale-system"
    assert set(doc["stringData"]) == {SECRET_KEY}
    assert doc["stringData"][SECRET_KEY].startswith("ENC[")
    assert doc["sops"]["age"], "must be encrypted to the repo's age recipient"


def test_no_tracked_file_carries_a_literal_cookie_secret_value():
    result = subprocess.run(
        ["git", "grep", "-n", "-I", "-E", r"^[[:space:]]*cookie_secret:[[:space:]]*[^[:space:]]"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    # 0 = matches, 1 = none; anything else means the scan did not run.
    assert result.returncode in (0, 1), result.stderr
    assert result.returncode == 0, "expected at least the placeholder line to match"
    offenders = []
    for line in result.stdout.splitlines():
        path, lineno, text = line.split(":", 2)
        value = text.split("cookie_secret:", 1)[1].split("#", 1)[0].strip().strip("\"'")
        if value.startswith("<") or value == PLACEHOLDER:
            continue
        offenders.append(f"{path}:{lineno}")
    assert offenders == [], f"literal cookie_secret values in the tree: {offenders}"
