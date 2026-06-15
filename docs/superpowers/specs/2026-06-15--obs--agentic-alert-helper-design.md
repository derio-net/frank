# Agentic Alert-Helper + Extracted Persistent-Agent Interface

**Layers:** obs (frank — replaces the retired `apps/ai-alert-helper`) + agent-images (the reusable interface)
**Status:** Draft
**Date:** 2026-06-15
**Repos:** `derio-net/frank`, `derio-net/agent-images` (multi-repo)
**Supersedes:** `apps/ai-alert-helper/` (ns `ai-alert-helper-system`) — retired in this work.

## Implementation Plans

| Plan | Target repo | Slug | Status |
|------|-------------|------|--------|

> Multi-repo. The **agent-images** plan (bake the `agent-session` interface into the
> `multi-agent-shell` image) **gates** the **frank** plan (alert-agent + n8n migration consume the
> image-built-in driver). Sequence: agent-images merges → image builds → frank bumps the image SHA.

## Problem

The old `ai-alert-helper` (FastAPI app + two CronJobs, ns `ai-alert-helper-system`) builds a fixed
fact sheet (GoatCounter / VictoriaLogs / Caddy / Falco / CrowdSec) and makes **one** LiteLLM
chat-completion call to write a Telegram narrative. Two structural flaws:

1. **Circular dependency.** Its LLM call goes LiteLLM → Ollama. When local inference dies (the
   GPU-timeshare hands gpu-1 to ComfyUI — the steady state for now), it 500s. The tool meant to
   report "inference is down" dies *with* inference.
2. **No agency.** One fixed fact sheet + one LLM shot can't investigate, follow a thread, or answer
   a follow-up.

Separately, the mechanism for **driving a persistent agent session** (the n8n `agent-session`
driver, frank #540) is currently a ConfigMap copy-pasted inside `apps/n8n-01/`. This alert-agent is
the **second** consumer and a **third** is planned — the pattern wants extraction before it drifts.

## Goal

1. Rebuild the alert-helper as an **autonomous agent** on the `multi-agent-shell` image: resilient
   to local-inference outages (brain = cloud `claude`, not LiteLLM/Ollama), able to **investigate**,
   and **conversational** (DM the bot, it investigates and replies) — keeping the old deterministic
   data plumbing (`facts.py`/`surge.py`) as tools, with bounded cloud spend via deterministic gating.
2. **Extract the persistent-agent interface** (`agent-session`) into the `multi-agent-shell` image
   as a reusable, versioned contract every consumer shares; migrate n8n onto it.

---

## Part A — Reusable `agent-session` interface (agent-images)

Move the `agent-session` driver + bootstrap **out of n8n's ConfigMap and into the image**, beside
the existing `/usr/local/lib/multi-agent-shell/notify-telegram.sh`.

- **Location:** `multi-agent-shell/rootfs/usr/local/lib/multi-agent-shell/agent-session` (Python),
  symlinked to `/usr/local/bin/agent-session` (mirrors the existing `…-reconcile` symlink).
- **Contract (stable, documented in the image README):**
  - `agent-session serve` — HTTP on `127.0.0.1:${AGENT_SESSION_PORT:-8765}`, `POST /session/send
    {session_id, agent, message, timeout_s?} → {session_id, agent, status, turn, payload}`,
    `GET /healthz`. Drives the **running** session (never `-p`): bracketed-paste submit + per-turn
    nonce-file read (the file appearing + parsing = completion). Locked atomic turn counter.
  - `agent-session send '<json>'` — same core as a CLI (debug/manual).
- **Configurable agent** (the operator decision): `ensure_session` dispatches on the `agent` field
  via a small per-agent launch profile. `claude` (default) → `claude --permission-mode auto`
  (fully wired + verified). `antigravity` (`agy`) / `codex` → their own launch + auto-approve flags
  (config-selectable; verifying each is a follow-up). The profile table lives in the image so every
  consumer inherits new agents on image bump.
- **Bootstrap becomes a baked s6 service** (improvement over n8n's postStart hook, which has no
  ordering guarantee with the ENTRYPOINT): an s6-overlay **longrun** (`/etc/services.d/<svc>/run`)
  runs `agent-session serve` **directly** — s6 supervises restarts, so the n8n bootstrap's
  `while true … sleep 2` loop (needed only inside a tmux pane) is dropped. It also pre-trusts the
  workspace, **gated on `AGENT_SESSION_SERVE=1`** (default off — a plain interactive shell is
  unaffected; consumers opt in).
- **Genericize naming:** rename to `AGENT_SESSION_*` with the REAL source vars (verified against the
  driver + tests): `AGENT_SESSION_TURN_DIR ← STOA_TURN_DIR`, `_OUT_DIR ← STOA_OUT_DIR`,
  `_PORT ← STOA_SESSION_PORT`, `_POLL_S ← STOA_POLL_S`, `_SETTLE_S ← STOA_SETTLE_S`,
  `_NAME ← STOA_SESSION_NAME` (the last lives in the bootstrap, not the driver). The interface is
  generic infra, not stoa-specific (and shouldn't carry a private codename). Keep each `STOA_*` as a
  **deprecated alias** (read if the new var is unset) for one cycle so a consumer mid-migration never
  breaks.
- **Tests:** port the existing tmux-mock tests from `scripts/tests/test_agent_session_driver.py`
  (paste + file-write flow, turn counter, timeout, HTTP serve) into the image's `tests/`, **adding**
  new per-agent-dispatch tests for the launch-profile table (none exist today — the driver hardcodes
  claude). Re-point the test's driver-source fixture from the n8n ConfigMap path
  (`apps/n8n-01/manifests/agent-session-driver.yaml`) to the baked image file.
- **Output:** a new `multi-agent-shell` image tag carrying the baked `agent-session`.

This is the **gating deliverable** — frank consumes the new tag.

---

## Part B — alert-agent (frank, layer obs)

```
┌─ alert-agent  (Deployment, replicas:1, strategy:Recreate) ──────────────────────────┐
│  image: ghcr.io/derio-net/multi-agent-shell:<new tag>  (cloud claude, PVC login —   │
│                                                          NO LiteLLM/Ollama/GPU)      │
│  AGENT_SESSION_SERVE=1  → baked agent-session serve (localhost POST /session/send)   │
│  persistent agent session (tmux), configurable agent (default claude)               │
│  telegram-bridge   long-poll getUpdates (allowlist) ↔ /session/send; SOLE bot-token │
│                    owner (single consumer) + deterministic OUTBOUND sender           │
│  supercronic crontab   surge */15 (deterministic gate) · digest daily               │
│  grafana-webhook   HTTP receiver (re-pointed "AI Helper Webhook") → triage prompt   │
│  agent TOOLS (HTTP-only, read-only): frank-facts CLI · LogsQL/PromQL curl ·          │
│                                      Grafana alert API · GoatCounter · fetch-text    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Why resilient:** `multi-agent-shell` runs `claude` on an Anthropic subscription (PVC login state,
first `claude login` is a manual op). Zero dependency on LiteLLM/Ollama/GPU — it can narrate a
local-inference outage *because* its brain isn't local inference.

### The four triggers (all deterministically gated)

The **paid cloud agent wakes only on a real event** — cron runs cheap deterministic checks; the
agent runs on escalation / the daily digest / an alert / an inbound question. Edge-triggered +
cooldown (preserving `SURGE_ABS_FLOOR` / `SURGE_VISITOR_FLOOR` / `SURGE_COOLDOWN_HOURS`).

| Trigger | Mechanism | Gate |
|---------|-----------|------|
| **Daily digest** | supercronic cron (daily) | once/day |
| **Traffic surge** | cron */15 → `frank-facts surge-compute` | agent woken ONLY when the deterministic surge math escalates (edge + cooldown) |
| **Grafana alert triage** | `grafana-webhook` (re-pointed contact point) | per firing alert (Grafana gates) |
| **Inbound ask-the-cluster** | `telegram-bridge` getUpdates | per allowlisted DM |

**Delivery is orchestration-owned (deterministic), not agent-owned.** Cron/webhook handlers
`POST /session/send`, get the `payload`, and hand it to `telegram-bridge` to send — the daily
digest is *guaranteed* to post even if the agent is terse. The agent returns a structured payload;
it never owns the bot token. **Fallback:** if `/session/send` returns `status:timeout` or an empty
payload (the driver's nonce-file never appeared), the handler posts the deterministic `frank-facts`
render instead — so a stuck or unauthenticated agent never *silences* the digest.

### Components

1. **alert-agent Deployment** — `multi-agent-shell` image, `replicas:1`, `strategy:Recreate`
   (single Telegram consumer + single tmux session), PVC for `~/.claude` login + agent-session turn
   state, `AGENT_SESSION_SERVE=1`. **Default ServiceAccount, no RBAC** (see boundary below).
2. **telegram-bridge** — single process owning the bot token: long-poll getUpdates, drop
   non-allowlisted chats (WARN), route allowlisted messages → `/session/send` → reply; the
   deterministic outbound sender for cron/webhook narratives. `replicas:1` + `Recreate` mandatory
   (one getUpdates consumer per token — the old analyst gotcha).
3. **frank-facts CLI** — `facts.py`/`surge.py` repackaged: `surge-compute` (the gate), `digest`,
   `surge`, `alert`, + granular `top-attacker-ips` / `top-scanned-paths` / `crowdsec` /
   `scan-patterns` for ad-hoc investigation. Pure deterministic HTTP data access; no LLM, no kube.
   **Dependency decision (settle in the plan):** `facts.py` imports `httpx` + needs Python ≥3.12, so
   it is NOT a drop-in bare-ConfigMap script like `fetch-text` (which is stdlib `urllib` precisely so
   it runs on the image's `python3`). Either (a) port `facts.py` to stdlib `urllib.request` — then
   `tests/test_facts.py` (currently `respx`-based) is rewritten too — or (b) ship it against a baked
   httpx / venv. Recommend (a) for parity with the fetch-text precedent and zero image change.
4. **grafana-webhook receiver** — re-point `apps/grafana-alerting/manifests/contact-points-cm.yaml`
   "AI Helper Webhook" (uid `ai-alert-helper-webhook`) from
   `http://ai-alert-helper.ai-alert-helper-system.svc.cluster.local:8080/alert` to this.
5. **agent guidance** — a `SKILL.md`/SOUL: the job, the tool catalog, the HTTP-only/read-only
   boundary, the output-payload contract.

### Read-only boundary (HTTP-only — match the old posture, do NOT widen the attack surface)

The agent now consumes **untrusted input** (arbitrary Telegram DMs, raw log lines) and feeds it to
an LLM that can run tools — a prompt-injection surface. And its job is to narrate to Telegram, so
any read primitive is also an exfil primitive. Therefore:

- **No Kubernetes credential.** Default ServiceAccount, **no Role/ClusterRole** — exactly the old
  helper's posture (it never had a kube token). Investigation is purely over **read-only HTTP data
  planes**: VictoriaLogs (LogsQL, query-only), VictoriaMetrics (PromQL), the Grafana alert API,
  GoatCounter (stats-scoped token).
- **Cluster-API agentic investigation is explicitly out of scope and out of slice.** That capability
  (`kubectl get`/`describe` driven by an agent) was always intended to be **Sympozium's** charter
  (currently inactive) — a different, more carefully-scoped slice of the cluster. The alert-agent
  does not annex it. (Documented-and-deferred, not silently dropped.)
- Read-only safety = no kube credential + stats-scoped GoatCounter token + query-only log/metric APIs.
- **Named residual — exfil-via-narration.** No-kube bounds the *kube* blast radius, but a successful
  prompt injection can still reflect read-plane data (logs/metrics) into the *outbound narrative* —
  the allowlist gates who can DM the bot, not what the bot says back. Accepted because outbound goes
  only to the allowlisted operator chat, and the read planes carry no secrets beyond observability
  data the operator already sees. (If outbound ever fans out beyond the operator, revisit.)

### Boundaries vs Grafana alerting + health-bridge

Grafana = detection. health-bridge = tile/bug lifecycle. **alert-agent = human-facing narration /
investigation / digest.** It consumes Grafana alerts (the re-pointed webhook) to *explain* them; it
does not manage tiles or issues. No overlap.

### Cutover (clean replace)

1. Stand up the alert-agent (manifests + ArgoCD app on the new image), `claude login` (manual op).
2. Re-point the Grafana "AI Helper Webhook" contact point.
3. Move GoatCounter + Telegram secret refs to the new app's ESO.
4. Verify all four triggers end-to-end.
5. Remove `apps/ai-alert-helper/` + its root Application; delete `ai-alert-helper-system`; update
   the obs-digest gotchas + operating post.

---

## Part C — n8n migration (frank)

n8n-01 currently bolts the driver on via the `agent-session-driver` / `agent-session-bootstrap`
ConfigMaps. Migrate it onto the image-baked `agent-session`:

- Bump `apps/n8n-01` multi-agent-shell sidecar image to the new tag.
- Set `AGENT_SESSION_SERVE=1` on the sidecar (the baked s6 service replaces the postStart bootstrap).
- Remove the `agent-session-driver` + `agent-session-bootstrap` ConfigMaps and their mounts/hook.
- n8n's only session config is `AGENT_SIDECAR_URL=http://localhost:8765` (the driver's default port)
  — **unchanged**. n8n sets none of the `STOA_*` vars itself (it relied on driver/bootstrap
  defaults), so the migration is config-clean; the deprecated aliases are belt-and-suspenders, not
  load-bearing for n8n. Verify content-factory's session still drives end-to-end after the swap.
  (Alias coverage is proven by the ported unit tests, not by n8n's live behaviour.)

This proves the extraction against its original client and removes the duplicate.

---

## Multi-repo sequencing

0. **fr-enablement (agent-images) — already done.** agent-images is fr-enabled: it has
   `docs/superpowers/{specs,plans}`, an existing v2 plan with `vk_version`, and a
   `.devcontainer/dev/` profile (`fr-profiles.yaml` default `dev`). So the agent-session plan is
   authored + dispatched exactly like a frank plan — **no `fr-init` needed**. (An earlier review
   flagged a missing profile; verified false against the live checkout.)
1. **agent-images plan** merges first → CI builds the new `multi-agent-shell` image tag.
   (agent-images CI builds on `push:main`, paths-ignore `docs/**`; validate a branch via
   `gh workflow run build.yaml --ref <branch>` — **confirm in the plan that the dispatch build
   publishes a BRANCH-tagged image** to consume, not a main tag, since the whole gate depends on it.)
2. **frank plan** bumps the image SHA in both `apps/n8n-01` (Part C) and the new `apps/alert-agent`
   (Part B), then proceeds. n8n stays on its current pinned SHA (with its existing ConfigMap driver)
   until Part C explicitly bumps it — so there is no window where n8n is broken. Front-load nothing in
   frank that needs the baked driver before the agent-images tag exists.

## Secrets / manual operations

- **`claude login`** in the alert-agent shell (PVC-resident; like n8n's MO-4): subscription auth,
  first login is manual (operator attaches via tmux/ssh). `# manual-operation`.
- Telegram bot token + chat id (`FRANK_C2_TELEGRAM_BOT_TOKEN` / `_CHAT_ID`) + GoatCounter stats
  token via ESO from Infisical (existing keys).

## Non-goals (v1)

- **Kubernetes / cluster-API access for the agent** — HTTP-only; cluster-API agentic investigation
  is Sympozium's slice (deferred).
- **Shared memory across agents/restarts** — operator is adding it at the image level; out of scope.
  v1 = one persistent session with within-lifetime continuity; context resets on pod restart.
- **Write-actions** — read-only investigation only.
- **antigravity / codex verification** — config-selectable; claude is the wired+verified default.

## Testing

- **agent-images:** ported tmux-mock driver tests (paste + file-write, turn counter, timeout) **plus
  new per-agent-dispatch tests** (none exist today); CI smoke that `agent-session serve` binds in the
  image.
- **frank (deterministic, no LLM):** `frank-facts` unit tests (port `facts.py`/`surge.py` tests —
  rewritten off `respx` if I-1 chooses the stdlib `urllib` port), surge gate escalate/cooldown,
  telegram-bridge allowlist + single-consumer invariant + the timeout→deterministic-render fallback.
- **End-to-end (post-deploy, operator-driven — needs `claude login`):** all four alert-agent
  triggers deliver to Telegram and the agent demonstrably investigates (cites a tool it ran); n8n's
  content-factory session still drives after migration. A layer is not Deployed until observed.
