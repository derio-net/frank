---
title: "Operating on Hermes Agent Shell"
date: 2026-06-06
draft: false
tags: ["operations", "hermes", "agents", "byok", "litellm", "agent-shell-base", "ssh", "mosh"]
summary: "Day-to-day commands for the hermes shell pod — connecting via SSH/Mosh, running hermes against LiteLLM, rotating the virtual key and ssh keys, and the env-scrub troubleshooting tree."
weight: 29
---

Companion to [Hermes Agent Shell — A BYOK Pod That Ignored Its Own Keys]({{< relref "/docs/building/33-hermes-shell" >}}). Everything here assumes the Frank kubeconfig (`source .env` from the repo root — remember the [relative-path trap]({{< relref "/docs/operating/01-cluster-nodes" >}})).

## What "Healthy" Looks Like

```bash
kubectl -n hermes-agent-shell get pods,svc,pvc
```

- One pod `Running` on **gpu-1**, `1/1 Ready`
- Service `hermes-agent-shell` holding **192.168.55.226** (TCP 22 + UDP 60032–60047)
- PVC `hermes-agent-shell-home` `Bound` (20Gi Longhorn)

The real health check is a chat completion, not pod status — this layer's entire build story is surface checks passing while inference was broken:

```bash
kubectl exec -n hermes-agent-shell deploy/hermes-agent-shell -- \
  bash -lc 'hermes chat -Q -q "Reply with the single word: alive"'
```

`bash -lc` matters: it makes the profile.d BYOK shim run so the env is populated. A bare `bash -c` reproduces the env-scrubbed state.

## Connecting

### SSH

```bash
ssh agent@192.168.55.226
```

The MOTD's auth-status block should show `OPENAI_BASE_URL` and `OPENAI_API_KEY` as set. If it prints "not set", see Troubleshooting — that's the env shim failing, and hermes will not reach LiteLLM.

### Mosh

```bash
mosh --ssh="ssh agent@192.168.55.226" \
     --server="mosh-server new -p 60032:60047" 192.168.55.226
```

Pin the port range to match the Service; the per-shell wrapper in `apps/hermes-agent-shell/client-setup/laptop/` does this for you. Mosh sessions reap after 1h idle (`MOSH_SERVER_NETWORK_TMOUT=3600`) — a 16-port range fills up fast under the 168h default.

### Scripted access

`ssh agent@192.168.55.226 -- cmd` runs **without** the BYOK env (non-interactive shells skip profile.d, by design). For automation use:

```bash
kubectl exec -n hermes-agent-shell deploy/hermes-agent-shell -- bash -lc '<cmd>'
```

## Running hermes

The provider is pinned to LiteLLM in `~/.hermes/config.yaml` (home PVC, seeded manually — manual-op `orch-hermes-config-provider`):

```bash
hermes                      # interactive; default model gemma-12b-64k-nothin
hermes chat -Q -q "..."     # one-shot
/model                      # switch model in-session (any LiteLLM alias)
/info                       # shows the model's context window — should read 65,536 on the default
```

Useful aliases on the gateway: `gemma-12b-64k-nothin` (64k window, no
thinking-token tax — the default since 2026-06-06), `gemma-12b-64k` (same
window, thinking on — budget several hundred `max_tokens`),
`mistral-small-24b` (strongest local function calling, 16k window),
`qwen-think-14b`. Avoid editing the `model:` mapping into prefix forms
(`litellm/<alias>` etc.) — they silently unpin the provider and route to
openrouter (401).

**Context budgets (2026-06-06):** `~/.hermes/config.yaml` carries per-model
`context_length` overrides that mirror the live server (64k pair = 65536,
everything else = `OLLAMA_CONTEXT_LENGTH` = 16384) — manual-op
`orch-hermes-context-budgets`. They keep hermes's compressor honest; without
them an unknown alias resolves to a fantasy 256k window and Ollama silently
truncates history front-first ("session amnesia" — full chain in the building
post's update). If the gateway lineup changes, update the overrides in the
same breath. Switching mid-session to a 16k model after the conversation has
grown past ~8k triggers aggressive compaction — expected, not a bug.

**Reading web pages:** use `fetch-text <url>` (size-capped text extraction,
mounted at `/usr/local/bin/fetch-text`), never raw `curl` for HTML. SOUL.md
steers hermes to it; check after a long session that it obeyed:
`kubectl logs -n ollama deploy/ollama --since=1h | grep -c "truncated = 1"` → 0.

## Rotating Credentials

### LiteLLM virtual key

```bash
# 1. Mint a new virtual key against LiteLLM (admin UI or API at 192.168.55.206:4000)
# 2. Update HERMES_LITELLM_KEY in Infisical
# 3. ESO syncs hermes-agent-shell-llm; restart to re-inject on PID 1:
kubectl -n hermes-agent-shell rollout restart deploy/hermes-agent-shell
```

The env lands on PID 1 at boot; the login-shell shim reads `/proc/1/environ`, so a restart is required for shells to see the new key.

### SSH authorized keys

```bash
# Edit secrets/hermes-agent-shell/ssh-keys.yaml (SOPS round-trips)
sops --decrypt secrets/hermes-agent-shell/ssh-keys.yaml | kubectl apply -f -
# cont-init only COPIES keys at pod boot — restart to pick up:
kubectl -n hermes-agent-shell rollout restart deploy/hermes-agent-shell
```

## Inventory ConfigMap

`apps/hermes-agent-shell/manifests/configmap-inventory.yaml` ships **sparse** (all keys empty) so the boot reconcile is a genuine no-op. Do not seed `harnesses: { hermes: latest }` — the image bakes hermes at 0.15.2, and a populated entry runs `hermes update` on every boot (non-zero exit pages Telegram). Pin an explicit version only when you mean to float.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| MOTD: "OPENAI_BASE_URL not set" | sshd env-scrub; shim ConfigMap not mounted or secret not yet synced | Check `hermes-agent-shell-env` ConfigMap mount + `kubectl get externalsecret -n hermes-agent-shell` |
| `401 Missing Authentication header` from `openrouter.ai` | Provider unpinned — config.yaml missing/malformed (`model:` must be a *mapping* with `provider:`) | Re-seed `~/.hermes/config.yaml` per `orch-hermes-config-provider` |
| Every reply is `{"name": "text_to_speech", ...}` JSON | A LiteLLM alias reverted to `ollama/` prefix (prompt-based tools break under streaming) | Aliases must be `ollama_chat/` in `apps/litellm/values.yaml` |
| Reasoning-only empty replies | Thinking model exhausted `max_tokens` on reasoning | Raise the budget or switch model (`/model gemma-12b-64k-nothin`) |
| Model "forgets" earlier turns mid-session | Prompt exceeds the real server window; Ollama truncates front-first, silently | New session. Verify budgets: config.yaml `context_length` = live reality; check `kubectl logs -n ollama deploy/ollama \| grep "truncated = 1"` |
| `fetch-text: command not found` | ConfigMap mount missing or pod predates it | `kubectl -n hermes-agent-shell rollout restart deploy/hermes-agent-shell` (subPath mounts never live-update) |
| Mosh hangs on connect | Port range mismatch or all 16 ports held by stale sessions | Use `-p 60032:60047`; stale servers reap after 1h |
| Env present in `kubectl exec` but not over SSH | Using `ssh -- cmd` (non-interactive skips profile.d) | `bash -lc` via kubectl exec, or interactive SSH |

## References

- [Building post]({{< relref "/docs/building/33-hermes-shell" >}}) — the deploy narrative and the three-act failure chain
- `docs/runbooks/frank-gotchas/agent-shells.md` — BYOK provider-pinning section, env-scrub gotcha
- `docs/runbooks/manual-operations.yaml` — `orch-hermes-litellm-virtual-key`, `orch-hermes-shell-ssh-keys`, `orch-hermes-config-provider`
- [Operating on Local Inference]({{< relref "/docs/operating/07-inference" >}}) — LiteLLM gateway operations
