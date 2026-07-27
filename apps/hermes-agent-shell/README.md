# hermes-agent-shell

Nous Research's official `hermes-agent` image running as a three-container pod
on gpu-1, with an SSH sidecar for operators and a self-hosted Hindsight memory
backend.

**Live since the 2026-07-09 cutover** (willikins#285). This file documents the
deployed state; the narrative of how it was built is in the blog posts
`blog/content/docs/building/33-hermes-shell/` and
`blog/content/docs/operating/28-hermes-shell/`.

## Topology

One pod, three containers sharing a network namespace:

| Container | Image | Job |
|---|---|---|
| `hermes` | `docker.io/nousresearch/hermes-agent:<calver>` (unmodified upstream) | gateway API (8642) + dashboard (9119) |
| `ssh` | `ghcr.io/derio-net/hermes-agent-shell-ssh:<sha>` (agent-images) | sshd (2222) + mosh (60032-60047) + `hermes` CLI passthrough |
| `hindsight` | `ghcr.io/derio-net/hermes-agent-shell-hindsight:<sha>` (agent-images) | Hindsight memory backend: PostgreSQL 18.4 + pgvector + `hindsight-api` on loopback |

Four RWO Longhorn PVCs:

| PVC | Size | Mounted at | Contents |
|---|---|---|---|
| `hermes-agent-shell-data` | 20Gi | `/opt/data` (hermes, ssh) | `HERMES_HOME` — config.yaml, skills, cron, sessions, state DB, memory, SOUL.md |
| `hermes-agent-shell-home` | 40Gi | `/opt/data/home` (hermes, ssh) | `$HOME` — see the sizing note below |
| `hermes-agent-shell-repos` | 20Gi | `/opt/data/home/repos` (hermes, ssh) | Local working repos |
| `hermes-agent-shell-hindsight` | 5Gi | `/opt/hindsight` (hindsight only) | `PGDATA` for the memory backend |

Note `repos` is mounted **inside** `home`. Any `du` across `$HOME` needs `-x`
or it double-counts through the nested mount.

### What is actually on the home volume

`$HOME` is not a dotfile volume — it carries every tool install and cache the
agent has ever made, and sizing it as if it were dotfiles is what took it to
94% full (frank#715). Measured 2026-07-27 at 19G used:

```
.local/opt/hermes-agent   6.0G   PVC-resident Hermes venv (frank#496)
.vscode-server            3.3G
.cache                    1.9G   playwright, uv, huggingface, pip, fr
.local/{micromamba,share} 2.5G   mise, mamba, uv, claude
worktrees                 1.3G   fr isolation checkouts
```

Growth is dominated by tool installs and caches, not by the fr worktrees whose
failure surfaced it. Treat a future fill as a signal to prune caches first.
Nothing currently alerts on this volume filling.

## Routing

- **SSH / Mosh** — Cilium L2 LoadBalancer at `192.168.55.226` (`service.yaml`)
- **Dashboard + gateway API** — ClusterIP (`service-dashboard.yaml`) exposed via
  Traefik at `hermes.cluster.derio.net` and `hermes-api.cluster.derio.net`
  (`apps/traefik/manifests/ingressroutes.yaml`)

Those routes carry `ip-allowlist` + `security-headers` only. `authentik-forwardauth`
was removed 2026-07-12: no authentik application was configured for these hosts,
so the outpost 404'd every request — and the dashboard self-authenticates anyway
(see below). SSO via authentik remains a possible follow-up.

## Bootstrap secrets (out-of-band, not ArgoCD-managed)

SOPS-encrypted, applied from `secrets/hermes-agent-shell/` before the pod can
start. Neither is optional — the container genuinely refuses to bind without them:

- `hermes-agent-shell-dashboard-auth` — `HERMES_DASHBOARD_BASIC_AUTH_{USERNAME,PASSWORD,SECRET}`
- `hermes-agent-shell-api-key` — `API_SERVER_KEY`

`hermes-agent-shell-ssh-keys` follows the same pattern for operator SSH keys.

## Design findings worth keeping

**The dashboard hard-refuses an unauthenticated public bind.** The image will
not bind 9119 to a non-loopback interface without an auth provider — *"there is
no unauthenticated public-bind option"* — and that refusal loops and blocks the
gateway API (8642) from binding at all, CrashLooping the whole container. An
IngressRoute alone was never sufficient; the basic-auth env is what makes it work.

**The gateway API port is env-driven, not config-driven.** There is no
`api_server:` section in `config.yaml`. `API_SERVER_ENABLED` / `API_SERVER_HOST`
/ `API_SERVER_KEY` are the only mechanism that binds 8642. Without them the pod
comes up, the dashboard serves, and the pod sits at 2/3 forever with a
tcpSocket probe that never passes.

**Hindsight's backend is ours; its client is upstream's.** The official image
ships the Hindsight *client* and, left alone, self-spawns a Postgres + API stack
from its data dir under a tmux watchdog — an arrangement that survives until it
does not, and takes the memory with it. The `hindsight` sidecar replaces that
with a real container Kubernetes supervises, reached in `local_external` mode at
`127.0.0.1:8888`. Only data lives on the PVC (`PGDATA=/opt/hindsight/pgdata`),
which also put memory on its own volume inside Longhorn's recurring-backup group.

**Probes must be `exec`, not `httpGet`.** `hindsight-api` binds `127.0.0.1`
only; the kubelet runs `httpGet` against the pod IP and gets connection-refused
forever (37 restarts before this was found). An exec probe curls loopback from
inside the container, which is where the API actually listens.

**The main container runs as root; the sidecars do not.** The upstream image
boots only as root with the default capability set — strict `runAsUser: 1000` +
`cap-drop: ALL` fails at s6 preinit, and even root + `cap-drop: ALL` fails at
`s6-applyuidgid`. `HERMES_UID`/`HERMES_GID=1000` remap the image's internal user
so the gateway worker still runs as 1000 and `/opt/data` ends up 1000-owned —
"root to init, 1000 to work". The `ssh` sidecar keeps the strict posture.

## Operational notes

- `config.yaml` is **PVC state**, seeded by hand. `HERMES_HOME=/opt/data`, so the
  live file is `/opt/data/config.yaml` — *not* `~/.hermes/config.yaml`, which
  still exists as a stale pre-migration copy and is not what Hermes reads.
  Manual ops: `orch-hermes-config-provider`, `orch-hermes-context-budgets`,
  `orch-hermes-default-qwen64k`, `orch-hermes-qwen64k-budgets`.
- The Hermes venv is PVC-resident and re-seeds only when its `.seed-version`
  marker changes (frank#496) — so an image bump is **not** evidence the running
  Hermes moved. Check `hermes --version` inside the pod.
- The pod has three containers, so `kubectl exec` needs an explicit `-c`.

## History

The 2026-07-09 cutover ran alongside a temporary `hermes-agent-shell-migrate`
stack (its own Deployment, Service, Secrets and five PVCs) used to validate the
new topology against the old one. It was hand-created, never committed to git,
and therefore invisible to ArgoCD's `prune: false` reconciliation — it sat at
`replicas: 0` holding 75Gi of Longhorn reservations until it was purged
2026-07-27. Findings originally attributed to "the migrate deployment" in
`deployment.yaml` comments are preserved there as history, not as pointers to
anything still on the cluster.
