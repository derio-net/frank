# Paperclip via LiteLLM (opencode + hermes adapters) — Design

**Status:** Deployed (2026-05-22 — both `opencode_local` and `hermes_local` adapters hired and routing through LiteLLM; gotchas + manual-ops runbook entries synced. 2026-05-23 — building/15-paperclip + operating/18-paperclip retroactive updates landed, closing the Phase 6 deferral)
**Layer:** `orch`
**Spec date:** 2026-05-17

## Goal

Let Paperclip hire and run agents backed by Frank's local LLM stack — Ollama on `gpu-1`, fronted by the LiteLLM gateway at `litellm.litellm.svc:4000`. Concretely, install and wire **two** new adapters by default:

1. **`opencode_local`** — opencode-ai CLI, talks to LiteLLM as a custom OpenAI-compatible provider declared in `opencode.json`.
2. **`hermes_local`** — Nous Research's Hermes Agent (Python-based, multi-tool), pointed at LiteLLM via an `$HERMES_HOME/config.yml` inference chain.

Both default to one of the LiteLLM model aliases (`mistral-small-24b`, `qwen-coder-14b`, `qwen-think-14b`, `qwen36-a3b-nothin`, etc.). The paperclip-shell sidecar's MOTD documents the setup so operators know how to install, verify, and hire.

This is a **layer extension** of the existing `paperclip` deployment (layer `orch`), not a new layer.

## Motivation

Two halves of the wiring already exist:

1. **LiteLLM serves Ollama models with friendly names.** `apps/litellm/values.yaml` already exposes the local lineup at `192.168.55.206:4000` / `litellm.litellm.svc:4000` with virtual-key auth. See `2026-03-09--infer--ollama-litellm-design.md`.
2. **Paperclip already gets `LITELLM_API_KEY` and `LITELLM_BASE_URL` injected** from Infisical via `apps/paperclip/manifests/external-secret-llm.yaml`.

What's missing is the *consumer*: nothing inside Paperclip reads those env vars. The comment in `external-secret-llm.yaml` says Paperclip's "`http-local` adapter (currently 'coming soon')" will be the consumer — that comment is now **stale**. What shipped upstream is the `http` adapter, but it's a generic webhook adapter (POSTs `{agentId, runId, context}` to a URL), **not** an OpenAI-compatible LLM adapter. There is no first-class "point Paperclip at an OpenAI-compatible gateway" path.

The remaining adapters wrap specific agentic CLIs (`claude-code`, `codex`, `gemini`, `opencode`, `cursor`, etc.), each authenticated through that CLI's own provider plumbing. `codex_local` is already known unusable (LiteLLM doesn't proxy `/v1/responses` — see `frank-gotchas.md`), and `gemini_local` talks to Google directly.

Two adapters are clean matches, both with **declarative, config-file-driven** provider setup (so neither relies on container-wide `OPENAI_*` env vars that would re-create the PR #228 codex/gemini auth-clobber regression):

- **`opencode_local`** — opencode-ai's config declares custom OpenAI-compatible providers via `@ai-sdk/openai-compatible`, with `{env:VAR}` substitution for the API key. Configured globally via `opencode.json` shipped in a ConfigMap mounted under `$XDG_CONFIG_HOME`.
- **`hermes_local`** — Hermes Agent has its own `config.yml` with an `inference.chain:` block. Backends use `type: openai`, `base_url: <litellm>`, `api_key_env: LITELLM_API_KEY` (key referenced by env var name, read from the container-wide secret that ESO already injects). Mounted under `$HERMES_HOME`. This config shape has been pre-validated in a separate, simpler deployment hitting Frank's LiteLLM gateway, so we're porting a known-working chain rather than designing one from scratch.

Both run from the existing single Paperclip pod. The deliverable is an end-to-end run from at least one agent of each type — work routed through LiteLLM to Ollama on `gpu-1`, with no traffic leaving the cluster.

## Current state (audit)

| Piece | Status | Notes |
|---|---|---|
| LiteLLM gateway up | ✅ | `litellm.litellm.svc:4000`, master key + virtual keys via Infisical |
| LiteLLM Ollama model aliases | ✅ | `mistral-small-24b`, `gemma-12b`, `qwen-vl-7b`, `qwen-coder-14b`, `qwen-think-14b`, `qwen36-a3b`, `qwen36-a3b-nothin` |
| LiteLLM virtual key for Paperclip in Infisical (`PAPERCLIP_LITELLM_KEY`) | ✅ | Synced via ExternalSecret to `paperclip-llm-key` |
| `LITELLM_API_KEY` + `LITELLM_BASE_URL` env on paperclip container | ✅ | But nothing reads them today |
| `http-local` Paperclip adapter referenced in `external-secret-llm.yaml` comment | ❌ | Does not exist upstream; shipped `http` is a webhook adapter, not an LLM adapter |
| `opencode-ai` CLI on paperclip container's PATH | ❌ | Not in the upstream Paperclip image; only `codex` and `claude-code` are |
| `opencode.json` provider config | ❌ | Needs to be authored + delivered |
| `XDG_CONFIG_HOME` set on paperclip container | ❌ | Currently unset; defaults to `$HOME/.config` which is unusable on read-only image |
| `hermes` CLI on paperclip container's PATH | ❌ | Hermes is Python-based; Paperclip image is Node-only. Needs a Python interpreter and venv reachable from the paperclip container's filesystem. |
| `$HERMES_HOME/config.yml` provider config | ❌ | Inference chain with `type: openai` backends pointed at `litellm.litellm.svc:4000` |
| `HERMES_HOME` env on paperclip container | ❌ | Currently unset; needs to point at the ConfigMap mount path |
| Hired Paperclip agents using `opencode_local` / `hermes_local` adapters | ❌ | Manual step via paperclip-create-agent skill or UI once wiring lands |
| paperclip-shell MOTD documents setup | ❌ | The existing `60-paperclip-shell-tips.sh` ConfigMap doesn't mention either install step |

## Constraints

1. **Paperclip image untouched.** Same upstream image (`ghcr.io/paperclipai/paperclip:sha-c445e59`); install opencode-ai and hermes-agent onto the shared `/paperclip` PVC, not into the image.
2. **Match existing PVC-as-toolchain pattern.** PR #224 already installs `gemini` to `/paperclip/agent-bin/node_modules/.bin` and adds that path to PATH on the paperclip container. opencode-ai follows the same npm-on-PVC shape; hermes needs a Python-on-PVC variant since it's `pip install`.
3. **Declarative for both adapters.** `opencode.json` (under `$XDG_CONFIG_HOME/opencode/`) configures all opencode agents globally. Hermes's `config.yml` (under `$HERMES_HOME/`) configures all hermes agents globally, pointed at the in-cluster LiteLLM service URL. No per-agent env blocks; `adapterConfig` only nominates `model`.
4. **No new services.** All traffic flows through the existing LiteLLM Service. No webhook proxy, no per-Paperclip adapter package.
5. **Operator API mutations need the documented Origin header + `%3D` cookie encoding gotcha** when an agent is hired via curl (per `paperclip-ruflo.md`); hiring through the Paperclip UI sidesteps that.
6. **Single-model default per adapter; not single-model overall.** Both adapters point at the same LiteLLM gateway and can use any of the LiteLLM aliases; the *default* hire payload nominates one (`qwen-coder-14b` for opencode's coding-leaning agents, `qwen-think-14b` for hermes's reasoning-leaning agents). Operators are free to override per hire.
7. **Adapter-internal behavior must be verified at plan time:**
   - `opencode_local`: the adapter constructs a temporary `XDG_CONFIG_HOME` per run and copies our base `opencode.json` into it; rely on that copy preserving the `provider`/`models` blocks. (Per upstream `packages/adapters/opencode-local/src/server/runtime-config.ts`.)
   - `hermes_local`: the adapter's `normalizeHermesConfig` passes through process env (including `HERMES_HOME` and `LITELLM_API_KEY`) and merges in `adapterConfig.env` if set. We do not need the env-merge path; the config-file path is sufficient.
8. **Python on shared PVC via `uv`.** Install hermes-agent with `uv python install` plus `uv pip install 'hermes-agent @ git+https://github.com/NousResearch/hermes-agent.git@v2026.4.16'` onto `/paperclip/agent-bin/hermes-agent/venv`, with the entry-point shim at `/paperclip/agent-bin/bin/hermes`. (PyPI has a different `hermes-agent` package; we install from the upstream git tag.) uv produces a self-contained, relocatable Python install — the venv's shebang resolves to a path that exists in both the shell sidecar and the paperclip container's filesystem because both mount the same `/paperclip` PVC. (`v2026.4.16` is the pinned upstream Hermes release used here because it's the one already exercised against Frank's LiteLLM elsewhere.)

## Architecture

```
                                    paperclip-system namespace
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  ┌────────────────────────┐   ┌────────────────────────┐   ┌──────────────┐  │
│  │ ConfigMap              │   │ ConfigMap              │   │ ConfigMap    │  │
│  │ paperclip-opencode     │   │ paperclip-hermes       │   │ paperclip-   │  │
│  │ (NEW)                  │   │ (NEW)                  │   │ shell-motd-  │  │
│  │ opencode.json          │   │ config.yml (inference  │   │ tips (EDIT)  │  │
│  │ (provider=litellm)     │   │  chain → litellm)      │   │              │  │
│  └─────────┬──────────────┘   └────────┬───────────────┘   └──────┬───────┘  │
│            │                           │                          │          │
│            │ mount (paperclip ctr):    │ mount (paperclip ctr):   │ (shell)  │
│            │ /etc/paperclip/opencode-  │ /etc/paperclip/hermes-   │          │
│            │   base/opencode/          │   base/config.yml        │          │
│            │     opencode.json         │                          │          │
│            ▼                           ▼                          ▼          │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ Deployment: paperclip                                                  │  │
│  │  Volumes shared: paperclip-data PVC → /paperclip in both containers    │  │
│  │                                                                        │  │
│  │  container: paperclip                container: paperclip-shell        │  │
│  │    env:                                (SSH + Mosh entry, sidecar)     │  │
│  │      XDG_CONFIG_HOME=                  reconcile writes to /paperclip: │  │
│  │        /etc/paperclip/opencode-base      /paperclip/agent-bin/         │  │
│  │      HERMES_HOME=                          node_modules/.bin/opencode  │  │
│  │        /etc/paperclip/hermes-base          hermes-agent/venv/...       │  │
│  │      LITELLM_API_KEY  (existing ESO)       bin/hermes  (shim)          │  │
│  │      LITELLM_BASE_URL (existing ESO)                                   │  │
│  │      (NO container-wide OPENAI_*)                                      │  │
│  │                                                                        │  │
│  │    PATH includes                                                       │  │
│  │      /paperclip/agent-bin/node_modules/.bin                            │  │
│  │      /paperclip/agent-bin/bin                                          │  │
│  │                                                                        │  │
│  │    spawns CLI per agent run:                                           │  │
│  │      • opencode → reads opencode.json (provider=litellm)               │  │
│  │      • hermes   → reads $HERMES_HOME/config.yml                        │  │
│  │                   (type=openai, base_url=litellm,                      │  │
│  │                    api_key_env=LITELLM_API_KEY)                        │  │
│  └──────────────────────────────────────┬─────────────────────────────────┘  │
│                                         │                                    │
│            POST /v1/chat/completions    │                                    │
│            Authorization: Bearer …      │                                    │
│                                         ▼                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ litellm.litellm.svc:4000 → Ollama (gpu-1) → mistral / qwen / gemma   │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Hermes `config.yml` (provider config delivered via ConfigMap)

The Hermes-side schema uses `type: openai` for any OpenAI-protocol-compatible endpoint — LiteLLM speaks that protocol natively. This shape (with `type: openai` + `base_url` + `api_key_env`) has been confirmed working against the Frank LiteLLM gateway in a separate small deployment, which is why we're transplanting it rather than designing it from scratch.

```yaml
# Mounted at $HERMES_HOME/config.yml = /etc/paperclip/hermes-base/config.yml
inference:
  chain:
    - name: frank-litellm-coder
      type: openai
      base_url: http://litellm.litellm.svc:4000/v1
      model: qwen-coder-14b
      api_key_env: LITELLM_API_KEY
    - name: frank-litellm-reasoner
      type: openai
      base_url: http://litellm.litellm.svc:4000/v1
      model: qwen-think-14b
      api_key_env: LITELLM_API_KEY
    - name: frank-litellm-default
      type: openai
      base_url: http://litellm.litellm.svc:4000/v1
      model: mistral-small-24b
      api_key_env: LITELLM_API_KEY

tools:
  filesystem:
    read_roots:
      - /paperclip
    write_roots: []
  shell:
    enabled: false
```

`api_key_env: LITELLM_API_KEY` tells Hermes to read the env var **by name** (not value), so the existing container-wide `LITELLM_API_KEY` from the ExternalSecret is picked up without any per-agent wiring. The `inference.chain` is ordered preference — Hermes selects the first entry whose `name` matches the agent's `adapterConfig.model`, or falls through to the default.

### opencode.json (provider config delivered via ConfigMap)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "litellm": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Frank LiteLLM",
      "options": {
        "baseURL": "http://litellm.litellm.svc:4000/v1",
        "apiKey": "{env:LITELLM_API_KEY}"
      },
      "models": {
        "mistral-small-24b": { "name": "Mistral Small 3.2 24B (local)" },
        "qwen-coder-14b":    { "name": "Qwen2.5-Coder 14B Q6 (local)" },
        "qwen-think-14b":    { "name": "Qwen3 14B Thinking (local)" },
        "qwen36-a3b":        { "name": "Qwen3.6 35B-A3B MoE (local)" },
        "qwen36-a3b-nothin": { "name": "Qwen3.6 35B-A3B MoE — no-think (local)" },
        "gemma-12b":         { "name": "Gemma 3 12B multimodal (local)" }
      }
    }
  }
}
```

### Agent hire payloads (initial agents — one per adapter)

Used through the paperclip-create-agent skill or Paperclip UI:

**opencode_local** — provider config is global (from `opencode.json`), so the hire payload just nominates the model:

```json
{
  "name": "Local Coder",
  "role": "engineer",
  "title": "Local Engineer",
  "icon": "wrench",
  "adapterType": "opencode_local",
  "adapterConfig": {
    "model": "litellm/qwen-coder-14b",
    "promptTemplate": "<role-specific prompt>"
  },
  "runtimeConfig": { "heartbeat": { "enabled": false } }
}
```

**hermes_local** — provider config is global (from `$HERMES_HOME/config.yml`), so the hire payload just nominates a backend `name` from the inference chain via the `model` field:

```json
{
  "name": "Local Reasoner",
  "role": "engineer",
  "title": "Local Reasoner (Hermes)",
  "icon": "brain",
  "adapterType": "hermes_local",
  "adapterConfig": {
    "model": "frank-litellm-reasoner",
    "hermesCommand": "/paperclip/agent-bin/bin/hermes",
    "toolsets": "terminal,file,web",
    "persistSession": true,
    "promptTemplate": "<role-specific prompt>"
  },
  "runtimeConfig": { "heartbeat": { "enabled": false } }
}
```

The exact `model` field shape — whether Hermes wants the backend `name` from the inference chain, a `provider/model` tuple, or a bare model ID — is verified in the plan phase against Hermes `v2026.4.16`. The fallback is to flatten the inference chain to one backend named `default` and let Hermes pick it.

The exact `model` field shape for opencode (`litellm/qwen-coder-14b` vs bare `qwen-coder-14b`) is verified in the plan phase against the installed opencode-ai version.

## Components touched

| File | Change | Why |
|---|---|---|
| `apps/paperclip/manifests/configmap-opencode.yaml` | **New** | Holds `opencode.json` with the LiteLLM provider block |
| `apps/paperclip/manifests/configmap-hermes.yaml` | **New** | Holds `config.yml` (Hermes inference chain) with `type: openai` backends pointed at `litellm.litellm.svc:4000`. |
| `apps/paperclip/manifests/deployment.yaml` | **Edit** | Mount both new ConfigMaps; set `XDG_CONFIG_HOME` and `HERMES_HOME`; extend `PATH` with `/paperclip/agent-bin/bin` so the hermes shim is visible; consider an initContainer or post-start hook that runs the reconcile so cold PVs install opencode + hermes without manual SSH |
| `apps/paperclip/manifests/configmap-shell-inventory.yaml` | **Edit** | Extend the inventory schema with a new `paperclip-shared` section (or equivalent) for tools that must land on `/paperclip` not on the shell's home PV. Entries: `opencode-ai` (npm, into `/paperclip/agent-bin/node_modules/`), `hermes-agent` pinned to `v2026.4.16` (Python via uv into `/paperclip/agent-bin/hermes-agent/venv`). The existing `npm-global` / `pipx` / `cargo` lists stay shell-home-scoped. |
| `apps/paperclip/manifests/configmap-shell-motd-tips.yaml` | **Edit** | New "LiteLLM-backed agents" section with: (a) install commands for opencode + hermes, (b) the model-name → backend-name map for hires, (c) verification one-liners, (d) link to the runbook |
| `apps/paperclip/manifests/external-secret-llm.yaml` | **Edit** | Replace the stale "`http-local` coming soon" comment with the actual wiring (opencode reads `{env:LITELLM_API_KEY}` from `opencode.json`; hermes reads `LITELLM_API_KEY` via `api_key_env:` in `config.yml`) |
| `docs/runbooks/frank-gotchas/paperclip-ruflo.md` (new "LiteLLM-backed agents" section) | **Edit** | Both ConfigMap shapes, the Python-on-PVC pattern (uv-based install), the hermes inference-chain naming convention, and any new gotchas surfaced during plan/execute (e.g., `model` field shape per CLI version) |
| `agents/rules/frank-gotchas.md` | **Edit** | One-liner pointing at the new runbook section |

No changes to `apps/litellm/` (the gateway), `apps/ollama/` (the runtime), `apps/paperclip/manifests/configmap.yaml` (PAPERCLIP_HOME etc. unchanged), or `secrets/paperclip/` (the SOPS bootstrap).

## Data flow (per agent run)

**opencode_local agent:**

1. Paperclip scheduler decides to run agent `Local Coder`.
2. `opencode_local` adapter (`packages/adapters/opencode-local/src/server/execute.ts`) constructs a fresh per-run XDG dir, copying our base `opencode.json` into it.
3. Adapter spawns `opencode run -m litellm/qwen-coder-14b --prompt "<task>"` (exact CLI shape verified in plan).
4. opencode reads its merged config, resolves `apiKey` from `LITELLM_API_KEY` env (container-wide), and POSTs `/v1/chat/completions` to `litellm.litellm.svc:4000` with model `qwen-coder-14b`.
5. LiteLLM routes to `ollama/qwen2.5-coder:14b-instruct-q6_K` on `gpu-1`.
6. Streamed completion flows back through opencode → Paperclip transcript.
7. Paperclip records the run, transcript, and exit code.

**hermes_local agent:**

1. Paperclip scheduler decides to run agent `Local Reasoner`.
2. `hermes_local` adapter (`hermes-paperclip-adapter/server`) calls `normalizeHermesConfig` and spawns the hermes CLI. The container env already has `HERMES_HOME=/etc/paperclip/hermes-base` and `LITELLM_API_KEY=<value>`, so hermes auto-discovers our `config.yml` on launch.
3. Adapter spawns `hermes chat -q --model frank-litellm-reasoner "<task>"` (exact CLI shape verified in plan).
4. Hermes reads `config.yml`, selects the `frank-litellm-reasoner` backend (`type: openai`, `base_url: …`), resolves `api_key_env: LITELLM_API_KEY` from process env, and POSTs `/v1/chat/completions` to LiteLLM.
5. LiteLLM routes to `ollama/qwen3:14b` on `gpu-1`.
6. Streamed completion → hermes structured transcript → Paperclip adapter parses into `TranscriptEntry` objects (tool cards) → Paperclip UI/run history.
7. Hermes session state lives under `$HERMES_HOME/sessions/` — but `$HERMES_HOME` is a read-only ConfigMap mount. Plan-phase task: set the session DB path explicitly via `config.yml` to a writable path under `/paperclip/agent-bin/.hermes/` so `--resume` survives pod restarts.

## Failure modes

| Failure | Symptom | Handling |
|---|---|---|
| Virtual key revoked / rotated | opencode/hermes 401 from `/v1/chat/completions` | Paperclip surfaces adapter failure; rotate `PAPERCLIP_LITELLM_KEY` in Infisical; ESO re-syncs within 5m |
| LiteLLM pod down | Connection refused | Existing LiteLLM canary/Rollout health story applies; Paperclip retries per its own scheduler |
| Ollama model swap evicts hot model | First request slow, may timeout if model is large (qwen36-a3b cold-load is ~20s) | Default agents pin an always-warm model (`mistral-small-24b` for opencode, `qwen-think-14b` for hermes); document `OLLAMA_KEEP_ALIVE=24h` gotcha for cold MoE loads |
| opencode CLI missing from PVC after wipe | `opencode: command not found` | Declarative-install via initContainer (preferred), or operator runs the reconcile from the shell sidecar — surfaced in the MOTD instructions |
| hermes CLI missing from PVC after wipe | `hermes: command not found` | Same as opencode — the shared `paperclip-shared` inventory section drives reconcile; MOTD points at it |
| opencode runtime-config-copy strips provider block | Agent run fails with unknown provider | Plan-time verification of the copy behavior; if it strips, fall back to setting `XDG_CONFIG_HOME` to the ConfigMap mount and rely on the adapter's directory-copy without per-run overwrites |
| hermes ignores `HERMES_HOME` or reads a different filename | Hermes falls back to defaults or errors on "no config" | Plan-time check: confirm `v2026.4.16` honors `HERMES_HOME` for `config.yml` discovery. Low-risk (the prior validated deployment relies on this behavior) but verify at our pinned version. |
| `model` field maps to a backend `name` not present in our inference chain | hermes error "unknown model" / falls through to next chain entry | Plan-time verification: hire one agent with each named backend (`frank-litellm-coder`, `-reasoner`, `-default`) and confirm the call lands on the expected LiteLLM model |
| Hermes session DB written under read-only `$HERMES_HOME` mount | `--resume` fails or hermes can't write | Override session/database paths in `config.yml` to point under `/paperclip/agent-bin/.hermes/`. Plan-phase task. |
| Python interpreter on PVC has wrong arch / libc | `hermes: cannot execute binary file` on Paperclip container | Plan-time validation: install via `uv python install` — uv produces a relocatable Python compatible with any glibc-compatible Linux — and exec it from both the shell and the paperclip containers before declaring `Deployed` |
| Hermes SELinux relabel needed (Fedora hosts only) | systemd `203/EXEC` if the install path is `var_lib_t` | Not applicable — paperclip-system pods run unconfined inside the cluster; no SELinux denial path here. |
| `model` field shape mismatch (opencode) | opencode error "unknown model" | Plan-time verification of `litellm/<name>` vs bare `<name>` per opencode-ai version |

## Verification — "Deployed" gate

Per `agents/rules/frank-gotchas.md` ("Process / practice — a layer is not Deployed until its workflow has been triggered + observed end-to-end"):

**opencode_local path:**

1. `opencode` CLI present on PATH inside paperclip container (single `kubectl exec ... -- which opencode`).
2. `kubectl exec paperclip-… -c paperclip -- opencode run -m litellm/qwen-coder-14b -p "say ping"` resolves to a successful completion **and the request shows up in LiteLLM's request log** (admin UI, filtered by the Paperclip virtual key).
3. Through the Paperclip UI: hire one `opencode_local` agent, assign a trivial issue, watch the run complete with transcript.

**hermes_local path:**

4. `hermes` CLI present on PATH inside paperclip container; `hermes --version` succeeds; `cat $HERMES_HOME/config.yml` shows the LiteLLM inference chain.
5. `kubectl exec paperclip-… -c paperclip -- hermes chat -q --model frank-litellm-reasoner "say ping"` completes and the request appears in LiteLLM's log (model = `qwen-think-14b`).
6. Through the Paperclip UI: hire one `hermes_local` agent with `adapterConfig.model: "frank-litellm-reasoner"`, assign a trivial issue, watch the transcript flow back as structured tool cards.

**Cross-path:**

7. Confirm with LiteLLM logs that both adapters' calls routed to Ollama (not OpenRouter).
8. Confirm both agents survive a Paperclip pod restart (`strategy: Recreate`) — the PVC-resident CLIs persist; the hermes session resumes from `--resume`.

Only after step 6 succeeds end-to-end (both adapters, both via Paperclip UI) is the spec status promoted to `Deployed`.

## Out of scope

- Wiring the *other* hermes providers (`openrouter`, `nous`, `zai`, `kimi-coding`, `minimax`, …). LiteLLM-via-`openai` covers our local + free-cloud needs since LiteLLM itself fronts OpenRouter; cluttering hermes with overlapping providers is YAGNI.
- A third adapter beyond opencode and hermes (e.g. `claude_local` against LiteLLM's Anthropic-compat surface, `pi_local`, `acpx_local`). Those are pre-vetted as possible but not part of this scope.
- Cloud-fallback policy inside agents — the gateway already does that. Agents pick a LiteLLM model name; LiteLLM decides where the call lands.
- Replacing the existing `claude_local` / `codex_local` agents in Paperclip; this is purely additive.
- Authentik SSO for the LiteLLM admin UI (separate concern).
- Per-agent virtual keys + spend limits in LiteLLM (one shared Paperclip key for now; revisit if multiple agents start churning quota).
- Declarative initContainer install of opencode-ai + hermes-agent. Surfaced as a follow-up if PVC wipes start happening often enough to justify it.

## paperclip-shell MOTD (`60-paperclip-shell-tips.sh` addition)

The shell sidecar prints `/etc/profile.d/60-paperclip-shell-tips.sh` on interactive SSH login. A new "LiteLLM-backed agents" section is appended (rendered conditionally — only if `opencode` or `hermes` aren't already on the paperclip container's PATH). Indicative shape:

```text
─── LiteLLM-backed agents ──────────────────────────────────────────
 LiteLLM (Frank's local LLM gateway) is wired into Paperclip via:

   opencode_local  — opencode CLI, provider declared globally in
                     /etc/paperclip/opencode-base/opencode/opencode.json
                     Default model:  litellm/qwen-coder-14b
                     Install once:   paperclip-shell-reconcile
                     Verify:         kubectl exec ... -- opencode --version

   hermes_local    — Hermes Agent (Nous Research, Python). Inference
                     chain declared globally in
                     $HERMES_HOME/config.yml (mounted from ConfigMap).
                     Pick a backend by name in adapterConfig.model:
                       • frank-litellm-coder    → qwen-coder-14b
                       • frank-litellm-reasoner → qwen-think-14b
                       • frank-litellm-default  → mistral-small-24b
                     Install once:   paperclip-shell-reconcile
                     Verify:         kubectl exec ... -- hermes --version

 Hire flow: use the paperclip-create-agent skill from your dev box, or
 the Paperclip UI at http://192.168.55.212:3100. Both adapters need
 only adapterConfig.model — no per-agent env blocks. Full runbook:
 docs/runbooks/frank-gotchas/paperclip-ruflo.md#litellm-backed-agents
────────────────────────────────────────────────────────────────────
```

The MOTD's reconcile suggestion (`paperclip-shell-reconcile`) is the existing helper from the shell-sidecar layer; the spec adds the new install items into the inventory so the same reconcile picks them up. The MOTD intentionally **does not** print secrets — only the `{env:...}` placeholder.

## Manual operations

```yaml
# manual-operation
id: orch-paperclip-reconcile-shared-agent-clis
layer: orch
app: paperclip
plan: docs/superpowers/specs/2026-05-17--orch--paperclip-litellm-agents-design.md
when: "After the inventory ConfigMap is synced and on every fresh /paperclip PV"
why_manual: "PVC-resident tools are installed by the shell sidecar's reconcile, not by ArgoCD. Declarative-initContainer is the long-term home; for now this stays operator-imperative + idempotent."
commands:
  - "SSH into paperclip-shell: ssh paperclip-shell"
  - "Run reconcile: paperclip-shell-reconcile  # installs opencode-ai + hermes-agent onto /paperclip/agent-bin"
  - "Verify from paperclip container: kubectl -n paperclip-system exec deploy/paperclip -c paperclip -- which opencode hermes"
verify:
  - "Both `opencode --version` and `hermes --version` succeed when exec'd in the paperclip container"
status: pending
```

```yaml
# manual-operation
id: orch-paperclip-hire-opencode-litellm-agent
layer: orch
app: paperclip
plan: docs/superpowers/specs/2026-05-17--orch--paperclip-litellm-agents-design.md
when: "After the reconcile op above has installed opencode on the PVC"
why_manual: "Agent hire is a board-level operator action through Paperclip's API; not declarative"
commands:
  - "Smoke test: kubectl -n paperclip-system exec deploy/paperclip -c paperclip -- opencode run -m litellm/qwen-coder-14b -p 'say ping'"
  - "Hire agent through Paperclip UI or via paperclip-create-agent skill with adapterType=opencode_local"
  - "Assign a trivial issue and confirm transcript completes"
verify:
  - "LiteLLM admin UI request log shows the call from the Paperclip virtual key against model=qwen-coder-14b"
  - "Paperclip run history shows successful completion with non-empty transcript"
status: pending
```

```yaml
# manual-operation
id: orch-paperclip-hire-hermes-litellm-agent
layer: orch
app: paperclip
plan: docs/superpowers/specs/2026-05-17--orch--paperclip-litellm-agents-design.md
when: "After the reconcile op above has installed hermes on the PVC"
why_manual: "Agent hire is a board-level operator action; hermes inference chain is global via config.yml so the hire payload only needs adapterConfig.model"
commands:
  - "Smoke test: kubectl -n paperclip-system exec deploy/paperclip -c paperclip -- hermes chat -q --model frank-litellm-reasoner 'say ping'"
  - "Hire agent through Paperclip UI or via paperclip-create-agent skill with adapterType=hermes_local, adapterConfig.model=frank-litellm-reasoner"
  - "Assign a trivial issue and confirm transcript completes with structured tool cards"
verify:
  - "LiteLLM admin UI request log shows the call from the Paperclip virtual key against model=qwen-think-14b"
  - "Paperclip run history shows successful completion; hermes session ID is captured for --resume continuity"
status: pending
```

(If a declarative initContainer install lands, `orch-paperclip-reconcile-shared-agent-clis` becomes belt-and-braces rather than load-bearing.)

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| Paperclip LiteLLM-Backed Agents Implementation Plan |  | `2026-05-17--orch--paperclip-litellm-agents` | — |

## References

- Existing Paperclip design: `docs/superpowers/specs/2026-03-14--orch--paperclip-design.md`
- Paperclip shell sidecar design: `docs/superpowers/specs/2026-05-02--orch--paperclip-shell-sidecar-design.md`
- Ollama+LiteLLM design: `docs/superpowers/specs/2026-03-09--infer--ollama-litellm-design.md`
- LiteLLM values + model aliases: `apps/litellm/values.yaml`
- Paperclip LiteLLM ExternalSecret: `apps/paperclip/manifests/external-secret-llm.yaml`
- Paperclip deployment: `apps/paperclip/manifests/deployment.yaml`
- Paperclip MOTD ConfigMap: `apps/paperclip/manifests/configmap-shell-motd-tips.yaml`
- Paperclip shell-sidecar inventory: `apps/paperclip/manifests/configmap-shell-inventory.yaml`
- Paperclip-Ruflo gotchas (codex `/v1/responses` issue, board-mutation CSRF gotcha): `docs/runbooks/frank-gotchas/paperclip-ruflo.md`
- Upstream `opencode_local` adapter package: `paperclipai/paperclip` → `packages/adapters/opencode-local/`
- opencode.ai provider docs (custom OpenAI-compatible providers + `{env:VAR}` substitution): `https://opencode.ai/docs/providers`, `https://opencode.ai/docs/config`
- Upstream `hermes_local` adapter package: `NousResearch/hermes-paperclip-adapter`
- Hermes Agent itself: `NousResearch/hermes-agent` (we pin `v2026.4.16`)
- Hermes env-variables reference: `https://hermes-agent.nousresearch.com/docs/reference/environment-variables`
- `uv` for relocatable Python on the shared PVC: `https://github.com/astral-sh/uv`
