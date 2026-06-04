# Deploy hermes-agent-shell pod on Frank (gpu-1)

> **For VK agents:** use vk-execute to implement assigned phases.
> **For local execution:** subagent-driven-development or executing-plans.
> **For dispatch:** vk-dispatch to create Issues from this plan.

**Spec:** `docs/superpowers/specs/2026-06-03--orch--hermes-agent-shell-deploy-design.md`
**Layer:** `orch` (15 — AI Agent Orchestrator)
**Status:** Not Started

**Goal:** Stand up a standalone, SSH-able shell pod on `gpu-1` running the Nous
Research `hermes` agent, wired BYOK to Frank's in-cluster LiteLLM gateway, with
PV-resident state. Consumes the `hermes-agent-shell` image just delivered by the
`agent-images` agent-shells-batch feature (pinned at the cluster-wide
agent-images SHA `95e719b`).

**Context:** Modeled on `secure-agent-pod` (the existing standalone
interactive-shell pod); secret/inventory/MOTD wiring borrowed from
`paperclip-shell` / `ruflo-shell`. This is NOT the in-paperclip hermes shim — it
is a dedicated pod whose only job is hosting `hermes` interactively.

## Architecture

```
agent-base
└── agent-shell-base
    └── hermes-agent-shell   ← deployed here (BYOK → litellm.litellm.svc:4000/v1)
```

Single-container Deployment on `gpu-1` (no GPU requested — inference is remote
via LiteLLM; gpu-1 chosen as Frank's largest CPU/RAM box). Combined SSH+Mosh
LoadBalancer on `192.168.55.226` (TCP 22→2222, UDP 60032–60047). 20Gi Longhorn
home PVC at `/home/agent` holding `~/.hermes/`.

## Two-phase shape

```
Phase 1 (manual)   LiteLLM virtual key + Infisical entry; SOPS ssh-keys prep   depends_on: []
Phase 2 (agentic)  manifests + deploy + apply secret + verify + post-deploy    depends_on: [1]
```

Phase 1 is pure prep with no cluster-ordering hazard. The `kubectl apply` of the
SOPS ssh-keys secret deliberately lands in Phase 2/T2 because it needs the
namespace ArgoCD creates first. The pod boots even before Phase 1 completes
(both secret refs are `optional: true`) — it just can't reach LiteLLM and sshd
accepts no keys until the bootstraps land. That is the declarative-only
bootstrap exception, by design.

## Critical wiring note — sshd env-scrub

`agent-shell-base`'s sshd runs `UsePAM no` with no `PermitUserEnvironment`, so
the K8s-injected BYOK env (`OPENAI_BASE_URL` / `OPENAI_API_KEY` on PID 1) does
NOT reach an interactive SSH/Mosh login shell. Without a fix, `hermes` launched
from the shell silently can't reach LiteLLM (and the image's own MOTD prints
"OPENAI_BASE_URL not set" despite the manifest setting it). Phase 2 ships a
ConfigMap-mounted profile.d shim (`35-hermes-agent-shell-byok-env.sh`) that
re-exports the env from `/proc/1/environ` for login shells — the same `subPath`
mechanism paperclip uses for its tips drop-in, so no `agent-images` change is
needed. Non-interactive `ssh host -- cmd` stays env-less by design (use
`kubectl exec`).

## Manual operations

Two `# manual-operation` blocks (documented in the spec, synced via
`/sync-runbook` in Phase 2/T3.S5):

- `orch-hermes-litellm-virtual-key` — mint a LiteLLM virtual key, store as
  `HERMES_LITELLM_KEY` in Infisical.
- `orch-hermes-shell-ssh-keys` — build + SOPS-encrypt + apply the
  `hermes-agent-shell-ssh-keys` Secret.

## Post-deploy

Standard checklist minus Step 1 (the shell is SSH/Mosh-only — no web exposure,
no homepage tile; the `frank-infrastructure.md` service-table row is still
added). Building + operating blog posts (`orch` layer), README sync, runbook
sync, status → Deployed after end-to-end observation.
