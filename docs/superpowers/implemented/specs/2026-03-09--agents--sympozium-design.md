# Sympozium: Agentic Control Plane

## Overview

Deploy [Sympozium](https://sympozium.ai/) (v0.1.1) on Frank as the Agents layer. Sympozium is a Kubernetes-native AI agent orchestration platform where every agent is an ephemeral Pod, every policy is a CRD, and every execution is a Job. It enables both agentic cluster administration (self-healing, diagnostics, scaling) and multi-agent workflow orchestration (code review, data pipelines).

## Architecture

### ArgoCD Applications

| App | Type | Chart/Source | Namespace |
|-----|------|-------------|-----------|
| `cert-manager` | Helm | `jetstack/cert-manager` v1.17.1 from `https://charts.jetstack.io` | `cert-manager` |
| `sympozium` | Helm | `oci://ghcr.io/alexsjones/sympozium/charts/sympozium` v0.1.0 | `sympozium-system` |
| `sympozium-extras` | Raw manifests | `apps/sympozium-extras/manifests/` | `sympozium-system` |

The split follows Frank's existing pattern (e.g., `longhorn` + `longhorn-extras`): Helm chart resources in one ArgoCD app, custom CRs and configuration manifests in another.

### Component Topology

```
┌─────────────────────────────────────────────────────────┐
│ sympozium-system namespace                              │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │  Controller   │  │  API Server  │  │   Webhook     │ │
│  │  Manager      │  │  + Web UI    │  │   Server      │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────────┘ │
│         │                 │                              │
│  ┌──────┴─────────────────┴──────┐                      │
│  │     NATS JetStream (StatefulSet)  │                  │
│  │     Persistent on Longhorn        │                  │
│  └───────────────────────────────┘                      │
│                                                         │
│  ┌──────────────┐  ┌──────────────────────────────────┐ │
│  │  OTel        │  │  Agent Runs (ephemeral Jobs)     │ │
│  │  Collector   │  │  + Skill Sidecars + RBAC         │ │
│  └──────────────┘  └──────────────────────────────────┘ │
│                                                         │
│  PersonaPacks: platform-team, devops-essentials         │
└─────────────────────┬───────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          │  LiteLLM Gateway      │
          │  litellm.litellm.svc  │
          │  :4000/v1             │
          │  (OpenAI-compatible)  │
          └───────────────────────┘
                      │
          ┌───────────┴───────────┐
          │  Ollama (gpu-1)       │  + OpenRouter cloud models
          │  Local inference      │
          └───────────────────────┘
```

### Network Access

| Service | IP | Port | Exposed Via |
|---------|-----|------|-------------|
| Sympozium Web UI | 192.168.55.207 | 8080 | Cilium L2 LoadBalancer |

### LLM Backend

Agents connect to the existing LiteLLM gateway as an OpenAI-compatible endpoint. This gives agents access to both local Ollama models and OpenRouter cloud models without any Sympozium-side reconfiguration when adding new models.

- **Provider**: `openai` (LiteLLM speaks OpenAI API)
- **Base URL**: `http://litellm.litellm.svc.cluster.local:4000/v1`
- **Default model**: `qwen3.5` (local, fast, tool-calling capable)
- **Auth**: Dedicated LiteLLM API key stored in Infisical, synced via ExternalSecret

## ArgoCD App Configuration

### cert-manager

Prerequisite for Sympozium's admission webhook TLS. Deployed as a standalone ArgoCD app with sync wave annotation to ensure it's ready before Sympozium.

Key values:
- `crds.enabled: true` — install cert-manager CRDs
- Minimal configuration — just the base install
- ArgoCD sync wave: `-1` (deploys before Sympozium)

### sympozium (Helm)

Core control plane deployment.

Key values:
```yaml
apiserver:
  webUI:
    enabled: true
    token: ""                # Auto-generates Secret
  service:
    type: LoadBalancer
    annotations:
      lbipam.cilium.io/ips: "192.168.55.207"

nats:
  persistence:
    enabled: true
    storageClass: longhorn
    size: 1Gi

certManager:
  enabled: true

installCRDs: true

networkPolicies:
  enabled: true

observability:
  enabled: true              # Built-in OTel collector
```

### sympozium-extras (Raw Manifests)

Custom resources managed as raw manifests:

1. **ExternalSecret** — Syncs `sympozium-llm-key` from Infisical to `sympozium-system`
2. **SympoziumInstance** — LLM provider config pointing to LiteLLM
3. **PersonaPacks** — `platform-team` and `devops-essentials` built-in packs
4. **SympoziumPolicy** — Per-persona tool policies (Default for ops, Restrictive for dev)
5. **SympoziumSchedule** — Hourly heartbeat for platform-team health checks

## PersonaPacks

### platform-team

SRE/ops agents for cluster diagnostics, scaling, and incident triage.

- **Skills**: `k8s-ops`, `sre-observability`, `incident-response`
- **Tool Policy**: Default (execute_command requires approval)
- **Model**: `qwen3.5` via LiteLLM
- **Schedule**: Every hour (`0 * * * *`) — periodic health checks

### devops-essentials

Development workflow agents for code review and GitOps.

- **Skills**: `code-review`, `github-gitops`
- **Tool Policy**: Restrictive (read-only by default, explicit allowlist)
- **Model**: `qwen3.5` via LiteLLM
- **Schedule**: On-demand only

## Secret Management

### sympozium-llm-key

A dedicated LiteLLM API key for Sympozium agents, stored in Infisical and synced via ExternalSecret to the `sympozium-system` namespace.

```yaml
# manual-operation
id: agents-create-sympozium-llm-key
layer: agents
app: sympozium-extras
plan: docs/superpowers/specs/2026-03-09--agents--sympozium-design.md
when: "Before deploying sympozium-extras — ExternalSecret needs the Infisical source"
why_manual: "Infisical secret creation requires UI/API interaction outside ArgoCD"
commands:
  - "Generate a LiteLLM virtual key: curl -X POST http://192.168.55.206:4000/key/generate -H 'Authorization: Bearer <MASTER_KEY>' -d '{\"key_alias\": \"sympozium\"}'"
  - "Store the generated key in Infisical under path /sympozium/LITELLM_API_KEY"
verify:
  - "kubectl get externalsecret sympozium-llm-key -n sympozium-system — should show SecretSynced"
status: pending
```

### Telegram Bot Token (Deferred)

```yaml
# manual-operation
id: agents-telegram-bot-setup
layer: agents
app: sympozium-extras
plan: docs/superpowers/specs/2026-03-09--agents--sympozium-design.md
when: "When ready to enable Telegram channel — not required for initial deploy"
why_manual: "Telegram BotFather interaction is manual, token must be stored in Infisical"
commands:
  - "Create bot via Telegram BotFather: /newbot, follow prompts"
  - "Store bot token in Infisical under path /sympozium/TELEGRAM_BOT_TOKEN"
  - "Enable Telegram channel in SympoziumInstance manifest and push"
verify:
  - "kubectl get pods -n sympozium-system -l app=sympozium-telegram — should be Running"
status: pending
```

## Gotchas

- **cert-manager ordering**: CRDs must exist before Sympozium deploys. Use ArgoCD sync wave `-1` on cert-manager Application CR.
- **Namespace creation**: `sympozium-system` and `cert-manager` need `CreateNamespace=true` in ArgoCD sync options.
- **NATS on Longhorn**: NATS persistence PVC schedules on control-plane nodes where Longhorn replicas live. No special affinity needed.
- **Web UI token**: Auto-generated on first deploy. Retrieve with `kubectl get secret sympozium-ui-token -n sympozium-system -o jsonpath='{.data.token}' | base64 -d`.
- **Early-stage software**: Sympozium is v0.1.1 — "APIs will change, things will break." Pin chart version, expect breaking changes on upgrades.
- **ServerSideApply**: Required as always for ArgoCD sync options.
- **prune: false**: Manual pruning only, consistent with all Frank apps.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| Sympozium: Agentic Control Plane Implementation Plan | derio-net/superpowers-for-vk | `2026-03-09--agents--sympozium` | — |

## Out of Scope

- PostgreSQL for Sympozium session history — add later if web dashboard needs it
- Custom SkillPacks — start with built-in skills, write custom ones as follow-up
- WhatsApp/Slack/Discord channels — web + deferred Telegram only
- Envoy Gateway / web endpoint skills — future enhancement
- OTel → VictoriaMetrics integration details — wire up after verifying collector output

## References

- [Sympozium GitHub](https://github.com/AlexsJones/sympozium)
- [Sympozium Docs](https://deploy.sympozium.ai/docs)
- [Sympozium Helm Chart](https://deploy.sympozium.ai/docs/reference/helm/)
- [Ollama Integration Guide](https://deploy.sympozium.ai/docs/guides/ollama/)
- [cert-manager Installation](https://cert-manager.io/docs/installation/helm/)
