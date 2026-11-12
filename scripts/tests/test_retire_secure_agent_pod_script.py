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
if [ -n "${STUB_FAIL:-}" ]; then
  case " $* " in *" $STUB_FAIL "*) echo "stub: $STUB_FAIL failed" >&2; exit 1 ;; esac
fi
if [ -n "${STUB_CUT:-}" ]; then "$@" | head -c "$STUB_CUT"; exit 0; fi
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


def _fixture_creds(home):
    for rel in (".claude/.credentials.json", "orgs/x/credentials.json", ".hermes/.env",
                ".hermes/auth.json", "orgs/x/id_rsa", "orgs/x/id_ed25519.pub", "orgs/x/k.pem",
                "orgs/x/.ssh/known_hosts", "orgs/x/.config/gh/hosts.yml"):
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("secret")


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
                   ".gnupg", ".config/gh", ".claude.json", ".env", "auth.json"):
        lines = [l for l in SCRIPT.read_text().splitlines() if needle in l]
        assert lines, needle
        assert all("CRED_NAMES=" in l for l in lines), (needle, lines)


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


# --- review fixes -----------------------------------------------------------

def _archive_ok(tmp_path, extra_env=None, home=None, args=()):
    home = home or _fixture_home(tmp_path)
    dest = tmp_path / "arch"
    env = _env(tmp_path, home=home)
    env.update(extra_env or {})
    r = _run("archive", "--dest", str(dest), *args, env=env)
    return r, dest, env, home


def _clone_with_remote(home, tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    clone = home / "repos/willikins"
    _git("init", "-q", "-b", "main", cwd=clone)
    _git("remote", "add", "origin", str(bare), cwd=clone)
    (clone / "f").write_text("1")
    _git("add", "f", cwd=clone)
    _git("commit", "-qm", "one", cwd=clone)
    _git("push", "-q", "-u", "origin", "main", cwd=clone)
    _git("checkout", "-q", "-b", "local-only", cwd=clone)
    (clone / "g").write_text("2")
    _git("add", "g", cwd=clone)
    _git("commit", "-qm", "two", cwd=clone)
    return clone


def test_bundle_excludes_pushed_branch_and_keeps_local_only(tmp_path):
    home = _fixture_home(tmp_path)
    _clone_with_remote(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    heads = subprocess.run(["git", "bundle", "list-heads", str(bundle)],
                           capture_output=True, text=True, check=True).stdout
    assert "refs/heads/local-only" in heads
    assert "refs/heads/main" not in heads
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout + v.stderr


def test_truncated_tarball_stream_fails_archive(tmp_path):
    r, dest, _, _ = _archive_ok(tmp_path, {"STUB_CUT": "300"})
    assert r.returncode != 0


def test_verify_fails_on_a_truncated_tarball(tmp_path):
    dest, env = _good_archive(tmp_path)
    t = dest / "secure-agent-pod-home.tar.gz"
    data = t.read_bytes()
    t.write_bytes(data[:-100])
    # regenerate the local manifest so only the structural/remote-digest checks can catch it
    subprocess.run("find . -type f ! -name MANIFEST.sha256 | sort | sed 's#^./##' | "
                   "while read f; do shasum -a 256 \"$f\"; done > MANIFEST.sha256",
                   shell=True, cwd=dest, check=True)
    r = _run("verify", "--dest", str(dest), env=env)
    assert r.returncode != 0
    assert "FAIL" in r.stdout


def test_verify_fails_on_a_truncated_bundle(tmp_path):
    home = _fixture_home(tmp_path)
    _clone_with_remote(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    bundle.write_bytes(bundle.read_bytes()[:-100])
    out = _run("verify", "--dest", str(dest), env=env)
    assert out.returncode != 0
    assert "FAIL bundle" in out.stdout
    # also with a manifest regenerated to match, the pack checksum catches it
    subprocess.run("find . -type f ! -name MANIFEST.sha256 | sort | sed 's#^./##' | "
                   "while read f; do shasum -a 256 \"$f\"; done > MANIFEST.sha256",
                   shell=True, cwd=dest, check=True)
    out = _run("verify", "--dest", str(dest), env=env)
    assert out.returncode != 0
    assert "FAIL bundle" in out.stdout


def test_a_failing_rev_list_fails_the_run(tmp_path):
    home = _fixture_home(tmp_path)
    _clone_with_remote(home, tmp_path)
    r, dest, _, _ = _archive_ok(tmp_path, {"STUB_FAIL": "rev-list"}, home=home)
    assert r.returncode != 0
    assert not (dest / "bundles/NONE.txt").exists() or \
        "willikins" not in (dest / "bundles/NONE.txt").read_text()


def test_session_guard_catches_herdr_tmux_node_and_versioned_claude(tmp_path):
    for ps in ("herdr serve\n", "tmux: server\n",
               "node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js\n",
               "/home/claude/.local/share/claude/versions/2.1.0 --resume x\n"):
        sub = tmp_path / ps.split()[0].replace("/", "_").replace(":", "")
        sub.mkdir()
        env = _env(sub, ps=ps, home=_fixture_home(sub))
        out = _run("archive", "--dest", str(sub / "arch"), env=env)
        assert out.returncode != 0, ps
        assert "interactive session still running" in out.stderr, ps


def test_session_guard_survives_a_huge_listing(tmp_path):
    filler = "bash -c sleep 1000 # padding padding padding padding\n" * 12000
    assert len(filler) > 500_000
    for i, ps in enumerate((filler + "claude --resume abc\n", "claude --resume abc\n" + filler)):
        sub = tmp_path / f"huge{i}"
        sub.mkdir()
        env = _env(sub, ps=ps, home=_fixture_home(sub))
        out = _run("archive", "--dest", str(sub / "arch"), env=env)
        assert out.returncode != 0
        assert "interactive session still running" in out.stderr


def test_credentials_are_excluded_at_depth_and_verify_rejects_them(tmp_path):
    home = _fixture_home(tmp_path)
    _fixture_creds(home)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    names = tarfile.open(dest / "secure-agent-pod-home.tar.gz").getnames()
    for bad in (".credentials.json", "credentials.json", ".env", "auth.json", "id_rsa",
                "id_ed25519.pub", ".pem", ".ssh", ".config/gh"):
        assert not any(bad in n for n in names), (bad, names)
    assert any(n.endswith("chorebot/config.yaml") for n in names)
    # a tarball that does carry a credential fails verify
    t = dest / "secure-agent-pod-home.tar.gz"
    with tarfile.open(t, "w:gz") as tf:
        for n in ("interviews", "orgs"):
            tf.add(home / n, arcname=n)
        tf.add(home / "repos/willikins/scripts/chorebot/config.yaml",
               arcname="repos/willikins/scripts/chorebot/config.yaml")
        tf.add(home / ".claude/.credentials.json", arcname=".claude/.credentials.json")
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0
    assert "FAIL no credential files in tarball" in v.stdout


def test_missing_optional_path_is_skipped_but_essentials_fail_verify(tmp_path):
    import shutil
    home = _fixture_home(tmp_path)
    shutil.rmtree(home / ".hermes")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert ".hermes" in (dest / "SKIPPED.txt").read_text()
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0
    shutil.rmtree(tmp_path / "arch")
    shutil.rmtree(home / "interviews")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0
    assert "FAIL essential paths archived" in v.stdout


def test_sqlite_wal_and_shm_are_archived_when_present(tmp_path):
    home = _fixture_home(tmp_path)
    d = home / ".local/share/vibe-kanban"
    (d / "db.v2.sqlite-wal").write_text("w")
    (d / "db.v2.sqlite-shm").write_text("s")
    r, dest, _, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    names = tarfile.open(dest / "secure-agent-pod-home.tar.gz").getnames()
    assert any(n.endswith("db.v2.sqlite-wal") for n in names)
    assert any(n.endswith("db.v2.sqlite-shm") for n in names)


def test_tags_stash_and_detached_work_are_covered(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    (clone / "t").write_text("t")
    _git("add", "t", cwd=clone)
    _git("commit", "-qm", "tagged", cwd=clone)
    _git("tag", "keepme", cwd=clone)
    _git("reset", "-q", "--hard", "origin/main", cwd=clone)
    wt = home / "repos/wt"
    _git("worktree", "add", "-q", "--detach", str(wt), "main", cwd=clone)
    (wt / "d").write_text("d")
    _git("add", "d", cwd=wt)
    _git("commit", "-qm", "detached work", cwd=wt)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    heads = subprocess.run(["git", "bundle", "list-heads", str(bundle)],
                           capture_output=True, text=True, check=True).stdout
    assert "refs/tags/keepme" in heads
    assert "WARNING" in r.stdout + r.stderr
    assert (dest / "DETACHED.txt").read_text().strip()
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout
    assert "WARN" in v.stdout


def test_rerun_clears_stale_bundles(tmp_path):
    home = _fixture_home(tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    (dest / "bundles/stale.bundle").write_text("old")
    r2 = _run("archive", "--dest", str(dest), env=env)
    assert r2.returncode == 0, r2.stderr
    assert not (dest / "bundles/stale.bundle").exists()


def _key_env(tmp_path, live_b64, tekton_b64, old_b64=None, git_ok=True):
    kubectl = tmp_path / "kubectl"
    kubectl.write_text(f"#!/usr/bin/env bash\nprintf '%s' '{live_b64}'\n")
    sops = tmp_path / "sops"
    old = old_b64 if old_b64 is not None else tekton_b64
    sops.write_text(
        "#!/usr/bin/env bash\n"
        'for a; do last=$a; done\n'
        f'if [ "$last" = /dev/stdin ]; then cat >/dev/null; v={old}; else v={tekton_b64}; fi\n'
        "printf 'data:\\n    key: %s\\n' \"$v\"\n")
    git = tmp_path / "git"
    git.write_text("#!/usr/bin/env bash\n" + ("echo ENCRYPTED\n" if git_ok else "exit 1\n"))
    for f in (kubectl, sops, git):
        f.chmod(0o755)
    return {**os.environ, "KUBECTL": str(kubectl), "SOPS": str(sops), "GIT": str(git)}


def test_key_fingerprint_compares_the_deleted_file_from_origin_main(tmp_path):
    import base64
    a = base64.b64encode(b"pem-a").decode()
    b = base64.b64encode(b"pem-b").decode()
    ok = _run("key-fingerprint", env=_key_env(tmp_path, a, a))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "origin/main" in ok.stdout
    bad = _run("key-fingerprint", env=_key_env(tmp_path, a, a, old_b64=b))
    assert bad.returncode != 0


def test_key_fingerprint_fails_when_the_old_file_cannot_be_found(tmp_path):
    import base64
    a = base64.b64encode(b"pem-a").decode()
    env = _key_env(tmp_path, a, a, git_ok=False)
    assert _run("key-fingerprint", env=env).returncode != 0
    ok = _run("key-fingerprint", "--old-file-gone-ok", env=env)
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_key_fingerprint_rejects_empty_values(tmp_path):
    env = _key_env(tmp_path, "", "")
    r = _run("key-fingerprint", "--old-file-gone-ok", env=env)
    assert r.returncode != 0
