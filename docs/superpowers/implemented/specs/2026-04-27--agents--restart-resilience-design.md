# Agent Pod Restart Resilience — Design

**Spec:** `docs/superpowers/specs/2026-04-27--agents--restart-resilience-design.md`
**Layer:** `agents`
**Type:** Foundation extension (extends [`2026-04-15--agents--agent-images-and-vk-local-sidecar-design`](2026-04-15--agents--agent-images-and-vk-local-sidecar-design.md) and [`2026-03-30--agents--secure-agent-pod-design`](2026-03-30--agents--secure-agent-pod-design.md))
**Status:** Draft

---

## Goal

Make the secure-agent-pod (and the planned fleet of sibling agent pods) **survive container restarts gracefully**:

1. After any restart — scheduled (image bump) or unscheduled (in-pod error, OOM) — the operator can re-attach via mosh and tmux-continuum restores the layout, cwd, and pane structure they had moments before the death.
2. A single non-critical process dying inside the pod (e.g., supercronic getting SIGHUP'd by an in-pod agent's reload-signal experiment) does **not** take down the whole container.
3. When a scheduled restart happens, the operator gets a Telegram heads-up *before* the disruption, identifying which pod is being recreated.

The work also lays the foundation for ≥5 future agent pods (gemini-secure, gpt-secure, pii-secure, hermes-agent, media-generation-agent) to inherit these properties without per-pod plumbing.

## Motivation

This design is grounded in two real failures observed on `2026-04-26` / `2026-04-27`:

### Incident 1 — supercronic SIGHUP (2026-04-26 23:27 local)

An agent session running inside the kali container (`/home/claude/.willikins-agent/audit.jsonl` session `611ec71e-...`) was investigating supercronic's reload behavior. At 21:27:20 UTC it located the supercronic PID (67), then read `supercronic --help` looking for the reload signal. Seven seconds later supercronic died with SIGHUP — the agent had sent `kill -HUP 67`, expecting it to reload the crontab. supercronic's reload signal is `SIGUSR2`, not `SIGHUP`, and it doesn't trap SIGHUP, so the default action (terminate) ran. The kali container's `wait -n` saw the child die, the entrypoint exited, and kubelet restarted the container. mosh-server, tmux server, and every in-progress shell died with it.

This failure demonstrates that **any process under `wait -n` becomes a single point of failure for the whole container**, regardless of whether the process is critical to the pod's purpose.

### Incident 2 — image-bump cascade (2026-04-27 ~05:35 local)

PR #128 (`chore(agents): bump agent-images to a90c6c1`) auto-merged. ArgoCD synced. `secure-agent-pod`'s `Recreate` strategy meant the old pod terminated and a new pod started with the new image. ~30s of downtime. The operator's mosh session — which had survived Incident 1's restart by being re-spawned via `Cmd+Shift+2` (PR #127) — was killed again, with no warning.

This demonstrates that **scheduled restarts are common** (every agent-images push triggers one) and need to be visible to the operator with enough lead time to save context.

### Cost of the current design

The cumulative cost of these failures is hours of lost shell state per incident: in-flight `vim` buffers, half-typed commands, mid-debug `git rebase -i` sessions, attached `claude` REPL contexts. PR #127 ships the operator-side ergonomic patch (Cmd+Shift+2 re-spawn + the mosh+tmux availability) but **does not address the underlying disruption**. This spec does.

### Already shipped (PR #127)

The wezterm `Cmd+Shift+{1,2}` re-spawn key bindings and operating-post documentation landed in PR #127 (merged `2026-04-27`). They are the operator-side mitigation. This spec covers the cluster-side and image-side foundation that makes those re-spawns *cheap to recover from* rather than *catastrophic to start over from*.

## Constraints

1. **agent-base must remain shared between vk-local and shell-driven children.** Anything we add must respect the spec's discipline: "tools go here only if ≥2 children need them" (per the 2026-04-15 spec).
2. **vk-local stays single-driver-process.** vibe-kanban is K8s-supervised; vibe-kanban supervises its spawned children. Adding a third level of supervision (s6 in vk-local) would invert the K8s health contract and is out of scope.
3. **Existing secure-agent-kali state must be preserved.** No PV migration in this plan. The user/home rename to `agent`/`/home/agent` is deferred to a separate plan that can be scheduled when convenient.
4. **Non-root execution preserved.** UID 1000, all capabilities dropped, `runAsNonRoot: true`. The s6-overlay non-root path must work in this security context.
5. **Cilium L2 LB IPs preserved.** No Service changes; SSH on `192.168.55.215`, mosh on `192.168.55.219`.
6. **The fleet is the design target.** Six pods are coming. Anything we encode now should generalize to siblings without per-pod plumbing.
7. **Bump cadence is the existing pattern.** agent-images CI builds → `repository_dispatch` → frank's bumper workflow. We do not change this.

## Architecture

### Three-tier image base

```
┌──────────────────────────── derio-net/agent-images ────────────────────────────┐
│                                                                                │
│   agent-base (existing)                                                        │
│     debian:bookworm-slim + kubectl/jq/git/curl/claude/gh CLIs                  │
│     + /opt/agent-init.d/         [NEW] shared first-boot scripts:              │
│         01-pvc-dirs              (mkdir $AGENT_HOME/{repos,.ssh,...})          │
│         02-credential-migrate    (gitconfig env-var → /proc/1/environ helper)  │
│         03-credential-scrub      (remove leaked tokens from PVC state)         │
│     + tini still PID 1 for vk-local-style children                             │
│   │                                                                            │
│   ├── agent-shell-base                                                         │
│   │     [NEW] FROM agent-base                                                  │
│   │     + s6-overlay v3 install                                                │
│   │     + ENTRYPOINT ["/init"]   (replaces tini for shell pods)                │
│   │     + sshd + supercronic + tmux + mosh + locales-all                       │
│   │     + tmux-plugin-manager + tmux-resurrect + tmux-continuum                │
│   │       (system-wide at /usr/local/share/tmux-plugins/)                      │
│   │     + /etc/skel/.tmux.conf   (baseline tmux config seeded on first boot)   │
│   │     + /etc/cont-init.d/      00-run-agent-init                             │
│   │                              10-ssh-host-keys                              │
│   │                              20-venv (uv venv for cron-monitor scripts)    │
│   │                              30-authorized-keys                            │
│   │     + /etc/services.d/       sshd/run + supercronic/run                    │
│   │     + /etc/cont-finish.d/    01-shutdown                                   │
│   │                              02-tmux-save                                  │
│   │     + ARG AGENT_USER=agent / AGENT_HOME=/home/agent (parameterized)        │
│   │                                                                            │
│   │   ├── secure-agent-kali (existing → migrate)                               │
│   │   │     FROM agent-shell-base                                              │
│   │   │     --build-arg AGENT_USER=claude AGENT_HOME=/home/claude              │
│   │   │     drops its own entrypoint.sh; the responsibilities migrate to       │
│   │   │     agent-shell-base's cont-init.d / services.d / cont-finish.d        │
│   │   │     keeps: kali repo + pentest tools, /opt/scripts/, /opt/crontab      │
│   │   │                                                                        │
│   │   └── (future) secure-agent-{gemini,gpt,pii}, hermes-agent,                │
│   │       media-generation-agent — all FROM agent-shell-base, default          │
│   │       AGENT_USER=agent / AGENT_HOME=/home/agent (no build-arg override)    │
│   │                                                                            │
│   └── vk-local (existing → minimal change)                                     │
│         FROM agent-base                                                        │
│         ENTRYPOINT: thin wrapper:                                              │
│           for s in /opt/agent-init.d/*; do "$s"; done                          │
│           exec vibe-kanban                                                     │
│         tini stays PID 1 (handles vibe-kanban's spawned children for reaping)  │
│         no s6, no sshd, no supercronic, no tmux                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Why three tiers (not jinja snippets, not single-tier-with-build-args)

| Approach | Verdict | Reason |
|----------|---------|--------|
| Single base + build-arg toggles | Rejected | Same complexity as multiple Dockerfiles, smashed into one with conditionals; harder to read |
| Composable Dockerfile.j2 snippets | Rejected | We have **2 patterns** (shell-driven, single-driver-process), not N orthogonal features. The 6 planned pods cleanly split. Snippets buy flexibility for variants that don't exist; cost is jinja preprocessing + composition rules + test matrix forever after |
| **Three-tier base (chosen)** | Accepted | Agent-images already uses `FROM` chaining. Adding `agent-shell-base` is the same pattern, no new infra. Each child of `agent-shell-base` is a 5-line Dockerfile (FROM + COPY app-specific stuff). vk-local stays untouched in shape |

If we hit a third pattern in the next year (e.g., GPU-bound + ssh + Jupyter), revisit. The cost of revisiting is one Dockerfile refactor; the cost of premature snippet abstraction is permanent.

### User/home parameterization

`agent-shell-base` accepts build args:

```dockerfile
ARG AGENT_USER=agent
ARG AGENT_UID=1000
ARG AGENT_GID=1000
ARG AGENT_HOME=/home/agent
ENV AGENT_USER=${AGENT_USER} AGENT_UID=${AGENT_UID} AGENT_HOME=${AGENT_HOME}

RUN groupadd --gid ${AGENT_GID} ${AGENT_USER} && \
    useradd --uid ${AGENT_UID} --gid ${AGENT_GID} \
            --create-home --home-dir ${AGENT_HOME} \
            --shell /bin/bash ${AGENT_USER}

USER ${AGENT_USER}
WORKDIR ${AGENT_HOME}
```

- `secure-agent-kali` overrides via `--build-arg AGENT_USER=claude AGENT_HOME=/home/claude` to preserve all current PV-resident state (including VK SQLite worktree paths, cron schedules, claude session state).
- New shell-driven pods inherit the defaults — they're born `agent`/`/home/agent`, no migration debt accrues.
- All scripts in `/opt/agent-init.d/`, `/etc/cont-init.d/`, `/etc/services.d/*/run` use `$AGENT_HOME` exclusively. **No hardcoded `/home/claude` strings in any new code.** This is a hard rule for the implementation phase.

The future "rename existing secure-agent-kali" plan flips the build args, runs a SQL UPDATE on the VK SQLite to rewrite worktree paths, adds a temporary `/home/claude → /home/agent` symlink for backwards compat with PV-resident hardcodes, updates docs. Single PR, single bounce, scheduled when convenient.

## Component design

### agent-shell-base directory layout

```
/init                                       # s6-overlay, PID 1 (replaces tini for shell pods)

/etc/cont-init.d/                           # stage 1: one-shot setup, blocks until done, lexical order
  00-run-agent-init                         # for s in /opt/agent-init.d/*; do "$s"; done
  10-ssh-host-keys                          # gen $AGENT_HOME/.ssh-host-keys/* (first boot only)
  20-venv                                   # uv venv + croniter (first boot only) — for cron-monitor scripts
  30-authorized-keys                        # cp /etc/ssh-keys/authorized_keys → $AGENT_HOME/.ssh/authorized_keys

/etc/services.d/                            # stage 2: long-running, supervised
  sshd/
    run                                     # exec /usr/sbin/sshd -f /opt/sshd_config -D -e
    finish                                  # logs death + exit 0 (let s6 respawn per policy)
  supercronic/
    run                                     # exec supercronic $AGENT_HOME/.crontab
    finish                                  # logs death + exit 0

/etc/cont-finish.d/                         # stage 3: container shutdown
  01-shutdown                               # if [ -x /opt/scripts/shutdown.sh ]; then /opt/scripts/shutdown.sh; fi
  02-tmux-save                              # if pgrep tmux >/dev/null; then \
                                            #   tmux run-shell ~/.tmux/plugins/tmux-resurrect/scripts/save.sh; \
                                            # fi

/usr/local/share/tmux-plugins/              # system-wide plugin installs
  tmux-resurrect/
  tmux-continuum/

/etc/skel/.tmux.conf                        # baseline tmux config seeded into $AGENT_HOME on first boot
```

The `cont-init.d` ordering matters:
- `00-run-agent-init` calls the **shared** scripts in `/opt/agent-init.d/` (PVC dirs, credential safety) — these also run in vk-local
- `10-30` are shell-driven-only (sshd-related, cron venv-related)

### Crashloop policy

s6 service config uses `S6_RC_RESTART_LIMIT=5` and `S6_RC_RESTART_INTERVAL=60` (seconds). On the 6th restart within 60 seconds, s6 stops respawning the service. The service stays down; other services keep running.

| Failure mode | s6 response | K8s visibility |
|--------------|-------------|----------------|
| Single transient flap (e.g., supercronic SIGHUP'd once) | Respawn within ~1s | None — pod stays Ready, mosh+tmux uninterrupted |
| 5 deaths in 60s (e.g., binary missing, config corrupt) | Stop respawning; service stays down | sshd-down: K8s readinessProbe (TCP/sshd) trips; pod removed from LB. Supercronic-down: no probe, but `s6-svstat /run/service/supercronic` shows down — visible to ops scripts |
| Sustained crashloop > 60s | Same as above; s6's death counter window slides; service can recover later if it stops dying | Same |

Rationale: 5-in-60s catches true crashloops (something is fundamentally broken) while shrugging off transient flaps. Telegram alerts on bail-out are out of scope for this plan; bolt on later if real-world ops show value.

### Persistent shells: tmux-resurrect + tmux-continuum

Plugins installed at `/usr/local/share/tmux-plugins/` (system-wide, image-baked). `/etc/skel/.tmux.conf` enables them with these settings:

```
# tmux-resurrect: save/restore tmux state. Save path on PV survives container restarts.
set -g @resurrect-dir '~/.tmux/resurrect'
set -g @resurrect-capture-pane-contents 'on'

# tmux-continuum: auto-save layout every 5 min. Auto-restore on tmux server start.
set -g @continuum-save-interval '5'
set -g @continuum-restore 'on'

run-shell /usr/local/share/tmux-plugins/tmux-resurrect/resurrect.tmux
run-shell /usr/local/share/tmux-plugins/tmux-continuum/continuum.tmux
```

**What's preserved across a restart**: window names, pane layouts, cwd per pane, focused-process commandline (visible in `tmux ls`).

**What's NOT preserved**: in-flight running processes (vim's unsaved buffer, an in-progress `claude` REPL, a half-typed command, an open `git rebase -i`). This is the fundamental ceiling of any tool short of CRIU. The recovery story is "your layout came back; resume where you were."

The `/etc/skel/.tmux.conf` only seeds on first boot. Existing `~/.tmux.conf` files on the PV (if the user has customized) are not overwritten. The current secure-agent-kali pod has a `~/.tmux.conf` from PR #127 — implementation must merge the resurrect/continuum config without clobbering operator customizations. Approach: append-on-first-boot if `# managed-by-agent-shell-base` marker is absent; idempotent.

### Pre-restart save: cont-finish.d/02-tmux-save

When K8s sends SIGTERM (image bump, manual rollout, drain, etc.), s6 runs `cont-finish.d/` scripts in lexical order:

1. `01-shutdown` — calls `/opt/scripts/shutdown.sh` (existing logic from secure-agent-kali: signal claude remote-control PIDs for `bridge:shutdown` deregistration, ~30s graceful with SIGKILL fallback).
2. `02-tmux-save` — runs `tmux run-shell .../save.sh` to force a final continuum save **before** the tmux server dies.

This guarantees the saved snapshot is the latest possible state, not "up to 5 min stale." Without this, a user who just rearranged their session 30 seconds before a bump would lose those changes; the pre-stop save bridges that gap.

`02-tmux-save` is a no-op if no tmux server is running. It runs in <100ms when one is. The existing 45s `terminationGracePeriodSeconds` accommodates both shutdown.sh (~30s) and the tmux save (<1s) with margin.

### Process supervisor: s6-overlay v3

Why s6-overlay (and not bash respawn loop, runit, or others):
- **Container-lifecycle stages** (cont-init.d / services.d / cont-finish.d) match exactly what we need: one-shot setup separated from supervised long-runners separated from teardown.
- **Real PID-1 init** that handles zombie reaping and signal forwarding correctly. The current bash trap + `wait -n` works but is the kind of thing that subtly breaks when refactored.
- **Service dependencies (s6-rc)** become useful as soon as the second shell pod arrives — e.g., gemini-secure-pod's gemini-cli waiting on credential-mount-ready before starting.
- **Per-service log routing via s6-log** — clean per-service logs without a logrotate layer for the supervisor itself.
- **Active maintenance** — Bercot's stack is still developed; v3 is the stable target.

s6-overlay v3 install (in agent-shell-base Dockerfile):

```dockerfile
ARG S6_OVERLAY_VERSION=3.2.0.2
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz /tmp/
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz && \
    tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz && \
    rm /tmp/s6-overlay-*.tar.xz

ENV S6_KEEP_ENV=1 \
    S6_VERBOSITY=2 \
    S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    S6_KILL_GRACETIME=10000

ENTRYPOINT ["/init"]
```

`S6_KEEP_ENV=1` and `S6_VERBOSITY=2` are required for the non-root path; without them, services don't inherit the container's environment correctly. `S6_BEHAVIOUR_IF_STAGE2_FAILS=2` (default in v3) means a failed cont-init.d aborts startup. `S6_KILL_GRACETIME=10000` (10s) is the time s6 waits between sending SIGTERM and SIGKILL to surviving services after `cont-finish.d/` completes — sshd and supercronic exit on SIGTERM in 1-2s, so 10s is comfortable margin.

Total shutdown budget: `cont-finish.d/01-shutdown` (≤30s for `shutdown.sh` drain) + `cont-finish.d/02-tmux-save` (<1s) + S6_KILL_GRACETIME (≤10s) = ≤41s, fits within `terminationGracePeriodSeconds: 45`.

### Bump notifications: ArgoCD Notifications → Telegram

The notifications controller ships with the argo-cd Helm chart and is opt-in. Add to `apps/argocd/values.yaml`:

```yaml
notifications:
  enabled: true
```

Three additional resources in `apps/argocd-notifications/manifests/`:

**`configmap.yaml`** — defines the Telegram service, triggers, and templates:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-notifications-cm
  namespace: argocd
data:
  service.telegram: |
    token: $telegram-token

  trigger.on-sync-running: |
    - description: Application is rolling out
      send: [agent-pod-rolling]
      when: app.status.operationState.phase in ['Running']

  trigger.on-sync-succeeded: |
    - description: Application sync completed
      send: [agent-pod-ready]
      when: app.status.operationState.phase in ['Succeeded']

  template.agent-pod-rolling: |
    message: |
      🔄 *{{.app.metadata.name}}* is rolling out
      From: `{{.app.status.sync.revision | substr 0 7}}`
      To:   `{{.app.spec.source.targetRevision | substr 0 7}}`
      Pods will recreate in ~30s. mosh sessions will need re-spawn (Cmd+Shift+2).
    telegram:
      chatIds:
        - $telegram-chat-id

  template.agent-pod-ready: |
    message: |
      ✅ *{{.app.metadata.name}}* synced — `{{.app.status.sync.revision | substr 0 7}}`
    telegram:
      chatIds:
        - $telegram-chat-id
```

**`externalsecret.yaml`** — pulls the Telegram bot token + chat ID from Infisical via ESO into a `argocd-notifications-secret` Secret with keys `telegram-token` and `telegram-chat-id`.

**`vmservicescrape.yaml`** (optional, for observability) — scrapes the controller's metrics endpoint.

Subscribe by annotation on the Application CR. In `apps/root/templates/secure-agent-pod.yaml`:

```yaml
metadata:
  annotations:
    notifications.argoproj.io/subscribe.on-sync-running.telegram: ""
    notifications.argoproj.io/subscribe.on-sync-succeeded.telegram: ""
```

For new pods (gemini-secure, gpt-secure, etc.): copy the annotation block. Two-line opt-in. Template's `{{.app.metadata.name}}` automatically distinguishes which pod is rolling.

### vk-local minimal change

vk-local's existing entrypoint runs `vibe-kanban` directly (or via a thin shim under tini). The change is small: gain shared first-boot setup consistency.

```dockerfile
# vk-local/Dockerfile (existing, with addition)
COPY --from=ghcr.io/derio-net/agent-base:${BASE_SHA} /opt/agent-init.d /opt/agent-init.d

# Wrapper that runs shared first-boot scripts before exec'ing vibe-kanban.
COPY entrypoint-vk-local.sh /entrypoint.sh
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
```

```bash
#!/bin/sh
# entrypoint-vk-local.sh
set -e
for s in /opt/agent-init.d/*; do
  [ -x "$s" ] && "$s"
done
exec vibe-kanban "$@"
```

That's the entire vk-local diff. No s6, no service supervision, no behavioral change.

## Cluster-side changes (frank repo)

| File | Change | Reason |
|------|--------|--------|
| `apps/argocd/values.yaml` | Add `notifications.enabled: true` | Opt-in to argocd-notifications controller |
| `apps/argocd-notifications/manifests/configmap.yaml` | NEW — Telegram service + triggers + templates | Bump alert wiring |
| `apps/argocd-notifications/manifests/externalsecret.yaml` | NEW — pulls Telegram token/chat from Infisical | Secrets for the controller |
| `apps/root/templates/argocd-notifications.yaml` | NEW — Application CR pointing at the manifests/ dir | ArgoCD pattern |
| `apps/secure-agent-pod/manifests/deployment.yaml` | Remove `lifecycle.preStop.exec` (cont-finish.d/01-shutdown replaces it) | s6 owns shutdown |
| `apps/root/templates/secure-agent-pod.yaml` | Add notifications annotations | Subscribe to Telegram |

Image bumps in agent-images repo (the actual implementation work) live there; the bumper workflow updates `apps/secure-agent-pod/manifests/deployment.yaml`'s `image:` tag automatically once a new SHA exists. No manual bump in this plan.

## Migration sequence

The plan needs to land in a specific order to avoid disruption:

1. **agent-images: ship `agent-base` updates** — add `/opt/agent-init.d/*`. Existing children (kali, vk-local) keep working because nobody calls these scripts yet. Verify via CI.
2. **agent-images: ship `agent-shell-base`** — new image, no children depend on it yet. Build smoke test runs s6 + supercronic kill/respawn locally. Verify non-root path works.
3. **agent-images: migrate `secure-agent-kali`** — change FROM, add build args, delete entrypoint.sh. Per-pod additions (kali repos, /opt/scripts/, /opt/crontab) stay. CI matrix builds the new image. **This produces a new SHA that triggers a frank bump.**
4. **agent-images: update `vk-local`** — add the entrypoint-vk-local.sh wrapper. CI builds. Behavior unchanged. **Same bump cycle as step 3** (matrix builds happen together).
5. **frank: deploy argocd-notifications first** — controller + configmap + secret. Verify Telegram fires on a benign trigger (e.g., test app sync) before adding subscriptions to real apps.
6. **frank: bump agent-images SHA** (auto via bumper) — pulls in the new secure-agent-kali + vk-local images. Pod restarts with s6 as PID 1. Operator must re-spawn mosh via `Cmd+Shift+2`. Verify pod reaches Ready, sshd accessible, supercronic running, kill+respawn works.
7. **frank: drop preStop, add notifications annotations to secure-agent-pod Application** — second pod restart. Operator gets Telegram alert this time. Re-spawn via Cmd+Shift+2.
8. **Verification phase** — exercise the full restart resilience story end-to-end (see Verification section below).
9. **Documentation phase** — update operating post (s6 status commands, troubleshooting), building post (architecture diagram), README, gotchas.

Steps 6 and 7 are two separate disruptions deliberately — keeping them sequential reduces blast radius if something goes wrong in either.

## Verification

End-to-end story that must work after deployment:

1. **Shell session establishment**: `Cmd+2` opens the frank workspace, mosh+tmux attach to `claude-frank-secure-pod`.
2. **In-pod resilience**: SSH into the pod, `pkill supercronic`. Within 1-2s, `pgrep supercronic` finds it again. mosh+tmux session is uninterrupted.
3. **Layout persistence**: split the tmux session into 4 panes with different cwds, wait 6 minutes (one auto-save cycle plus margin), trigger a pod restart (`kubectl delete pod -n secure-agent-pod -l app=secure-agent-pod`). Telegram alert fires *first* (announcing the rollout). Mosh session blackholes. `Cmd+Shift+2` re-spawns. tmux-continuum auto-restores: 4 panes back, cwds back. Running processes are gone (expected).
4. **Image bump resilience**: same as above but triggered by a `chore(agents): bump` PR auto-merge. Telegram alert from ArgoCD Notifications. Cmd+Shift+2 re-spawn. Layout restored.
5. **Crashloop bail**: rename `/usr/local/bin/supercronic` to `/usr/local/bin/supercronic.broken` inside the running pod (simulating a broken update). Trigger 5 supercronic restarts in 60s by repeatedly killing the respawned PID. Observe `s6-svstat /run/service/supercronic` showing `down`. sshd remains up. Pod readinessProbe passes (it checks sshd, not supercronic). Restore the binary; `s6-svc -u /run/service/supercronic` brings it back.
6. **Independent service deaths**: kill sshd. Pod's readinessProbe fails. LB sheds the pod from the SSH service. supercronic keeps running. After 1s respawn, sshd is back, readiness recovers.

A subset of these become automated smoke tests in agent-images CI (1, 2, 5, 6 are containerizable; 3 and 4 require cluster).

## Risks

| Risk | Probability | Mitigation |
|------|-------------|------------|
| s6 non-root quirks (UID 1000 + caps-dropped + readOnlyRootFS-adjacent constraints) bite | Medium | Build-time smoke test runs against the exact pod SecurityContext locally; `S6_KEEP_ENV=1` + `S6_VERBOSITY=2` set explicitly; spec captures the verified config |
| Migration to s6 introduces subtle behavior change (signal forwarding, log routing) that breaks existing scripts | Medium | Side-by-side: deploy new image to a copy of the pod manifest in a different namespace first (`secure-agent-pod-staging`), exercise SSH+mosh+tmux+cron+claude+VK for ~24h before cutover |
| ArgoCD Notifications controller fights argocd-server during chart upgrade | Low | Both ship from the same Helm chart; opt-in is a single value flag; rollback is removing the flag |
| tmux-continuum auto-save runs while s6 is shutting down → corrupted save | Low | `cont-finish.d/02-tmux-save` runs *after* `01-shutdown` and *before* tmux server dies; explicit save before SIGTERM cascade |
| Bumping agent-shell-base image forces coupled bumps for ALL shell-driven children | Medium (long-term) | Acceptable initially (only secure-agent-kali exists). Revisit pinning strategy when second shell pod arrives — likely solution is each child pinning a specific agent-shell-base SHA in its FROM line, only updated deliberately |
| Telegram-token rotation breaks notifications silently | Low | ESO syncs from Infisical; if Infisical updates the secret, ESO refreshes within 1 minute; controller picks up the change on its next reconcile loop |
| The /etc/skel/.tmux.conf seed clobbers operator customizations on existing PV | High if naive | First-boot seeding uses a marker (`# managed-by-agent-shell-base`) — only writes if marker absent. Existing PV has no marker → seed writes ONCE and is then user-modifiable |
| Crashloop bail leaves supercronic down indefinitely without operator awareness | Medium | sshd-readinessProbe-based bail is visible (pod removed from LB); supercronic-only bail surfaces in `s6-svstat` and via the staleness alerts that already exist (`session-manager-stale`, `audit-digest-stale` in the operating post). Telegram alerts on s6 bail-out are a future enhancement, not in this plan |

## Rollback

Each layer has independent rollback:

| Layer | Forward | Rollback |
|-------|---------|----------|
| `/opt/agent-init.d/` in agent-base | Add scripts | Drop scripts; nothing depends on them yet |
| `agent-shell-base` image | Build new image | Don't use it; secure-agent-kali stays on previous SHA |
| secure-agent-kali migration | FROM agent-shell-base + delete entrypoint.sh | Revert: FROM agent-base + restore entrypoint.sh from git. One PR revert |
| vk-local entrypoint wrapper | Add wrapper script | Revert wrapper, restore previous ENTRYPOINT |
| ArgoCD Notifications controller | Helm flag | Set `notifications.enabled: false`; controller scales to 0 |
| Notifications subscription annotations | Add annotations | Remove annotations; controller becomes inert for that app |
| preStop removal | Drop block from deployment.yaml | Restore the block; cont-finish.d still works alongside (idempotent — both call shutdown.sh via different paths) |
| tmux-resurrect/continuum config in /etc/skel | Append + run-shell lines | Comment out the run-shell lines in /etc/skel/.tmux.conf; existing per-user .tmux.conf files unaffected |

## Out of scope

Items deliberately not included in this plan:

- **Existing secure-agent-kali rename** to `agent`/`/home/agent`. Will be a separate plan when scheduled.
- **Tmux usage inside vk-local.** If VK starts wrapping spawned `claude` in tmux for resumability, that's a vk-local feature decision needing its own design (which tmux server runs, save policy, attach mechanism, etc.).
- **Per-pod egress profiles** for new shell pods. Cilium policies are pod-specific; gemini-secure-pod's egress allowlist (Google APIs), gpt-secure-pod's (OpenAI), pii-secure-pod's (none?) are individual-plan concerns.
- **Generalized `spawn_agent_workspace(name, ssh_ip, udp_ip, tmux_session)` in wezterm.lua.** The current `spawn_frank_workspace` will be parameterized when the second shell pod arrives — premature now.
- **Telegram alerts on s6 crashloop bail-out.** Useful operational visibility but small marginal value over the existing staleness alerts. Bolt-on candidate after fleet expansion if real ops show value.
- **Service dependencies (s6-rc) for credential-mount-ready before agent-CLI start.** Will become valuable when gemini-secure-pod / gpt-secure-pod arrive (their CLIs need credentials at startup); declarative dependency expression is a per-pod addition then.
- **CRIU-based process checkpointing** for true running-process survival. Kubernetes alpha, not viable here. The fundamental ceiling stands: in-flight processes don't survive container restarts.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| Agent Pod Restart Resilience — Implementation Plan (agent-images side) | `derio-net/agent-images` | `2026-04-27--agents--restart-resilience` | — |
| Agent Pod Restart Resilience — Implementation Plan (frank side) | `derio-net/frank` | `2026-04-27--agents--restart-resilience` | Phases 1-4 of agent-images side (cross-repo) |

## Open questions

None blocking. Items resolved during the brainstorming:

- Supervisor choice: **s6-overlay v3** (vs bash respawn, vs runit) — fleet of 6 pods makes s6's structure earn its weight.
- Base topology: **three-tier** (vs single-base + build-args, vs jinja snippets) — matches the 2-pattern split (shell-driven vs single-driver-process).
- User parameterization: **build-args, defaults to `agent`/`/home/agent`** (vs hardcoded, vs deferred) — secure-agent-kali overrides to preserve state; new pods inherit defaults.
- Telegram source: **ArgoCD Notifications** (vs GHA workflow, vs health-bridge extension) — fires at sync time, scales by annotation, native primitive.
- tmux save interval: **5 minutes** (vs 15 default, vs 1).
- Crashloop policy: **bail after 5 deaths in 60s** (vs respawn forever, vs page-on-bail) — bail without alert for now.

---

## References

- [Incident 1 audit log entry](https://github.com/derio-net/frank/blob/main/docs/superpowers/implemented/plans/2026-04-26--agents--secure-pod-tmux-mosh.md.v1-archive#appendix-client-side-configuration--debug-journey) — supercronic SIGHUP at 21:27:35 UTC
- [PR #126](https://github.com/derio-net/frank/pull/126) — mosh tuning, 16 ports + 1h server timeout
- [PR #127](https://github.com/derio-net/frank/pull/127) — Phase 4 docs + wezterm Cmd+Shift+{1,2} re-spawn
- [PR #128](https://github.com/derio-net/frank/pull/128) — agent-images bump that re-killed the post-Incident-1 mosh session
- [s6-overlay v3 docs](https://github.com/just-containers/s6-overlay)
- [tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect) + [tmux-continuum](https://github.com/tmux-plugins/tmux-continuum)
- [ArgoCD Notifications controller](https://argo-cd.readthedocs.io/en/stable/operator-manual/notifications/)
