"""Guard: authentik-server's Prometheus multiprocess dir must NOT live in /dev/shm.

The authentik image sets TMPDIR=/dev/shm/ and its entrypoint (/lifecycle/ak)
defaults PROMETHEUS_MULTIPROC_DIR to ${TMPDIR}/authentik_prometheus_tmp unless
the variable is already set. prometheus_client writes one mmap'd .db file per
metric type per gunicorn worker PID, and gunicorn recycles workers every
max_requests=1000 (+jitter), so the directory grows ~1MB/day for the life of
the pod (authentik's worker_id reuse does not cover metrics instantiated in the
master under preload_app). /dev/shm is the pod sandbox's 64M tmpfs, so after
~64 days it fills, the next mmap write faults with SIGBUS, gunicorn can never
start again, and container restarts cannot recover it (the tmpfs belongs to
the sandbox, not the container). That took one authentik-server replica down
on 2026-11-26 with the other at 93% — debug journal:
docs/superpowers/journals/debug/2026-11-26-authentik-shm-sigbus.md.

The fix points PROMETHEUS_MULTIPROC_DIR at a DISK-backed emptyDir with a
sizeLimit: a full disk emptyDir gets the pod evicted (a clean reset) instead
of SIGBUS-looping forever.
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
VALUES = REPO / "apps/authentik/values.yaml"


def _server():
    return yaml.safe_load(VALUES.read_text())["server"]


def _multiproc_dir(server):
    for e in server.get("env") or []:
        if e.get("name") == "PROMETHEUS_MULTIPROC_DIR":
            return e.get("value")
    return None


def test_server_sets_prometheus_multiproc_dir_outside_dev_shm():
    path = _multiproc_dir(_server())
    assert path, "server.env must set PROMETHEUS_MULTIPROC_DIR (image default is /dev/shm)"
    assert not path.startswith("/dev/shm"), path
    assert not path.startswith("/tmp"), path  # also a candidate tmpfs; keep it explicit


def test_multiproc_dir_is_a_disk_backed_emptydir_with_size_limit():
    server = _server()
    path = _multiproc_dir(server)
    mounts = {m["mountPath"]: m["name"] for m in server.get("volumeMounts") or []}
    assert path in mounts, f"{path} must be a volumeMount, not the container layer"
    vols = {v["name"]: v for v in server.get("volumes") or []}
    vol = vols[mounts[path]]
    ed = vol.get("emptyDir")
    assert ed is not None, "must be an emptyDir (per-pod, reset on reschedule)"
    # medium: Memory would recreate the exact tmpfs/SIGBUS failure.
    assert ed.get("medium") in (None, ""), "must be disk-backed, not medium: Memory"
    assert ed.get("sizeLimit"), "sizeLimit turns a full dir into an eviction, not unbounded growth"
