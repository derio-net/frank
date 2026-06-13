# Plan — hermes-agent-shell: PVC-resident venv + baked auto-continue patch (#496)

Implements [frank#496](https://github.com/derio-net/frank/issues/496) per the
design spec `docs/superpowers/specs/2026-06-07--orch--hermes-agent-shell-pvc-venv-design.md`.

## Why

The `agent` user (uid 1000) in the `hermes-agent-shell` pod cannot patch or
maintain the root-owned `/opt/hermes-agent` Hermes venv (no privesc;
`fsGroup` doesn't touch image-baked files). Operator-chosen fix (Q&A):

1. **PVC-resident venv** — the live venv moves to `/home/agent/.local/opt/hermes-agent`
   (uid-1000-owned, writable, persists across restarts), seeded on first boot
   from a **relocatable** image seed at `/opt/hermes-agent`. Proven:
   `uv venv --relocatable` + `cp -a` runs at the new path.
2. **Bake the auto-continue patch** — widen Hermes' announce-only countermeasure
   gate from `codex_responses` to also fire on `chat_completions` (the LiteLLM
   path Frank uses), permanently fixing the qwen36-a3b "announce then idle"
   stall.

## Cross-repo shape

- **Phase 1 (agentic, agent-images)** is the substantive deliverable: Dockerfile
  relocatable seed venv, first-boot version-aware seed hook, baked patch,
  tests, README. Ships as its **own PR** in `derio-net/agent-images`. (agent-images
  is not fr-enabled — it holds no plan folder; this frank plan tracks the work.)
- **Phase 2 (manual, back-loaded, frank)** can only run after Phase 1 merges and
  CI publishes the new commit-SHA image tag. The operator runs `/bump-image`,
  adds the runbook gotcha, and updates the existing blog posts. It ships in the
  **frank PR deliberately unimplemented**, marked for the operator.

`depends_on` is within-plan only; the real Phase-2-after-Phase-1 dependency is a
cross-PR ordering enforced by the build chain (frank's target SHA does not exist
until agent-images CI builds it).

## Verification

TDD throughout Phase 1 (bats tests red→green for the patch and the seed hook;
the Docker build + extended `smoke-test-hermes-agent-shell` are the integration
gate — build fails loudly if the patch does not apply; smoke asserts the live
PVC venv is uid-1000-writable, `hermes` runs from it, and the widened gate is
present). The post-merge Test Plan (spec `## Test Plan`) confirms live-pod
behaviour and the stall fix via the operator's session-replay matrix.
