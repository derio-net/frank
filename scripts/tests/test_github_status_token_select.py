"""github-status picks the GitHub token by the repo owner (spec section 3, R6).

Runs the Task's real shell script with curl stubbed on PATH, so the test
exercises what ships. Three orgs, three Secrets: a missing token for one org
must fail that TaskRun loudly and name the owner, never fall back to another
org's token (one App's token 404s on another org's repos, and a silent
fallback would also leak the wrong credential into the request).
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
TASK = REPO / "apps/tekton/tasks/github-status.yaml"

TOKENS = {
    "agentic-stoa": ("GITHUB_TOKEN", "tok-stoa"),
    "derio-homelab": ("GITHUB_TOKEN_DERIO_HOMELAB", "tok-homelab"),
    "derio-net": ("GITHUB_TOKEN_DERIO_NET", "tok-net"),
}


def _step() -> dict:
    task = yaml.safe_load(TASK.read_text())
    return task["spec"]["steps"][0]


def _run(tmp_path: Path, repo: str, env_tokens: dict[str, str]):
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    log = tmp_path / "curl.log"
    stub = stub_dir / "curl"
    # Records the Authorization header, writes a 201 body for -o, prints the code.
    stub.write_text(
        "#!/bin/sh\n"
        'out=""\n'
        'while [ $# -gt 0 ]; do\n'
        '  case "$1" in\n'
        '    -o) out="$2"; shift 2;;\n'
        f'    -H) case "$2" in Authorization*) echo "$2" >> {log};; esac; shift 2;;\n'
        f'    -X|-d|-w) [ "$1" = -d ] && echo "$2" >> {log}.body; shift 2;;\n'
        '    *) shift;;\n'
        "  esac\n"
        "done\n"
        '[ -n "$out" ] && echo "{}" > "$out"\n'
        "printf 201\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    env = {
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "REPO_FULL_NAME": repo,
        "REVISION": "a" * 40,
        "STATE": "success",
        "DESCRIPTION": "d",
        "CONTEXT": "gitea-actions/x",
        "TARGET_URL": "",
        "GITHUB_API_URL": "https://api.github.com",
        "BEST_EFFORT": "false",
        **env_tokens,
    }
    script = _step()["args"][0].replace("/tmp/resp", str(tmp_path / "resp"))
    proc = subprocess.run(
        ["/bin/sh", "-e", "-c", script], env=env, capture_output=True, text=True, cwd=tmp_path
    )
    sent = log.read_text().strip() if log.exists() else ""
    return proc, sent


def _all_tokens() -> dict[str, str]:
    return {var: value for var, value in TOKENS.values()}


@pytest.mark.parametrize("org", sorted(TOKENS))
def test_owner_selects_its_own_token(tmp_path: Path, org: str) -> None:
    proc, sent = _run(tmp_path, f"{org}/some-repo", _all_tokens())
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert sent == f"Authorization: token {TOKENS[org][1]}"


@pytest.mark.parametrize("org", ["derio-homelab", "derio-net"])
def test_missing_org_token_fails_naming_the_owner_and_sends_nothing(tmp_path: Path, org: str) -> None:
    tokens = _all_tokens()
    tokens[TOKENS[org][0]] = ""
    proc, sent = _run(tmp_path, f"{org}/some-repo", tokens)
    assert proc.returncode != 0
    assert org in proc.stdout + proc.stderr
    assert sent == "", "must not fall back to another org's token"


def test_unknown_owner_fails_loudly(tmp_path: Path) -> None:
    proc, sent = _run(tmp_path, "someone-else/x", _all_tokens())
    assert proc.returncode != 0
    assert "someone-else" in proc.stdout + proc.stderr
    assert sent == ""


def test_one_orgs_missing_token_does_not_blind_another(tmp_path: Path) -> None:
    tokens = _all_tokens()
    tokens["GITHUB_TOKEN_DERIO_NET"] = ""
    proc, sent = _run(tmp_path, "agentic-stoa/hum", tokens)
    assert proc.returncode == 0, proc.stderr
    assert sent == "Authorization: token tok-stoa"


def test_secret_refs_are_optional_for_the_new_orgs() -> None:
    env = {e["name"]: e for e in _step()["env"]}
    stoa = env["GITHUB_TOKEN"]["valueFrom"]["secretKeyRef"]
    assert (stoa["name"], stoa["key"]) == ("stoa-github-mirror", "token")
    assert not stoa.get("optional")
    for var, secret in (
        ("GITHUB_TOKEN_DERIO_HOMELAB", "derio-homelab-github-mirror"),
        ("GITHUB_TOKEN_DERIO_NET", "derio-net-github-mirror"),
    ):
        ref = env[var]["valueFrom"]["secretKeyRef"]
        assert (ref["name"], ref["key"], ref["optional"]) == (secret, "token", True)
