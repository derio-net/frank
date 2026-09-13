# Paperclip LiteLLM-backed agents — fold #382 into the house structure

**Layer:** orch · **Kind:** layer extension (docs-only) · **PR:** derio-net/frank#382
**Branch:** `chore/paperclip-doc-touchups`

## Goal

PR #382 appended two old-layout sections to the Paperclip posts. They document how
Paperclip hires `opencode_local` and `hermes_local` agents that run on Frank's own
inference through LiteLLM:

- `## Two CLIs Through One Gateway` in `building/15-paperclip`
- `## LiteLLM-Backed Agents` in `operating/18-paperclip`

That content exists nowhere else on the blog. Finish the PR in four moves:

1. Re-check every claim against the running cluster.
2. Correct the claims that drifted since May 2026.
3. Fold the material into each post's current house structure.
4. Get the PR through review.

## Operator decisions (batched Q&A, 2026-09-13)

| # | Decision |
|---|----------|
| d1 | **Fold into house sections**, not dedicated appended sections. |
| d2 | **CI waits for #787.** The PR stays a draft until #787 merges, then gets rebased. This PR makes no mermaid changes. |
| d3 | **Keep full hermes coverage**, updated to the current image. |
| d4 | **Post-merge Test Plan:** a rendered-page check on the live blog. |

## Verified reality (2026-09-13, Paperclip image `sha-8e6edcd`)

| Claim in #382 | Status | Evidence |
|---|---|---|
| `XDG_CONFIG_HOME=/etc/paperclip/opencode-base` ← `paperclip-opencode` ConfigMap | holds | live Deployment env + volumes |
| `HERMES_HOME=/paperclip/agent-bin/.hermes`, seeded by the `hermes-init` initContainer | holds | live Deployment; `config.yaml` present in the pod |
| Hermes v0.10.0 has no config/state split | holds | `hermes --version` → `v0.10.0 (2026.4.16)`; HERMES_HOME holds `state.db`, `sessions/`, `logs/`, `memories/` |
| The image bakes opencode **1.14.48**; the PVC install (1.15.3) is a *newer* fallback | **drifted** | image `/usr/local/bin/opencode` is **1.18.23**; PVC `/paperclip/agent-bin/node_modules/.bin/opencode` is still **1.15.3** (May 17) → the PVC copy is now the *older*, stale one |
| opencode adapter does `fs.cp` and merges only `permission` | holds | `packages/adapters/opencode-local/src/server/runtime-config.ts` L139/L152 |
| opencode needs `litellm/<alias>` | holds | smoke: `opencode run -m litellm/qwen-coder-14b` → `ack` |
| The `ollama-cloud/` prefix on the default model lets a bare `-m` route via LiteLLM | holds, **narrower than stated** | the adapter now always pushes `--provider <resolved>` unless the resolution is `auto` (`execute.ts` ~L430). For a bare `qwen-*`, the hint `["qwen","auto"]` resolves to `auto`, so no flag is passed and the config default wins. An alias matching a non-auto hint would get that provider forced, bypassing LiteLLM: `claude`→anthropic, `gpt-4`/`o1-`→openai-codex, `gpt-5`→copilot, `hermes-`→nous, `glm-`→zai, `kimi`→kimi-coding. Smoke: bare `-m qwen-think-14b` → `Acknowledged.` |
| `VALID_PROVIDERS` lacks `ollama-cloud` → the UI provider field is a silent no-op | holds | `shared/constants.ts` L34–48; `resolveProvider` drops invalid explicit providers |
| The UI stores `extraArgs` as one argv token | **drifted** | `cfgStringArray` accepts only a string array; a single string is ignored entirely (`execute.ts` L69) |
| The session ID is truncated to 16 chars → the 2nd heartbeat onward breaks; workaround `persistSession: false` | holds | `execute.ts:594` `parsed.sessionId.slice(0, 16)`; `persistSession` still honoured (L346/L456); derio-net/paperclip#1 still OPEN |
| Stranded-agent SQL on `agent_task_sessions(session_params_json, session_display_id)` | holds | `\d agent_task_sessions` |
| Pod selector `-l app=paperclip` | **wrong** | the pod carries `app.kubernetes.io/name=paperclip`; `app=paperclip` matches nothing |
| `kubectl logs deploy/litellm \| grep POST` proves routing | **unreliable** | LiteLLM runs 5 replicas and `deploy/` reads one pod. `blackbox-exporter` (the `litellm_chat` probe) also POSTs, so the grep must filter on the Paperclip pod IP across all pods. Verified: two POSTs from `10.244.10.187` across two replicas |
| "see Database Health above" | **dangling** | no such section; the psql recipe lives under `## Verify` |
| `paperclip-shell-reconcile` in the sidecar | holds | `/usr/local/bin/paperclip-shell-reconcile` |

Adjacent drift inside sections this change touches: the post says the Paperclip pod is `1/1 Running`, but it is really `2/2` (app container plus shell sidecar). Fix it here because the healthy-state list gains CLI bullets.

Live usage: one `opencode_local` agent is hired and no `hermes_local` agents.

## Design — where content lands

### building/15-paperclip (diataxis: tutorial)

- **New `## Hiring Agents on Local Inference`**, placed after `## Shell Sidecar` and before
  `## Missteps`, containing:
  - `### opencode — config for the binary that wins on PATH`: `XDG_CONFIG_HOME` ConfigMap, the adapter's `fs.cp` + `permission`-only merge, and the PVC install now being the stale copy.
  - `### hermes — a writable home seeded on every boot`: `HERMES_HOME` on the PVC plus the `hermes-init` initContainer, with a YAML excerpt of the seeded `config.yaml`.
  - `### Two model shapes through one gateway`: `litellm/<alias>` versus a bare alias, and why the bare form routes. It covers the adapter's `--provider` rule and the `qwen → auto` hint, and warns which alias families would be hijacked.
  - A short closing paragraph with the portable lesson (config/state boundary), without the plan-internal "Phase 1" session residue.
- **`## Missteps` gains rows:**
  1. the PR #296 `--provider` wrapper, which was subcommand-scoped, unnecessary, and reverted;
  2. the `litelllm` alias typo, which the probe of the hand-convenient CLI path missed;
  3. the session-ID truncation (upstream, paperclip#1, `persistSession: false`).
- **`## Recovery Path` gains rows:**
  - opencode `Model not found` → use `litellm/<alias>`
  - hermes `No LLM API keys found` / routes to a cloud provider → check the seeded `config.yaml` and a non-`auto` model-prefix hint
  - hermes `Session not found` on the 2nd heartbeat → `persistSession: false`
  - hermes fails on first write → `HERMES_HOME` read-only
- **Frontmatter:**
  - bump `last_updated` to 2026-09-13
  - add `opencode` and `hermes` to `tags`
  - extend `reader_goal` with hiring LiteLLM-backed agents
- **`## References`** gains `apps/paperclip/manifests/configmap-opencode.yaml`, `configmap-hermes.yaml`, and derio-net/paperclip#1.

### operating/18-paperclip (diataxis: how-to + reference)

- **What Healthy Looks Like:** fix `2/2`, and add a "both agent CLIs answer through LiteLLM" bullet.
- **Verify:** add the opencode and hermes smoke commands, using the image binary and the `bin/hermes` shim the adapter invokes. Add the routing proof: take the pod IP via `app.kubernetes.io/name=paperclip`, then grep all running LiteLLM pods for that IP.
- **Steps:**
  - `### Hire a LiteLLM-Backed Agent`: model-field table, leave `provider`/`extraArgs` blank, and `persistSession: false` for hermes.
  - `### Recover CLIs on a Cold PVC`: an `ls` check plus reconcile; `hermes-init` re-seeds `config.yaml`.
- **Recover:**
  - `### hermes Agent Fails from the Second Heartbeat`: symptom, cause, prevention.
  - `### Stranded hermes Agent`: the SQL, pointing at the Verify psql recipe.
- **Missteps rows:**
  - the UI provider/`extraArgs` fields assumed to work
  - `deploy/litellm` logs assumed to prove routing
- **Quick Reference rows:** both smoke commands and the routing grep.
- **Frontmatter:** bump `last_updated` and `last_updated_commit` (the latter is set at delivery), and extend `reader_goal`.
- The old appended `## LiteLLM-Backed Agents` section is removed entirely. Everything in it moves into the sections above.

### Spec-review additions (2026-09-13)

- **building/15 `## References`:** drop `apps/paperclip-extras/`. It does not exist; the sidecar PVC and ConfigMaps live under `apps/paperclip/manifests/`.
- **building/15 `## What Transfers`:** add a closing section before References, carrying the portable lessons. The lint's `what_transfers` check expects one on a tutorial, and the warning already existed on `main`.
- **operating/18 cold-PVC step:** the shell MOTD tip also fires when the PVC copy of opencode is missing (`configmap-shell-motd-tips.yaml` checks both), so say a reconcile restores both.

## Constraints

- Frank voice at `voice_level: balanced`. Keep the persona thin and the commands verifiable.
- Blog gates must pass locally:
  - `validate_educational.py` (reader_goal, diataxis, actionable sections carry commands)
  - `scripts/tests/test_actionable_sections_carry_commands.py`
  - the frontmatter validators
  - `hugo --minify`
  - the AI-tells lint (warnings reviewed)
- No new mermaid. The `validate_mermaid_layout` failure on 5 pre-existing diagrams belongs to #787 (d2).
- No cluster mutation. Every command in the posts was run read-only or as a smoke call on 2026-09-13.

## Out of scope

- Narrowing the 5 over-budget diagrams (#787).
- Other stale facts in untouched sections of either post (e.g. the architecture diagram's `OPENAI_API_KEY` labels, Recover's `app.kubernetes.io/name` selectors).
- Removing the stale PVC opencode install from `configmap-shell-inventory.yaml`. That is a manifest change and is noted in the PR as a follow-up.

## Test Plan (post-merge — operator-driven)

After the blog deploys:

1. Open `building/15-paperclip` and `operating/18-paperclip` on the live blog.
2. Confirm the new sections render and the cross-post `relref` links resolve.
3. Confirm the Quick Reference commands match the post body.
