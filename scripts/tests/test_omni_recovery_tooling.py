"""Tripwire: the Omni legacy-config recovery tooling must keep its three guarantees.

`scripts/omni-legacy-recovery/` is break-glass tooling for the Omni v1.5 rollback
race (see docs/runbooks/frank-gotchas/omni.md, "Rollback race on Omni v1.5"). It
is exercised approximately never — the 2026-08-01 dual-issuer incident is the
only time it has been needed — which is exactly why it needs a guard. Tooling
that is only read during an outage cannot be debugged during one.

Three properties are load-bearing, and all three were defects in the original
scratch scripts this was reconstructed from:

1. THE MARKER CONTENT MUST DIFFER ON EVERY RUN. The mechanism is the config-hash
   change; identical content produces no hash change, so Omni resends nothing.
   The originals hardcoded the content and were hand-bumped `-v1`/`-v2`/`-v3`
   across attempts — each bump is a run that silently did nothing.

2. EVERY WRITTEN PATH MUST BE UNDER /var. Talos v1.12 rejects `machine.files`
   `op: create` outside /var during boot and the machine stops before kubelet,
   trustd and etcd. That rejection IS the outage this tooling recovers from;
   writing the recovery marker outside /var would re-cause it.

3. MACHINES MUST BE DERIVED FROM OMNI, NOT HARDCODED. The originals pinned seven
   UUIDs. They happen to still be valid (machine UUIDs are hardware-derived and
   survived the Omni rebuild), which is the trap: a hardcoded list keeps working
   right up until a node is replaced, then silently skips it — and the wait loop
   compares against the wrong denominator, reporting "all recovered".

The render test stubs `omnictl` rather than asserting on the script text, so it
exercises the real generation path with no cluster.
"""

import json
import os
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_DIR = REPO_ROOT / "scripts/omni-legacy-recovery"
SCRIPTS = ["force-recovery.sh", "wait-recovery.sh", "remove-recovery.sh"]

# Two machines is enough to prove per-machine rendering; the hostnames are
# arbitrary and deliberately NOT the real fleet, so the test cannot quietly
# start depending on live cluster shape.
FAKE_MACHINES = [
    {"metadata": {"id": "aaaaaaaa-0000-0000-0000-000000000001",
                  "labels": {"omni.sidero.dev/hostname": "test-node-a"}}},
    {"metadata": {"id": "bbbbbbbb-0000-0000-0000-000000000002",
                  "labels": {"omni.sidero.dev/hostname": "test-node-b"}}},
]


def test_scripts_exist_and_are_executable():
    for name in SCRIPTS:
        p = TOOL_DIR / name
        assert p.is_file(), f"missing {p.relative_to(REPO_ROOT)}"
        assert p.stat().st_mode & stat.S_IXUSR, f"{name} is not executable"


def test_readme_exists():
    assert (TOOL_DIR / "README.md").is_file(), "break-glass tooling with no README"


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_fail_fast(name):
    """`set -e`/`-u`/`-o pipefail` — a recovery script must not limp on."""
    body = (TOOL_DIR / name).read_text()
    assert "set -euo pipefail" in body, f"{name} lacks `set -euo pipefail`"


@pytest.mark.parametrize("name", SCRIPTS)
def test_no_hardcoded_machine_uuids(name):
    """Guarantee 3. Machines come from Omni, so a replaced node cannot be skipped."""
    body = (TOOL_DIR / name).read_text()
    # The original scripts' seven pinned UUIDs. Any of them reappearing means
    # someone re-hardcoded the fleet.
    for uuid in (
        "ce4d0d52-6c10-bdc9-746c-88aedd67681b",
        "6ea7c1c6-6ba6-b59d-c77a-88aedd676447",
        "d1f01c97-d17e-e3ef-12ee-88aedd6768b6",
        "03de0294-0480-05ab-3106-410700080009",
        "03ff0210-04e0-05b0-ab06-300700080009",
        "30303031-3030-3030-3662-353662376100",
        "30303031-3030-3030-3337-613762353000",
    ):
        assert uuid not in body, (
            f"{name} hardcodes machine UUID {uuid}; derive from omnictl instead "
            "so a replaced node is not silently skipped"
        )


def test_wait_requires_multiple_stable_samples():
    """Omni can report 'applied' immediately before a scheduled reboot."""
    body = (TOOL_DIR / "wait-recovery.sh").read_text()
    assert "STABLE_SAMPLES" in body, "wait-recovery.sh accepts a single sample as recovery"
    assert "stable=0" in body, "wait-recovery.sh never resets its stability counter"


def _stub_env(tmp_path: Path) -> tuple[Path, dict]:
    """A fake BASE_REPO with .env/.env_devops, plus a stubbed omnictl on PATH."""
    base = tmp_path / "repo"
    base.mkdir()
    (base / ".env").write_text("# stub\n")
    (base / ".env_devops").write_text("# stub\n")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    payload = "\n".join(json.dumps(m) for m in FAKE_MACHINES)
    fixture = tmp_path / "machines.json"
    fixture.write_text(payload)

    stub = bindir / "omnictl"
    stub.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            # Only the status query is used by the render path.
            case "$*" in
              *clustermachinestatuses*) cat {str(fixture)!r} ;;
              *) echo "" ;;
            esac
            """
        )
    )
    stub.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["BASE_REPO"] = str(base)
    return base, env


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq not available")
def test_dry_run_renders_one_patch_per_machine(tmp_path):
    """Exercises the real generation path against a stubbed Omni."""
    _, env = _stub_env(tmp_path)
    result = subprocess.run(
        [str(TOOL_DIR / "force-recovery.sh"), "--dry-run"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"dry-run failed:\n{result.stderr}"

    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    assert len(docs) == len(FAKE_MACHINES), (
        f"rendered {len(docs)} patches for {len(FAKE_MACHINES)} machines"
    )

    ids = sorted(d["metadata"]["id"] for d in docs)
    assert ids == ["999-recovery-test-node-a", "999-recovery-test-node-b"]

    targeted = {d["metadata"]["labels"]["omni.sidero.dev/cluster-machine"] for d in docs}
    assert targeted == {m["metadata"]["id"] for m in FAKE_MACHINES}, (
        "rendered patches do not target exactly the machines Omni reported"
    )


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq not available")
def test_every_written_path_stays_under_var(tmp_path):
    """Guarantee 2. Writing outside /var re-causes the outage being recovered from."""
    _, env = _stub_env(tmp_path)
    result = subprocess.run(
        [str(TOOL_DIR / "force-recovery.sh"), "--dry-run"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    for doc in (d for d in yaml.safe_load_all(result.stdout) if d):
        for entry in yaml.safe_load(doc["spec"]["data"])["machine"]["files"]:
            assert entry["path"].startswith("/var/"), (
                f"recovery marker writes {entry['path']} outside /var — Talos v1.12 "
                "rejects this at boot and the machine stops before etcd"
            )


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq not available")
def test_marker_content_differs_between_runs(tmp_path):
    """Guarantee 1. Identical content = no hash change = Omni resends nothing."""
    _, env = _stub_env(tmp_path)

    def marker_of(stdout: str) -> set:
        return {
            f["content"]
            for d in (x for x in yaml.safe_load_all(stdout) if x)
            for f in yaml.safe_load(d["spec"]["data"])["machine"]["files"]
        }

    first = subprocess.run([str(TOOL_DIR / "force-recovery.sh"), "--dry-run"],
                           env=env, capture_output=True, text=True, timeout=60)
    assert first.returncode == 0, first.stderr
    m1 = marker_of(first.stdout)
    assert len(m1) == 1, f"a single run used {len(m1)} different markers: {m1}"

    # The timestamp has second resolution, so force a distinct second rather
    # than sleeping: patch the clock the script sees via a `date` stub.
    bindir = tmp_path / "bin"
    datestub = bindir / "date"
    datestub.write_text("#!/bin/sh\necho 19700101T000000Z\n")
    datestub.chmod(0o755)

    second = subprocess.run([str(TOOL_DIR / "force-recovery.sh"), "--dry-run"],
                            env=env, capture_output=True, text=True, timeout=60)
    assert second.returncode == 0, second.stderr
    m2 = marker_of(second.stdout)

    assert m1 != m2, (
        "the recovery marker is identical across runs. The config-hash change IS "
        "the mechanism: with identical content Omni sees no divergence and "
        "resends nothing, so the recovery silently does nothing — which looks "
        "exactly like the failure it is meant to fix."
    )


def test_remove_discovers_patches_rather_than_hardcoding(tmp_path):
    """Cleanup must cover a patch created for a machine that did not exist before."""
    body = (TOOL_DIR / "remove-recovery.sh").read_text()
    assert "999-recovery-" in body, "remove-recovery.sh does not scope to recovery patches"
    assert "startswith" in body or "grep" in body, (
        "remove-recovery.sh appears to hardcode patch ids; discover them instead"
    )
