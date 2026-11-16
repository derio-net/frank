"""scripts/github_app_token.py: mint a narrowed, short-lived GitHub App
installation token on demand (fr ops identities, batch kid-laptops-mirror).

The ops gate needs GitHub credentials for two kid-laptops ops. Rather than pass a
long-lived, merge-capable PAT through to every probe, each op's identity mints a
~1h installation token of the homelab App narrowed to ONE repo and only the
permissions that op needs. These tests drive the script against a stub GitHub API
that verifies the RS256 JWT with the App's (throwaway) public key, so a wrong
signature, claim or request body fails here rather than at gate time.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "github_app_token.py"


@pytest.fixture(scope="module")
def keypair(tmp_path_factory):
    d = tmp_path_factory.mktemp("key")
    key, pub = d / "app.pem", d / "app.pub"
    subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
    subprocess.run(["openssl", "rsa", "-in", str(key), "-pubout", "-out", str(pub)], check=True, capture_output=True)
    return key, pub


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class _Stub:
    def __init__(self, pub: Path, status: int = 201, body: dict | None = None):
        self.pub, self.status, self.body = pub, status, body or {"token": "ghs_stubtoken", "expires_at": "x"}
        self.requests: list[dict] = []
        stub = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n) or b"{}")
                auth = self.headers.get("Authorization", "")
                stub.requests.append({"path": self.path, "auth": auth, "body": payload,
                                      "accept": self.headers.get("Accept", "")})
                ok = stub._verify(auth.removeprefix("Bearer "))
                code = stub.status if ok else 401
                out = json.dumps(stub.body if ok else {"message": "bad jwt"}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _verify(self, jwt: str) -> bool:
        try:
            h, p, s = jwt.split(".")
        except ValueError:
            return False
        tmp = Path(self.pub).with_suffix(".sig")
        tmp.write_bytes(_b64d(s))
        r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(self.pub), "-signature", str(tmp)],
                           input=f"{h}.{p}".encode(), capture_output=True)
        self.claims = json.loads(_b64d(p))
        self.header = json.loads(_b64d(h))
        return r.returncode == 0


def _run(keypair, stub, *extra, key_file=True):
    key, _ = keypair
    args = [sys.executable, str(SCRIPT), "--app-id", "4403773", "--install-id", "149345112",
            "--repo", "kid-laptops", "--perm", "repository_hooks=write", "--perm", "metadata=read", *extra]
    if key_file:
        args += ["--key-file", str(key)]
    return subprocess.run(args, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin:/usr/local/bin", "GITHUB_API": stub.url})


def test_mints_a_token_narrowed_to_one_repo_and_the_named_permissions(keypair):
    stub = _Stub(keypair[1])
    r = _run(keypair, stub)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "ghs_stubtoken\n"  # the token alone, nothing else on stdout
    (req,) = stub.requests
    assert req["path"] == "/app/installations/149345112/access_tokens"
    assert req["body"] == {"repositories": ["kid-laptops"],
                           "permissions": {"repository_hooks": "write", "metadata": "read"}}
    assert stub.header == {"alg": "RS256", "typ": "JWT"}
    assert stub.claims["iss"] == "4403773"
    now = time.time()
    assert stub.claims["iat"] <= now and stub.claims["exp"] - stub.claims["iat"] <= 600  # GitHub's 10 min cap


def test_a_rejected_mint_fails_without_printing_anything_on_stdout(keypair):
    stub = _Stub(keypair[1], status=422, body={"message": "permission repository_hooks not granted"})
    r = _run(keypair, stub)
    assert r.returncode != 0
    assert r.stdout == ""  # fr reads stdout as the credential; a failure must leave it empty
    assert "repository_hooks not granted" in r.stderr


def test_a_signature_from_the_wrong_key_is_refused(keypair, tmp_path):
    other = tmp_path / "other.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(other), "2048"], check=True, capture_output=True)
    stub = _Stub(keypair[1])
    r = subprocess.run([sys.executable, str(SCRIPT), "--app-id", "1", "--install-id", "2", "--repo", "x",
                        "--perm", "metadata=read", "--key-file", str(other)],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin:/usr/local/bin", "GITHUB_API": stub.url})
    assert r.returncode != 0 and r.stdout == ""


@pytest.mark.parametrize("perm", ["repository_hooks", "=write", "repository_hooks=admin", "a b=read"])
def test_malformed_permissions_are_refused_before_any_request(keypair, perm):
    stub = _Stub(keypair[1])
    key, _ = keypair
    r = subprocess.run([sys.executable, str(SCRIPT), "--app-id", "1", "--install-id", "2", "--repo", "x",
                        "--perm", perm, "--key-file", str(key)],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin:/usr/local/bin", "GITHUB_API": stub.url})
    assert r.returncode != 0 and r.stdout == "" and stub.requests == []


def test_the_key_comes_from_exactly_one_source(keypair):
    stub = _Stub(keypair[1])
    r = _run(keypair, stub, "--key-secret", "tekton-pipelines/github-app-homelab-key")
    assert r.returncode != 0 and stub.requests == []
    r = _run(keypair, stub, key_file=False)
    assert r.returncode != 0 and stub.requests == []


def test_ops_identities_use_the_minting_script_and_ops_need_them() -> None:
    """The two GitHub-side kid-laptops ops run under narrowed App identities, not a
    passed-through PAT."""
    import yaml

    repo = SCRIPT.parents[1]
    cfg = yaml.safe_load((repo / ".fr/ops.yaml").read_text())
    assert "GH_TOKEN" not in (cfg.get("env_passthrough") or []), "no repo-wide GH_TOKEN passthrough"
    ids = cfg["identities"]
    hooks = ids["homelab-kid-laptops-hooks"]["env"]["GH_TOKEN"]["from"]
    status = ids["homelab-kid-laptops-statuses"]["env"]["GH_TOKEN"]["from"]
    for cmd in (hooks, status):
        assert "scripts/github_app_token.py" in cmd and "--repo kid-laptops" in cmd
        assert "--key-secret tekton-pipelines/github-app-homelab-key" in cmd
    assert "--perm repository_hooks=write" in hooks and "statuses" not in hooks
    assert "--perm statuses=read" in status and "repository_hooks" not in status
    ops = {o["id"]: o for o in yaml.safe_load(
        (repo / "docs/superpowers/plans/2026-11-15--cicd--kid-laptops-mirror-pr-heads/ops.yaml").read_text())["ops"]}
    assert ops["webhook-pull-request"]["identities"] == ["homelab-kid-laptops-hooks"]
    assert ops["molecule-on-pr-head"]["identities"] == ["homelab-kid-laptops-statuses"]
    assert "app-webhooks-permission" in ops["webhook-pull-request"]["needs"]


def test_the_webhooks_grant_is_temporary_and_its_revocation_is_proven() -> None:
    """Narrowing to kid-laptops is per mint; the GRANT is installation-wide, so a
    PEM leak could mint hooks:write on every installed repo while it stands. The
    webhook PATCH is one-off, so the grant must be revoked after it, and the
    revoke op must prove revocation positively (a statuses mint still works, so a
    failing hooks mint is not just an unreadable key)."""
    import yaml

    repo = SCRIPT.parents[1]
    ops = {o["id"]: o for o in yaml.safe_load(
        (repo / "docs/superpowers/plans/2026-11-15--cicd--kid-laptops-mirror-pr-heads/ops.yaml").read_text())["ops"]}
    grant, revoke = ops["app-webhooks-permission"], ops["app-webhooks-permission-revoke"]
    assert "app-webhooks-permission-revoke" in str(grant["undo"])
    assert revoke["phase"] == "post-merge"
    assert "webhook-pull-request" in revoke["needs"]
    check = revoke["check"]
    assert "--perm metadata=read" in check and "! python3" in check and "repository_hooks=write" in check
    assert check.index("--perm metadata=read") < check.index("! python3"), "positive mint first"

