# CrowdSec agent goes blind on Kubernetes log rotation (Hop)

**Date:** 2026-06-21
**Layer:** obs / edge security (Hop CrowdSec)
**Fix branch:** `fix/crowdsec-log-rotation-blind`

## Symptom & reproduction

The Hop CrowdSec agent (`crowdsec-agent-pxtr7`) stopped producing bans at
**2026-06-20T11:37Z**; last successful ban **09:55Z** the same day. Azure scan
IPs kept hitting Caddy and getting 404s, but CrowdSec never saw the requests.
The agent pod stayed `Running 1/1`, 0 restarts, and ArgoCD stayed green — a
**silent** blindness lasting ~19h until reported via the alert-agent.

Reproduction is structural, not interactive: any size-based kubelet rotation of
the Caddy container log reproduces it while inotify tailing is in effect.

## Evidence

Agent log, in order:

```
14:34:01 warning  File /var/log/containers/caddy-..._caddy-system_...log is a
                  symlink, but inotify polling is enabled. Crowdsec will not be
                  able to detect rotation. Consider setting poll_without_inotify
                  to true in your configuration
14:34:01 info     Starting tail (offset: 0, whence: 2) file=.../caddy-...log
...
11:37:22 info     Re-opening moved/deleted file /var/log/containers/caddy-...log ...
11:37:22 info     Waiting for /var/log/containers/caddy-...log to appear...
   (no parsed events after this point)
```

- **The Caddy pod never restarted** — `caddy-6cc4c6bdc4-4xbfk`, 27d uptime, 0
  restarts. So this was NOT "new pod → new symlink"; it was a **size-based
  kubelet rotation** (`containerLogMaxSize`) of the *same* container's log.
- `cscli metrics`: the single source shows `Lines read 10.67k / parsed 10.61k`
  — cumulative since the 06-19 14:34 start and **frozen** since 11:37. Parsers
  and scenarios all work (caddy-logs, cri-logs, http-* all parsing) — the
  tailer is simply stuck.
- Live acquisition config (`/etc/crowdsec/acquis.yaml`):
  `force_inotify: true`, `poll_without_inotify: false`.
- Chart template `templates/acquis-configmap.yaml` (crowdsec 0.24.0):
  - line 14: `force_inotify: true` — **hardcoded, not overridable**
  - line 15: `poll_without_inotify: {{ .poll_without_inotify | default "false" }}`
    — **per-acquisition overridable**

## Root cause

CrowdSec tails `/var/log/containers/caddy-*_caddy-system_*.log`, which are
**symlinks** to the kubelet's per-container log (`/var/log/pods/.../0.log`).
The chart hardcodes `force_inotify: true` and defaults `poll_without_inotify:
false`, so the per-file tailer follows the resolved inode via **inotify**. When
the kubelet rotates that underlying log by **size** (renaming `0.log` →
`0.log.<ts>` and opening a fresh `0.log`, **without** a pod restart), the
inotify tailer cannot follow the rotation: it logs "Re-opening moved/deleted
file" then hangs forever in "Waiting for … to appear", parsing zero lines. The
glob does not help because the symlink *name* never changes — there is no new
file for the directory watcher to discover.

Stated as X-because-Y: **the agent went blind because it tails a rotating
symlinked container log with inotify, which cannot re-attach across a kubelet
size-rotation.** The agent printed the exact remedy at startup.

## Fix

Add `poll_without_inotify: true` to the `agent.acquisition[]` entry in
`clusters/hop/apps/crowdsec/values.yaml`. This is the only chart-overridable
lever (`force_inotify` is hardcoded but orthogonal — it governs directory-watch
for *new* files, not the per-file tailer). Polling is stat-based, detects
rotation/truncation, and re-attaches to the fresh inode.

Verified by rendering the chart with the updated values — the configmap now
emits `poll_without_inotify: true`. Deploying it (ArgoCD sync → configmap change
→ DaemonSet rollout) restarts the agent, which resumes tailing.

Pinned by a failing-first guard: `scripts/tests/test_crowdsec_log_rotation_poll.py`
asserts every acquisition entry sets `poll_without_inotify: true` (RED before
the fix, GREEN after; existing `test_crowdsec_cri_logs.py` /
`test_crowdsec_lapi_persistence.py` still pass).

## Rejected / separate

- **"New pod created a new symlink the agent polls for."** Ruled out: the Caddy
  pod has 27d uptime / 0 restarts. The trigger was a size-rotation of the same
  container's log, not a pod churn.
- **Heartbeat / "attempt 1 out of 2" / `connection refused` to
  `crowdsec-service:8080`.** Transient fallout of the LAPI pod restart (LAPI
  AGE 11h, from the 06-19 persistence work) — self-healing and NOT the
  blindness cause. The acquisition hang is independent of LAPI reachability.

## Follow-up (out of scope for this PR)

This is the third CrowdSec wrinkle in the 06-19→06-21 window (emptyDir→hostPath
persistence #583, docker→containerd runtime, now inotify→poll). Each was a
*silent* failure (agent Running, ArgoCD green, zero bans). Worth a standing
end-to-end ban-pipeline canary so the next silent break pages instead of
waiting for a human to notice the bans stopped.
