# Hermes Context-Window Survival — Truthful Budgets, 64k Variant, Fetch Hygiene

**Date:** 2026-06-06
**Status:** Draft
**Layer:** orch (consumer fix) — touches `infer` apps (ollama, litellm)
**Extends:** hermes-agent-shell layer 33 (building-33 / operating-28 posts get retroactive updates, no new posts)

## Overview

A single `curl -s` of a 208 KB blog page permanently destroyed a Hermes shell
session this morning: every subsequent turn was silently truncated by Ollama
and the model lost all conversation history ("amnesia"). This spec makes
Hermes survive long sessions on local inference by fixing all three layers of
the failure:

1. **Truthful context budgets** — Hermes believed `gemma-12b` had a 256,000-token
   window (its resolver's *default fallback* when every probe fails on a custom
   LiteLLM alias); the Ollama server truncates at 16,384. Per-model
   `context_length` overrides make Hermes's built-in compressor engage at the
   real boundary instead of 8× past it.
2. **A 64k gemma4 variant** — measured headroom on gpu-1's RTX 5070 Ti makes a
   4× window nearly free (+846 MiB). Declared via the ollama chart's
   `models.create` (Modelfile `num_ctx` overrides the server env), exposed as
   LiteLLM aliases, made the Hermes default.
3. **Fetch hygiene** — Hermes v0.15.2 has no key-free web-extract backend
   (that's why it raw-curled HTML). A ConfigMap-mounted `fetch-text` helper
   plus a SOUL.md steering line keeps web page reads at ~5k tokens instead
   of ~50k.

## Incident & root cause (2026-06-06, hermes shell, gemma-12b)

Chain, each link verified live:

1. User asked Hermes to read `https://blog.derio.net/frank/docs/building/33-hermes-shell/`
   → Hermes ran `curl -s` → 208,753 bytes of raw HTML.
2. Hermes's `tool_output.max_bytes: 50000` capped it to 50 KB ≈ 15k tokens —
   still the entire real window by itself.
3. Hermes believed the window was 256k (`get_model_context_length` resolution
   step 9: "Default fallback (256K)"), so neither its compressor
   (`compression.threshold: 0.5` → engages ~128k believed) nor any trim fired.
4. LiteLLM cannot pass per-request `num_ctx` to `ollama_chat`
   (BerriAI/litellm#12930) → Ollama truncated the prompt **front-first and
   silently** at `OLLAMA_CONTEXT_LENGTH=16384`. Runner log:
   `n_tokens = 16383, truncated = 1` at 08:50:42–08:53:20, one line per turn —
   initial + 3 continuation retries + the user's follow-up.
5. Front-first truncation drops system prompt + history, keeps the HTML tail →
   the model genuinely never saw earlier turns. The giant tool result lives in
   session history, so **every** later turn re-overflows: the session is
   poisoned permanently.
6. Secondary: gemma4 thinking tokens consumed the output budget inside the
   already-full context → `finish_reason='length'` → Hermes's continuation
   loop re-sent the same oversized prompt 3×.

## Evidence — KV-cache cost measurement (gpu-1, RTX 5070 Ti 16 GB, gemma4:12b)

Measured 2026-06-06 via derived-model tags (since removed; this spec recreates
the 64k one declaratively). `ollama ps` reported 100% GPU at every size;
Modelfile `PARAMETER num_ctx` confirmed to override `OLLAMA_CONTEXT_LENGTH`
(the `CONTEXT` column showed the Modelfile value).

| num_ctx | nvidia-smi used | delta vs 16k |
|---------|----------------|--------------|
| 16,384 (baseline) | 8,840 MiB | — |
| 32,768 | 9,110 MiB | +270 MiB |
| 65,536 | 9,686 MiB | +846 MiB |
| 131,072 | 10,426 MiB | +1,586 MiB |

≈12.4 MiB per 1k tokens — gemma4's sliding-window attention keeps KV cheap.
**Operator decision: 64k** (128k fits but doubles worst-case prefill latency
and stresses 12B long-range recall for marginal benefit).

## Operator decisions (batched Q&A, 2026-06-06)

| Decision | Choice |
|----------|--------|
| Variant context size | **64k** (`gemma4:12b-64k`) |
| Hermes default model | **`gemma-12b-64k-nothin`** (thinking variant stays available via `/mode`) |
| Fetch-hygiene vehicle | **ConfigMap `fetch-text` helper + SOUL.md line** (no SaaS key, no image rebuild) |
| Post-merge Test Plan | **Full replay** of the original failing scenario |

## Design

### D1 — Declarative 64k variant (apps/ollama/values.yaml)

The otwld ollama chart (1.50.0, already pinned) supports model creation at
container startup:

```yaml
ollama:
  models:
    create:
      - name: gemma4:12b-64k
        template: |
          FROM gemma4:12b
          PARAMETER num_ctx 65536
```

- Blob-sharing: the derived tag adds only a manifest layer (~bytes on the
  200Gi PVC); `FROM gemma4:12b` reuses existing blobs.
- `models.clean` stays `false`.
- Rollout note: the values change restarts the ollama pod (model unload +
  cold reload on next request — same disruption class as any ollama bump).

### D2 — LiteLLM aliases (apps/litellm/values.yaml)

Mirroring the existing `gemma-12b` / `gemma-12b-nothin` pair:

```yaml
- model_name: gemma-12b-64k
  litellm_params:
    model: ollama_chat/gemma4:12b-64k
    api_base: http://ollama.ollama.svc.cluster.local:11434

- model_name: gemma-12b-64k-nothin
  litellm_params:
    model: ollama_chat/gemma4:12b-64k
    api_base: http://ollama.ollama.svc.cluster.local:11434
    extra_body:
      think: false
```

With comments carrying the measurement table reference and the "Modelfile
num_ctx overrides OLLAMA_CONTEXT_LENGTH" mechanism (the documented escape
hatch from litellm#12930).
Rollout note: litellm is behind the Argo Rollouts canary — config change
rides the standard analysis.

### D3 — Truthful Hermes context budgets (PVC config.yaml — manual-operation)

`/home/agent/.hermes/config.yaml` on the hermes shell PVC, under the existing
`providers.litellm`: add a `models:` mapping with per-model `context_length`
(hermes v0.15.2 honors `custom_providers[].models.<id>.context_length` on
startup, `/model` switch, and `/info` display — upstream #15779):

```yaml
providers:
  litellm:
    base_url: http://litellm.litellm.svc:4000/v1
    key_env: HERMES_LITELLM_KEY
    models:
      gemma-12b-64k:        { context_length: 65536 }
      gemma-12b-64k-nothin: { context_length: 65536 }
      gemma-12b:            { context_length: 16384 }
      gemma-12b-nothin:     { context_length: 16384 }
      mistral-small-24b:    { context_length: 16384 }
      qwen-think-14b:       { context_length: 16384 }
      qwen-coder-14b:       { context_length: 16384 }
      qwen-vl-7b:           { context_length: 16384 }
      qwen36-a3b:           { context_length: 16384 }
      qwen36-a3b-nothin:    { context_length: 16384 }
      all-proxy-models:     { context_length: 16384 }
```

(A provider-level `context_length` key also exists in the v0.15.2 normalizer,
but only the per-model path is verified through
`get_custom_provider_context_length` — the explicit enumeration is the
load-bearing choice. `all-proxy-models` is LiteLLM's built-in router
exposure, not a values.yaml alias; the override is harmless belt-and-braces.)

Plus:

- `model.default: gemma-12b-64k-nothin` (was `mistral-small-24b`).
- `tool_output.max_bytes: 50000 → 24000` — largest useful single tool result
  that still leaves >50% of a 16k window for system + history when the user
  `/mode`s to a 16k model; negligible (~6%) on the 64k default. The
  compressor (`threshold: 0.5`, already enabled) handles accumulation.

Why manual: config.yaml is PVC state, seeded manually by design (precedent:
`orch-hermes-config-provider`). Executed agentically via `kubectl exec` +
verified, documented as a `# manual-operation` block for reproducibility.

### D4 — `fetch-text` helper (apps/hermes-agent-shell/manifests)

New `configmap-fetch-text.yaml` + deployment mount:

- Python 3 **stdlib-only** script (the image carries python3.11 for hermes;
  no new packages): fetch URL, follow redirects, strip
  `script`/`style`/`nav`, extract title + body text via `html.parser`,
  cap output at 20,000 chars (`--max-chars` flag), print final URL +
  truncation notice.
- Mounted via `subPath` at `/usr/local/bin/fetch-text`, `defaultMode: 0755`
  (single-file mount, same idiom as the byok-env profile.d shim; no PATH
  work needed).
- SOUL.md steering line (PVC, same manual-operation as D3): use `fetch-text
  <url>` for web pages; never raw `curl` for HTML.
- Kustomize note: manifests dir is plain (no configMapGenerator here);
  changing the script requires no pod roll (binary not projected via env),
  but kubelet subPath staleness applies — script edits need a pod restart,
  acceptable for a rarely-edited helper. Documented inline.

### D5 — Documentation

- Gotchas one-liners (`agents/rules/frank-gotchas.md`):
  - *other-apps / LiteLLM section:* hermes custom-alias context resolution
    falls back to 256K — set `providers.<p>.models.<id>.context_length`;
    Ollama truncates front-first + silently past `OLLAMA_CONTEXT_LENGTH`
    (only signal: runner `truncated = 1`); a giant tool result poisons the
    session permanently (history re-sent every turn).
  - *Agent shells section:* `gemma4:12b-64k` exists because Modelfile
    `num_ctx` is the per-model escape hatch from litellm#12930.
- Full prose + recovery commands in `docs/runbooks/frank-gotchas/other-apps.md`
  and `agent-shells.md`.
- Retroactive updates to building-33 and operating-28 posts (fix/extension
  workflow — no new posts): incident narrative + the new default model +
  fetch-text guidance.
- `/sync-runbook` after plan lands (manual-operation blocks in D3/D4).

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-06-06--orch--hermes-context-survival | `derio-net/frank` | `docs/superpowers/plans/2026-06-06--orch--hermes-context-survival/` | — |

## Test Plan (post-merge — operator-driven, agent-assisted)

1. `ssh agent@192.168.55.226` → start hermes → confirm default model is
   `gemma-12b-64k-nothin` with context 65,536 (`/info`).
2. Ask Hermes to read
   `https://blog.derio.net/frank/docs/building/33-hermes-shell/` — expect it
   to use `fetch-text` (not raw curl) and summarize successfully.
3. Follow-up question requiring memory of turn 1 ("what did I ask you to read,
   and what was the third section about?") — expect correct recall.
4. `kubectl logs -n ollama deploy/ollama --since=30m | grep "truncated = 1"`
   — expect zero hits during the session.
5. `ollama ps` during the session — expect `gemma4:12b-64k`, `CONTEXT 65536`,
   `100% GPU`; `nvidia-smi` ≈ 9.7 GB.

## Out of scope

- 64k variants for the other 5 models (create on demand; same recipe).
- Paperclip/MOTD advertisement of the 64k aliases (follow-up if wanted).
- Hermes web search backend configuration (search ≠ extract; separate need).
- Raising `OLLAMA_CONTEXT_LENGTH` server-wide (would tax every model; the
  per-model Modelfile route is strictly better).
- ai-alert-helper `ANALYST_NUM_CTX` stays 16384 (its model stays
  mistral-small-24b per the 2026-06-06 analyst evaluation).

## Risks

| Risk | Mitigation |
|------|------------|
| Chart `models.create` behavior at startup (ordering, idempotency) untested on Frank | Implementation phase verifies on the live rollout; create-from-existing-blobs is instant |
| 64k prefill latency on long sessions (~15-20s worst case) | Accepted in Q&A; compressor keeps typical prompts far below max |
| Hermes `providers.<p>.models` schema drift across hermes upgrades | Override read path verified in v0.15.2 source (config.py `get_custom_provider_context_length`); pin noted in manual-op block |
| `/mode` to a 16k model mid-session that already grew past 16k | Truthful budgets make hermes compress on switch; residual risk documented in operating-28 |
