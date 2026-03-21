# Sympozium Agent PodSecurity, LLM Routing & Developer PersonaPack (Extension)

**Date**: 2026-03-10
**Layer**: agents (extension)
**Status**: Implementation

## Problem Statement

Three issues prevent Sympozium agents from functioning:

1. **PodSecurity blocks agent pods**: The `frankie` SympoziumInstance uses the `llmfit` SkillPack, which injects sidecars requiring `hostPID: true` and `hostPath` volumes. The `sympozium-system` namespace defaults to `baseline` PodSecurity, rejecting these pods. All AgentRun jobs fail at pod creation with: `violates PodSecurity "baseline:latest": host namespaces (hostPID=true), hostPath volumes`.

2. **Missing LLM base URL**: PersonaPack-generated SympoziumInstances don't receive a `baseURL` because the PersonaPack CRD has no `baseURL` field. Without it, agents default to `https://api.openai.com/v1` instead of the in-cluster LiteLLM gateway. Since the auth secret contains a LiteLLM virtual key (not an OpenAI key), all LLM calls fail.

3. **No developer-team PersonaPack**: Only platform-team and devops-essentials are deployed. The built-in developer-team (7-persona "2-pizza dev team") from the Sympozium chart is not deployed.

## Investigation Findings

### Agent Namespace Constraint

Sympozium agent pods run in the **same namespace** as the controller. The controller reads its namespace from the downward API (`metadata.namespace`) and has no `--agent-namespace` flag. Creating a separate `sympozium-agents` namespace would not redirect agent pods — the fix must apply to `sympozium-system` directly.

### baseURL: PersonaPack CRD Limitation

| CRD | Has baseURL? | Notes |
|-----|-------------|-------|
| SympoziumInstance | Yes (`spec.agents.default.baseURL`) | Works on manually created instances (e.g. `frankie`) |
| PersonaPack | No | No field at persona or pack level; generated instances lack baseURL |

### Auth Secret Injection (Key Finding)

The controller injects the auth secret using `envFrom` with `SecretRef` (`agentrun_controller.go:1352-1363`). This means **every key in the referenced Secret becomes an environment variable** in the agent container. Adding `OPENAI_BASE_URL` to the `sympozium-llm-key` secret will propagate it to all agent pods without needing standalone SympoziumInstances.

### Built-in Developer Team

The Sympozium chart includes a built-in `developer-team` PersonaPack at `charts/sympozium/files/personas/developer-team.yaml` with 7 personas: tech-lead, backend-dev, frontend-dev, qa-engineer, code-reviewer, devops-engineer, docs-writer. It ships without `authRefs` or `policyRef` — these must be added for deployment.

Our values have `defaultPersonas.enabled: false`, so the built-in is not deployed. We create a customized version in sympozium-extras.

## Solution

### Task 1 — Namespace PodSecurity Label

Create a declarative Namespace manifest for `sympozium-system` with `pod-security.kubernetes.io/enforce: privileged`. This allows agent pods using the `llmfit` SkillPack (which requires `hostPID` and `hostPath`) to pass PodSecurity admission.

**File**: `apps/sympozium-extras/manifests/namespace.yaml`

### Task 2 — LLM Base URL via ExternalSecret Template

Add `OPENAI_BASE_URL: http://litellm.litellm.svc:4000` to the `sympozium-llm-key` Secret using the ExternalSecret `target.template` feature. This injects the LiteLLM endpoint into all agent pods via the controller's `envFrom` mechanism.

**File**: `apps/sympozium-extras/manifests/external-secret.yaml` (modify)

### Task 3 — Developer Team PersonaPack

Deploy a customized version of the built-in developer-team PersonaPack in sympozium-extras with:
- `authRefs` pointing to `sympozium-llm-key`
- `policyRef: default-policy`
- `model: qwen3.5` on all personas (matching other packs)
- Schedules adjusted for homelab resources (longer intervals)

**File**: `apps/sympozium-extras/manifests/personapack-developer-team.yaml`

### Task 4 — Blog Update

Update the Sympozium blog post to document the PodSecurity fix, LLM routing via secret injection, and the developer-team deployment.

**File**: `blog/content/posts/11-agentic-control-plane/index.md`

## Files

| Action | File | Purpose |
|--------|------|---------|
| Create | `apps/sympozium-extras/manifests/namespace.yaml` | Privileged PodSecurity on sympozium-system |
| Modify | `apps/sympozium-extras/manifests/external-secret.yaml` | Add OPENAI_BASE_URL to auth secret |
| Create | `apps/sympozium-extras/manifests/personapack-developer-team.yaml` | Developer team (7 personas) |
| Modify | `blog/content/posts/11-agentic-control-plane/index.md` | Document fixes and new pack |
