# Agent Pod Restart Resilience — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-27--agents--restart-resilience-design.md`
**Status:** Not Started

**Type:** Fix/extension of the `agents` layer (extends [`2026-04-15--agents--agent-images-and-vk-local-sidecar`](../archived-plans/2026-04-15--agents--agent-images-and-vk-local-sidecar.md) and [`2026-03-30--agents--secure-agent-pod`](../archived-plans/2026-03-30--agents--secure-agent-pod.md)). Per `repo-workflows.md`: same layer code, update existing layer's blog posts (no new posts).

**Goal:** Make the secure-agent-pod (and the planned fleet of sibling agent pods) survive container restarts gracefully — sessions re-attachable with layout intact, scheduled disruptions surface as Telegram alerts, and a single non-critical process dying inside the pod no longer takes down the whole container.

**Why now:** Two real failures on 2026-04-26/27 (in-pod agent SIGHUP'd supercronic → kali container died; image bump 4.5h later silently recreated the pod) made the cost of the current design concrete. PR #127 shipped operator-side mitigation (wezterm Cmd+Shift+{1,2} re-spawn); this plan addresses the underlying disruption.

**Cross-repo:** Plan touches both `derio-net/agent-images` (Phases 1-4) and `derio-net/frank` (Phases 5-9). Each phase declares its target repo. Plan file lives in frank; agent-images-targeted issues file against that repo when dispatched.

---

## Phase 1: `/opt/agent-init.d/` shared first-boot scripts in `agent-base` [agentic]
**Target repo:** `derio-net/agent-images`
**Depends on:** —

<!-- Tracking: Add scripts to agent-base; both kali (via shell-base) and vk-local (via direct entrypoint) consume them. -->

Move the first-boot setup that's currently inline in `kali/entrypoint.sh` into a per-repo location both children can call. Scripts must be idempotent (every boot) and safe to call as the non-root agent user.

### Task 1: Add `/opt/agent-init.d/01-pvc-dirs` to `agent-base/`

- [ ] **Step 1: Create `agent-base/opt/agent-init.d/01-pvc-dirs` script**

```bash
#!/bin/bash
# 01-pvc-dirs — Create PVC-backed directories with correct permissions.
# Idempotent: every-boot script. Uses $AGENT_HOME (set in agent-base ENV).
set -e
HOME="${AGENT_HOME:-$HOME}"
mkdir -p "$HOME/.ssh-host-keys" "$HOME/.ssh" "$HOME/repos" "$HOME/.claude" "$HOME/.willikins-agent"
chmod 700 "$HOME/.ssh-host-keys" "$HOME/.ssh"
```

- [ ] **Step 2: Add to `agent-base/Dockerfile`**

```dockerfile
COPY opt/agent-init.d/ /opt/agent-init.d/
RUN chmod +x /opt/agent-init.d/*
```

### Task 2: Add `/opt/agent-init.d/02-credential-migrate`

- [ ] **Step 1: Create `agent-base/opt/agent-init.d/02-credential-migrate` script**

Migrates the legacy gitconfig credential helper from env-var-based (which silently failed for VS Code subprocesses and cron) to `/proc/1/environ` reader. Lifted from current `kali/entrypoint.sh` lines covering this migration. Use `$AGENT_HOME`, not `/home/claude`.

```bash
#!/bin/bash
# 02-credential-migrate — Migrate legacy gitconfig credential helper to /proc/1/environ.
set -e
HOME="${AGENT_HOME:-$HOME}"
[ -f /opt/gitconfig ] || exit 0
[ -f "$HOME/.gitconfig" ] || exit 0
if grep -qF 'password=$GITHUB_TOKEN' "$HOME/.gitconfig"; then
    echo "[agent-init] migrating git credential helper to /proc/1/environ reader"
    cp /opt/gitconfig "$HOME/.gitconfig"
fi
```

### Task 3: Add `/opt/agent-init.d/03-credential-scrub`

- [ ] **Step 1: Create `agent-base/opt/agent-init.d/03-credential-scrub` script**

Removes leaked git credentials from PVC state (URL `.insteadof` rewrites, embedded-token origin URLs). Lifted from current `kali/entrypoint.sh`. Idempotent — runs every boot.

```bash
#!/bin/bash
# 03-credential-scrub — Strip leaked tokens from PVC-resident git config.
set -e
HOME="${AGENT_HOME:-$HOME}"

while IFS= read -r key; do
    [ -z "$key" ] && continue
    case "$key" in
        *@github.com*) git config --global --unset-all "$key" || true ;;
    esac
done < <(git config --global --name-only --get-regexp '^url\..*\.insteadof$' 2>/dev/null || true)

shopt -s nullglob
for repo_dir in "$HOME"/repos/*/; do
    [ -d "$repo_dir/.git" ] || continue
    origin_url=$(git -C "$repo_dir" remote get-url origin 2>/dev/null) || continue
    clean_url=$(printf '%s' "$origin_url" | sed -E 's#https://[^@/]+@github\.com/#https://github.com/#')
    if [ "$origin_url" != "$clean_url" ]; then
        git -C "$repo_dir" remote set-url origin "$clean_url"
        echo "[agent-init] scrubbed credentials from $(basename "$repo_dir") origin"
    fi
done
shopt -u nullglob
```

### Task 4: Validate scripts work standalone

- [ ] **Step 1: Build agent-base locally and exercise the scripts**

```bash
cd agent-images
docker build -t agent-base:test ./agent-base
docker run --rm -e AGENT_HOME=/tmp/test-home -e HOME=/tmp/test-home agent-base:test \
    bash -c 'mkdir -p /tmp/test-home && for s in /opt/agent-init.d/*; do echo "==> $s"; "$s"; done'
```

Expected: each script runs to completion with exit 0. The `01-pvc-dirs` script creates the expected dirs. `02-credential-migrate` and `03-credential-scrub` are no-ops on the empty test home.

### Task 5: Open PR + merge

- [ ] **Step 1: Open PR `feat(base): /opt/agent-init.d shared first-boot scripts`**

Body explains the role: shared first-boot setup that both `agent-shell-base`-derived images (via `cont-init.d`) and `vk-local` (via entrypoint wrapper) call. No behavior change to existing children yet — kali still has its own entrypoint that doesn't call these. Phase 3 cuts kali over.

- [ ] **Step 2: Wait for matrix CI green, then merge**

CI builds agent-base + secure-agent-kali + vk-local on every push. Confirm all three still build. The bumper workflow will fire a chore PR in frank — **do not merge it yet** until Phase 4 lands. Hold or close the bump PR.

---

## Phase 2: Build `agent-shell-base` image [agentic]
**Target repo:** `derio-net/agent-images`
**Depends on:** Phase 1

<!-- Tracking: New base image with s6-overlay v3 + supervised sshd/supercronic + tmux-resurrect/continuum + parameterization. -->

Net-new Dockerfile + cont-init.d + services.d + cont-finish.d + tmux-plugin install. Builds once in agent-images CI; no children depend on it yet (Phase 3 cuts kali over).

### Task 1: Scaffold `agent-shell-base/` directory in `agent-images`

- [ ] **Step 1: Create the directory layout**

```text
agent-shell-base/
├── Dockerfile
├── sshd_config
├── etc/
│   ├── cont-init.d/
│   │   ├── 00-run-agent-init
│   │   ├── 10-ssh-host-keys
│   │   ├── 20-venv
│   │   └── 30-authorized-keys
│   ├── services.d/
│   │   ├── sshd/
│   │   │   ├── run
│   │   │   └── finish
│   │   └── supercronic/
│   │       ├── run
│   │       └── finish
│   ├── cont-finish.d/
│   │   ├── 01-shutdown
│   │   └── 02-tmux-save
│   ├── skel/
│   │   └── .tmux.conf
│   └── agent/
│       └── tmux-resurrect.conf
└── README.md
```

### Task 2: Write `agent-shell-base/Dockerfile`

- [ ] **Step 1: s6-overlay install + parameterization**

```dockerfile
ARG BASE_SHA=latest
FROM ghcr.io/derio-net/agent-base:${BASE_SHA}

ARG AGENT_USER=agent
ARG AGENT_UID=1000
ARG AGENT_GID=1000
ARG AGENT_HOME=/home/agent
ENV AGENT_USER=${AGENT_USER} AGENT_UID=${AGENT_UID} AGENT_HOME=${AGENT_HOME}

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server \
      tmux mosh locales-all \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd /var/run/sshd

ARG SUPERCRONIC_VERSION=0.2.30
RUN curl -fsSLo /usr/local/bin/supercronic \
      https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64 \
    && chmod +x /usr/local/bin/supercronic

RUN mkdir -p /usr/local/share/tmux-plugins \
    && git clone --depth 1 https://github.com/tmux-plugins/tmux-resurrect /usr/local/share/tmux-plugins/tmux-resurrect \
    && git clone --depth 1 https://github.com/tmux-plugins/tmux-continuum /usr/local/share/tmux-plugins/tmux-continuum

ARG S6_OVERLAY_VERSION=3.2.0.2
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz /tmp/
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz \
    && tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz \
    && rm /tmp/s6-overlay-*.tar.xz

ENV S6_KEEP_ENV=1 \
    S6_VERBOSITY=2 \
    S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    S6_KILL_GRACETIME=10000

RUN groupadd --gid ${AGENT_GID} ${AGENT_USER} \
    && useradd --uid ${AGENT_UID} --gid ${AGENT_GID} \
               --create-home --home-dir ${AGENT_HOME} \
               --shell /bin/bash ${AGENT_USER}

COPY etc/ /etc/
RUN chmod +x /etc/cont-init.d/* /etc/services.d/*/run /etc/services.d/*/finish /etc/cont-finish.d/*

COPY sshd_config /opt/sshd_config
RUN sed -i "s|__AGENT_HOME__|${AGENT_HOME}|g" /opt/sshd_config

USER ${AGENT_USER}
WORKDIR ${AGENT_HOME}

ENTRYPOINT ["/init"]
```

### Task 3: Write `etc/cont-init.d/00-run-agent-init`

- [ ] **Step 1: Wrapper that calls all scripts in `/opt/agent-init.d/` in order**

```bash
#!/usr/bin/with-contenv bash
# 00-run-agent-init — Call shared first-boot scripts from agent-base.
set -e
shopt -s nullglob
for s in /opt/agent-init.d/*; do
    [ -x "$s" ] || continue
    echo "[cont-init] running $s"
    "$s"
done
```

`with-contenv` passes Docker env vars (including `$AGENT_HOME`) into the script — required for non-root mode.

### Task 4: Write `etc/cont-init.d/10-ssh-host-keys`

- [ ] **Step 1: Generate sshd host keys on first boot, idempotent**

```bash
#!/usr/bin/with-contenv bash
set -e
KEYDIR="${AGENT_HOME}/.ssh-host-keys"
if [ ! -f "$KEYDIR/ssh_host_ed25519_key" ]; then
    echo "[cont-init] generating SSH host keys (first boot)"
    ssh-keygen -t ed25519 -f "$KEYDIR/ssh_host_ed25519_key" -N ""
    ssh-keygen -t rsa -b 4096 -f "$KEYDIR/ssh_host_rsa_key" -N ""
fi
chmod 600 "$KEYDIR"/ssh_host_*_key
```

### Task 5: Write `etc/cont-init.d/20-venv`

- [ ] **Step 1: Create uv venv with croniter for cron-monitor scripts**

```bash
#!/usr/bin/with-contenv bash
# 20-venv — Python venv for cron heartbeat scripts (compute-next-run.py,
# push-next-expected.sh use croniter).
set -e
VENV="${AGENT_HOME}/.willikins-agent/.venv"
if [ ! -d "$VENV" ]; then
    echo "[cont-init] creating Python venv for cron monitor scripts"
    mkdir -p "${AGENT_HOME}/.willikins-agent"
    uv venv "$VENV"
    uv pip install --python "$VENV/bin/python" croniter
fi
```

### Task 6: Write `etc/cont-init.d/30-authorized-keys`

- [ ] **Step 1: Copy authorized_keys from mounted Secret to $AGENT_HOME/.ssh/**

```bash
#!/usr/bin/with-contenv bash
set -e
if [ -f /etc/ssh-keys/authorized_keys ]; then
    cp /etc/ssh-keys/authorized_keys "${AGENT_HOME}/.ssh/authorized_keys"
    chmod 600 "${AGENT_HOME}/.ssh/authorized_keys"
fi
```

### Task 7: Write `etc/services.d/sshd/{run,finish}`

- [ ] **Step 1: sshd service definition**

`run`:
```bash
#!/usr/bin/with-contenv bash
exec /usr/sbin/sshd -f /opt/sshd_config -D -e
```

`finish`:
```bash
#!/usr/bin/with-contenv bash
echo "[s6] sshd exited code=$1 (signal=$2)"
exit 0
```

### Task 8: Write `etc/services.d/supercronic/{run,finish}`

- [ ] **Step 1: supercronic service definition**

`run`:
```bash
#!/usr/bin/with-contenv bash
exec supercronic "${AGENT_HOME}/.crontab"
```

`finish`:
```bash
#!/usr/bin/with-contenv bash
echo "[s6] supercronic exited code=$1 (signal=$2)"
exit 0
```

### Task 9: Write `etc/cont-finish.d/{01-shutdown, 02-tmux-save}`

- [ ] **Step 1: 01-shutdown — calls per-pod shutdown.sh if present**

```bash
#!/usr/bin/with-contenv bash
set +e
if [ -x /opt/scripts/shutdown.sh ]; then
    echo "[cont-finish] running /opt/scripts/shutdown.sh"
    /opt/scripts/shutdown.sh
fi
exit 0
```

- [ ] **Step 2: 02-tmux-save — force tmux-resurrect save before shutdown**

```bash
#!/usr/bin/with-contenv bash
set +e
if pgrep -u "${AGENT_USER}" tmux >/dev/null 2>&1; then
    echo "[cont-finish] forcing tmux-resurrect save before shutdown"
    su - "${AGENT_USER}" -c 'tmux run-shell /usr/local/share/tmux-plugins/tmux-resurrect/scripts/save.sh' || true
fi
exit 0
```

### Task 10: Write `etc/skel/.tmux.conf` baseline

- [ ] **Step 1: Baseline seeded into $AGENT_HOME on first boot**

```text
# Baseline tmux config — seeded from /etc/skel into $AGENT_HOME on first boot.
# Subsequent boots leave any operator customizations alone.

set -g default-terminal "tmux-256color"
set -g mouse on
set -g history-limit 100000
set -g status-right "#{?client_prefix,#[bg=red,bold] PREFIX ,}#H:#M"

bind | split-window -h \; select-layout even-horizontal
bind S split-window -v \; select-layout even-vertical
bind r source-file ~/.tmux.conf \; display "reloaded"

source-file /etc/agent/tmux-resurrect.conf
```

### Task 11: Write `etc/agent/tmux-resurrect.conf`

- [ ] **Step 1: Plugin loader + settings — sourced by .tmux.conf**

```text
set -g @resurrect-dir '~/.tmux/resurrect'
set -g @resurrect-capture-pane-contents 'on'

set -g @continuum-save-interval '5'
set -g @continuum-restore 'on'

run-shell /usr/local/share/tmux-plugins/tmux-resurrect/resurrect.tmux
run-shell /usr/local/share/tmux-plugins/tmux-continuum/continuum.tmux
```

### Task 12: Write baseline `sshd_config`

- [ ] **Step 1: Non-root sshd config with __AGENT_HOME__ placeholders**

```text
Port 2222
HostKey __AGENT_HOME__/.ssh-host-keys/ssh_host_ed25519_key
HostKey __AGENT_HOME__/.ssh-host-keys/ssh_host_rsa_key
AuthorizedKeysFile __AGENT_HOME__/.ssh/authorized_keys
PubkeyAuthentication yes
PasswordAuthentication no
UsePAM no
StrictModes no
PidFile __AGENT_HOME__/.ssh/sshd.pid
```

The Dockerfile's `RUN sed` substitutes `__AGENT_HOME__` with the actual `$AGENT_HOME` value at build time.

### Task 13: Add agent-shell-base to CI matrix

- [ ] **Step 1: Update `.github/workflows/build.yml` matrix**

Add `agent-shell-base` to the matrix list. Build order: agent-base → agent-shell-base (uses `BASE_SHA` arg from agent-base's just-built tag) → kali/vk-local.

### Task 14: Build smoke test

- [ ] **Step 1: Local container exercises s6 + sshd + supercronic + crashloop bail**

```bash
docker build -t agent-shell-base:test \
    --build-arg BASE_SHA=$(git rev-parse HEAD) \
    ./agent-shell-base

docker run -d --name shell-test \
    --user 1000 \
    --cap-drop ALL \
    -v $(pwd)/test-home:/home/agent \
    -p 2222:2222 \
    agent-shell-base:test

sleep 3

docker exec shell-test s6-svstat /run/service/sshd
docker exec shell-test s6-svstat /run/service/supercronic
docker exec shell-test pgrep -af supercronic
docker exec shell-test pgrep -af 'sshd: /usr/sbin'

# Single transient flap — observe respawn within 1-2s.
docker exec shell-test pkill -SIGTERM supercronic
sleep 2
docker exec shell-test s6-svstat /run/service/supercronic

# Crashloop bail — 5 deaths in 60s.
for i in 1 2 3 4 5 6; do
    docker exec shell-test pkill -SIGKILL supercronic 2>/dev/null
    sleep 0.5
done
sleep 5
docker exec shell-test s6-svstat /run/service/supercronic   # down
docker exec shell-test s6-svstat /run/service/sshd          # still up

docker rm -f shell-test
```

Expected: respawn works for single flap; bail-out triggers after 5 deaths in 60s; sshd unaffected by supercronic bail.

### Task 15: Open PR + merge

- [ ] **Step 1: Open PR `feat(images): agent-shell-base — s6-overlay supervisor + tmux persistence`**

- [ ] **Step 2: Wait for matrix CI green, merge**

Bumper fires for kali + vk-local with the new agent-base SHA — **still hold those bumps** until Phase 4 lands.

---

## Phase 3: Migrate `secure-agent-kali` to `FROM agent-shell-base` [agentic]
**Target repo:** `derio-net/agent-images`
**Depends on:** Phase 2

<!-- Tracking: Cut kali over to s6-based shell-base; preserve claude/home/claude state via build args; delete bespoke entrypoint.sh. -->

The migration that actually delivers the resilience to the running pod. Kali keeps its identity (`claude`/`/home/claude`) via build args; everything else (sshd, supercronic, tmux, /opt/scripts/, /opt/crontab) stays.

### Task 1: Update `kali/Dockerfile` to FROM agent-shell-base

- [ ] **Step 1: Change FROM line, override agent identity, drop entrypoint logic**

```dockerfile
ARG BASE_SHA=latest
FROM ghcr.io/derio-net/agent-shell-base:${BASE_SHA}

# Preserve existing PV state: stay as `claude` / `/home/claude`.
ARG AGENT_USER=claude
ARG AGENT_HOME=/home/claude
USER root

# agent-shell-base created `agent` user; replace with legacy identity.
RUN userdel -r agent 2>/dev/null || true \
    && groupadd --gid 1000 ${AGENT_USER} \
    && useradd --uid 1000 --gid 1000 \
               --create-home --home-dir ${AGENT_HOME} \
               --shell /bin/bash ${AGENT_USER}

ENV AGENT_USER=${AGENT_USER} AGENT_HOME=${AGENT_HOME}

# Re-substitute sshd_config for the legacy home.
RUN sed -i "s|/home/agent|${AGENT_HOME}|g" /opt/sshd_config

# Kali repos + tools (existing).
RUN apt-get update && apt-get install -y --no-install-recommends \
      kali-archive-keyring \
    && echo "deb https://http.kali.org/kali kali-rolling main contrib non-free non-free-firmware" > /etc/apt/sources.list.d/kali.list \
    && apt-get update && apt-get install -y --no-install-recommends \
       kali-tools-top10 nmap netcat-traditional logrotate \
    && rm -rf /var/lib/apt/lists/*

# Existing /opt/scripts/, /opt/crontab, /opt/load-env.sh, /opt/bashrc,
# /opt/settings.json, /opt/gitconfig — UNCHANGED, copied as before.
COPY opt/ /opt/

# Existing CLI installs (kubectl, talosctl, omnictl, claude, gh, ...) —
# UNCHANGED; copy from current Dockerfile lines.

USER ${AGENT_USER}
WORKDIR ${AGENT_HOME}

# ENTRYPOINT inherited from agent-shell-base ("/init"). Do NOT override.
```

### Task 2: Delete `kali/entrypoint.sh`

- [ ] **Step 1: Remove the file**

Its responsibilities migrated to:
- First-boot dirs/configs → `/opt/agent-init.d/01-pvc-dirs` (Phase 1)
- Credential migration/scrub → `/opt/agent-init.d/02-credential-migrate`, `03-credential-scrub` (Phase 1)
- ssh host keys → `/etc/cont-init.d/10-ssh-host-keys` (Phase 2)
- venv creation → `/etc/cont-init.d/20-venv` (Phase 2)
- authorized_keys → `/etc/cont-init.d/30-authorized-keys` (Phase 2)
- sshd start → `/etc/services.d/sshd/run` (Phase 2)
- supercronic start → `/etc/services.d/supercronic/run` (Phase 2)
- SIGTERM trap → handled by s6
- shutdown.sh → `/etc/cont-finish.d/01-shutdown` calls `/opt/scripts/shutdown.sh`
- `wait -n` → not needed; s6 supervises

### Task 3: Audit `/opt/scripts/*.sh` for hardcoded /home/claude paths

- [ ] **Step 1: Grep + replace**

```bash
grep -rnE '/home/claude' kali/opt/scripts/
```

Most current scripts use `${WILLIKINS_AGENT_DIR:-$HOME/.willikins-agent}` or similar — these are clean. Any hardcoded `/home/claude` references must be replaced with `$HOME` or `$AGENT_HOME` even though kali stays as `claude` today. **Required cleanup before merge** — hardcoded paths block the future rename plan.

### Task 4: Smoke test the migrated image

- [ ] **Step 1: Build with explicit build args**

```bash
docker build -t secure-agent-kali:test \
    --build-arg BASE_SHA=$(git rev-parse HEAD) \
    --build-arg AGENT_USER=claude \
    --build-arg AGENT_HOME=/home/claude \
    ./kali
```

- [ ] **Step 2: Run with the same SecurityContext as the deployment**

```bash
docker run -d --name kali-test \
    --user 1000 \
    --cap-drop ALL \
    -v $(pwd)/test-home:/home/claude \
    -p 2222:2222 \
    secure-agent-kali:test

sleep 3
docker exec kali-test id
docker exec kali-test ls /home/claude/.ssh-host-keys/ssh_host_ed25519_key
docker exec kali-test pgrep -af 'sshd: /usr/sbin'
docker exec kali-test pgrep -af supercronic
docker exec kali-test ls /usr/local/share/tmux-plugins/

ssh -p 2222 -i test-key claude@127.0.0.1 'whoami'   # claude

docker rm -f kali-test
```

### Task 5: Open PR + merge

- [ ] **Step 1: Open PR `feat(kali): migrate to agent-shell-base; delete entrypoint.sh`**

- [ ] **Step 2: Wait for matrix CI green, merge**

Bumper fires; **STILL hold the bump** in frank until Phase 4 lands. Bundling kali + vk-local in one cutover is cleaner than two consecutive bounces.

---

## Phase 4: `vk-local` entrypoint wrapper [agentic]
**Target repo:** `derio-net/agent-images`
**Depends on:** Phase 1

<!-- Tracking: Add wrapper that runs /opt/agent-init.d/* before exec'ing vibe-kanban. No s6, no supervisor — vibe-kanban stays the driver process under tini's PID 1. -->

Minimal change: vk-local gains shared first-boot setup consistency; doesn't gain s6 (would invert K8s health contract for the driver process).

### Task 1: Add `vk-local/entrypoint-vk-local.sh`

- [ ] **Step 1: Thin wrapper script**

```bash
#!/bin/sh
# entrypoint-vk-local.sh — Run shared first-boot scripts, then exec vibe-kanban.
# vibe-kanban remains the driver process under tini's PID 1; K8s supervises.
set -e

shopt -s nullglob 2>/dev/null || true
for s in /opt/agent-init.d/*; do
    [ -x "$s" ] && "$s"
done

exec vibe-kanban "$@"
```

### Task 2: Update `vk-local/Dockerfile`

- [ ] **Step 1: Add wrapper, set ENTRYPOINT through tini**

```dockerfile
# (existing FROM agent-base + COPY of vibe-kanban binary, etc.)

COPY entrypoint-vk-local.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
```

### Task 3: Smoke test vk-local

- [ ] **Step 1: Build + run + verify vibe-kanban starts and serves /api/health**

```bash
docker build -t vk-local:test --build-arg BASE_SHA=$(git rev-parse HEAD) ./vk-local
docker run -d --name vk-test \
    --user 1000 \
    -v $(pwd)/test-home:/home/claude \
    -p 8081:8081 \
    -e PORT=8081 -e HOST=0.0.0.0 \
    vk-local:test

sleep 5
curl -fsS http://127.0.0.1:8081/api/health   # 200 OK
docker exec vk-test ls /home/claude/repos    # dir exists (created by 01-pvc-dirs)
docker rm -f vk-test
```

### Task 4: Open PR + merge

- [ ] **Step 1: Open PR `feat(vk-local): wrapper runs /opt/agent-init.d/* before vibe-kanban`**

- [ ] **Step 2: Wait for matrix CI green, merge**

Bumper accumulates 4 changes (Phases 1-4). Either let it open one combined bump PR, or open one explicitly with all SHAs. Hold the bump merge until Phase 5 lands (notifications must exist before the cutover so we get the alert).

---

## Phase 5: Deploy ArgoCD Notifications + Telegram template [agentic]
**Target repo:** `derio-net/frank`
**Depends on:** —

<!-- Tracking: Independent of agent-images work; can land in parallel. Must exist before Phase 7's annotations have anything to subscribe to. -->

Cluster-side wiring for the bump alert. Two new ArgoCD Applications + ESO secret.

### Task 1: Enable notifications in argocd Helm values

- [ ] **Step 1: Edit `apps/argocd/values.yaml`**

```yaml
notifications:
  enabled: true
```

Verify the chart version supports this; current frank argocd is on argo-cd Helm chart 5.x or 6.x — both support the notifications subchart.

### Task 2: Create `apps/argocd-notifications/manifests/configmap.yaml`

- [ ] **Step 1: Telegram service + triggers + templates**

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

### Task 3: Create `apps/argocd-notifications/manifests/externalsecret.yaml`

- [ ] **Step 1: Pull Telegram credentials from Infisical via ESO**

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: argocd-notifications-secret
  namespace: argocd
spec:
  refreshInterval: 1m
  secretStoreRef:
    name: infisical-clustersecretstore
    kind: ClusterSecretStore
  target:
    name: argocd-notifications-secret
    creationPolicy: Owner
  data:
    - secretKey: telegram-token
      remoteRef:
        key: FRANK_C2_TELEGRAM_BOT_TOKEN
    - secretKey: telegram-chat-id
      remoteRef:
        key: FRANK_C2_TELEGRAM_CHAT_ID
```

### Task 4: Add Application CR to `apps/root/templates/argocd-notifications.yaml`

- [ ] **Step 1: Wire it into the App-of-Apps**

Single source pointing at `apps/argocd-notifications/manifests/`, ServerSideApply, prune false, selfHeal true. Match the pattern in existing root templates.

### Task 5: Push, sync, verify controller starts

- [ ] **Step 1: Push the branch + open PR + merge**

- [ ] **Step 2: Sync and verify**

```bash
argocd app sync argocd-notifications --port-forward --port-forward-namespace argocd
kubectl -n argocd get pods -l app.kubernetes.io/name=argocd-notifications-controller
```

Expected: controller pod runs.

- [ ] **Step 3: Verify the secret resolves**

```bash
kubectl -n argocd get secret argocd-notifications-secret -o jsonpath='{.data}' \
  | python3 -c "import json,sys,base64; d=json.load(sys.stdin); [print(f'{k}: {len(base64.b64decode(v))} bytes') for k,v in d.items()]"
```

Expected: `telegram-token: <some bytes>`, `telegram-chat-id: <some bytes>`.

### Task 6: Test with a benign trigger

- [ ] **Step 1: Annotate any test app temporarily, force a sync, observe Telegram**

```bash
kubectl -n argocd annotate app homepage \
    notifications.argoproj.io/subscribe.on-sync-running.telegram="" --overwrite
argocd app sync homepage --port-forward --port-forward-namespace argocd
```

Expected: Telegram message arrives. Remove the annotation:

```bash
kubectl -n argocd annotate app homepage \
    notifications.argoproj.io/subscribe.on-sync-running.telegram- --overwrite
```

---

## Phase 6: Image bump cutover [manual]
**Target repo:** `derio-net/frank`
**Depends on:** Phase 3, Phase 4

<!-- Tracking: Wait for Phases 1-4 to land in agent-images, merge bumper PR in frank. Manual: requires operator confirmation that cutover landed cleanly before proceeding to Phase 7. -->

The disruptive moment. Pod restarts onto the new s6-based image. Operator must manually re-spawn mosh and verify behavior.

### Task 1: Confirm Phases 1-4 are merged in agent-images

- [ ] **Step 1: Check agent-images main has all four PRs**

```bash
cd ~/path/to/agent-images
git log --oneline -10 origin/main | grep -E "agent-init.d|agent-shell-base|migrate to agent-shell-base|vk-local.*wrapper"
```

Expected: 4 commits.

### Task 2: Merge the accumulated bumper PR in frank

- [ ] **Step 1: Identify the bump PR**

```bash
gh pr list --repo derio-net/frank --label vk-ready --search "bump agent-images"
```

There may be multiple if Phases 1-4 each fired the bumper. The latest one supersedes earlier ones; close the older ones.

- [ ] **Step 2: Merge the latest bump PR**

```bash
gh pr merge <PR_NUMBER> --repo derio-net/frank --squash
```

### Task 3: Observe the rollout

- [ ] **Step 1: Watch ArgoCD sync + pod recreation**

```bash
argocd app get secure-agent-pod --port-forward --port-forward-namespace argocd
kubectl -n secure-agent-pod get pods -w
```

Expected: old pod terminates, new pod creates with the new image SHAs (kali + vk-local). Recreate strategy means ~30s of downtime.

Note: this first cutover happens *without* the agent-pod-specific Telegram alert because Phase 7's subscription annotations haven't been added yet. The Phase 5 Task 6 test left no permanent subscription.

### Task 4: Re-spawn mosh + verify pod-side state

- [ ] **Step 1: Cmd+Shift+2 in WezTerm**

A fresh mosh session attaches to a fresh tmux server. tmux-continuum auto-restore fires; on first cutover there's no prior layout to restore.

- [ ] **Step 2: Verify s6 + services**

```bash
ssh claude@192.168.55.215 'ps -ef | head -20'
# PID 1 should be /init (s6); s6-rc supervisors visible.

ssh claude@192.168.55.215 's6-svstat /run/service/sshd /run/service/supercronic'
# Expected: both up

ssh claude@192.168.55.215 'tmux -V; mosh-server --version | head -1'
# Expected: tmux 3.6, mosh-server 1.4.x

ssh claude@192.168.55.215 'ls /usr/local/share/tmux-plugins/'
# Expected: tmux-resurrect/, tmux-continuum/

ssh claude@192.168.55.215 'cat ~/.tmux.conf | tail -5'
# Should contain `source-file /etc/agent/tmux-resurrect.conf`.
# IF MISSING: existing PR #127-deposited ~/.tmux.conf overrode /etc/skel.
# Append the line manually once: echo 'source-file /etc/agent/tmux-resurrect.conf' >> ~/.tmux.conf
# Then `tmux source ~/.tmux.conf` to load the plugins in the running server.
```

### Task 5: Smoke test in-pod resilience

- [ ] **Step 1: Kill supercronic, observe respawn**

```bash
ssh claude@192.168.55.215 'pkill supercronic'
sleep 3
ssh claude@192.168.55.215 'pgrep -af supercronic'
# Expected: supercronic running with low elapsed time
```

mosh+tmux session uninterrupted (no container restart).

- [ ] **Step 2: Confirm no historical regressions**

Open a tmux session, split panes, attach `claude` REPL, type a message, observe everything works as before.

---

## Phase 7: Drop preStop, add notification annotations [agentic]
**Target repo:** `derio-net/frank`
**Depends on:** Phase 5, Phase 6

<!-- Tracking: Manifest changes that complete the resilience picture. -->

### Task 1: Remove `lifecycle.preStop` from deployment.yaml

- [ ] **Step 1: Edit `apps/secure-agent-pod/manifests/deployment.yaml`**

Delete the entire `lifecycle:` block from the kali container spec. cont-finish.d/01-shutdown now handles the same shutdown.sh call, with the bonus that cont-finish.d/02-tmux-save runs after.

### Task 2: Add notification subscription annotations to the Application CR

- [ ] **Step 1: Edit `apps/root/templates/secure-agent-pod.yaml`**

Add to the Application CR's `metadata.annotations`:

```yaml
notifications.argoproj.io/subscribe.on-sync-running.telegram: ""
notifications.argoproj.io/subscribe.on-sync-succeeded.telegram: ""
```

### Task 3: Open PR + merge

- [ ] **Step 1: Open PR `feat(agents): drop preStop, subscribe to ArgoCD bump alerts`**

- [ ] **Step 2: Merge after CI green**

ArgoCD syncs the Application change. Telegram fires (`on-sync-running` then `on-sync-succeeded`) — this is the **second cutover**, the first one with the heads-up. Pod recreates because the deployment.yaml change applies.

### Task 4: Re-spawn mosh + verify Telegram fired

- [ ] **Step 1: Cmd+Shift+2**

- [ ] **Step 2: Confirm Telegram alert arrived for this sync**

If alert is missing, check `argocd-notifications-controller` logs for delivery errors. Typical issues: bot token misconfigured (rare), chat ID typo, template parse error.

---

## Phase 8: End-to-end verification [manual]
**Target repo:** n/a
**Depends on:** Phase 7

<!-- Tracking: Exercise the full restart resilience story before declaring success. -->

### Task 1: Layout persistence across an image bump

- [ ] **Step 1: Set up a test layout**

In the frank workspace:
- Split tmux into 4 panes
- Each pane has a different cwd: `~/repos/agent-images`, `~/repos/frank`, `/tmp`, `~/.willikins-agent`
- One pane runs `vim /tmp/test.txt` with some unsaved content

- [ ] **Step 2: Wait 6 minutes**

Continuum auto-saves every 5 min; 6 min ensures at least one save fired.

- [ ] **Step 3: Trigger a pod restart**

```bash
kubectl -n secure-agent-pod delete pod -l app=secure-agent-pod
```

Telegram alert fires.

- [ ] **Step 4: Re-spawn mosh, observe restoration**

Cmd+Shift+2. After mosh handshakes and tmux server starts, tmux-continuum auto-restore fires. **Expected:** 4 panes back, cwds correct. **Lost:** vim's unsaved content (process is gone).

### Task 2: Crashloop bail

- [ ] **Step 1: Break supercronic and observe bail-out**

```bash
ssh claude@192.168.55.215
mv /usr/local/bin/supercronic /usr/local/bin/supercronic.broken   # or via kubectl exec
for i in 1 2 3 4 5 6; do pkill -KILL supercronic 2>/dev/null; sleep 0.5; done
sleep 10
s6-svstat /run/service/supercronic   # down
s6-svstat /run/service/sshd          # still up
```

- [ ] **Step 2: Restore supercronic and recover**

```bash
mv /usr/local/bin/supercronic.broken /usr/local/bin/supercronic
s6-svc -u /run/service/supercronic
sleep 2
s6-svstat /run/service/supercronic   # up
```

mosh+tmux session uninterrupted throughout.

### Task 3: Independent service deaths

- [ ] **Step 1: Kill sshd, observe readinessProbe failure + recovery**

```bash
ssh claude@192.168.55.215 'pkill sshd'
# SSH session drops. readinessProbe trips within ~30s.
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod
# Expected: READY 1/2 briefly
# s6 respawns sshd within 1-2s.
ssh claude@192.168.55.215 's6-svstat /run/service/sshd'   # up
kubectl -n secure-agent-pod get pod -l app=secure-agent-pod
# Expected: READY 2/2 again after probe cycle
```

### Task 4: Bump alert end-to-end

- [ ] **Step 1: Trigger a sync (real or simulated)**

```bash
kubectl -n argocd annotate app secure-agent-pod \
    test-trigger="$(date)" --overwrite
```

- [ ] **Step 2: Confirm Telegram alert content matches the template**

App name, from-revision, to-revision, the "mosh sessions will need re-spawn" line. If anything is off, edit `apps/argocd-notifications/manifests/configmap.yaml` and re-sync.

### Task 5: Document learned gotchas

- [ ] **Step 1: For any quirk encountered (s6 non-root edge cases, tmux save timing, ESO refresh latency), append to `.claude/rules/frank-gotchas.md`**

Even small edge-case findings belong here so the next operator has the context.

---

## Phase 9: Post-deploy documentation [agentic]
**Target repo:** `derio-net/frank`
**Depends on:** Phase 8

<!-- Tracking: Update existing layer docs (operating + building posts), README, gotchas. Per fix/extension rules, no new blog posts. -->

### Task 1: Update operating post

- [ ] **Step 1: Add an "Architecture: s6-overlay" section to `blog/content/docs/operating/14-secure-agent-pod/index.md`**

Cover: PID 1 is `/init`; cont-init.d/services.d/cont-finish.d roles; how to inspect with `s6-svstat /run/service/<name>`; how to restart a service (`s6-svc -t /run/service/<name>` then it auto-respawns); the bail policy.

- [ ] **Step 2: Update the "Persistent shells with mosh + tmux" section**

Add a paragraph about tmux-continuum auto-restore: "After a mosh re-spawn (Cmd+Shift+2), the new tmux server attaches to your saved layout — pane structure and cwds restored from the last save (≤5 min before the restart). Running processes are not restored; re-launch them yourself."

- [ ] **Step 3: Update the "What 'Healthy' Looks Like" process list**

Replace the `wait -n`-era process list with the s6-aware view: PID 1 = `/init`, services seen via `s6-svstat`, plus the supercronic-spawned children (claude session-manager, vk-bridge.py).

### Task 2: Update building post

- [ ] **Step 1: Update the "Architecture" section in `blog/content/docs/building/21-secure-agent-pod/index.md`**

Reflect the three-tier base lineage: agent-base → agent-shell-base → secure-agent-kali. Note that s6-overlay supervises sshd + supercronic independently, that crashloop bail-out is configured, and that kali keeps `claude`/`/home/claude` via build-arg parameterization (with a forward-link to "the rename plan").

- [ ] **Step 2: Update the "Process Supervision" section**

Replace the `wait -n` description with the s6-overlay model. Explain why this matters (the 23:27 SIGHUP incident). Link to the spec.

### Task 3: Update README

- [ ] **Step 1: Update Technology Stack row for Secure Agent Pod**

Mention s6-overlay-supervised + tmux-continuum-restored in the description.

- [ ] **Step 2: Add ArgoCD Notifications row to Technology Stack**

```markdown
| ArgoCD Notifications | Native ArgoCD subsystem | Telegram alerts on agent-pod sync events (image bumps, manual rollouts) — operator gets ~30s heads-up before mosh sessions die |
```

### Task 4: Update gotchas

- [ ] **Step 1: Add to `.claude/rules/frank-gotchas.md`**

```markdown
- **s6-overlay v3 in non-root mode requires `S6_KEEP_ENV=1` and `S6_VERBOSITY=2`** — without these, services don't inherit the container env. The `with-contenv` wrapper around cont-init.d / services.d scripts is also required for them to see `$AGENT_HOME`.
- **agent-shell-base parameterizes user via `AGENT_USER` / `AGENT_HOME` build args** (defaults `agent`/`/home/agent`). secure-agent-kali overrides to `claude`/`/home/claude` to preserve PV-resident state. New shell-driven children inherit defaults.
- **tmux-continuum auto-restore only fires when tmux server starts fresh** — `tmux source ~/.tmux.conf` in a running server reloads plugins but does not trigger restore. Auto-restore = fresh server start.
- **/etc/skel/.tmux.conf only seeds on first boot of a fresh PV** — existing PVs (like secure-agent-kali's) keep their existing ~/.tmux.conf. To pick up the resurrect/continuum line, append `source-file /etc/agent/tmux-resurrect.conf` manually once.
- **s6 crashloop bail (5 deaths in 60s) leaves the service down without a Telegram alert** — sshd-down is visible via K8s readinessProbe (pod removed from LB); supercronic-down is only visible in `s6-svstat`. Future enhancement: alert on bail.
```

### Task 5: Set plan status

- [ ] **Step 1: Edit `**Status:**` to `Deployed`**

Once all phases passed verification.

### Task 6: Sync runbook

- [ ] **Step 1: Run `/sync-runbook`**

This plan has no `# manual-operation` blocks (all steps documented inline; no SOPS/UI-only operations). Expected: zero diff.

---

## Out of scope (deliberately)

Per spec — repeated here for plan-level clarity:

- secure-agent-kali rename to `agent`/`/home/agent` — separate plan, scheduled when convenient
- Tmux usage inside vk-local — VK-side decision
- Per-pod egress profiles for new shell pods — per-pod plans
- Generalized `spawn_agent_workspace(name)` in wezterm.lua — when second shell pod arrives
- Telegram alerts on s6 crashloop bail-out — bolt-on if real ops show value
- Service dependencies (s6-rc) for credential-mount-ready ordering — when it's needed
- CRIU process checkpointing — not viable
