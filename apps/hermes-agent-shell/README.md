# hermes-agent-shell

Nous Research's official `hermes-agent` image running as a four-container pod
on gpu-1, with an SSH sidecar for operators, a self-hosted Hindsight memory
backend and a pgvector retrieval store.

**Live since the 2026-07-09 cutover** (willikins#285). This file documents the
deployed state; the narrative of how it was built is in the blog posts
`blog/content/docs/building/33-hermes-shell/` and
`blog/content/docs/operating/28-hermes-shell/`.

## Topology

One pod, four containers sharing a network namespace:

| Container | Image | Job |
|---|---|---|
| `hermes` | `docker.io/nousresearch/hermes-agent:<calver>` (unmodified upstream) | gateway API (8642) + dashboard (9119) |
| `ssh` | `ghcr.io/derio-net/hermes-agent-shell-ssh:<sha>` (agent-images) | sshd (2222) + mosh (60032-60047) + `hermes` CLI passthrough |
| `hindsight` | `ghcr.io/derio-net/hermes-agent-shell-hindsight:<sha>` (agent-images) | Hindsight memory backend: PostgreSQL 18.4 + pgvector + `hindsight-api` on loopback |
| `gbrain` | `pgvector/pgvector:0.8.6-pg18` (stock upstream, digest-pinned) | Retrieval store: PostgreSQL 18 + pgvector on loopback `5434` — see below |

Five RWO Longhorn PVCs:

| PVC | Size | Mounted at | Contents |
|---|---|---|---|
| `hermes-agent-shell-data` | 20Gi | `/opt/data` (hermes, ssh) | `HERMES_HOME` — config.yaml, skills, cron, sessions, state DB, memory, SOUL.md |
| `hermes-agent-shell-home` | 40Gi | `/opt/data/home` (hermes, ssh) | `$HOME` — see the sizing note below |
| `hermes-agent-shell-repos` | 20Gi | `/opt/data/home/repos` (hermes, ssh) | Local working repos |
| `hermes-agent-shell-hindsight` | 5Gi | `/opt/hindsight` (hindsight only) | `PGDATA` for the memory backend |
| `hermes-agent-shell-gbrain` | 10Gi | `/opt/gbrain` (gbrain only) | `PGDATA` for the retrieval store |

The two Postgres sidecars share nothing — different images, different volumes,
different ports. That separation is the point, not an accident of layout; see
`pvc-gbrain.yaml` for why the alternative was withdrawn.

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

The `gbrain` store has **no** bootstrap secret, deliberately — see below.

## The retrieval store (`gbrain`)

Added 2026-08-03 (frank#759): stock `pgvector/pgvector:0.8.6-pg18`,
digest-pinned, PostgreSQL 18 + pgvector on its own 10Gi Longhorn volume at
`/opt/gbrain` (`PGDATA=/opt/gbrain/pgdata`). It exists so an external client's
CLI — run by an operator from the `ssh` sidecar — has somewhere to keep
vectors. Hindsight is a different memory layer with different write patterns
and different recovery expectations, and is untouched by this: same image,
same env, same 5Gi PVC.

**The DSN is `postgres://gbrain@127.0.0.1:5434/gbrain`.** No password: the
server runs `POSTGRES_HOST_AUTH_METHOD=trust`. Port 5434 because 5433 is
Hindsight's Postgres and all four containers share one network namespace.
There is no `containerPort`, no Service, no LoadBalancer IP and no
IngressRoute — declaring any of them would advertise reachability that does
not exist. For the same reason the probes are `exec` + `pg_isready` rather
than `tcpSocket`: the kubelet dials the *pod IP*, which this server never
listens on.

**It can be a stock image because `PGDATA` is a subdirectory of the mount.**
The container runs the same strict posture as `ssh` and `hindsight` (uid 1000,
`runAsNonRoot`, `cap-drop: ALL`) and needs no build layer to do it: `fsGroup`
leaves the volume *root* at `0775`, Postgres refuses a data directory wider
than `0750`, and the entrypoint creating `/opt/gbrain/pgdata` itself is what
makes that directory uid-owned and `0700`. Because a stock image has no boot
hook, the pod-level `fsGroupChangePolicy: OnRootMismatch` is load-bearing here
rather than defence-in-depth — it is the only thing stopping the kubelet
re-loosening a populated `PGDATA` on the next recreate. Full prose:
`docs/runbooks/frank-gotchas/agent-shells.md`.

**Loopback plus `trust` means every container in this pod is a superuser of
this database.** `listen_addresses=127.0.0.1` keeps the socket inside the
pod's network namespace, so nothing off-pod can reach it with or without
credentials — but *inside* the pod there is no boundary at all, and that
includes `hermes`, which is unmodified upstream running LLM-driven agent code.
An agent that decides to `DROP TABLE` can. This is the posture the Hindsight
sidecar has always run, so it adds no new *class* of exposure to the pod; the
alternative fails worse, because a password Secret must exist before first
boot and a missing or mistyped one crashloops a container inside a pod two
other containers are living in. Tightening it later is a
`POSTGRES_HOST_AUTH_METHOD` flip plus an `ALTER ROLE … PASSWORD`, not a
redesign.

**`CREATE EXTENSION vector` runs once, at initdb, and never again.** It ships
as a ConfigMap mounted at `/docker-entrypoint-initdb.d`
(`configmap-gbrain-initdb.yaml`), and the Postgres entrypoint reads that
directory *only* when it has to initialise an empty `PGDATA`. Every later
start skips it entirely. So editing that ConfigMap does nothing to a volume
that has already been initialised: ArgoCD reports Synced, the new SQL is
visibly on disk inside the pod, and the database is exactly as it was. Any
later extension, schema or migration change is `psql` work against the live
database (or a migration the CLI owns):

```bash
kubectl -n hermes-agent-shell exec -it deploy/hermes-agent-shell -c gbrain -- \
  psql -h 127.0.0.1 -p 5434 -U gbrain -d gbrain
```

**The client CLI is installed by hand onto the home PVC, and is therefore not
reproducible from git.** The `ssh` sidecar image carries only a generic Bun
runtime plus a `/etc/profile.d/36-hermes-bun-path.sh` shim putting
`$HOME/.bun/bin` on `PATH` in login shells; the CLI itself is a one-time
global install by the operator into `$HOME=/opt/data/home`, which is a
Longhorn PVC — the same persistent-agent pattern this pod already uses for
`claude` and `gh` auth. **If the home PVC is ever rebuilt, the install must be
repeated.** Nothing reconciles it, nothing alerts when it is missing, and the
symptom is a `command not found` in a shell that otherwise looks healthy.
Manual op `orch-hermes-gbrain-cli-install`. Verify it in a **login** shell —
`ssh … 'bash -lc "<cli> --version"'` — because `ssh host -- cmd` skips
`/etc/profile.d` entirely and would prove nothing about the `PATH` shim.

There is deliberately **no `DATABASE_URL` env shim**. The obvious move is a
`profile.d` export like the BYOK one, but nobody in this repo knows which
variable the CLI reads, and a guessed variable name is a thing that is never
read. The DSN above is the contract; wiring it in is a one-line follow-up once
the CLI's own contract is known.

### "No restart required" meant no volume detach — not no restart

frank#759 says the revised shape needs *"no restart required by this work."*
That is true about **volumes**: it avoids the withdrawn 5Gi → 10Gi Hindsight
expansion, which is a detach-and-expand on an RWO volume holding a live
database — a scheduled, risky operation.

It is not true about the **pod**. This Deployment is `strategy: Recreate` and
cannot be anything else, because every volume is RWO and cannot double-mount.
Adding a fourth container therefore tears the pod down and builds a new one:
Hindsight goes down for as long as that takes, and every live `tmux`, SSH and
mosh session on the shell is dropped. That is the routine cost of *any*
manifest change to this pod rather than a special risk of this one — but it is
a restart, ArgoCD takes it on merge, and there is no separate window to book,
so whoever merges is choosing when it happens.

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
- The pod has four containers, so `kubectl exec` needs an explicit `-c`
  (`hermes`, `ssh`, `hindsight`, `gbrain`).

## History

The 2026-07-09 cutover ran alongside a temporary `hermes-agent-shell-migrate`
stack (its own Deployment, Service, Secrets and five PVCs) used to validate the
new topology against the old one. It was hand-created, never committed to git,
and therefore invisible to ArgoCD's `prune: false` reconciliation — it sat at
`replicas: 0` holding 75Gi of Longhorn reservations until it was purged
2026-07-27. Findings originally attributed to "the migrate deployment" in
`deployment.yaml` comments are preserved there as history, not as pointers to
anything still on the cluster.
