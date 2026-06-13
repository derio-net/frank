# Ruflo Pod — Design

**Status:** Draft
**Layer:** `orch`
**Spec date:** 2026-05-02

## Goal

Deploy `ruflo` (the rebrand of `claude-flow` by ruvnet — [myaiguide.co/repos/ruflo](https://myaiguide.co/repos/ruflo)) to Frank as a long-running multi-agent orchestration platform, with:

1. **A 24/7 ruvocal web UI** at `https://ruflo.cluster.derio.net`, Authentik-protected, for browsing hives, kicking off swarms, and monitoring runs.
2. **An always-on swarm orchestrator process** — ruvocal is a single Node.js process that drives both the dashboard and the long-running agent runs.
3. **An SSH-able shell sidecar** (`ruflo-shell`) for operator interaction: tmux sessions, manual `claude-flow` invocations, debugging swarm state, attaching to runs in flight.
4. **Zero direct frontier-LLM provider keys.** All LLM traffic flows through the in-cluster LiteLLM gateway (192.168.55.206) or OpenRouter, by design.

This is a **new layer extension** of the `orch` capability domain (sibling to Paperclip), not a modification of an existing layer.

## Motivation

Frank already runs Paperclip as a structured multi-agent orchestrator (org-chart agents, delegation chains, formal task lifecycle). Ruflo offers a contrasting paradigm — more organic, more chaotic, more swarm-like — built on top of Claude Code's primitives. Running both side-by-side lets the cluster's "let competing paradigms decide via the work" philosophy continue past Paperclip into a second orchestration vendor with a different design philosophy.

The architectural pattern is a near-clone of the paperclip-shell-sidecar design (also dated 2026-05-02, in flight) — same shell sidecar shape, same `agent-shell-base` lineage, same fail-open inventory installer with Telegram alerting. Three meaningful differences:

1. **Ruflo is a fresh deployment**, not a sidecar grafted onto an upstream image already running. We get to design the service-side from scratch instead of working around an unmodifiable container.
2. **No upstream image runs ruvocal as a long-lived service today.** The official `ruvnet/claude-flow:v2-alpha` image is CLI-only; the web UI lives at `src/ruvocal/Dockerfile` in the upstream repo and ships a build with optional embedded MongoDB. We build a `ruflo-server` image from it ourselves.
3. **Discovery framing.** Initial deployment is intentionally minimal — bare manifests, empty inventory, conservative resource sizing. Tuning happens after a discovery week of actual operator use.

Three constraints shape the design:

1. **Service-container PVC is RWO.** Ruvocal owns `/workspace`; the shell shares it. Sidecar in the same pod is the only viable shape, same as paperclip-shell.
2. **Non-root, capability-dropped security context** on the shell sidecar (`runAsUser: 1000`, `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`). Inherits all the s6-overlay v3 lessons from the paperclip-shell + secure-agent-kali smoke-test campaign in `derio-net/agent-images`.
3. **Declarative-only.** Image SHA-pinned in git; software inventory in a versioned ConfigMap; SSH keys via Infisical→ESO; LLM access through cluster gateways. The Mongo password is the one new secret added to Infisical at deploy time.

## Constraints

1. **`ruflo-workspace` is RWO.** Single-pod, `strategy: Recreate`, no rolling updates.
2. **`ruflo-shell` runs non-root with caps dropped.** Userspace package management only (mise, cargo, pipx, npm-global). No `apt` at runtime.
3. **`ruflo-server` runs as a separate process from MongoDB.** `apps/ruflo-db/` is its own ArgoCD sub-app, mirroring `apps/paperclip-db/`.
4. **Shell image evolves on a separate cadence from ruflo-server.** Both live in `derio-net/agent-images` and bump independently.
5. **No direct Anthropic/OpenAI/Gemini keys in the pod.** Routed through LiteLLM gateway. OpenRouter is the deliberate exception (broader model catalog, free models, exotic providers).

## Architecture

### Pod topology

```
namespace: ruflo-system
└── Deployment: ruflo
    │   strategy: Recreate                            # RWO PVC requirement
    │   nodeSelector: { zone: core }                  # mini-1/2/3
    │   securityContext: { fsGroup: 1000 }
    │   shareProcessNamespace: true                   # shell can ps/strace ruvocal
    │
    ├── container: ruflo                              # ruvocal web UI + swarm
    │     image: ghcr.io/derio-net/ruflo-server:<sha>
    │     env:
    │       MONGO_URL:           from ruflo-db sub-app (Service DNS + secret)
    │       OPENROUTER_API_KEY:  ESO → Infisical
    │       EMAIL_RESEND_API_KEY: ESO → Infisical
    │       LITELLM_BASE_URL:    http://litellm.litellm-system:4000
    │     volumeMounts:
    │       ruflo-workspace → /workspace              # 50 Gi, RWO (path TBD plan-time)
    │     ports:
    │       3000/TCP                                  # ruvocal HTTP (TBD plan-time)
    │     resources:
    │       requests: { cpu: 500m,  memory: 1Gi }
    │       limits:   { cpu: 4000m, memory: 8Gi }
    │     readinessProbe: { httpGet: { port: 3000, path: / } }
    │
    └── container: ruflo-shell                        # operator side door
          image: ghcr.io/derio-net/ruflo-shell:<sha>
          securityContext:
            runAsUser: 1000
            runAsGroup: 1000
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
          volumeMounts:
            ruflo-shell-home      → /home/agent       # 20 Gi, RWO
            ruflo-workspace       → /workspace        # SHARED RW with ruflo
            ruflo-shell-ssh-keys  → /etc/ssh-keys     # ESO Secret (shared)
            ruflo-shell-inventory → /etc/ruflo-shell  # ConfigMap
          ports:
            2222/TCP                                  # sshd
            60016-60031/UDP                           # mosh range (16 sessions)
          resources:
            requests: { cpu: 500m,  memory: 1Gi }
            limits:   { cpu: 2000m, memory: 4Gi }
          readinessProbe: { tcpSocket: { port: 2222 } }
          livenessProbe:  { tcpSocket: { port: 2222 } }
```

### Image lineage

```
ghcr.io/derio-net/agent-shell-base:<tag>
  + s6-overlay v3 (non-root mode), sshd, tmux, mosh, base CLI tools
  + AGENT_USER=agent (default), AGENT_HOME=/home/agent (default)
      │
      ├──► ghcr.io/derio-net/secure-agent-kali:<sha>     (existing)
      ├──► ghcr.io/derio-net/vk-local:<sha>              (existing)
      ├──► ghcr.io/derio-net/paperclip-shell:<sha>       (in flight, dispatched today)
      └──► ghcr.io/derio-net/ruflo-shell:<sha>           (NEW)
              defaults inherited; layer-1 baked: mise + rustup + pipx + claude CLI
              cont-init.d/40-shell-inventory pattern reused from paperclip-shell

ghcr.io/derio-net/ruflo-server:<sha>                     (NEW; not derivative of agent-shell-base)
  built from upstream ruvnet/ruflo at src/ruvocal/Dockerfile with INCLUDE_DB=false
  CI lives in derio-net/agent-images/ruflo-server/
```

### Networking

```
┌─ Browser ─────────────────────────────────────────────────────────────┐
│ https://ruflo.cluster.derio.net                                       │
│   → Authentik forward-auth (existing authentik-forwardauth middleware)│
│   → Traefik IngressRoute (apps/traefik/manifests/ingressroutes.yaml)  │
│   → Service: ruflo-web (ClusterIP) → ruvocal port 3000                │
│   → ruvocal in container `ruflo`                                      │
└───────────────────────────────────────────────────────────────────────┘

┌─ Operator laptop ─────────────────────────────────────────────────────┐
│ ssh agent@192.168.55.222                                              │
│ mosh agent@192.168.55.222                                             │
│   → Service: ruflo-shell (LoadBalancer, mixed TCP+UDP, 192.168.55.222)│
│       port 22/TCP   → 2222/TCP   (sshd)                               │
│       port 60016-60031/UDP                                            │
│   → ruflo-shell container                                             │
└───────────────────────────────────────────────────────────────────────┘
```

`192.168.55.222` is the next free LB IP after `.221` (reserved for paperclip-shell). The web UI Service is **ClusterIP-only** — Traefik handles external exposure, no dedicated LB IP.

The mosh range `60016-60031` is chosen to avoid overlap with secure-agent-pod's `60000-60015`. Sixteen UDP ports = sixteen simultaneous mosh sessions, mirroring the paperclip-shell allocation.

### State persistence

| PVC | Size | RWO | Owner | Purpose |
|---|---|---|---|---|
| `ruflo-workspace` | 50 Gi | yes | shared | Swarm runs, AgentDB / HNSW vector store, agent scratch files |
| `ruflo-shell-home` | 20 Gi | yes | operator | `/home/agent` — dotfiles, mise/cargo/pipx tools, tmux-resurrect, ssh keypairs |
| `ruflo-db-data` | 20 Gi | yes | `apps/ruflo-db/` | MongoDB — ruvocal's persistent state (hives, history, settings) |

**Three persistence boundaries, made explicit:**

1. `/workspace` is shared between ruvocal and the shell. Ruvocal owns the schema; the shell may read/write. Concurrent edits work via `fsGroup: 1000`.
2. `/home/agent` is the operator's. Nothing upstream (ruvocal or future ruflo-server bumps) can touch it. This is the durability anchor for "tools survive image bumps."
3. `ruflo-db-data` is owned by the `ruflo-db` sub-app's Mongo pod. Backups via Longhorn snapshots, separate from the workspace.

Sized larger than paperclip-workspace (`50 Gi` vs `20 Gi`) because swarm runs accumulate vector embeddings + per-run artifacts and the design philosophy is "let it sprawl during discovery, prune later."

### `apps/ruflo-db/` sub-app

A separate ArgoCD app mirroring `apps/paperclip-db/`'s shape. MongoDB Helm chart (chart choice = whatever paperclip-db uses, for consistency), single replica, 20 Gi PVC, ClusterIP-only Service, password from ESO referencing a new Infisical entry `RUFLO_DB_PASSWORD`. Connection string flows into `ruflo-server` as `MONGO_URL` env.

### LLM gateway principle

Ruflo holds **zero direct frontier-LLM provider keys**. All Claude/GPT/Gemini access flows through `LITELLM_BASE_URL` → in-cluster LiteLLM gateway at `192.168.55.206`. Three consequences worth recording:

1. Revoking ruflo's access to any model provider is a one-line change at LiteLLM's config — no Infisical rotation, no pod restart.
2. Cost tracking and observability are uniform across cluster agents (Paperclip, secure-agent-pod, ruflo all visible in the same dashboards).
3. If ruflo's swarm goes runaway with API calls, the kill switch is at the gateway, not at the pod.

The remaining `OPENROUTER_API_KEY` is a deliberate escape hatch for accessing OpenRouter's broader catalog (free models, exotic providers, models LiteLLM may not be configured for). `EMAIL_RESEND_API_KEY` is for transactional email from agent runs (matches the Paperclip wiring added earlier today, observation 2506).

### SSH key management

Reuse the existing `agent-ssh-keys` Infisical entries via a new `ExternalSecret` CR pointing at the same source. One operator identity across `secure-agent-pod`, `paperclip-shell`, and `ruflo-shell`. Rotating a key in Infisical reconciles all three pods on the next ESO refresh.

## `ruflo-server` image design

Built from upstream `ruvnet/ruflo`'s `src/ruvocal/Dockerfile` with `INCLUDE_DB=false`. CI lives in `derio-net/agent-images/ruflo-server/`. Two reasonable build paths, decided at plan time:

- **Direct vendor build:** clone upstream at a pinned SHA, `docker build src/ruvocal/ --build-arg INCLUDE_DB=false`. Cleanest if the upstream Dockerfile cooperates.
- **Thin wrapper Dockerfile:** if the upstream Dockerfile assumes `INCLUDE_DB=true` (e.g., Mongo install steps not gated on the build arg), wrap it with our own Dockerfile that strips the Mongo layer.

CI smoke test: container starts, listens on its declared port, connects to a test Mongo, serves the UI's healthcheck endpoint.

**Explicitly NOT in the image:** any LLM provider keys (those are env vars at runtime), any operator dotfiles, any tools beyond what upstream ships. The shell container is for operator ergonomics; this container is the upstream artifact, kept thin.

## `ruflo-shell` image design

`FROM ghcr.io/derio-net/agent-shell-base:<tag>`. Inherits sshd, tmux, mosh, base CLI tools, and the `cont-init.d` non-root-mode setup that's been hardened across the s6-overlay v3 PR campaign in `derio-net/agent-images`.

**Adds (Layer-1, baked into image):**
- `mise` (asdf-replacement), `rustup`, `pipx` — Layer-1 runtime managers, slow-changing.
- `@anthropic-ai/claude-code` global npm install — so the operator can immediately invoke `claude` against LiteLLM from the shell, no inventory wait.
- `/etc/cont-init.d/40-shell-inventory`, `install-inventory.sh`, `notify-telegram.sh` — direct copies from the paperclip-shell rootfs (literally the same scripts; if the pattern proliferates further, future work could factor them into a shared layer in `agent-images`).
- `/etc/skel/.bashrc` exporting `LITELLM_BASE_URL`, plus a banner noting "you're inside ruflo-shell, `/workspace` is shared with the ruvocal process."
- `/etc/skel/.tmux.conf` sourcing the existing `/etc/agent/tmux-resurrect.conf` (per the kali pattern).

**Defaults inherited from `agent-shell-base`:**
- `AGENT_USER=agent`, `AGENT_HOME=/home/agent` (no override needed; fresh PV, unlike `secure-agent-kali`'s legacy `claude`/`/home/claude`).
- s6-overlay v3 in non-root mode, including the `/run` ownership fix (observation 2459).
- `cont-init.d` shebang/with-contenv path conventions inherited from the `agent-shell-base` fix chain (observations 2469–2474).

**CI smoke test:** mirror paperclip-shell exactly — `/init` under `--cap-drop=ALL --security-opt=no-new-privileges --user 1000`. Verify sshd binds 2222, empty inventory installer runs without blocking, MOTD renders.

## Declarative software inventory

Identical pattern to paperclip-shell's `configmap-shell-inventory.yaml`. Initial deploy ships an empty inventory; `claude-flow` is the first thing the operator adds during the discovery phase. See the paperclip-shell-sidecar design for the full installer behaviour, schema, and editing flow — the implementation is reused verbatim.

## Visibility & alerting

Three layers, identical to paperclip-shell:

| Layer | Mechanism | Visible when |
|---|---|---|
| 1 | Tee installer output to stdout + log file | `kubectl logs ruflo -c ruflo-shell` |
| 2 | MOTD on SSH login prints last-boot summary | Every SSH session |
| 3 | Telegram alert on any failure via `@agent_zero_cc_bot` | Within seconds of pod boot |

Reuses `FRANK_C2_TELEGRAM_BOT_TOKEN` + `FRANK_C2_TELEGRAM_CHAT_ID` from Infisical.

## Documentation & rollout surface

This change touches three repos and several documentation surfaces.

### `derio-net/agent-images` (companion repo, separate PR)

```
agent-images/
├── ruflo-server/                         (NEW)
│   ├── Dockerfile                        (FROM upstream ruvocal or thin wrapper)
│   ├── README.md
│   └── ci/                               (smoke test wiring)
└── ruflo-shell/                          (NEW)
    ├── Dockerfile                        (FROM agent-shell-base)
    ├── rootfs/
    │   ├── etc/cont-init.d/40-shell-inventory
    │   ├── usr/local/lib/ruflo-shell/install-inventory.sh
    │   ├── usr/local/lib/ruflo-shell/notify-telegram.sh
    │   └── etc/skel/{.bashrc,.tmux.conf,...}
    └── README.md
```

CI: matrix-build alongside existing children; smoke test under non-root + cap-drop.

### `derio-net/frank` `apps/ruflo/` (this repo)

```
apps/ruflo/
├── manifests/
│   ├── namespace.yaml
│   ├── deployment.yaml                     # 2 containers, shareProcessNamespace
│   ├── service-web.yaml                    # ClusterIP for Traefik
│   ├── service-shell.yaml                  # mixed TCP+UDP LB, 192.168.55.222
│   ├── pvc-workspace.yaml                  # 50 Gi
│   ├── pvc-shell-home.yaml                 # 20 Gi
│   ├── configmap-shell-inventory.yaml      # initial empty inventory
│   ├── externalsecret-openrouter.yaml
│   ├── externalsecret-resend.yaml
│   ├── externalsecret-shell-ssh-keys.yaml  # references shared agent-ssh-keys
│   ├── externalsecret-db-credentials.yaml
│   └── serviceaccount.yaml
└── client-setup/
    └── laptop/                             # mirrors paperclip-shell / secure-agent-pod
        ├── README.md
        └── ssh-config-snippet
```

### `derio-net/frank` `apps/ruflo-db/` (NEW sub-app)

Mongo Helm chart, values matched to `paperclip-db`'s shape. Separate `Application` CR in `apps/root/templates/ruflo-db.yaml`. Synced before `ruflo` so `MONGO_URL` resolves on first ruvocal boot.

### `apps/root/templates/`

Two new `Application` CRs: `ruflo-db.yaml` (synced first) and `ruflo.yaml`.

### Cross-cutting cluster surfaces

- `apps/traefik/manifests/ingressroutes.yaml` — new IngressRoute for `ruflo.cluster.derio.net` with `authentik-forwardauth` middleware.
- `apps/authentik-extras/manifests/blueprints-cluster-proxy-providers.yaml` — new proxy provider entry for ruflo (`forward_single` mode).
- `apps/homepage/manifests/configmap-services.yaml` — new tile under "AI Agents" or "Orchestration" category.

### CLAUDE.md rules

- `.claude/rules/frank-infrastructure.md` — add rows to Frank Cluster Services for `Ruflo Web UI | (via Traefik) | IngressRoute (ruflo.cluster.derio.net)` and `Ruflo Shell (SSH+Mosh) | 192.168.55.222`.
- `.claude/rules/frank-gotchas.md` — add anything novel discovered during implementation.

### Blog posts

This is a **new layer** (sibling to Paperclip), so per `repo-workflows.md` it gets its own building post + operating post. Use `/blog-post`. Update series index (`blog/content/docs/building/00-overview/index.md`) and roadmap shortcode (`blog/layouts/shortcodes/cluster-roadmap.html`).

### README

Run `/update-readme` post-deploy.

## Migration plan

Sequence (high level — converted to phased plan in `vk-plan`):

1. **agent-images PR:** add `ruflo-shell/` and `ruflo-server/` directories with Dockerfiles, rootfs, smoke tests. Merge once CI green.
2. **Pre-flight Infisical:** add `RUFLO_DB_PASSWORD` entry; ensure `OPENROUTER_API_KEY` and `EMAIL_RESEND_API_KEY` are reachable from a `ruflo-system` namespace path (or copy them in).
3. **Frank PR — manifests:** add `apps/ruflo-db/`, `apps/ruflo/`, both `Application` CRs in `apps/root/templates/`, the Traefik IngressRoute, the Authentik blueprint entry, the homepage tile, the CLAUDE.md rule rows.
4. **First deploy validation:** `ruflo-db` healthy → `ruflo` Recreate-strategy comes up → ruvocal connects to Mongo → readiness probes green → Traefik route serves a 401 (Authentik intercepting). Run **manual outpost provider assignment** via Django ORM. Browser SSO works; ruvocal UI loads.
5. **SSH validation:** `ssh agent@192.168.55.222` lands in `/home/agent`; `cd /workspace` shows ruvocal's view; `ls /workspace` reflects what ruvocal sees.
6. **Inventory population:** add `claude-flow` (and whatever else feels right after first hour of poking) to `configmap-shell-inventory.yaml`, commit, run `ruflo-shell-reconcile` from the shell.
7. **Documentation pass:** new building + operating blog posts via `/blog-post`. Update series index + roadmap shortcode. `/update-readme`. `/sync-runbook` if any new manual-ops blocks were introduced.
8. **Plan status → Deployed.**

Rollback at any step: revert the frank PR. `ruflo-db`'s PVC remains by default (per `prune: false`); to fully wipe, delete the PVC manually.

## Decisions log

- **Hybrid pod (service + shell sidecar), not separate Deployments.** RWO PVC + the requirement to share `/workspace` make the sidecar the only viable shape. Same reasoning as paperclip-shell.
- **New `ruflo-server` image, built from upstream ruvocal source.** No published image runs ruvocal as a long-lived service today; we own the build pipeline. CI lives alongside the rest of `agent-images`.
- **`ruflo-shell` based on `agent-shell-base`, not on `ruflo-server`.** Shell evolution decoupled from upstream ruvocal cadence. Same reasoning as paperclip-shell.
- **No direct frontier-LLM provider keys in the pod.** All Claude/GPT/Gemini traffic flows through the in-cluster LiteLLM gateway. OpenRouter is the deliberate exception. Resend is for transactional email.
- **Separate `ruflo-db` sub-app, not embedded MongoDB.** Mirrors the existing `paperclip` + `paperclip-db` split. Cleaner backup/restore via Longhorn snapshots; ruvocal can restart without bouncing Mongo.
- **Web UI ClusterIP-only, exposed via Traefik.** Saves an LB IP; matches the homepage / n8n-01 pattern. SSH+Mosh keep their own LB IP because direct laptop-side `ssh agent@192.168.55.222` and the 16-port mosh UDP range don't fit cleanly behind Traefik or NodePorts.
- **Single mixed TCP+UDP LoadBalancer for SSH+Mosh.** Per paperclip-shell precedent (and the K8s 1.26+ MixedProtocolLBService capability supported by Cilium L2 + kube-proxy-replacement).
- **Shared SSH keys with `secure-agent-pod` and `paperclip-shell`.** One operator identity; one source of truth in Infisical.
- **`shareProcessNamespace: true`.** Cheap; lets the shell `ps`/`strace`/`lsof` ruvocal's processes when debugging swarms.
- **Mosh enabled (16-port UDP range, 60016–60031).** Mosh ports are bound per-(IP, port) so overlap with secure-agent-pod (60000–60015) or paperclip-shell would be functionally fine — the distinct range is for diagnostic clarity (`netstat` output makes it obvious whose mosh session a given UDP port belongs to).
- **`zone: core` placement.** No GPU needed; long-running but bursty CPU; matches Paperclip.
- **Conservative initial sizing.** `500m/1Gi` requests across the board; tune after a discovery week.
- **Defer egress restriction.** Ruflo needs wide egress for swarm-driven model calls + npm/pipx/cargo/mise installs from the inventory. Threat-model upgrade is a future plan.

## Out of scope

- **Periodic Mongo backups beyond Longhorn snapshots.** Default snapshot policy is the backup story.
- **Multi-replica ruvocal.** Single replica + RWO PVC + Recreate matches the architectural choice.
- **Direct frontier-provider keys (Anthropic/OpenAI/Gemini).** Routed through LiteLLM by design.
- **Federated ruflo + paperclip orchestration.** They run side-by-side; coordination is "the operator decides which to use." Cross-pod orchestration is a future plan if it ever feels needed.
- **Egress restrictions.** Defer until threat model warrants.
- **Prometheus exporter / Grafana panels for ruflo internals.** Telegram + MOTD + LiteLLM dashboards cover visibility at one-pod scale.
- **DNS record for `ruflo-shell.cluster.derio.net`.** Operator can add a `~/.ssh/config` host entry on the laptop side; cluster-side DNS not required.
- **Periodic inventory reconciler cron.** Interactive `ruflo-shell-reconcile` covers all real cases at one-pod scale.

## Open questions (plan-time investigation)

- **ruvocal port** (likely `3000` — unconfirmed; needs Dockerfile read or runtime probe).
- **ruvocal workspace path** (likely `/app/workspace` or configurable via env; affects the `ruflo-shell` mount path. The two containers must agree.).
- **ruvocal's `MONGO_URL` env var name** (could be `MONGODB_URI`, `MONGO_CONNECTION_STRING`, etc.).
- **`INCLUDE_DB=false` build path stability.** Whether upstream's Dockerfile is well-tested with that build arg, or whether we need a thin wrapper that strips the Mongo install layer.
- **ruvocal's exact entrypoint** (CMD vs ENTRYPOINT; which `node` script it runs).
- **MongoDB chart choice for `ruflo-db`.** Ideally identical to `paperclip-db`'s — to be confirmed at plan time.
- **Resource sizing pass.** Initial requests/limits are guesses; refine after first week of operator use.
- **Whether `mise` and `claude-flow` coexist cleanly in `/home/agent`** (claude-flow npm-installs into mise's node@20; needs verification on first deploy).
- **MOTD plumbing reuse.** Whether `agent-shell-base`'s sshd config already enables PAM motd from the paperclip-shell campaign.

## Success criteria

- `https://ruflo.cluster.derio.net` lands on the ruvocal UI after Authentik SSO.
- Hives can be created in the UI and runs orchestrated end-to-end.
- `ssh agent@192.168.55.222` lands in `/home/agent` with `mise`, `claude`, `tmux`, `mosh` on PATH.
- `mosh agent@192.168.55.222` reattaches across network changes; tmux-resurrect restores prior sessions on pod restart.
- `cd /workspace` from the shell shows the same files ruvocal is operating on; concurrent edits work (PVC owned by both via `fsGroup: 1000`).
- Editing `configmap-shell-inventory.yaml` and running `ruflo-shell-reconcile` installs declared additions without restarting the pod.
- A pod restart preserves: `/home/agent`, installed inventory tools, ssh keypairs, dotfiles, tmux sessions (via resurrect), all swarm state in Mongo, all workspace files.
- A pod restart does NOT preserve anything in either container's image rootfs outside `/home/agent`, `/workspace`, and the Mongo PVC.
- An induced inventory failure (e.g., add a non-existent npm package) fires a Telegram alert within ~30s of pod boot; sshd remains available; MOTD on next login shows the failure.
- All ruvocal LLM traffic flows through LiteLLM (visible in LiteLLM dashboards) or OpenRouter (visible at openrouter.ai dashboard); zero direct frontier-provider traffic from the pod.
- Bumping `ruflo-server` image SHA does not affect `/home/agent` or the operator's installed tools.
- Bumping `ruflo-shell` image SHA does not affect ruvocal or its data.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| Ruflo Pod Implementation Plan | `derio-net/frank` | `2026-05-02--orch--ruflo-pod` | — |
