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

# Captured from the live server 2026-09-19, not hand-written: the whole point
# of this signal is that the obvious series is the wrong one, and a fixture
# invented alongside the parser would agree with whatever the parser assumed.
FIXTURES = REPO / "scripts/tests/fixtures/ovms-retrieval"
METRICS_IDLE = FIXTURES / "metrics-idle.txt"
METRICS_BUSY = FIXTURES / "metrics-busy.txt"

GIB = 1024**3
LIMIT = 16 * GIB


def _sum_series(metrics: pathlib.Path, name: str) -> int:
    """Sum one metric across its label sets — the fixture's own arithmetic, so
    a re-capture moves the tests with it instead of stranding a literal."""
    return sum(
        int(float(line.rsplit(" ", 1)[1]))
        for line in metrics.read_text(encoding="utf-8").splitlines()
        # Same anchoring as the script's sum_series: the name plus the character
        # the exposition format guarantees follows it. Mirroring the bug here
        # would make the tests agree with a broken parser.
        if line.startswith(name + "{") or line.startswith(name + " ")
    )


def _activity(metrics: pathlib.Path) -> int:
    return (
        _sum_series(metrics, "ovms_requests_accepted")
        + _sum_series(metrics, "ovms_requests_rejected")
    )


IDLE_ACTIVITY = _activity(METRICS_IDLE)


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
    """64 documents x 600 tokens measured at 3.40 GiB as a single call. If the
    threshold sat above limit-minus-that, the pool could be 'healthy' and the
    very next cap-sized request would still OOM.

    Note the threshold is sized against the ASCENDING case, not this one: Test
    Plan row 10 peaked at 8.49 GiB walking 20 -> 40 -> 64 documents, where the
    same cap as a single call costs 5.67 GiB. That is why CRITICAL_PERCENT is
    not a value derived from the single-call figure alone.

    It reads 53 rather than 50 because the numerator became `memory.current`
    on 2026-09-20; see test_the_numerator_change_did_not_silently_move_the
    _trigger for the offset that accounts for the difference."""
    critical = int(_env()["CRITICAL_PERCENT"]) / 100 * LIMIT
    assert critical + 3.40 * GIB <= LIMIT


def test_the_numerator_change_did_not_silently_move_the_trigger():
    """`CRITICAL_PERCENT` was calibrated against `shmem`. Rule 1 now reads
    `memory.current`, which runs a roughly CONSTANT ~0.5 GiB higher (live
    baseline: shmem 1.72 GiB, anon 0.50, kernel 0.01, current 2.22 — and with
    swap off none of it is reclaimable, which is why the numerator change is
    right). Porting the percentage across unchanged would tighten the trigger
    by ~3.1 points of the limit without anyone deciding to.

    Measured against the incident this whole plan exists to fix: peak
    `shmem` 8313102336 (7.74 GiB) sat under the old 8.00 GiB line, but the same
    moment as `memory.current` is ~8.17 GiB — over it. Rule 1 would have killed
    the batch index that Rule 2 killed, and row 5 of the Test Plan would fail
    for a new reason.

    So the percentage moves with the numerator: the measurement becomes honest,
    the trigger stays where it was actually calibrated."""
    ANON_GAP = 459558912  # measured live: memory.current 2296066048 - shmem 1836507136
    INCIDENT_PEAK_SHMEM = 8313102336  # the 19:40:12 restart's own log line
    critical = LIMIT // 100 * int(_env()["CRITICAL_PERCENT"])

    assert INCIDENT_PEAK_SHMEM + ANON_GAP < critical, (
        "the incident's own peak crosses Rule 1's trigger once read as "
        "memory.current: the consumer's index would be restarted again, by the "
        "other rule"
    )
    # And the other direction — this is a recalibration, not a licence to
    # loosen. The trigger must stay within a quarter-GiB of where the shmem
    # -calibrated line effectively sat.
    assert critical - ANON_GAP <= LIMIT // 100 * 50 + GIB // 4, (
        "raised further than the anon offset justifies — that is a new "
        "threshold, and it needs its own measurement"
    )


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
        '                 echo "$FAKE_SHMEM"; echo "$FAKE_CURRENT"; echo "$FAKE_LIMIT"\n'
        # The same exec scrapes the server's own /metrics, so the pool figure
        # and the activity figure describe one pod at one instant. There is no
        # CPU sample to stub any more, and deliberately so: it was a 10-second
        # cpu.stat delta that read 5 millicores on a server indexing on the
        # iGPU, and leaving the plumbing here would imply a signal that no
        # longer exists.
        '                 cat "$FAKE_METRICS" ;;\n'
        # Two annotations are read through `get deployment`, and they are told
        # apart by the jsonpath. The activity case MUST come first — both
        # patterns contain "get deployment" and `case` takes the first match.
        # Failure injection for the one call whose failure would otherwise be
        # invisible: the idle-clock stamp inside restart(). `set -e` means a
        # non-zero kubectl there aborts the script, so anything AFTER it in
        # restart() never runs.
        '  *"annotate"*"pool-watchdog-last-busy"*)\n'
        '                 [ -z "${FAKE_ANNOTATE_FAILS:-}" ] || exit 1 ;;\n'
        '  *"pool-watchdog-last-activity"*) echo "$FAKE_LAST_ACTIVITY" ;;\n'
        '  *"get deployment"*) echo "$FAKE_LAST_BUSY" ;;\n'
        '  *) : ;;\n'
        'esac\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)

    def _run(**overrides):
        calls.write_text("", encoding="utf-8")
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env.update({k: str(v) for k, v in _env().items()})
        env.setdefault("FAKE_POD", "ovms-retrieval-abc")
        env.setdefault("FAKE_METRICS", str(METRICS_IDLE))
        # The idle fixture's counters sum to IDLE_ACTIVITY, so a stamp of the
        # same value is the "nothing has happened since the last tick" default.
        env.setdefault("FAKE_LAST_ACTIVITY", str(IDLE_ACTIVITY))
        env.update({k: str(v) for k, v in overrides.items()})
        # memory.current defaults to the same value as shmem when a test does
        # not care about the distinction — this is what every pre-phase-3 test
        # implicitly assumed (Rule 1 used to compare shmem itself), so it
        # keeps every existing scenario's Rule 1 outcome unchanged.
        env.setdefault("FAKE_CURRENT", env.get("FAKE_SHMEM", ""))
        proc = subprocess.run(
            ["bash", "-euo", "pipefail", str(script)],
            capture_output=True, text=True, env=env, timeout=60,
        )
        return proc, calls.read_text(encoding="utf-8")

    return _run


def test_the_script_reads_the_servers_own_metrics(run_script):
    """The activity signal comes from OVMS, not from the cgroup's CPU.

    `metrics-busy.txt` was captured with one `/v3/embeddings` request in flight
    (`ovms_current_graphs{name="bge-m3"} 1`). If the tick cannot report that,
    it is deciding on something other than what the server is doing."""
    proc, _ = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=1, FAKE_METRICS=METRICS_BUSY,
    )
    assert "in_flight=1" in proc.stdout, proc.stdout


def test_a_gpu_busy_server_with_a_stale_idle_clock_is_not_restarted(run_script):
    """The 2026-09-19 incident, replayed from its own log line:

        19:36:12 action=restart reason=idle-with-elevated-pool
                 shmem=5104066560 millicores=5

    OpenVINO offloads inference to the iGPU, so a working server's container
    CPU is near zero by construction — 5 millicores against a 50 millicore
    threshold — while `shmem` climbed 5.10 -> 7.24 -> 8.31 GiB across those
    very ticks. The server was serving; the CPU sampler called it asleep and
    the watchdog killed a batch-index job at batch 7 of 40."""
    import time
    proc, calls = run_script(
        FAKE_SHMEM=5104066560, FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=int(time.time()) - 3600,
        FAKE_METRICS=METRICS_BUSY,
    )
    assert "rollout restart" not in calls, proc.stdout
    assert "reason=busy" in proc.stdout, proc.stdout


def test_work_since_the_last_tick_counts_as_busy(run_script):
    """Nothing is in flight at the instant the watchdog looks, but requests
    have arrived since the last tick — the gaps BETWEEN a batch job's batches,
    which is exactly what a 10-second CPU window could never see. The counter
    delta covers the whole two-minute interval; the gauge only covers the two
    instants sampled."""
    import time
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=int(time.time()) - 3600,
        FAKE_METRICS=METRICS_IDLE,
        FAKE_LAST_ACTIVITY=IDLE_ACTIVITY - 1,
    )
    assert "rollout restart" not in calls, proc.stdout
    assert "reason=busy" in proc.stdout, proc.stdout


def _with_probe_traffic_only(dest: pathlib.Path, hits: int = 3) -> pathlib.Path:
    """The idle fixture, advanced by `hits` readiness probes and nothing else.

    Measured 2026-09-19: over 12 idle seconds the ONLY series that moved was
    `ovms_requests_success{...,method="ModelReady",name="bge-reranker-v2-m3"}`,
    because `readinessProbe` hits `/v2/models/bge-reranker-v2-m3/ready` every
    10s (`deployment.yaml:364`). Every other byte is left alone, so anything
    this file makes the watchdog do, the probe alone did."""
    out, bumped = [], 0
    for line in METRICS_IDLE.read_text(encoding="utf-8").splitlines(keepends=True):
        if line.startswith("ovms_requests_success{") and 'method="ModelReady"' in line:
            labels, _, value = line.rstrip("\n").rpartition(" ")
            out.append(f"{labels} {int(float(value)) + hits}\n")
            bumped += 1
        else:
            out.append(line)
    assert bumped, "the fixture no longer carries a ModelReady success series"
    dest.write_text("".join(out), encoding="utf-8")
    return dest


def test_a_suffixed_metric_name_is_not_counted_as_activity(run_script, tmp_path):
    """`ovms_requests_accepted` must match that series and not one whose name
    merely STARTS with it.

    This is not hypothetical: the same endpoint already ships
    `ovms_graph_processing_time_us_bucket` / `_count` / `_sum`, so suffixing a
    base name is OVMS's established habit. A prefix match would silently fold a
    future `ovms_requests_accepted_total` into the activity sum — and the
    failure would be a permanently-busy watchdog, which is the quiet direction:
    Rule 2 stops reclaiming and nothing reports it until the ceiling."""
    poisoned = tmp_path / "suffixed.txt"
    poisoned.write_text(
        METRICS_IDLE.read_text(encoding="utf-8")
        + 'ovms_requests_accepted_total{api="V3",name="bge-m3"} 100000\n',
        encoding="utf-8",
    )
    import time
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=int(time.time()) - 3600,
        FAKE_METRICS=poisoned,
        FAKE_LAST_ACTIVITY=IDLE_ACTIVITY,
    )
    assert f"activity={IDLE_ACTIVITY}" in proc.stdout, proc.stdout
    assert "rollout restart" in calls, (
        "an unrelated suffixed series made an idle server look busy: " + proc.stdout
    )


def test_readiness_probe_traffic_alone_does_not_read_as_busy(run_script, tmp_path):
    """The failure this design came closest to shipping, in the opposite
    direction to the one it fixes.

    A first draft chose `ovms_requests_success` as the activity counter, on the
    strength of this repo's own gotchas file. That series counts the readiness
    probe and never moves on `/v3` inference — so `busy` would have read yes on
    every tick forever, Rule 2 would be silently dead, the pool never
    reclaimed, and there would be no symptom until the ceiling. Loud bug traded
    for a quiet one.

    A server that only its own kubelet is talking to is idle, and an elevated
    pool on it is exactly what the hygiene rule exists to reclaim."""
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_METRICS=_with_probe_traffic_only(tmp_path / "metrics-probe-only.txt"),
        FAKE_LAST_ACTIVITY=IDLE_ACTIVITY,
        FAKE_LAST_BUSY=1,  # epoch 1: idle for decades
    )
    assert "reason=busy" not in proc.stdout, proc.stdout
    assert "action=restart" in proc.stdout and "idle-with-elevated-pool" in proc.stdout
    assert "rollout restart" in calls


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
    proc, calls = run_script(
        FAKE_SHMEM=int(5 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_METRICS=METRICS_BUSY,
    )
    assert "reason=busy" in proc.stdout
    assert "rollout restart" not in calls
    assert "annotate" in calls, "a busy tick must stamp the last-busy clock"


def test_restarts_a_busy_server_once_the_pool_is_critical(run_script):
    """Deliberate: past this point the next cap-sized request takes the process
    down anyway, and an OOM costs the in-flight request plus ~10s of refused
    connections. A controlled 11s restart is strictly cheaper."""
    proc, calls = run_script(
        FAKE_SHMEM=int(0.95 * LIMIT), FAKE_LIMIT=LIMIT,
    )
    assert "action=restart" in proc.stdout and "critical-pool" in proc.stdout
    assert "rollout restart" in calls


def test_rule_one_triggers_on_memory_current_not_shmem(run_script):
    """The kernel's OOM killer compares `memory.current` against
    `memory.max`, not `shmem`. Measured live at baseline: shmem 1836507136,
    memory.current 2296066048 -- a ~25% gap, very likely the "68% with no
    watchdog action" #813 files as unexplained. `shmem` sits below the 50%
    line here; `memory.current` sits above it."""
    proc, calls = run_script(
        FAKE_SHMEM=int(1.71 * GIB), FAKE_CURRENT=int(0.6 * LIMIT),
        FAKE_LIMIT=LIMIT, FAKE_LAST_BUSY=1,
    )
    assert "action=restart" in proc.stdout and "critical-pool" in proc.stdout, proc.stdout
    assert "rollout restart" in calls


def test_the_elevated_pool_is_still_measured_on_shmem(run_script):
    """Rule 2 asks a different question than Rule 1: is the GPU POOL above its
    post-boot baseline. `memory.current` running above `ELEVATED_BYTES` while
    the pool itself (`shmem`) sits at baseline is nothing to reclaim -- Rule 2
    must keep reading `shmem`, not the numerator Rule 1 now reads."""
    proc, calls = run_script(
        FAKE_SHMEM=int(1.71 * GIB), FAKE_CURRENT=int(3 * GIB),
        FAKE_LIMIT=LIMIT, FAKE_LAST_BUSY=1,  # idle for decades
    )
    assert "rollout restart" not in calls, proc.stdout
    assert "pool-at-baseline" in proc.stdout, proc.stdout


def test_does_nothing_when_the_pool_is_at_baseline(run_script):
    proc, calls = run_script(
        FAKE_SHMEM=int(1.71 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=1,
    )
    assert "pool-at-baseline" in proc.stdout
    assert "rollout restart" not in calls


def test_restarts_when_idle_long_enough_with_an_elevated_pool(run_script):
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=1,  # epoch 1: idle for decades
    )
    assert "action=restart" in proc.stdout and "idle-with-elevated-pool" in proc.stdout
    assert "rollout restart" in calls


def test_does_not_restart_when_idleness_is_recent(run_script):
    """The case that would make every caller pay a cold start."""
    import time
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=int(time.time()) - 60,
    )
    assert "idle-too-recent" in proc.stdout
    assert "rollout restart" not in calls


def test_an_unlimited_cgroup_does_not_divide_by_a_word(run_script):
    """`memory.max` reads the literal string `max` when unlimited."""
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT="max",
        FAKE_LAST_BUSY=1,
    )
    assert proc.returncode == 0, proc.stderr
    assert "action=restart" in proc.stdout


def test_a_restart_stamps_the_idle_clock(run_script):
    """2026-09-19 replayed: the last-busy clock lives on the Deployment and
    `rollout restart` never touches it, so once a restart fires the clock is
    still exactly as stale as it was before the restart — the next tick sees
    the same `idle_for` and restarts again. Four restarts in six minutes, one
    per tick, until the caller gave up.

    A restart must stamp `pool-watchdog-last-busy=$now` itself: the annotation
    means "how long since the server was last known to be doing something",
    and a restart destroys the process that observation was about."""
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=1,  # epoch 1: idle for decades
    )
    assert "action=restart" in proc.stdout and "idle-with-elevated-pool" in proc.stdout
    lines = calls.splitlines()
    restart_idx = next(i for i, line in enumerate(lines) if "rollout restart" in line)
    assert any(
        "pool-watchdog-last-busy=" in line
        for line in lines[restart_idx:]
    ), (
        "a restart must stamp the idle clock alongside the rollout restart: "
        + calls
    )


def test_a_second_consecutive_tick_does_not_restart_again(run_script):
    """The regression shape for the actual incident: one restart is a
    decision, five is a machine. A tick immediately following a restart must
    see a freshly-stamped clock and do nothing."""
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=1,
    )
    assert "action=restart" in proc.stdout and "idle-with-elevated-pool" in proc.stdout

    now = int(__import__("time").time())
    proc2, calls2 = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=now,
    )
    assert "rollout restart" not in calls2, proc2.stdout
    assert "idle-too-recent" in proc2.stdout, proc2.stdout


def test_a_restart_is_logged_even_if_stamping_the_clock_fails(run_script):
    """The result line is the ONLY record that a restart happened.

    `restart()` does three things under `set -e`: roll the Deployment, stamp
    the idle clock, print the result line. If the stamp fails — a transient API
    error is enough — the script aborts before the print, and a restart that
    really did happen leaves no trace: not in the log, and therefore not in the
    `action=restart` alert that phase 4 builds on top of it.

    So the print comes first. A failed stamp still aborts the tick non-zero,
    which is right (the Job fails visibly and the stale clock is not silently
    accepted), but it can no longer swallow the evidence."""
    import time
    proc, calls = run_script(
        FAKE_SHMEM=int(6.2 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=int(time.time()) - 7200,
        FAKE_ANNOTATE_FAILS="1",
    )
    assert "rollout restart" in calls, calls
    assert "action=restart" in proc.stdout, (
        "the restart happened but was never logged: " + repr(proc.stdout)
    )


def test_a_counter_reset_reads_as_busy_not_idle(run_script):
    """A restarted pod serves `activity` from zero, since OVMS counters start
    fresh on every process — that is a counter reset, not idleness. Without
    detecting it, the first requests after every restart would read as idle,
    reintroducing root cause A through the back door."""
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=int(__import__("time").time()) - 3600,
        FAKE_METRICS=METRICS_IDLE,
        FAKE_LAST_ACTIVITY=IDLE_ACTIVITY + 1000,
    )
    assert "reason=busy" in proc.stdout, proc.stdout
    assert "rollout restart" not in calls, proc.stdout
    assert "annotate" in calls, "a busy tick (via counter reset) must stamp the last-busy clock"


def test_unreadable_metrics_take_no_hygiene_action(run_script):
    """The cgroup read can succeed while the curl portion of the same exec
    fails — the scrape can fail without the exec failing. When that happens
    the tick must not silently treat the missing metrics as zero activity (the
    quiet way root cause A came back): it must refuse to take hygiene action
    and say so."""
    proc, calls = run_script(
        FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT,
        FAKE_LAST_BUSY=1,  # idle clock stale
        FAKE_METRICS="",
    )
    assert "reason=metrics-unreadable" in proc.stdout, proc.stdout
    assert "rollout restart" not in calls, proc.stdout


def test_rule_one_still_fires_when_metrics_are_unreadable(run_script):
    """Rule 1 does not consult `busy`, so unreadable metrics must not disarm
    it — the cost of failing toward busy is an unreclaimed pool, not a missed
    OOM-avoiding restart."""
    proc, calls = run_script(
        FAKE_SHMEM=int(0.95 * LIMIT), FAKE_LIMIT=LIMIT,
        FAKE_METRICS="",
    )
    assert "action=restart" in proc.stdout and "critical-pool" in proc.stdout, proc.stdout
    assert "rollout restart" in calls


def test_every_exit_path_emits_a_greppable_result_line(run_script):
    """The GC CronJob in this repo learned this the hard way: a silent job is
    indistinguishable from one that never ran."""
    import time
    scenarios = [
        dict(FAKE_POD=""),
        dict(FAKE_SHMEM=""),
        dict(FAKE_SHMEM=int(1.71 * GIB), FAKE_LIMIT=LIMIT, FAKE_LAST_BUSY=1),
        dict(FAKE_SHMEM=int(4.18 * GIB), FAKE_LIMIT=LIMIT, FAKE_LAST_BUSY=int(time.time())),
        dict(FAKE_SHMEM=int(9.9 * GIB), FAKE_LIMIT=LIMIT, FAKE_LAST_BUSY=1),
    ]
    for kw in scenarios:
        proc, _ = run_script(**kw)
        assert "pool-watchdog result:" in proc.stdout, f"silent exit for {kw}"
