# hermes-agent-shell — official-Hermes-first migration (willikins#285)

Target state manifests for the two-container model. **Not yet live** — this PR
is the reviewable Part 1 (manifests + new sidecar image). The live backup +
cutover is Part 2, gated on operator review. See the design spec in the
willikins repo (`docs/superpowers/specs/2026-07-09-hermes-official-migration-design.md`).

## Topology

One pod, two containers, sharing three RWO Longhorn PVCs:

| Container | Image | Job |
|---|---|---|
| `hermes` | `docker.io/nousresearch/hermes-agent:v2026.7.7.2` (unmodified) | gateway API (8642) + dashboard (9119) + embedded Hindsight |
| `ssh` | `ghcr.io/derio-net/hermes-agent-shell-ssh:<sha>` (new agent-images dir) | sshd (2222) + mosh (60032-60047) + `hermes` CLI passthrough |

| PVC | Mount (both containers) | Contents |
|---|---|---|
| `hermes-agent-shell-data` (new) | `/opt/data` | Hermes profile: config, skills, cron, sessions, state DB, memory, SOUL.md, Hindsight client config **and** the embedded Hindsight Postgres data (see below) |
| `hermes-agent-shell-home` (reused) | `/opt/data/home` | `.ssh`, `.gitconfig`, `.config/gh`, compat `.hermes.md` |
| `hermes-agent-shell-repos` (new) | `/opt/data/home/repos` | Local working repos |

Routing: SSH/Mosh stays on the Cilium L2 LoadBalancer (`service.yaml`,
`192.168.55.226`). Dashboard + API get a ClusterIP (`service-dashboard.yaml`)
exposed via Traefik (`apps/traefik/manifests/ingressroutes.yaml`:
`hermes.cluster.derio.net`, `hermes-api.cluster.derio.net`).

## Phase 0 finding — Hindsight is embedded, NOT an external service

The spec's Hindsight section (a separate first-class `hindsight-postgres`
Deployment/Service the pod connects to over cluster DNS) was **provisional
pending this live inventory**. The inventory (`kubectl exec` into the running
pod, 2026-07-09) shows Hindsight is **not** an external service:

- `hermes gateway run` (PID of the gateway) **spawns and supervises** two child
  processes itself — not s6, not systemd:
  1. **PostgreSQL 18.4** from a bundled **micromamba env** (`hindsight-pg`),
     listening on port **5433** + a unix socket under `.local/pgsql`, `pg_hba`
     = `trust`, role `hindsight`. Data dir `…/.local/pgsql/hindsight-data`.
  2. **`hindsight-api`** — a Python console script from the `hindsight_api`
     package in the Hermes venv, listening on `127.0.0.1:8888`. This is the
     `local_external` "API" Hermes talks to; Hermes does not proxy it.
- A `hermes_stack_watchdog.py` (tmux) keeps that stack alive.

Because the official image bundles and self-spawns the whole stack from its data
dir, **this migration does NOT ship a standalone `hindsight-postgres`
Deployment/Service/PVC.** Doing so would create dead infrastructure the gateway
never connects to, unless Hindsight is also reconfigured away from
`local_external` mode to a remote DSN — a larger change that needs the official
image's actual on-disk layout confirmed against a real pull (Phase 3) and is out
of scope for Part 1. The embedded Postgres data therefore lives on the `-data`
PVC (as it does today on the single combined PVC), and memory continuity is
preserved by the Phase 1/2 `pg_dump` + restore, not by externalization.

**Externalization option (deferred, operator decision):** if first-class,
separately-managed Postgres is still wanted, the path is: stand up a PG18 service
(with the same extensions — confirm `pgvector` etc. at backup time), set
`HINDSIGHT_API_MIGRATION_DATABASE_URL` / the hindsight DSN to it, and confirm
the official image can be told NOT to spawn its embedded PG. Not attempted here.

## Open flags for Part 2 (see PR body / igor report)

1. **Official image runs as `root`** (config `User: "root"`, own s6 `/init`).
   The `runAsUser:1000` + cap-drop-ALL posture is unverified against it and may
   break s6 `/run` chowns — Phase 3 validation item; fallback is a relaxed
   securityContext (namespace PSA is `baseline`).
2. **Auto-continue patch (frank#496) is not in the official image.** Confirm
   upstream fixed it between 0.15.2 and v2026.7.7.2, else apply the
   patch-at-pod-start mitigation (spec Open Risks).
3. **Sidecar image SHA is a placeholder** — merge the agent-images PR first.
