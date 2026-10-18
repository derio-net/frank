"""Guard: scripts/ci_gate_coverage.py (spec 2026-10-18 section 6)."""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ci_gate_coverage as cgc  # noqa: E402

FIX = REPO_ROOT / "scripts/tests/fixtures/ci_gate_coverage"
RUNNER_CONFIG = REPO_ROOT / "apps/gitea-runner/manifests/files/config.yaml"
LABELS = {"ubuntu-latest", "ubuntu-24.04"}


def _run(name, tier="github-preferred", secrets=()):
    files = {name: (FIX / name).read_text()}
    return {
        (f.job, f.verdict) for f in cgc.check_workflows(files, tier, list(secrets), LABELS)
    }


def test_fully_gated_job_is_ok():
    assert _run("ok-gated.yml") == {("check", "ok")}


def test_ungated_job():
    assert _run("ungated.yml") == {("check", "ungated")}


def test_github_pinned_macos_is_ok():
    assert _run("pinned-macos.yml") == {("build", "ok")}


def test_unserved_label():
    assert ("check", "fallback-on-unserved-label") in _run("unserved-label.yml")


def test_runs_on_expression():
    assert ("check", "fallback-runs-on-expression") in _run("runs-on-expression.yml")


def test_secret_not_mirrored_then_mirrored():
    assert ("check", "fallback-secret-not-mirrored") in _run("secret-deploy-key.yml")
    assert _run("secret-deploy-key.yml", secrets=["DEPLOY_KEY"]) == {("check", "ok")}


def test_github_token_to_github():
    assert ("check", "fallback-github-token-to-github") in _run("github-token.yml")


def test_missing_rerun_triggers():
    got = _run("missing-rerun.yml")
    assert ("", "missing-rerun-triggers") in got
    assert ("check", "ok") in got


def test_existing_if_joined_by_and_is_ok():
    assert _run("and-joined.yml") == {("check", "ok")}


def test_exact_gate_expression_is_ok():
    assert _run("exact-gate.yml") == {("check", "ok")}


def test_gitea_only_requires_a_gate_on_every_job():
    assert _run("ungated.yml", tier="gitea-only") == {("check", "ungated")}
    assert _run("ok-gated.yml", tier="gitea-only") == {("check", "ok")}
    assert _run("pinned-macos.yml", tier="gitea-only") == {("build", "ok")}


def test_github_only_is_not_checked():
    assert _run("ungated.yml", tier="github-only") == set()


def test_runner_labels_of_real_config():
    assert cgc.runner_labels(RUNNER_CONFIG.read_text()) == {"ubuntu-latest", "ubuntu-24.04"}


def test_cli_exit_codes(tmp_path):
    import subprocess

    wf = tmp_path / ".github/workflows"
    wf.mkdir(parents=True)
    (wf / "a.yml").write_text((FIX / "ungated.yml").read_text())
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/ci_gate_coverage.py"), str(tmp_path),
         "--tier", "github-preferred", "--runner-config", str(RUNNER_CONFIG)],
        capture_output=True, text=True,
    )
    assert r.returncode == 1 and "ungated" in r.stdout
    (wf / "a.yml").write_text((FIX / "ok-gated.yml").read_text())
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/ci_gate_coverage.py"), str(tmp_path),
         "--tier", "github-preferred", "--runner-config", str(RUNNER_CONFIG)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout
