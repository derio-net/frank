"""Behaviour tests for scripts/gitea-repair-empty-objects.sh.

THE FAILURE. On 2026-08-01 an unclean stop left 13 zero-byte loose objects in
Gitea's copy of derio-homelab/kid-laptops (frank#849). It sat silent for ten
weeks, then the first new push (2026-10-13 16:50Z) made every
`derio-homelab-pull-sync` run fail in seconds: Gitea's unpacker could not
resolve the pack's deltas against the empty bases, and `main` itself pointed at
one of the empty objects.

THE OBVIOUS FIX IS WRONG. frank#849 proposed "delete the empty loose objects,
then re-push from GitHub". Measured on a copy of the real repo: that leaves
`refs/heads/main` pointing at a missing commit and the re-push is rejected the
same way, because the pushing client assumes the remote already HAS those
objects and never re-sends them. The objects must be put back explicitly,
from a clone of the authoritative source.

These tests build a small replica of the incident (loose objects, a delta
against a zeroed base, a zeroed branch tip) and pin both halves: the naive fix
fails, the script's fix works.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "gitea-repair-empty-objects.sh"

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    # keep the developer's global config (hooks, signing, templates) out of it
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def git(*args: str, cwd: Path | None = None, check: bool = True, git_dir: Path | None = None):
    cmd = ["git"]
    if git_dir is not None:
        cmd += [f"--git-dir={git_dir}"]
    cmd += list(args)
    return subprocess.run(cmd, cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=check)


def _body(n: int) -> str:
    # large and line-oriented, so a one-line edit becomes a DELTA in a pack
    return "\n".join(f"line {i} of a configuration file, revision {n}" for i in range(400)) + "\n"


class Incident:
    """A GitHub-like source clone plus a Gitea-like bare copy with zeroed objects."""

    def __init__(self, root: Path):
        self.src = root / "src"
        self.bare = root / "gitea.git"
        self.zeroed: list[str] = []

        git("init", "-q", "-b", "main", str(self.src))
        (self.src / "a.txt").write_text(_body(0))
        (self.src / "b.txt").write_text(_body(1))
        git("add", "-A", cwd=self.src)
        git("commit", "-q", "-m", "c1", cwd=self.src)
        (self.src / "a.txt").write_text(_body(0).replace("line 7 ", "line 7 EDITED "))
        git("commit", "-q", "-am", "c2", cwd=self.src)

        # Gitea's copy: keep objects LOOSE (as on the real instance) so they can be zeroed.
        git("init", "-q", "--bare", "-b", "main", str(self.bare))
        git("config", "receive.unpackLimit", "100000", git_dir=self.bare)
        git("push", "-q", str(self.bare), "main:main", cwd=self.src)

        # Zero the branch tip and the base blob of a.txt, as the unclean stop did.
        tip = git("rev-parse", "HEAD", cwd=self.src).stdout.strip()
        base_blob = git("rev-parse", "HEAD~1:a.txt", cwd=self.src).stdout.strip()
        for h in (tip, base_blob):
            p = self.bare / "objects" / h[:2] / h[2:]
            assert p.exists(), "fixture expects loose objects"
            p.unlink()  # git writes loose objects 0444; replace rather than overwrite
            p.write_bytes(b"")
            self.zeroed.append(h)

        # The next real commit upstream: a.txt edited again => thin delta against the zeroed base.
        (self.src / "a.txt").write_text(_body(0).replace("line 7 ", "line 7 EDITED AGAIN "))
        git("commit", "-q", "-am", "c3", cwd=self.src)
        self.new_head = git("rev-parse", "HEAD", cwd=self.src).stdout.strip()

    def empties(self) -> list[str]:
        return sorted(
            p.parent.name + p.name
            for p in (self.bare / "objects").glob("??/*")
            if p.is_file() and p.stat().st_size == 0
        )

    def push(self) -> subprocess.CompletedProcess:
        return git("push", "-q", str(self.bare), "main:main", cwd=self.src, check=False)

    def fsck_output(self) -> str:
        r = git("fsck", "--no-dangling", git_dir=self.bare, check=False)
        return (r.stdout + r.stderr).strip()


@pytest.fixture()
def incident(tmp_path: Path) -> Incident:
    return Incident(tmp_path)


def run_script(inc: Incident, *extra: str) -> subprocess.CompletedProcess:
    env = {**GIT_ENV, "GITEA_EXEC": "", "GITEA_REPOS_DIR": str(inc.bare.parent)}
    return subprocess.run(
        ["bash", str(SCRIPT), "--repo", inc.bare.name.removesuffix(".git"), "--source", str(inc.src), *extra],
        env=env,
        capture_output=True,
        text=True,
    )


def test_fixture_reproduces_the_incident(incident: Incident):
    """Guard the guard: the replica must actually fail the way production did."""
    assert sorted(incident.zeroed) == incident.empties()
    r = incident.push()
    assert r.returncode != 0, "a push against zeroed delta bases must be rejected"
    assert "unpack" in (r.stderr + r.stdout).lower() or "empty" in (r.stderr + r.stdout).lower()


def test_deleting_the_empty_objects_and_repushing_does_not_repair_it(incident: Incident):
    """frank#849's proposed fix. Measured wrong on the real repo; pinned here."""
    for h in incident.empties():
        (incident.bare / "objects" / h[:2] / h[2:]).unlink()

    # main now points at a missing commit ...
    assert "refs/heads/main: invalid sha1 pointer" in incident.fsck_output()
    # ... and the client still will not re-send what it believes the remote has.
    assert incident.push().returncode != 0


def test_dry_run_changes_nothing(incident: Incident):
    before = incident.empties()
    r = run_script(incident)
    assert r.returncode == 0, r.stderr
    assert incident.empties() == before
    for h in before:
        assert h in r.stdout


def test_apply_restores_a_clean_repo_and_unblocks_the_push(incident: Incident):
    r = run_script(incident, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr

    assert incident.empties() == []
    assert incident.fsck_output() == "", incident.fsck_output()
    for h in incident.zeroed:
        assert git("cat-file", "-e", h, git_dir=incident.bare, check=False).returncode == 0

    push = incident.push()
    assert push.returncode == 0, push.stderr
    assert git("rev-parse", "main", git_dir=incident.bare).stdout.strip() == incident.new_head


def test_apply_is_idempotent_on_a_clean_repo(incident: Incident):
    assert run_script(incident, "--apply").returncode == 0
    again = run_script(incident, "--apply")
    assert again.returncode == 0, again.stderr
    assert "no empty" in again.stdout.lower()


def test_apply_refuses_when_the_source_cannot_supply_an_object(incident: Incident):
    """Deleting an empty object the source cannot re-supply would turn a loud
    failure into a silent hole. Abort BEFORE touching anything."""
    ghost = "ab" + "0" * 38
    ghost_path = incident.bare / "objects" / "ab" / ("0" * 38)
    ghost_path.parent.mkdir(exist_ok=True)
    ghost_path.write_bytes(b"")

    before = incident.empties()
    r = run_script(incident, "--apply")

    assert r.returncode == 2, r.stdout + r.stderr
    assert ghost in r.stdout + r.stderr
    assert incident.empties() == before, "nothing may be deleted when the plan is unsafe"


def test_allow_missing_repairs_what_it_can_and_reports_the_rest(incident: Incident):
    ghost_path = incident.bare / "objects" / "ab" / ("0" * 38)
    ghost_path.parent.mkdir(exist_ok=True)
    ghost_path.write_bytes(b"")

    r = run_script(incident, "--apply", "--allow-missing")
    assert r.returncode == 0, r.stdout + r.stderr
    assert incident.empties() == []
    assert ("ab" + "0" * 38) in r.stdout, "the unrecoverable object must still be reported"
