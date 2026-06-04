# Hop Security Trace Analyst

**Spec:** docs/superpowers/specs/2026-06-04--obs--security-trace-analyst-design.md
**Status:** In Progress

## What this builds

ai-alert-helper grows from a one-way narrator into a two-way security analyst.
The operator messages `@agent_zero_cc_bot` in the existing alert chat; the
local LLM (`mistral-small-24b` via LiteLLM) investigates scan/attack traces in
VictoriaLogs through six curated read-only tools plus a guarded LogsQL escape
hatch, and answers in-thread. Slash commands (`/scan_patterns 6h`,
`/attacker_profile <ip> 24h`, `/logsql <q>`) invoke the same tools
deterministically — no LLM, no GPU dependency — so the query path survives
gpu-1 saturation (the 2026-06-04 failure mode that motivated half this design).

The trace-analysis expertise is written once: the canonical playbook at
`apps/ai-alert-helper/skill/SKILL.md` is mounted into the pod via a Kustomize
configMapGenerator (hash-suffixed → pod rolls on every edit) AND discovered by
Claude Code through the registry pointer `agents/skills/hop-trace-analysis/`.
The canonical file lives inside the kustomize root because the load restrictor
forbids out-of-root refs and out-of-bounds symlinks are a known GitOps-loop
killer in this repo.

## Phase shape

1. **Skill + enriched facts** — the playbook, four new fact builders
   (scan-probe counts, attacker IPs, scanned paths, CrowdSec decision detail
   parsed from the VictoriaLogs trail — Hop's LAPI is unreachable from Frank),
   digest wiring, and the `LLM_MODEL_FALLBACK`-optional code fix. Value lands
   before any agent exists: sharper digests, a usable skill.
2. **Tool registry + commands** — `tools.py` with caps enforced in dispatch
   (≤50 rows, ≤4KB, ≤6 rounds, 120s), schema generation, slash-command parsing,
   entities-based monospace replies. Help/tools/setMyCommands all render from
   one registry dict.
3. **Analyst + poller + manifests + image** — the agent loop with explicit
   context budgeting (`num_ctx` via the verified pass-through; Ollama's 4096
   default silently truncates), the chat-ID-gated getUpdates poller, the
   plain-directory→kustomize conversion with a `kustomize build` diff gate
   before the `prune: true` flip, version 0.2.0, branch image build.
4. **[manual] Post-merge** — operator merges the single PR; spec §13 Test Plan
   runs operator+agent; blog retro-updates; status → Deployed.

## Verification posture

TDD throughout (the repo's pytest fixture pattern in
`apps/ai-alert-helper/src/tests/`). Pre-merge: full suite green,
`POST /ask?dry_run=true` tool-trace, kustomize diff evidence, GHCR tag present.
Live behavior is deliberately post-merge (ArgoCD deploys from main): that is
the Test Plan, not a skipped step.
