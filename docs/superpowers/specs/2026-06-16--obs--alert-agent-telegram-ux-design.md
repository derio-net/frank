# Alert-Agent Telegram UX + Agent-Session Driver Reliability

**Layers:** obs (frank — extends `apps/alert-agent`) + agent-images (the `agent-session` driver)
**Status:** Draft
**Date:** 2026-06-16
**Repos:** `derio-net/frank`, `derio-net/agent-images` (multi-repo)
**Extends:** `2026-06-15--obs--agentic-alert-helper-design.md` (the agentic alert-agent this builds on)

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|-------------|------|--------|
| agent-session-coldstart (Thread A, **gating**) | `derio-net/agent-images` | `2026-06-16-agent-session-coldstart` | — |
| 2026-06-16--obs--alert-agent-telegram-ux (Threads B+C) | `derio-net/frank` | `2026-06-16--obs--alert-agent-telegram-ux` | — |

> Multi-repo, **two plans**. The **agent-images** plan (Thread A — make the baked `agent-session`
> driver survive a cold session) **gates** the **frank** plan only for the live end-to-end smoke
> test: the bridge changes (Threads B+C) are independently valuable and independently unit-tested,
> but the post-merge "cold DM gets answered" proof needs the fixed driver image deployed.
> Sequence: agent-images merges → CI builds a new `multi-agent-shell` tag → the frank PR bumps the
> image SHA in `apps/alert-agent/manifests/deployment.yaml` (the cross-repo join) → operator merges
> → smoke test.

## Problem

The agentic alert-agent (PR #563, live) works end-to-end on a **warm** agent session — a synthetic
Grafana alert was triaged and delivered to Telegram. But three UX/reliability gaps remain, surfaced
when the operator tried real Telegram interaction:

1. **Cold-start race — inbound DMs go unanswered.** The baked `agent-session` driver
   (`multi-agent-shell/rootfs/usr/local/lib/multi-agent-shell/agent-session`) creates a tmux session
   with `tmux new-session -d … 'claude --permission-mode auto'` and **returns immediately**. `send()`
   then pastes the message and presses Enter after a fixed `SETTLE_S=0.5s`. On a **cold** pane
   (claude still booting its TUI, ~5–8s) the Enter lands before the REPL accepts input → dropped →
   the turn times out → the bridge posts its "(the agent did not return a reply…)" fallback. The
   operator's `/edge-traffic` and `/help` both hit this. Turn 2+ on a warm pane works perfectly.
   Bumping `SETTLE_S` is a band-aid; the structural fix is a readiness gate. A *second* swallowed-Enter
   source: the first-ever `--permission-mode auto` entry shows a one-time interstitial warning that
   eats an Enter — the same class of bug `pretrust()` already fixes for the folder-trust dialog.

2. **Slash commands and the argless-from-menu trap.** The old `ai-alert-helper` exposed Telegram
   commands (`/edge-traffic`, `/help`, …) that needed positional arguments. Telegram's bot command
   **menu sends a command immediately when tapped** — no chance to append an argument — so a
   parameterized command always arrived bare and failed. The bridge currently has *no* command
   layer at all: every allowlisted DM is forwarded verbatim to `/session/send`.

3. **No receipt/answer feedback.** A DM that triggers a multi-second (or timing-out) turn gives the
   operator no signal that the message was even received. The single getUpdates consumer blocks in
   `process_update` for the whole turn, so the chat looks dead until the reply (or fallback) lands.

## Thread A — Driver cold-start reliability (`agent-images`)

All three changes are in the single `agent-session` driver file. Stdlib-only, as the rest of it.

**A1. Readiness gate in `ensure_session`.** After `tmux new-session`, poll `tmux capture-pane -p -t
<session_id>` until the claude REPL input prompt is rendered and accepting input, then return. A
hard timeout (`AGENT_SESSION_READY_TIMEOUT_S`, default ~30s) caps the wait → on timeout, log to
stderr and proceed best-effort (never hang a request forever). Covers **every** session id —
including the lazily-created per-chat DM sessions (`alert-agent-tg-<chat>`) and the
`alert-agent-ops` handler session — which is why a boot-time pre-warm of one session would not be
enough. The readiness marker is a stable substring of the claude prompt box; the **exact marker is
verified live against the running pod** during implementation (`tmux capture-pane` on a real cold
boot), with a permissive fallback (pane non-empty AND unchanged across two consecutive polls) so a
marker drift across claude versions degrades to a stability heuristic rather than a hard fail.

**A2. Seed the auto-mode-entry flag in `pretrust()`.** Alongside `hasTrustDialogAccepted=True`, set
the first-run auto-mode-entry warning flag so the interstitial never appears to eat the first Enter.
The **exact `~/.claude.json` key is verified live** against the running pod's file during
implementation (candidate: `hasSeenAutoModeEntryWarning`) — `pretrust()` writes it idempotently the
same way it writes the trust flag, tolerant of an absent/corrupt file.

**A3. Verified submit in `submit()`.** After the post-paste Enter, re-capture the pane; if the
pasted message text is still sitting in the input box (not submitted), press Enter once more. A
belt-and-suspenders that makes submission self-healing even if the A1 readiness marker is wrong on a
future claude version. Single retry only — no unbounded loop.

**Test (Thread A):** unit tests with a tmux mock (mirroring the existing extract plan's driver
tests): readiness gate polls then returns once the mocked pane reports ready; `pretrust()` writes
both flags; verified-submit retries Enter exactly once when the mocked pane still shows the message,
and not at all when it cleared. The true proof is the post-merge live smoke test (below).

## Thread B — Slash commands (`frank` bridge)

A new command layer in `apps/alert-agent/telegram-bridge/tg_bridge/bridge.py`. No argument parsing —
commands are **prompt templates** expanded into one English instruction for the agent, which already
has the `frank-facts` CLI as a shell tool. The argless trap is *dissolved*, not handled: there is no
positional argument to be missing.

**`COMMANDS` registry** — single source of truth for both `setMyCommands` (the Telegram menu) and
routing. Each entry: a short menu description + either a **static** handler or a **prompt template**.

| Command | Kind | Behaviour |
|---------|------|-----------|
| `/help` | static | Bridge renders the command list directly from the registry — never touches the agent (works when the agent is cold/unauthenticated). |
| `/digest` | template | "Run the daily digest (`frank-facts digest`) and summarize for the operator." |
| `/surge` | template | "Report current surge status (`frank-facts surge`)." |
| `/edge-traffic` | template | "Summarize Hop edge traffic — top scanned paths and attacker IPs (`frank-facts top-scanned-paths`, `top-attacker-ips`), last 24h by default." |
| `/security` | template | "Summarize the security picture — CrowdSec decisions and scan patterns (`frank-facts crowdsec`, `scan-patterns`), plus any notable Falco events." |
| `/status` | template | "Give a short cluster + alert-agent health snapshot from the HTTP probes you can reach (Derio Ops / blackbox)." |

**`expand_command(text) -> (kind, payload)`** — pure function: strips the leading `/`, splits the
command word from any trailing free-text the operator *did* type. Returns:
- `("static", help_text)` for `/help`;
- `("prompt", template + appended-args + "Use sensible defaults and answer now; if a parameter is
  truly needed, pick the obvious default and state which you used.")` for a templated command (the
  **Defaults & proceed** philosophy, encoded once in the suffix);
- `("unknown", "Unknown command — try /help")` for an unrecognized `/foo`.

**`setMyCommands` on startup** — best-effort; a failure logs a WARN and the bridge runs anyway (the
menu is a nicety, not a dependency). Called once at `poll_loop` entry.

**`process_update` routing** — a leading `/` dispatches through `expand_command`: static → reply
directly (no `session_send`); prompt → `session_send` with the expanded instruction; unknown →
reply directly. **No leading `/` → unchanged free-text Q&A path** (forward verbatim to the agent).

## Thread C — Ack/answer reactions (`frank` bridge)

`setMessageReaction` on the operator's own message gives instant, in-place feedback.

- **On receipt** (before `session_send`, inside `process_update` once the message is allowlisted): set
  ⚡ via `setMessageReaction(chat_id, message_id, [{type:"emoji", emoji:"⚡"}])`.
- **On completion**: set 👍 for a real agent answer; **🤔** when only the deterministic fallback was
  posted (agent timed out / returned no payload). Reactions **replace** (⚡ → 👍/🤔), so the final
  glyph tells the operator whether the brain actually answered.
- **Best-effort, never blocking.** A new `tg_react(chat_id, message_id, emoji)` helper wraps
  `setMessageReaction` in try/except — a reaction API failure logs a WARN and is swallowed so it can
  never delay or suppress the reply. Static-command replies (`/help`, unknown) get ⚡→👍 too (they
  always "succeed"). ⚡ and 👍/🤔 are all in Telegram's allowed free-reaction set.

`process_update` gains the `message_id` (already present in the update) and threads it through.
`render_payload(resp) is not None` is the existing success/fallback discriminator — reuse it to pick
👍 vs 🤔.

## Cross-cutting — keep the poll loop synchronous (YAGNI)

The single getUpdates consumer (required: one consumer per bot token) stays **synchronous**. The ⚡
reaction fires *before* the blocking `session_send`, so the operator gets instant receipt feedback
even while a turn runs. Thread A collapses warm-turn latency to a few seconds, so the historical
~120s block largely evaporates. Per-update worker threads (with per-session locks to stop two DMs to
the same chat interleaving pastes into one tmux session) are **deferred** until a real multi-operator
need exists — a single-operator ops bot does not justify the concurrency surface.

## Multi-repo sequencing

0. **agent-images is fr-enabled** (verified in the parent work — `.devcontainer/dev` + v2 plans).
1. **agent-images plan (Thread A) merges first** → CI builds a new `multi-agent-shell` image tag.
   (agent-images CI builds on `push:main`, `paths-ignore: docs/**`; a branch is validated via
   `gh workflow run build.yaml --ref <branch>`.)
2. **frank plan (Threads B+C)** implements the bridge changes (independently unit-tested, no image
   dependency) and **bumps `apps/alert-agent/manifests/deployment.yaml`** to the new image SHA — the
   cross-repo join. The SHA only exists after step 1 merges + builds, so the bump is the **last**
   frank step (back-loaded): the operator reports the agent-images tag, the bump lands on the same
   frank PR, then the operator merges.
3. The bridge changes do **not** require the new image to *function* (the bridge talks to the driver
   over HTTP; A's behaviour change is internal to the driver). The new image is required only for
   the live cold-start smoke test to pass.

`depends_on` reaches only within a plan — this cross-repo ordering lives here in the spec and in PR
sequencing, not in either plan's `depends_on`.

## Test Plan (post-merge, operator-driven)

The deliverable is a deployed bot; the real proof needs the operator's Telegram client and a cold
pod. After **both** PRs merge and ArgoCD rolls the new `multi-agent-shell` image:

1. **Cold-start answered.** Restart the alert-agent pod (`kubectl -n alert-agent rollout restart
   deploy/alert-agent`) so the agent session is cold. From Telegram, send a free-text DM (e.g.
   "what's the cluster status?"). **Expect:** ⚡ appears on the message within ~1s, then a real agent
   answer within seconds and the reaction flips to 👍 — not the "(the agent did not return a reply…)"
   fallback.
2. **Slash command, argless.** Tap `/edge-traffic` from the Telegram command menu (sends it bare).
   **Expect:** ⚡ → a defaults-based edge-traffic summary that states the default window it used →
   👍.
3. **Static `/help`.** Tap `/help`. **Expect:** an immediate command list rendered by the bridge
   (no agent latency), ⚡→👍.
4. **Fallback reaction.** (Optional, hard to force) If a turn ever times out, confirm the terminal
   reaction is 🤔, not 👍.

## Named gaps

- **Readiness marker fragility.** The exact claude prompt substring can change across versions; A1's
  stability-heuristic fallback (non-empty + unchanged across two polls) is the mitigation, but a
  future claude TUI redesign may need the marker re-verified. Documented as a gotcha.
- **Auto-mode flag name.** `hasSeenAutoModeEntryWarning` is the candidate; the live `~/.claude.json`
  is the source of truth, verified at implementation. If claude renames it, A3's verified-submit
  still catches the swallowed Enter (defense in depth).
- **Reaction permission.** In a private DM the bot can always react; no group-permission edge here.

## Counter-arguments considered

- **"Just pre-warm one session at boot."** Rejected: the bridge uses a *per-chat* session id and the
  handlers use `alert-agent-ops`, so there are multiple lazily-created sessions — only a readiness
  gate in `ensure_session` covers them all. Pre-warm is at best a latency nicety on one id.
- **"Parse command arguments properly (inline keyboard)."** Rejected (operator chose Defaults &
  proceed): an LLM brain with the `frank-facts` CLI makes argument parsing redundant and adds
  stateful pending-command tracking to a deliberately stateless bridge.
- **"Thread the poll loop for responsiveness."** Deferred: ⚡-before-block already gives receipt
  feedback, and Thread A removes the latency that made blocking painful; threading adds per-session
  locking for no single-operator benefit.
