"""Tests for the iGPU buffer-pool watchdog.

Contract source of truth:
docs/superpowers/specs/2026-09-11--infer--ovms-rerank-batch-guard-design.md

The Intel iGPU has no VRAM, so OpenVINO's GPU buffers are shmem-backed host
pages, PINNED UNEVICTABLE in the ovms container's cgroup (measured live:
`shmem` and `unevictable` identical at 5.11 GiB, `inactive_file` and
`active_file` both zero, swap disabled). `limits.memory` is therefore the GPU
memory budget, and nothing is ever released while the container lives. The
graph-level cap bounds what ONE request may allocate; only a restart returns
the pool to baseline. This watchdog is that restart.

## Why the behaviour is tested and not just the shape

This job restarts a production Deployment on a timer. A manifest-shape test
would confirm it exists while saying nothing about *when* it fires, and the
expensive failure modes here are both behavioural: restarting while the server
is working, and restarting so eagerly that a caller sending one request every
few minutes pays an 11s cold start every time. So the inline script is
extracted and run against a stubbed `kubectl`, once per decision branch.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = REPO / "apps/ovms-retrieval/manifests/pool-watchdog.yaml"

GIB = 1024**3
LIMIT = 10 * GIB


def _docs() -> list[dict]:
    return [d for d in yaml.safe_load_all(MANIFEST.read_text(encoding="utf-8")) if d]


def _by_kind(kind: str) -> dict:
    found = [d for d in _docs() if d["kind"] == kind]
    assert len(found) == 1, f"expected exactly one {kind}, found {len(found)}"
    return found[0]


def _container() -> dict:
    return _by_kind("CronJob")["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]


def _env() -> dict[str, str]:
    return {e["name"]: e["value"] for e in _container()["env"]}


def _script() -> str:
    return _container()["args"][0]


# --- shape ----------------------------------------------------------------

def test_manifest_carries_its_own_rbac():
    """A CronJob that can restart a Deployment should say so in the repo, not
    borrow a broader ServiceAccount from elsewhere in the namespace."""
    for kind in ("ServiceAccount", "Role", "RoleBinding", "CronJob"):
        _by_kind(kind)


def test_rbac_cannot_delete_anything():
    """`delete` on pods would let this bypass the Recreate strategy that the
    RWO model PVC requires — deleting the pod directly races the replacement
    against a volume that can only be mounted once."""
    rules = _by_kind("Role")["rules"]
    for rule in rules:
        assert "delete" not in rule["verbs"], f"delete granted on {rule['resources']}"
    granted = {(r["apiGroups"][0], res) for r in rules for res in r["resources"]}
    assert ("apps", "deployments") in granted
    assert ("", "pods/exec") in granted, (
        "the pool is read from the container's own cgroup; without exec this "
        "would have to trust a scraped metric instead"
    )


def test_cronjob_forbids_overlapping_runs():
    cj = _by_kind("CronJob")["spec"]
    assert cj["concurrencyPolicy"] == "Forbid", (
        "two watchdogs sampling and restarting at once could restart a pod "
        "that the other is still measuring"
    )
    assert cj["schedule"]


def test_image_is_version_pinned():
    image = _container()["image"]
    assert ":" in image and not image.endswith(":latest")


def test_runs_unprivileged():
    pod = _by_kind("CronJob")["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert _container()["securityContext"]["capabilities"]["drop"] == ["ALL"]


def test_registered_in_the_kustomization():
    kust = yaml.safe_load((REPO / "apps/ovms-retrieval/manifests/kustomization.yaml").read_text())
    assert "pool-watchdog.yaml" in kust["resources"]


def test_no_generator_was_introduced():
    """The app is deliberately generator-free so its Application can stay
    `prune: false` and the 20Gi model cache is never one mis-sync from
    deletion. The watchdog script is inline for the same reason the seed
    script is."""
    kust = yaml.safe_load((REPO / "apps/ovms-retrieval/manifests/kustomization.yaml").read_text())
    assert "configMapGenerator" not in kust
    assert _script().strip(), "the script must be inline, not mounted"


def test_thresholds_are_present_and_ordered():
    env = _env()
    assert int(env["ELEVATED_BYTES"]) > 1.71 * GIB, (
        "must sit above the post-boot baseline of 1.71 GiB of model weights, "
        "or every tick would see an 'elevated' pool with nothing to reclaim"
    )
    assert int(env["ELEVATED_BYTES"]) < int(env["CRITICAL_PERCENT"]) / 100 * LIMIT
    assert int(env["IDLE_SECONDS"]) >= 600, (
        "too short and a caller sending a request every few minutes pays an "
        "11s cold start each time"
    )


def test_critical_threshold_leaves_room_for_one_cap_sized_request():
    """64 documents x 600 tokens measured at 3.40 GiB. If the threshold sat
    above limit-minus-that, the pool could be 'healthy' and the very next
    cap-sized request would still OOM."""
    critical = int(_env()["CRITICAL_PERCENT"]) / 100 * LIMIT
    assert critical + 3.40 * GIB <= LIMIT


# --- behaviour ------------------------------------------------------------

@pytest.fixture
def run_script(tmp_path):
    """Run the inline script with a stubbed `kubectl`, and report what it did."""
    script = tmp_path / "watchdog.sh"
    script.write_text(_script(), encoding="utf-8")
    calls = tmp_path / "calls.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "kubectl"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{calls}"\n'
        'case "$*" in\n'
        '  *"get pods"*)  echo "$FAKE_POD" ;;\n'
        '  *"exec"*)      [ -n "$FAKE_SHMEM" ] || exit 1\n'
        '                 echo "$FAKE_SHMEM"; echo "$FAKE_LIMIT"\n'
        # The script reads cpu.stat twice and derives millicores from the
        # delta, so the stub MUST answer differently on the second exec or the
        # busy branch is unreachable and every test silently exercises "idle".
        f'                 if [ -e "{tmp_path}/seen" ]; then echo "$FAKE_CPU2"; '
        f'else touch "{tmp_path}/seen"; echo "$FAKE_CPU1"; fi ;;\n'
        '  *"get deployment"*) echo "$FAKE_LAST_BUSY" ;;\n'
        '  *) : ;;\n'
        'esac\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)

    def _run(**overrides):
        calls.write_text("", encoding="utf-8")
        (tmp_path / "seen").unlink(missing_ok=True)
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env.update({k: str(v) for k, v in _env().items()})
        env.setdefault("FAKE_POD", "ovms-retrieval-abc")
        env["SAMPLE_SECONDS"] = "1"
        env.update({k: str(v) for k, v in overrides.items()})
        proc = subprocess.run(
            ["bash", "-euo", "pipefail", str(script)],
            capture_output=True, text=True, env=env, timeout=60,
        )
        return proc, calls.read_text(encoding="utf-8")

    return _run


def _busy_cpu(millicores: int, seconds: int = 1) -> tuple[int, int]:
    """cpu.stat usage_usec pair producing the given millicores over `seconds`."""
    return 0, millicores * 1000 * seconds


def test_does_nothing_when_no_pod_is_running(run_script):
    proc, calls = run_script(FAKE_POD="")
    assert "action=none" in proc.stdout and "no-running-pod" in proc.stdout
    assert "rollout restart" not in calls


def test_does_nothing_when_the_cgroup_cannot_be_read(run_script):
    """A pod mid-restart is not a reason to restart it again."""
    proc, calls = run_script(FAKE_SHMEM="")
    assert "unreadable-cgroup" in proc.stdout
    assert "rollout restart" not in calls


def test_never_restarts_a_busy_server_below_critical(run_script):
    lo, hi = _busy_cpu(900)
    proc, calls = run_script(
        FAKE_SHMEM=int(5 * GIB), FAKE_LIMIT=LIMIT, FAKE_CPU1=lo, FAKE_CPU2=hi,
    )
    assert "reason=busy" in proc.stdout
    assert "rollout restart" not in calls
    assert "annotate" in calls, "a busy tick must stamp the last-busy clock"


def test_restarts_a_busy_server_once_the_pool_is_critical(run_script):
    """Deliberate: past this point the next cap-sized request takes the process
    down anyway, and an OOM costs the in-flight request plus ~10s of refused
    connections. A controlled 11s restart is strictly cheaper."""
    lo, hi = _busy_cpu(900)
    proc, calls = run_script(
        FAKE_SHMEM=int(0.95 * LIMIT), FAKE_LIMIT=LIMIT, FAKE_CPU1=lo, FAKE_CPU2=hi,
    )
    assert "action=restart" in proc.stdout and "critical-pool" in proc.stdout
    assert "rollout restart" in calls


def test_does_nothing_when_the_pool_is_at_baseline(run_script):
    lo, hi = _busy_cpu(0)
    proc, calls = run_script(
        FAKE_SHMEM=int(1.71 * GIB), FAKE_LIMIT=LIMIT, FAKE_CPU1=lo, FAKE_CPU2=hi,
        FAKE_LAST_BUSY=1,
    )
    assert "pool-at-baseline" in proc.stdout
    assert "rollout restart" not in calls


def test_restarts_when_idle_long_enough_with_an_elevated_pool(run_script):
    lo, hi = _busy_cpu(0)
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT, FAKE_CPU1=lo, FAKE_CPU2=hi,
        FAKE_LAST_BUSY=1,  # epoch 1: idle for decades
    )
    assert "action=restart" in proc.stdout and "idle-with-elevated-pool" in proc.stdout
    assert "rollout restart" in calls


def test_does_not_restart_when_idleness_is_recent(run_script):
    """The case that would make every caller pay a cold start."""
    import time
    lo, hi = _busy_cpu(0)
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT, FAKE_CPU1=lo, FAKE_CPU2=hi,
        FAKE_LAST_BUSY=int(time.time()) - 60,
    )
    assert "idle-too-recent" in proc.stdout
    assert "rollout restart" not in calls


def test_an_unlimited_cgroup_does_not_divide_by_a_word(run_script):
    """`memory.max` reads the literal string `max` when unlimited."""
    lo, hi = _busy_cpu(0)
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT="max", FAKE_CPU1=lo, FAKE_CPU2=hi,
        FAKE_LAST_BUSY=1,
    )
    assert proc.returncode == 0, proc.stderr
    assert "action=restart" in proc.stdout


def test_every_exit_path_emits_a_greppable_result_line(run_script):
    """The GC CronJob in this repo learned this the hard way: a silent job is
    indistinguishable from one that never ran."""
    import time
    scenarios = [
        dict(FAKE_POD=""),
        dict(FAKE_SHMEM=""),
        dict(FAKE_SHMEM=int(1.71 * GIB), FAKE_LIMIT=LIMIT, FAKE_CPU1=0, FAKE_CPU2=0, FAKE_LAST_BUSY=1),
        dict(FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT, FAKE_CPU1=0, FAKE_CPU2=0, FAKE_LAST_BUSY=int(time.time())),
        dict(FAKE_SHMEM=int(9.9 * GIB), FAKE_LIMIT=LIMIT, FAKE_CPU1=0, FAKE_CPU2=0, FAKE_LAST_BUSY=1),
    ]
    for kw in scenarios:
        proc, _ = run_script(**kw)
        assert "pool-watchdog result:" in proc.stdout, f"silent exit for {kw}"
