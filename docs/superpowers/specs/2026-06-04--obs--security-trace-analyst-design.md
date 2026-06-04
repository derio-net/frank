# Design: Hop Security Trace Analyst

**Date:** 2026-06-04
**Layer:** obs (extends the ai-alert-helper observability stack)
**Status:** Draft — pending operator review

## 1. Goal & scope

Turn ai-alert-helper from a one-way narrator into a two-way security analyst. The operator replies to (or messages) `@agent_zero_cc_bot` in the existing alert chat; the local LLM investigates scan/attack traces in VictoriaLogs through curated tools and answers in-thread. The same expertise ships as a repo skill (`agents/skills/hop-trace-analysis/`) so Claude Code and the analyst share one source of truth. The first cut also enriches the security facts (CrowdSec decision detail, attacker-IP/path aggregations) that both the digest and the analyst draw on.

**Out of scope (deferred):**

- New Grafana/CrowdSec alert *rules* — let a few weeks of Q&A reveal which alerts earn their keep.
- Frontier-model fallback — the cluster runs local inference only (PR #461). The analyst inherits that constraint.
- Non-security alert Q&A — the poller and loop are alert-domain-agnostic by construction, so this extends later without rework.

## 2. Architecture

Everything runs inside the existing `ai-alert-helper` Deployment. Single replica is not just inherited — Telegram allows exactly one `getUpdates` consumer per bot token, so the design *requires* it.

```
Telegram chat ──getUpdates long-poll──▶ poller (asyncio task, chat-ID gate)
                                          │
                          ┌── command? ───┴── question?
                          ▼                    ▼
                   command dispatch      analyst loop (analyst.py)
                   (no LLM, no GPU)      system prompt = SKILL.md (ConfigMap)
                          │                    │ tool calls (≤6 rounds)
                          └────────┬───────────┘
                                   ▼
                     tools.py — curated wrappers over facts.py
                     queries + free-form LogsQL escape hatch
                                   │ HTTP, read-only
                                   ▼
                  VictoriaLogs (+ GoatCounter for visitor facts)
                                   │
                answer ──sendMessage──▶ same Telegram thread
```

**New modules:** `analyst.py` (poller, command dispatch, agent loop), `tools.py` (tool schemas, argument validation, dispatch, result caps).
**Touched modules:** `facts.py` (enriched queries, refactored so tools and fact-sheet builders share them), `telegram.py` (`getUpdates`, reply-to-message, `setMyCommands`), `api.py` (start poller in FastAPI lifespan; add `POST /ask?dry_run=true`).

## 3. Phases

**Phase 1 — Expertise + enriched facts.** Value lands before any agent exists:

- `agents/skills/hop-trace-analysis/SKILL.md`: the field-schema map (fluent-bit vs Loki-push field names), canonical LogsQL patterns per question type, the known-baseline table (ArgoCD reconcile Notices, blackbox probe identity, headscale-backup Critical), and a scan-classification playbook (scanner vs crawler vs targeted probe).
- New fact builders in `facts.py`:
  - `crowdsec_decisions_detail` — IP, scenario, country, duration per decision, parsed from CrowdSec's log trail in VictoriaLogs (fluent-bit path). The helper runs on Frank and cannot reach Hop's LAPI ClusterIP (Tailscale routes LAN CIDRs only, not the kube service CIDR), so the log trail is the only viable source. If the trail proves too lossy, exposing LAPI read-only over the mesh becomes a named follow-up — not part of this design.
  - `top_attacker_ips` / `top_scanned_paths` — Caddy 4xx/404 aggregations, probe-excluded.
  - `scan_pattern_counts` — hit counts for known probe paths (`/wp-login.php`, `/xmlrpc.php`, `/.env`, `/.git/config`, admin panels).
- Wire the new facts into `prompts/digest.txt` so daily digests name attackers instead of counting them.

**Phase 2 — The analyst.** Poller, command dispatch, agent loop, tools, ConfigMap mount, image bump, deploy. The phase closes only after a real Telegram question about a real scan gets a correct in-thread answer (workflow triggered and observed end-to-end, per house rule).

## 4. Tool surface — curated + escape hatch

All tools are read-only, probe-excluded by default, and return compact JSON.

| Tool | Backing | Typical question |
|---|---|---|
| `edge_traffic(window, group_by, host?, status_class?)` | Caddy logs | "what hit the blog last hour?" |
| `attacker_profile(ip, window)` | Caddy logs | "what did 1.2.3.4 do?" — paths, UAs, status mix, first/last seen |
| `falco_events(window, priority?, rule?)` | Falco stream | "any Criticals overnight?" |
| `crowdsec_decisions(window)` | CrowdSec logs in VictoriaLogs | "who got banned and why?" |
| `scan_patterns(window)` | Caddy logs | "are we being scanned?" |
| `logsql_query(query, limit)` | escape hatch | anything the templates miss |

Hard caps live in dispatch code, outside the model's control: ≤ 50 result rows and ~4 KB per call, ≤ 6 tool rounds per question, ≤ 120 s wall clock per question. The escape hatch enforces a `_time` filter, rejects anything but select-path queries, and the HTTP layer only ever calls `/select/*` endpoints — that last constraint is the real guarantee.

## 5. Telegram command interface

Messages starting with `/` bypass the LLM entirely and hit the dispatch layer as deterministic code. This gives a help system, direct tool access, and — because no model is involved — a query path that works even when gpu-1 is saturated or down.

- **`/help`** — lists every command with its usage line and one example each. Also sent as the reply to any unparseable command.
- **`/tools`** — the curated tool list with parameter signatures (the same table the LLM sees).
- **Direct invocation** — one slash command per curated tool, positional args first, then `key=value`:
  - `/edge_traffic 1h group_by=host`
  - `/attacker_profile 1.2.3.4 24h`
  - `/scan_patterns 6h`
  - `/falco_events 12h priority=Critical`
  - `/crowdsec_decisions 24h`
  - `/logsql request.host:"blog.derio.net" _time:1h | stats by (status) count()`
- **Output:** fixed compact formatting of the tool's JSON (monospace block), no narration. Suffix ` explain` (e.g. `/scan_patterns 6h explain`) routes the result through the LLM for a one-paragraph read — explicit opt-in to the GPU dependency.
- **`/reset`** — clears conversation history.
- **Discovery:** at startup the poller calls Telegram's `setMyCommands` with the command list, so the client's `/` menu autocompletes them. The list is generated from the tool registry — one source, no drift.

Parse errors reply with that command's usage line, not a generic error.

## 6. Model & context strategy

- **Model:** `mistral-small-24b` (function calling, fully VRAM-resident, 128K-capable). Configured as `LLM_MODEL_ANALYST`, independent of the digest's `LLM_MODEL_PRIMARY`.
- **Context:** Ollama defaults to `num_ctx=4096` and silently truncates (observed live 2026-06-04: `prompt=5691 keep=4 new=4096`). Every analyst request sets `num_ctx` explicitly — target 16384, fallback 8192. The override must travel via LiteLLM's `extra_body` → Ollama `options` pass-through (the same proven path as `qwen36-a3b-nothin`'s `think: false`); a top-level `num_ctx` param is silently dropped. `LLM_MODEL_ANALYST` is net-new env wiring on the Deployment. The loop tracks (system prompt + history + tool results) against the budget and evicts oldest tool results first; it never relies on server-side truncation.
- **VRAM risk:** KV cache at 16K on the 24B model is the main unknown on a 16 GB card. Phase 2 includes a measurement step (`ollama ps` CPU/GPU split before and after) with the 8192 fallback decision documented in the plan.
- **No fallback model:** per the local-only policy, an LLM failure produces a loud in-channel error, not a silent cloud retry. Direct commands (§5) remain available throughout.

## 7. Expertise sharing — one file, two runtimes

The canonical playbook is `apps/ai-alert-helper/skill/SKILL.md` — it must live *inside* the kustomize root because Kustomize's load restrictor forbids out-of-root file refs and out-of-bounds symlinks are a known GitOps-loop killer in this repo. `agents/skills/hop-trace-analysis/SKILL.md` is the thin registry pointer (frontmatter + "read the canonical file") so skill discovery still works:

- **Claude Code** discovers the registry skill, which directs it to the canonical playbook.
- **The analyst** receives it via a Kustomize `configMapGenerator` (hash-suffixed name, whole-file key — the homepage subPath gotcha rules out live-updating subPath mounts; the hash suffix rolls the pod on every content change). `analyst.py` loads it at startup.

**Conversion required (explicit Phase 2 step):** `apps/ai-alert-helper/manifests/` is today a *plain directory* sync (`path:` source, `prune: false` in `apps/root/templates/ai-alert-helper.yaml`). Adopting the generator means (a) adding a `kustomization.yaml` that enumerates all four existing manifests — any manifest left out vanishes from the render — and (b) flipping the Application to `prune: true` so superseded hash-suffixed ConfigMaps are garbage-collected. The prune flip is a real blast-radius change on an app that has never pruned; it gets its own reviewed step with a `kustomize build` diff against the live render before merging.

The file carries two marked sections: an **agent-runtime section** (terse, token-budgeted, ~1,500 tokens — field map, query patterns, baselines, classification rules) and a **human section** (full prose, examples, narrative). The loader extracts only the former. Editing expertise = git commit → ArgoCD sync → pod rolls. No image rebuild.

## 8. Conversation state

In-memory, per-chat: last ~6 exchanges, 30-minute idle expiry, `/reset` to clear. Process-global state is already the established pattern here (surge de-dup), with the same justification: single replica, one uvicorn worker, restart loses only conversational nicety. No PVC.

## 9. Security boundary

- **Inbound gate:** updates from chat IDs other than `FRANK_C2_TELEGRAM_CHAT_ID` are dropped and logged at WARNING — someone probing the bot is itself a security signal.
- **Read-only by construction:** tools reach only VictoriaLogs `/select/*`. No kubectl, no writes, no shell.
- **Prompt injection from logs:** attacker-controlled strings (UAs, paths, referrers) enter the model's context by design. Mitigations: tool results are wrapped in delimited blocks with a system-prompt rule that block content is data, never instructions; tool dispatch is deterministic code, so a poisoned UA cannot invoke anything — the worst case is a misleading narrative; replies are length-capped; and the bot only talks to the operator's chat. This is the digest's existing trust posture, made explicit.
- **getUpdates exclusivity:** `replicas: 1` and `strategy: Recreate` documented on the Deployment so old and new pods never poll concurrently.

## 10. Failure behavior & observability

Fail loud, in-channel: tool errors and LLM timeouts produce a short "couldn't complete: <reason>" reply, never silence. The poller task catches its own crashes and restarts with backoff; a dead poller logs at ERROR, which fluent-bit ships to VictoriaLogs (the helper watches Hop; Frank's log pipeline watches the helper). Every Q&A logs question, tool calls, durations, and token counts — `kubectl logs deploy/ai-alert-helper | grep analyst` is the audit trail.

## 11. Testing

- **Phase 1:** pytest per new fact builder against recorded VictoriaLogs JSON fixtures (existing test pattern). The skill is validated by using it from Claude Code on a real recent scan before the phase closes.
- **Phase 2:** unit tests for tool dispatch (caps, arg validation, escape-hatch rejection rules, command parsing); `POST /ask?dry_run=true` returns the full tool-call trace for a canned question without touching Telegram; end-to-end gate = a real Telegram question about a real scan, answered correctly in-thread.

## 12. Rollout

- **Phase 1:** pure git — skill file, fact builders, digest prompt, helper version bump through the existing `build-ai-alert-helper.yml` workflow (bump the hardcoded tag with the version, per the obs-digest runbook).
- **Phase 2:** second image bump (analyst + tools), ConfigMap and Deployment changes in the same PR, ArgoCD sync, verification per §11.
- **No manual operations anticipated:** the bot token already has the needed scope; `getUpdates` and `setMyCommands` need no BotFather changes.
- **Rides along:** make `LLM_MODEL_FALLBACK` optional in code, closing the 2026-06-04 workaround that points it at the primary.

## 13. Test Plan (post-merge, operator-driven)

Run after the Phase 2 PR merges and ArgoCD syncs. The agent drives; the operator confirms what the agent can't reach (the Telegram client).

1. **Rollout health:** `ai-alert-helper` Application Synced/Healthy; new pod Running with the analyst ConfigMap mounted (`kubectl describe pod` shows the hash-suffixed name); superseded ConfigMaps pruned.
2. **Discovery:** in Telegram, `/` shows the command menu (setMyCommands took); `/help` and `/tools` reply with usage and the tool table.
3. **No-LLM path:** `/scan_patterns 6h` and `/edge_traffic 1h group_by=host` return data in monospace blocks — verify timing feels instant (no GPU dependency).
4. **Parse errors:** `/attacker_profile` with no args replies with that command's usage line, not a stack trace or generic error.
5. **LLM path:** one natural-language question about a real recent scan (e.g. "who scanned the blog today and what were they after?") — answer arrives in-thread, cites tool-derived facts (IPs/paths/UAs), and the Deployment log shows the tool-call trace.
6. **Explain opt-in:** `/scan_patterns 6h explain` returns the LLM narration of the same data.
7. **State:** follow-up question uses prior context; `/reset` clears it (next question lacks the context).
8. **Security gate:** a message from a non-allowlisted chat (second Telegram account or group) gets no reply and produces a WARNING log line.
9. **Context budget:** Ollama logs show NO `truncating input prompt` lines during the above; `ollama ps` during a question shows the analyst model's CPU/GPU split — record it; if KV cache pushes past VRAM at 16384, drop to 8192 per §6 and re-verify.
10. **Digest regression:** next morning's 08:00 digest still arrives (the poller didn't break the cron path).

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-06-04--obs--security-trace-analyst | `derio-net/frank` | `docs/superpowers/plans/2026-06-04--obs--security-trace-analyst/` | — |
