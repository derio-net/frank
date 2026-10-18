"""Guard: scripts/ci_gate_coverage.py (spec 2026-10-18 section 6)."""

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ci_gate_coverage as cgc  # noqa: E402

FIX = REPO_ROOT / "scripts/tests/fixtures/ci_gate_coverage"
RUNNER_CONFIG = REPO_ROOT / "apps/gitea-runner/manifests/files/config.yaml"
LABELS = {"ubuntu-latest", "ubuntu-24.04"}


def _run(name, tier="github-preferred", secrets=(), extra=()):
    files = {n: (FIX / n).read_text() for n in (name, *extra)}
    return {
        (f.job, f.verdict)
        for f in cgc.check_workflows(files, tier, list(secrets), LABELS)
        if f.workflow == name
    }


OK = {("check", "ok")}

# fixture -> exact expected (job, verdict) set under tier github-preferred
CASES = {
    "ok-gated.yml": OK,
    "ungated.yml": {("check", "ungated")},
    "pinned-macos.yml": {("build", "ok")},
    "unserved-label.yml": {("check", "fallback-on-unserved-label")},
    "runs-on-expression.yml": {("check", "fallback-runs-on-expression")},
    "secret-deploy-key.yml": {("check", "fallback-secret-not-mirrored")},
    "github-token.yml": {("check", "fallback-github-token-to-github")},
    "missing-rerun.yml": {("", "missing-rerun-triggers"), ("check", "ok")},
    "and-joined.yml": OK,
    "exact-gate.yml": OK,
    # p1-r1/r2: gate parsing
    "gate-near-miss.yml": {("check", "malformed-gate")},
    "gate-lowercase.yml": {("check", "malformed-gate")},
    "gate-no-default.yml": {("check", "malformed-gate")},
    "gate-or.yml": {("check", "malformed-gate")},
    "gate-negated.yml": {("check", "malformed-gate")},
    "pin-or-true.yml": {("check", "ungated")},
    "pin-paren-and.yml": OK,
    # p1-r3/r4: rerun triggers
    "on-list-push.yml": OK,
    "on-str-push.yml": OK,
    "push-tags-only.yml": {("", "missing-rerun-triggers"), ("check", "ok")},
    "push-null.yml": OK,
    "push-empty-dict.yml": OK,
    "branches-ignore-ok.yml": OK,
    "branches-ignore-hit.yml": {("", "missing-rerun-triggers"), ("check", "ok")},
    "branches-one-only.yml": {("", "missing-rerun-triggers"), ("check", "ok")},
    "branches-star-glob.yml": OK,
    "push-only-no-pr.yml": {("", "missing-rerun-triggers"), ("check", "ok")},
    "push-only-with-sync.yml": OK,
    # p1-r5/r6: secrets and tokens
    "wf-env-secret.yml": {("check", "fallback-secret-not-mirrored")},
    "wf-defaults-secret.yml": {("check", "fallback-secret-not-mirrored")},
    "wf-env-token.yml": {("check", "fallback-github-token-to-github")},
    "token-backtick.yml": {("check", "fallback-github-token-to-github")},
    "token-github-script.yml": {("check", "fallback-github-token-to-github")},
    "secret-bracket.yml": {("check", "fallback-secret-not-mirrored")},
    "token-benign.yml": OK,
    # p1-r7: reusable workflows
    "reusable-inherit.yml": {("check", "fallback-secret-not-mirrored")},
    "reusable-local-bad.yml": {("check", "fallback-on-unserved-label")},
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_fixture_verdicts(name):
    extra = [n for n in ("callee-ok.yml", "callee-bad.yml") if n in (FIX / name).read_text()]
    assert _run(name, extra=extra) == CASES[name]


def test_secret_mirrored_is_ok():
    assert _run("secret-deploy-key.yml", secrets=["DEPLOY_KEY"]) == OK
    assert _run("secret-bracket.yml", secrets=["DEPLOY_KEY"]) == OK
    assert _run("wf-env-secret.yml", secrets=["DEPLOY_KEY"]) == OK


def test_inherit_detail():
    files = {n: (FIX / n).read_text() for n in ("reusable-inherit.yml", "callee-ok.yml")}
    fs = cgc.check_workflows(files, "github-preferred", ["DEPLOY_KEY"], LABELS)
    inh = [f for f in fs if f.workflow == "reusable-inherit.yml"]
    assert [f.detail for f in inh] == ["inherit"]


def test_gitea_only_requires_a_gate_on_every_job():
    assert _run("ungated.yml", tier="gitea-only") == {("check", "ungated")}
    assert _run("ok-gated.yml", tier="gitea-only") == OK
    assert _run("pinned-macos.yml", tier="gitea-only") == {("build", "ok")}


def test_github_only_is_not_checked():
    assert _run("ungated.yml", tier="github-only") == set()


def test_load_checkout_reads_both_workflow_dirs(tmp_path):
    for d in (".github/workflows", ".gitea/workflows"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "a.yml").write_text("name: x\njobs: {}\n")
    got = cgc.load_checkout(tmp_path)
    assert set(got) == {".github/workflows/a.yml", ".gitea/workflows/a.yml"}


def test_runner_labels_of_real_config():
    assert cgc.runner_labels(RUNNER_CONFIG.read_text()) == {"ubuntu-latest", "ubuntu-24.04"}


def test_ubuntu_2404_label_maps_to_its_own_tag():
    labels = yaml.safe_load(RUNNER_CONFIG.read_text())["runner"]["labels"]
    assert "ubuntu-24.04:docker://gitea/runner-images:ubuntu-24.04" in labels


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
