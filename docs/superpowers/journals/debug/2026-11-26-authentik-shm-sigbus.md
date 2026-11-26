<!-- fr:journal-schema=4 -->
# Journal: 2026-11-26-authentik-shm-sigbus

<!-- fr:journal kind=repro scope=debug id=38af1b7b05e6 created=2026-11-26T08:33:28+00:00 -->
### 38af1b7b05e6 · repro · authentik-server crashloops with gunicorn SIGBUS; /dev/shm 64M/64M

layer-13-auth-down fired 2026-11-26 ~08:00Z: deploy/authentik-server 1/2. Pod 797dd89f79-frjq9 (mini-2, 64d old) looped bootstrap -> 'applying django migrations' -> 'gunicorn process died, signal: bus error' every ~0.5s; startup probe 502. df /dev/shm = 64M/64M, all of it /dev/shm/authentik_prometheus_tmp (~10k files). Healthy sibling 62shr (mini-1) at 60M/64M (93%), 2152 PIDs x {counter,gauge_all,histogram}_<pid>.db. Worker deployment 1.3M. Mitigated by deleting both pods (fresh sandbox shm).

<!-- fr:journal kind=ruled-out scope=debug id=57fe2108b07b created=2026-11-26T08:33:31+00:00 -->
### 57fe2108b07b · ruled-out · Container restart does not clear it

/dev/shm is the pod sandbox's tmpfs (containerd default 64M), so it survives container restarts; liveness/startup kills cannot recover the pod and each failed start mints new PIDs, making the leak self-reinforcing. Only a pod delete resets it.

<!-- fr:journal kind=ruled-out scope=debug id=fe694c4b66d7 created=2026-11-26T08:33:34+00:00 -->
### fe694c4b66d7 · ruled-out · authentik's worker_id reuse does not bound the files

/lifecycle/gunicorn.conf.py post_fork sets prometheus ValueClass keyed by worker._worker_id and worker_exit calls mark_process_dead(worker_id). But on a 2-min-old pod the files are counter_51/52 = the gunicorn worker PIDs from 'Booting worker with pid: 51/52': with preload_app=True the metrics are instantiated in the master before post_fork, so they keep the PID-keyed identifier. mark_process_dead only removes gauge_live files anyway. max_requests=1000(+jitter 50) recycles workers, each recycle leaks 3 files (~9.5KB).
