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
# the pod-side digest wrapper: `bash -c <script> _ <cmd...>`; serve ps from the fixture
if [ "$1" = bash ] && [ "$5" = ps ]; then exec bash -c "$3" _ cat "$STUB_PS"; fi
if [ -n "${STUB_FAIL:-}" ]; then
  case " $* " in *" $STUB_FAIL "*) echo "stub: $STUB_FAIL failed" >&2; exit 1 ;; esac
fi
if [ -n "${STUB_CUT:-}" ]; then
  hit=0
  if [ -z "${STUB_CUT_MATCH:-}" ]; then hit=1; else case " $* " in *" $STUB_CUT_MATCH "*) hit=1 ;; esac; fi
  if [ "$hit" = 1 ]; then t=$(mktemp); "$@" > "$t"; rc=$?; head -c "$STUB_CUT" "$t"; rm -f "$t"; exit $rc; fi
fi
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
    _git("remote", "add", "origin", "https://example.invalid/r.git", cwd=clone)
    _git("remote", "set-url", "--push", "origin", str(bare), cwd=clone)
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
    (bundle,) = [b for b in (dest / "bundles").glob("*.bundle") if not b.name.endswith(".HEAD.bundle")]
    heads = subprocess.run(["git", "bundle", "list-heads", str(bundle)],
                           capture_output=True, text=True, check=True).stdout
    assert "refs/tags/keepme" in heads
    # the commit made in the detached linked worktree is restorable from its bundle
    (hb,) = list((dest / "bundles").glob("*.HEAD.bundle"))
    assert (dest / "DETACHED.txt").read_text() == ""
    fresh = tmp_path / "fresh"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "remote.git"), str(fresh)], check=True)
    subprocess.run(["git", "fetch", "-q", str(hb), "HEAD:refs/heads/restored"], cwd=fresh, check=True)
    log = subprocess.run(["git", "log", "-1", "--format=%s", "restored"], cwd=fresh,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert log == "detached work"
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout


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


# --- uncommitted clone state --------------------------------------------------

def _status(clone):
    return subprocess.run(["git", "status", "--porcelain=v1", "--ignored"], cwd=clone,
                          capture_output=True, check=True).stdout


def _dirty_clone(home, tmp_path):
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    (clone / ".gitignore").write_text("*.cache\n")
    _git("add", ".gitignore", cwd=clone)
    _git("commit", "-qm", "ignore", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    (clone / "f").write_text("stash one\n")
    _git("stash", "push", "-q", cwd=clone)
    (clone / "f").write_text("stash two\n")
    (clone / "new.txt").write_text("n")
    _git("add", "new.txt", cwd=clone)
    _git("stash", "push", "-q", cwd=clone)
    (clone / "f").write_text("modified, unstaged\n")
    (clone / "staged.txt").write_text("staged\n")
    _git("add", "staged.txt", cwd=clone)
    (clone / "untracked file.txt").write_text("u")
    (clone / "creds").mkdir()
    (clone / "creds/credentials.json").write_text("secret")
    (clone / "junk.cache").write_text("ignored")
    return clone


def _wd(dest, needle="willikins"):
    (wd,) = [p for p in _worktrees_dirs(dest) if needle in p.name]
    return wd


def _worktrees_dirs(dest):
    d = dest / "worktrees"
    return sorted(p for p in d.iterdir()) if d.exists() else []


def test_dirty_clone_state_is_archived_read_only(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _dirty_clone(home, tmp_path)
    before = _status(clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert _status(clone) == before  # nothing in the clone changed
    wd = _wd(dest)
    dirty = (dest / "DIRTY.txt").read_text()
    assert "willikins" in dirty and "stash=2" in dirty
    # the patch applies to a fresh checkout of HEAD and carries both tracked changes
    staged, tracked = wd / "staged.patch", wd / "tracked.patch"
    assert staged.stat().st_size > 0 and tracked.stat().st_size > 0
    fresh = tmp_path / "fresh"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "remote.git"), str(fresh)], check=True)
    ap = subprocess.run(["git", "apply", "--check", "--index", str(staged)], cwd=fresh, capture_output=True, text=True)
    assert ap.returncode == 0, ap.stderr
    subprocess.run(["git", "apply", "--index", str(staged)], cwd=fresh, check=True)
    ap = subprocess.run(["git", "apply", "--check", str(tracked)], cwd=fresh, capture_output=True, text=True)
    assert ap.returncode == 0, ap.stderr
    assert "staged.txt" in staged.read_text()
    assert "modified, unstaged" in tracked.read_text()
    # untracked: the plain file only (no credential file, no ignored file)
    names = tarfile.open(wd / "untracked.tar.gz").getnames()
    assert any(n.endswith("untracked file.txt") for n in names), names
    assert not any("credentials.json" in n or "junk.cache" in n for n in names), names
    # stashes
    assert (wd / "stash-list.txt").read_text().count("stash@{") == 2
    for i in (0, 1):
        assert (wd / f"stash-{i}.patch").stat().st_size > 0
    assert (wd / "status.txt").stat().st_size > 0
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout
    assert "willikins" in v.stdout and "dirty" in v.stdout.lower()


def test_clean_clone_writes_nothing_under_worktrees(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    (clone / ".gitignore").write_text("scripts/\n")  # the fixture's untracked dirs
    _git("add", ".gitignore", cwd=clone)
    _git("commit", "-qm", "ignore", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    assert _status(clone).replace(b"!! scripts/\n", b"") == b""
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert _worktrees_dirs(dest) == []
    assert (dest / "DIRTY.txt").read_text() == ""
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout
    assert "no dirty clones" in v.stdout


def test_verify_fails_when_a_dirty_clone_patch_is_deleted_or_truncated(tmp_path):
    home = _fixture_home(tmp_path)
    _dirty_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest)
    patch = wd / "staged.patch"
    keep = patch.read_bytes()
    patch.write_bytes(keep[:-10])
    assert _run("verify", "--dest", str(dest), env=env).returncode != 0
    patch.unlink()
    assert _run("verify", "--dest", str(dest), env=env).returncode != 0


def test_verify_fails_when_a_dirty_clone_directory_is_missing(tmp_path):
    import shutil
    home = _fixture_home(tmp_path)
    _dirty_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    wd = _wd(dest)
    shutil.rmtree(wd)
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0
    assert "FAIL dirty clone state present" in v.stdout


def test_verify_fails_when_untracked_tarball_carries_a_credential(tmp_path):
    home = _fixture_home(tmp_path)
    _dirty_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    wd = _wd(dest)
    with tarfile.open(wd / "untracked.tar.gz", "w:gz") as t:
        t.add(home / ".hermes/auth.json" if (home / ".hermes/auth.json").exists() else home / "orgs/o.txt",
              arcname="x/auth.json")
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0
    assert "FAIL no credential files in untracked tarballs" in v.stdout


def test_a_failing_git_status_aborts_instead_of_recording_clean(tmp_path):
    home = _fixture_home(tmp_path)
    _dirty_clone(home, tmp_path)
    r, dest, _, _ = _archive_ok(tmp_path, {"STUB_FAIL": "status"}, home=home)
    assert r.returncode != 0


# --- archive review fixes ------------------------------------------------------

def _out(*a, cwd, text=True):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=text, check=True).stdout


def _fresh_clone(tmp_path, name="fresh"):
    fresh = tmp_path / name
    subprocess.run(["git", "clone", "-q", str(tmp_path / "remote.git"), str(fresh)], check=True)
    return fresh


def _restore(fresh, wd):
    """Recreate a worktree's staged + unstaged state from the two patches."""
    subprocess.run(["git", "apply", "--index", str(wd / "staged.patch")], cwd=fresh, check=True)
    subprocess.run(["git", "apply", str(wd / "tracked.patch")], cwd=fresh, check=True)


def _tracked_state(repo):
    return _out("status", "--porcelain=v1", "--untracked-files=no", cwd=repo)


def test_staged_and_unstaged_states_survive_ad_md_and_mixed(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    (clone / "md").write_text("tracked\n")
    (clone / "mixed").write_text("m1\n")
    _git("add", "md", "mixed", cwd=clone)
    _git("commit", "-qm", "more", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    (clone / "md").write_text("staged change\n")
    _git("add", "md", cwd=clone)
    (clone / "md").unlink()                      # MD: modified in the index, deleted in the tree
    (clone / "ad").write_text("added\n")
    _git("add", "ad", cwd=clone)
    (clone / "ad").unlink()                      # AD: added in the index, deleted in the tree
    (clone / "mixed").write_text("m2 staged\n")
    _git("add", "mixed", cwd=clone)
    (clone / "mixed").write_text("m3 unstaged\n")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest)
    fresh = _fresh_clone(tmp_path)
    _restore(fresh, wd)
    assert _tracked_state(fresh) == _tracked_state(clone)
    assert (fresh / "mixed").read_text() == "m3 unstaged\n"


def test_unborn_head_with_unstaged_edits_is_captured(tmp_path):
    home = _fixture_home(tmp_path)
    repo = home / "repos/unborn"
    repo.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / "a").write_text("staged\n")
    _git("add", "a", cwd=repo)
    (repo / "a").write_text("staged\nunstaged\n")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest, "unborn")
    assert (wd / "NOTE.txt").exists()
    assert (wd / "staged.patch").stat().st_size > 0 and (wd / "tracked.patch").stat().st_size > 0
    fresh = tmp_path / "fresh-unborn"
    fresh.mkdir()
    _git("init", "-q", "-b", "main", cwd=fresh)
    _restore(fresh, wd)
    assert (fresh / "a").read_text() == "staged\nunstaged\n"


def test_hostile_gitconfig_cannot_change_the_patch_format(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _dirty_clone(home, tmp_path)
    ext = tmp_path / "extdiff.sh"
    ext.write_text("#!/bin/sh\necho EXTERNAL-DIFF-JUNK\n")
    ext.chmod(0o755)
    for k, v in (("diff.noprefix", "true"), ("color.diff", "always"), ("color.ui", "always"),
                 ("diff.external", str(ext)), ("diff.mnemonicprefix", "true"),
                 ("diff.relative", "true")):
        _git("config", k, v, cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest)
    for name in ("staged.patch", "tracked.patch", "stash-0.patch"):
        txt = (wd / name).read_text()
        assert "EXTERNAL-DIFF-JUNK" not in txt and "\x1b[" not in txt, name
        assert "diff --git a/" in txt and " b/" in txt, name
    fresh = _fresh_clone(tmp_path)
    _restore(fresh, wd)


def test_status_show_untracked_files_no_does_not_hide_untracked(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _dirty_clone(home, tmp_path)
    _git("config", "status.showUntrackedFiles", "no", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    names = tarfile.open(_wd(dest) / "untracked.tar.gz").getnames()
    assert any(n.endswith("untracked file.txt") for n in names)


def test_stash_entries_include_binary_and_untracked_parts(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    (clone / "bin.dat").write_bytes(bytes(range(256)))
    _git("add", "bin.dat", cwd=clone)
    _git("commit", "-qm", "bin", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    (clone / "bin.dat").write_bytes(bytes(reversed(range(256))))
    (clone / "stash-only-untracked.txt").write_text("hello from stash\n")
    _git("stash", "push", "-q", "--include-untracked", cwd=clone)
    (clone / "bin.dat").write_bytes(b"\x00\x01second")
    _git("stash", "push", "-q", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest)
    fresh = _fresh_clone(tmp_path)
    for i in (0, 1):
        assert (wd / f"stash-{i}.patch").stat().st_size > 0
        subprocess.run(["git", "apply", "--check", str(wd / f"stash-{i}.patch")], cwd=fresh, check=True)
    # entry 1 (older) carried the untracked file; its patch restores it
    up = wd / "stash-1.untracked.patch"
    assert up.stat().st_size > 0 and "hello from stash" in up.read_text()
    assert not (wd / "stash-0.untracked.patch").exists()
    subprocess.run(["git", "apply", str(up)], cwd=fresh, check=True)
    assert (fresh / "stash-only-untracked.txt").read_text() == "hello from stash\n"
    # binary content is byte-exact
    subprocess.run(["git", "apply", str(wd / "stash-1.patch")], cwd=fresh, check=True)
    assert (fresh / "bin.dat").read_bytes() == bytes(reversed(range(256)))


def test_submodule_local_commits_and_dirty_state_are_captured(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    sub_src = tmp_path / "subsrc"
    sub_src.mkdir()
    _git("init", "-q", "-b", "main", cwd=sub_src)
    (sub_src / "s").write_text("1")
    _git("add", "s", cwd=sub_src)
    _git("commit", "-qm", "sub one", cwd=sub_src)
    _git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub_src), "vendor/sub", cwd=clone)
    _git("commit", "-qm", "add submodule", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    sub = clone / "vendor/sub"
    (sub / "s").write_text("2")
    _git("add", "s", cwd=sub)
    _git("commit", "-qm", "sub local commit", cwd=sub)
    (sub / "dirty.txt").write_text("sub untracked")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    bundles = [b for b in (dest / "bundles").glob("*.bundle") if "vendor__sub" in b.name]
    assert bundles, list((dest / "bundles").iterdir())
    heads = _out("bundle", "list-heads", str(bundles[0]), cwd=tmp_path)
    assert "refs/heads/" in heads
    names = tarfile.open(_wd(dest, "vendor__sub") / "untracked.tar.gz").getnames()
    assert any(n.endswith("dirty.txt") for n in names)
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0


def test_bare_repo_beyond_depth_six_is_bundled(tmp_path):
    home = _fixture_home(tmp_path)
    deep = home / "a/b/c/d/e/f/g/h"
    deep.mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    _git("init", "-q", "-b", "main", cwd=work)
    (work / "x").write_text("x")
    _git("add", "x", cwd=work)
    _git("commit", "-qm", "only local", cwd=work)
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(deep / "store.git")], check=True)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert [b for b in (dest / "bundles").glob("*store.git*.bundle")]


def test_clone_under_cache_is_skipped_and_recorded(tmp_path):
    home = _fixture_home(tmp_path)
    cached = home / ".cache/some/clone"
    cached.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=cached)
    (cached / "f").write_text("f")
    _git("add", "f", cwd=cached)
    _git("commit", "-qm", "cached", cwd=cached)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert "pruned (regenerable cache, not archived)" in (dest / "SKIPPED.txt").read_text()
    assert ".cache" in (dest / "SKIPPED.txt").read_text()
    assert not [b for b in (dest / "bundles").glob("*.bundle") if "some__clone" in b.name]
    assert "clones under" in subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True).stderr


def test_symlinked_pod_home_still_captures_stashes(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    home = _fixture_home(real)
    clone = _dirty_clone(home, tmp_path)
    link = tmp_path / "linkhome"
    link.symlink_to(home)
    env = _env(tmp_path, home=link)
    dest = tmp_path / "arch"
    r = _run("archive", "--dest", str(dest), env=env)
    assert r.returncode == 0, r.stderr
    assert "stash=2" in (dest / "DIRTY.txt").read_text()
    assert _status(clone)  # untouched
    assert (_wd(dest) / "stash-1.patch").exists()


def test_notes_and_annotated_tags_are_preserved_by_identity(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    _git("notes", "add", "-m", "a local note", cwd=clone)
    _git("tag", "-a", "v1", "-m", "annotated on a pushed commit", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    (bundle,) = [b for b in (dest / "bundles").glob("*.bundle") if not b.name.endswith(".HEAD.bundle")]
    heads = _out("bundle", "list-heads", str(bundle), cwd=tmp_path)
    assert "refs/notes/commits" in heads
    tagobj = _out("rev-parse", "refs/tags/v1", cwd=clone).strip()
    saved = list((dest / "tags").rglob(f"{tagobj}.tag"))
    assert saved and "annotated on a pushed commit" in saved[0].read_text()
    assert "refs/tags/v1" in "".join(p.read_text() for p in (dest / "refs").iterdir())


def test_local_path_remote_is_not_a_safe_copy(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    _git("remote", "set-url", "origin", str(tmp_path / "remote.git"), cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert "local path" in r.stderr
    (bundle,) = [b for b in (dest / "bundles").glob("*.bundle") if not b.name.endswith(".HEAD.bundle")]
    assert "refs/heads/main" in _out("bundle", "list-heads", str(bundle), cwd=tmp_path)


def test_ignored_list_and_excluded_credentials_are_reported(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _dirty_clone(home, tmp_path)
    (clone / "id_rsa_notes.md").write_text("keep me")
    (clone / "id_rsa").write_text("private")
    (clone / "tracked-creds").mkdir()
    (clone / "tracked-creds/credentials.json").write_text("v1")
    _git("add", "-f", "tracked-creds/credentials.json", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest)
    names = tarfile.open(wd / "untracked.tar.gz").getnames()
    assert any(n.endswith("id_rsa_notes.md") for n in names)
    assert not any(n.endswith("/id_rsa") or n == "id_rsa" for n in names)
    ex = (dest / "EXCLUDED.txt").read_text()
    assert "credentials.json" in ex and "id_rsa" in ex and "in patch" in ex
    assert (wd / "staged.patch").read_text().count("tracked-creds/credentials.json") >= 1
    ign = "".join(p.read_text() for p in (dest / "ignored").iterdir())
    assert "junk.cache" in ign and "ignored" not in ign.replace("junk.cache", "")
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout
    assert "WARN credential-named paths" in v.stdout


def test_skip_worktree_and_assume_unchanged_edits_are_archived(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    (clone / "au").write_text("1\n")
    (clone / "sw").write_text("1\n")
    _git("add", "au", "sw", cwd=clone)
    _git("commit", "-qm", "hidden files", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    _git("update-index", "--assume-unchanged", "au", cwd=clone)
    _git("update-index", "--skip-worktree", "sw", cwd=clone)
    (clone / "au").write_text("edited au\n")
    (clone / "sw").write_text("edited sw\n")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert "hidden=2" in (dest / "DIRTY.txt").read_text()
    wd = _wd(dest)
    tf = tarfile.open(wd / "hidden.tar.gz")
    got = {n.split("/")[-1]: tf.extractfile(n).read() for n in tf.getnames() if tf.getmember(n).isfile()}
    assert got["au"] == b"edited au\n" and got["sw"] == b"edited sw\n"
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0


def test_a_truncated_probe_that_exits_zero_aborts(tmp_path):
    home = _fixture_home(tmp_path)
    _dirty_clone(home, tmp_path)
    for match in ("for-each-ref", "find", "worktree"):
        sub = tmp_path / f"cut-{match}"
        sub.mkdir()
        h = _fixture_home(sub)
        _dirty_clone(h, sub)
        env = _env(sub, home=h)
        env.update({"STUB_CUT": "5", "STUB_CUT_MATCH": match})
        r = _run("archive", "--dest", str(sub / "arch"), env=env)
        assert r.returncode != 0, match
        assert "cut" in r.stderr or "damaged" in r.stderr, (match, r.stderr)


def test_detached_txt_fails_verify(tmp_path):
    r, dest, env, _ = _archive_ok(tmp_path)
    assert r.returncode == 0, r.stderr
    (dest / "DETACHED.txt").write_text("/somewhere abc123\n")
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0 and "FAIL no uncaptured detached" in v.stdout


def test_verify_checks_dirty_counts_against_content(tmp_path):
    home = _fixture_home(tmp_path)
    _dirty_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest)
    for name in ("stash-1.patch", "untracked.tar.gz", "tracked.patch"):
        keep = (wd / name).read_bytes()
        (wd / name).unlink()
        v = _run("verify", "--dest", str(dest), env=env)
        assert v.returncode != 0, name
        (wd / name).write_bytes(keep)
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0
    d = (dest / "DIRTY.txt").read_text()
    (dest / "DIRTY.txt").write_text(d.replace("stash=2", "stash=3"))
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0 and "FAIL dirty clone state present" in v.stdout


def test_verify_live_diffs_the_pod_and_plain_verify_stays_offline(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _dirty_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    live = _run("verify", "--live", "--dest", str(dest), env=env)
    assert live.returncode == 0, live.stdout + live.stderr
    assert "PASS live dirty state matches" in live.stdout
    # plain verify never calls kubectl
    dead = tmp_path / "dead-kubectl"
    dead.write_text("#!/bin/sh\nexit 99\n")
    dead.chmod(0o755)
    off = _run("verify", "--dest", str(dest), env={**env, "KUBECTL": str(dead)})
    assert off.returncode == 0, off.stdout
    # the pod moves on: --live notices
    (clone / "late-file.txt").write_text("late")
    live2 = _run("verify", "--live", "--dest", str(dest), env=env)
    assert live2.returncode != 0 and "FAIL live dirty state" in live2.stdout
    # and a new clone shows up in the clone list
    (clone / "late-file.txt").unlink()
    other = home / "repos/newcomer"
    other.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=other)
    live3 = _run("verify", "--live", "--dest", str(dest), env=env)
    assert live3.returncode != 0 and "FAIL live clone list" in live3.stdout


def test_worktree_directory_names_do_not_collide(tmp_path):
    home = _fixture_home(tmp_path)
    for rel in ("a/b__c", "a__b/c"):
        d = home / "repos" / rel
        d.mkdir(parents=True)
        _git("init", "-q", "-b", "main", cwd=d)
        (d / "u.txt").write_text(rel)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    dirs = [p for p in _worktrees_dirs(dest) if "b__c" in p.name or "a__b" in p.name]
    assert len(dirs) == 2
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0


def test_untracked_file_with_a_newline_in_its_name_is_captured(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _dirty_clone(home, tmp_path)
    (clone / "odd\nname.txt").write_text("odd")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    names = tarfile.open(_wd(dest) / "untracked.tar.gz").getnames()
    assert any("odd\nname.txt" in n for n in names)


def test_a_corrupt_head_object_is_never_recorded_as_clean_or_unborn(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _dirty_clone(home, tmp_path)
    (clone / ".git/refs/heads/main").write_text("0123456789012345678901234567890123456789\n")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode != 0
