# Deploy hermes-agent-shell pod on Frank (gpu-1)

> **For VK agents:** use vk-execute to implement assigned phases.
> **For local execution:** subagent-driven-development or executing-plans.
> **For dispatch:** vk-dispatch to create Issues from this plan.

**Spec:** `docs/superpowers/specs/2026-06-03--orch--hermes-agent-shell-deploy-design.md`
**Layer:** `orch` (15 — AI Agent Orchestrator)
**Status:** Deployed

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

## Deployment Deviations

### 2026-06-04 — hermes provider pinning (P2.T2.S3 follow-up)

The spec assumed hermes consumes `OPENAI_BASE_URL`/`OPENAI_API_KEY` directly
(BYOK). On v0.15.2 those env vars do NOT drive chat inference: provider
`auto` resolves to openrouter and the first real `hermes` run 401'd
(`Missing Authentication header`, endpoint `https://openrouter.ai/api/v1`).
The T2.S3 verification (MOTD row + `--version` + `curl $OPENAI_BASE_URL`)
all passed while the actual inference path was broken — none of the three
exercised a chat completion.

Fix: pin the default provider in `~/.hermes/config.yaml` (home-PVC state,
seeded manually — manual-op `orch-hermes-config-provider` in the spec):
`model:` as a mapping (`default: mistral-small-24b`, `provider: litellm`)
plus `providers: { litellm: { base_url: http://litellm.litellm.svc:4000/v1,
key_env: OPENAI_API_KEY } }`. Model-string prefix forms (`litellm/<alias>`,
`custom/<alias>`, `custom:litellm:<alias>`) do NOT pin the provider on this
build. Verified live: bare `hermes chat -Q -q …` answers through LiteLLM
(`provider=custom base_url=http://litellm.litellm.svc:4000/v1` in hermes
logs). Full prose: `docs/runbooks/frank-gotchas/agent-shells.md` (BYOK
provider-pinning section). Lesson folded into the verification habit: a
BYOK layer's e2e check must include one real chat completion, not just
endpoint reachability.

### 2026-06-04 (later) — LiteLLM `ollama/` breaks tools+streaming (cluster-wide fix)

After provider pinning, interactive hermes wrapped EVERY reply in fake
tool-call JSON (`{"name": "text_to_speech", …}`). Isolation: `-t none` →
clean text; non-stream curl with tools → proper native `tool_calls`;
**stream + tools → scaffold JSON leaks into `content`, zero `tool_calls`
deltas**. Root cause is LiteLLM's `ollama/` provider (prompt-based function
calling, re-parsed only non-streamed) — hermes always streams. Fixed by
flipping all 7 local aliases in `apps/litellm/values.yaml` to `ollama_chat/`
(native /api/chat tool calling, stream-safe). Affects every tool-using
LiteLLM consumer, not just hermes. Gotcha: LiteLLM entry in
`docs/runbooks/frank-gotchas/other-apps.md`; testing lesson — always probe
the STREAMING path when validating tool-calling.
