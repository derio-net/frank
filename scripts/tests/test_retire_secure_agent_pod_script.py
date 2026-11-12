"""Tests for scripts/retire-secure-agent-pod.sh (retire-vk Phase 2, R9).

The script is driven against a stub `kubectl` (KUBECTL env var) that runs the
remote argv locally against a fixture standing in for the pod's home
(POD_HOME), except `ps`, whose output the test supplies. Nothing here touches a
cluster, and every destination lives under tmp_path, outside any git work tree.
"""
import os
import subprocess
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/retire-secure-agent-pod.sh"

STUB = """#!/usr/bin/env bash
# stub kubectl: `kubectl -n NS exec deploy/X -c C -- <argv>` runs <argv> locally.
while [ "$1" != "--" ]; do shift; done
shift
if [ "$1" = ps ]; then cat "$STUB_PS"; exit 0; fi
exec "$@"
"""


def _env(tmp_path, ps="bash\nclaude remote-control\n", home=None):
    stub = tmp_path / "kubectl"
    stub.write_text(STUB)
    stub.chmod(0o755)
    psf = tmp_path / "ps.txt"
    psf.write_text(ps)
    env = {**os.environ, "KUBECTL": str(stub), "STUB_PS": str(psf)}
    if home is not None:
        env["POD_HOME"] = str(home)
    return env


def _run(*args, env, cwd=None):
    return subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, cwd=cwd,
        capture_output=True, text=True,
    )


def _fixture_home(tmp_path):
    home = tmp_path / "home"
    for rel, body in {
        "interviews/a.txt": "x",
        "orgs/o.txt": "y",
        ".hermes/h": "z",
        ".willikins-agent/audit-archive/a": "a",
        ".local/share/vibe-kanban/db.v2.sqlite": "db",
        "repos/willikins/scripts/chorebot/config.yaml": "k: v",
        "orgs/node_modules/skip.js": "no",
    }.items():
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return home


def _git(*a, cwd):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def test_script_is_valid_bash_and_usage_exits_2():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 2
    for sub in ("archive", "verify", "key-fingerprint"):
        assert sub in r.stderr


def test_credential_paths_only_appear_in_the_exclude_list():
    for needle in ("credentials.json", "server_ed25519_signing_key", ".ssh",
                   ".gnupg", ".config/gh", ".claude.json"):
        lines = [l for l in SCRIPT.read_text().splitlines() if needle in l]
        assert lines, needle
        assert all("--exclude" in l for l in lines), (needle, lines)


def test_archive_refuses_a_destination_inside_a_git_work_tree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    dest = repo / "arch"
    r = _run("archive", "--dest", str(dest), env=_env(tmp_path, home=_fixture_home(tmp_path)))
    assert r.returncode != 0
    assert "git work tree" in r.stderr
    assert not dest.exists()
    assert not any(p.name != ".git" for p in repo.iterdir())


def test_archive_refuses_a_loose_destination_mode(tmp_path):
    dest = tmp_path / "arch"
    dest.mkdir()
    dest.chmod(0o755)
    r = _run("archive", "--dest", str(dest), env=_env(tmp_path, home=_fixture_home(tmp_path)))
    assert r.returncode != 0
    assert "700" in r.stderr
    assert list(dest.iterdir()) == []


def test_archive_refuses_while_an_interactive_session_runs(tmp_path):
    dest = tmp_path / "arch"
    env = _env(tmp_path, ps="bash\nclaude remote-control\nclaude --resume abc\n",
               home=_fixture_home(tmp_path))
    r = _run("archive", "--dest", str(dest), env=env)
    assert r.returncode != 0
    assert "interactive session still running" in r.stderr
    assert not dest.exists()


def test_remote_control_alone_does_not_block_and_archive_verifies(tmp_path):
    home = _fixture_home(tmp_path)
    clone = home / "repos/willikins"
    _git("init", "-q", "-b", "main", cwd=clone)
    (clone / "f").write_text("1")
    _git("add", "f", cwd=clone)
    _git("commit", "-qm", "one", cwd=clone)
    dest = tmp_path / "arch"
    env = _env(tmp_path, home=home)
    r = _run("archive", "--dest", str(dest), env=env)
    assert r.returncode == 0, r.stderr
    assert oct(dest.stat().st_mode & 0o777) == "0o700"
    names = tarfile.open(dest / "secure-agent-pod-home.tar.gz").getnames()
    assert any(n.endswith("chorebot/config.yaml") for n in names)
    assert not any("node_modules" in n for n in names)
    # a local-only commit (no remotes at all) is bundled
    assert list((dest / "bundles").glob("*.bundle"))
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout + v.stderr
    assert "FAIL" not in v.stdout


def test_session_ended_confirmed_overrides_the_process_check(tmp_path):
    dest = tmp_path / "arch"
    env = _env(tmp_path, ps="claude --resume abc\n", home=_fixture_home(tmp_path))
    r = _run("archive", "--dest", str(dest), "--session-ended-confirmed", env=env)
    assert r.returncode == 0, r.stderr


def _good_archive(tmp_path):
    dest = tmp_path / "arch"
    env = _env(tmp_path, home=_fixture_home(tmp_path))
    assert _run("archive", "--dest", str(dest), env=env).returncode == 0
    return dest, env


def test_verify_fails_when_the_tarball_is_missing(tmp_path):
    dest, env = _good_archive(tmp_path)
    (dest / "secure-agent-pod-home.tar.gz").unlink()
    r = _run("verify", "--dest", str(dest), env=env)
    assert r.returncode != 0
    assert "FAIL" in r.stdout


def test_verify_fails_when_the_manifest_does_not_match(tmp_path):
    dest, env = _good_archive(tmp_path)
    with open(dest / "secure-agent-pod-home.tar.gz", "ab") as f:
        f.write(b"tamper")
    r = _run("verify", "--dest", str(dest), env=env)
    assert r.returncode != 0
    assert "FAIL MANIFEST.sha256 matches" in r.stdout


def test_verify_fails_without_chorebots_config(tmp_path):
    home = _fixture_home(tmp_path)
    (home / "repos/willikins/scripts/chorebot/config.yaml").unlink()
    dest = tmp_path / "arch"
    env = _env(tmp_path, home=home)
    # archive itself fails (tar cannot find the file), so build the tarball by hand
    dest.mkdir(mode=0o700)
    with tarfile.open(dest / "secure-agent-pod-home.tar.gz", "w:gz") as t:
        t.add(home / "interviews", arcname="interviews")
        t.add(home / "orgs", arcname="orgs")
    (dest / "bundles").mkdir()
    subprocess.run("shasum -a 256 secure-agent-pod-home.tar.gz > MANIFEST.sha256",
                   shell=True, cwd=dest, check=True)
    r = _run("verify", "--dest", str(dest), env=env)
    assert r.returncode != 0
    assert "FAIL tarball lists chorebot config.yaml" in r.stdout


def test_key_fingerprint_compares_without_printing_key_material(tmp_path):
    # Stub kubectl and sops; secrets/ files in the repo are never decrypted here.
    secret = "TOP-SECRET-PEM"
    import base64
    b64 = base64.b64encode(secret.encode()).decode()
    kubectl = tmp_path / "kubectl"
    kubectl.write_text(f"#!/usr/bin/env bash\nprintf '%s' '{b64}'\n")
    sops = tmp_path / "sops"
    sops.write_text(f"#!/usr/bin/env bash\nprintf 'data:\\n    key: {b64}\\n'\n")
    for f in (kubectl, sops):
        f.chmod(0o755)
    env = {**os.environ, "KUBECTL": str(kubectl), "SOPS": str(sops)}
    r = _run("key-fingerprint", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert secret not in r.stdout + r.stderr and b64 not in r.stdout + r.stderr
    # a differing live value fails
    kubectl.write_text("#!/usr/bin/env bash\nprintf '%s' 'b3RoZXI='\n")
    assert _run("key-fingerprint", env=env).returncode != 0
