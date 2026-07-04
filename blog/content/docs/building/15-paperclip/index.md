---
title: "Paperclip — An AI Agent Orchestrator on Frank"
series: ["building"]
layer: orch
date: 2026-03-14
draft: false
tags: ["paperclip", "agents", "ai", "orchestration", "postgresql", "ghcr", "litellm"]
summary: "Deploying Paperclip — an AI orchestrator that organises agents into virtual companies with org charts and budgets — alongside Sympozium, to compare two fundamentally different agentic paradigms."
weight: 16
---

Layer 11 gave the cluster a Kubernetes-native agentic control plane: Sympozium, where agents are Pods, policies are CRDs, and the API server is the source of truth. It maps cleanly onto the mental model of someone who already lives in Kubernetes.

Layer 14 adds a second perspective. [Paperclip](https://github.com/paperclipai/paperclip) organises agents differently — into virtual companies with org charts, budgets, reporting lines, and governance. Where Sympozium asks "which Kubernetes primitive models this agent?", Paperclip asks "what role would this agent have in a company?".

The goal is not to choose one over the other right now. Both run side by side. The cluster will make the comparison for me.

## What Is Paperclip?

Paperclip is an open-source AI agent orchestrator. Its core abstraction is the **company**: a named organisation with a CEO agent, department heads, and individual contributor agents, each with a defined role, a tool set, and a budget for LLM calls. Agents collaborate through message passing and report up the chain of command.

The web UI — served on the same port as the API — lets you define the org chart, deploy the company, watch agents reason and delegate, and review execution traces.

Paperclip does not publish container images. The project ships a Dockerfile but leaves building to the operator. That made this layer slightly more involved than usual.

## Architecture

```
paperclip-system
├── paperclip-db          (ArgoCD app, wave 0)
│   └── Bitnami PostgreSQL 14.1.10 — Longhorn 5Gi
└── paperclip             (ArgoCD app, wave 1)
    ├── Deployment         ghcr.io/paperclipai/paperclip:sha-3494e84  (upstream)
    ├── ExternalSecret     OPENAI_API_KEY + OPENAI_BASE_URL (LiteLLM)
    ├── ExternalSecret     BETTER_AUTH_SECRET
    ├── ExternalSecret     BRAVE_API_KEY (optional, web search)
    ├── ExternalSecret     RESEND_API_KEY (optional, transactional email)
    ├── PVC /paperclip data volume — Longhorn 10Gi

    └── Service (LB)       192.168.55.212:3100
```

Two ArgoCD apps, ordered by sync-wave. The database deploys first (wave 0); the application follows (wave 1) once PostgreSQL is healthy. Agents route through the existing LiteLLM gateway — same `OPENAI_BASE_URL` pattern as Sympozium.

## Building the Container Image

> **Historical, since v2026.428.0.** Paperclip now ships an upstream public image at `ghcr.io/paperclipai/paperclip` and we run that directly — no GHCR fork, no `paperclip-ghcr` `imagePullSecret`. The build/push workflow below describes how this layer worked while we maintained the `derio-net` fork; it's preserved for context on why the original architecture had a GHCR pull secret in it.

Paperclip's Dockerfile is straightforward Node.js — `pnpm install`, `pnpm build`, `USER node`. But the image is not small. It installs Claude Code, Codex, and opencode-ai globally as part of the agent tooling. The final image sits around 2GB.

```bash
git clone https://github.com/paperclipai/paperclip.git /tmp/paperclip
cd /tmp/paperclip && git checkout v0.3.1

docker buildx build \
  --platform linux/amd64 \
  -t ghcr.io/derio-net/paperclip:v0.3.1 \
  --push .
```

The first attempt pushed an `arm64`-only image — the build machine defaulted to its native architecture. Every node in the cluster's worker pool (mini-1/2/3, gpu-1, pc-1) is `amd64`. The pod scheduled, pulled successfully, and immediately failed with `no match for platform in manifest`. A rebuild with `--platform linux/amd64` fixed it.

The image lives in the `derio-net` org on GHCR, pulled via an `imagePullSecret` sourced from Infisical.

## The PostgreSQL Mirror Problem

Bitnami no longer serves named image tags from Docker Hub. Any chart version older than a few months will point to a tag like `bitnami/postgresql:16.2.0-debian-11-r16` that simply returns `404`. This affects not just the main database image but also the metrics sidecar (`bitnami/postgres-exporter`).

The working solution — already established by the `infisical-postgresql` app — is to override the image registry to `mirror.gcr.io/bitnamilegacy`:

```yaml
image:
  registry: mirror.gcr.io
  repository: bitnamilegacy/postgresql

metrics:
  enabled: true
  image:
    registry: mirror.gcr.io
    repository: bitnamilegacy/postgres-exporter
```

The GCR mirror carries all the legacy tags. Both images pull cleanly.

## Probe Behaviour in Private Mode

Paperclip runs in `authenticated` mode with `private` exposure. In this configuration the root path `/` returns `403` to any request not coming from `localhost`. The kubelet issues readiness probes from the node IP — not from within the container — so `httpGet` probes against `/` or `/api/health` get `403` and the pod never becomes `Ready`.

From inside the container, `/api/health` returns `200`. From the kubelet, it returns `403`. The fix is a TCP socket probe: it checks that port 3100 is accepting connections without making an HTTP request at all.

```yaml
readinessProbe:
  tcpSocket:
    port: http
  periodSeconds: 10
livenessProbe:
  tcpSocket:
    port: http
  initialDelaySeconds: 30
  periodSeconds: 15
```

## The PVC Rollout Deadlock

The `/paperclip` data volume uses `ReadWriteOnce` — only one pod can hold the claim at a time. During rolling updates the Deployment creates the new pod before terminating the old one (the default `RollingUpdate` strategy). The new pod gets scheduled, tries to attach the PVC, and stalls with `Multi-Attach error` because the old pod still holds it.

Since the old pod was in `CrashLoopBackOff` it was never going to release the PVC gracefully. Each fix cycle added a new ReplicaSet, each new ReplicaSet created a new pod, and the PVC stayed locked.

The solution: scale the old ReplicaSet to zero manually to release the PVC, then let the new pod attach and start cleanly. Once the new pod passes its probe the Deployment controller cleans up the old RS on its own.

For a single-replica stateful app backed by `ReadWriteOnce`, a `Recreate` deployment strategy would avoid this entirely — kill the old pod first, then start the new one. Worth revisiting if this becomes a permanent fixture.

## Volume Permissions

The Dockerfile does `chown node:node /paperclip` before `USER node`. When Longhorn mounts the PVC over `/paperclip`, the mounted directory is owned by `root` and the `chown` in the image never runs again. The `node` user (uid 1000, gid 1000) cannot write to it.

```yaml
spec:
  securityContext:
    fsGroup: 1000
```

`fsGroup` tells Kubernetes to `chown` the mounted volume to gid 1000 before handing it to the container. With that in place, the `node` user can create `/paperclip/instances/default/logs` and everything else it needs.

## Secret Management

Four ExternalSecrets sync from Infisical:

| Secret | Contains | How Used |
|--------|----------|----------|
| `paperclip-llm-key` | `OPENAI_API_KEY` + `OPENAI_BASE_URL` | `envFrom` — routes LLM calls through LiteLLM |
| `paperclip-auth` | `BETTER_AUTH_SECRET` | `envFrom` — session signing |
| `paperclip-brave` | `BRAVE_API_KEY` | `envFrom` — Brave Search API key for agent web-search tools (optional) |
| `paperclip-resend` | `RESEND_API_KEY` | `envFrom` — Resend API key for agent transactional email (optional) |

`paperclip-brave` and `paperclip-resend` are both marked `optional: true` in the Deployment — the pod starts normally without them. The Brave key is only needed by agents that invoke a web-search tool (e.g. the Brave Search MCP server); the Resend key is only needed by agents that send transactional email. Lesson learned: any `secretRef` for a feature that isn't always provisioned should be `optional: true`, otherwise a missing Secret blocks rolling updates entirely (`CreateContainerConfigError` on the new pod, old pod stuck alive). An earlier `paperclip-anthropic` ExternalSecret carrying `ANTHROPIC_API_KEY` for the `claude_local` adapter taught the same lesson the hard way before being retired when Paperclip switched to the upstream public image; a `paperclip-ghcr` `imagePullSecret` (used while we built our own image, see *Building the Container Image* above) was retired at the same time.

Both feature keys use the same source-vs-consumer remap pattern the LiteLLM secret uses (`PAPERCLIP_LITELLM_KEY` → `OPENAI_API_KEY`): the Brave key remaps `BRAVE_SEARCH_KEY_PAPERCLIP` to the standard `BRAVE_API_KEY` env var the Brave Search MCP server and SDKs expect, and the Resend key remaps `EMAIL_RESEND_API_KEY` to `RESEND_API_KEY` — the standard env var the Resend Node.js SDK and the Resend MCP server look for.

The LiteLLM secret uses the template merge pattern from Sympozium: a single Infisical key (`PAPERCLIP_LITELLM_KEY`) is combined with a static base URL at sync time, so the Deployment just does `envFrom` and gets both variables.

The database password follows the same pattern as all Bitnami chart deployments: the chart auto-generates a password and stores it in a `<releaseName>-postgresql` Secret. The Deployment reads it via `secretKeyRef` and builds the full `DATABASE_URL` using Kubernetes variable expansion:

```yaml
env:
  - name: PG_PASSWORD
    valueFrom:
      secretKeyRef:
        name: paperclip-db-postgresql
        key: password
  - name: DATABASE_URL
    value: "postgres://paperclip:$(PG_PASSWORD)@paperclip-db-postgresql.paperclip-system.svc:5432/paperclip"
```

## First Boot

Once the pod is `1/1 Running`, open `http://192.168.55.212:3100`. Paperclip prompts for a bootstrap admin account. After that, `pnpm paperclipai onboard` (run inside the pod) generates the Agent JWT that unlocks full agent functionality.

The startup log is informative:

```
Server          3100
API             http://localhost:3100/api
UI              http://localhost:3100
Database        postgres://paperclip:***@paperclip-db-postgresql...
Migrations      applied (pending migrations)
Agent JWT       missing (run `pnpm paperclipai onboard`)
Heartbeat       enabled (30000ms)
DB Backup       enabled (every 60m, keep 30d)
```

Database migrations applied on first start. Automatic PostgreSQL backups to `/paperclip/instances/default/data/backups` every hour.

{{< screenshot src="paperclip-ui.png" caption="Paperclip orchestrator showing active agents" >}}

## Memory Tuning and the Move to gpu-1

The original Deployment shipped with `requests.memory: 256Mi` and `limits.memory: 1Gi`, scheduling onto any node in the `zone: core` pool — the three control-plane minis. Those numbers were a guess inherited from the fork-era image and never re-validated when we switched to the upstream public build.

The guess was wrong twice.

**Round one: 1Gi → 2Gi.** Six weeks after `GEMINI_API_KEY` was added as an optional envFrom secret, paperclip started CrashLoopBackOff-ing every five minutes with exit 137 (OOMKilled). The container survived about nine seconds after start, dying right after the `reaped orphaned heartbeat runs` log line — far enough into boot that the JVM-style "warm up, then collapse" pattern was unmistakable. The Google AI SDK appears to eagerly init when its env var is present, even if no Gemini-backed agent ever runs. Bumping `requests.memory` to 512Mi and `limits.memory` to 2Gi got the pod through boot.

**Round two: 2Gi → 12Gi, on gpu-1.** Two hours later, OOMKilled again. This time under load, with agent runs actually doing work. Bumping the limit higher on a 64GB mini was possible but uncomfortable — the core-zone minis run the control plane, ArgoCD, Cilium, Longhorn, observability, the registry, Authentik. They have headroom but not the kind that absorbs a 12Gi tenant without complaint.

gpu-1, meanwhile, was sitting at roughly 20% of its 128GB requested. So paperclip moved.

```yaml
nodeSelector:
  kubernetes.io/hostname: gpu-1
tolerations:
  - key: nvidia.com/gpu
    effect: NoSchedule
resources:
  requests:
    memory: 512Mi
    cpu: 250m
  limits:
    memory: 12Gi
    cpu: "1"
```

Two things to call out about that block.

First, paperclip does not request a GPU. It is a CPU/RAM workload that happens to live on the GPU node — gpu-1 just happens to also be the cluster's biggest CPU/RAM box. The naming is misleading on purpose: gpu-1 is the "anything that needs more than 64GB" node.

Second, the `nvidia.com/gpu:NoSchedule` toleration is *defensive*, not active. gpu-1's live taint list is empty right now; nothing on it requires a toleration to schedule. But the GPU operator periodically re-validates drivers and can re-assert the taint during that window. Any non-GPU workload pinned to gpu-1 without the toleration would be evicted on the spot. The cluster idiom is to mirror the toleration on every gpu-1 tenant — ollama, n8n, openrgb, secure-agent-pod, and now paperclip all carry it. It's insurance, not enforcement.

The lesson generalises: limits inherited from a previous image are not measurements. They are placeholders waiting to be wrong. Paperclip's real working set turned out to be roughly an order of magnitude higher than the inherited 1Gi guess. The cluster will have opinions about resource sizing — best to let it tell you.

## Adding a Side Door: SSH-able Shell Sidecar

After Paperclip had been running for a few weeks the workflow shape stabilised, and the friction with `kubectl exec` got harder to ignore. The expected day-to-day is *24/7 agentic work* — long sessions, persistent tmux state, mosh over a flaky home connection, dotfiles, and the occasional "let me try `eza` for a minute, see if it earns a slot." `kubectl exec` is functional but loses everything on disconnect, has no first-class entry in `~/.ssh/config`, and doesn't survive a laptop sleep.

The instinct was to install sshd into the upstream Paperclip container. We deliberately rejected that. Layer 14 had just stepped *off* the maintenance treadmill of forking `ghcr.io/paperclipai/paperclip` (`b35b781` and `d4060c8`); putting sshd back into a fork would put us right back on. The other instinct — install sshd onto the PV at runtime via Ansible — was rejected for the same reason: the install would silently rot on every upstream rebase.

The answer is a separate sibling container in the same Pod.

### Pod topology

```
namespace: paperclip-system
└── Deployment: paperclip   (strategy: Recreate)
    │   securityContext: { fsGroup: 1000 }
    │
    ├── container: paperclip                          (UNCHANGED)
    │     image: ghcr.io/paperclipai/paperclip:sha-…
    │     volumeMount: paperclip-data → /paperclip
    │     port: 3100/TCP                              (LB 192.168.55.212)
    │
    └── container: paperclip-shell                    (NEW)
          image: ghcr.io/derio-net/paperclip-shell:<sha>
          securityContext: { runAsUser: 1000, drop: [ALL] }
          volumeMounts:
            paperclip-shell-home      → /home/agent      (NEW PVC, RWO 20Gi)
            paperclip-data            → /paperclip       (SHARED RW with paperclip)
            paperclip-shell-ssh-keys  → /etc/ssh-keys    (SOPS Secret)
            paperclip-shell-inventory → /etc/paperclip-shell  (ConfigMap)
          ports:
            22/TCP                                       (sshd, LB 192.168.55.221)
            60000-60015/UDP                              (mosh range, same LB IP)
```

The upstream container is bit-identical to what it was before — same image, same env, same mount, same probe. The shell sidecar runs alongside it, sharing the `paperclip-data` PVC at `/paperclip` (`fsGroup: 1000` makes the PV group-writable so both containers' UID-1000 processes can read and write there) and exposing SSH and Mosh on a separate `LoadBalancer` IP, `192.168.55.221`. The two LB IPs make the layering legible at the routing level: `:212` is the Paperclip API; `:221` is the operator's terminal.

`MixedProtocolLBService` does the heavy lifting. A single Service binds TCP/22 + UDP/60000–60015 on the same EndpointSlice and Cilium 1.17 + Kubernetes 1.35 answer both cleanly, so we don't pay the complexity tax of two Services for one operator-facing IP.

### Three-layer install model

The image alone can't be the answer. A single image bumped on every tool tweak would put us back on the upstream-treadmill problem we were trying to escape. So the shell environment is built in three layers, each declarative at a different cadence:

| Layer | Where | Cadence | Examples |
|---|---|---|---|
| 1 — Runtime managers | Image | Slow (image rebuild) | `mise`, `rustup`, `pipx`, sshd, mosh, tmux |
| 2 — Tool inventory | ConfigMap | Medium (commit + sync) | `python@3.12`, `node@20`, `ripgrep`, `claude-code`, `codex` |
| 3 — Interactive | Operator | On demand | `cargo install fd-find` over SSH |

Layer 1 is the slow loop. The image — `ghcr.io/derio-net/paperclip-shell` — is a thin extension of `agent-shell-base` (the same image `ruflo-shell` and `secure-agent-kali` derive from). All it adds is the runtime *managers* and a single `cont-init.d` hook.

Layer 2 is the medium loop. `apps/paperclip/manifests/configmap-shell-inventory.yaml` declares the operator's expected toolset as a YAML inventory grouped by manager (`mise`, `npm-global`, `pipx`, `cargo`, plus a `removed:` block for opt-in uninstalls). On every container boot, `cont-init.d/40-shell-inventory` reads the inventory, queries each manager, computes the diff, and converges. Idempotent — re-running with no changes is a sub-second no-op. State lives on `paperclip-shell-home` (the new RWO 20Gi PVC mounted at `/home/agent`), not in the image, so the same image happily serves wildly different toolsets across pods.

Layer 3 is the escape hatch. SSH in, `cargo install fd-find`, decide later whether it earns a slot in the inventory. The binary lands on the PV; it survives pod restarts as a side-effect of PV reuse. The promotion rule is *survival across PV migration*: anything you want re-installed on a fresh PV must be in the inventory ConfigMap. Layer 3 is intentional — a fast feedback loop for "is this tool worth committing to" — not an oversight.

### Fail-open with Telegram alerting

The installer's hardest design question was what to do when something fails. There are two extreme positions and they're both wrong.

The strict position: a `cargo install` failure should fail the container, ArgoCD reports `Degraded`, the Pod restarts, the operator notices and fixes it. Clean GitOps discipline. But this also means a transient `crates.io` 503 takes the operator's terminal offline. SSH was the *whole point* of the layer; it should not depend on every tool successfully installing.

The lax position: log failures to a file, move on, sshd comes up. SSH stays available. But now an inventory entry can silently rot for days. The next time the operator tries to invoke a tool that "should be" there, it isn't, and they have to go figure out why.

We pick fail-open + active alert. The installer continues past failures and writes the per-step exit codes to `/var/log/cont-init.d/40-shell-inventory.log`. sshd comes up regardless. *And* on any non-zero exit, it fires a Telegram message via `@agent_zero_cc_bot` (the same path as Frank's ArgoCD notifications, reusing `FRANK_C2_TELEGRAM_BOT_TOKEN` / `FRANK_C2_TELEGRAM_CHAT_ID` from Infisical). The MOTD on next login also flips to the failure summary (`⚠ paperclip-shell: 1 install(s) failed on last reconcile (npm i -g @openai/codex)`), so a passive `ssh` shows the state without having to read the log.

Three visibility layers, ranked passive → active:

1. `kubectl logs paperclip -c paperclip-shell` — full installer output via `tee`.
2. MOTD on SSH login — last-reconcile summary line.
3. Telegram message — within seconds of pod boot.

Layer 3 is the load-bearing one. We don't notice (2) unless we ssh in; we don't notice (1) unless we go looking. (3) interrupts.

Success is signalled too — on clean reconcile, MOTD prints `✓ paperclip-shell: 0 installed, 9 already present, 0 removed @ 2026-05-03T19:10` so a fresh login confirms a recent inventory edit applied. No Telegram noise on success.

### Why not Ansible, why not modify the upstream image

Ansible is built for fleets and idempotent role composition. For one container with a flat list of tools, the playbook + inventory + role ceremony exceeds the problem. A ~50-line bash script reading a YAML inventory does the same job with no new system to learn. The non-root security context is the binding constraint regardless — Ansible cannot make `apt` work in a `cap-drop=ALL` container; that needs root or image rebuild, both of which are explicit decisions, not config-management automation.

Modifying the upstream Paperclip image was rejected for the same reason we ditched the fork: the image bumps unpredictably, pinning sshd into a derivative would put us on the upstream-rebase treadmill, and any UID/entrypoint drift would silently break SSH. The whole point of the sidecar shape is that the operator's environment evolves on its own cadence — the only contract with the upstream container is the shared `/paperclip` mount and `fsGroup: 1000`.

### What this layer taught the cluster

The thing the cluster actually learned here isn't "how to bolt sshd onto a Pod." It's that **the boundary between the workload and the operator's environment can be a Pod boundary inside a single Deployment**. Same scheduling, same lifecycle, same shared volume — but separate images, separate update cadences, separate security postures. `paperclip-shell` and `paperclip` rebuild on different schedules and never see each other's filesystems except through the explicitly shared mount. The shell sidecar is the operator's home; the workload container is the application. Both fit in the same Pod and neither has to know about the other.

`ruflo-shell` had already demonstrated the pattern on a fresh hybrid Pod. `paperclip-shell` proved it retrofits cleanly onto an existing layer without touching the upstream container at all.

## What's Next

Paperclip and Sympozium now coexist on the same cluster, sharing the same LiteLLM gateway. The practical comparison will play out over the next few layers as I try to automate the same workflows through both and see which abstraction fits better.

Paperclip's company/org-chart model might be better suited for long-running autonomous work with clear delegation chains. Sympozium's CRD-native model fits better for workloads that need to interact with Kubernetes directly. Or they serve different purposes entirely and both stay.

The cluster will have opinions.
