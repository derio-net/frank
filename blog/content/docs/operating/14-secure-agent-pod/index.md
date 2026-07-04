---
title: "Operating on Secure Agent Pod"
series: ["operating"]
layer: agents
date: 2026-03-31
draft: false
tags: ["operations", "security", "agent", "claude", "ssh", "vibekanban", "cilium", "cron", "telegram", "monitoring"]
summary: "Day-to-day commands for managing the secure agent pod — SSH access, process health, VibeKanban, secret rotation, and troubleshooting."
weight: 15
---

This is the operational companion to [Secure Agent Pod — Hardening an AI Coding Workstation]({{< relref "/docs/building/21-secure-agent-pod" >}}). That post explains the architecture and security model. This one is the day-to-day runbook.

## What "Healthy" Looks Like

A healthy secure-agent-pod has:
- One pod running (`2/2 Ready`) on gpu-1 — `kali` + `vk-local` sidecar
- PID 1 in `kali` is `/init` (s6-overlay), supervising sshd and supercronic
- SSH accessible at `192.168.55.215:22`
- mosh accessible on UDP `192.168.55.219:60000-60015`
- VibeKanban UI accessible at `192.168.55.218:8081` (served by the `vk-local` sidecar)
- All running as UID 1000 (`claude`), no root

## Observing State

### Pod Health

```bash
# Pod status
kubectl -n secure-agent-pod get pods -o wide

# Detailed events and conditions
kubectl -n secure-agent-pod describe pod -l app=secure-agent-pod

# Container identity
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- id
# Expected: uid=1000(claude) gid=1000(claude) groups=1000(claude)
```

### Process Health

The `kali` container runs s6-overlay as PID 1. Two long-running services are supervised — `sshd` and `supercronic` — and the cron schedule plus user shell sessions spawn additional children (claude session-manager, vk-bridge.py, mosh-server, tmux, etc.). The VibeKanban server itself runs in the **`vk-local` sidecar** container, not in `kali`.

```bash
# Service status (the supervised long-runners)
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- s6-svstat /run/service/sshd /run/service/supercronic
# Expected: both `up` with high uptime

# Full process tree
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- ps -ef
```

Expected top of the tree (`N`/`M`/`P`/`Q`/`R` are placeholder PIDs that vary per boot):

```
UID   PID  PPID CMD
1000    1     0 /package/admin/s6-overlay/.../bin/s6-svscan -d4 -- /run/service
1000    N    1  s6-supervise sshd
1000    M    N  /usr/sbin/sshd -f /opt/sshd_config -D
1000    P    1  s6-supervise supercronic
1000    Q    P  supercronic /home/claude/.crontab
1000    R    Q  /opt/scripts/session-manager.sh   # spawned by supercronic on schedule
…        many more shell/mosh/tmux/claude children attached to the user's interactive sessions
```

If a service dies, s6 respawns it within ~1s (per its `services.d/<name>/run` script). Five deaths within 60s trip the crashloop bail (see "Architecture: s6-overlay" below) and the service stays down without taking the pod with it. The K8s readinessProbe (TCP on port 2222) catches the **sshd**-down case — the pod is removed from the LB. Supercronic-down has no probe, so check `s6-svstat` if cron jobs go quiet.

The `vk-local` sidecar runs vibe-kanban directly with tini as PID 1; check it with:

```bash
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c vk-local -- ps -ef
```

### Services and Networking

```bash
# Verify LoadBalancer IPs
kubectl -n secure-agent-pod get svc

# SSH connectivity
ssh -o ConnectTimeout=5 claude@192.168.55.215 echo "SSH works"

# VibeKanban health
curl -s -o /dev/null -w "%{http_code}" http://192.168.55.218:8081
# Expected: 200
```

### ArgoCD Sync Status

```bash
argocd app get secure-agent-pod --port-forward --port-forward-namespace argocd
```

## Architecture: s6-overlay

The `kali` container is built from `agent-shell-base`, which uses [s6-overlay v3](https://github.com/just-containers/s6-overlay) as PID 1 (`/init`). s6 splits a container's life into three stages, mapped to directories baked into the image:

| Directory | Stage | Purpose |
|-----------|-------|---------|
| `/etc/cont-init.d/` | One-shot setup | Runs in lexical order at boot. Blocks until done. SSH host keys, authorized_keys seeding, venv setup. |
| `/etc/services.d/<name>/` | Long-running | Each subdir is a supervised service. `run` is exec'd; if it exits, s6 respawns it (within the crashloop policy). |
| `/etc/cont-finish.d/` | Teardown | Runs in lexical order on SIGTERM. `01-shutdown` calls `/opt/scripts/shutdown.sh`; `02-tmux-save` forces a final tmux-continuum save. |

The two supervised services are `sshd` (port 2222) and `supercronic` (cron). `vibe-kanban` is **not** an s6 service in this pod — it lives in the `vk-local` sidecar, which uses tini as PID 1.

### Inspecting and controlling services

```bash
# Status (up/down + uptime + PID)
ssh claude@192.168.55.215 's6-svstat /run/service/sshd /run/service/supercronic'

# Restart a service (sends SIGTERM; s6 respawns it)
ssh claude@192.168.55.215 's6-svc -t /run/service/supercronic'

# Bring a service down on purpose (won't auto-respawn until you bring it back up)
ssh claude@192.168.55.215 's6-svc -d /run/service/supercronic'

# Bring it back up
ssh claude@192.168.55.215 's6-svc -u /run/service/supercronic'
```

### Crashloop bail policy

s6 respawns a dying service immediately. If a service dies **5 times within 60 seconds**, s6 bails out and stops respawning that service. Other services keep running; the pod stays alive.

This catches truly broken services (binary missing, config corrupt) without panicking on transient flaps:

| Failure mode | s6 response | Externally visible? |
|--------------|-------------|---------------------|
| One transient flap (e.g., a stray SIGHUP) | Respawn within ~1s | No — pod stays Ready, mosh+tmux uninterrupted |
| 5 deaths within 60s | Stop respawning that service; leave it down | sshd-down: TCP readinessProbe trips, pod removed from LB. supercronic-down: only `s6-svstat` shows it; cron jobs stop firing |
| Sustained dying > 60s | Same — counter window slides; service can recover when it stops dying | Same |

To recover from a bail-out, fix the underlying cause and bring the service back with `s6-svc -u /run/service/<name>`.

### Why not just `wait -n`?

The original entrypoint was a single `bash -c '… & … & wait -n'`. That worked, but a single SIGHUP to the in-pod claude session manager could propagate to the whole pgroup, kill supercronic, and through `wait -n` exit the container — taking the SSH session, mosh server, and tmux layout with it. s6's process supervision is signal-isolated per service; a misbehaving cron child can't drag down sshd.

The 23:27 SIGHUP incident on 2026-04-26 (claude session-manager → supercronic → entire container) is what motivated the s6 migration; see the [building post]({{< relref "/docs/building/21-secure-agent-pod" >}}#process-supervision) and the [restart-resilience spec](https://github.com/derio-net/frank/blob/main/docs/superpowers/specs/2026-04-27--agents--restart-resilience-design.md).

## SSH Access

### Connecting

```bash
# Standard SSH
ssh claude@192.168.55.215

# With specific key
ssh -i ~/.ssh/id_rsa claude@192.168.55.215
```

The Service maps external port 22 → internal port 2222 (non-root sshd). SSH clients don't need to specify a port.

### Updating Authorized Keys

The SSH authorized keys come from a Kubernetes Secret:

```bash
# View current keys
kubectl get secret agent-ssh-keys -n secure-agent-pod -o jsonpath='{.data.authorized_keys}' | base64 -d

# Replace with a new key
kubectl create secret generic agent-ssh-keys \
  --namespace=secure-agent-pod \
  --from-file=authorized_keys=~/.ssh/id_rsa.pub \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart pod to pick up the new key
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

The entrypoint copies authorized_keys from the Secret mount to `~/.ssh/authorized_keys` on each boot.

### SSH Host Key Changed Warning

If you see "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED", the PVC was recreated (host keys regenerated):

```bash
ssh-keygen -R 192.168.55.215
ssh claude@192.168.55.215
```

## Persistent Shells with mosh + tmux

`mosh` keeps the connection alive across IP changes and laptop suspend; `tmux` keeps the *server-side* shells alive across mosh restarts. Together they make a long-running coding session that doesn't lose its place when you close the lid.

**Layout survives pod restarts.** `agent-shell-base` ships with `tmux-resurrect` and `tmux-continuum` baked in at `/usr/local/share/tmux-plugins/`, with `/etc/skel/.tmux.conf` enabling a 5-minute auto-save and auto-restore on tmux server start. After a mosh re-spawn (Cmd+Shift+2 in WezTerm), the new tmux server attaches to your saved layout — pane structure and cwds restored from the last save (≤5 min before the restart). Running processes are not restored; re-launch them yourself. The pre-stop save in `cont-finish.d/02-tmux-save` forces a final continuum snapshot during graceful shutdown, so an announced bump (image rollout, manual rollout) doesn't cost the work you did in the last 5 minutes — only an unannounced kill (OOM, node loss) falls back to the last 5-minute auto-save.

### Why SSH and UDP are on separate IPs

The pod is fronted by **two distinct Cilium L2 LoadBalancer IPs**:

| Service | IP | Protocol | Purpose |
|---------|-----|----------|---------|
| `secure-agent-ssh` | `192.168.55.215` | TCP/22 → 2222 | SSH bootstrap + interactive sessions |
| `secure-agent-mosh` | `192.168.55.219` | UDP/60000-60015 | mosh datagram channel |

Cilium L2 LB IPs are not shared between Services unless you opt in via `lbipam.cilium.io/sharing-key` annotation, and we deliberately did **not** opt in (Deployment Deviation #4 — the operator preferred the explicit two-IP model over editing both Services in lockstep). The cost: the mosh client invocation needs explicit `--ssh=…` plus the UDP positional, instead of the standard `mosh user@host` form.

### Canonical mosh invocation

```bash
export MOSH_SSH_PROXY='nc 192.168.55.215 22'
SHELL=/bin/sh mosh --experimental-remote-ip=local \
  --ssh='ssh -l claude -i ~/.ssh/your_private_key \
         -o ControlMaster=no -o ControlPath=none -o ControlPersist=no \
         -o ProxyCommand=$MOSH_SSH_PROXY' \
  --server='LC_ALL=C.UTF-8 mosh-server new -p 60000:60015' \
  192.168.55.219 -- \
  tmux new-session -A -s claude-frank-secure-pod
```

Every flag here is structurally load-bearing — none of them are "tries until it works." See the [plan appendix]({{< relref "/docs/building/21-secure-agent-pod" >}}) (linked from the building post) for the per-flag rationale; the short version of the most surprising ones:

- **`MOSH_SSH_PROXY` env-var indirection** — `mosh.pl` splits `--ssh=` on whitespace, so a multi-word `ProxyCommand` value has to live in a single token.
- **`-o ProxyCommand=` not `-o HostName=`** — `HostName=` poisons `ssh -G`, which mosh reads for the UDP target; ProxyCommand is invisible to it.
- **`--experimental-remote-ip=local`** — `proxy` mode needs ProxyCommand peer info that `nc` doesn't expose; `remote` mode returns the pod's internal `10.244.x.x` cluster IP.
- **`SHELL=/bin/sh`** — macOS `$SHELL=/bin/zsh`, and zsh doesn't word-split unquoted variable expansions, so `$MOSH_SSH_PROXY` ends up as one literal command name. /bin/sh word-splits.
- **The `ControlMaster/ControlPath/ControlPersist=no` triple** — OpenSSH 10.2+'s auto-mux discovery ignores `ControlPath=none` for *existing* masters; only all three together force a fresh, unmultiplexed connection.

### Port range

The mosh Service publishes 16 UDP ports (`60000-60015`). The matching `mosh-server new -p 60000:60015` constraint on the server side ensures every spawned server lands on a published port — without it, mosh-server picks uniformly from `60000-61000` and you get a ~1.6% hit rate against the published range.

The 16-port cap is sized for ~16 simultaneous stuck sessions before reuse pressure kicks in (mosh-server defaults to a 7-day idle timeout, but we override it via `MOSH_SERVER_NETWORK_TMOUT=3600` in the deployment env — sessions garbage-collect after 1h of silence).

### tmux on the pod

The pod's home directory is on a PVC, so `~/.tmux.conf` survives pod restarts. The canonical configs (matching the operator's laptop) are committed in `apps/secure-agent-pod/client-setup/pod/`. The starter is just enough to make tmux feel like home:

```bash
# /home/claude/.tmux.conf — minimum
set -g default-terminal "tmux-256color"
set -g mouse on
set -g history-limit 100000
set -g status-right "#{?client_prefix,#[bg=red,bold] PREFIX ,}#H:#M"

bind | split-window -h \; select-layout even-horizontal
bind S split-window -v \; select-layout even-vertical
bind r source-file ~/.tmux.conf \; display "reloaded"
```

The `client_prefix` indicator in `status-right` is a critical debugging aid: a red `PREFIX` badge appears the instant `C-b` is pressed and disappears as soon as the next key fires. Without it, "is tmux even seeing my keypress?" becomes guesswork.

For the full config (per-pane bg coloring by cwd, 6-pane grid bindings, the chpwd hook), see `apps/secure-agent-pod/client-setup/`. That directory's README covers both laptop and pod installation.

### Verifying mosh + tmux are present

```bash
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- sh -c 'tmux -V; mosh-server --version | head -1; echo "$LANG/$LC_ALL"'
# Expected:
#   tmux 3.6
#   mosh-server (mosh 1.4.0) [build mosh-1.4.0]
#   C.UTF-8/C.UTF-8
```

### Re-spawning a stuck mosh session

When the pod restarts (image bump, OOM, in-pod agent error), `mosh-server` dies with the container. The local mosh client can't tell — the WezTerm pane keeps showing the prediction cache and stops responding to input. SSH-based tools (VS Code Remote, `ssh` directly) auto-reconnect because sshd respawns; mosh has no equivalent.

The committed `wezterm.lua` (in `apps/secure-agent-pod/client-setup/laptop/`) binds **`Cmd+Shift+2`** to re-spawn the `frank` workspace: it opens a fresh window with a new mosh invocation and switches to it. The dead window stays visible until you close it (`Cmd+W`), but the new one connects cleanly. **`Cmd+Shift+1`** does the same for the `local` workspace.

```text
Cmd+1         switch to local workspace
Cmd+2         switch to frank workspace
Cmd+Shift+1   re-spawn local workspace (fresh tmux attach)
Cmd+Shift+2   re-spawn frank workspace (fresh mosh + tmux attach)
```

If you've quit the dead pane via mosh's `Ctrl-^ .` escape, you don't need to restart WezTerm — just `Cmd+Shift+2`.

### Troubleshooting

If a fresh mosh connect fails, the most diagnostic single artifact is the wezterm log (when launched via the operator's WezTerm wrapper):

```bash
tail -f /tmp/wezterm-mosh.log
```

The plan's [Appendix: Client-Side Configuration & Debug Journey](https://github.com/derio-net/frank/blob/main/docs/superpowers/archived-plans/2026-04-26--agents--secure-pod-tmux-mosh.md#appendix-client-side-configuration--debug-journey) walks through the ten distinct failure modes seen during the first end-to-end connect, with the exact error message and structural cause for each. If your symptom looks like one of those, the cause almost certainly is too — the boundaries between OpenSSH, mosh.pl, tmux, the macOS terminal, and zsh don't move quickly.

## VibeKanban

### Accessing the UI

VibeKanban runs on port 8081, exposed via LoadBalancer at `192.168.55.218`:

```
http://192.168.55.218:8081
```

Access via Tailscale/Headscale mesh or direct LAN. First login uses VibeKanban's built-in local auth.

### Configuration

VibeKanban stores its SQLite database and binary cache on the PVC:

```
/home/claude/.vibe-kanban/     # Binary cache + SQLite DB
/home/claude/repos/            # Git workspaces managed by VibeKanban
```

Key environment variables (set in the Deployment manifest):

| Variable | Value | Purpose |
|----------|-------|---------|
| `PORT` | `8081` | Fixed server port (default is random) |
| `HOST` | `0.0.0.0` | Listen on all interfaces (default is 127.0.0.1) |

### Checking VibeKanban Logs

VibeKanban runs in the `vk-local` sidecar — its logs are scoped to that container, not `kali`:

```bash
# VibeKanban server logs
kubectl logs -n secure-agent-pod deploy/secure-agent-pod -c vk-local

# Follow logs
kubectl logs -n secure-agent-pod deploy/secure-agent-pod -c vk-local -f

# Filter
kubectl logs -n secure-agent-pod deploy/secure-agent-pod -c vk-local | grep -E "server|INFO|WARN|ERROR"
```

For sshd / supercronic / cron-spawned agent activity, swap `-c vk-local` for `-c kali`. s6-overlay routes each supervised service's stdout/stderr to its own logger, so `kubectl logs -c kali` shows the merged stream from `/init`, `s6-supervise`, sshd, and supercronic.

## Secret Management

### Tier 1: Infisical (ESO)

Currently no active Tier 1 secrets (Claude Code uses Max subscription login). When needed:

1. Add the secret to Infisical
2. Create/update the ExternalSecret manifest at `apps/secure-agent-pod/manifests/externalsecret.yaml`
3. Commit and push — ArgoCD syncs, ESO creates the K8s Secret
4. Restart the pod to pick up new env vars

### Tier 2: Manual Secrets

```bash
# View current tier-2 secrets
kubectl get secret agent-secrets-tier2 -n secure-agent-pod -o jsonpath='{.data}' | python3 -c "import json,sys,base64; d=json.load(sys.stdin); [print(f'{k}: {base64.b64decode(v).decode()[:20]}...') for k,v in d.items()]"

# Update a secret value
kubectl patch secret agent-secrets-tier2 -n secure-agent-pod \
  --type merge -p '{"stringData":{"TELEGRAM_BOT_TOKEN":"new-token-here"}}'

# Restart to pick up changes
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

> GitHub auth is **not** a tier-2 secret anymore — it's a rotating App
> installation token (next section). Don't put a `GITHUB_TOKEN` here.

### GitHub authentication: App installation token (git + gh)

The agent authenticates to GitHub with a **rotating GitHub App installation
token** (App `derio-fr-automation`), not a PAT. ESO's `GithubAccessToken`
generator mints a ~1 h token into the `agent-github-token` Secret, mounted
live-updated at `/var/run/github/token`; the App **private key never touches the
pod**. Two shims read that file: the `~/.gitconfig` credential helper (git) and
the `/usr/local/bin/gh` wrapper (gh). This replaced the old org-owner PAT.

```bash
# Is ESO minting?  (want READY=True)
kubectl -n secure-agent-pod get externalsecret agent-github-token

# In-pod: token present + git/gh auth. Verify against a PRIVATE repo — public
# repos auth with no token and give a false pass.
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- bash -lc '
  wc -c < /var/run/github/token
  git ls-remote https://github.com/derio-net/willikins HEAD >/dev/null && echo git-OK
  gh api graphql -f query="{repository(owner:\"derio-net\",name:\"willikins\"){name}}" >/dev/null && echo gh-OK'
```

To grant access to a new repo, add it to the App's install (org → Developer
settings → GitHub Apps → `derio-fr-automation` → repository access); the next ESO
refresh (≤45 m) mints a token covering it. `gh auth status` calling the token
"invalid" is **expected** — App installation tokens have no user identity, but
repo/issue/PR/GraphQL ops still work. If git/gh fail after a token or identity
change, see the credential-helper + gh-wrapper gotchas in
[`docs/runbooks/frank-gotchas/agent-shells.md`](https://github.com/derio-net/frank/blob/main/docs/runbooks/frank-gotchas/agent-shells.md)
(the dash `$(cat)` rule, the `gh auth setup-git` host-override) and the live-patch
stopgap there.

### Config Files (talosconfig, kubeconfig, omniconfig)

Mounted at `/home/claude/.kube/configs/`:

```bash
# Verify configs are mounted
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- ls -la /home/claude/.kube/configs/

# Rotate configs
sops --decrypt secrets/secure-agent-pod/agent-configs.yaml | kubectl apply -f -
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

## Pod Lifecycle

### Restarting

```bash
# Graceful restart (new pod, then old pod terminates)
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod

# Force restart (immediate)
kubectl delete pod -l app=secure-agent-pod -n secure-agent-pod
```

Strategy is `Recreate` (RWO PVC), so there's always a brief downtime during restart.

### Checking PVC Data

```bash
# PVC status
kubectl get pvc -n secure-agent-pod

# What's on the PVC
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- du -sh /home/claude/*
```

### Image Updates

The deployment uses `ghcr.io/derio-net/secure-agent-kali:latest`. To pick up a new image:

```bash
# Force pull latest
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

For pinned SHA tags, update the `image:` field in `apps/secure-agent-pod/manifests/deployment.yaml` and push.

## Cron Jobs

Cron is managed by supercronic reading `/home/claude/.crontab`. The crontab template is seeded from the image on first boot; after that it's user-modifiable on the PVC.

Scripts live at `/opt/scripts/` — baked into the image, immutable. They update when the `secure-agent-kali` image is rebuilt and the pod is restarted.

```bash
# View current crontab
cat ~/.crontab

# View available scripts
ls /opt/scripts/
# audit-digest.sh      guardrails-hook.py  push-heartbeat.sh
# exercise-cron.sh     notify-telegram.sh  session-manager.sh

# Edit crontab (supercronic picks up changes automatically)
vi ~/.crontab
```

### Current Schedule

| Job | Schedule | Script |
|-----|----------|--------|
| Session manager | Every 5 min | `/opt/scripts/session-manager.sh` |
| Self-update (git pull) | Daily 04:00 UTC | inline |
| Claude Code update | Weekly Sun 04:30 UTC | inline |
| Exercise reminders | 5x daily, Fri-Mon | `/opt/scripts/exercise-cron.sh` |
| Audit digest | Daily 21:00 UTC | `/opt/scripts/audit-digest.sh` |

### Updating Scripts

Scripts at `/opt/scripts/` are read-only (from the image). To update them:

1. Commit changes to the `secure-agent-kali` repo
2. GHA rebuilds and pushes the image to GHCR
3. Restart the pod: `kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod`

The crontab on the PVC is independent — editing `~/.crontab` takes effect immediately via supercronic's file watcher.

## Health Monitoring

Each cron script pushes a heartbeat metric to Prometheus Pushgateway after successful execution:

```bash
# Check current heartbeat state
curl -s http://pushgateway.monitoring.svc.cluster.local:9091/api/v1/metrics | \
  python3 -c "
import json, sys
from datetime import datetime, timezone
for g in json.load(sys.stdin)['data']:
    job = g['labels'].get('job','?')
    ts = float(g['push_time_seconds']['metrics'][0]['value'])
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%H:%M:%S UTC')
    print(f'{job:30s} {dt}')
"
```

Grafana alert rules fire when heartbeats go stale:

| Alert | Threshold | Severity |
|-------|-----------|----------|
| `exercise-reminder-stale` | 3 hours | critical |
| `audit-digest-stale` | 26 hours | warning |
| `session-manager-stale` | 10 minutes | critical |

Alerts are bridged to GitHub Issues via the health-bridge webhook — the Quartermaster (Willikins staff) tracks these on the "Derio Ops" project board.

### Manually Pushing a Heartbeat

```bash
/opt/scripts/push-heartbeat.sh <job_name> [label=value ...]
# Example: /opt/scripts/push-heartbeat.sh exercise_reminder context=desk
```

## Cilium Egress Policy

**Current status:** Temporarily disabled due to Cilium 1.17 FQDN LRU bug.

The policy manifest is at `apps/secure-agent-pod/cilium-egress.yaml.disabled`. To re-enable:

```bash
# Move back to manifests directory
mv apps/secure-agent-pod/cilium-egress.yaml.disabled apps/secure-agent-pod/manifests/cilium-egress.yaml
git add -A && git commit -m "feat(agents): re-enable Cilium egress policy" && git push

# Verify policy status
kubectl get ciliumnetworkpolicy -n secure-agent-pod
# VALID column should be True
```

If the policy shows `VALID: False` with "LRU not yet initialized":

```bash
# Restart Cilium agent on gpu-1
kubectl delete pod -n kube-system -l k8s-app=cilium --field-selector spec.nodeName=gpu-1

# Wait for agent restart, then delete and reapply
kubectl delete ciliumnetworkpolicy agent-egress -n secure-agent-pod
kubectl apply -f apps/secure-agent-pod/manifests/cilium-egress.yaml

# Delete the pod to clear stale BPF state
kubectl delete pod -l app=secure-agent-pod -n secure-agent-pod
```

### Testing Egress (When Policy is Active)

```bash
# Should SUCCEED
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- \
  curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" https://api.anthropic.com/
# Expected: 404

# Should FAIL (blocked)
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- \
  curl -s --connect-timeout 5 https://httpbin.org/ip
# Expected: timeout
```

## Troubleshooting

### CrashLoopBackOff

Check which process died:

```bash
kubectl logs -n secure-agent-pod deploy/secure-agent-pod -c kali --previous
```

Common causes:
- **"Download failed"** — VibeKanban can't reach `npm-cdn.vibekanban.com` (Cilium blocking or DNS issue)
- **"No such file or directory: /entrypoint.sh"** — image didn't include the entrypoint (rebuild needed)
- **sshd fails** — check host key permissions (`chmod 600` on private keys, `chmod 700` on `.ssh-host-keys/`)

### Pod Stuck in CreateContainerConfigError

A referenced Secret doesn't exist:

```bash
kubectl describe pod -l app=secure-agent-pod -n secure-agent-pod | grep -A5 "Warning"
```

The `agent-secrets-tier1` and `agent-secrets-tier2` secretRefs are `optional: true`, so they won't block. But `agent-ssh-keys` is required — create it if missing:

```bash
kubectl create secret generic agent-ssh-keys \
  --namespace=secure-agent-pod \
  --from-file=authorized_keys=~/.ssh/id_rsa.pub
```

### Can't SSH In

1. **Check pod is running:** `kubectl get pods -n secure-agent-pod`
2. **Check sshd process:** `kubectl exec ... -- ps aux | grep sshd`
3. **Check service IP:** `kubectl get svc -n secure-agent-pod` — verify `192.168.55.215` is assigned
4. **Check authorized_keys:** `kubectl exec ... -- cat /home/claude/.ssh/authorized_keys`
5. **Check sshd logs:** `kubectl logs ... | grep sshd`

### VibeKanban Not Accessible

1. **Check process:** `kubectl exec ... -- pgrep -f vibe-kanban`
2. **Check port:** `kubectl exec ... -- curl -s http://127.0.0.1:8081` — should return HTML
3. **Check service:** `kubectl get svc secure-agent-vibekanban -n secure-agent-pod`
4. **Check env vars:** `kubectl exec ... -- env | grep -E "PORT|HOST"` — should show `PORT=8081`, `HOST=0.0.0.0`

### Env Vars Not Updated After Secret Change

Environment variables are set at container start. After changing a Secret:

```bash
kubectl rollout restart deployment/secure-agent-pod -n secure-agent-pod
```

## References

- [Building Post 21: Secure Agent Pod]({{< relref "/docs/building/21-secure-agent-pod" >}})
- [Claude Code Hooks Documentation](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [VibeKanban](https://github.com/BloopAI/vibe-kanban)
- [Cilium Network Policies](https://docs.cilium.io/en/stable/security/policy/)
- [supercronic](https://github.com/aptible/supercronic)
