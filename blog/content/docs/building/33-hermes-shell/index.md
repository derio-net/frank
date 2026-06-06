---
title: "Hermes Agent Shell — A BYOK Pod That Ignored Its Own Keys"
date: 2026-06-06
draft: false
tags: ["hermes", "nous-research", "agents", "ai", "byok", "litellm", "agent-shell-base", "ssh", "mosh", "ollama"]
summary: "Deploying Nous Research's hermes CLI as a dedicated SSH/Mosh shell pod on gpu-1 — and discovering that BYOK env vars, an sshd env-scrub, and LiteLLM's ollama/ prefix all conspire against the first chat completion."
weight: 34
---

Layer 15 keeps growing tenants. [Paperclip]({{< relref "/docs/building/15-paperclip" >}}) runs the org-chart agents, [Ruflo]({{< relref "/docs/building/29-ruflo" >}}) runs the chaotic swarm, and now there's a third lodger: [hermes](https://github.com/NousResearch/hermes), Nous Research's terminal-native agent CLI. Not embedded in either orchestrator — a dedicated pod whose only job is hosting `hermes` interactively, the way `secure-agent-pod` hosts Claude Code.

The deployment itself is the boring part, and I mean that as a compliment: the `agent-shell-base` lineage from the [agent-images]({{< relref "/docs/building/28-agent-images-sidecar" >}}) work means a new agent shell is mostly a values file and a Service. What this post is actually about is the three-act failure chain between "pod is Healthy" and "hermes answers a question" — an sshd that scrubs the environment, a CLI that ignores the environment, and a gateway prefix that corrupts the answers. All three passed their surface checks.

## What This Layer Ships

```
agent-base
└── agent-shell-base
    └── hermes-agent-shell   ← this deploy (BYOK → litellm.litellm.svc:4000/v1)
```

- A single-container Deployment on **gpu-1**, consuming the `hermes-agent-shell` image from the agent-images batch (pinned at the cluster-wide SHA `95e719b`)
- A combined SSH+Mosh LoadBalancer on **192.168.55.226** (TCP 22→2222, UDP 60032–60047)
- A 20Gi Longhorn home PVC at `/home/agent` holding `~/.hermes/`
- BYOK wiring to Frank's in-cluster LiteLLM gateway — no frontier keys, same zero-egress posture as Ruflo
- One ConfigMap that turned out to be the load-bearing artifact of the whole deploy

No GPU requested, despite the node name. Inference is remote via LiteLLM (which fans out to Ollama on the same node, so the electrons barely travel); gpu-1 is just Frank's largest CPU/RAM box and the natural home for interactive agent sessions.

## The Pod Boots Before Its Secrets Exist — By Design

The plan's Phase 1 is pure manual prep: mint a LiteLLM virtual key (`HERMES_LITELLM_KEY` in Infisical), build and SOPS-encrypt the ssh-keys Secret. Phase 2 deploys the manifests. But both secret references are `optional: true`, so the pod boots even if Phase 1 hasn't landed — it just can't reach LiteLLM and sshd accepts no keys until the bootstraps arrive. That's the declarative-only bootstrap exception working as intended: ArgoCD creates the namespace, the out-of-band secrets slot in afterwards, nothing deadlocks.

```yaml
envFrom:
  - secretRef:
      name: hermes-agent-shell-llm
      optional: true     # pod boots pre-bootstrap; env lands when ESO syncs
```

The Service follows the ruflo/paperclip pattern — one MixedProtocolLBService carrying TCP 22 and the UDP Mosh range on a single IP, which works fine on Cilium 1.17 + K8s 1.35. The Mosh range 60032–60047 is carved out so it doesn't overlap secure-agent-pod/paperclip (60000–60015) or ruflo (60016–60031). The port plan for agent shells is now officially a spreadsheet concern.

## Act One: sshd Eats the Environment

Here's the trap, known from the gotchas file but never before load-bearing: `agent-shell-base`'s sshd runs `UsePAM no` with no `PermitUserEnvironment`. The Kubernetes-injected env — `OPENAI_BASE_URL`, `OPENAI_API_KEY`, set on PID 1 by `envFrom` — is **scrubbed from every interactive SSH/Mosh login shell**. For the other shells this was an annoyance. For a pod whose entire purpose is running an env-keyed CLI over SSH, it's fatal: hermes launched from the shell silently can't reach LiteLLM, and the image's own MOTD prints "OPENAI_BASE_URL not set" on every login while the manifest very much sets it.

The fix needs no `agent-images` change. The whole container runs as UID 1000, so PID 1's environment is readable from inside — `/proc/1/environ` is the escape hatch. A ConfigMap-mounted profile.d drop-in re-exports the BYOK vars for login shells:

```bash
# /etc/profile.d/35-hermes-agent-shell-byok-env.sh
if [ -r /proc/1/environ ]; then
    for _hv in OPENAI_BASE_URL OPENAI_API_KEY; do
        eval "_hcur=\${$_hv:-}"
        if [ -z "$_hcur" ]; then
            _hval=$(tr '\0' '\n' < /proc/1/environ | sed -n "s/^${_hv}=//p" | head -n1)
            [ -n "$_hval" ] && export "$_hv=$_hval"
        fi
    done
    unset _hv _hcur _hval
fi
```

Mounted via `subPath` — the same mechanism paperclip uses for its tips drop-in — and numbered `35-` so it runs before the image's `50-` auth-status MOTD, which then correctly reports the keys as present. Non-interactive `ssh host -- cmd` still skips profile.d and stays env-less; that's by design, use `kubectl exec` for scripted access.

## Act Two: hermes Ignores the Keys Anyway

With the shim in place, the Phase 2 verification passed: MOTD shows the env, `hermes --version` works, `curl $OPENAI_BASE_URL` reaches LiteLLM. Ship it?

The first real `hermes` run returned `HTTP 401 Missing Authentication header` — from **`https://openrouter.ai/api/v1`**. The spec assumed hermes consumes `OPENAI_BASE_URL`/`OPENAI_API_KEY` directly, the way most OpenAI-compatible CLIs do. On v0.15.2 it does not: provider `auto` resolves to openrouter regardless of those vars, and the bare `OPENAI_API_KEY` registers only as the STT/TTS key. All three verification steps passed while the actual inference path was broken, because none of them exercised a chat completion.

The fix is pinning the provider in `~/.hermes/config.yaml` — and the *shape* matters:

```yaml
model:
  default: mistral-small-24b
  provider: litellm          # ← model as a MAPPING; this is what pins it
providers:
  litellm:
    base_url: http://litellm.litellm.svc:4000/v1
    key_env: OPENAI_API_KEY  # resolved from the login-shell env (the shim, again)
```

Every model-string prefix form — `litellm/<alias>`, `custom/<alias>`, `custom:litellm:<alias>` — does **not** pin the provider on this build; the whole string is sent as a model name to the default provider. The paperclip-era `ollama-cloud/<alias>` trick worked only because `ollama-cloud` is a built-in provider name. Since `~/.hermes/config.yaml` lives on the home PVC, seeding it is a documented manual operation (`orch-hermes-config-provider`), not declarative state. Verified live: bare `hermes chat -Q -q …` answers through LiteLLM with `provider=custom base_url=http://litellm.litellm.svc:4000/v1` in the logs.

## Act Three: Every Reply Is a Fake Tool Call

Provider pinned, chat flowing — and now every interactive reply arrived wrapped in tool-call JSON:

```json
{"name": "text_to_speech", "arguments": {...}}
```

Isolation narrowed it fast: `-t none` (no tools) → clean text. Non-streaming curl with tools → proper native `tool_calls`. **Streaming with tools → scaffolding JSON leaks into `content` and `tool_calls` never populates.** Hermes always streams, so hermes always lost.

The root cause sat in LiteLLM, not the model and not hermes: the `ollama/` provider prefix implements *prompt-based* function calling and only re-parses the scaffold on non-streamed responses. The fix was flipping all seven local aliases in `apps/litellm/values.yaml` from `ollama/` to `ollama_chat/` — Ollama's native `/api/chat` tool-calling path, stream-safe. That's a cluster-wide fix masquerading as a hermes bug: every tool-using LiteLLM consumer was exposed; hermes was merely the first to stream tools at a local model and look closely at the output.

```
That is a three-stage failure pipeline in which every stage reported success.
```

## The Lesson, Folded Into the Process

Two testing habits came out of this deploy and went straight into the verification checklist:

1. **A BYOK layer's end-to-end check must include one real chat completion.** Endpoint reachability, version strings, and MOTD rows all passed while inference 401'd against the wrong vendor on the other side of the planet.
2. **Always probe the streaming path when validating tool calling.** Non-streamed curl tests are the happy path that hides the `ollama/` class of bug entirely.

Both are now one-liners in `agents/rules/frank-gotchas.md` with full prose in the runbooks — the agent-shells file gained the BYOK provider-pinning section, the LiteLLM entry documents `ollama_chat/`.

## What's Next

The inventory ConfigMap ships deliberately sparse — all three keys empty, so the boot reconcile is a genuine no-op (the image bakes hermes at 0.15.2; a populated harness entry would `hermes update` on *every* boot and page Telegram on any non-zero exit). Pinning versions through it is future work, as is whatever hermes grows into once it's used in anger. For now: SSH in, ask it things, watch LiteLLM's dashboard light up.

## References

- [Nous Research hermes](https://github.com/NousResearch/hermes)
- [agent-images repo](https://github.com/derio-net/agent-images) — `hermes-agent-shell` image lineage
- [Building post 28 — Agent Images and the VK-Local Sidecar]({{< relref "/docs/building/28-agent-images-sidecar" >}})
- [Building post 29 — Ruflo]({{< relref "/docs/building/29-ruflo" >}}) — the zero-frontier-keys posture this pod inherits
- [Operating on Hermes Agent Shell]({{< relref "/docs/operating/28-hermes-shell" >}}) — companion day-to-day guide
- [LiteLLM Ollama provider docs](https://docs.litellm.ai/docs/providers/ollama) — `ollama` vs `ollama_chat`
