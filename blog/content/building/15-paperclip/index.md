---
title: "Paperclip — An AI Agent Orchestrator on Frank"
date: 2026-03-14
draft: false
tags: ["paperclip", "agents", "ai", "orchestration", "postgresql", "ghcr", "litellm"]
summary: "Deploying Paperclip — an AI orchestrator that organises agents into virtual companies with org charts and budgets — alongside Sympozium, to compare two fundamentally different agentic paradigms."
weight: 16
cover:
  image: cover.png
  alt: "Frank the cluster monster in a corporate boardroom with tiny AI agents seated around a table as employees"
  relative: true
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
    ├── Deployment         ghcr.io/derio-net/paperclip:v0.3.1
    ├── ExternalSecret     OPENAI_API_KEY + OPENAI_BASE_URL (LiteLLM)
    ├── ExternalSecret     BETTER_AUTH_SECRET
    ├── ExternalSecret     GHCR imagePullSecret
    ├── PVC                /paperclip data volume — Longhorn 2Gi
    └── Service (LB)       192.168.55.212:3100
```

Two ArgoCD apps, ordered by sync-wave. The database deploys first (wave 0); the application follows (wave 1) once PostgreSQL is healthy. Agents route through the existing LiteLLM gateway — same `OPENAI_BASE_URL` pattern as Sympozium.

## Building the Container Image

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
| `paperclip-ghcr` | `.dockerconfigjson` | `imagePullSecrets` — GHCR auth |
| `paperclip-anthropic` | `ANTHROPIC_API_KEY` | `envFrom` — direct Anthropic access via `claude_local` adapter (optional) |

The `paperclip-anthropic` secret is marked `optional: true` in the Deployment — the pod starts normally without it. The `claude_local` adapter only needs it if you want to bypass LiteLLM and call Anthropic directly. Lesson learned: any `secretRef` for a feature that isn't always provisioned should be `optional: true`, otherwise a missing Secret blocks rolling updates entirely (`CreateContainerConfigError` on the new pod, old pod stuck alive).

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

## What's Next

Paperclip and Sympozium now coexist on the same cluster, sharing the same LiteLLM gateway. The practical comparison will play out over the next few layers as I try to automate the same workflows through both and see which abstraction fits better.

Paperclip's company/org-chart model might be better suited for long-running autonomous work with clear delegation chains. Sympozium's CRD-native model fits better for workloads that need to interact with Kubernetes directly. Or they serve different purposes entirely and both stay.

The cluster will have opinions.
