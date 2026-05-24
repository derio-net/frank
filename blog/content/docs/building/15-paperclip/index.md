---
title: "Paperclip — An AI Agent Orchestrator on Frank"
series: ["building"]
layer: orch
date: 2026-03-14
draft: false
tags: ["paperclip", "agents", "ai", "orchestration", "postgresql", "ghcr", "litellm"]
summary: "Deploying Paperclip — an AI orchestrator that organises agents into virtual companies with org charts and budgets — alongside Sympozium, to compare two fundamentally different agentic paradigms."
weight: 16
reader_goal: "Deploy Paperclip on Talos with a shell sidecar, work around probe deadlocks, PVC rollout deadlock, fsGroup permissions, and memory tuning"
diataxis: tutorial
last_updated: 2026-07-15
description: "Deploying Paperclip — an AI orchestrator that organises agents into virtual companies with org charts and budgets — alongside Sympozium, to compare two fundamentally different…"
---

Layer 11 gave the cluster a Kubernetes-native agentic control plane — Sympozium, where agents are Pods and policies are {{< abbr "CRD" "CRDs" >}}. Layer 15 adds a second perspective. [Paperclip](https://github.com/paperclipai/paperclip) organises agents differently — into virtual companies with org charts, budgets, reporting lines, and governance. Where Sympozium asks "which Kubernetes primitive models this agent?", Paperclip asks "what role would this agent have in a company?".

Both run side by side. The cluster makes the comparison.

```mermaid
flowchart LR
  subgraph Paperclip[Paperclip — paperclip-system]
    App[paperclip Deployment<br/>ghcr.io/paperclipai/paperclip]
    Shell[paperclip-shell sidecar<br/>SSH: 192.168.55.221]
    DB[paperclip-db StatefulSet<br/>Bitnami PostgreSQL 14.1.10<br/>5Gi Longhorn]
    PVC[paperclip-data PVC<br/>10Gi Longhorn<br/>shared between containers]
    Secrets[ExternalSecrets<br/>4 from Infisical]
  end
  subgraph LLM[LiteLLM Gateway]
    LL[litellm.litellm.svc:4000]
  end
  subgraph Operator[Operator Access]
    SSH[SSH + Mosh<br/>192.168.55.221:22]
    UI[Paperclip UI<br/>192.168.55.212:3100]
  end

  App -->|DATABASE_URL| DB
  App -->|OPENAI_API_KEY + BASE_URL| LL
  App --> Shell
  App -->|envFrom| Secrets
  Shell -->|shared /paperclip| App
  UI --> App
  SSH --> Shell
```

## Architecture

Two ArgoCD apps, ordered by sync-wave. The `paperclip` Application carries `argocd.argoproj.io/sync-wave: "1"`, so every resource in it waits for wave 0 — the database — to report Healthy before it is applied:

```mermaid
flowchart LR
  subgraph Wave0[Sync Wave 0]
    DB[paperclip-db<br/>Bitnami PostgreSQL<br/>5Gi Longhorn]
  end
  subgraph Wave1[Sync Wave 1]
    P[paperclip<br/>Deployment]
    ES[ExternalSecrets × 4<br/>from Infisical]
    PVC[paperclip-data<br/>10Gi Longhorn<br/>RWO]
    LB[LoadBalancer<br/>192.168.55.212:3100]
  end

  DB --> P
  DB --> ES
  DB --> PVC
  DB --> LB
```

| App | Chart | Purpose |
|-----|-------|---------|
| `paperclip-db` | {{< abbr "OCI" >}} Bitnami postgresql 14.1.10 | PostgreSQL, image from `mirror.gcr.io/bitnamilegacy` |
| `paperclip` | Raw manifests | Deployment, ExternalSecrets, {{< abbr "PVC" >}}, Service |

## Deploying the Database

The PostgreSQL mirror problem is the same as Infisical's Layer 9: Bitnami no longer serves named image tags from Docker Hub. Override the registry to `mirror.gcr.io/bitnamilegacy`:

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

## Deploying the Application

Paperclip does not publish its own public image at the time of writing. The project ships a Dockerfile; building is left to the operator. The cluster initially maintained a fork at `ghcr.io/derio-net/paperclip`, built with:

```bash
docker buildx build --platform linux/amd64 \
  -t ghcr.io/derio-net/paperclip:v0.3.1 --push .
```

**Since v2026.428.0**, Paperclip ships an upstream public image at `ghcr.io/paperclipai/paperclip`. The cluster now uses that directly — no fork, no `imagePullSecret`.

### Probe Behaviour in Private Mode

Paperclip runs in `authenticated` mode with `private` exposure. In this configuration the root path `/` returns `403` to any request not from `localhost`. The kubelet issues readiness probes from the node IP, so `httpGet` probes against `/` or `/api/health` get `403` and the pod never becomes `Ready`.

The fix is a TCP socket probe — it checks that port 3100 accepts connections without making an HTTP request:

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

### PVC Rollout Deadlock

The `/paperclip` data volume uses `ReadWriteOnce` — only one pod can hold the claim at a time. During rolling updates the Deployment creates the new pod before terminating the old one. The new pod tries to attach the PVC and stalls with `Multi-Attach error`.

Scale the old ReplicaSet to zero manually to release the PVC:

```bash
kubectl scale deployment paperclip -n paperclip-system --replicas=0
# wait for PVC to release
kubectl scale deployment paperclip -n paperclip-system --replicas=1
```

For a single-replica stateful app backed by `RWO`, a `Recreate` deployment strategy avoids this entirely — kill the old pod first, then start the new one.

### Volume Permissions (fsGroup)

The Dockerfile does `chown node:node /paperclip` before `USER node`. When Longhorn mounts the PVC over `/paperclip`, the mounted directory is owned by `root` and the `chown` in the image never runs again. The `node` user (uid 1000) cannot write to it:

```yaml
spec:
  securityContext:
    fsGroup: 1000
```

`fsGroup` tells Kubernetes to `chown` the mounted volume to gid 1000 before handing it to the container.

## Secret Management

Four ExternalSecrets sync from Infisical, all consumed via `envFrom`:

| Secret | Keys | Optional |
|--------|------|----------|
| `paperclip-llm-key` | `OPENAI_API_KEY` + `OPENAI_BASE_URL` → LiteLLM | No |
| `paperclip-auth` | `BETTER_AUTH_SECRET` | No |
| `paperclip-brave` | `BRAVE_API_KEY` → Brave Search | Yes |
| `paperclip-resend` | `RESEND_API_KEY` → transactional email | Yes |

The database password comes from the Bitnami chart auto-generated Secret, referenced via `secretKeyRef` and Kubernetes variable expansion:

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

## Memory Tuning and the Move to gpu-1

The original Deployment had `requests.memory: 256Mi` and `limits.memory: 1Gi`. This guess was wrong twice.

**Round 1 (1Gi → 2Gi):** After `GEMINI_API_KEY` was added, the container started OOMKilling every five minutes. The Google AI SDK appears to eagerly init when its env var is present. Bumping the limit to 2Gi got the pod through boot.

**Round 2 (2Gi → 12Gi, on gpu-1):** Two hours later, OOMKilled again under load. The core-zone mini nodes (control plane + dozens of services) did not have 12Gi to spare. gpu-1 was at ~20% of 128GB. Paperclip moved:

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

Paperclip does not request a GPU. gpu-1 is the cluster's biggest CPU/RAM box — the "anything that needs more than 64GB" node. The `nvidia.com/gpu:NoSchedule` toleration is defensive: the GPU operator can re-assert the taint during driver validation, and any non-GPU workload pinned to gpu-1 without the toleration would be evicted on the spot.

## Shell Sidecar

After weeks of production use, the friction with `kubectl exec` got hard to ignore — lost tmux state on disconnect, no `~/.ssh/config` entry, no mosh over flaky connections. The instinct was to install sshd into the upstream Paperclip container. We deliberately rejected that: forking the image to add sshd puts us back on the upstream-rebase treadmill.

The answer is a separate sibling container in the same Pod:

```mermaid
flowchart LR
  subgraph Pod[paperclip Deployment Pod]
    PC[paperclip container<br/>ghcr.io/paperclipai/paperclip<br/>port 3100]
    PSH[paperclip-shell container<br/>ghcr.io/derio-net/paperclip-shell<br/>port 22 + mosh UDP]
    PVC[paperclip-data PVC<br/>10Gi Longhorn<br/>shared RW]
    SHOME[paperclip-shell-home PVC<br/>20Gi Longhorn<br/>RWO]
  end
  subgraph Network
    LB1[LB 192.168.55.212:3100<br/>Paperclip API]
    LB2[LB 192.168.55.221:22<br/>SSH + Mosh]
  end

  PC -->|envFrom| Secrets
  PC -->|mount /paperclip| PVC
  PSH -->|mount /paperclip| PVC
  PSH -->|mount /home/agent| SHOME
  LB1 --> PC
  LB2 --> PSH
```

The upstream container is bit-identical — same image, same env, same probes. The shell sidecar runs alongside, sharing the `paperclip-data` PVC at `/paperclip` and exposing SSH + Mosh on a separate LoadBalancer IP `192.168.55.221`.

### Three-Layer Install Model

| Layer | Where | Cadence | Examples |
|-------|-------|---------|----------|
| 1 — Runtime managers | Image | Slow (image rebuild) | `mise`, `rustup`, `pipx`, sshd, mosh, tmux |
| 2 — Tool inventory | ConfigMap | Medium (commit + sync) | `python@3.12`, `node@20`, `ripgrep`, `claude-code` |
| 3 — Interactive | Operator | On demand | `cargo install fd-find` over SSH |

Layer 1 is the image — `ghcr.io/derio-net/paperclip-shell`, a thin extension of `agent-shell-base`.

Layer 2 is the ConfigMap. On every container boot, `cont-init.d/40-shell-inventory` reads a YAML tool inventory, queries each manager (`mise`, `npm-global`, `pipx`, `cargo`), computes the diff, and converges. Idempotent — sub-second no-op when nothing changed.

Layer 3 is the escape hatch. SSH in, install something ad-hoc, decide later if it earns a slot in the inventory. State lives on `paperclip-shell-home` (20Gi {{< abbr "RWO" >}} PVC at `/home/agent`), so it survives pod restarts.

### Fail-Open with Telegram Alerting

The installer fails open: on any non-zero exit, it fires a Telegram message via `@agent_zero_cc_bot` (reusing `FRANK_C2_TELEGRAM_BOT_TOKEN` / `FRANK_C2_TELEGRAM_CHAT_ID` from Infisical). The {{< abbr "MOTD" >}} on next login shows the failure summary. Three visibility layers:

1. `kubectl logs paperclip -c paperclip-shell` — full installer output
2. MOTD on SSH login — last-reconcile summary
3. Telegram message — within seconds of pod boot

Layer 3 is the load-bearing one. We do not notice (2) unless we SSH in. Layer 3 interrupts.

## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---------------|-----------------|-----------------|--------|
| **HTTP probes get 403 in private mode** — kubelet probes from node IP, but Paperclip's `/` returns 403 to non-localhost | Paperclip's `private` exposure denies all non-localhost HTTP | Switched from `httpGet` to `tcpSocket` probes | — |
| **PVC rollout deadlock** — new pod cannot attach RWO PVC until old pod releases it; rolling update creates new pod first | Default `RollingUpdate` strategy creates new pod before terminating old one | Scale old ReplicaSet to zero manually; or use `Recreate` strategy | — |
| **fsGroup missing — PVC owned by root** — `node` user (uid 1000) cannot write to `/paperclip` | Dockerfile `chown` runs at image build, does not re-run on PVC mount | Added `fsGroup: 1000` to pod securityContext | — |
| **Initial memory limit 1Gi too low** — container OOMKilled under agent load | Memory guess inherited from fork-era image, never re-validated | Bumped to 12Gi on gpu-1 | — |
| **arm64-only image pushed** — build machine defaulted to native arch; cluster nodes are amd64 | `docker buildx build` without `--platform linux/amd64` | Added explicit platform flag | — |
| **Optional secrets blocking rollout** — missing `imagePullSecret` caused `CreateContainerConfigError`, old pod stayed alive with PVC locked | Any `secretRef` for a non-essential feature should be `optional: true` | Marked optional secrets with `optional: true` | — |

## Two CLIs Through One Gateway: opencode and hermes

The shell sidecar gave the operator a place to live. The next question was whether Paperclip's *agents* — the ones the company hires to actually do work — could run on Frank's own inference instead of reaching out to a cloud provider. Paperclip ships adapters for both [opencode](https://github.com/sst/opencode) and [Hermes](https://github.com/NousResearch/hermes-agent), and both speak an OpenAI-shaped API. LiteLLM (`litellm.litellm.svc:4000`, fronting Ollama on gpu-1) speaks that dialect. So the wiring is, in principle, three things: install the CLI, point it at LiteLLM, and tell the adapter which model to ask for.

In practice each CLI disagreed with the spec about exactly *how*, and the two disagreements were not the same disagreement. That is the whole story of this extension.

### Where the config lives, and who wins

The shared `/paperclip` PVC is mounted by both the `paperclip` workload container and the `paperclip-shell` sidecar, so the obvious move was to install both CLIs onto the PVC and be done. opencode had other ideas. The image already bakes `opencode 1.14.48` at `/usr/local/bin/opencode`, and the container's PATH puts the image dirs *before* the PVC suffix — a deliberate choice from the sidecar work ("suffix, not prefix, so image-baked binaries still win"). So `which opencode` resolves to the image binary, not the newer 1.15.3 the PVC install dropped at `/paperclip/agent-bin/node_modules/.bin/opencode`. Fighting that ordering would have meant special-casing one tool against a rule the rest of the layer relies on. Instead the layer wires config *to the binary that wins*: `XDG_CONFIG_HOME=/etc/paperclip/opencode-base`, a read-only ConfigMap holding `opencode.json` with the `provider.litellm` block and `{env:LITELLM_API_KEY}` interpolation. The PVC install stays as a newer-version fallback reachable by absolute path.

opencode's adapter rewrites its runtime config on every run, which raised the obvious fear: does it clobber our `provider.litellm` block? Reading `runtime-config.ts` in the running image settled it — the adapter does a recursive `fs.cp` of the source config dir and then a shallow merge (`{...existingConfig, permission: {...}}`), so our provider block survives untouched. Verifying that *before* committing a manifest, rather than after three pod bounces, is the entire reason Phase 1 of this work existed as a standalone "probe everything that can surprise us" phase.

hermes wanted the opposite of a read-only mount. The spec had assumed `HERMES_HOME` could be a ConfigMap mounted read-only, the same trick opencode uses. Hermes v0.10.0 does not have a config/state split: `ensure_hermes_home()` creates `sessions/`, `state.db`, `logs/`, `memories/`, `auth.json` — *everything* — under `$HERMES_HOME`, and there is no key to point the writable state somewhere else. A read-only mount makes hermes fail on its first write. So `HERMES_HOME=/paperclip/agent-bin/.hermes/` is a writable PVC path, and the `config.yaml` template ships as a ConfigMap mounted at `/etc/paperclip/hermes-template/`, seeded into `HERMES_HOME` by a `hermes-init` initContainer on **every** pod boot. An initContainer rather than the shell-sidecar bootstrapper, because the sidecar may not have started before the workload container's first hermes call — the initContainer runs before any app container and writes once, unconditionally.

### The model-shape divergence

Both CLIs route to the same LiteLLM, but they name the model differently, and that difference is load-bearing:

- **opencode** wants the provider-prefixed form: `litellm/qwen-coder-14b`. Bare `qwen-coder-14b` fails with `Model not found`. The slash form is mandatory.
- **hermes** uses a built-in `ollama-cloud` provider that reads `OLLAMA_BASE_URL` + `OLLAMA_API_KEY` from the container env (both pointed at LiteLLM). The seeded `config.yaml` sets `model: "ollama-cloud/qwen-think-14b"` — and that *prefix on the default model* is the trick. It pins `ollama-cloud` as the install's default provider, so when the adapter later invokes a **bare** `-m qwen-think-14b` (no prefix, no `--provider` flag), hermes still routes through LiteLLM instead of falling back to a cloud provider it has no key for. One line in a ConfigMap is what makes the bare invocation work.

### Two wrong turns

True to form, the cluster learned more from the parts that didn't work.

**The wrapper that fixed a non-problem and was itself broken.** The first hermes hire failed, and the error was a `No LLM API keys found in environment` warning. That reads exactly like "you forgot to tell me the provider," so the natural fix was to inject `--provider ollama-cloud`. The operator tried adding it through the UI's `extraArgs` field; Paperclip's schema-driven config form stored `"--provider ollama-cloud"` as a *single* argv token (one string with an embedded space) instead of the two tokens argparse expects. I then misread the whole thing as proof that the adapter's provider whitelist was silently dropping `ollama-cloud`, and built a wrapper script — a ConfigMap + initContainer that shadowed the hermes binary to prepend `--provider ollama-cloud` to every call. That shipped as PR #296. It was wrong twice over: `--provider` is a *subcommand-scoped* flag (`hermes chat --provider X`), so prepending it produced `hermes --provider ollama-cloud chat …`, which argparse rejects because it reads the first positional as the subcommand name. And it was *unnecessary* — the actual first failure was a typo in the model alias (`litelllm`, four L's), and the `ollama-cloud/` default-provider prefix already made the bare invocation route correctly. The wrapper got reverted; the fix was to seed `config.yaml` and document the two UI fields as "do not touch." The real lesson: Phase 1 had probed the hermes CLI in isolation (`--provider ollama-cloud --model …`) but never probed the adapter's *actual* invocation pattern (`-m <bare>`, no `--provider`). Probing the codepath you'll actually run, not the one that's convenient to test by hand, would have caught both the typo's failure mode and the wrapper's pointlessness before any manifest changed.

**The session ID that comes back 16 characters long.** Once hermes hires worked, a second bug surfaced on every agent's *second* heartbeat onward: `Session not found`, exit 1, in about two seconds. The chain is upstream and two-sided. Hermes session IDs are 22 characters (`YYYYMMDD_HHMMSS_<6hex>`); the `hermes-paperclip-adapter` truncates them to a 16-char "display ID" (`parsed.sessionId.slice(0, 16)`). Paperclip's heartbeat logic prefers that display ID over the real one, stores the truncated value, and feeds it back as `--resume <truncated>` next heartbeat — which hermes cannot find. The adapter's stdout regex then mis-captures the word `from` out of hermes's own error message and writes `{"sessionId":"from"}` into the task's session state, permanently, until the agent is flagged `Stranded`. It's tracked at [derio-net/paperclip#1](https://github.com/derio-net/paperclip/issues/1). The operational workaround — hire with `persistSession: false` so hermes starts fresh each heartbeat and the truncation bug never fires — lives in the operating post. opencode, for the record, has no equivalent problem; this is purely a hermes-adapter session-id round-trip defect.

### What this layer taught the cluster

The portable lesson isn't "how to point a CLI at LiteLLM." It's that **two tools solving the same problem will disagree about the boundary between config and state, and the disagreement is where the real design work hides.** opencode wanted read-only config and a binary that wins by PATH order; hermes wanted a writable home and a default-provider prefix doing double duty as a routing directive. Same gateway, same models, opposite mounting strategies. The declarative answer was not one pattern applied twice — it was two patterns, each shaped to the tool's actual behavior, both discovered by running the thing before writing the YAML.

## Recovery Path

| Symptom | Cause | Fix |
|---------|-------|-----|
| Pod never Ready | HTTP probe gets 403 from private mode | Use `tcpSocket` probe instead of `httpGet` |
| Pod stuck Multi-Attach error | Rolling update + RWO PVC | Scale old RS to 0; consider `Recreate` strategy |
| Pod CrashLoopBackOff with exit 137 | OOMKilled — memory limit too low | Check `kubectl logs --previous`; bump limits |
| Pod CrashLoopBackOff with permission errors | `fsGroup` not set | Add `securityContext.fsGroup: 1000` |
| New pod stuck CreateContainerConfigError | Missing secret (optional one not provisioned) | Add `optional: true` to the secretRef |
| SSH unreachable on 192.168.55.221 | Shell sidecar not starting | Check `kubectl logs paperclip -c paperclip-shell` |
| Agent {{< abbr "JWT" >}} missing on first boot | Need to run onboard command | `kubectl exec -n paperclip-system deploy/paperclip -- pnpm paperclipai onboard` |

## References

- [Paperclip](https://github.com/paperclipai/paperclip) — Agent orchestrator
- `apps/paperclip/` — Deployment, values, manifests
- `apps/paperclip-extras/` — Shell sidecar PVC, ConfigMaps
- `apps/paperclip/manifests/configmap-shell-inventory.yaml` — Tool inventory

**Next: [Media Generation — ComfyUI and Stable Diffusion](/docs/building/16-media-generation)**
