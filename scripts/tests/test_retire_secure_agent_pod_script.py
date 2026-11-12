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
if [ -n "${STUB_CALLS_LOG:-}" ]; then echo "$*" >> "$STUB_CALLS_LOG"; fi
# transport faults: STUB_FAULT=drop|flip|nostatus|cut, first STUB_FAULT_TIMES matching calls
if [ -n "${STUB_FAULT:-}" ]; then
  m=${STUB_FAULT_MATCH:-}; hit=0
  if [ -z "$m" ]; then hit=1; else case " $* " in *" $m "*) hit=1 ;; esac; fi
  if [ "$hit" = 1 ]; then
    n=$(cat "$STUB_FAULT_COUNT" 2>/dev/null || echo 0)
    if [ "$n" -lt "${STUB_FAULT_TIMES:-1000}" ]; then
      echo $((n + 1)) > "$STUB_FAULT_COUNT"
      t=$(mktemp); e=$(mktemp); "$@" > "$t" 2> "$e"
      case $STUB_FAULT in
        drop) head -c "${STUB_FAULT_BYTES:-7}" "$t"; rm -f "$t" "$e"; exit 1 ;;
        cut) head -c "${STUB_FAULT_BYTES:-7}" "$t"; cat "$e" >&2; rm -f "$t" "$e"; exit 0 ;;
        flip) cat "$t"; printf x; cat "$e" >&2; rm -f "$t" "$e"; exit 0 ;;
        nostatus) cat "$t"; grep -v '^REMOTE-' "$e" >&2; rm -f "$t" "$e"; exit 0 ;;
      esac
    fi
  fi
fi
# a real, non-zero exit status of the pod command (reported through the sentinel)
if [ -n "${STUB_FAIL_RC:-}" ] && [ "$1" = bash ]; then
  case " $* " in *" $STUB_FAIL_RC "*) exec bash -c "$3" _ sh -c 'exit 7' ;; esac
fi
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
    env = {**os.environ, "KUBECTL": str(stub), "STUB_PS": str(psf),
           "STUB_FAULT_COUNT": str(tmp_path / "fault-count"), "STUB_CALLS_LOG": str(tmp_path / "calls.log"),
           "ARCHIVE_RETRY_DELAYS": "0 0 0"}
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


def test_bundle_is_self_contained_and_local_only_is_reported(tmp_path):
    home = _fixture_home(tmp_path)
    _clone_with_remote(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    heads = subprocess.run(["git", "bundle", "list-heads", str(bundle)],
                           capture_output=True, text=True, check=True).stdout
    assert "refs/heads/local-only" in heads and "refs/heads/main" in heads
    assert "refs/remotes/origin/main" in heads
    lo = (dest / "LOCAL-ONLY.txt").read_text()
    assert "refs/heads/local-only" in lo and "refs/heads/main" not in lo
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout + v.stderr


def test_truncated_tarball_stream_fails_archive(tmp_path):
    # a stub that ALWAYS truncates still fails, now after the bounded retries
    r, dest, _, _ = _archive_ok(tmp_path, {"STUB_CUT": "300"})
    assert r.returncode != 0
    assert "after 4 attempts" in r.stderr
    assert not list(dest.rglob("*.part"))


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
    (bundle,) = [b for b in (dest / "bundles").glob("*.bundle") if b.name.count(".") == 2]
    heads = subprocess.run(["git", "bundle", "list-heads", str(bundle)],
                           capture_output=True, text=True, check=True).stdout
    assert "refs/tags/keepme" in heads
    # the commit made in the detached linked worktree is restorable from its bundle
    assert (dest / "DETACHED.txt").read_text() == ""
    detached = _out("rev-parse", "HEAD", cwd=wt).strip()
    assert detached in (dest / "EXTRA-REVS.txt").read_text()
    fresh = tmp_path / "fresh"
    subprocess.run(["git", "init", "-q", str(fresh)], check=True)
    _git("fetch", "-q", str(bundle), "+refs/*:refs/archive/*", cwd=fresh)
    assert _out("log", "-1", "--format=%s", detached, cwd=fresh).strip() == "detached work"
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
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    heads = _out("bundle", "list-heads", str(bundle), cwd=tmp_path)
    assert "refs/notes/commits" in heads and "refs/tags/v1" in heads
    tagobj = _out("rev-parse", "refs/tags/v1", cwd=clone).strip()
    assert tagobj in heads            # the annotated tag object itself is in the bundle
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
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
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


# --- archive re-review fixes ---------------------------------------------------

def _tar_text(path, member_suffix):
    tf = tarfile.open(path)
    for n in tf.getnames():
        if n.endswith(member_suffix):
            return tf.extractfile(n).read().decode()
    raise AssertionError((member_suffix, tf.getnames()))


def _plain_clone(home, tmp_path):
    clone = _clone_with_remote(home, tmp_path)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "local-only", cwd=clone)
    return clone


def _git_state_files(clone):
    d = clone / ".git"
    return {p.name: p.read_bytes() for p in d.iterdir()
            if p.name in ("MERGE_HEAD", "MERGE_MSG", "MERGE_MODE", "CHERRY_PICK_HEAD") and p.is_file()}


def test_commits_only_in_a_local_path_remotes_tracking_refs_are_bundled(tmp_path):
    import shutil
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    sib = tmp_path / "sib"
    sib.mkdir()
    _git("init", "-q", "-b", "feature", cwd=sib)
    (sib / "s").write_text("s")
    _git("add", "s", cwd=sib)
    _git("commit", "-qm", "sibling only commit", cwd=sib)
    _git("remote", "add", "sib", str(sib), cwd=clone)
    _git("fetch", "-q", "sib", "feature", cwd=clone)
    shutil.rmtree(sib)  # the sibling repo is gone after the teardown
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    (bundle,) = [b for b in (dest / "bundles").glob("*.bundle") if b.name.count(".") == 2]
    assert "refs/remotes/sib/feature" in _out("bundle", "list-heads", str(bundle), cwd=tmp_path)
    fresh = _fresh_clone(tmp_path)
    _git("fetch", "-q", str(bundle), "refs/remotes/sib/feature:refs/heads/rest", cwd=fresh)
    assert _out("log", "-1", "--format=%s", "rest", cwd=fresh).strip() == "sibling only commit"


def _snapshot(clone):
    return (_status(clone), _git_state_files(clone), (clone / ".git/rebase-merge").exists())


def test_merge_conflict_mixed_with_normal_hunks_is_reconstructable(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    (clone / "c.txt").write_text("a\nb\nc\nd\ne\n")
    _git("add", "c.txt", cwd=clone)
    _git("commit", "-qm", "c base", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    _git("checkout", "-q", "-b", "side", cwd=clone)
    (clone / "c.txt").write_text("a\nB-side\nc\nd\nE-side\n")
    _git("commit", "-qam", "side change", cwd=clone)
    side = _out("rev-parse", "HEAD", cwd=clone).strip()
    _git("checkout", "-q", "main", cwd=clone)
    (clone / "c.txt").write_text("a\nB-main\nc\nD-main\ne\n")
    _git("commit", "-qam", "main change", cwd=clone)
    _git("branch", "-D", "side", cwd=clone)  # MERGE_HEAD is now reachable only through MERGE_HEAD
    merge = subprocess.run(["git", "merge", side], cwd=clone, capture_output=True, text=True,
                           env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    assert merge.returncode != 0
    before = _snapshot(clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert _snapshot(clone) == before          # read-only, state files untouched
    assert "unmerged=1" in (dest / "DIRTY.txt").read_text() and "state=1" in (dest / "DIRTY.txt").read_text()
    wd = _wd(dest)
    txt = _tar_text(wd / "conflicted.tar.gz", "c.txt")
    assert "<<<<<<<" in txt and "D-main" in txt and "E-side" in txt
    stages = wd / "conflict-stages.tar.gz"
    assert _tar_text(stages, "stage1/c.txt") == "a\nb\nc\nd\ne\n"
    assert "B-main" in _tar_text(stages, "stage2/c.txt") and "B-side" in _tar_text(stages, "stage3/c.txt")
    assert _tar_text(wd / "inprogress.tar.gz", "MERGE_HEAD").strip() == side
    assert (wd / "NOTE.txt").exists()
    assert side in (dest / "EXTRA-REVS.txt").read_text()
    (sb,) = list((dest / "bundles").glob("*.bundle"))
    fresh = tmp_path / "fresh-mh"
    subprocess.run(["git", "init", "-q", str(fresh)], check=True)
    _git("fetch", "-q", str(sb), "+refs/*:refs/archive/*", cwd=fresh)
    assert _out("log", "-1", "--format=%s", side, cwd=fresh).strip() == "side change"
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0
    # verify refuses an archive whose conflicted tarball is gone
    (wd / "conflicted.tar.gz").unlink()
    assert _run("verify", "--dest", str(dest), env=env).returncode != 0


def test_rebase_in_progress_is_captured(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    (clone / "f").write_text("base\n")
    _git("add", "f", cwd=clone)
    _git("commit", "-qm", "f base", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    _git("checkout", "-q", "-b", "topic", cwd=clone)
    (clone / "t1").write_text("t1")
    _git("add", "t1", cwd=clone)
    _git("commit", "-qm", "t1", cwd=clone)
    (clone / "f").write_text("topic edit\n")
    _git("commit", "-qam", "t2", cwd=clone)
    _git("checkout", "-q", "main", cwd=clone)
    (clone / "f").write_text("main edit\n")
    _git("commit", "-qam", "m1", cwd=clone)
    _git("checkout", "-q", "topic", cwd=clone)
    rb = subprocess.run(["git", "rebase", "main"], cwd=clone, capture_output=True, text=True,
                        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "GIT_EDITOR": "true"})
    assert rb.returncode != 0 and (clone / ".git/rebase-merge").is_dir()
    before = _snapshot(clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert _snapshot(clone) == before and (clone / ".git/rebase-merge").is_dir()
    line = (dest / "DIRTY.txt").read_text()
    assert "state=1" in line and "unmerged=1" in line
    wd = _wd(dest)
    names = tarfile.open(wd / "inprogress.tar.gz").getnames()
    assert any(n.startswith("rebase-merge") for n in names), names
    assert "HEAD" in (dest / "EXTRA-REVS.txt").read_text()   # the detached, partly rebased HEAD
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0


def test_stash_entry_index_state_is_exported(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    (clone / "md").write_text("committed\n")
    _git("add", "md", cwd=clone)
    _git("commit", "-qm", "md", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    (clone / "md").write_text("staged content\n")
    _git("add", "md", cwd=clone)
    (clone / "md").unlink()
    _git("stash", "push", "-q", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest)
    idx = wd / "stash-0.index.patch"
    assert "staged content" in idx.read_text()
    subprocess.run(["git", "apply", "--check", str(idx)], cwd=_fresh_clone(tmp_path), check=True)
    idx.unlink()
    assert _run("verify", "--dest", str(dest), env=env).returncode != 0


def _locked_dir(home):
    d = home / "repos/locked"
    d.mkdir(parents=True)
    (d / "x").write_text("x")
    d.chmod(0)
    return d


def test_unreadable_paths_fail_verify_unless_accepted(tmp_path):
    home = _fixture_home(tmp_path)
    d = _locked_dir(home)
    try:
        r, dest, env, _ = _archive_ok(tmp_path, home=home)
        assert r.returncode == 0, r.stderr
        assert "unreadable:" in (dest / "SKIPPED.txt").read_text()
        v = _run("verify", "--dest", str(dest), env=env)
        assert v.returncode != 0 and "FAIL no unreadable or unusable paths" in v.stdout
        acc = tmp_path / "acc"
        acc.mkdir()
        r2, dest2, env2, _ = _archive_ok(acc, home=home, args=("--accept-unreadable",))
        assert r2.returncode == 0, r2.stderr
        assert "unreadable:" in (dest2 / "ACCEPTED.txt").read_text()
        v2 = _run("verify", "--dest", str(dest2), env=env2)
        assert v2.returncode == 0, v2.stdout
        assert "WARN unreadable or unusable paths, accepted" in v2.stdout
    finally:
        d.chmod(0o755)


def test_a_junk_repository_is_recorded_not_fatal(tmp_path):
    home = _fixture_home(tmp_path)
    junk = home / "repos/junk"
    junk.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=junk)
    (junk / ".git/HEAD").write_text("garbage\n")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert "not a usable git repository" in (dest / "SKIPPED.txt").read_text()
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0 and "FAIL no unreadable or unusable paths" in v.stdout


def test_every_git_call_passes_safe_directory_and_no_locale_dependent_class():
    src = SCRIPT.read_text()
    assert "-c safe.directory=*" in src
    assert "[a-zS]" not in src


def test_verify_live_compares_refs_and_skipped_paths(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _dirty_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    ok = _run("verify", "--live", "--dest", str(dest), env=env)
    assert ok.returncode == 0, ok.stdout
    assert "PASS live refs match" in ok.stdout and "PASS live skipped paths match" in ok.stdout
    _git("branch", "new-branch-after-archive", cwd=clone)
    v = _run("verify", "--live", "--dest", str(dest), env=env)
    assert v.returncode != 0 and "FAIL live refs match" in v.stdout
    _git("branch", "-D", "new-branch-after-archive", cwd=clone)
    d = _locked_dir(home)
    try:
        v2 = _run("verify", "--live", "--dest", str(dest), env=env)
        assert v2.returncode != 0 and "FAIL live skipped paths match" in v2.stdout
    finally:
        d.chmod(0o755)


def test_verify_warns_about_ignored_files_with_counts(tmp_path):
    home = _fixture_home(tmp_path)
    _dirty_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout
    assert "WARN ignored files are listed under ignored/" in v.stdout
    assert "ignored path(s):" in v.stdout


def test_deinitialised_submodule_commits_are_bundled(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
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
    _git("commit", "-qm", "sub local only", cwd=sub)
    _git("submodule", "deinit", "-f", "vendor/sub", cwd=clone)
    assert not (sub / ".git").exists()
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    bundles = [b for b in (dest / "bundles").glob("*.bundle") if "modules__vendor__sub" in b.name]
    assert bundles, sorted(p.name for p in (dest / "bundles").iterdir())
    fresh = tmp_path / "fresh-sub"
    subprocess.run(["git", "init", "-q", str(fresh)], check=True)
    _git("fetch", "-q", str(bundles[0]), "refs/heads/main:refs/heads/restored", cwd=fresh)
    assert _out("log", "-1", "--format=%s", "restored", cwd=fresh).strip() == "sub local only"


def test_a_tag_of_a_tag_keeps_the_inner_tag_object(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    _git("tag", "-a", "inner", "-m", "the inner tag", cwd=clone)
    _git("tag", "-a", "outer", "-m", "tag of a tag", "inner", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    fresh = tmp_path / "fresh-tags"
    subprocess.run(["git", "init", "-q", str(fresh)], check=True)
    _git("fetch", "-q", str(bundle), "+refs/tags/*:refs/tags/*", cwd=fresh)
    assert "the inner tag" in _out("cat-file", "-p", "inner", cwd=fresh)
    outer = _out("cat-file", "-p", "outer", cwd=fresh)
    assert "tag of a tag" in outer and "type tag" in outer


def test_pod_side_digest_match_is_an_exact_line_match(tmp_path):
    home = _fixture_home(tmp_path)
    _dirty_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    wd = _wd(dest)
    rel = f"worktrees/{wd.name}/status.txt"
    lines = (dest / "REMOTE.sha256").read_text().splitlines()
    digest = [l for l in lines if l.endswith("  " + rel)][0].split()[0]
    (wd / "status.txt.bak").write_bytes((wd / "status.txt").read_bytes())
    kept = [l for l in lines if not l.endswith("  " + rel)]
    kept.append(f"{digest}  {rel}.bak")          # a longer name that contains the path
    (dest / "REMOTE.sha256").write_text("\n".join(kept) + "\n")
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0 and "FAIL every worktrees/ file has a pod-side digest" in v.stdout


# --- archive round 3 -----------------------------------------------------------

GITENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
          "GIT_COMMITTER_EMAIL": "t@t", "GIT_EDITOR": "true"}


def _git_rc(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **GITENV})


def _restore_cmd(dest, worktree, target, env):
    return _run("restore-worktree", "--dest", str(dest), "--worktree", str(worktree),
                "--target", str(target), env=env)


def _same_state(orig, restored, extra=()):
    assert _out("status", "--porcelain=v1", cwd=restored) == _out("status", "--porcelain=v1", cwd=orig)
    assert _out("ls-files", "-s", cwd=restored) == _out("ls-files", "-s", cwd=orig)
    assert _out("rev-parse", "HEAD", cwd=restored) == _out("rev-parse", "HEAD", cwd=orig)
    for f in extra:
        assert (restored / f).read_bytes() == (orig / f).read_bytes(), f


def _make_merge_conflict(home, tmp_path):
    clone = _plain_clone(home, tmp_path)
    (clone / "c.txt").write_text("a\nb\nc\nd\ne\n")
    _git("add", "c.txt", cwd=clone)
    _git("commit", "-qm", "c base", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    _git("checkout", "-q", "-b", "side", cwd=clone)
    (clone / "c.txt").write_text("a\nB-side\nc\nd\nE-side\n")
    _git("commit", "-qam", "side change", cwd=clone)
    side = _out("rev-parse", "HEAD", cwd=clone).strip()
    _git("checkout", "-q", "main", cwd=clone)
    (clone / "c.txt").write_text("a\nB-main\nc\nD-main\ne\n")
    _git("commit", "-qam", "main change", cwd=clone)
    _git("branch", "-D", "side", cwd=clone)
    assert _git_rc("merge", side, cwd=clone).returncode != 0
    return clone, side


def test_restore_worktree_rebuilds_a_conflicted_merge_end_to_end(tmp_path):
    home = _fixture_home(tmp_path)
    clone, side = _make_merge_conflict(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    target = tmp_path / "restored"
    rr = _restore_cmd(dest, clone, target, env)
    assert rr.returncode == 0, rr.stdout + rr.stderr
    _same_state(clone, target, extra=("c.txt",))
    assert (target / ".git/MERGE_HEAD").read_bytes() == (clone / ".git/MERGE_HEAD").read_bytes()
    stages = _out("ls-files", "-s", "c.txt", cwd=target)
    assert [l.split()[2] for l in stages.splitlines()] == ["1", "2", "3"]   # no stage 0 left
    # resolving and committing must not silently take HEAD's side
    (target / "c.txt").write_text("a\nresolved\nc\nD-main\nE-side\n")
    _git("add", "c.txt", cwd=target)
    assert _git_rc("commit", "--no-edit", cwd=target).returncode == 0
    assert _out("show", "HEAD:c.txt", cwd=target) == "a\nresolved\nc\nD-main\nE-side\n"
    assert len(_out("rev-list", "--parents", "-n1", "HEAD", cwd=target).split()) == 3   # merge commit


def test_restore_worktree_rebuilds_a_rebase_in_progress_end_to_end(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    (clone / "f").write_text("base\n")
    _git("add", "f", cwd=clone)
    _git("commit", "-qm", "f base", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    _git("checkout", "-q", "-b", "topic", cwd=clone)
    (clone / "t1").write_text("t1")
    _git("add", "t1", cwd=clone)
    _git("commit", "-qm", "t1", cwd=clone)
    (clone / "f").write_text("topic edit\n")
    _git("commit", "-qam", "t2", cwd=clone)
    _git("checkout", "-q", "main", cwd=clone)
    (clone / "f").write_text("main edit\n")
    _git("commit", "-qam", "m1", cwd=clone)
    _git("checkout", "-q", "topic", cwd=clone)
    assert _git_rc("rebase", "main", cwd=clone).returncode != 0
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    target = tmp_path / "restored"
    rr = _restore_cmd(dest, clone, target, env)
    assert rr.returncode == 0, rr.stdout + rr.stderr
    _same_state(clone, target, extra=("f", "t1"))
    for n in ("head-name", "onto", "orig-head"):
        assert (target / ".git/rebase-merge" / n).read_bytes() == (clone / ".git/rebase-merge" / n).read_bytes(), n
    (target / "f").write_text("resolved\n")
    _git("add", "f", cwd=target)
    done = _git_rc("rebase", "--continue", cwd=target)
    assert done.returncode == 0, done.stderr
    assert _out("show", "topic:f", cwd=target) == "resolved\n"
    assert not (target / ".git/rebase-merge").exists()


def test_a_conflicted_submodule_does_not_abort_and_restores(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    src = tmp_path / "subsrc"
    src.mkdir()
    _git("init", "-q", "-b", "main", cwd=src)
    (src / "s").write_text("1")
    _git("add", "s", cwd=src)
    _git("commit", "-qm", "s1", cwd=src)
    _git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(src), "vendor/sub", cwd=clone)
    _git("commit", "-qm", "add sub", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    sub = clone / "vendor/sub"
    s1 = _out("rev-parse", "HEAD", cwd=sub).strip()
    _git("checkout", "-q", "-b", "a", cwd=clone)
    (sub / "s").write_text("A")
    _git("commit", "-qam", "sA", cwd=sub)
    _git("add", "vendor/sub", cwd=clone)
    _git("commit", "-qm", "A", cwd=clone)
    _git("checkout", "-q", "main", cwd=clone)
    _git("checkout", "-q", "--detach", s1, cwd=sub)
    (sub / "s").write_text("B")
    _git("commit", "-qam", "sB", cwd=sub)
    _git("checkout", "-q", "-b", "b", cwd=clone)
    _git("add", "vendor/sub", cwd=clone)
    _git("commit", "-qm", "B", cwd=clone)
    assert _git_rc("merge", "a", cwd=clone).returncode != 0
    assert "160000" in _out("ls-files", "-u", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest, "willikins")
    assert "160000" in (wd / "unmerged.z").read_bytes().decode()
    assert "vendor/sub" in (wd / "NOTE.txt").read_text()
    target = tmp_path / "restored"
    rr = _restore_cmd(dest, clone, target, env)
    assert rr.returncode == 0, rr.stdout + rr.stderr
    assert _out("ls-files", "-s", "vendor/sub", cwd=target) == _out("ls-files", "-s", "vendor/sub", cwd=clone)


def test_every_head_of_an_octopus_merge_is_bundled(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    shas = []
    for n in ("a", "b"):
        _git("checkout", "-q", "-b", n, "main", cwd=clone)
        (clone / f"{n}.txt").write_text(n)
        _git("add", f"{n}.txt", cwd=clone)
        _git("commit", "-qm", f"branch {n}", cwd=clone)
        shas.append(_out("rev-parse", "HEAD", cwd=clone).strip())
    _git("checkout", "-q", "main", cwd=clone)
    assert _git_rc("merge", "--no-commit", "a", "b", cwd=clone).returncode == 0
    assert len((clone / ".git/MERGE_HEAD").read_text().split()) == 2
    _git("branch", "-D", "a", "b", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    extra = (dest / "EXTRA-REVS.txt").read_text()
    assert shas[0] in extra and shas[1] in extra
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    fresh = tmp_path / "fresh-oct"
    subprocess.run(["git", "init", "-q", str(fresh)], check=True)
    _git("fetch", "-q", str(bundle), "+refs/*:refs/archive/*", cwd=fresh)
    for sha in shas:
        assert _out("cat-file", "-t", sha, cwd=fresh).strip() == "commit"


def test_uid_mismatched_repositories_do_not_abort_the_archive(tmp_path):
    home = _fixture_home(tmp_path)
    clone, _ = _make_merge_conflict(home, tmp_path)
    (clone / "creds").mkdir()
    (clone / "plain untracked.txt").write_text("u")
    r, dest, env, _ = _archive_ok(tmp_path, {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}, home=home)
    assert r.returncode == 0, r.stderr
    wd = _wd(dest)
    assert (wd / "untracked.tar.gz").exists() and (wd / "conflicted.tar.gz").exists()
    assert (wd / "conflict-stages.tar.gz").exists()


def test_no_inline_pod_script_runs_plain_git():
    import re
    src = SCRIPT.read_text()
    # pod-side bash -c bodies must start from the shared git wrapper ("$PODGITFN"'...'),
    # never from a bare single-quoted script that calls git directly
    for m in re.finditer(r"bash -c '([^']*)'", src):
        assert "git " not in m.group(1), m.group(1)[:80]
    assert src.count('bash -c "$PODGITFN"') >= 5


def test_hidden_and_untracked_lists_that_end_up_empty_still_archive(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    (clone / ".gitignore").write_text("scripts/\n")
    _git("add", ".gitignore", cwd=clone)
    _git("commit", "-qm", "ignore", cwd=clone)
    (clone / "id_rsa").write_text("only a credential is untracked")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert tarfile.open(_wd(dest) / "untracked.tar.gz").getnames() == []


def _empty_bare(tmp_path, name):
    bare = tmp_path / name
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    return bare


def _refs(repo):
    return sorted(_out("for-each-ref", "--format=%(objectname) %(refname)", "refs/", cwd=repo).splitlines())


def test_a_branch_living_only_in_a_stale_tracking_ref_is_restorable(tmp_path):
    import shutil
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    _git("checkout", "-q", "-b", "feature", cwd=clone)
    (clone / "ft").write_text("ft")
    _git("add", "ft", cwd=clone)
    _git("commit", "-qm", "only upstream had this", cwd=clone)
    _git("push", "-q", "origin", "feature", cwd=clone)
    _git("checkout", "-q", "main", cwd=clone)
    _git("branch", "-D", "feature", cwd=clone)
    subprocess.run(["git", "-C", str(tmp_path / "remote.git"), "branch", "-D", "feature"], check=True)
    assert "refs/remotes/origin/feature" in _out("for-each-ref", "refs/remotes", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    shutil.rmtree(tmp_path / "remote.git")
    bare = _empty_bare(tmp_path, "restored.git")
    _git("fetch", "-q", str(bundle), "+refs/*:refs/*", cwd=bare)
    assert _out("log", "-1", "--format=%s", "refs/remotes/origin/feature", cwd=bare).strip() == "only upstream had this"


def test_bundles_have_no_prerequisites_so_a_vanished_upstream_does_not_matter(tmp_path):
    import shutil
    home = _fixture_home(tmp_path)
    _clone_with_remote(home, tmp_path)       # local-only branch on top of a pushed main
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    shutil.rmtree(tmp_path / "remote.git")   # upstream gone (or force-pushed away)
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    empty = tmp_path / "empty"
    subprocess.run(["git", "init", "-q", str(empty)], check=True)
    ok = subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=empty, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert "requires" not in (ok.stdout + ok.stderr).lower() or "does not require" in (ok.stdout + ok.stderr).lower()
    bare = _empty_bare(tmp_path, "restored.git")
    _git("fetch", "-q", str(bundle), "+refs/heads/*:refs/heads/*", cwd=bare)
    assert _out("log", "-1", "--format=%s", "local-only", cwd=bare).strip() == "two"


def test_a_clean_fully_pushed_clone_still_gets_a_bundle_with_identical_refs(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    (clone / ".gitignore").write_text("scripts/\n")
    _git("add", ".gitignore", cwd=clone)
    _git("commit", "-qm", "ignore", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    _git("tag", "-a", "v9", "-m", "tag", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert _worktrees_dirs(dest) == []
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    bare = _empty_bare(tmp_path, "restored.git")
    _git("fetch", "-q", str(bundle), "+refs/*:refs/*", cwd=bare)
    assert _refs(bare) == _refs(clone)
    assert (dest / "LOCAL-ONLY.txt").read_text() == ""


def test_verify_requires_one_valid_bundle_per_clone_and_sizes_are_reported(tmp_path):
    home = _fixture_home(tmp_path)
    _plain_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert "git dir on the pod" in r.stdout and "bundles:" in r.stdout
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    keep = bundle.read_bytes()
    bundle.unlink()
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0 and "FAIL bundle present" in v.stdout
    bundle.write_bytes(keep)
    rec = (dest / "BUNDLES.txt").read_text()
    (dest / "BUNDLES.txt").write_text("")
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0 and "FAIL bundle recorded" in v.stdout
    (dest / "BUNDLES.txt").write_text(rec)


# --- archive round 4 -----------------------------------------------------------

def _autostash_rebase_fixture(home, tmp_path):
    clone = _plain_clone(home, tmp_path)
    (clone / "f").write_text("base\n")
    (clone / "u.txt").write_text("committed u\n")
    _git("add", "f", "u.txt", cwd=clone)
    _git("commit", "-qm", "base files", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    _git("checkout", "-q", "-b", "topic", cwd=clone)
    (clone / "f").write_text("topic edit\n")
    _git("commit", "-qam", "t2", cwd=clone)
    _git("checkout", "-q", "main", cwd=clone)
    (clone / "f").write_text("main edit\n")
    _git("commit", "-qam", "m1", cwd=clone)
    _git("checkout", "-q", "topic", cwd=clone)
    (clone / "u.txt").write_text("uncommitted autostashed edit\n")
    assert _git_rc("rebase", "--autostash", "main", cwd=clone).returncode != 0
    assert (clone / ".git/rebase-merge/autostash").exists()
    return clone


def test_a_rebase_autostash_survives_archive_restore_and_continue(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _autostash_rebase_fixture(home, tmp_path)
    auto = (clone / ".git/rebase-merge/autostash").read_text().strip()
    state_before = (clone / ".git/rebase-merge/autostash").read_bytes()
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert (clone / ".git/rebase-merge/autostash").read_bytes() == state_before
    assert auto in (dest / "EXTRA-REVS.txt").read_text()
    assert "rebase-merge/" in (dest / "EXTRA-REVS.txt").read_text()   # other state files are mined too
    wd = _wd(dest)
    assert "uncommitted autostashed edit" in (wd / "autostash-0.patch").read_text()
    # (c) the commit is fetchable from the bundle alone
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    only = tmp_path / "only-bundle"
    subprocess.run(["git", "init", "-q", str(only)], check=True)
    _git("fetch", "-q", str(bundle), "+refs/*:refs/archive/*", cwd=only)
    assert _out("cat-file", "-t", auto, cwd=only).strip() == "commit"
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0
    # (a) restore, resolve, continue: the autostashed edit comes back
    target = tmp_path / "restored"
    rr = _restore_cmd(dest, clone, target, env)
    assert rr.returncode == 0, rr.stdout + rr.stderr
    assert (target / ".git/rebase-merge/autostash").read_text().strip() == auto
    (target / "f").write_text("resolved\n")
    _git("add", "f", cwd=target)
    done = _git_rc("rebase", "--continue", cwd=target)
    assert done.returncode == 0, done.stderr
    assert (target / "u.txt").read_text() == "uncommitted autostashed edit\n"
    # verify fails when the state file names an autostash that the bundles do not hold
    ex = (dest / "EXTRA-REVS.txt").read_text()
    (dest / "EXTRA-REVS.txt").write_text("\n".join(l for l in ex.splitlines() if auto not in l) + "\n")
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0 and "FAIL autostash commits are in the bundles" in v.stdout


def test_a_merge_autostash_survives_archive_restore_and_commit(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    (clone / "c.txt").write_text("a\nb\nc\n")
    (clone / "u.txt").write_text("committed u\n")
    _git("add", "c.txt", "u.txt", cwd=clone)
    _git("commit", "-qm", "base", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    _git("checkout", "-q", "-b", "side", cwd=clone)
    (clone / "c.txt").write_text("a\nside\nc\n")
    _git("commit", "-qam", "side change", cwd=clone)
    _git("checkout", "-q", "main", cwd=clone)
    (clone / "c.txt").write_text("a\nmain\nc\n")
    _git("commit", "-qam", "main change", cwd=clone)
    (clone / "u.txt").write_text("merge autostashed edit\n")
    assert _git_rc("merge", "--autostash", "side", cwd=clone).returncode != 0
    assert (clone / ".git/MERGE_AUTOSTASH").exists()
    auto = (clone / ".git/MERGE_AUTOSTASH").read_text().strip()
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    assert auto in (dest / "EXTRA-REVS.txt").read_text()
    assert "merge autostashed edit" in (_wd(dest) / "autostash-0.patch").read_text()
    target = tmp_path / "restored"
    rr = _restore_cmd(dest, clone, target, env)
    assert rr.returncode == 0, rr.stdout + rr.stderr
    (target / "c.txt").write_text("a\nresolved\nc\n")
    _git("add", "c.txt", cwd=target)
    assert _git_rc("commit", "--no-edit", cwd=target).returncode == 0
    assert (target / "u.txt").read_text() == "merge autostashed edit\n"


def test_restore_of_a_dirty_unborn_repository_without_a_bundle(tmp_path):
    home = _fixture_home(tmp_path)
    repo = home / "repos/unborn"
    repo.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / "a").write_text("staged\n")
    _git("add", "a", cwd=repo)
    (repo / "a").write_text("staged\nunstaged\n")
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    target = tmp_path / "restored"
    rr = _restore_cmd(dest, repo, target, env)
    assert rr.returncode == 0, rr.stdout + rr.stderr
    assert _out("status", "--porcelain=v1", cwd=target) == _out("status", "--porcelain=v1", cwd=repo)
    assert _out("ls-files", "-s", cwd=target) == _out("ls-files", "-s", cwd=repo)


def test_restored_stashes_come_back_in_order_with_their_messages(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    (clone / "s.txt").write_text("base\n")
    _git("add", "s.txt", cwd=clone)
    _git("commit", "-qm", "s", cwd=clone)
    _git("push", "-q", "origin", "main", cwd=clone)
    for msg in ("first stash", "second stash", "third stash"):
        (clone / "s.txt").write_text(msg + "\n")
        _git("stash", "push", "-q", "-m", msg, cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    target = tmp_path / "restored"
    rr = _restore_cmd(dest, clone, target, env)
    assert rr.returncode == 0, rr.stdout + rr.stderr
    assert _out("stash", "list", cwd=target) == _out("stash", "list", cwd=clone)
    assert _out("stash", "show", "-p", "stash@{2}", cwd=target) == _out("stash", "show", "-p", "stash@{2}", cwd=clone)


def test_restore_reapplies_skip_worktree_and_assume_unchanged_bits(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
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
    target = tmp_path / "restored"
    rr = _restore_cmd(dest, clone, target, env)
    assert rr.returncode == 0, rr.stdout + rr.stderr
    assert _out("ls-files", "-v", cwd=target) == _out("ls-files", "-v", cwd=clone)
    assert _out("status", "--porcelain=v1", cwd=target) == _out("status", "--porcelain=v1", cwd=clone)
    assert (target / "sw").read_text() == "edited sw\n"


def _df_stub(tmp_path, free_kb):
    df = tmp_path / "df-stub"
    df.write_text(f"#!/bin/sh\necho 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
                  f"echo '/dev/x 100000 1 {free_kb} 1% /'\n")
    df.chmod(0o755)
    return str(df)


def test_space_preflight_aborts_when_free_space_is_short(tmp_path):
    home = _fixture_home(tmp_path)
    _plain_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, {"DF": _df_stub(tmp_path, 1)}, home=home)
    assert r.returncode != 0
    assert "not enough free space" in r.stderr and "--skip-space-check" in r.stderr
    assert "space check:" in r.stdout
    assert not (dest / "secure-agent-pod-home.tar.gz").exists()   # nothing streamed yet


def test_space_preflight_can_be_skipped_and_passes_with_room(tmp_path):
    home = _fixture_home(tmp_path)
    _plain_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, {"DF": _df_stub(tmp_path, 1)}, home=home, args=("--skip-space-check",))
    assert r.returncode == 0, r.stderr
    assert "continuing because of --skip-space-check" in r.stderr
    sub = tmp_path / "roomy"
    sub.mkdir()
    h2 = _fixture_home(sub)
    r2, dest2, _, _ = _archive_ok(sub, {"DF": _df_stub(sub, 10_000_000)}, home=h2)
    assert r2.returncode == 0, r2.stderr
    assert "space check:" in r2.stdout


# --- ~/.claude in the home tarball ---------------------------------------------

CLAUDE_KEPT = (
    ".claude/projects/slug/0000-uuid.jsonl", ".claude/projects/slug/memory/MEMORY.md",
    ".claude/CLAUDE.md", ".claude/settings.json", ".claude/settings.local.json",
    ".claude/history.jsonl",
    # joined, not literal: validate-agent-config.sh rejects these two paths under scripts/
    "/".join((".claude", "agents", "a.md")), "/".join((".claude", "commands", "c.md")),
    ".claude/skills/s/SKILL.md", ".claude/hooks/h.sh", ".claude/plans/p.md",
    ".claude/memory/m.md", ".claude/todos/t.json", ".claude/ide/state.json",
)
CLAUDE_DROPPED_FILES = (
    ".claude/.credentials.json", ".claude/credentials.json", ".claude/x.token",
    ".claude/oauth-state.json", ".claude/.mcp-auth/f", ".claude/mcp-auth-cache.json",
    ".claude/ide/1234.lock", ".claude/top.lock",
)
CLAUDE_DROPPED_DIRS = (
    ".claude/statsig", ".claude/shell-snapshots", ".claude/cache", ".claude/.cache",
    ".claude/plugins/cache", ".claude/plugins/marketplaces", ".claude/node_modules",
)


def _claude_home(tmp_path):
    home = _fixture_home(tmp_path)
    for rel in CLAUDE_KEPT + CLAUDE_DROPPED_FILES + tuple(d + "/x" for d in CLAUDE_DROPPED_DIRS):
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("data")
    for rel in ("orgs/x/cache/file", "interviews/logs/file", "orgs/x/statsig/file",
                "orgs/x/plugins/cache/file"):
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("keep")
    return home


def test_claude_home_is_archived_without_credentials_and_caches(tmp_path):
    home = _claude_home(tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    names = tarfile.open(dest / "secure-agent-pod-home.tar.gz").getnames()
    for kept in CLAUDE_KEPT:
        assert kept in names, (kept, names)
    for gone in CLAUDE_DROPPED_FILES:
        assert gone not in names, gone
    for d in CLAUDE_DROPPED_DIRS:
        assert not any(n == d or n.startswith(d + "/") for n in names), d
    # the cache excludes are anchored to .claude: other trees keep same-named dirs
    for kept in ("orgs/x/cache/file", "interviews/logs/file", "orgs/x/statsig/file",
                 "orgs/x/plugins/cache/file"):
        assert kept in names, kept
    ex = (dest / "EXCLUDED.txt").read_text().splitlines()
    assert any(l.endswith(".claude/.credentials.json") for l in ex), ex
    for d in CLAUDE_DROPPED_DIRS:
        lines = [l for l in ex if l.endswith(d)]
        assert len(lines) == 1, (d, ex)
    assert not any(l.endswith("statsig/x") for l in ex)       # one line per cache directory
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout
    assert "INFO .claude/projects is in the tarball" in v.stdout


def test_a_missing_claude_projects_is_a_warning_not_a_failure(tmp_path):
    r, dest, env, _ = _archive_ok(tmp_path)
    assert r.returncode == 0, r.stderr
    assert ".claude" in (dest / "SKIPPED.txt").read_text().splitlines()
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout
    assert "WARN .claude/projects is not in the tarball" in v.stdout


def test_verify_fails_when_a_claude_credential_is_in_the_tarball(tmp_path):
    home = _claude_home(tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, home=home)
    assert r.returncode == 0, r.stderr
    t = dest / "secure-agent-pod-home.tar.gz"
    with tarfile.open(t, "w:gz") as tf:
        for n in ("interviews", "orgs"):
            tf.add(home / n, arcname=n)
        tf.add(home / "repos/willikins/scripts/chorebot/config.yaml",
               arcname="repos/willikins/scripts/chorebot/config.yaml")
        tf.add(home / ".claude/x.token", arcname=".claude/x.token")
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode != 0 and "FAIL no credential files in tarball" in v.stdout


def test_the_usage_text_lists_the_claude_exclusions():
    usage = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True).stderr
    for needle in (".claude", "statsig", "shell-snapshots", "plugins/cache", "transcripts"):
        assert needle in usage, needle


# --- bounded retry of cut exec streams; session guard vs sshd ---------------------

def _calls(tmp_path, word):
    log = tmp_path / "calls.log"
    return [l for l in log.read_text().splitlines() if word in l] if log.exists() else []


def test_a_probe_cut_on_the_first_attempt_succeeds_on_the_second(tmp_path):
    home = _fixture_home(tmp_path)
    _plain_clone(home, tmp_path)
    ref_env = tmp_path / "ref"
    ref_env.mkdir()
    h2 = _fixture_home(ref_env)
    _plain_clone(h2, ref_env)
    r0, dest0, _, _ = _archive_ok(ref_env, home=h2)
    assert r0.returncode == 0, r0.stderr
    r, dest, env, _ = _archive_ok(tmp_path, {"STUB_FAULT": "drop", "STUB_FAULT_MATCH": "for-each-ref",
                                             "STUB_FAULT_TIMES": "1"}, home=home)
    assert r.returncode == 0, r.stderr
    assert "retry: stream refs.txt attempt 1/4" in r.stderr
    assert "refs.txt\t2" in (dest / "RETRIES.txt").read_text()
    assert len(_calls(tmp_path, "for-each-ref")) == 2
    # identical to an uncut run (paths differ by tmp dir, so compare the ref listings' shapes)
    got = sorted(l.split("\t")[:2] for p in (dest / "refs").iterdir() for l in p.read_text().splitlines())
    want = sorted(l.split("\t")[:2] for p in (dest0 / "refs").iterdir() for l in p.read_text().splitlines())
    assert [g[0] for g in got] == [w[0] for w in want]
    v = _run("verify", "--dest", str(dest), env=env)
    assert v.returncode == 0, v.stdout
    assert "INFO archive needed retries" in v.stdout and "refs.txt" in v.stdout


def test_a_large_stream_cut_twice_then_succeeding_is_byte_identical(tmp_path):
    home = _fixture_home(tmp_path)
    clone = _plain_clone(home, tmp_path)
    (clone / "big.bin").write_bytes(os.urandom(600_000))
    _git("add", "big.bin", cwd=clone)
    _git("commit", "-qm", "big", cwd=clone)
    r, dest, env, _ = _archive_ok(tmp_path, {"STUB_FAULT": "cut", "STUB_FAULT_MATCH": "bundle",
                                             "STUB_FAULT_TIMES": "2", "STUB_FAULT_BYTES": "100000"}, home=home)
    assert r.returncode == 0, r.stderr
    (bundle,) = list((dest / "bundles").glob("*.bundle"))
    sha = subprocess.run(["shasum", "-a", "256", str(bundle)], capture_output=True, text=True).stdout.split()[0]
    lines = [l for l in (dest / "REMOTE.sha256").read_text().splitlines() if l.endswith(bundle.name)]
    assert lines == [f"{sha}  bundles/{bundle.name}"]
    assert not list(dest.rglob("*.part"))
    assert subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=tmp_path / "home" / "repos" / "willikins",
                          capture_output=True).returncode == 0
    assert r.stderr.count("retry: stream") == 2
    assert _run("verify", "--dest", str(dest), env=env).returncode == 0


def test_four_cuts_in_a_row_die_with_the_attempt_count_and_leave_nothing(tmp_path):
    home = _fixture_home(tmp_path)
    _plain_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, {"STUB_FAULT": "drop", "STUB_FAULT_MATCH": "bundle"}, home=home)
    assert r.returncode != 0
    assert "after 4 attempts" in r.stderr and r.stderr.count("retry: stream") == 3
    assert not list(dest.rglob("*.part")) and not list((dest / "bundles").glob("*.bundle"))
    assert "bundles/" not in (dest / "REMOTE.sha256").read_text()


def test_a_real_nonzero_pod_exit_status_is_not_retried(tmp_path):
    home = _fixture_home(tmp_path)
    _plain_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, {"STUB_FAIL_RC": "rev-list"}, home=home)
    assert r.returncode != 0
    assert "retry: stream" not in r.stderr
    assert "exit 7" in r.stderr
    assert len(_calls(tmp_path, "rev-list")) == 1


def test_a_digest_mismatch_and_a_missing_status_line_are_retried(tmp_path):
    for mode in ("flip", "nostatus", "cut"):
        sub = tmp_path / mode
        sub.mkdir()
        home = _fixture_home(sub)
        _plain_clone(home, sub)
        r, dest, env, _ = _archive_ok(sub, {"STUB_FAULT": mode, "STUB_FAULT_MATCH": "--count",
                                            "STUB_FAULT_TIMES": "1", "STUB_FAULT_BYTES": "1"}, home=home)
        assert r.returncode == 0, (mode, r.stderr)
        assert "retry: stream count attempt 1/4" in r.stderr, mode
        assert "count\t2" in (dest / "RETRIES.txt").read_text(), mode


def test_retries_are_reported_at_the_end_of_archive(tmp_path):
    home = _fixture_home(tmp_path)
    _plain_clone(home, tmp_path)
    r, dest, env, _ = _archive_ok(tmp_path, {"STUB_FAULT": "drop", "STUB_FAULT_MATCH": "--count",
                                             "STUB_FAULT_TIMES": "2"}, home=home)
    assert r.returncode == 0, r.stderr
    assert "transport retries: 1 stream(s)" in r.stdout
    assert "count\t3" in (dest / "RETRIES.txt").read_text()
    clean = tmp_path / "clean"
    clean.mkdir()
    h2 = _fixture_home(clean)
    r2, dest2, env2, _ = _archive_ok(clean, home=h2)
    assert (dest2 / "RETRIES.txt").read_text() == ""
    assert "INFO archive needed retries" not in _run("verify", "--dest", str(dest2), env=env2).stdout


def test_the_session_guard_ignores_sshd_logins_but_not_real_sessions(tmp_path):
    sshd = "sshd-session: claude [postauth]\n"
    for i, (ps, blocked) in enumerate((
            (sshd, False),
            ("/usr/sbin/sshd -D\nsshd: claude@pts/0\n", False),
            ("bash\nsu - claude\nsudo -u claude bash\n", False),
            (sshd + "claude --resume abc\n", True),
            (sshd + "node /home/claude/.npm/claude-code/cli.js\n", True),
            ("tmux: server\n", True),
            ("herdr serve\n", True),
            ("/home/claude/.local/share/claude/versions/2.1.0 --resume x\n", True))):
        sub = tmp_path / f"g{i}"
        sub.mkdir()
        env = _env(sub, ps=ps, home=_fixture_home(sub))
        out = _run("archive", "--dest", str(sub / "arch"), env=env)
        if blocked:
            assert out.returncode != 0 and "interactive session still running" in out.stderr, ps
        else:
            assert "interactive session still running" not in out.stderr, ps


def test_key_fingerprint_retries_a_failing_kubectl_read(tmp_path):
    import base64
    a = base64.b64encode(b"pem-a").decode()
    env = _key_env(tmp_path, a, a)
    # a kubectl that fails twice, then answers
    kubectl = tmp_path / "kubectl"
    cnt = tmp_path / "kcount"
    kubectl.write_text("#!/usr/bin/env bash\nn=$(cat '%s' 2>/dev/null || echo 0)\necho $((n+1)) > '%s'\n"
                       "if [ \"$n\" -lt 2 ]; then exit 1; fi\nprintf '%%s' '%s'\n" % (cnt, cnt, a))
    kubectl.chmod(0o755)
    env["ARCHIVE_RETRY_DELAYS"] = "0 0 0"
    ok = _run("key-fingerprint", "--old-file-gone-ok", env=env)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert int(cnt.read_text()) == 3
