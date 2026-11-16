#!/usr/bin/env python3
"""Mint a narrowed, short-lived GitHub App installation token and print it.

Used as an fr ops identity `from:` command (.fr/ops.yaml): each GitHub-side op
gets a ~1h installation token of the App, narrowed to ONE repository and only
the permissions that op needs, minted at check/apply time. Nothing long-lived is
stored or passed through, unlike a PAT in the probe environment.

  python3 scripts/github_app_token.py --app-id 4403773 --install-id 149345112 \
      --key-secret tekton-pipelines/github-app-homelab-key \
      --repo kid-laptops --perm repository_hooks=write --perm metadata=read

The App's private key is read live from a Kubernetes Secret (`ns/name[:key]`,
key defaults to `key`) with the caller's kubeconfig, or from `--key-file`.
stdout carries the token and nothing else; on any failure stdout stays empty
and the reason goes to stderr (fr reads stdout as the credential).

Stdlib only; signs the RS256 JWT with `openssl`. `GITHUB_API` overrides the API
base for tests.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PERM_RE = re.compile(r"^([a-z_]+)=(read|write)$")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _fail(msg: str) -> None:
    print(f"github_app_token: {msg}", file=sys.stderr)
    sys.exit(1)


def _read_key(args: argparse.Namespace) -> bytes:
    if args.key_file:
        with open(args.key_file, "rb") as f:
            return f.read()
    ref, _, field = args.key_secret.partition(":")
    ns, _, name = ref.partition("/")
    if not ns or not name:
        _fail("--key-secret must be <namespace>/<name>[:<key>]")
    field = field or "key"
    r = subprocess.run(
        ["kubectl", "-n", ns, "get", "secret", name, "-o", f"jsonpath={{.data.{field}}}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        _fail(f"cannot read secret {ns}/{name} key {field}: {r.stderr.strip() or 'empty'}")
    return base64.b64decode(r.stdout.strip())


def _jwt(app_id: str, pem: bytes) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    # iat backdated 60s for clock skew; exp within GitHub's 10-minute cap.
    claims = _b64(json.dumps({"iat": now - 60, "exp": now + 480, "iss": app_id}, separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode()
    fd, keypath = tempfile.mkstemp(prefix="gh-app-", suffix=".pem")
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, pem)
        os.close(fd)
        r = subprocess.run(["openssl", "dgst", "-sha256", "-sign", keypath],
                           input=signing_input, capture_output=True)
    finally:
        os.unlink(keypath)
    if r.returncode != 0:
        _fail(f"openssl could not sign the JWT: {r.stderr.decode(errors='replace').strip()}")
    return f"{header}.{claims}.{_b64(r.stdout)}"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--app-id", required=True)
    p.add_argument("--install-id", required=True)
    p.add_argument("--repo", required=True, help="repository NAME (no owner) the token is narrowed to")
    p.add_argument("--perm", action="append", required=True, help="permission=read|write (repeatable)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--key-secret", help="<namespace>/<name>[:<key>] holding the App PEM")
    src.add_argument("--key-file", help="path to the App PEM")
    try:
        args = p.parse_args(argv)
    except SystemExit as e:  # argparse prints usage to stderr; keep stdout empty
        sys.exit(e.code or 2)

    perms: dict[str, str] = {}
    for spec in args.perm:
        m = PERM_RE.match(spec)
        if not m:
            _fail(f"bad --perm {spec!r}: want <name>=read|write")
        perms[m.group(1)] = m.group(2)

    jwt = _jwt(args.app_id, _read_key(args))
    api = os.environ.get("GITHUB_API", "https://api.github.com").rstrip("/")
    req = urllib.request.Request(
        f"{api}/app/installations/{args.install_id}/access_tokens",
        data=json.dumps({"repositories": [args.repo], "permissions": perms}).encode(),
        headers={"Authorization": f"Bearer {jwt}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            token = json.loads(resp.read()).get("token")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("message", "")
        except ValueError:
            msg = ""
        _fail(f"GitHub refused the mint (HTTP {e.code}): {msg}")
    except (urllib.error.URLError, TimeoutError) as e:
        _fail(f"GitHub unreachable: {e}")
    if not token:
        _fail("GitHub returned no token")
    print(token)


if __name__ == "__main__":
    main()
