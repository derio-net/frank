---
title: "Agentic Control Plane — Sympozium"
date: 2026-03-10
draft: false
tags: ["sympozium", "agents", "ai", "control-plane", "nats", "litellm"]
summary: "A Kubernetes-native control plane where every AI agent is a Pod, every policy is a CRD, and every execution is a Job — orchestrated by Sympozium."
weight: 12
cover:
  image: cover.png
  alt: "Frank the cluster monster commanding a fleet of AI agent pods from a control tower"
  relative: true
---

The cluster can serve models. Phase 10 wired up Ollama and LiteLLM so anything on the network can call an OpenAI-compatible endpoint. But models sitting behind an API are passive — they wait for requests and return responses. They don't act.

Phase 11 adds the layer that makes them act. [Sympozium](https://sympozium.ai/) is a Kubernetes-native agentic control plane. It turns the cluster into something that can reason, plan, and execute — autonomously, on a schedule, or on demand — all governed by Kubernetes-native policy.

## Why Not Just Run Agents in Containers?

You could deploy an agent framework in a Deployment, give it a ServiceAccount, and let it call `kubectl`. That works for one agent. The moment you want multiple agents with different permissions, scheduled runs, policy enforcement, and audit trails, you are reinventing half of what Sympozium provides.

Sympozium maps agentic concepts to Kubernetes primitives:

| Agent Concept | Kubernetes Primitive |
|--------------|---------------------|
| Agent identity | SympoziumInstance (CRD) |
| Execution | AgentRun (CRD) → Pod |
| Policy | SympoziumPolicy (CRD) |
| Skills | SkillPack (CRD) |
| Scheduling | SympoziumSchedule (CRD) |
| Persona bundle | PersonaPack (CRD) |
| Event bus | NATS JetStream (StatefulSet) |

Every agent run is an ephemeral Pod. When it finishes, the Pod exits. Kubernetes handles the lifecycle — retries, timeouts, resource limits. The controller watches AgentRun resources and reconciles them like any other operator.

## The Architecture

Five components run in the `sympozium-system` namespace:

```
                            ┌─────────────────────┐
                            │   Web Dashboard     │
                            │  192.168.55.207:8080│
                            └────────┬────────────┘
                                     │
                            ┌────────▼────────────┐
                            │    API Server        │
                            │  (embedded web UI)   │
                            └────────┬────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
    ┌─────────▼──────────┐ ┌────────▼─────────┐ ┌─────────▼──────────┐
    │  Controller Manager │ │    Webhook       │ │  OTel Collector    │
    │  (reconcile loop)   │ │ (policy enforce) │ │  (observability)   │
    └─────────┬──────────┘ └──────────────────┘ └────────────────────┘
              │
    ┌─────────▼──────────┐
    │   NATS JetStream   │
    │  (durable events)  │
    └────────────────────┘
              │
    ┌─────────▼──────────┐
    │   Agent Pods        │
    │  (ephemeral Jobs)   │──── LiteLLM ──── Ollama / OpenRouter
    └────────────────────┘
```

**Controller Manager** watches for AgentRun CRs and spawns agent Pods. It manages the reconciliation loop — creating, monitoring, and cleaning up agent executions.

**Webhook** intercepts AgentRun creation and enforces SympoziumPolicies before admission. If a run violates a policy (wrong tools, too many sub-agents, sandbox required but not present), the webhook rejects it.

**NATS JetStream** is the internal event bus. Components communicate through durable streams — agent status updates, skill invocations, and inter-agent messages all flow through NATS. The StatefulSet uses a 1Gi Longhorn PVC for message persistence.

**OTel Collector** ships traces and metrics from agent runs to the cluster's observability stack.

**API Server** serves the REST API and embeds the web dashboard.

## PersonaPacks: Agent Bundles

Rather than configuring agents one by one, Sympozium uses PersonaPacks — CRDs that bundle a persona's identity, policy, skills, and schedule into a single resource. When a PersonaPack is applied, the controller stamps out the individual SympoziumInstances, schedules, and configuration.

Two PersonaPacks are deployed:

### Platform Team

| Persona | Policy | Schedule | Purpose |
|---------|--------|----------|---------|
| `sre-agent` | default-policy | Hourly heartbeat | Cluster health checks, resource monitoring |
| `incident-responder` | default-policy | On-demand | Event-triggered diagnostics |

The SRE agent runs every hour via a SympoziumSchedule. It uses the `k8s-ops` SkillPack to interact with the Kubernetes API — listing nodes, checking pod health, reading logs.

### DevOps Essentials

| Persona | Policy | Schedule | Purpose |
|---------|--------|----------|---------|
| `code-reviewer` | restrictive-policy | On-demand | Read-only code analysis |

The code reviewer has a deliberately constrained policy. It can read files and list directories but cannot write, execute commands, or fetch URLs. The restrictive policy enforces this at the webhook level.

## Policy Enforcement

Policies are the key governance primitive. Each SympoziumPolicy CRD defines:

- **Tool gating** — which tools an agent can use (allow, deny, or ask-for-approval)
- **Sub-agent limits** — max depth and concurrency for agent-spawned sub-agents
- **Sandbox requirements** — whether agent Pods must run in a sandbox with CPU/memory limits
- **Network policy** — whether to deny all egress (with exceptions for DNS and the event bus)
- **Feature gates** — enable/disable capabilities like browser automation, code execution, file access

Two policy presets:

```yaml
# default-policy — for trusted ops agents
toolGating:
  defaultAction: allow
  rules:
    - tool: execute_command
      action: ask        # human approval for shell commands
sandboxPolicy:
  required: false
networkPolicy:
  denyAll: false

# restrictive-policy — for dev-facing agents
toolGating:
  defaultAction: deny
  rules:
    - tool: read_file
      action: allow
    - tool: list_directory
      action: allow
    - tool: write_file
      action: deny
sandboxPolicy:
  required: true
  maxCPU: "2"
  maxMemory: 4Gi
networkPolicy:
  denyAll: true
```

The webhook enforces these at admission time. An AgentRun referencing a restrictive-policy persona that attempts to use `write_file` is rejected before the Pod ever starts.

## LLM Routing Through LiteLLM

Agent Pods don't talk directly to Ollama. They route through the LiteLLM gateway from Phase 10:

```
Agent Pod → LiteLLM (litellm.litellm.svc:4000) → Ollama / OpenRouter
```

This means agents automatically benefit from the full model roster — local models on the RTX 5070 and free cloud models via OpenRouter. The LLM API key is managed by an ExternalSecret that syncs a LiteLLM virtual key from Infisical:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: sympozium-llm-key
  namespace: sympozium-system
spec:
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  data:
    - secretKey: OPENAI_API_KEY
      remoteRef:
        key: SYMPOZIUM_LITELLM_KEY
```

No plaintext secrets in the repo. The ExternalSecret refreshes every 5 minutes.

## Deploying with ArgoCD

Three ArgoCD apps:

| App | Source | Purpose |
|-----|--------|---------|
| `cert-manager` | Helm (jetstack) | Webhook TLS certificates |
| `sympozium` | Git (GitHub, chart path) | Core control plane |
| `sympozium-extras` | Raw manifests | Policies, PersonaPacks, ExternalSecret, LB Service |

### cert-manager

Sympozium's webhook needs TLS certificates signed by a trusted CA. cert-manager handles the lifecycle — issuing, renewing, and injecting certificates into the webhook configuration.

```yaml
# apps/root/templates/cert-manager.yaml
annotations:
  argocd.argoproj.io/sync-wave: "-1"  # Deploy before Sympozium
```

### Sympozium Core

The Helm chart is sourced from Git — it is not published to any OCI or Helm registry:

```yaml
sources:
  - repoURL: https://github.com/AlexsJones/sympozium.git
    targetRevision: v0.1.3
    path: charts/sympozium
```

One gotcha: the chart's `appVersion` is `0.1.1` but v0.1.3 images include a critical webhook fix. Override the image tag explicitly:

```yaml
# apps/sympozium/values.yaml
image:
  tag: v0.1.3
```

### sympozium-extras

The chart's built-in service template doesn't support `type` or `annotations` overrides, so the LoadBalancer lives in a separate manifest:

```yaml
# apps/sympozium-extras/manifests/service-lb.yaml
apiVersion: v1
kind: Service
metadata:
  name: sympozium-apiserver-lb
  namespace: sympozium-system
  annotations:
    lbipam.cilium.io/ips: "192.168.55.207"
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/component: apiserver
  ports:
    - name: http
      port: 8080
      targetPort: http
```

## Gotchas

### Git-Sourced Helm Chart

The Sympozium chart is not published to an OCI or Helm registry. ArgoCD must use a Git source with `path: charts/sympozium` instead of `chart:`. This is the same pattern used for the vendored Intel GPU DRA driver chart.

### Image Tag Override

The chart's `appVersion` lags behind the latest tagged release. The v0.1.3 images fix a critical nil-pointer panic in the webhook's PolicyEnforcer (the `Decoder` field was uninitialized). Without the override, agent creation is rejected with `invalid memory address or nil pointer dereference`.

### Service Template Limitations

The chart's apiserver deployment template hardcodes a ClusterIP service with no support for type or annotation overrides. Custom service configuration requires a separate manifest in extras.

### CRD Discovery Timing

After initial deployment, `sympozium-extras` may fail to sync because ArgoCD hasn't discovered the Sympozium CRDs yet. A manual sync of the root app followed by a retry resolves this.

## What is Next

The control plane is running. PersonaPacks are deployed and schedules are active. Agent execution depends on Ollama, which is waiting for a GPU Operator fix on gpu-1 (PCIe link speed resolved, operator pod init sequence in progress).

Once local inference is live, the SRE agent's hourly heartbeat will start producing real cluster health reports. From there: Telegram channel integration for mobile notifications, custom SkillPacks for cluster-specific operations, and connecting agents to the observability stack for closed-loop monitoring.
