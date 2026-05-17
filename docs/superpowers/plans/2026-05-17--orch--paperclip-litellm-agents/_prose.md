# Paperclip via LiteLLM (opencode + hermes adapters) — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-17--orch--paperclip-litellm-agents-design.md`
**Status:** Not Started
**Layer:** `orch` (fix/extension of existing Paperclip deployment)

## Narrative

The spec laid out the design; this plan implements it in five working phases plus the auto-appended post-deploy checklist. The shape mirrors the spec's structure but front-loads all the plan-time-only verifications into a single Phase 1 so risks surface before any manifest change lands. The two adapter wirings (opencode in Phase 2, hermes in Phase 3) are independent — they can execute in parallel after Phase 1 — and the MOTD / runbook / stale-comment cleanup waits for both before documenting them in Phase 4. Phase 5 is the only manual phase: hiring agents through Paperclip's UI to satisfy the cluster rule that a layer isn't "Deployed" until its workflow has run end-to-end.

### Why Phase 1 exists as a standalone phase

Three open assumptions from the spec must be resolved before manifest commits:

1. **opencode `model` field shape.** Whether opencode wants `litellm/qwen-coder-14b` or bare `qwen-coder-14b` once `provider.litellm` is declared. Different opencode versions disagree.
2. **Hermes `--model <name>` argument shape.** Whether Hermes accepts a backend `name` from the inference chain (the most ergonomic choice), or whether it always expects `provider/model` or a bare model ID.
3. **Hermes session-DB write path.** `$HERMES_HOME` will be a read-only ConfigMap mount in Phase 3, so Hermes must NOT default its session DB to that location. The override key in `config.yml` must be identified at plan time, otherwise hermes will fail on first write.

Each of these is a CLI-behavior observation, not a Paperclip-side change — they're cheaper to discover by running the CLIs against LiteLLM from the shell sidecar than by guessing in YAML and bouncing the pod three times.

### Phase 1 doubles as the bootstrap install

Verifying CLI behavior requires installing the CLIs first. Phase 1's installs land on the shared `/paperclip` PVC in the same locations Phases 2 and 3 will rely on (`/paperclip/agent-bin/node_modules/.bin/opencode`, `/paperclip/agent-bin/bin/hermes`). The wiring phases then add the declarative inventory entry so the install survives PVC wipes — but the wiring phases never have to re-install, which keeps them fast and PR-shaped.

### Phase 2 and 3 are independent verticals

Each phase delivers one fully-wired adapter end-to-end: ConfigMap → mount → env → smoke test against LiteLLM. If hermes turns out harder than opencode (likely — Python on a Node-only container is the non-trivial part), opencode still lands on its own merits and provides a working LiteLLM-backed adapter for Phase 5's hire.

### Phase 4 is docs-first

External docs (MOTD, runbook, stale comment) are batched because they document things readers compare in one place — if a reader needs to know "how do I hire a LiteLLM-backed agent," they want both adapters covered in one location, not two PRs of context they have to merge in their head.

### Phase 5 is the real success criterion

Per `agents/rules/frank-gotchas.md`:

> A layer is not "Deployed" until its workflow has been triggered + observed end-to-end. ArgoCD Synced/Healthy proves artifacts exist; not that they work.

So Phase 5 is non-skippable: hire one agent of each adapter type, assign each a trivial issue, watch the transcripts complete, and confirm in LiteLLM's logs that the calls were routed to Ollama. Only then does Phase 6 (post-deploy) run.

## Plan-time verification log

To be populated as Phase 1 executes. Each entry: timestamp, finding, evidence (command output excerpt or LiteLLM log line).

### opencode

- _(P1.T1.S3 — working model shape)_
- _(P1.T1.S3 — env interpolation behavior)_
- _(P1.T1.S4 — LiteLLM route confirmation)_
- _(P1.T3.S1 — runtime-config-copy verification)_

### hermes

- _(P1.T2.S2 — install + relocatable venv verification)_
- _(P1.T2.S3 — both-containers reachability)_
- _(P1.T2.S4 — working `--model` shape)_
- _(P1.T2.S5 — session-DB default + override syntax)_
- _(P1.T2.S6 — LiteLLM route confirmation)_

### Resolutions for Phase 2/3/4

- _(P1.T4.S1 — exact deployment.yaml diff drafted)_
- _(P1.T4.S2 — exact external-secret-llm.yaml comment drafted)_

## Deployment Deviations

To be populated during execution. Each entry: phase + step, observed deviation, decision, links.

## References

- Spec: `docs/superpowers/specs/2026-05-17--orch--paperclip-litellm-agents-design.md`
- Frank gotchas process rule: `agents/rules/frank-gotchas.md` (#process / practice)
- Post-deploy checklist rule: `agents/rules/plan-post-deploy-checklist.md`
- Paperclip deployment manifest: `apps/paperclip/manifests/deployment.yaml`
- LiteLLM values + model aliases: `apps/litellm/values.yaml`
