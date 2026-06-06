# Hermes Context-Window Survival

**Spec:** `docs/superpowers/specs/2026-06-06--orch--hermes-context-survival-design.md`
**Status:** In progress

One `curl -s` of a 208 KB blog page killed a Hermes shell session on
2026-06-06: Ollama silently truncated every subsequent prompt front-first at
`OLLAMA_CONTEXT_LENGTH=16384` while Hermes believed the window was 256,000
tokens (its resolver's default fallback for unknown custom aliases), so its
compressor never engaged and the oversized tool result poisoned the session
history permanently.

Three-layer fix, one phase each plus a back-loaded manual phase:

1. **Phase 1 — 64k inference path.** `gemma4:12b-64k` declared via the otwld
   chart's `ollama.models.create` (Modelfile `PARAMETER num_ctx 65536` — the
   per-model escape hatch from litellm#12930), exposed as LiteLLM aliases
   `gemma-12b-64k` / `gemma-12b-64k-nothin`. Measured cost on gpu-1: +846 MiB
   over the 16k baseline, 100% GPU (9,686 / 16,303 MiB).
2. **Phase 2 — fetch-text helper.** Stdlib-only ConfigMap script mounted at
   `/usr/local/bin/fetch-text` (subPath, 0755), TDD'd via a `--stdin` mode so
   pytest exercises the exact bytes the ConfigMap ships.
3. **Phase 3 — docs.** Gotchas one-liners + runbook prose, retroactive
   building-33 / operating-28 updates (fix/extension workflow — no new posts),
   runbook sync.
4. **Phase 4 — [manual]** post-merge verification, the two hermes PVC
   manual-operations (truthful `context_length` overrides + default model +
   `tool_output.max_bytes`; SOUL.md fetch-text steering), and the full-replay
   Test Plan chosen in the Q&A.

Key invariant introduced: **hermes config.yaml `context_length` values must
equal the live server reality** (64k pair = 65536, everything else =
`OLLAMA_CONTEXT_LENGTH` = 16384). The compressor
(`compression.threshold: 0.5`, already enabled) does the rest.

Operator decisions (batched Q&A 2026-06-06): 64k size; default model
`gemma-12b-64k-nothin`; ConfigMap helper over paid extract backends or
image bake; full-replay test plan.
