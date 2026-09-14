---
title: "Paperclip — An AI Agent Orchestrator on Frank"
series: ["building"]
layer: orch
date: 2026-03-14
draft: false
tags: ["paperclip", "agents", "ai", "orchestration", "postgresql", "ghcr", "litellm", "opencode", "hermes"]
summary: "Deploying Paperclip — an AI orchestrator that organises agents into virtual companies with org charts and budgets — alongside Sympozium, to compare two fundamentally different agentic paradigms."
weight: 16
reader_goal: "Deploy Paperclip on Talos with a shell sidecar, work around probe deadlocks, PVC rollout deadlock, fsGroup permissions, and memory tuning, then hire opencode and hermes agents that run on the cluster's own inference through LiteLLM"
diataxis: tutorial
last_updated: 2026-09-13
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

## Hiring Agents on Local Inference

The shell sidecar gave the operator a place to live. The next question was whether the agents Paperclip hires could run on the cluster's own inference instead of a cloud provider. Paperclip ships adapters for [opencode](https://github.com/sst/opencode) (`opencode_local`) and [Hermes](https://github.com/NousResearch/hermes-agent) (`hermes_local`). Both speak an OpenAI-shaped API, and so does LiteLLM (`litellm.litellm.svc:4000`, fronting Ollama on gpu-1).

On paper that is three steps: install the CLI, point it at LiteLLM, name the model. In practice the two CLIs disagree about where config ends and state begins, so each needs a different mounting strategy.

### opencode — config for the binary that wins on PATH

The Paperclip image bakes opencode at `/usr/local/bin/opencode`. The shell inventory also installs `opencode-ai` onto the shared PVC at `/paperclip/agent-bin/node_modules/.bin/opencode`, but the container `PATH` appends the PVC directories *after* the image ones — deliberately, so image-baked binaries win. Check which binary the adapter gets:

```bash
kubectl exec -n paperclip-system deploy/paperclip -c paperclip -- sh -c \
  'which opencode; /usr/local/bin/opencode --version; /paperclip/agent-bin/node_modules/.bin/opencode --version'
```

On 2026-09-13 that printed `1.18.23` for the image binary and `1.15.3` for the PVC copy. When this wiring was built in May the image binary was the older of the two; upstream image bumps have since overtaken the PVC install, which is now a stale leftover rather than a newer fallback. Pinning config to one path would have broken on that flip. Wiring it to the binary that wins does not.

So the config goes wherever the winning binary reads it. opencode reads `$XDG_CONFIG_HOME/opencode/opencode.json`, and the Deployment points that at a read-only ConfigMap:

```yaml
env:
  - name: XDG_CONFIG_HOME
    value: /etc/paperclip/opencode-base
volumeMounts:
  - name: opencode-config                 # ConfigMap paperclip-opencode
    mountPath: /etc/paperclip/opencode-base/opencode/opencode.json
    subPath: opencode.json
```

The ConfigMap holds a `provider.litellm` block (`@ai-sdk/openai-compatible`, `baseURL: http://litellm.litellm.svc:4000/v1`, `apiKey: "{env:LITELLM_API_KEY}"`) plus the model aliases LiteLLM serves.

The adapter rewrites opencode's runtime config on every run, which raised the obvious fear that it would clobber the provider block. It does not: `packages/adapters/opencode-local/src/server/runtime-config.ts` copies the source config directory with `fs.cp` and then merges only the `permission` key over the existing config. The provider block survives untouched — re-checked against image `sha-8e6edcd`.

### hermes — a writable home seeded on every boot

Hermes wanted the opposite of a read-only mount. Hermes v0.10.0 has no config/state split: `ensure_hermes_home()` creates `sessions/`, `state.db`, `logs/`, `memories/` and `auth.json` under `$HERMES_HOME`, and no key points the state anywhere else. A read-only ConfigMap at `HERMES_HOME` fails on the first write.

So `HERMES_HOME=/paperclip/agent-bin/.hermes` lives on the writable PVC, and the template ships as a ConfigMap that an initContainer copies in on **every** pod boot:

```yaml
initContainers:
  - name: hermes-init
    command: ["sh", "-c"]
    args:
      - |
        mkdir -p /paperclip/agent-bin/.hermes /paperclip/agent-bin/bin
        cp /etc/paperclip/hermes-template/config.yaml /paperclip/agent-bin/.hermes/config.yaml
        if [ -e /paperclip/agent-bin/hermes-agent/venv/bin/hermes ]; then
          rm -f /paperclip/agent-bin/bin/hermes
          ln -s /paperclip/agent-bin/hermes-agent/venv/bin/hermes /paperclip/agent-bin/bin/hermes
        fi
```

An initContainer rather than the shell sidecar's reconcile, because the sidecar may not have started before the app container's first hermes call — an initContainer always finishes before any app container starts. The seeded `config.yaml` is one line that matters:

```yaml
model: "ollama-cloud/qwen-think-14b"
```

Hermes' built-in `ollama-cloud` provider reads `OLLAMA_BASE_URL` and `OLLAMA_API_KEY` from the container env, and the Deployment points both at LiteLLM (`http://litellm.litellm.svc:4000/v1` and the `LITELLM_API_KEY` secret).

### Two model shapes through one gateway

Both CLIs reach the same LiteLLM, but the hire payload names the model differently, and the difference is load-bearing:

| Adapter | Model field | Why |
|---|---|---|
| `opencode_local` | `litellm/qwen-coder-14b` | provider-prefixed form is mandatory; bare `qwen-coder-14b` fails with `Model not found` |
| `hermes_local` | `qwen-think-14b` | bare; the `ollama-cloud/` prefix lives in the seeded `config.yaml` |

The hermes half works for a narrower reason than it first appears. The adapter passes `-m <model>` and then **always** adds `--provider <resolved>` unless the resolved provider is `auto`. Resolution walks a priority chain in `packages/adapters/hermes/src/server/detect-model.ts`: an explicit provider from the hire payload (only if it is in `VALID_PROVIDERS`), then the Hermes config file (only if its model matches the requested one), then a model-name prefix table, then `auto`.

For a bare `qwen-think-14b` the prefix table entry `["qwen", "auto"]` wins, so no `--provider` flag is passed and Hermes falls back to the default provider its `config.yaml` implies — `ollama-cloud`, i.e. LiteLLM. Confirm the bare invocation routes, using the shim path the adapter invokes:

```bash
kubectl exec -n paperclip-system deploy/paperclip -c paperclip -- \
  /paperclip/agent-bin/bin/hermes chat -q "say ack" -Q -m qwen-think-14b
```

The same table sends other alias families somewhere else entirely. Per `packages/adapters/hermes/src/shared/constants.ts` at image `sha-8e6edcd`, matching is `startsWith` on the model name (after any `provider/` part is stripped), and these prefixes force a cloud provider: `claude` → `anthropic`; `gpt-4`, `o1-`, `o3-`, `o4-` → `openai-codex`; `gpt-5` → `copilot`; `hermes-` → `nous`; `glm-` → `zai`; `moonshot`, `kimi` → `kimi-coding`; `minimax` → `minimax`. A LiteLLM alias starting with any of them gets a forced `--provider` and bypasses the gateway. `qwen`, `mistral`, `llama`, `deepseek` and `gemini` map to `auto`, and `gemma` matches nothing and also falls through to `auto`. Name local aliases accordingly, and re-read the table after a Paperclip image bump.

## Missteps

| What Happened | Why It Was Wrong | How We Fixed It | Commit |
|---------------|-----------------|-----------------|--------|
| **HTTP probes get 403 in private mode** — kubelet probes from node IP, but Paperclip's `/` returns 403 to non-localhost | Paperclip's `private` exposure denies all non-localhost HTTP | Switched from `httpGet` to `tcpSocket` probes | — |
| **PVC rollout deadlock** — new pod cannot attach RWO PVC until old pod releases it; rolling update creates new pod first | Default `RollingUpdate` strategy creates new pod before terminating old one | Scale old ReplicaSet to zero manually; or use `Recreate` strategy | — |
| **fsGroup missing — PVC owned by root** — `node` user (uid 1000) cannot write to `/paperclip` | Dockerfile `chown` runs at image build, does not re-run on PVC mount | Added `fsGroup: 1000` to pod securityContext | — |
| **Initial memory limit 1Gi too low** — container OOMKilled under agent load | Memory guess inherited from fork-era image, never re-validated | Bumped to 12Gi on gpu-1 | — |
| **arm64-only image pushed** — build machine defaulted to native arch; cluster nodes are amd64 | `docker buildx build` without `--platform linux/amd64` | Added explicit platform flag | — |
| **Optional secrets blocking rollout** — missing `imagePullSecret` caused `CreateContainerConfigError`, old pod stayed alive with PVC locked | Any `secretRef` for a non-essential feature should be `optional: true` | Marked optional secrets with `optional: true` | — |
| **A `--provider` wrapper for hermes** — the first hermes hire warned `No LLM API keys found in environment`, which read like a missing provider, so a ConfigMap + initContainer shadowed the binary to prepend `--provider ollama-cloud` | `--provider` is scoped to the `chat` subcommand, so `hermes --provider ollama-cloud chat …` is rejected by argparse. It was also unnecessary: the real failure was a typo in the model alias (`litelllm`), and the `ollama-cloud/` default already routed bare invocations | Reverted the wrapper from #296 in #297; seeded `config.yaml` instead | #297 |
| **Probed the convenient CLI path, not the adapter's** — the pre-manifest probe ran `hermes chat --provider ollama-cloud --model …` by hand | The adapter invokes `-m <bare alias>` with no `--provider`, so the probe never exercised the path that failed | Smoke-test with the adapter's own invocation shape (see the bare-alias command above) | — |
| **hermes agents strand from their second heartbeat** — `Session not found`, exit 1 in ~2s | Upstream: the adapter truncates Hermes' 22-char session ID to a 16-char display ID (`execute.ts`, `parsed.sessionId.slice(0, 16)`), Paperclip stores it and replays it as `--resume`; the output regex then captures the word `from` as the session ID. Tracked at [derio-net/paperclip#1](https://github.com/derio-net/paperclip/issues/1), still open | Hire `hermes_local` agents with `persistSession: false`; recovery for already-stranded agents is in the operating post | — |

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
| opencode agent fails `Model not found` | Bare alias in the hire payload | Use the provider-prefixed `litellm/<alias>` form |
| hermes agent reaches a cloud provider or warns `No LLM API keys found` | `config.yaml` not seeded, or the alias matches a non-`auto` prefix hint and gets a forced `--provider` | Check `kubectl exec -n paperclip-system deploy/paperclip -c paperclip -- cat /paperclip/agent-bin/.hermes/config.yaml`; rename the LiteLLM alias away from `claude`/`gpt-`/`o1-`/`o3-`/`o4-`/`hermes-`/`glm-`/`moonshot`/`kimi`/`minimax` prefixes |
| hermes fails on its first write | `HERMES_HOME` mounted read-only | Keep `HERMES_HOME` on the PVC; seed config via the `hermes-init` initContainer |
| hermes agent fails from the second heartbeat with `Session not found` | Session-ID truncation ([derio-net/paperclip#1](https://github.com/derio-net/paperclip/issues/1)) | Hire with `persistSession: false` |

## What Transfers

Wiring two agent CLIs to one gateway taught three things that apply well beyond Paperclip:

- **Find where a tool splits config from state before you choose a mount.** opencode separates them, so a read-only ConfigMap works. Hermes keeps both under one home directory, so it needs a writable volume that an initContainer seeds on every boot. The same trick applied to both tools would have failed one of them.
- **Wire configuration to the binary that actually runs, not to a version you pinned once.** The image-baked opencode and the PVC copy swapped which one was newer within four months. Config keyed to `PATH` resolution survived that; config keyed to a path would not have.
- **Probe the caller's invocation, not the convenient one.** The hand-run `--provider` probe passed while the adapter's bare `-m` call was the path that failed. Read the adapter's argument builder, then smoke-test with exactly those arguments.

## References

- [Paperclip](https://github.com/paperclipai/paperclip) — Agent orchestrator
- [Operating on Paperclip]({{< relref "/docs/operating/18-paperclip" >}}) — smoke tests, hiring, and stranded-agent recovery
- `apps/paperclip/` — Deployment, values, manifests (including the shell sidecar's `pvc-shell-home.yaml` and ConfigMaps)
- `apps/paperclip/manifests/configmap-shell-inventory.yaml` — Tool inventory
- `apps/paperclip/manifests/configmap-opencode.yaml` — opencode LiteLLM provider block
- `apps/paperclip/manifests/configmap-hermes.yaml` — hermes `config.yaml` template
- [derio-net/paperclip#1](https://github.com/derio-net/paperclip/issues/1) — hermes session-ID truncation

**Next: [Media Generation — ComfyUI and Stable Diffusion](/docs/building/16-media-generation)**
