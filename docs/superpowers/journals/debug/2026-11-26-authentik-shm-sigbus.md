<!-- fr:journal-schema=4 -->
# Journal: 2026-11-26-authentik-shm-sigbus

<!-- fr:journal kind=repro scope=debug id=38af1b7b05e6 created=2026-11-26T08:33:28+00:00 -->
### 38af1b7b05e6 · repro · authentik-server crashloops with gunicorn SIGBUS; /dev/shm 64M/64M

layer-13-auth-down fired 2026-11-26 ~08:00Z: deploy/authentik-server 1/2. Pod 797dd89f79-frjq9 (mini-2, 64d old) looped bootstrap -> 'applying django migrations' -> 'gunicorn process died, signal: bus error' every ~0.5s; startup probe 502. df /dev/shm = 64M/64M, all of it /dev/shm/authentik_prometheus_tmp (~10k files). Healthy sibling 62shr (mini-1) at 60M/64M (93%), 2152 PIDs x {counter,gauge_all,histogram}_<pid>.db. Worker deployment 1.3M. Mitigated by deleting both pods (fresh sandbox shm).
