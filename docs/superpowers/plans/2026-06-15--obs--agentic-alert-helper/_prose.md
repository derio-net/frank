# Agentic Alert-Helper (frank — Plan B)

**Status:** Implemented (agentic phases 1-7) — pending merge. Remaining gate (post-merge, operator-driven): Phase 8 manual `claude login` (manual-op `obs-alert-agent-claude-login`) + the four-trigger end-to-end verification. Set to **Deployed** after that. Consumes the agent-images `multi-agent-shell@56c652e` image (Plan A, merged).
**Spec:** `docs/superpowers/specs/2026-06-15--obs--agentic-alert-helper-design.md` (Part B + Cutover)
**Layer:** obs (replaces the retired `apps/ai-alert-helper`)

## Why

The old `ai-alert-helper` calls LiteLLM→Ollama to write its narrative, so it dies when local
inference dies (a circular dependency the GPU-timeshare exposed), and a single fixed LLM shot can't
investigate. This rebuilds it as an autonomous agent on the `multi-agent-shell` image — brain =
cloud `claude` (no local-inference dependency), able to investigate, conversational over Telegram —
keeping the tested `facts.py`/`surge.py` plumbing as deterministic tools.

## Depends on (cross-repo)

Consumes the `multi-agent-shell` image tag produced by **Plan A** (agent-images
`2026-06-15-agent-session-extract` — the baked `agent-session` + `AGENT_SESSION_SERVE`). `fr`
`depends_on` is within-plan only, so this gate lives here in prose: do not pin/deploy P5 before
Plan A's tag exists.

## Phase map

1. **frank-facts CLI** — port `facts.py`/`surge.py` to **stdlib urllib** (so it runs as a bare
   mounted script on the image's python3, like `fetch-text`), tests rewritten off `respx`.
2. **telegram-bridge** — single-consumer getUpdates poller ↔ `/session/send` + the deterministic
   outbound sender; allowlist; **timeout→deterministic-`frank-facts`-render fallback**.
3. **surge-gate + digest** — the deterministic gate wakes the (paid) agent only on a real surge
   (edge-trigger + cooldown) and once/day for the digest.
4. **grafana-webhook receiver** — alert → triage prompt → narrate; `/healthz` for the cutover check.
5. **alert-agent Deployment** — `multi-agent-shell` image, `AGENT_SESSION_SERVE=1`, PVC,
   **default SA / no RBAC (HTTP-only)**, ESO secrets, supercronic crontab, SKILL/SOUL.
6. **Cutover** — re-point the Grafana "AI Helper Webhook"; retire `apps/ai-alert-helper` **last**
   (after the new receiver is verified serving — see the spec's ordered Cutover).
7. **Post-Deploy Checklist.**
8. **[manual] `claude login`** — back-loaded; the agent's subscription auth (PVC-resident). Nothing
   agentic depends on it.

## Boundary

HTTP-only, read-only: VictoriaLogs/VictoriaMetrics/Grafana-alert-API/GoatCounter. **No kube
credential** (matches the old posture; cluster-API agentic investigation is Sympozium's deferred
slice). Named residual: exfil-via-narration to the allowlisted operator chat (accepted).

## Post-merge verification (operator-driven, needs `claude login`)

All four triggers deliver to Telegram and the agent demonstrably investigates: the daily digest, a
synthetic surge escalation, a test Grafana alert, an inbound allowlisted DM. Not Deployed until
observed.
