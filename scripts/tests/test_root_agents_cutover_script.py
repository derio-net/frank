"""scripts/root-agents-cutover.sh: the devops ops of plan 2026-11-14--auth--root-agents-least-privilege call it.

Static checks on the script text, plus behaviour against a FAKE kubectl on PATH: the real script is only
ever run by the operator after merge, and never touches a cluster from here.
"""
import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/root-agents-cutover.sh"
SUBCOMMANDS = ("matrix", "verify", "move-membership", "membership", "token-review")

# A fake kubectl. `create -f - ... jsonpath` answers a SubjectAccessReview from FAKE_POLICY:
#   good   = the intended policy (root-agents read-only, root-admins everything, masters everything)
#   broken = root-agents may read Secrets in argocd
#   deaf   = everything is allowed (an API that ignores the subject, like `can-i --as` through the Omni proxy)
#   nomasters = the system:masters control answers denied
FAKE = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
if a[:1] == ["exec"]:
    print(os.environ.get("FAKE_MEMBERSHIP", "GROUPS=root-agents")); sys.exit(0)
if a[:1] == ["create"]:
    sar = json.load(sys.stdin)
    if sar.get("kind") == "TokenReview":
        print(os.environ.get("FAKE_TOKEN_AUTH", "true") + "|" + os.environ.get("FAKE_TOKEN_USER", "authentik:claude-agent")
              + "|" + os.environ.get("FAKE_TOKEN_GROUPS", '["system:authenticated"]')); sys.exit(0)
    assert sar["apiVersion"] == "authorization.k8s.io/v1" and sar["kind"] == "SubjectAccessReview", sar
    s = sar["spec"]; groups = s.get("groups", []); ra = s.get("resourceAttributes", {})
    pol = os.environ.get("FAKE_POLICY", "good")
    if "system:masters" in groups:
        print("false" if pol == "nomasters" else "true"); sys.exit(0)
    if pol == "deaf":
        print("true"); sys.exit(0)
    if "root-admins" in groups:
        print("true"); sys.exit(0)
    res, verb, ns = ra.get("resource", ""), ra.get("verb", ""), ra.get("namespace", "")
    if pol == "broken" and res == "secrets" and ns == "argocd":
        print("true"); sys.exit(0)
    protected = {"upgrade-sessions", "cluster-update-fr", "runs-fr"}
    ok = verb in ("get", "list") and res in ("pods", "configmaps", "nodes") and ns not in protected
    print("true" if ok else "false"); sys.exit(0)
sys.exit(0)
'''


@pytest.fixture
def env(tmp_path):
    kc = tmp_path / "kubectl"
    kc.write_text(FAKE)
    kc.chmod(kc.stat().st_mode | stat.S_IEXEC)
    curl = tmp_path / "curl"
    curl.write_text("#!/bin/sh\ncat >/dev/null\nprintf '%s' '{\"access_token\":\"fake-access-token\"}'\n")
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    e = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}", KUBECONFIG=str(tmp_path / "none"))
    return e


def run(sub, env, **extra):
    return subprocess.run(["bash", str(SCRIPT), sub], capture_output=True, text=True, env={**env, **extra})


def test_script_exists_and_parses():
    assert SCRIPT.exists()
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0
    assert "set -euo pipefail" in SCRIPT.read_text()


def test_every_subcommand_is_dispatched():
    text = SCRIPT.read_text()
    for sub in SUBCOMMANDS:
        assert re.search(rf"^\s*{sub}\)", text, re.M), sub


def test_uses_server_side_sar_with_a_masters_control_not_can_i():
    text = SCRIPT.read_text()
    assert "kubectl auth can-i" not in text
    assert "authorization.k8s.io/v1" in text and "SubjectAccessReview" in text
    assert "kubectl create -f -" in text and ".status.allowed" in text
    assert "system:masters" in text


def test_never_echoes_a_token():
    text = SCRIPT.read_text()
    assert "set -x" not in text
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        assert not re.search(r"(echo|printf)\b[^|]*\$\{?(TOKEN|token|access_token|SECRET)", line), line
    assert "token-review" in text and "groups" in text


def test_matrix_prints_cells_and_the_control(env):
    r = run("matrix", env)
    assert r.returncode == 0, r.stderr
    assert "root-agents" in r.stdout and "root-admins" in r.stdout and "system:masters" in r.stdout
    assert "secrets" in r.stdout and "upgrade-sessions" in r.stdout


def test_verify_passes_on_the_intended_policy(env):
    r = run("verify", env, FAKE_POLICY="good")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("policy", ["broken", "deaf", "nomasters"])
def test_verify_fails_on_a_wrong_policy(env, policy):
    assert run("verify", env, FAKE_POLICY=policy).returncode != 0, policy


def test_membership_requires_only_root_agents(env):
    assert run("membership", env, FAKE_MEMBERSHIP="GROUPS=root-agents").returncode == 0
    assert run("membership", env, FAKE_MEMBERSHIP="GROUPS=root-admins,root-agents").returncode != 0
    assert run("membership", env, FAKE_MEMBERSHIP="GROUPS=").returncode != 0


def test_token_review_refuses_root_admins_and_prints_no_token(env):
    secret = "s3cr3t-value-xyz"
    base = dict(K8S_AGENT_CLIENT_SECRET=secret, FAKE_TOKEN_GROUPS='["system:authenticated","root-admins"]')
    r = run("token-review", env, **base)
    assert r.returncode != 0 and secret not in r.stdout + r.stderr
    ok = run("token-review", env, K8S_AGENT_CLIENT_SECRET=secret, FAKE_TOKEN_GROUPS='["system:authenticated","root-agents"]')
    assert ok.returncode == 0, ok.stderr
    assert "root-agents" in ok.stdout and "fake-access-token" not in ok.stdout + ok.stderr and secret not in ok.stdout
    assert run("token-review", env).returncode != 0  # no client secret configured
    # an unauthenticated review proves nothing, even with empty groups
    bad = run("token-review", env, K8S_AGENT_CLIENT_SECRET=secret, FAKE_TOKEN_AUTH="", FAKE_TOKEN_GROUPS="")
    assert bad.returncode != 0 and "not authenticated" in bad.stderr
    # the resolved user is printed, so the operator sees which identity the review exercised
    assert "claude-agent" in ok.stdout
    # username mode needs the password too
    assert run("token-review", env, K8S_AGENT_CLIENT_SECRET=secret, K8S_AGENT_USERNAME="claude-agent").returncode != 0
