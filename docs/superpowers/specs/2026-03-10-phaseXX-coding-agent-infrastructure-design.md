# PhaseXX — Autonomous Coding Agent Infrastructure — Design

**Date:** 2026-03-10

## Overview

Deploy a full autonomous coding agent pipeline on Frank. Aider runs as K8s Jobs on gpu-1, orchestrated by n8n workflows. Gitea provides local Git hosting with GitHub Actions-compatible CI/CD. Harbor serves as the container and artifact registry. The two desktop workers (pc-1, pc-2) form a new CI/CD scheduling zone optimized for disk-heavy, latency-tolerant workloads.

## Goals

- Agents autonomously pick up tasks, write code, open PRs, and run CI — with human review before merge
- All infrastructure runs on-cluster, declaratively managed via ArgoCD
- GPU remains dedicated to inference (Ollama); agent orchestration uses CPU/RAM
- CI/CD and artifact storage lands on the desktop workers, keeping the minis and gpu-1 focused

## Architecture

```
GitHub Issue / n8n trigger / manual
        │
        ▼
   n8n workflow (192.168.55.208)
        │  creates K8s Job
        ▼
   Aider Job (gpu-1)
        │  clones from Gitea, codes, commits
        │  LLM calls → LiteLLM → Ollama
        ▼
   Push branch + open PR on Gitea
        │
        ▼
   Gitea Actions runners (pc-1/pc-2)
        │  run tests, lint, build
        ▼
   Artifacts → Harbor (pc-1/pc-2)
        │
        ▼
   n8n notification (Telegram / dashboard)
        │
        ▼
   Human review & merge
```

## Components

### Aider (Coding Agent)

**What:** AI coding assistant that edits files, runs commands, and auto-commits with descriptive messages. Runs headless as K8s Jobs.

**Image:** `paulgauthier/aider-full`

**Execution model:** Each task = one K8s Job on gpu-1. The Job:
1. Clones the target repo from Gitea (init container)
2. Runs `aider --message "<task>" --yes --no-stream --no-pretty`
3. Pushes a feature branch and opens a PR via Gitea API
4. Exits (ephemeral Pod)

**Scheduling:**
- `nvidia.com/gpu: 0` — does not claim GPU (Ollama owns it)
- Tolerates gpu-1's NoSchedule taint
- Node affinity to gpu-1 for lowest-latency LLM calls to co-located Ollama

**LLM backend:** LiteLLM gateway at `http://litellm.litellm.svc.cluster.local:4000/v1` (OpenAI-compatible). Aider natively supports OpenAI-compatible endpoints.

**Configuration (via env vars / ConfigMap):**
- `AIDER_MODEL` — model to use (e.g., `openai/qwen3.5` via LiteLLM)
- `OPENAI_API_BASE` — `http://litellm.litellm.svc.cluster.local:4000/v1`
- `OPENAI_API_KEY` — LiteLLM virtual key (from Infisical via ExternalSecret)
- `AIDER_YES=true` — auto-confirm all prompts
- `AIDER_AUTO_COMMITS=true` — commit changes automatically
- `AIDER_NO_STREAM=true` — disable streaming for log capture

### n8n (Workflow Orchestration)

**What:** Low-code workflow automation platform. Serves as the agent control panel — triggers Aider Jobs, monitors progress, sends notifications.

**Chart:** [8gears/n8n](https://artifacthub.io/packages/helm/n8n/n8n)

**Namespace:** `n8n`

**Service:** LoadBalancer at `192.168.55.208`, port 5678

**Scheduling:** Runs on minis (control-plane nodes). Lightweight, needs reliability over raw compute.

**Storage:** PostgreSQL on Longhorn NVMe PVC (workflow state, execution history).

**Key workflows:**
1. **GitHub webhook → Aider Job** — new issue labeled `agent` triggers a coding run
2. **Scheduled batch** — process a queue of tasks at defined intervals
3. **PR status monitor** — watch Gitea Actions results, notify on completion
4. **Manual trigger** — kick off ad-hoc tasks via n8n dashboard

**IaC approach:** Workflow JSON files stored in Git (`apps/n8n/workflows/`). Imported via init container or n8n CLI on startup.

**Secrets (via Infisical → ExternalSecret):**
- `N8N_ENCRYPTION_KEY` — workflow credential encryption
- Gitea API token
- LiteLLM API key (for direct LLM calls from workflows if needed)
- Telegram bot token (for notifications)

### Gitea (Git Hosting + Issue Tracker)

**What:** Lightweight, self-hosted Git forge. GitHub-compatible API. Built-in issue tracker and pull request workflow.

**Chart:** [gitea/gitea](https://gitea.com/gitea/helm-chart)

**Namespace:** `gitea`

**Service:** LoadBalancer at `192.168.55.209`, port 3000 (web) + port 22 (SSH)

**Scheduling:** Runs on pc-1/pc-2 (CI/CD zone). Node affinity to desktop workers.

**Storage:** Longhorn-HDD PVC (2 replicas across pc-1 and pc-2) for:
- Git repositories
- LFS objects
- PostgreSQL database

**Configuration:**
- OAuth2 / local auth (decide during implementation)
- Webhook integration with n8n
- Repository mirroring from GitHub (optional — sync upstream repos for local agent work)

### Gitea Actions (CI/CD Runners)

**What:** GitHub Actions-compatible CI/CD. Runners execute workflow YAML files using the same syntax as GitHub Actions.

**Runner image:** `gitea/act_runner`

**Execution model:** DaemonSet or Deployment on pc-1/pc-2. Runners register with Gitea and pick up jobs from a queue.

**Scheduling:** Runs on pc-1/pc-2. CI workloads are bursty, CPU+disk heavy — the desktops handle this well.

**Container execution:** Runners need to build and run containers for CI steps. Options:
- **DinD sidecar** — Docker-in-Docker (privileged, but isolated to CI zone)
- **Kaniko** — for container image builds without Docker daemon
- Decision deferred to implementation phase based on Talos compatibility testing

### Harbor (Container + Artifact Registry)

**What:** Cloud-native container registry with vulnerability scanning, RBAC, replication, and support for Helm charts, OCI artifacts, and container images.

**Chart:** [goharbor/harbor-helm](https://github.com/goharbor/harbor-helm)

**Namespace:** `harbor`

**Service:** LoadBalancer at `192.168.55.210`, port 443 (HTTPS)

**Scheduling:** Runs on pc-1/pc-2. Image storage is disk-intensive, HDD is acceptable for a local registry.

**Storage:** Longhorn-HDD PVCs for:
- Registry blob storage (bulk of disk usage)
- PostgreSQL database
- Redis (can use emptyDir or small PVC)
- Trivy vulnerability database

**Configuration:**
- Self-signed TLS or cert-manager issued certificate
- Containerd mirror config on all nodes (Talos machine patch) so the cluster pulls from Harbor
- Robot accounts for Aider Jobs and Gitea Actions runners
- Automatic vulnerability scanning on push

## Node Topology

| Node | Zone | Role in Phase 12 | Key Resources |
|------|------|-------------------|---------------|
| mini-1/2/3 | Core | n8n, LiteLLM (existing) | NVMe, 64GB RAM each |
| gpu-1 | AI Compute | Ollama (existing), Aider Jobs | i9, 128GB RAM, RTX 5070 |
| pc-1 | CI/CD | Gitea, Gitea Actions runners, Harbor | ~32GB RAM, HDD storage |
| pc-2 | CI/CD | Gitea, Gitea Actions runners, Harbor | ~32GB RAM, HDD storage |

## Storage Strategy

| Zone | Backing | StorageClass | Replication | Use |
|------|---------|-------------|-------------|-----|
| Core (minis) | NVMe | `longhorn` (existing) | 3 replicas | Databases, n8n state |
| AI Compute (gpu-1) | SSD | `longhorn` (existing) | As configured | Ollama models |
| CI/CD (pc-1/pc-2) | HDD | `longhorn-hdd` (new) | 2 replicas | Git repos, container images, CI artifacts |

**Note:** Exact disk capacity on pc-1 and pc-2 must be audited before implementation. The 2-replica Longhorn-HDD strategy assumes sufficient and roughly symmetric storage on both machines.

## Network — New Cilium L2 IPs

| Service | IP | Port |
|---------|-----|------|
| n8n | 192.168.55.208 | 5678 |
| Gitea | 192.168.55.209 | 3000 (HTTP), 22 (SSH) |
| Harbor | 192.168.55.210 | 443 (HTTPS) |

## Secrets (all via Infisical → ExternalSecret)

| Secret | Namespace | Purpose |
|--------|-----------|---------|
| `aider-llm-key` | `aider` | LiteLLM virtual key for Aider Jobs |
| `n8n-secrets` | `n8n` | Encryption key, API tokens |
| `gitea-admin` | `gitea` | Admin credentials |
| `harbor-admin` | `harbor` | Admin credentials |
| `harbor-tls` | `harbor` | TLS certificate (or cert-manager) |

## ArgoCD Integration

### File Structure

```
apps/aider/manifests/           # Job template, RBAC, ConfigMap, ExternalSecret
apps/n8n/values.yaml            # n8n Helm values
apps/n8n/workflows/             # Workflow JSON files (IaC)
apps/n8n/manifests/             # ExternalSecret, additional config
apps/gitea/values.yaml          # Gitea Helm values
apps/gitea/manifests/           # ExternalSecret, runner config
apps/harbor/values.yaml         # Harbor Helm values
apps/harbor/manifests/          # ExternalSecret, robot accounts
apps/root/templates/n8n.yaml    # Application CR
apps/root/templates/gitea.yaml  # Application CR
apps/root/templates/harbor.yaml # Application CR
apps/root/templates/aider.yaml  # Application CR (manifests-only)
```

### Sync Policy (all apps)

```yaml
syncPolicy:
  automated:
    prune: false
    selfHeal: true
  syncOptions:
    - ServerSideApply=true
    - RespectIgnoreDifferences=true
    - CreateNamespace=true
```

## Implementation Sequence

1. **Storage** — Add pc-1/pc-2 to cluster, configure `longhorn-hdd` StorageClass
2. **Gitea** — Deploy Gitea + PostgreSQL on CI/CD zone
3. **Gitea Actions** — Deploy runners on pc-1/pc-2, verify CI pipeline works
4. **Harbor** — Deploy registry, configure containerd mirrors on all nodes
5. **n8n** — Deploy on minis, build initial workflows
6. **Aider** — Create Job template, ExternalSecret, test manual runs
7. **Integration** — Wire n8n → Aider → Gitea → Gitea Actions → Harbor end-to-end
8. **Notifications** — Telegram bot for PR/CI status updates

## Out of Scope

- GitHub mirroring (sync repos between GitHub and Gitea) — future enhancement
- Multiple concurrent Aider agents (start with one-at-a-time, scale later)
- Custom Aider Docker image (use upstream `paulgauthier/aider-full` initially)
- SonarQube or advanced static analysis — add as a Gitea Actions step later
- Sympozium integration with this pipeline
- Production TLS with external CA (self-signed or cert-manager internal is fine for homelab)

## Open Questions

- Exact disk capacity on pc-1 and pc-2 (determines Longhorn-HDD sizing)
- DinD vs Kaniko for container builds in Gitea Actions on Talos
- Whether to mirror GitHub repos to Gitea or work exclusively on Gitea
- Telegram bot setup for n8n notifications (reuse Sympozium's bot or create a new one)

## References

- [Aider Docker](https://aider.chat/docs/install/docker.html)
- [Aider Scripting](https://aider.chat/docs/scripting.html)
- [n8n Helm Chart](https://artifacthub.io/packages/helm/n8n/n8n)
- [Gitea Helm Chart](https://gitea.com/gitea/helm-chart)
- [Gitea Actions](https://docs.gitea.com/usage/actions/overview)
- [Harbor Helm Chart](https://github.com/goharbor/harbor-helm)
- [Harbor Installation](https://goharbor.io/docs/latest/install-config/)
