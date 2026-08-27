# Journal: 2026-08-27-alert-agent-oom-overload

<!-- fr:journal kind=repro scope=debug id=55baf647fe4a created=2026-08-27T17:04:15 -->
### 55baf647fe4a · repro · agent container pinned at memory.max; OOMKilled mid-investigation

Symptom: pod 'overloaded' before operator credential re-login. Measured: agent container memory.current 8,589,840,384 of memory.max 8,589,934,592 (94KB headroom); memory.events max=2,352,495 reclaim-limit hits, oom_kill=0 — a reclaim storm, every allocation stalling processes in D-state (an operator 'claude' launched 13:31Z sat in Dl+ state). RSS holders: tmux session alert-agent-surge (claude --resume, since Aug 15) 4.35GB; alert-agent-digest (since Aug 16) 3.9GB; alert-agent-tg-2034763022 (since Aug 19) 450MB. At 14:00:26Z the */15 surge-gate cron wake allocated into the zero-headroom cgroup and the kernel group-OOM-killed the container (exit 137, OOMKilled, restarts 0->1). Post-restart memory.current: 602MB.

<!-- fr:journal kind=hypothesis scope=debug id=5fd899e9e66e created=2026-08-27T17:04:16 -->
### 5fd899e9e66e · hypothesis · Growth source: Claude Code native auto-updater running inside the pod

~/.local/share/claude/versions/ shows five binaries downloaded IN-POD: 2.1.231 (Aug 13 08:51), 2.1.232 (Aug 13 23:30), 2.1.233 (Aug 14 22:30), 2.1.236 (Aug 19 21:04), 2.1.247 (Aug 27 14:01 — began within a minute of the post-OOM container restart). The auto-updater is the documented memory bomb (agent-shells gotcha: buffers the ~245-335MB download ~17x in anon memory, ~4.2GiB peak) — and the two bloated sessions sat at 4.35GB and 3.9GB, matching that peak, not the ~400MB/session budget from the frank#599 per-stream design. The 8Gi limit was sized for ~400MB sessions; two updater-inflated processes alone consume it.

<!-- fr:journal kind=finding scope=debug id=9ed6c8023bad created=2026-08-27T17:04:18 state=open -->
### 9ed6c8023bad · finding [open] · All three claude sessions wedged on the 'Set up auto mode' onboarding dialog

tmux capture-pane on all three sessions (pre-OOM) showed the interactive 'Set up auto mode for your environment?' first-run wizard blocking each pane — turn injection dead regardless of the (separately) blank OAuth token. The tg session even had an operator DM ('what's in /run/service?') queued behind the dialog. This dialog ships with the newer Claude Code the auto-updater pulled; it will REAPPEAR on fresh launches after the OOM restart unless suppressed via config/flag. Second, independent C&C killer alongside the blank refresh token.

<!-- fr:journal kind=root-cause scope=debug id=c3a84347702e created=2026-08-27T17:04:19 -->
### c3a84347702e · root-cause · Auto-updater + unbounded persistent sessions saturated the 8Gi limit

The overload is memory saturation, because the in-pod Claude Code auto-updater inflated the long-lived per-stream claude sessions (surge, digest) to ~4GB anon RSS each, pinning the agent container at its 8Gi memory.max in a permanent direct-reclaim storm; the 14:00Z surge-gate wake then tipped it into a group OOM kill. Contributing: the per-stream session design keeps claude processes alive for weeks (IDLE_RESET /clear resets context but never the process, so RSS never shrinks), and nothing in the pod disables the auto-updater despite the documented memory-safe-install convention.

<!-- fr:journal kind=finding scope=debug id=1e789feb81f8 created=2026-08-27T17:12:25 state=fixed -->
### 1e789feb81f8 · finding [fixed] · DISABLE_AUTOUPDATER=1 on every claude-running container + kali shim re-export

Fix: env DISABLE_AUTOUPDATER=1 added to alert-agent/agent, secure-agent-pod/kali+vk-local, n8n-01/multi-agent-shell, cnc-base/node; DISABLE_AUTOUPDATER joined the kali fr-env profile.d re-export loop (sshd scrubs container env from the SSH shells kali launches claude from). Failing-test-first: scripts/tests/test_claude_autoupdater_disabled.py (mirrors test_fr_isolation_target_env.py — env assertion per container + shim loop-line assertion) failed red on the unpatched manifests, green after. Gotcha one-liner in agents/rules/frank-gotchas.md + full prose in docs/runbooks/frank-gotchas/obs-digest.md. Out of scope, operational: the OOM already recycled the pod (memory now ~600MB), so the operator can attach and /login for the separate blank-refresh-token outage; dismissing the 'Set up auto mode' wizard with 'Don't show again' persists on the PVC. Follow-up for agent-images: session-process recycling (RSS never shrinks even without the updater) and pinning the wizard-suppressing config in the image seed.
